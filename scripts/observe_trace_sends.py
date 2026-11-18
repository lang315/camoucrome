"""Surfaces sent from a startup trace: channels.json and matches.json for an external spawner (no patchright).

Reads the camou.send.* events of a --trace-startup JSON trace (contract: additions/camoucfg/observe_tables.h)
and applies the same join, partial, missing and cut rules as DecodeTables. Values stay on the host: the trace, the
truth and the bodies hold them; channels.json, matches.json and trace_sends.json carry names, counts and matches only.
"""
import argparse
import base64
import binascii
import json
import pathlib
import re
import sys

import observe_drive as d
import sites


def load_events(path):
    """The send events of a Chrome JSON trace ({"traceEvents": [...]} or a bare list); a trace killed before its
    closing brackets is repaired."""
    text = pathlib.Path(path).read_text(encoding="utf-8")
    data = None
    for tail in ("", "]}", "]"):
        try:
            data = json.loads(text.rstrip().rstrip(",") + tail if tail else text)
            break
        except ValueError:
            continue
    if data is None:
        raise ValueError("trace is not JSON")
    events = data.get("traceEvents", []) if isinstance(data, dict) else data
    return [e for e in events if isinstance(e, dict) and str(e.get("name", "")).startswith("camou.send.")]


def _uint(args, key):
    """base::StringToUint64: ASCII digits (one optional '+'), no space, no '_', no sign '-', below 2**64."""
    text = str(args.get(key, ""))
    if not re.fullmatch(r"\+?[0-9]+", text):
        return None
    v = int(text)
    return v if v < 2 ** 64 else None


def _cut(args):
    c = str(args.get("cut", ""))
    return c not in ("", "0")


def _b64(s):
    try:
        return base64.b64decode(s, validate=True)
    except (binascii.Error, ValueError):
        return None


def _site_ok(site, top_site, counts):
    if not top_site:
        return True
    if not site:  # a worker (ws) or an unattributed request: kept, counted apart
        counts["no_site"] += 1
        return True
    if site == top_site:
        counts["matched"] += 1
        return True
    return False


def assemble(events, top_site=""):
    """(requests, frames, counts) in observe_drive's record shapes. Mirrors DecodeTables' loader join."""
    counts = dict.fromkeys(("http", "ws", "partial", "missing", "cut", "file", "no_site", "ws_undecodable", "matched"), 0)
    loaders = {}
    frames = []
    for ev in events:
        args = ev.get("args") or {}
        name = ev["name"]
        if name == "camou.send.ws":
            if not _site_ok(args.get("site", ""), top_site, counts):
                continue
            raw = _b64(args.get("b64", ""))
            if raw is None:
                counts["ws_undecodable"] += 1
                continue
            counts["ws"] += 1
            counts["cut"] += _cut(args)
            frames.append({"url": "ws://" + str(args.get("endpoint", "")), "dir": "sent",
                           "opcode": _uint(args, "opcode") or 2, "payload_b64": base64.b64encode(raw).decode()})
            continue
        if name not in ("camou.send.http", "camou.send.body", "camou.send.file"):
            continue
        lid = _uint(args, "loader")
        if not lid:
            continue
        ld = loaders.setdefault(lid, {"http": None, "elements": {}, "files": set(), "cut": False})
        if name == "camou.send.http":
            ld["http"] = ld["http"] or args  # the first wins
        elif name == "camou.send.file":
            e = _uint(args, "element")
            if e is not None:
                ld["files"].add(e)
        else:
            e, off, raw = _uint(args, "element"), _uint(args, "offset"), _b64(args.get("b64", ""))
            if e is None or off is None or raw is None:
                continue  # a failed decode drops that fragment
            ld["elements"].setdefault(e, {}).setdefault(off, raw)  # a 307/308 repeat of an offset is kept once
            ld["cut"] |= _cut(args)
    requests = []
    for ld in loaders.values():
        http = ld["http"]
        if http is None or not _site_ok(http.get("top_site", ""), top_site, counts):
            continue
        body, gap = b"", False
        for frags in (ld["elements"][i] for i in sorted(ld["elements"])):
            nxt = 0
            for off in sorted(frags):
                gap |= off != nxt
                nxt = off + len(frags[off])
                body += frags[off]
        n = _uint(http, "elements") or 0
        if n:
            seen = set(ld["files"]) | set(ld["elements"])
            gap |= len(seen) != n or max(seen, default=0) >= n
        if not body and not ld["files"] and n == 0:
            continue
        counts["http"] += 1
        counts["cut"] += ld["cut"]
        counts["file"] += len(ld["files"])
        rec = {"url": "http://" + str(http.get("endpoint", "")), "method": http.get("method", "POST"),
               "content_type": http.get("content_type", ""), "initiator": "", "via": "trace", "cut": ld["cut"]}
        if not body:
            if ld["files"]:  # file elements only: a row of kind file, their bytes are never read
                requests.append({**rec, "body_b64": "", "missing": False, "file": True})
                continue
            counts["missing"] += 1
            requests.append({**rec, "body_b64": "", "missing": True})
        elif gap:
            counts["partial"] += 1  # not decoded
        else:
            requests.append({**rec, "body_b64": base64.b64encode(body).decode(), "missing": False})
    return requests, frames, counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("trace", nargs="?", help="startup trace JSON")
    ap.add_argument("--truth", help="truth.json: the TRUTH_JS result, read back from the page")
    ap.add_argument("--out", help="output directory (channels.json, matches.json, bool_fields.json, trace_sends.json)")
    ap.add_argument("--site", default="facebook", help="site profile (hooks that expand field values)")
    ap.add_argument("--top-site", default="", help="keep one top-level site, e.g. https://facebook.com")
    ap.add_argument("--print-truth-js", action="store_true",
                    help="print the async function that reads the truth; evaluate it with awaitPromise on a 127.0.0.1 page")
    a = ap.parse_args(argv)
    if a.print_truth_js:
        print(d.TRUTH_JS)
        return 0
    if not (a.trace and a.truth and a.out):
        ap.error("trace, --truth and --out are required")
    events = load_events(a.trace)
    if not events:
        print("UNMEASURED: no send events (was disabled-by-default-camou.observe.send in --trace-startup?)")
        return 2
    try:
        site = sites.load(a.site)
    except sites.SiteError as e:
        print(f"UNMEASURED site: {e}")
        return 3
    requests, frames, counts = assemble(events, a.top_site)
    if a.top_site and not counts["matched"]:  # sends with no site (workers) do not count as a match
        n = sum(e["name"] in ("camou.send.http", "camou.send.ws") for e in events)
        print(f"UNMEASURED: --top-site matched none of the {n} send(s) (use the SchemefulSite form: scheme://host, no port, registrable domain)")
        return 2
    if not (counts["http"] or counts["ws"]):
        print("UNMEASURED: no usable send (only orphan bodies, requests with no elements or undecodable messages)")
        return 2
    if not counts["ws"] and not any(not r.get("missing") for r in requests):
        print(f"UNMEASURED: every request was partial or missing (partial {counts['partial']}, missing {counts['missing']}) and no ws message")
        return 2
    truth = json.loads(pathlib.Path(a.truth).read_text(encoding="utf-8"))
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    d.write_tables(out, "trace", requests, frames, truth, site)
    (out / "trace_sends.json").write_text(json.dumps(counts, indent=1, sort_keys=True), encoding="utf-8")
    print("trace sends: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    if counts["no_site"]:
        print(f"note: {counts['no_site']} send(s) had no top site (workers, unattributed requests); kept")
    return 0


if __name__ == "__main__":
    sys.exit(main())

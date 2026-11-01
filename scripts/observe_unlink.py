"""Facebook profile unlinking (social mode part 2): which fields link three fork profiles on one host.

Runs on the host after observe-auto's lf and lc arms. It reads each arm's capture, compares
values across profiles in memory, and writes only field names, value classes, counts and classes
(spec docs/superpowers/specs/2026-10-30-fb-unlink-design.md, local).
"""
import argparse
import collections
import hashlib
import json
import pathlib
import sys
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import observe_drive as d  # noqa: E402
import sites  # noqa: E402



def endpoint_path(url, endpoints=None):
    p = urllib.parse.urlsplit(url).path.rstrip("/")
    endpoints = endpoints if endpoints is not None else sites.load().unlink_endpoints
    return next((e for e in endpoints if e.rstrip("/") == p), None)


def profile_values(requests, endpoints=None):
    """{"<endpoint> <path>": [values]} over one profile's captured POST bodies on the site's unlink endpoints."""
    out = collections.defaultdict(list)
    for r in requests:
        ep = None if r.get("missing") else endpoint_path(r.get("url", ""), endpoints)
        if ep:
            for path, v in d.fields(d._b64(r["body_b64"]), r.get("content_type", ""))[1]:
                out[f"{ep} {path}"].append(v)
    return dict(out)


def _form(v):
    # shortcut: an opaque part keeps only its length, so two opaque parts of one length read as equal; multipart file parts only
    return json.dumps(v, sort_keys=True, default=lambda o: f"opaque<{getattr(o, 'n', '?')}>")


def digest(values):
    """One profile's values for a path, order-free: the hash of its sorted distinct forms."""
    return hashlib.sha256("\n".join(sorted({_form(v) for v in values})).encode()).hexdigest()


def field_key(path, fields):
    """The site's fields.json key a captured path belongs to: equal to it, or ending in '.' + key (longest key wins)."""
    p = path.split(" ", 1)[1]
    for k in sorted(fields, key=len, reverse=True):
        if p == k or p.endswith("." + k):
            return k
    return None


def _same(a, b):
    return type(a) is type(b) and a == b  # step2_rows._same: type-strict, so True is not 1


def limit_kind(key, doc, light):
    """"limit", or "light-limit" (owner ruling 2026-10-30: DPR 1 by design, accepted in a light run only), or None."""
    if key in doc.get("limits", {}):
        return "limit"
    return "light-limit" if light and key in doc.get("light_limits", {}) else None


def explain(key, doc, constants, accepted, fork_vals, stock_vals, light=False):
    """Why a gap is acceptable, or None: an owner limit, a machine constant, or an accepted default (ruling R6)."""
    if limit_kind(key, doc, light):
        return limit_kind(key, doc, light)
    leaves = (doc["fields"].get(key) or {}).get("leaves") or []
    prefixes = tuple(k for k in constants if k.endswith("."))  # step2_rows.unexplained: a key ending in '.' is a prefix
    if any(leaf in constants or leaf.startswith(prefixes) for leaf in leaves):
        return "machine-constant"
    for leaf in leaves:
        row = accepted.get(leaf)
        if row and stock_vals and all(_same(v, row["value"]) for v in fork_vals + stock_vals):
            return "accepted-default"
    return None


def classify(fork, stock, doc, constants, accepted, light=False, fork_only=False, prediction=None):
    """fork, stock: one profile_values() dict per profile. Returns the unlink document (no values)."""
    fields, ip_bound = doc["fields"], set(doc["ip_bound"])
    rows, counts = [], collections.Counter()
    paths = sorted(set().union(*fork, *stock))
    for path in paths:
        fv = [p[path] for p in fork if path in p]
        sv = [p[path] for p in stock if path in p]
        key = field_key(path, fields)
        fd, sd = len({digest(v) for v in fv}), len({digest(v) for v in sv})
        r = {"field": path, "key": key, "value_class": d.value_class((fv or sv)[0][0]),
             "fork_n": len(fv), "stock_n": len(sv), "fork_distinct": fd, "stock_distinct": sd}
        if key in ip_bound:
            cls = "ip-bound"
        elif len(fv) < 2:
            cls = "sparse"
        elif fd > 1:
            cls = "unlinked"
        elif fork_only and key is None:
            cls = "unmapped-same"  # no stock to tell a site constant from a link: listed for a review of its names
        elif key is None and len(sv) < 2:
            cls = "unmapped-thin"  # owner ruling 2026-11-01: too few stock loads to call it a gap or a site constant
        elif key is None and len(sv) >= 2 and sd == 1 and digest(sv[0]) == digest(fv[0]):
            cls = "site-constant"
        elif sd > 1:
            cls = "pinned"
            if limit_kind(key, doc, light):
                r["explained_by"] = limit_kind(key, doc, light)
            else:
                counts["net_pinned"] += 1
        else:
            cls = "gap"
            r["explained_by"] = explain(key, doc, constants, accepted, fv[0], sv[0] if sv else [], light)
            r["low_cardinality"] = all(d._weak(v) for v in fv[0])
            if r["explained_by"] is None and fork_only and (prediction or {}).get(key) == "shared":
                r["explained_by"] = "predicted-shared"  # every identity carries one value: equal is expected, not a link
            if r["explained_by"] is None:
                counts["net_gap"] += 1
        r["class"] = cls
        counts[cls] += 1
        rows.append(r)
    seen = {r["key"] for r in rows if r["key"] and r["fork_n"]}
    for k in sorted(set(fields) - seen):
        rows.append({"field": k, "key": k, "class": "absent"})
        counts["absent"] += 1
    counts["raw_gap"] = counts.pop("gap", 0)
    in_fork = {p for f in fork for p in f}
    in_stock = {p for s in stock for p in s}
    sjd = next((r["fork_distinct"] for r in rows if r.get("key") == "sjd" and "fork_distinct" in r), None)
    names = ("net_gap", "raw_gap", "pinned", "net_pinned", "unlinked", "ip-bound", "site-constant") \
        + (() if fork_only else ("unmapped-thin",)) + ("sparse", "absent")
    out = {"rows": rows, "counts": {k: counts.get(k, 0) for k in names},
           "fork_only": sorted(in_fork - in_stock), "stock_only": sorted(in_stock - in_fork), "sjd_fork_distinct": sjd}
    if fork_only:
        out["counts"]["unmapped-same"] = counts.get("unmapped-same", 0)
        out["fork_only_mode"] = True
    return out


def lookup(identity, key):
    if key.startswith("launch."):
        return identity["launch"].get(key[len("launch."):])
    return identity["config"].get(key)


def predict(fields, identities):
    """B (ruling R2): a field whose identity keys take one value in every identity is predicted shared."""
    out = {}
    for k, f in fields.items():
        keys = f.get("keys")
        if keys is None:
            out[k] = "unknown"
        else:
            seen = {json.dumps([lookup(i, x) for x in keys], sort_keys=True) for i in identities}
            out[k] = "varies" if len(seen) > 1 else "shared"
    return out


def attach_prediction(doc, prediction):
    """A measured gap or pinned row predicted to vary, or an unlinked row predicted shared, is a disagreement:
    facebook transforms the value before sending it, or the identity does not reach the field."""
    bad = []
    for r in doc["rows"]:
        p = prediction.get(r.get("key"))
        if p is None:
            continue
        r["prediction"] = p
        if (p == "varies" and r["class"] in ("gap", "pinned")) or (p == "shared" and r["class"] == "unlinked"):
            bad.append(r["field"])
    doc["disagreements"] = bad
    return doc


def has_bz(requests, site=None):
    site = site or sites.load()
    return any(not r.get("missing") and endpoint_path(r.get("url", ""), site.unlink_endpoints) == site.beacon_path
               for r in requests)


def render(doc):
    c = doc["counts"]
    head = "UNLINK " + " ".join(f"{k}={c[k]}" for k in c) + f" disagreements={len(doc['disagreements'])}" \
        + f" sjd_fork_distinct={doc['sjd_fork_distinct'] if doc['sjd_fork_distinct'] is not None else '-'} seeds={doc.get('seeds', '-')}"
    lines = [head, ""]
    sections = [("Gaps (net)", lambda r: r["class"] == "gap" and not r.get("explained_by")),
                ("Gaps (explained)", lambda r: r["class"] == "gap" and r.get("explained_by")),
                ("Pinned (net)", lambda r: r["class"] == "pinned" and not r.get("explained_by")),
                ("Pinned (explained)", lambda r: r["class"] == "pinned" and r.get("explained_by")),
                ("Site constants (unmapped, same everywhere: review the names)", lambda r: r["class"] == "site-constant")]
    if "unmapped-thin" in c:
        sections.append(("Unmapped, fewer than two stock loads (review the names)", lambda r: r["class"] == "unmapped-thin"))
    sections.append(("Absent", lambda r: r["class"] == "absent"))
    if doc.get("fork_only_mode"):
        sections.append(("Unmapped, same in all three (review the names)", lambda r: r["class"] == "unmapped-same"))
    for title, keep in sections:
        rs = [r for r in doc["rows"] if keep(r)]
        lines += [f"## {title} ({len(rs)})", ""]
        lines += [f"- `{r['field']}` {r.get('value_class', '')} fork {r.get('fork_distinct', '-')}/{r.get('fork_n', '-')}"
                  f" stock {r.get('stock_distinct', '-')}/{r.get('stock_n', '-')}"
                  f"{' low-cardinality' if r.get('low_cardinality') else ''}"
                  f"{' explained: ' + r['explained_by'] if r.get('explained_by') else ''}"
                  f"{' predicted: ' + r['prediction'] if r.get('prediction') else ''}" for r in rs]
        lines.append("")
    if doc.get("fork_only_mode"):
        seen = doc.get("not_seen_logged_out")
        if seen is None:
            lines += ["## Not seen logged out: no logged-out reference given", ""]
        else:
            lines += [f"## Not seen logged out ({len(seen)})", ""] + [f"- `{n}`" for n in seen] + [""]
        tail = (("Disagreements with the prediction", doc["disagreements"]),)
    else:
        tail = (("Disagreements with the prediction", doc["disagreements"]),
                ("Fork only", doc["fork_only"]), ("Stock only", doc["stock_only"]))
    for title, names in tail:
        lines += [f"## {title} ({len(names)})", ""] + [f"- `{n}`" for n in names] + [""]
    return "\n".join(lines)


def _load(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fork", nargs=3, required=True, metavar="ARM_DIR")
    ap.add_argument("--stock", nargs=3, metavar="ARM_DIR")
    ap.add_argument("--fork-only", action="store_true", help="logged-in unlinking (S5): three fork profiles, no stock")
    ap.add_argument("--logged-out", help="the unlink.json of a logged-out run: lists the paths it never saw")
    ap.add_argument("--settings", required=True, help="a dir with machine_constants.json and accepted_defaults.json (fields come from the site profile)")
    ap.add_argument("--site", default="facebook")
    ap.add_argument("--seeds", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--md", required=True)
    ap.add_argument("--light", action="store_true", help="a light run: light_limits in the site's fields.json explain rows like limits")
    a = ap.parse_args(argv)
    if bool(a.fork_only) == bool(a.stock):
        ap.error("give either --stock or --fork-only")
    stock_dirs = a.stock or []
    try:
        site = sites.load(a.site)
    except sites.SiteError as e:
        print(f"UNMEASURED site: {e}")
        return 3
    caps = [d.read_jsonl(pathlib.Path(x) / "capture" / "requests.jsonl") for x in a.fork + stock_dirs]
    empty = [pathlib.Path(x).name for x, c in zip(a.fork + stock_dirs, caps) if not has_bz(c, site)]
    if empty:
        print(f"UNMEASURED unlink: no {site.beacon_path} body in " + ", ".join(empty), file=sys.stderr)  # ruling R5
        return 3
    s = pathlib.Path(a.settings)
    doc = _load(site.dir / "fields.json")
    prediction = predict(doc["fields"], [_load(pathlib.Path(x) / "capture" / "identity.json") for x in a.fork])
    out = classify([profile_values(c, site.unlink_endpoints) for c in caps[:3]], [profile_values(c, site.unlink_endpoints) for c in caps[3:]], doc,
                   _load(s / "machine_constants.json")["leaves"], _load(s / "accepted_defaults.json")["leaves"],
                   light=a.light, fork_only=a.fork_only, prediction=prediction)
    attach_prediction(out, prediction)
    if a.fork_only:
        ref = pathlib.Path(a.logged_out) if a.logged_out else None
        if ref and ref.exists():
            before = {r["field"] for r in _load(ref)["rows"] if r.get("fork_n")}
            out["not_seen_logged_out"] = sorted({r["field"] for r in out["rows"] if r.get("fork_n")} - before)
        else:
            out["not_seen_logged_out"] = None
    out["seeds"] = a.seeds
    pathlib.Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    pathlib.Path(a.md).write_text(render(out), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

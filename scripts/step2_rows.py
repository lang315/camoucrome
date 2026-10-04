"""Roadmap step 2, the pure half: rows, their labels, the argv and version
preconditions, run-to-run comparison and the tables
(docs/superpowers/specs/2026-10-04-step2-measurement-design.md). No browser,
no host: test_step2_rows.py runs it in CI. measure_step2.py is the browser half."""
import collections
import json
import re

from oracle_rules import SHAPE_ONLY, flatten  # noqa: F401  (flatten is re-exported for measure_step2)

MODES = ("headed", "headless")
ARMS = ("control", "fork")
ABSENT = "<absent>"
UNMEASURED = "UNMEASURED"

# Row name (or dotted prefix) -> why it changes between runs of the same arm.
# Calibrated by the null runs of Task 7; every entry carries its reason.
VOLATILE = {
    "net.ja3": "Chrome permutes its TLS extension order per connection",
}
# Row name (or dotted prefix) -> why the fork's value differs from stock's by design.
EXPECTED = {
    "net.user_agent": "the identity's User-Agent",
    "link": "a record of what two profiles share, not a fork-vs-control finding",
}
# Oracle leaves compared by type only: a value difference is the identity's or the machine's.
SHAPE = {f"oracle.{k}": "identity- or machine-bound; compared by type" for k in SHAPE_ONLY}
# Identity-derived flags the client adds to the fork arm only (launcher.build_args).
ARGV_ALLOWED = ("--accept-lang=", "--user-data-dir=", "--window-size=", "--force-device-scale-factor=")
# Regexes over detector text lines that change between runs (clock, IP, session ids). Task 7 calibrates.
VOLATILE_LINES = []


def _reason(name, table):
    return next((why for k, why in table.items() if name == k or name.startswith(k + ".")), None)


def label_rows(control, fork):
    """Every row whose value differs between the arms, sorted by name, as
    (name, control value, fork value, label, reason). A row missing on one side
    reads ABSENT. A detector that did not settle is `unmeasured`, never a difference."""
    out = []
    for name in sorted(set(control) | set(fork)):
        c, f = control.get(name, ABSENT), fork.get(name, ABSENT)
        if c == f:
            continue
        site = ".".join(name.split(".")[:2])
        if UNMEASURED in (c, f) or UNMEASURED in (control.get(site), fork.get(site)):
            out.append((name, c, f, "unmeasured", "a detector page did not settle"))
        elif _reason(name, VOLATILE):
            out.append((name, c, f, "volatile", _reason(name, VOLATILE)))
        elif _reason(name, SHAPE):
            same = type(c) is type(f)
            out.append((name, c, f, "expected" if same else "unexpected", _reason(name, SHAPE) if same else "type changed"))
        elif _reason(name, EXPECTED):
            out.append((name, c, f, "expected", _reason(name, EXPECTED)))
        else:
            out.append((name, c, f, "unexpected", ""))
    return out


def argv_problems(control_argv, fork_argv, allowed=ARGV_ALLOWED):
    """Differences between the two browser argvs outside `allowed` prefixes.
    argv[0] (the executable) is not compared. An unread argv is a problem: an
    empty list would otherwise compare equal to nothing at all."""
    if not control_argv or not fork_argv:
        return [f"argv not read: control={len(control_argv)} fork={len(fork_argv)} elements"]
    keep = lambda argv: [a for a in argv[1:] if not a.startswith(tuple(allowed))]  # noqa: E731
    c, f = keep(control_argv), keep(fork_argv)
    return [f"control only: {a}" for a in c if a not in f] + [f"fork only: {a}" for a in f if a not in c]


def version_problems(versions, pin):
    return [f"{arm} is {v}, the pin is {pin}" for arm, v in versions.items() if v != pin]


def network_rows(data):
    """tls.peet.ws/api/all -> rows. Header NAMES in sent order; values the identity sets stay out."""
    tls, h2 = data.get("tls") or {}, data.get("http2") or {}
    headers = next((f.get("headers") for f in h2.get("sent_frames") or [] if f.get("frame_type") == "HEADERS"), None) or []
    return {"net.http_version": data.get("http_version"), "net.ja4": tls.get("ja4"), "net.ja3": tls.get("ja3"),
            "net.akamai": h2.get("akamai_fingerprint"), "net.h2_order": [h.split(": ", 1)[0] for h in headers],
            "net.user_agent": data.get("user_agent")}


def stability_rows(first, second):
    """Two flattened oracle reports from one profile, launched twice."""
    keys = set(first) | set(second)
    return {"stab.compared": len(keys), "stab.changed": sorted(k for k in keys if first.get(k, ABSENT) != second.get(k, ABSENT))}


def link_rows(a, b):
    """Two flattened oracle reports from two profiles of one arm: the leaves they share."""
    return {"link.total": len(set(a) | set(b)), "link.shared": sorted(k for k in a if k in b and a[k] == b[k])}


def parse_tabbed(text):
    """sannysoft: its result tables give one row per line, cells tab-separated."""
    out = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.split("\t")]
        if len(cells) >= 2 and cells[0]:
            out[cells[0]] = " | ".join(cells[1:])
    return out


def parse_colon(text):
    """CreepJS: "label: value" lines; the first occurrence of a label wins."""
    out = {}
    for line in text.splitlines():
        k, sep, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if sep and k and v and len(k) <= 40:
            out.setdefault(k, v)
    return out


PARSERS = {"sannysoft": parse_tabbed, "creepjs": parse_colon}


def line_diff(control_text, fork_text):
    """(lines only the control shows, lines only the fork shows), as multisets,
    stripped, blank and VOLATILE_LINES-matching lines dropped."""
    def lines(t):
        return collections.Counter(s for s in (x.strip() for x in t.splitlines())
                                   if s and not any(re.search(p, s) for p in VOLATILE_LINES))
    c, f = lines(control_text), lines(fork_text)
    return sorted((c - f).elements()), sorted((f - c).elements())


def compare_runs(a, b):
    """Every row on which two runs disagree, outside VOLATILE, as (probe/arm/mode/row, a, b)."""
    out = []
    for probe in sorted(set(a["rows"]) | set(b["rows"])):
        for arm in ARMS:
            for mode in MODES:
                ra = (a["rows"].get(probe) or {}).get(arm, {}).get(mode) or {}
                rb = (b["rows"].get(probe) or {}).get(arm, {}).get(mode) or {}
                for name in sorted(set(ra) | set(rb)):
                    va, vb = ra.get(name, ABSENT), rb.get(name, ABSENT)
                    if va != vb and not _reason(name, VOLATILE):
                        out.append((f"{probe}/{arm}/{mode}/{name}", va, vb))
    return out


def _cell(v):
    s = json.dumps(v, ensure_ascii=False)
    return (s if len(s) <= 80 else s[:77] + "...").replace("|", "\\|")


def render_tables(doc, texts):
    """tables.md: per probe and mode, every labelled difference; the fork's shared
    leaves for linkability; detector line diffs from `texts[(site, mode)]`."""
    out = ["# Step 2 tables", "",
           f"Run `{doc['run']}`; control {doc['versions'].get('control')}, fork {doc['versions'].get('fork')}; "
           f"flags {json.dumps(doc.get('flags', {}))}.", ""]
    for probe, arms in doc["rows"].items():
        for mode in MODES:
            out.append(f"## {probe} / {mode}")
            c, f = (arms.get("control") or {}).get(mode), (arms.get("fork") or {}).get(mode)
            if c is None or f is None:
                errs = [v for k, v in doc.get("errors", {}).items() if k.startswith(f"{probe}/") and k.endswith(f"/{mode}")]
                out += [f"UNMEASURED: {'; '.join(errs) or 'no rows'}", ""]
                continue
            rows = label_rows(c, f)
            counts = collections.Counter(r[3] for r in rows)
            out.append(f"{len(rows)} differing rows: " + ", ".join(f"{n} {k}" for k, n in sorted(counts.items())))
            if rows:
                out += ["", "| row | control | fork | label | reason |", "|---|---|---|---|---|"]
                out += [f"| {n} | {_cell(cv)} | {_cell(fv)} | {lab} | {why} |" for n, cv, fv, lab, why in rows]
            if probe == "linkability":
                out += ["", f"Leaves the two fork profiles share ({len(f.get('link.shared', []))} of {f.get('link.total')}):",
                        "", ", ".join(f"`{k}`" for k in f.get("link.shared", []))]
            out.append("")
    for (site, mode), (ct, ft) in sorted(texts.items()):
        out.append(f"## detector text {site} / {mode}")
        if ct is None or ft is None:
            out += ["UNMEASURED", ""]
            continue
        co, fo = line_diff(ct, ft)
        out += [f"control only ({len(co)}):", *[f"- `{_cell(s)}`" for s in co], f"fork only ({len(fo)}):", *[f"- `{_cell(s)}`" for s in fo], ""]
    return "\n".join(out) + "\n"

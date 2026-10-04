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
    "oracle.err.stack": "names the page's server, whose port changes per launch",
    "oracle.navConnection.downlink": "a network estimate; 1.75 vs 1.6 between two stock launches",
    "oracle.navConnection.rtt": "a network estimate; changed between two launches of one stock profile",
    "oracle.voices": "speechSynthesis loads asynchronously; stock's list differed between launches of one profile",
    "oracle.mediaDevices.groupIds": "stock draws groupId per session (286c5739... then b5a5219e..., one profile, one origin)",
    "det.creepjs.candidate": "a WebRTC candidate: per-load id and port",
    "det.creepjs.type & base ip": "a WebRTC candidate hash, per load",
    "det.creepjs.rtt": "a network estimate",
    "det.creepjs.stack": "stack depth, differed between two stock loads",
    "det.creepjs.trap": "a random value per load",
}
# Row name (or dotted prefix) -> why the fork's value differs from stock's by design.
EXPECTED = {
    "net.user_agent": "the identity's User-Agent",
    "link": "a record of what two profiles share, not a fork-vs-control finding",
    "oracle.nav.webdriver": "SP2: the fork hides automation; stock under the same driver reports true",
    "oracle.media.(pointer: fine)": "d-pointer-touch: a Windows claim reports a mouse; the host has none",
    "oracle.media.(pointer: none)": "d-pointer-touch: a Windows claim reports a mouse; the host has none",
    "oracle.media.(hover: hover)": "d-pointer-touch: a Windows claim reports a mouse; the host has none",
    "oracle.media.(any-pointer: fine)": "d-pointer-touch: a Windows claim reports a mouse; the host has none",
    "oracle.media.(any-hover: hover)": "d-pointer-touch: a Windows claim reports a mouse; the host has none",
    "oracle.ua": "the identity's User-Agent; stock headless says HeadlessChrome",
    "oracle.nav.appVersion": "the identity's User-Agent; stock headless says HeadlessChrome",
}
# Oracle leaves compared by type only: a value difference is the identity's or the machine's.
SHAPE = {f"oracle.{k}": "identity- or machine-bound; compared by type" for k in SHAPE_ONLY}
# Identity-derived flags the client adds to the fork arm only (launcher.build_args).
ARGV_ALLOWED = ("--accept-lang=", "--user-data-dir=", "--window-size=", "--force-device-scale-factor=")
# Regexes over detector text lines that changed between null runs on 2026-10-04 (timings, clocks,
# the WebRTC candidates and their hashes, CDN edge IPs, per-load hashes).
VOLATILE_LINES = [
    r"^\d+(\.\d+)? ?ms$",                       # CreepJS timings
    r"^WebRTC[0-9a-f]{8}$", r"^candidate:",       # CreepJS WebRTC section (also carries the public IP)
    r"^(rtt|stack|trap|type & base ip): ",        # CreepJS per-load values (det.creepjs.* rows are VOLATILE too)
    r'^"depth": \d+,$',                          # sannysoft stack depth
    r"GMT[+-]\d{4}",                             # BrowserScan clock lines
    r"^\d+ \d\d:\d\d$",                         # BrowserScan visit counter and time
    r"^\d{1,3}(\.\d{1,3}){3}\d* more$",          # BrowserScan CDN edge IP
    r"^[0-9A-F]{8}$",                            # BrowserScan per-load hashes
    r"^Ad$", r"^0$",
]
# BrowserScan's ad unit appends a rotating link text to the line before it ("springfieldTry Web Filters").
# ponytail: the phrases seen in 12 captures on 2026-10-04; a new one shows up as a --compare disagreement,
# which is where it gets added.
AD_SUFFIX = re.compile("(" + "|".join(re.escape(p) for p in (
    "Data Formats & Protocols", "Canvas fingerprint detection", "Browser authenticity checker", "HTTP2 test tool",
    "Web Browsers", "WebRTC leak test", "Compare Broadband", "HTTP2 SSL tester", "VPN & Remote Access",
    "WebGPU report tool", "Study Anatomy", "Anatomy", "Fingerprint detection tool", "Try Web Filters",
    "Port scanner tool", "Privacy policy template", "Convert Files", "Kernel detection tool", "Compare Browsers",
    "Privacy protection service", "Client hints checker", "Internet & Telecom", "Proxying & Filtering",
    "Security checking tool", "Internet speed test", "Privacy Issues", "Browser security solutions",
    "Bot detection tools", "Anti detection browser", "Affiliate marketing program", "Discover more", "Utilities",
    "Antidetect Browser")) + ")$")


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


def _steady(report):
    """A flattened oracle report without its VOLATILE leaves."""
    return {k: v for k, v in report.items() if not _reason(f"oracle.{k}", VOLATILE)}


def stability_rows(first, second):
    """Two flattened oracle reports from one profile, launched twice. Every
    leaf counts in `compared`; a VOLATILE leaf never counts as changed."""
    keys = set(first) | set(second)
    first, second = _steady(first), _steady(second)
    return {"stab.compared": len(keys), "stab.changed": sorted(k for k in keys if first.get(k, ABSENT) != second.get(k, ABSENT))}


def link_rows(a, b):
    """Two flattened oracle reports from two profiles of one arm: the leaves they
    share. A VOLATILE leaf is never listed as shared (its equality is chance)."""
    total = len(set(a) | set(b))
    a, b = _steady(a), _steady(b)
    return {"link.total": total, "link.shared": sorted(k for k in a if k in b and a[k] == b[k])}


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
    stripped of AD_SUFFIX, blank and VOLATILE_LINES-matching lines dropped."""
    def lines(t):
        kept = (AD_SUFFIX.sub("", x.strip()).strip() for x in t.splitlines())
        return collections.Counter(s for s in kept if s and not any(re.search(p, s) for p in VOLATILE_LINES))
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

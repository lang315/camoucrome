"""Roadmap step 2, the pure half: rows, their labels, the argv and version
preconditions, run-to-run comparison and the tables
(docs/superpowers/specs/2026-10-04-step2-measurement-design.md). No browser,
no host: test_step2_rows.py runs it in CI. measure_step2.py is the browser half."""
import collections
import ipaddress
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
    # step2b null runs (20261013-213709-null, -220324-null): changed between two stock loads.
    "det.detect_headless.Time Elapse": "the time to close an alert, a timing",
    "det.detect_headless.Connection Rtt": "a network estimate",
    "det.incolumitas.connectionRTT": "a network estimate (FAIL when rtt read 0)",
    "det.fingerprint_pro.High-Activity Device": "the visitor's history on the service: stock's id had loaded the page all day",
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
    "det.creepjs.....avail": "the identity's value, or a detector hash over identity values",
    "det.creepjs....screen": "the identity's value, or a detector hash over identity values",
    "det.creepjs.screen query": "the identity's value, or a detector hash over identity values",
    "det.creepjs.cores": "the identity's value, or a detector hash over identity values",
    "det.creepjs.lang": "the identity's value, or a detector hash over identity values",
    "det.creepjs.lang (1)": "the identity's value, or a detector hash over identity values",
    "det.creepjs.lang (18)": "the identity's value, or a detector hash over identity values",
    "det.creepjs.@media": "the identity's value, or a detector hash over identity values",
    "det.creepjs.matchMedia": "the identity's value, or a detector hash over identity values",
    "det.creepjs.FP ID": "the identity's value, or a detector hash over identity values",
    "det.creepjs.Fuzzy": "the identity's value, or a detector hash over identity values",
    "det.creepjs.copy": "the identity's value, or a detector hash over identity values",
    "det.creepjs.data": "the identity's value, or a detector hash over identity values",
    "det.creepjs.freq": "the identity's value, or a detector hash over identity values",
    "det.creepjs.sum": "the identity's value, or a detector hash over identity values",
    "det.creepjs.time": "the identity's value, or a detector hash over identity values",
    "det.creepjs.level": "the identity's value, or a detector hash over identity values",
    "det.sannysoft.screen": "the identity's value, or a detector hash over identity values",
    "det.sannysoft.navigator.mediaDevices": "the identity's value, or a detector hash over identity values",
    "det.sannysoft.navigator.userAgent": "the identity's value, or a detector hash over identity values",
    "det.sannysoft.CHR_MEMORY": "stock headless fails it (deviceMemory absent); the identity sets it",
    "det.sannysoft.HEADCHR_UA": "stock headless says HeadlessChrome; the identity UA does not",
    # step2b fork run 20261013-231750:
    "oracle.audio.sampleRate": "the identity's audio:sampleRate (48000); the RDP session's device runs at 44100",
    "det.dbi_bot.isBot": "SP2 hides webdriver, and the identity UA is not HeadlessChrome",
    "det.dbi_bot.hasWebdriverTrue": "SP2: the fork hides automation; stock under the same driver reports true",
    "det.dbi_bot.hasWebdriverInFrameTrue": "SP2: the fork hides automation; stock under the same driver reports true",
    "det.dbi_bot.hasBotUserAgent": "stock headless says HeadlessChrome; the identity UA does not",
    "det.incolumitas.webDriver": "SP2: the fork hides automation; stock under the same driver reports true",
    "det.incolumitas.webdriverPresent": "SP2: the fork hides automation; stock under the same driver reports true",
    "det.incolumitas.userAgent": "stock headless says HeadlessChrome; the identity UA does not",
    "det.incolumitas.HEADCHR_UA": "stock headless says HeadlessChrome; the identity UA does not",
    "det.incolumitas.CHR_MEMORY": "stock headless fails it (deviceMemory absent); the identity sets it",
    "det.rebrowser.navigatorWebdriver": "SP2: the fork hides automation; stock under the same driver reports true",
    "det.detect_headless.Webdriver": "SP2: the fork hides automation; stock under the same driver reports true",
    "det.detect_headless.Languages": "the identity's navigator.languages",
    "det.detect_headless.Outer dimensions": "the identity's window size",
    "det.detect_headless.User Agent": "the identity's User-Agent; stock headless says HeadlessChrome",
    "det.detect_headless.App Version": "the identity's User-Agent; stock headless says HeadlessChrome",
    "det.fingerprint_pro.Bot": "SP2 and the identity UA: stock reads as a webdriver / headless_chrome bot",
    "det.fingerprint_pro.Suspect Score": "the service's sum over its signals, which the rows around it explain",
    "det.fingerprint_pro.VPN": "'timezone mismatch': the identity's zone (seed 1) against the host's IP; a client pairs the identity with a matching proxy",
    "det.whoer.blocked": "Cloudflare challenges stock's HeadlessChrome UA; the identity UA is not headless",
    "det.creepjs.images": "the identity's canvas:seed",
    r"re:det\.creepjs\.\d+% (like )?headless": "SP2 and the identity UA move CreepJS's headless scores",
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
    r"^Status[0-9a-f]{8}$", r"^0\.1000003814697265\d$", r"^1$",  # CreepJS status section, flipped between two stock loads
    # step2b, the two null runs of 2026-10-13 (stock against stock, 20 sites):
    r"^(downlink|rtt|Downlink|effectiveType)\s*[:\t]", r"^Connection Rtt\t",   # network estimates
    r"\d{1,2}:\d\d:\d\d\s?[AP]M", r"^\d+ (seconds?|minutes?|hours?|days?) ago$",  # clocks
    r"\b1[7-8]\d{8}(\d{3})?\b", r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z",     # epoch s/ms, ISO times
    r"^0x([0-9A-F])A\1A$", r"^JA3\t", r"^JA4_o\t", r"^(config_id|payload_length)\t\d+$",  # TLS GREASE, per-connection order
    r"^(event_id|last_seen_at|first_seen_at|linked_id|visitor_id|timestamp|request_id|visitor_found): ",  # Fingerprint Pro, per load
    r"^(proxy|tampering|virtual_machine|vpn)_ml_score: ", r"^score: [\d.]+$", r"^Last Seen",
    r"^\d+ IPs?, \d+ Linked IDs? in the past 24 hours$", r"^(1_hour|24_hours|5_minutes|1_minute): \d+$",
    r'^"(ip_checksum|ip_id|cHeight|num_fingerprints|src_port|tcp_checksum|tcp_seq|tcp_timestamp|webSocketSupportTimeout|connectionRTT)": ',  # incolumitas, per load
    r"^\S+ \w+\t[\d.]+ ms\t",                   # rebrowser rows carry a timing; their status is parsed into rows
    r"^Time Elapse\t", r"^Ray ID: [0-9a-f]+$",
    r"^[+-]?\d+(\.\d+)?,?$", r"^[0-9a-f]{8,64}$", r"^[2-4]g$", r"^(true|false)$",  # bare values: the line diff cannot name them
    # Pixelscan's scan state and its verdict lines flipped between two stock loads: not a measurement.
    "^Collecting Data\u2026$", "^Your Browser Fingerprint is (scanning\u2026|inconsistent)$", r"^(No masking|Masking) detected$",
    r"^(Scroll Down for More Info|Restart|How to Fix it\?|Best antidetect browsers)$",
    r"^(Detection|Bot detection service|Browser fingerprinting tools)$",   # BrowserScan ad lines
    r"WHO\d+", r"aged accounts store", r"^\"?AccsBulk:", r"^(Open|Try)$",   # whoer.net ad unit
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
    "Antidetect Browser", "Gyroscope sensor tester", "DNS leak test", "Online privacy guide",
    "Secure Networks", "Online privacy security", "Protect Privacy")) + ")$")  # the last three: step2b, 2026-10-13


def _reason(name, table):
    """A key is a row name or a dotted prefix; a key starting "re:" is a full-match regex
    (CreepJS names rows after a percentage that changes)."""
    return next((why for k, why in table.items()
                 if (re.fullmatch(k[3:], name) if k.startswith("re:") else name == k or name.startswith(k + "."))), None)


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


# step2b verdict parsers: each shape fixed from its first stock capture (2026-10-13), each
# fixture in test_step2_rows.py synthetic in that shape.
REBROWSER_STATUS = {"\U0001f7e2": "pass", "\U0001f534": "fail", "⚪": "not triggered"}
REBROWSER_ROW = re.compile("^(\U0001f7e2|\U0001f534|⚪)️?\\s*(\\w+)\\t")
JSON_BOOL = re.compile(r'^\s*"(\w+)": (true|false),?$')
JSON_OKFAIL = re.compile(r'^\s*"(\w+)": "(OK|FAIL)",?$')
# Fingerprint Pro's smart signals; Geolocation, IP Address, Visitor ID and Velocity carry the host.
FP_PRO_SIGNALS = ("Incognito Mode", "Bot", "VPN", "Browser Tampering", "Developer Tools", "Virtual Machine",
                  "Privacy Settings", "IP Blocklist", "Proxy Detection", "High-Activity Device", "Rare Device",
                  "Suspect Score")


def parse_rebrowser(text):
    """rebrowser-bot-detector: "<status emoji> <test>\\t<ms>\\t<notes>" per test."""
    out = {}
    for line in text.splitlines():
        m = REBROWSER_ROW.match(line)
        if m:
            out.setdefault(m.group(2), REBROWSER_STATUS[m.group(1)])
    return out


def parse_dbi(text):
    """deviceandbrowserinfo are_you_a_bot: the raw-detection JSON's booleans. The prose
    below it repeats every key with a colon, so only the quoted JSON form counts."""
    out = {}
    for line in text.splitlines():
        m = JSON_BOOL.match(line)
        if m:
            out.setdefault(m.group(1), m.group(2) == "true")
    return out


def parse_incolumitas(text):
    """bot.incolumitas.com: "name": "OK"|"FAIL" lines; the first occurrence of a name wins."""
    out = {}
    for line in text.splitlines():
        m = JSON_OKFAIL.match(line)
        if m:
            out.setdefault(m.group(1), m.group(2))
    return out


def parse_fingerprint_pro(text):
    """Fingerprint Pro playground: a signal's label line ends in a tab, its value is the next non-empty line."""
    raw, out = text.splitlines(), {}
    for i, line in enumerate(raw):
        k = line.strip()
        if k in FP_PRO_SIGNALS and line.endswith("\t") and k not in out:
            out[k] = next((x.strip() for x in raw[i + 1:i + 4] if x.strip()), ABSENT)
    return out


def blocked(text):
    """A Cloudflare interstitial in place of the page (whoer.net to headless stock, 2026-10-13)."""
    return "cloudflare challenge" if "Performing security verification" in text else "no"


PARSERS = {"sannysoft": parse_tabbed, "creepjs": parse_colon, "detect_headless": parse_tabbed,
           "rebrowser": parse_rebrowser, "dbi_bot": parse_dbi, "incolumitas": parse_incolumitas,
           "fingerprint_pro": parse_fingerprint_pro}
VERDICT_SITES = ("rebrowser", "dbi_bot", "incolumitas", "fingerprint_pro")


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
                    site = ".".join(name.split(".")[:2])
                    if UNMEASURED in (ra.get(site), rb.get(site)):
                        continue  # a page that did not load in one run is not a value disagreement
                    if va != vb and not _reason(name, VOLATILE):
                        out.append((f"{probe}/{arm}/{mode}/{name}", va, vb))
    return out


def unmeasured_sites(a, b):
    """The detector sites UNMEASURED in either run, which compare_runs skips: listed, never silent."""
    out = []
    for tag, doc in (("a", a), ("b", b)):
        for probe, arms in doc["rows"].items():
            for arm, modes in (arms or {}).items():
                for mode, cell in (modes or {}).items():
                    out += [f"{tag}: {probe}/{arm}/{mode}/{k}" for k, v in sorted((cell or {}).items())
                            if k.count(".") == 1 and v == UNMEASURED]
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
    if "detectors" in doc["rows"]:
        out += verdict_table(doc)
    return "\n".join(out) + "\n"


def _verdict_row(name):
    parts = name.split(".")
    return len(parts) >= 3 and parts[0] == "det" and (parts[1] in VERDICT_SITES or parts[2] == "blocked")


def verdict_table(doc):
    """Every verdict row in all four cells, equal or not: both arms flagged is a finding too."""
    cells = doc["rows"].get("detectors") or {}
    cols = [(arm, mode) for mode in MODES for arm in ARMS]
    got = {c: (cells.get(c[0]) or {}).get(c[1]) for c in cols}
    names = sorted({k for v in got.values() if v for k in v if _verdict_row(k)})

    def val(cell, name):
        if cell is None or cell.get(".".join(name.split(".")[:2])) == UNMEASURED:
            return UNMEASURED
        return _cell(cell.get(name, ABSENT))
    out = ["## verdicts", "", "| row | " + " | ".join(f"{a} {m}" for a, m in cols) + " |", "|---" * (len(cols) + 1) + "|"]
    out += [f"| {n} | " + " | ".join(val(got[c], n) for c in cols) + " |" for n in names]
    return out + [""]


_IP_TOKEN = re.compile(r"(?<![\w:.])[0-9A-Fa-f:.]*[.:][0-9A-Fa-f:.]*(?![\w:.])")
_OCTET = r"(?:25[0-5]|2[0-4]\d|1?\d?\d)"
_IP_GLUED = re.compile(rf"(?<![\w.]){_OCTET}(?:\.{_OCTET}){{3}}\d{{1,2}}(?![\w.])")  # whoer: "203.0.113.1922"
_COORD = re.compile(r"-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}|\d{1,3}°\d{1,2}′[\d.]+″[NSEW]")


def _ip(tok):
    head, _, port = tok.rpartition(":")
    for cand, tail in ((tok, ""), (head, ":" + port)):
        try:
            a = ipaddress.ip_address(cand)
        except ValueError:
            continue
        return ("<ip>" if a.version == 4 else "<ip6>") + tail
    return tok


def scrub(value, geo):
    """`value` (str, or list/dict walked recursively) with IP addresses, coordinate pairs and the
    host's geo strings replaced. A candidate counts as an address only if ipaddress parses it, so
    a version (154.0.8037.93) or a clock (10:00:00) stays. `geo` maps a placeholder to the strings
    it replaces; it comes from CAMOU_SCRUB on the host and is never committed."""
    if isinstance(value, dict):
        return {scrub(k, geo): scrub(v, geo) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v, geo) for v in value]
    if not isinstance(value, str):
        return value
    s = _COORD.sub("<coord>", _IP_GLUED.sub("<ip>", _IP_TOKEN.sub(lambda m: _ip(m.group(0)), value)))
    for label, needles in geo.items():
        for n in sorted(needles, key=len, reverse=True):
            s = re.sub(re.escape(n), label, s, flags=re.IGNORECASE)  # BrowserScan prints the city lower-case
    return s

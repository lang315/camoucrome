"""Per-site summary of one tracking-observer session.

Usage: observe_report.py TRACE.json NETLOG.json [--cookies COOKIES_DB]

TRACE comes from --trace-startup=-*,disabled-by-default-camou.observe
--trace-startup-format=json; NETLOG from --log-net-log; COOKIES_DB is a copy of
the profile's Cookies sqlite taken after the browser exited. Prints markdown.
With the Intl recipe (adding v8,disabled-by-default-v8.runtime_stats) on a build with
v8_enable_runtime_call_stats = true, the report also counts Intl built-ins.
Only names, counts, hosts and query-stripped paths are printed: query strings
carry tokens and cookie values identify the account, so neither is read.
docs/observer/README.md is the operator guide.
"""
import argparse
import bisect
import collections
import json
import re
import sqlite3
import urllib.parse

CATEGORY = "disabled-by-default-camou.observe"
# V8 runtime call stats (docs/superpowers/specs/2026-10-13-observer-intl-rcs-design.md):
# each top-level V8 entry slice resets the counters at its start and carries their dump
# at its end; nested slices carry none, so summing the dumps counts each call once.
V8_ENTRY = ("V8.Execute", "V8.RunMicrotasks")
RCS_ARG = "runtime-call-stats"
# a C++ builtin's counter is dumped under its bare name (runtime functions carry "Runtime_")
INTL = re.compile(r"^(Intl|DateTimeFormat|NumberFormat|Collator|PluralRules|RelativeTimeFormat"
                  r"|ListFormat|DisplayNames|Segment|DurationFormat|Locale|V8BreakIterator)"
                  r"|^[A-Z][A-Za-z]*PrototypeToLocale|^StringPrototypeLocaleCompare")

# Mirror of the allow-list in the observe patch (bind_gen/interface.py).
# A "Interface.member" key wins over its interface's key.
GROUPS = {
    **dict.fromkeys(["Navigator", "WorkerNavigator", "NavigatorUAData", "PluginArray",
                     "MimeTypeArray", "NetworkInformation", "BatteryManager", "Permissions",
                     "StorageManager", "Keyboard", "MediaCapabilities"], "navigator"),
    **dict.fromkeys(["Screen", "ScreenOrientation"], "screen"),
    **dict.fromkeys(["HTMLCanvasElement", "OffscreenCanvas", "CanvasRenderingContext2D",
                     "OffscreenCanvasRenderingContext2D"], "canvas"),
    **dict.fromkeys(["WebGLRenderingContext", "WebGL2RenderingContext"], "webgl"),
    **dict.fromkeys(["GPU", "GPUAdapter"], "webgpu"),
    **dict.fromkeys(["BaseAudioContext", "AudioContext", "OfflineAudioContext",
                     "AnalyserNode", "AudioBuffer"], "audio"),
    **dict.fromkeys(["MediaDevices", "SpeechSynthesis"], "media"),
    "RTCPeerConnection": "webrtc",
    "FontFaceSet": "fonts",
    **dict.fromkeys(["Window.matchMedia", "Window.devicePixelRatio", "Window.outerWidth",
                     "Window.outerHeight", "Window.innerWidth", "Window.innerHeight",
                     "Window.screenX", "Window.screenY", "Window.screenLeft", "Window.screenTop",
                     "HTMLElement.offsetWidth", "HTMLElement.offsetHeight",
                     "Element.getBoundingClientRect", "Element.getClientRects"], "layout-probe"),
    "Document.cookie": "storage",
    "Storage": "storage",
}

NOT_OBSERVABLE = [
    "V8 built-ins Date.prototype.getTimezoneOffset (a CSA builtin) and Math; Intl counts need "
    "the Intl recording recipe and an observer build with v8_enable_runtime_call_stats = true",
    "CSS @media rules in stylesheets (only matchMedia is seen)",
    "Font enumeration by layout measurement beyond the listed layout members",
    "TLS/JA3, HTTP/2 framing, anything computed server-side",
    "Named and indexed access (localStorage.foo, navigator.plugins[0], "
    "mimeTypes['application/pdf']): it goes through interceptor callbacks, not the hooked ones",
    "Values: the report says that a page read a member, not what it got",
]


def load_trace(trace_path):
    with open(trace_path) as f:
        return json.load(f)


def all_events(data):
    return data["traceEvents"] if isinstance(data, dict) else data


def events_of(data):
    return [e for e in all_events(data) if e.get("cat") == CATEGORY]


def load_events(trace_path):
    return events_of(load_trace(trace_path))


def _find(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        obj = list(obj.values())
    if isinstance(obj, list):
        for v in obj:
            found = _find(v, key)
            if found is not None:
                return found
    return None


def buffer_note(data):
    """A full trace buffer stops the whole trace (record-as-much-as-possible
    discards new chunks): the session's tail is missing, observer events included."""
    bufs = _find(data.get("metadata", {}) if isinstance(data, dict) else {}, "traced_buf")
    if not bufs:
        return "Trace buffer: stats not in the trace; whether it filled is unknown."
    lost = sum(b.get("chunks_discarded", 0) for b in bufs)
    if lost:
        return (f"Trace buffer: FULL, {lost} chunks discarded. The trace stopped before the "
                "session ended; the counts below are lower bounds.")
    return "Trace buffer: no chunks discarded."


def group_of(name):
    parts = name.split(".")
    return GROUPS.get(".".join(parts[:2])) or GROUPS.get(parts[0], "other")


def script_label(url):
    """Host[:port] and path of a script URL; userinfo, query and fragment can carry
    credentials or ids, so they are dropped."""
    if not url:
        return "(no script)"
    u = urllib.parse.urlsplit(url)
    if u.scheme in ("blob", "data"):
        return u.scheme + ":"  # the rest is a per-object id or the script itself
    if not u.hostname:
        return url.split("?")[0].split("#")[0]
    try:
        port = f":{u.port}" if u.port else ""
    except ValueError:  # malformed port: one bad event must not abort the report
        port = ""
    return u.hostname + port + u.path


def surface_counts(events):
    """site -> (reading origin, script label) -> API name -> calls."""
    counts = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for e in events:
        args = e.get("args", {})
        origin = args.get("origin", "")
        counts[args.get("site") or origin][(origin, script_label(args.get("script")))][e["name"]] += 1
    return counts


def _dump(e):
    d = e.get("args", {}).get(RCS_ARG)
    if isinstance(d, str):  # a legacy JSON annotation can be exported as a string
        d = json.loads(d)
    return d if isinstance(d, dict) else None


def _by_thread(events):
    """(pid, tid) -> (start times, events), both in start order."""
    groups = collections.defaultdict(list)
    for e in events:
        groups[(e["pid"], e["tid"])].append(e)
    out = {}
    for key, evs in groups.items():
        evs.sort(key=lambda e: e["ts"])
        out[key] = ([e["ts"] for e in evs], evs)
    return out


def _entry_script(s, runs, observe):
    """The Blink v8.run around the slice (classic script top level), else the one script
    of the observer events inside it; handlers, timers, promise jobs and modules have no
    entry script of their own."""
    key, start, end = (s["pid"], s["tid"]), s["ts"], s["ts"] + s.get("dur", 0)
    ts, evs = runs.get(key, ((), ()))
    i = bisect.bisect_right(ts, start)
    # shortcut: checks the 8 latest-starting runs; deeper v8.run nesting falls to rule 2
    run = next((r for r in reversed(evs[max(0, i - 8):i]) if start <= r["ts"] + r.get("dur", 0)), None)
    if run:
        return script_label(run.get("args", {}).get("fileName"))
    ts, evs = observe.get(key, ((), ()))
    scripts = {e.get("args", {}).get("script")
               for e in evs[bisect.bisect_left(ts, start):bisect.bisect_right(ts, end)]}
    return script_label(scripts.pop()) if len(scripts) == 1 else "(unknown)"


def intl_counts(events):
    """(site, script label, builtin) -> calls; None when no dump holds any counter (the
    build lacks runtime call stats or the category was off: blind, not zero)."""
    slices = [(e, _dump(e)) for e in events if e.get("name") in V8_ENTRY]
    slices = [(e, d) for e, d in slices if d is not None]
    if not any(d for _, d in slices):
        return None
    observe = [e for e in events if e.get("cat") == CATEGORY]
    # a renderer's page site wins; a worker's origin stands in only where no event has a site
    sites = collections.defaultdict(collections.Counter)
    origins = collections.defaultdict(collections.Counter)
    for e in observe:
        a = e.get("args", {})
        if a.get("site"):
            sites[e["pid"]][a["site"]] += 1
        elif a.get("origin"):
            origins[e["pid"]][a["origin"]] += 1
    runs = _by_thread(e for e in events if e.get("name") == "v8.run")
    observe = _by_thread(observe)
    counts = collections.Counter()
    for s, d in slices:
        hits = {name: v[0] for name, v in d.items() if INTL.match(name)}
        if not hits:
            continue
        top = (sites.get(s["pid"]) or origins.get(s["pid"]) or collections.Counter()).most_common(1)
        site = top[0][0] if top else "(site unknown)"
        script = _entry_script(s, runs, observe)
        for name, n in hits.items():
            counts[(site, script, name)] += int(n)
    return dict(counts)


_SFC_SITE = re.compile(r"site=([^;}]+)")


def _request_site(params):
    top = params.get("network_isolation_key", "").split(" ")[0]
    if top.startswith("http"):
        return top
    m = _SFC_SITE.search(params.get("site_for_cookies", ""))
    return m.group(1) if m and m.group(1).startswith("http") else ""


def load_requests(netlog_path):
    with open(netlog_path) as f:
        data = json.load(f)
    start = data["constants"]["logEventTypes"]["URL_REQUEST_START_JOB"]
    begin = data["constants"]["logEventPhase"]["PHASE_BEGIN"]
    out = []
    for e in data.get("events", []):
        if e.get("type") != start or e.get("phase") != begin:
            continue
        p = e["params"]
        url = urllib.parse.urlsplit(p["url"])
        out.append((_request_site(p), url.hostname or "", url.path or "/", p.get("method", "")))
    return out


def load_cookie_names(db_path):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return con.execute(
            "select host_key, name, expires_utc, is_httponly from cookies order by host_key, name"
        ).fetchall()
    finally:
        con.close()


def render(events, requests, cookies, buffer=None, intl=None):
    lines = ["# Tracking observer report", ""]
    if buffer:
        lines += [buffer, ""]
    counts = surface_counts(events)
    by_site = collections.defaultdict(collections.Counter)
    for site, host, path, method in requests:
        by_site[site][(host, f"{method} {path}")] += 1
    for site in sorted(set(counts) | set(by_site)):
        lines += [f"## {site or '(no site)'}", "",
                  "| group | API | reading origin | script | calls |", "|---|---|---|---|---|"]
        by_script = collections.defaultdict(collections.Counter)
        for (origin, script), names in sorted(counts.get(site, {}).items()):
            by_script[script].update(names)
            for name, n in sorted(names.items(), key=lambda kv: (group_of(kv[0]), kv[0])):
                lines.append(f"| {group_of(name)} | {name} | {origin} | {script} | {n} |")
        if by_script:
            lines += ["", "Top scripts", "", "| script | calls | top APIs |", "|---|---|---|"]
            for script, names in sorted(by_script.items(), key=lambda kv: (-sum(kv[1].values()), kv[0])):
                top = ", ".join(f"{name} ({n})" for name, n in names.most_common(3))
                lines.append(f"| {script} | {sum(names.values())} | {top} |")
        reqs = by_site.get(site)
        total = sum(reqs.values()) if reqs else 0
        lines += ["", f"Requests: {total}", "", "| host | request | count |", "|---|---|---|"]
        for (host, req), n in sorted((reqs or {}).items()):
            lines.append(f"| {host} | {req} | {n} |")
        lines.append("")
    lines += ["## V8 built-ins (Intl)", ""]
    if intl is None:
        lines += ["Intl: blind (no V8 runtime call stats in this trace)", ""]
    elif not intl:
        lines += ["Intl: none called", ""]
    else:
        lines += ["| site | script | builtin | calls |", "|---|---|---|---|"]
        for (site, script, name), n in sorted(intl.items(), key=lambda kv: (kv[0][0], -kv[1], kv[0][1:])):
            lines.append(f"| {site} | {script} | {name} | {n} |")
        lines += ["", "script: the Blink v8.run entry script, else the one script of the observer "
                  "events in the same V8 slice, else (unknown). Event handlers, timers, promise "
                  "callbacks and module bodies have no entry script.", ""]
    if cookies:
        lines += ["## Cookies (names only)", "", "| host | name | expires_utc | httponly |",
                  "|---|---|---|---|"]
        lines += [f"| {h} | {n} | {exp} | {ho} |" for h, n, exp, ho in cookies]
        lines.append("")
    lines += ["## Not observable", ""] + [f"- {item}" for item in NOT_OBSERVABLE]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("trace")
    ap.add_argument("netlog")
    ap.add_argument("--cookies")
    a = ap.parse_args()
    cookies = load_cookie_names(a.cookies) if a.cookies else []
    data = load_trace(a.trace)
    print(render(events_of(data), load_requests(a.netlog), cookies, buffer_note(data),
                 intl_counts(all_events(data))), end="")


if __name__ == "__main__":
    main()

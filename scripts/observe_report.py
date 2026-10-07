"""Per-site summary of one tracking-observer session.

Usage: observe_report.py TRACE.json NETLOG.json [--cookies COOKIES_DB]

TRACE comes from --trace-startup=-*,disabled-by-default-camou.observe
--trace-startup-format=json; NETLOG from --log-net-log; COOKIES_DB is a copy of
the profile's Cookies sqlite taken after the browser exited. Prints markdown.
Only names, counts, hosts and query-stripped paths are printed: query strings
carry tokens and cookie values identify the account, so neither is read.
docs/observer/README.md is the operator guide.
"""
import argparse
import collections
import json
import re
import sqlite3
import urllib.parse

CATEGORY = "disabled-by-default-camou.observe"

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
    "V8 built-ins: Intl.* (resolvedOptions().timeZone, supportedLocalesOf), "
    "Date.prototype.getTimezoneOffset, Math (phase 2 covers Intl; getTimezoneOffset stays blind)",
    "CSS @media rules in stylesheets (only matchMedia is seen)",
    "Font enumeration by layout measurement beyond the listed layout members",
    "TLS/JA3, HTTP/2 framing, anything computed server-side",
    "Named and indexed access (localStorage.foo, navigator.plugins[0], "
    "mimeTypes['application/pdf']): it goes through interceptor callbacks, not the hooked ones",
    "Values: the report says that a page read a member, not what it got",
]


def load_events(trace_path):
    with open(trace_path) as f:
        data = json.load(f)
    events = data["traceEvents"] if isinstance(data, dict) else data
    return [e for e in events if e.get("cat") == CATEGORY]


def group_of(name):
    parts = name.split(".")
    return GROUPS.get(".".join(parts[:2])) or GROUPS.get(parts[0], "other")


def script_label(url):
    """Host[:port] and path of a script URL; userinfo, query and fragment can carry
    credentials or ids, so they are dropped."""
    if not url:
        return "(no script)"
    u = urllib.parse.urlsplit(url)
    if not u.hostname:
        return url.split("?")[0].split("#")[0]
    return u.hostname + (f":{u.port}" if u.port else "") + u.path


def surface_counts(events):
    """site -> (reading origin, script label) -> API name -> calls."""
    counts = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for e in events:
        args = e.get("args", {})
        origin = args.get("origin", "")
        counts[args.get("site") or origin][(origin, script_label(args.get("script")))][e["name"]] += 1
    return counts


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


def render(events, requests, cookies):
    lines = ["# Tracking observer report", ""]
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
    print(render(load_events(a.trace), load_requests(a.netlog), cookies), end="")


if __name__ == "__main__":
    main()

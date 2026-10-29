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
    # behaviour signals (docs/superpowers/specs/2026-10-28-observer-behaviour-signals-design.md)
    **dict.fromkeys(["Performance.now", "Window.requestAnimationFrame",
                     "DedicatedWorkerGlobalScope.requestAnimationFrame", "Window.setTimeout",
                     "Window.setInterval", "WorkerGlobalScope.setTimeout",
                     "WorkerGlobalScope.setInterval"], "timing"),
    **dict.fromkeys(["Document.visibilityState", "Document.hidden",
                     "Document.webkitVisibilityState", "Document.webkitHidden",
                     "Document.hasFocus"], "focus-visibility"),
    **dict.fromkeys(["Clipboard", "ClipboardItem", "Document.execCommand"], "clipboard"),
    **dict.fromkeys(["DeviceMotionEvent", "DeviceOrientationEvent", "DeviceMotionEventAcceleration",
                     "DeviceMotionEventRotationRate", "Sensor", "Accelerometer", "Gyroscope",
                     "Magnetometer", "AbsoluteOrientationSensor", "RelativeOrientationSensor",
                     "LinearAccelerationSensor", "GravitySensor"], "motion"),
}

# Listener registrations (one event per addEventListener call or on* setter, from the Blink hook
# in EventTarget::AddEventListenerInternal). A page can register any string as an event type, so
# the report prints a type only if it is in KNOWN_EVENT_TYPES; the others are counted, never named.
LISTENER = "EventTarget.addEventListener"
_TYPE_GROUPS = {
    "input-events": "click dblclick mousedown mouseup mousemove mouseover mouseout mouseenter "
                    "mouseleave contextmenu auxclick wheel mousewheel DOMMouseScroll pointerdown "
                    "pointerup pointermove pointerover pointerout pointerenter pointerleave "
                    "pointercancel pointerrawupdate gotpointercapture lostpointercapture touchstart "
                    "touchend touchmove touchcancel keydown keyup keypress beforeinput input "
                    "textInput compositionstart compositionupdate compositionend dragstart drag "
                    "dragenter dragover dragleave drop dragend scroll scrollend select "
                    "selectionchange selectstart gesturestart gesturechange gestureend",
    "focus-visibility": "focus blur focusin focusout visibilitychange pagehide pageshow freeze "
                        "resume beforeunload unload",
    "clipboard": "copy cut paste clipboardchange",
    "motion": "devicemotion deviceorientation deviceorientationabsolute orientationchange reading",
    "listeners-other": "load DOMContentLoaded readystatechange error abort resize message "
                       "messageerror storage online offline popstate hashchange change submit "
                       "reset invalid toggle play pause ended timeupdate canplay canplaythrough "
                       "loadedmetadata loadeddata loadstart progress stalled waiting seeking "
                       "seeked volumechange ratechange durationchange emptied suspend playing "
                       "animationstart animationend animationiteration animationcancel "
                       "transitionstart transitionrun transitionend transitioncancel "
                       "fullscreenchange fullscreenerror languagechange securitypolicyviolation "
                       "open close connect connecting statechange devicechange success complete "
                       "versionchange install activate push sync controllerchange updatefound "
                       "fetch beforeinstallprompt appinstalled cancel finish slotchange "
                       "unhandledrejection rejectionhandled beforeprint afterprint "
                       "formdata readystatechange timeout loadend",
}
TYPE_GROUP = {ty: g for g, names in _TYPE_GROUPS.items() for ty in names.split()}
KNOWN_EVENT_TYPES = frozenset(TYPE_GROUP)

NOT_OBSERVABLE = [
    "V8 built-ins Date.prototype.getTimezoneOffset (a CSA builtin) and Math; Intl counts need "
    "the Intl recording recipe and an observer build with v8_enable_runtime_call_stats = true",
    "CSS @media rules in stylesheets (only matchMedia is seen)",
    "Font enumeration by layout measurement beyond the listed layout members",
    "TLS/JA3, HTTP/2 framing, anything computed server-side",
    "Named and indexed access (localStorage.foo, navigator.plugins[0], "
    "mimeTypes['application/pdf']): it goes through interceptor callbacks, not the hooked ones",
    "Values: the report says that a page read a member, not what it got",
    "Handlers: a dispatch is counted, not what its handler does or how long it runs",
    "per-script dispatch attribution: a fire is joined to the scripts that registered that type and "
    "target kind, so two scripts registering one type cannot be told apart",
    "An on* handler re-assigned after its first assignment (only the first registers a listener)",
    "Date.now, performance.timeOrigin, PerformanceObserver, queueMicrotask, requestIdleCallback, "
    "scroll offsets",
    "document.execCommand: the command is not recorded, so copy cannot be told from bold",
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


def listener_name(args):
    """The API label of one listener registration; an unknown type is never named."""
    typ = args.get("type", "")
    label = typ if typ in KNOWN_EVENT_TYPES else "other"
    opts = args.get("opts")
    return f"{LISTENER}[{label}] target={args.get('target') or '?'}" + (f" opts={opts}" if opts else "")


def other_listener_types(events):
    """site -> number of distinct event types outside the known set (counted, never printed)."""
    types = collections.defaultdict(set)
    for e in events:
        a = e.get("args", {})
        if e["name"] == LISTENER and a.get("type", "") not in KNOWN_EVENT_TYPES:
            types[a.get("site") or a.get("origin", "")].add(a.get("type", ""))
    return {site: len(s) for site, s in types.items()}


DISPATCH = "EventTarget.dispatch"
DISPATCH_FLOOR_NOTE = "dispatch counts are floor values; up to 255 per type unflushed"


def _target_kind(target):
    """A dispatch reports a worker global scope as Worker; registrations name the scope class."""
    return "Worker" if target.endswith("WorkerGlobalScope") else target


def _int(s):
    try:
        return int(s)
    except (TypeError, ValueError):
        return 0


def dispatch_rows(events):
    """Coalesced listener dispatches aggregated by (type, target, trusted) across flushed events.
    Unknown types fold into one "[other]" row per (target, trusted): the distinct count is kept,
    the text never. registered_by joins to the scripts that registered that (type, target kind)."""
    regs = collections.defaultdict(set)
    for e in events:
        if e["name"] == LISTENER:
            a = e.get("args", {})
            regs[(a.get("type", ""), _target_kind(a.get("target") or "?"))].add(script_label(a.get("script")))
    agg = {}
    for e in events:
        if e["name"] != DISPATCH:
            continue
        a = e.get("args", {})
        typ = a.get("type", "")
        key = (typ if typ in KNOWN_EVENT_TYPES else "[other]", a.get("target") or "?",
               str(a.get("trusted")).lower())
        g = agg.setdefault(key, {"dispatches": 0, "handlers": 0, "ts": [], "types": set()})
        g["dispatches"] += _int(a.get("dispatches"))
        g["handlers"] += _int(a.get("handlers"))
        g["ts"].append(e["ts"])
        g["types"].add(typ)
    rows = []
    for (typ, target, trusted), g in agg.items():
        span = (max(g["ts"]) - min(g["ts"])) / 1e6  # trace timestamps are microseconds
        kind = _target_kind(target)
        if typ == "[other]":
            by = set().union(*[s for (t, k), s in regs.items() if t not in KNOWN_EVENT_TYPES and k == kind])
        else:
            by = regs.get((typ, kind), set())
        rows.append({"type": typ, "group": TYPE_GROUP.get(typ, "listeners-other"), "target": target,
                     "trusted": trusted, "dispatches": g["dispatches"], "handlers": g["handlers"],
                     "rate": g["dispatches"] / span if len(g["ts"]) > 1 and span > 0 else None,
                     "types": len(g["types"]) if typ == "[other]" else 1,
                     "registered_by": sorted(by)})
    return sorted(rows, key=lambda r: (r["group"], r["type"], r["target"], r["trusted"]))


def dispatch_type_gaps(events):
    """(registered but never fired, fired with no registration seen), as sets of event types."""
    reg = {e.get("args", {}).get("type", "") for e in events if e["name"] == LISTENER}
    fired = {e.get("args", {}).get("type", "") for e in events if e["name"] == DISPATCH}
    return reg - fired, fired - reg


def _type_list(types):
    known = sorted(t for t in types if t in KNOWN_EVENT_TYPES)
    n = len(types) - len(known)
    return ", ".join(known + ([f"{n} other"] if n else [])) or "none"


def group_of(name):
    if name.startswith(LISTENER + "["):
        return TYPE_GROUP.get(name[len(LISTENER) + 1:name.index("]")], "listeners-other")
    parts = name.split(".")
    return GROUPS.get(".".join(parts[:2])) or GROUPS.get(parts[0], "other")


_POP_MEDIA = re.compile(r"^scontent.*\.fbcdn\.net$")
_POP_FNA = re.compile(r"^.+\.fna\.(fbcdn\.net|whatsapp\.net)$")


def public_host(host):
    """Media CDN host names carry a regional POP code, which is a location: collapse them."""
    if _POP_MEDIA.match(host):
        return "scontent.*.fbcdn.net"
    m = _POP_FNA.match(host)
    return "*.fna." + m.group(1) if m else host


def public_endpoint(endpoint):
    """public_host on the host part of a 'host/path' key (or a bare host)."""
    host, sep, rest = endpoint.partition("/")
    return public_host(host) + sep + rest


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
    return public_host(u.hostname) + port + u.path


def surface_counts(events):
    """site -> (reading origin, script label) -> API name -> calls."""
    counts = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for e in events:
        args = e.get("args", {})
        origin = args.get("origin", "")
        name = listener_name(args) if e["name"] == LISTENER else e["name"]
        counts[args.get("site") or origin][(origin, script_label(args.get("script")))][name] += 1
    return counts


def timing_rates(events):
    """site -> (API name, script label) -> (calls, calls per second between the first and last
    event of that key; None when under two events or no elapsed time). Counts alone cannot tell
    a 60 Hz loop from a one-off."""
    seen = collections.defaultdict(list)
    for e in events:
        if group_of(e["name"]) != "timing":
            continue
        a = e.get("args", {})
        seen[(a.get("site") or a.get("origin", ""), e["name"], script_label(a.get("script")))].append(e["ts"])
    out = collections.defaultdict(dict)
    for (site, name, script), ts in seen.items():
        span = (max(ts) - min(ts)) / 1e6  # trace timestamps are microseconds
        out[site][(name, script)] = (len(ts), len(ts) / span if len(ts) > 1 and span > 0 else None)
    return out


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
        out.append((_request_site(p), public_host(url.hostname or ""), url.path or "/", p.get("method", "")))
    return out


def load_cookie_names(db_path):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return con.execute(
            "select host_key, name, expires_utc, is_httponly from cookies order by host_key, name"
        ).fetchall()
    finally:
        con.close()


BROWSER = "browser"  # a request with no page site, or a chrome:// one: the browser's own traffic
NET_KINDS = (("javascript", "js"), ("ecmascript", "js"), ("css", "css"), ("html", "html"), ("wasm", "wasm"),
             ("image", "image"), ("video", "video"), ("audio", "video"), ("font", "font"), ("json", "json"))
SEND_EVENTS = {"HTTP_TRANSACTION_SEND_REQUEST", "HTTP_TRANSACTION_HTTP2_SEND_REQUEST_HEADERS",
               "HTTP_TRANSACTION_QUIC_SEND_REQUEST_HEADERS"}


def kind_of(content_type, method):
    if method == "POST":
        return "beacon"
    ct = (content_type or "").lower()
    for needle, k in NET_KINDS:
        if needle in ct:
            return k
    return "other"


def load_costs(netlog_path):
    """Bytes per host and kind. network = pre-decode bytes of a request that went out (HTTP/1, 2 or QUIC);
    cache = pre-decode bytes of one that did not; decoded = after content decoding. None when unreadable."""
    try:
        with open(netlog_path, encoding="utf-8") as f:
            d = json.load(f)
        names = {v: k for k, v in d["constants"]["logEventTypes"].items()}
        events = d["events"]
    except (OSError, ValueError, KeyError):
        return None
    req = {}
    for e in events:
        t, p = names.get(e.get("type")), e.get("params") or {}
        r = req.setdefault(e["source"]["id"], {"url": None, "method": "GET", "ct": "", "raw": 0, "dec": 0, "sent": False,
                                               "hdr": False, "enc": False, "site": ""})
        if t == "URL_REQUEST_START_JOB" and r["url"] is None and "url" in p:
            r["url"], r["method"] = p["url"], p.get("method", "GET")
            r["site"] = _request_site(p)
        elif t == "URL_REQUEST_JOB_BYTES_READ":
            r["raw"] += p.get("byte_count", 0)
        elif t == "URL_REQUEST_JOB_FILTERED_BYTES_READ":
            r["dec"] += p.get("byte_count", 0)
        elif t in SEND_EVENTS:
            r["sent"] = True
        elif t == "HTTP_TRANSACTION_READ_RESPONSE_HEADERS":
            for h in p.get("headers", []):
                k, _, v = h.partition(":")
                if k.strip().lower() == "content-type":
                    r["ct"] = v.strip()
                elif k.strip().lower() == "content-encoding":
                    r["enc"] = True
            r["hdr"] = True
    out = {"by_host": {}, "by_kind": {}, "by_site_kind": {}, "posts": collections.Counter()}
    for r in req.values():
        if not r["url"] or not r["url"].startswith("http"):
            continue
        s = urllib.parse.urlsplit(r["url"])
        host = public_host(s.hostname or "?")
        # URL_REQUEST_JOB_BYTES_READ is logged only when a content decoder reads the stream; an identity
        # response has FILTERED_BYTES_READ alone, and there raw equals decoded. When the response may have
        # been encoded (or its headers were not logged) decoded is only a floor: the row is marked.
        raw, approx = r["raw"], False
        if not raw and r["dec"]:
            raw, approx = r["dec"], r["enc"] or not r["hdr"]
        kind = kind_of(r["ct"], r["method"])
        site = r["site"] if r["site"].startswith("http") else BROWSER
        site_table = out["by_site_kind"].setdefault(site, {})
        for key, table in ((host, out["by_host"]), (kind, out["by_kind"]), (kind, site_table)):
            row = table.setdefault(key, {"n": 0, "network": 0, "cache": 0, "decoded": 0})
            row["n"] += 1
            row["network" if r["sent"] else "cache"] += raw
            row["decoded"] += r["dec"] or raw
            if approx:
                row["approx"] = True
        if r["method"] == "POST":
            out["posts"][host + s.path] += 1
    out["posts"] = dict(out["posts"])
    return out


_APPROX = " (decoded used)"


def _mb(n):
    return f"{n / 1e6:.2f}"


def render_costs(costs):
    if costs is None:
        return "## Cost\n\nnetlog unreadable: no byte counts.\n"
    lines = ["## Cost", "", "Bytes in MB: network = pre-decode bytes fetched, cache = pre-decode bytes from cache.", "",
             "| host | requests | network | cache | decoded |", "|---|---|---|---|---|"]
    for h, v in sorted(costs["by_host"].items(), key=lambda x: -(x[1]["network"] + x[1]["cache"]))[:20]:
        lines.append(f"| `{h}`{_APPROX if v.get('approx') else ''} | {v['n']} | {_mb(v['network'])} | {_mb(v['cache'])} | {_mb(v['decoded'])} |")
    def total(kinds):
        return sum(v["network"] + v["cache"] for v in kinds.values())
    sites = costs["by_site_kind"]
    pages = sorted((s for s in sites if s != BROWSER), key=lambda s: -total(sites[s]))
    for site in pages + ([BROWSER] if BROWSER in sites else []):
        lines += ["", f"### {'browser-internal' if site == BROWSER else site}", "",
                  "| kind | requests | network | cache | decoded |", "|---|---|---|---|---|"]
        for k, v in sorted(sites[site].items(), key=lambda x: -(x[1]["network"] + x[1]["cache"])):
            lines.append(f"| {k}{_APPROX if v.get('approx') else ''} | {v['n']} | {_mb(v['network'])} | {_mb(v['cache'])} | {_mb(v['decoded'])} |")
    return "\n".join(lines) + "\n"


CPU_NAMES = {"FunctionCall": "run", "EvaluateScript": "run", "v8.compile": "compile"}


def _cpu_url(e):
    a = e.get("args") or {}
    return (a.get("data") or {}).get("url") or a.get("fileName") or ""


def cpu_by_script(events):
    """ms per script from complete devtools.timeline/v8 slices; a slice inside a counted one (same thread) counts once."""
    by_thread = collections.defaultdict(list)
    for e in events:
        if e.get("ph") == "X" and e.get("name") in CPU_NAMES:
            by_thread[(e.get("pid"), e.get("tid"))].append(e)
    out = collections.defaultdict(lambda: {"run": 0.0, "compile": 0.0})
    for evs in by_thread.values():
        end = None
        for e in sorted(evs, key=lambda e: (e["ts"], -e.get("dur", 0))):
            if end is not None and e["ts"] < end:
                continue
            end = e["ts"] + e.get("dur", 0)
            out[script_label(_cpu_url(e))][CPU_NAMES[e["name"]]] += e.get("dur", 0) / 1000
    return dict(out)


def ram_summary(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    by = collections.defaultdict(list)
    for s in d.get("samples", []):
        for t, b in s.get("by_type", {}).items():
            by[t].append(b)
    return {t: {"peak_mb": round(max(v) / 2**20, 1), "mean_mb": round(sum(v) / len(v) / 2**20, 1), "samples": len(v)}
            for t, v in by.items()}


def render_cpu(cpu):
    if not cpu:
        return "## CPU per script\n\nno devtools.timeline slices (category not recorded).\n"
    lines = ["## CPU per script", "", "| script | run ms | compile ms |", "|---|---|---|"]
    for k, v in sorted(cpu.items(), key=lambda x: -(x[1]["run"] + x[1]["compile"]))[:20]:
        lines.append(f"| `{k}` | {v['run']:.0f} | {v['compile']:.0f} |")
    return "\n".join(lines) + "\n"


def render_ram(ram):
    if not ram:
        return "## RAM\n\nno ram.json.\n"
    lines = ["## RAM (private bytes)", "", "| process | peak MB | mean MB | samples |", "|---|---|---|---|"]
    for t, v in sorted(ram.items()):
        lines.append(f"| {t} | {v['peak_mb']} | {v['mean_mb']} | {v['samples']} |")
    return "\n".join(lines) + "\n"


def reads_by_script(events):
    out = collections.defaultdict(collections.Counter)
    for site_rows in surface_counts(events).values():
        for (_origin, script), members in site_rows.items():
            out[script].update(members)
    return dict(out)


def render_channels(channels, costs):
    if not channels:
        return "## Channels\n\nno channels.json (undriven arm): POST counts are in Cost.\n"
    watched = {public_endpoint(ep).split("/", 1)[0] for ep in channels["endpoints"]}
    mine, other = 0, collections.Counter()
    for ep, n in (costs or {}).get("posts", {}).items():
        host = public_host(ep.split("/", 1)[0])
        if host in watched:
            mine += n
        else:
            other[host] += n
    lines = ["## Channels", "",
             f"captured {channels['posts_captured']} of {mine} POSTs in the netlog "
             f"({channels['posts_missing']} without a body)", ""]
    if other:
        lines += [f"{sum(other.values())} POSTs to other hosts: {', '.join(sorted(other))}", ""]
    lines += ["| endpoint | count | bytes | kinds | field | count | classes |", "|---|---|---|---|---|---|---|"]
    for ep, v in sorted(((public_endpoint(k), v) for k, v in channels["endpoints"].items()), key=lambda x: -x[1]["count"]):
        kinds = ", ".join(f"{k} {n}" for k, n in sorted(v["kinds"].items()))
        rows = sorted(v["fields"].items()) or [("", {"count": "", "classes": {}})]
        for i, (f, fv) in enumerate(rows):
            head = f"| `{ep}` | {v['count']} | {v['bytes']} | {kinds} |" if i == 0 else "| | | | |"
            cls = ", ".join(f"{c} {n}" for c, n in sorted(fv["classes"].items()))
            lines.append(f"{head} `{f}` | {fv['count']} | {cls} |" if f else f"{head} | | |")
    lines += ["", "| socket | sent | received | bytes sent | bytes received | topics |", "|---|---|---|---|---|---|"]
    for ws, v in sorted(((public_endpoint(k), v) for k, v in channels.get("ws", {}).items()), key=lambda x: x[0]):
        topics = ", ".join(f"`{t}` {tv['count']}" for t, tv in sorted(v["topics"].items()))
        lines.append(f"| `{ws}` | {v['frames_sent']} | {v['frames_received']} | {v['bytes_sent']} | {v['bytes_received']} | {topics} |")
    return "\n".join(lines) + "\n"


def render_matches(matches):
    if not matches:
        return "## Surfaces sent\n\nno matches.json.\n"

    def table(rows):
        out = ["| endpoint | field | surface | encoding | count |", "|---|---|---|---|---|"]
        out += [f"| `{public_endpoint(m['endpoint'])}` | `{m['field']}` | {m['surface']} | {m['encoding']} | {m['count']} |" for m in rows]
        return out
    lines = ["## Surfaces sent", ""] + table([m for m in matches if not m["weak"]])
    lines += ["", "Weak matches (a number below 100: may equal a surface by chance)", ""]
    lines += table([m for m in matches if m["weak"]])
    return "\n".join(lines) + "\n"


def render_join(channels, matches, reads):
    if not channels:
        return ""
    sent = collections.defaultdict(set)
    for m in matches or []:
        if not m["weak"]:
            sent[m["endpoint"]].add(m["surface"])
    by_script = collections.defaultdict(list)
    for ep, v in channels["endpoints"].items():
        for script in v["initiators"]:
            by_script[script].append(ep)
    lines = ["## Surface, script, channel", "", "| script | reads (top 8) | sends to | surfaces carried |", "|---|---|---|---|"]
    for script, eps in sorted(by_script.items()):
        top = ", ".join(f"{k} {n}" for k, n in (reads.get(script) or collections.Counter()).most_common(8))
        carried = ", ".join(sorted(set().union(*(sent[e] for e in eps))))
        lines.append(f"| `{public_endpoint(script)}` | {top} | {', '.join(f'`{public_endpoint(e)}`' for e in sorted(eps))} | {carried} |")
    return "\n".join(lines) + "\n"


def _load_json(path):
    if not path:
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def render(events, requests, cookies, buffer=None, intl=None):
    lines = ["# Tracking observer report", ""]
    if buffer:
        lines += [buffer, ""]
    counts = surface_counts(events)
    others = other_listener_types(events)
    rates = timing_rates(events)
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
        if others.get(site):
            lines += ["", f"Listener types outside the known set: {others[site]} distinct "
                      "(counted under [other], names not printed)."]
        if rates.get(site):
            lines += ["", "Timing call rates", "", "| API | script | calls | per second |", "|---|---|---|---|"]
            for (name, script), (n, per_s) in sorted(rates[site].items()):
                lines.append(f"| {name} | {script} | {n} | {'-' if per_s is None else f'{per_s:.1f}'} |")
        reqs = by_site.get(site)
        total = sum(reqs.values()) if reqs else 0
        lines += ["", f"Requests: {total}", "", "| host | request | count |", "|---|---|---|"]
        for (host, req), n in sorted((reqs or {}).items()):
            lines.append(f"| {host} | {req} | {n} |")
        lines.append("")
    drows = dispatch_rows(events)
    if drows:
        lines += ["## Listener dispatches", "",
                  "| group | type | target | trusted | dispatches | handlers | per second | registered by |",
                  "|---|---|---|---|---|---|---|---|"]
        for d in drows:
            typ = d["type"] + (f" ({d['types']} types)" if d["type"] == "[other]" else "")
            rate = "-" if d["rate"] is None else f"{d['rate']:.1f}"
            lines.append(f"| {d['group']} | {typ} | {d['target']} | {d['trusted']} | {d['dispatches']} "
                         f"| {d['handlers']} | {rate} | {', '.join(d['registered_by']) or '-'} |")
        never, unreg = dispatch_type_gaps(events)
        lines += ["", f"Registered but never fired: {_type_list(never)}",
                  f"Fired with no registration seen: {_type_list(unreg)}", "", DISPATCH_FLOOR_NOTE, ""]
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
    ap.add_argument("trace", help="trace JSON, or - for a trace-less arm")
    ap.add_argument("netlog")
    ap.add_argument("--cookies")
    ap.add_argument("--ram")
    ap.add_argument("--channels")
    ap.add_argument("--matches")
    a = ap.parse_args()
    cookies = load_cookie_names(a.cookies) if a.cookies else []
    data = None if a.trace == "-" else load_trace(a.trace)
    events = events_of(data) if data else []
    print(render(events, load_requests(a.netlog), cookies, buffer_note(data) if data else None,
                 intl_counts(all_events(data)) if data else None), end="")
    costs = load_costs(a.netlog)
    ch, mt = _load_json(a.channels), _load_json(a.matches)
    print(render_costs(costs))
    print(render_cpu(cpu_by_script(all_events(data) if data else [])))
    print(render_ram(ram_summary(a.ram) if a.ram else None))
    print(render_channels(ch, costs))
    print(render_matches(mt))
    print(render_join(ch, mt, reads_by_script(events)), end="")


if __name__ == "__main__":
    main()

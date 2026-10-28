"""Tracking observer verification (docs/superpowers/specs/2026-10-06-tracking-observer-design.md).

Launches content_shell on a local probe with startup tracing, no CDP attached,
and asserts EXACT per-name event counts with the right origin, site and script. Arms:
  on     Intl recipe: every row below must match exactly (probe page with its worker and Intl calls, then the hot page for V8 fast API calls)
  off    tracing on for blink,loading: zero camou.observe events, and at least one
         other event (an empty trace measured nothing)
  no-rcs v8 traced without runtime_stats: the report must say Intl blind, with V8 slices present
  --red  same as `on` with every expectation off by one: must FAIL
  dispatch  listener dispatch counts (docs/superpowers/specs/2026-10-28-observer-dispatch-counts-design.md):
         an exact run (browser launched with --camou-observe-dispatch-exact) asserts D1-D5 sums, a
         production-threshold run asserts the D1/D5 floor bounds and the report warning, and the
         category-off run asserts N-dispatch; --with-cdp-row adds D6 (trusted mousemove over CDP)
  --timing  prints call timings and trace sizes with the category off, on, and on with the Intl recipe (numbers, no verdict)
Run under ~/camoucrome-verify/venv/bin/python3 on the build box.
"""
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

import lib_shell
import observe_report

K = 3
CATEGORY = observe_report.CATEGORY
# "-*," excludes every default category: a filter listing only disabled-by-default
# categories still enables all the default ones (box, this probe: 7.17 MB and 77
# categories without "-*,", 68.9 KB and 2 with it).
ON_FILTER = "-*," + CATEGORY
# Intl recipe (docs/observer/README.md): V8 entry slices plus runtime call stats; and the
# same with the stats category left off, which must read as blind, not as zero calls
INTL_FILTER = ON_FILTER + ",v8,disabled-by-default-v8.runtime_stats"
NO_RCS_FILTER = ON_FILTER + ",v8"
INTL_ROWS = ("DateTimeFormatConstructor", "DateTimeFormatPrototypeResolvedOptions",
             "DateTimeFormatSupportedLocalesOf")

PROBE = """<!doctype html><title>observe probe</title><canvas id=c width=8 height=8></canvas>
<script src="http://localhost:%(port)d/ext.js"></script>
<script>
(async () => {
  const K = %(k)d, out = {};
  for (let i = 0; i < K; i++) {
    navigator.userAgent; navigator.deviceMemory; screen.width;
    document.getElementById('c').toDataURL(); matchMedia('(min-width: 1px)');
    document.cookie; document.title;
  }
  const dtfs = [];
  for (let i = 0; i < K; i++) { dtfs.push(new Intl.DateTimeFormat()); Intl.DateTimeFormat.supportedLocalesOf(['en']); }
  for (const d of dtfs) d.resolvedOptions();
  const gl = document.createElement('canvas').getContext('webgl');
  if (!gl) out.webgl = 'no context';
  else for (let i = 0; i < K; i++) gl.getParameter(gl.VERSION);
  const w = new Worker('/worker.js');
  await new Promise(r => { w.onmessage = r; });
  const f = document.createElement('iframe');
  f.src = 'http://localhost:%(port)d/frame.html';
  const framed = new Promise(r => { onmessage = e => { if (e.data === 'frame-done') r(); }; });
  document.body.appendChild(f);
  await framed;
  await fetch('/done', {method: 'POST', body: JSON.stringify(out)});
})();
</script>"""
# a parser-blocking cross-origin script: runs in the main frame (origin 127.0.0.1)
# before the inline probe script, like a third-party tag such as fbevents.js
EXT = "for (let i = 0; i < %(k)d; i++) navigator.userAgent;"
WORKER = ("const d = []; for (let i = 0; i < %(k)d; i++) { navigator.hardwareConcurrency; "
          "d.push(new Intl.DateTimeFormat()); Intl.DateTimeFormat.supportedLocalesOf(['en']); } "
          "for (const f of d) f.resolvedOptions(); postMessage('w');")
FRAME = ("<!doctype html><script>for (let i = 0; i < %(k)d; i++) navigator.userAgent;"
         "parent.postMessage('frame-done', '*');</script>")
TIMING = """<!doctype html><canvas id=c width=64 height=64></canvas><script>
(async () => {
  const t0 = performance.now(); for (let i = 0; i < 200000; i++) navigator.userAgent;
  const t1 = performance.now(); const c = document.getElementById('c');
  for (let i = 0; i < 300; i++) c.toDataURL();
  const t2 = performance.now();
  const el = document.createElement('div'), f = () => {};
  const d0 = Date.now(); for (let i = 0; i < 100000; i++) el.addEventListener('probe', f);
  const d1 = Date.now(); for (let i = 0; i < 200000; i++) performance.now();
  const d2 = Date.now();
  await fetch('/done', {method: 'POST', body: JSON.stringify({ua_200k_ms: t1 - t0, todataurl_300_ms: t2 - t1,
    addeventlistener_100k_ms: d1 - d0, performance_now_200k_ms: d2 - d1})});
})();
</script>"""

# [NoAllocDirectCall] fast paths (V8 fast API calls) take over once V8 optimizes
# the loop; with the hook only on the slow callbacks these counts come out short.
HOT_N = 100000
HOT = """<!doctype html><canvas id=c width=8 height=8></canvas><script>
(async () => {
  const ctx = document.getElementById('c').getContext('2d');
  for (let i = 0; i < %(n)d; i++) { ctx.lineWidth = 1 + (i & 1); ctx.fillRect(0, 0, 1, 1); }
  await fetch('/done', {method: 'POST', body: '{}'});
})();
</script>"""


# Behaviour signals (docs/superpowers/specs/2026-10-28-observer-behaviour-signals-design.md).
# The page itself uses no timer, rAF or performance.now except the counted calls below: it waits on
# promises and fetch only, so every count is exact.
BEHAVE = """<!doctype html><title>behaviour probe</title><div id=inl onclick="1"></div><div id=el></div>
<script>
(async () => {
  const K = %(k)d, f = () => {};
  for (let i = 0; i < K; i++) window.addEventListener('wheel', f, {passive: false});
  window.addEventListener('wheel', f, {passive: true});
  for (let i = 0; i < 2; i++) { document.addEventListener('keydown', f, true); document.addEventListener('visibilitychange', f); }
  document.getElementById('el').addEventListener('pointermove', f, {once: true});
  window.ondevicemotion = f; window.ondeviceorientation = f;
  window.addEventListener('probe-custom-type-xyz', f);
  for (let i = 0; i < K; i++) {
    performance.now(); requestAnimationFrame(f); setTimeout(f, 0);
    const id = setInterval(() => clearInterval(id), 50);
    document.hidden; document.visibilityState; document.webkitHidden; document.hasFocus();
    navigator.clipboard.writeText('x').catch(f); navigator.clipboard.readText().catch(f);
    new DeviceOrientationEvent('deviceorientation', {alpha: 1}).alpha;
    new DeviceMotionEvent('devicemotion', {acceleration: {x: 1}}).acceleration;
    window.removeEventListener('wheel', f); performance.mark('m'); document.title;
    clearTimeout(0); cancelAnimationFrame(0);
  }
  new ClipboardItem({'text/plain': new Blob(['x'], {type: 'text/plain'})});
  document.execCommand('copy');
  try { new Accelerometer(); } catch (e) {}
  const w = new Worker('/bworker.js');
  await new Promise(r => { w.onmessage = r; });
  const fr = document.createElement('iframe');
  fr.src = 'http://localhost:%(port)d/bframe.html';
  const framed = new Promise(r => { onmessage = e => { if (e.data === 'frame-done') r(); }; });
  document.body.appendChild(fr);
  await framed;
  await fetch('/done', {method: 'POST', body: '{}'});
})();
</script>"""
BWORKER = ("const f = () => {}; self.addEventListener('message', f); self.addEventListener('message', f);"
           "for (let i = 0; i < %(k)d; i++) { performance.now(); setTimeout(f, 0); } postMessage('w');")
BFRAME = ("<!doctype html><script>addEventListener('touchstart', () => {});"
          "parent.postMessage('frame-done', '*');</script>")


# Page invisibility (conventions rule 2): the same page on the same binary with the category on and
# off must report identical values, and the hooked accessors must stay [native code].
INV = """<!doctype html><script>
(async () => {
  const sig = (g) => {
    const out = {};
    const t = (o, k) => { try { return Function.prototype.toString.call(o[k]); } catch (e) { return 'ERR ' + e.name; } };
    out.now = t(g.Performance.prototype, 'now');
    out.ael = t(g.EventTarget.prototype, 'addEventListener');
    out.raf = typeof g.requestAnimationFrame === 'function' ? Function.prototype.toString.call(g.requestAnimationFrame) : 'n/a';
    out.st = Function.prototype.toString.call(g.setTimeout);
    out.keys = Object.keys(g).join(',');
    out.nowType = typeof performance.now();
    return out;
  };
  const res = {main: sig(window)};
  const w = new Worker('/iworker.js');
  res.worker = await new Promise(r => { w.onmessage = e => r(e.data); });
  await fetch('/done', {method: 'POST', body: JSON.stringify(res)});
})();
</script>"""
IWORKER = """const t = (o, k) => { try { return Function.prototype.toString.call(o[k]); } catch (e) { return 'ERR ' + e.name; } };
postMessage({now: t(Performance.prototype, 'now'), ael: t(EventTarget.prototype, 'addEventListener'),
  raf: typeof self.requestAnimationFrame === 'function' ? Function.prototype.toString.call(self.requestAnimationFrame) : 'n/a',
  st: Function.prototype.toString.call(self.setTimeout), keys: Object.keys(self).join(','), nowType: typeof performance.now()});"""


# Listener dispatch counts. The custom types d1..d5x* are used by this page only. Every listener is a
# fresh closure: the same function with the same options would be de-duplicated by addEventListener.
DISPATCH = """<!doctype html><title>dispatch probe</title><div id=p><div id=m><div id=c></div></div></div>
<script>
(async () => {
  const ev = (t, b) => new Event(t, {bubbles: !!b});
  const d = document.createElement('div');
  for (let i = 0; i < 3; i++) d.addEventListener('d1', () => {});
  for (let i = 0; i < 1000; i++) d.dispatchEvent(ev('d1'));
  for (const id of ['c', 'm', 'p']) document.getElementById(id).addEventListener('d2', () => {});
  document.getElementById('c').dispatchEvent(ev('d2', true));
  const g = () => {};
  d.addEventListener('d3', g); d.removeEventListener('d3', g);
  for (let i = 0; i < 5; i++) d.dispatchEvent(ev('d3'));
  const w = new Worker('/dworker.js');
  await new Promise(r => { w.onmessage = r; });
  for (let i = 0; i < 100; i++) { d.addEventListener('d5x' + i, () => {}); d.dispatchEvent(ev('d5x' + i)); }
  await fetch('/done', {method: 'POST', body: '{}'});
})();
</script>"""
DWORKER = ("for (let i = 0; i < 3; i++) self.addEventListener('d4', () => {}); "
           "self.dispatchEvent(new Event('d4')); postMessage('w');")
# D6: a page with a trusted-input listener; the move itself comes over CDP (--with-cdp-row)
MOUSE = "<!doctype html><title>mouse probe</title><script>addEventListener('mousemove', () => {});</script>"
DISPATCH_EVENT = observe_report.DISPATCH


def serve(k):
    done = threading.Event()
    result = {}

    class H(http.server.BaseHTTPRequestHandler):
        def _send(self, body, ctype):
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            port = self.server.server_port
            pages = {"/probe.html": (PROBE % {"k": k, "port": port}, "text/html"),
                     "/timing.html": (TIMING, "text/html"),
                     "/hot.html": (HOT % {"n": HOT_N}, "text/html"),
                     "/dispatch.html": (DISPATCH, "text/html"),
                     "/dworker.js": (DWORKER, "application/javascript"),
                     "/mouse.html": (MOUSE, "text/html"),
                     "/behave.html": (BEHAVE % {"k": k, "port": port}, "text/html"),
                     "/bworker.js": (BWORKER % {"k": k}, "application/javascript"),
                     "/bframe.html": (BFRAME, "text/html"),
                     "/inv.html": (INV, "text/html"),
                     "/iworker.js": (IWORKER, "application/javascript"),
                     "/worker.js": (WORKER % {"k": k}, "application/javascript"),
                     "/ext.js": (EXT % {"k": k}, "application/javascript"),
                     "/frame.html": (FRAME % {"k": k}, "text/html")}
            body, ctype = pages.get(self.path, ("", "text/plain"))
            self._send(body, ctype)

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            result.update(json.loads(self.rfile.read(n) or b"{}"))
            self._send("", "text/plain")
            done.set()

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, done, result


def run(page, categories, k=K, extra=()):
    """One browser session; returns (every trace event or None, page result, trace_path)."""
    server, done, result = serve(k)
    port = server.server_port
    tmp = tempfile.mkdtemp(prefix="camoucrome-observe-")
    trace = os.path.join(tmp, "trace.json")
    argv = [lib_shell.SHELL, *lib_shell.SHELL_FLAGS,
            "--use-angle=swiftshader", "--enable-unsafe-swiftshader",  # no GPU on the box
            f"--user-data-dir={tmp}/profile",
            *extra, f"--trace-startup={categories}", "--trace-startup-format=json",
            f"--trace-startup-file={trace}", "--trace-startup-duration=20",
            "--trace-startup-record-mode=record-as-much-as-possible",
            f"http://127.0.0.1:{port}/{page}"]
    env = {k_: v for k_, v in os.environ.items() if not k_.startswith("CAMOU_")}
    proc = subprocess.Popen(argv, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not done.wait(60):
            return None, {"error": "probe never reported"}, trace
        # SIGTERM does not flush content_shell's trace: the duration timer does
        for _ in range(80):
            if os.path.exists(trace):
                time.sleep(1)  # let the writer finish
                break
            time.sleep(0.5)
    finally:
        proc.terminate()
        try:
            proc.wait(30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(10)
        server.shutdown()
    if not os.path.exists(trace):
        return None, dict(result, error="no trace file written"), trace
    data = observe_report.load_trace(trace)
    return (data["traceEvents"] if isinstance(data, dict) else data), result, trace


def off_arm(events):
    """(ok, camou events, other events): the category must stay off while tracing
    demonstrably ran; metadata (thread names) is written even when nothing else is."""
    if events is None:
        return False, None, None
    camou = sum(e.get("cat") == CATEGORY for e in events)
    other = sum(e.get("cat") not in (CATEGORY, "__metadata") for e in events)
    return camou == 0 and other > 0, camou, other


def tally(events):
    counts = {}
    for e in events:
        a = e.get("args", {})
        key = (e["name"], a.get("origin"), a.get("site"), a.get("script"))
        counts[key] = counts.get(key, 0) + 1
    return counts


def hot_rows(c, main_origin, top, n, bump):
    """Exact counts for one fast-path method and one fast-path setter on /hot.html."""
    hot = f"{main_origin}/hot.html"
    rows = []
    for name in ("CanvasRenderingContext2D.fillRect", "CanvasRenderingContext2D.lineWidth.set"):
        got = c.get((name, main_origin, top, hot), 0)
        rows.append((got == n + bump, f"{name} x{n} (fast path) script={hot}: {got} (want {n + bump})"))
    return rows


def intl_rows(ic, site, scripts, k, bump):
    """Exact counts of the probe's three Intl built-ins per entry script (main, worker)."""
    rows = []
    for script in scripts:
        for name in INTL_ROWS:
            got = (ic or {}).get((site, script, name), 0)
            rows.append((got == k + bump, f"{name} site={site} script={script}: {got} (want {k + bump})"))
    return rows


def behave_rows(events, main_origin, frame_origin, top, k, bump):
    """Exact counts of the behaviour-signal probe. Listener rows are keyed by (type, target, opts)
    and, where it matters, the registering origin and site; the rest by API name."""
    L = [(e["args"].get("type"), e["args"].get("target"), e["args"].get("opts", ""),
          e["args"].get("origin"), e["args"].get("site"))
         for e in events if e["name"] == observe_report.LISTENER]
    c = tally(events)

    def listeners(typ, target, opts, origin=main_origin, site=top):
        return sum(1 for (t_, tg, o, og, s) in L if (t_, tg, o, og, s) == (typ, target, opts, origin, site))

    script = f"{main_origin}/behave.html"

    def api(*names, origin=main_origin, site=top, script=None):
        return sum(n for (nm, og, s, sc), n in c.items() if nm in names and og == origin and s == site
                   and (script is None or sc == script))

    rows = []

    def row(label, got, want):
        rows.append((got == want + bump, f"{label}: {got} (want {want + bump})"))

    row("L1 addEventListener wheel Window (passive:false) x K", listeners("wheel", "DOMWindow", ""), k)
    row("L1 addEventListener wheel Window passive", listeners("wheel", "DOMWindow", "passive"), 1)
    row("L2 keydown Document capture x2", listeners("keydown", "Document", "capture"), 2)
    row("L2 visibilitychange Document x2", listeners("visibilitychange", "Document", ""), 2)
    row("L3 pointermove HTMLDivElement once", listeners("pointermove", "Element", "once"), 1)
    row("L4 ondevicemotion setter", listeners("devicemotion", "DOMWindow", ""), 1)
    row("L4 ondeviceorientation setter", listeners("deviceorientation", "DOMWindow", ""), 1)
    row("L5 inline onclick attribute", listeners("click", "Element", ""), 1)
    row("L6 worker message x2 (origin of the creator, no site)",
        listeners("message", "DedicatedWorkerGlobalScope", "", site=""), 2)
    row("L7 cross-site frame touchstart (passive by default on a window)",
        listeners("touchstart", "DOMWindow", "passive", origin=frame_origin), 1)
    row("L8 custom type recorded in the raw trace", listeners("probe-custom-type-xyz", "DOMWindow", ""), 1)
    md = observe_report.render(observe_report.events_of(events), [], [])
    rows.append(("probe-custom-type-xyz" not in md, "L8 report never prints a type outside the known set"))
    row("T1 Performance.now page x K", api("Performance.now"), k)
    row("T1 Performance.now worker x K", api("Performance.now", site=""), k)
    row("T2 requestAnimationFrame x K", api("Window.requestAnimationFrame"), k)
    # a mixin member is emitted under the host interface's name, or the mixin's: both are accepted
    # and the label says which the generator produced
    timers = ("Window.setTimeout", "WindowOrWorkerGlobalScope.setTimeout")
    ivals = ("Window.setInterval", "WindowOrWorkerGlobalScope.setInterval")
    wtimers = ("WorkerGlobalScope.setTimeout", "DedicatedWorkerGlobalScope.setTimeout",
               "WindowOrWorkerGlobalScope.setTimeout")
    row("T2 setTimeout page x K", api(*timers), k)
    row("T2 setInterval page x K", api(*ivals), k)
    row("T2 setTimeout worker x K", api(*wtimers, site=""), k)
    for name in ("Document.hidden.get", "Document.visibilityState.get", "Document.webkitHidden.get",
                 "Document.hasFocus"):
        row(f"F1 {name} x K", api(name), k)
    row("C1 Clipboard.writeText x K", api("Clipboard.writeText"), k)
    row("C1 Clipboard.readText x K", api("Clipboard.readText"), k)
    row("C1 ClipboardItem.constructor", api("ClipboardItem.constructor"), 1)
    row("C1 Document.execCommand", api("Document.execCommand"), 1)
    row("M1 DeviceOrientationEvent.constructor x K (page script)", api("DeviceOrientationEvent.constructor", script=script), k)
    row("M1 DeviceOrientationEvent.alpha.get x K", api("DeviceOrientationEvent.alpha.get"), k)
    row("M1 DeviceMotionEvent.constructor x K (page script)", api("DeviceMotionEvent.constructor", script=script), k)
    # once ondevicemotion/ondeviceorientation exist, Blink constructs one event of each kind with no
    # script on the stack: a tell that a page registered motion listeners
    row("M1 DeviceOrientationEvent.constructor (no script, internal)", api("DeviceOrientationEvent.constructor", script=""), 1)
    row("M1 DeviceMotionEvent.constructor (no script, internal)", api("DeviceMotionEvent.constructor", script=""), 1)
    row("M1 DeviceMotionEvent.acceleration.get x K", api("DeviceMotionEvent.acceleration.get"), k)
    row("M2 Accelerometer.constructor", api("Accelerometer.constructor"), 1)
    for name in ("Performance.mark", "Document.title.get", "Window.clearTimeout",
                 "Window.cancelAnimationFrame", "EventTarget.removeEventListener"):
        row(f"N1 {name} (not allow-listed)", api(name), 0)
    return rows


def _fires(events, prefix=None, typ=None, target=None, trusted=None):
    """(dispatches, handlers, flushed events) over raw EventTarget.dispatch events; the custom
    types are not in KNOWN_EVENT_TYPES, so the rows read the trace, never the report text."""
    d = h = n = 0
    for e in events:
        a = e.get("args", {})
        if e["name"] != DISPATCH_EVENT or (typ is not None and a.get("type") != typ) \
                or (prefix is not None and not a.get("type", "").startswith(prefix)) \
                or (target is not None and a.get("target") != target) \
                or (trusted is not None and a.get("trusted") != trusted):
            continue
        d += observe_report._int(a.get("dispatches"))
        h += observe_report._int(a.get("handlers"))
        n += 1
    return d, h, n


def dispatch_rows_check(events, bump, exact):
    """Rows D1-D5 on /dispatch.html. exact: the browser ran with --camou-observe-dispatch-exact
    (threshold 1), so sums are exact; otherwise only the flush-threshold bounds hold. --red (bump)
    makes an exact expectation off by one and inverts a bound (a range has no 'one more')."""
    rows = []

    def row(label, got, want):
        rows.append((got == want + bump, f"{label}: {got} (want {want + bump})"))

    def within(label, got, lo, hi):
        rows.append(((lo <= got <= hi) != bool(bump), f"{label}: {got} (want {lo}..{hi}"
                     + (", RED: inverted)" if bump else ")")))

    md = observe_report.render(events, [], [])
    if exact:
        d1 = _fires(events, typ="d1", target="Element", trusted="false")
        row("D1 d1 dispatchEvent x1000 dispatches (Element, trusted false)", d1[0], 1000)
        row("D1 d1 handlers (3 listeners x 1000)", d1[1], 3000)
        row("D1 d1 trusted dispatches", _fires(events, typ="d1", trusted="true")[0], 0)
        d2 = _fires(events, typ="d2", target="Element")
        row("D2 bubbling child + 2 ancestors dispatches (Element)", d2[0], 3)
        row("D2 bubbling handlers", d2[1], 3)
        row("D3 listener removed before dispatch counts", _fires(events, typ="d3")[0], 0)
        d4 = _fires(events, typ="d4", target="Worker", trusted="false")
        row("D4 worker dispatchEvent dispatches (target Worker)", d4[0], 1)
        row("D4 worker handlers (3 listeners)", d4[1], 3)
        row("D5 100 distinct custom types, dispatches", _fires(events, prefix="d5x")[0], 100)
    else:
        within("D1 tail: summed flushed d1 dispatches", _fires(events, typ="d1")[0], 768, 1000)
        # 100 one-dispatch keys against a 64-key table: at least 36 keys were evicted and flushed
        within("D5 key cap: distinct d5x keys flushed", _fires(events, prefix="d5x")[2], 36, 100)
        rows.append(((observe_report.DISPATCH_FLOOR_NOTE in md) != bool(bump),
                     "report prints the dispatch floor warning"))
    rows.append(("d5x" not in md, "D5 report never prints a custom type"))
    return rows


def n_dispatch_row(events, bump):
    """Category off: the page dispatches, the trace holds no EventTarget.dispatch event."""
    got = _fires(events)[2]
    return got == bump, f"N-dispatch category off, dispatch events: {got} (want {bump})"


def trusted_mouse_row(events, bump):
    """D6: a browser-delivered mousemove reaches the page listener (a CDP session, verification only)."""
    got = _fires(events, typ="mousemove", trusted="true")[0]
    return (got > 0) != bool(bump), f"D6 trusted mousemove dispatches: {got} (want > 0{', RED: inverted' if bump else ''})"


def run_cdp_mouse():
    """One Input.dispatchMouseEvent through lib_shell, a separate session from every fidelity arm.
    Returns the raw events or None. shortcut: the page expression only keeps the browser alive past
    --trace-startup-duration, because SIGTERM does not flush the trace."""
    server, _, _ = serve(K)
    tmp = tempfile.mkdtemp(prefix="camoucrome-observe-")
    trace = os.path.join(tmp, "trace.json")
    flags = [f"--trace-startup={ON_FILTER}", "--trace-startup-format=json", f"--trace-startup-file={trace}",
             "--trace-startup-duration=6", "--trace-startup-record-mode=record-as-much-as-possible"]
    try:
        _, err = lib_shell.session(
            {}, ["new Promise(r => setTimeout(r, 9000))"],
            navigate_to=f"http://127.0.0.1:{server.server_port}/mouse.html", extra_flags=flags,
            cdp=[("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 20, "y": 20})])
    finally:
        server.shutdown()
    if err is not None or not os.path.exists(trace):
        return None
    data = observe_report.load_trace(trace)
    return observe_report.events_of(data)


def invisibility_rows(on, off):
    """The hooked accessors stay native, and a page sees the same values with the category on and
    off (same binary): the observer must not be observable from the page."""
    rows = []
    for scope in ("main", "worker"):
        for key in ("now", "ael", "st"):
            s = (on.get(scope) or {}).get(key, "")
            rows.append(("[native code]" in s, f"{scope} {key}.toString() is native: {s[:60]!r}"))
    rows.append((bool(on) and on == off, "page-visible signature identical, category on vs off "
                 "(toString, Object.keys(global), worker parity)"))
    rows.append(((on.get("main", {}).get("keys") == off.get("main", {}).get("keys")),
                 "Object.keys(window) identical, category on vs off"))
    return rows


def blind_arm(events):
    """(ok, V8 entry slices): v8 traced without runtime_stats must report blind, and V8
    slices must be present, or the arm measured nothing."""
    if events is None:
        return False, None
    n = sum(e.get("name") in observe_report.V8_ENTRY for e in events)
    return observe_report.intl_counts(events) is None and n > 0, n


def main():
    red = "--red" in sys.argv
    if "--timing" in sys.argv:
        for label, cats in (("off", "blink,loading"), ("on", ON_FILTER), ("intl", INTL_FILTER)):
            _, res, trace = run("timing.html", cats)
            size = os.path.getsize(trace) if os.path.exists(trace) else None
            print(f"timing {label}: {res} trace_bytes={size}")
        return 0

    rows = []
    events, res, trace = run("probe.html", INTL_FILTER)
    if events is None:
        print(f"FAIL on-arm: {res}")
        return 1
    if "webgl" in res:
        print(f"FAIL on-arm: probe reported {res}")
        return 1
    c = tally(observe_report.events_of(events))
    port = None
    for (name, origin, site, script) in c:
        if origin and origin.startswith("http://127.0.0.1:"):
            port = origin.rsplit(":", 1)[1]
            break
    main_origin, frame_origin, top = (f"http://127.0.0.1:{port}", f"http://localhost:{port}",
                                      "http://127.0.0.1")
    probe, ext = f"{main_origin}/probe.html", f"{frame_origin}/ext.js"
    bump = 1 if red else 0

    def count(name, origin, site=None, script=None):
        return sum(n for (n_, o, s, sc), n in c.items() if n_ == name and o == origin
                   and (site is None or s == site) and (script is None or sc == script))

    expect = [(n, main_origin, top, None) for n in (
        "Navigator.deviceMemory.get", "Screen.width.get", "HTMLCanvasElement.toDataURL",
        "Window.matchMedia", "Document.cookie.get", "WebGLRenderingContext.getParameter")]
    # ext.js reads share name/origin/site with the probe's own: split them by script
    expect.insert(0, ("Navigator.userAgent.get", main_origin, top, probe))
    expect += [("WorkerNavigator.hardwareConcurrency.get", main_origin, "", None),
               ("Navigator.userAgent.get", frame_origin, top, None),
               # script attribution: the URL at the top of the stack (inline scripts report
               # their document; an external script its own URL, whatever origin it reads from)
               ("Navigator.userAgent.get", main_origin, None, probe),
               ("WorkerNavigator.hardwareConcurrency.get", main_origin, None, f"{main_origin}/worker.js"),
               ("Navigator.userAgent.get", frame_origin, None, f"{frame_origin}/frame.html"),
               ("Navigator.userAgent.get", main_origin, top, ext)]
    for name, origin, site, script in expect:
        got = count(name, origin, site, script)
        label = (f"{name} origin={origin}" + ("" if site is None else f" site={site!r}")
                 + ("" if script is None else f" script={script}"))
        rows.append((got == K + bump, f"{label}: {got} (want {K + bump})"))
    title = sum(n for (name, _, _, _), n in c.items() if name.startswith("Document.title"))
    rows.append((title == 0 + bump, f"Document.title (not allow-listed): {title} (want {0 + bump})"))
    label = observe_report.script_label
    rows += intl_rows(observe_report.intl_counts(events), top,
                      (label(probe), label(f"{main_origin}/worker.js")), K, bump)

    # fast paths: a separate session, so 2 x HOT_N events do not crowd the probe's trace
    hot_events, hot_res, _ = run("hot.html", ON_FILTER)
    if hot_events is None:
        rows.append((red, f"hot arm: {hot_res}"))  # never an expected --red failure
    else:
        hc = tally(observe_report.events_of(hot_events))
        hot_port = next((o.rsplit(":", 1)[1] for (_, o, _, _) in hc
                         if o and o.startswith("http://127.0.0.1:")), None)
        rows += hot_rows(hc, f"http://127.0.0.1:{hot_port}", top, HOT_N, bump)

    # behaviour signals: a separate session, so its listener and timer events do not crowd the probe's
    bev, bres, _ = run("behave.html", ON_FILTER)
    if bev is None:
        rows.append((red, f"behaviour arm: {bres}"))  # never an expected --red failure
    else:
        bobs = observe_report.events_of(bev)
        bport = next((o.rsplit(":", 1)[1] for e in bobs for o in [e["args"].get("origin", "")]
                      if o.startswith("http://127.0.0.1:")), None)
        rows += behave_rows(bobs, f"http://127.0.0.1:{bport}", f"http://localhost:{bport}", top, K, bump)

    # dispatch counts: exact run (verify-only switch), production-threshold run, category off
    for label, cats, extra, exact in (("exact", ON_FILTER, ["--camou-observe-dispatch-exact"], True),
                                      ("production-threshold", ON_FILTER, [], False)):
        dev_, dres, _ = run("dispatch.html", cats, extra=extra)
        if dev_ is None:
            rows.append((red, f"dispatch arm ({label}): {dres}"))  # never an expected --red failure
        else:
            rows += dispatch_rows_check(observe_report.events_of(dev_), bump, exact)
    dn, dnres, _ = run("dispatch.html", "blink,loading")
    if dn is None:
        rows.append((red, f"dispatch off arm: {dnres}"))
    else:
        rows.append((off_arm(dn)[0] == (not red), "N-dispatch off arm: tracing ran (want 0 camou, >0 other events)"))
        rows.append(n_dispatch_row(observe_report.events_of(dn), bump))
    if "--with-cdp-row" in sys.argv:
        cev = run_cdp_mouse()
        rows.append(trusted_mouse_row(cev, bump) if cev is not None else (red, "D6 CDP session never wrote a trace"))

    # invisibility: the same page, category on and off
    inv_on = run("inv.html", ON_FILTER)[1]
    inv_off = run("inv.html", "blink,loading")[1]
    if "error" in inv_on or "error" in inv_off:
        rows.append((red, f"invisibility arm: {inv_on} / {inv_off}"))
    else:
        rows += [(ok and not red, text) for ok, text in invisibility_rows(inv_on, inv_off)]

    # off arm: a normal default set ("blink,loading") must not pull the category in
    off_events, off_res, _ = run("probe.html", "blink,loading")
    off_ok, off_camou, off_other = off_arm(off_events)
    rows.append((off_ok == (not red), "off arm (blink,loading traced, category not requested): "
                 + ("no file" if off_events is None else f"{off_camou} camou, {off_other} other events")
                 + " (want 0 camou, >0 other)"))
    rows.append(((off_events is not None and observe_report.intl_counts(off_events) is None) == (not red),
                 "off arm: report says Intl blind (want blind)"))
    nr_events, _, _ = run("probe.html", NO_RCS_FILTER)
    nr_ok, nr_slices = blind_arm(nr_events)
    rows.append((nr_ok == (not red), f"v8 on, runtime_stats off: Intl blind with {nr_slices} V8 entry "
                 "slices (want blind, >0 slices)"))

    passed = sum(ok for ok, _ in rows)
    for ok, text in rows:
        print(("PASS " if ok else "FAIL ") + text)
    print(f"{passed}/{len(rows)} PASS{' (RED mode: expected failures)' if red else ''}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())

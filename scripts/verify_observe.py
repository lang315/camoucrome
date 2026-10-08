"""Tracking observer verification (docs/superpowers/specs/2026-10-06-tracking-observer-design.md).

Launches content_shell on a local probe with startup tracing, no CDP attached,
and asserts EXACT per-name event counts with the right origin, site and script. Arms:
  on     category enabled: every row below must match exactly (probe page, then the hot page for V8 fast API calls)
  off    tracing on for blink,loading: zero camou.observe events, and at least one
         other event (an empty trace measured nothing)
  --red  same as `on` with every expectation off by one: must FAIL
  --timing  prints call timings with the category off and on (numbers, no verdict)
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
WORKER = "for (let i = 0; i < %(k)d; i++) navigator.hardwareConcurrency; postMessage('w');"
FRAME = ("<!doctype html><script>for (let i = 0; i < %(k)d; i++) navigator.userAgent;"
         "parent.postMessage('frame-done', '*');</script>")
TIMING = """<!doctype html><canvas id=c width=64 height=64></canvas><script>
(async () => {
  const t0 = performance.now(); for (let i = 0; i < 200000; i++) navigator.userAgent;
  const t1 = performance.now(); const c = document.getElementById('c');
  for (let i = 0; i < 300; i++) c.toDataURL();
  const t2 = performance.now();
  await fetch('/done', {method: 'POST', body: JSON.stringify({ua_200k_ms: t1 - t0, todataurl_300_ms: t2 - t1})});
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


def run(page, categories, k=K):
    """One browser session; returns (every trace event or None, page result, trace_path)."""
    server, done, result = serve(k)
    port = server.server_port
    tmp = tempfile.mkdtemp(prefix="camoucrome-observe-")
    trace = os.path.join(tmp, "trace.json")
    argv = [lib_shell.SHELL, *lib_shell.SHELL_FLAGS,
            "--use-angle=swiftshader", "--enable-unsafe-swiftshader",  # no GPU on the box
            f"--user-data-dir={tmp}/profile",
            f"--trace-startup={categories}", "--trace-startup-format=json",
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


def main():
    red = "--red" in sys.argv
    if "--timing" in sys.argv:
        for label, cats in (("off", "blink,loading"), ("on", ON_FILTER)):
            _, res, _ = run("timing.html", cats)
            print(f"timing {label}: {res}")
        return 0

    rows = []
    events, res, trace = run("probe.html", ON_FILTER)
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

    # fast paths: a separate session, so 2 x HOT_N events do not crowd the probe's trace
    hot_events, hot_res, _ = run("hot.html", ON_FILTER)
    if hot_events is None:
        rows.append((red, f"hot arm: {hot_res}"))  # never an expected --red failure
    else:
        hc = tally(observe_report.events_of(hot_events))
        hot_port = next((o.rsplit(":", 1)[1] for (_, o, _, _) in hc
                         if o and o.startswith("http://127.0.0.1:")), None)
        rows += hot_rows(hc, f"http://127.0.0.1:{hot_port}", top, HOT_N, bump)

    # off arm: a normal default set ("blink,loading") must not pull the category in
    off_events, off_res, _ = run("probe.html", "blink,loading")
    off_ok, off_camou, off_other = off_arm(off_events)
    rows.append((off_ok == (not red), "off arm (blink,loading traced, category not requested): "
                 + ("no file" if off_events is None else f"{off_camou} camou, {off_other} other events")
                 + " (want 0 camou, >0 other)"))

    passed = sum(ok for ok, _ in rows)
    for ok, text in rows:
        print(("PASS " if ok else "FAIL ") + text)
    print(f"{passed}/{len(rows)} PASS{' (RED mode: expected failures)' if red else ''}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())

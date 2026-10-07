"""Tracking observer verification (docs/superpowers/specs/2026-10-06-tracking-observer-design.md).

Launches content_shell on a local probe with startup tracing, no CDP attached,
and asserts EXACT per-name event counts with the right origin and site. Arms:
  on     category enabled: every row below must match exactly
  off    tracing on for other categories: zero camou.observe events
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
# categories still enables all the default ones (51 MB trace for a tiny probe).
ON_FILTER = "-*," + CATEGORY

PROBE = """<!doctype html><title>observe probe</title><canvas id=c width=8 height=8></canvas>
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
                     "/worker.js": (WORKER % {"k": k}, "application/javascript"),
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
    """One browser session; returns (events or None, page result, trace_path)."""
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
    return observe_report.load_events(trace), result, trace


def tally(events):
    counts = {}
    for e in events:
        a = e.get("args", {})
        key = (e["name"], a.get("origin"), a.get("site"))
        counts[key] = counts.get(key, 0) + 1
    return counts


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
    c = tally(events)
    port = None
    for (name, origin, site) in c:
        if origin and origin.startswith("http://127.0.0.1:"):
            port = origin.rsplit(":", 1)[1]
            break
    main_origin, frame_origin, top = (f"http://127.0.0.1:{port}", f"http://localhost:{port}",
                                      "http://127.0.0.1")
    bump = 1 if red else 0
    expect = {(n, main_origin, top): K + bump for n in (
        "Navigator.userAgent.get", "Navigator.deviceMemory.get", "Screen.width.get",
        "HTMLCanvasElement.toDataURL", "Window.matchMedia", "Document.cookie.get",
        "WebGLRenderingContext.getParameter")}
    expect[("WorkerNavigator.hardwareConcurrency.get", main_origin, "")] = K + bump
    expect[("Navigator.userAgent.get", frame_origin, top)] = K + bump
    for key, want in expect.items():
        got = c.get(key, 0)
        rows.append((got == want, f"{key[0]} origin={key[1]} site={key[2]!r}: {got} (want {want})"))
    title = sum(n for (name, _, _), n in c.items() if name.startswith("Document.title"))
    rows.append((title == 0 + bump, f"Document.title (not allow-listed): {title} (want {0 + bump})"))

    # off arm: a normal default set ("blink,loading") must not pull the category in
    off_events, off_res, _ = run("probe.html", "blink,loading")
    off_ok = off_events is not None and len(off_events) == 0
    rows.append((off_ok == (not red), f"off arm (tracing on, category not requested): "
                 f"{'no file' if off_events is None else len(off_events)} camou events (want 0)"))

    passed = sum(ok for ok, _ in rows)
    for ok, text in rows:
        print(("PASS " if ok else "FAIL ") + text)
    print(f"{passed}/{len(rows)} PASS{' (RED mode: expected failures)' if red else ''}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())

"""SP2b measurement 3: is the attached-state timing cost from Runtime, or from
any CDP attach at all?

Measurement 2 found state C (Playwright attached) ~24% slower at Error+.stack
construction than unattached, non-overlapping across runs -- but with a
confound it could not remove: Playwright navigates through its own page agent
and enables the Runtime domain, so "attach", "Runtime.enable" and "a
concurrent agent" all changed at once. This measurement removes them one at a
time by driving CDP directly over a raw WebSocket, enabling exactly the
domains named and nothing else.

Four states, each the SAME self-timing page reporting over plain HTTP so the
result never travels the channel under test:

  A  no debugging port                          (baseline, from measurement 2)
  B  port open, nothing attached                (baseline, from measurement 2)
  D  raw CDP attached, Page domain only, NO Runtime, no injected agent
  E  raw CDP attached, Page + Runtime.enable, still no injected agent

D vs B isolates the cost of a bare attach. E vs D isolates Runtime.enable
specifically -- which is the exact thing D1 option (a), "never enable the
Runtime domain", would avoid. If D matches B and only E is elevated, option
(a) closes the vector and no V8 patch is warranted. If D is already elevated,
the cost is inherent to CDP attach and option (a) does not help.

There is deliberately no Playwright here. Playwright was the confound; this
attaches with a WebSocket and speaks CDP by hand so that the only domains
enabled are the ones each state names.
"""

import http.server
import json
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

import websocket  # websocket-client 1.9.0, installed into the venv

import lib_shell

TRIALS = 7
ERRORS_PER_TRIAL = 10000

PAGE = """<!doctype html><title>attach</title><script>
(async () => {
  const TRIALS = %d, N = %d;
  const times = [];
  for (let t = 0; t < TRIALS; t++) {
    const t0 = performance.now();
    let sink = 0;
    for (let i = 0; i < N; i++) sink += (new Error('probe')).stack.length;
    times.push(performance.now() - t0);
    if (sink < 0) console.log(sink);
  }
  await fetch('/result?d=' + encodeURIComponent(JSON.stringify({
    times_ms: times,
    stack_trace_limit: Error.stackTraceLimit,
    has_prepare: typeof Error.prepareStackTrace,
  })));
})();
</script>"""


def serve():
    got = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            p = urllib.parse.urlparse(self.path)
            if p.path == "/result":
                got.append(json.loads(urllib.parse.parse_qs(p.query)["d"][0]))
                body = b"ok"
            else:
                body = (PAGE % (TRIALS, ERRORS_PER_TRIAL)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_port}/", got, srv


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def launch_with_port(flags):
    """chrome with a fixed debugging port, no CDP client yet. Returns
    (proc, port). A fixed port so we can open the WS ourselves; the feature
    it force-enables (AutomationControlled) is irrelevant to Error timing."""
    port = free_port()
    profile = tempfile.mkdtemp(prefix="camou-attach-")
    proc = subprocess.Popen(
        [lib_shell.CHROME, "--no-sandbox", *flags,
         f"--user-data-dir={profile}", f"--remote-debugging-port={port}",
         # Chrome 141+ rejects a WebSocket whose Origin it did not expect
         # (403 "Rejected an incoming WebSocket connection"). Playwright sets
         # no Origin so never trips it; websocket-client does. Allowing the
         # loopback origin is a client-attach concern, not a timing one -- it
         # changes nothing the page measures.
         "--remote-allow-origins=*",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/version", timeout=1).read()
            return proc, port
        except Exception:
            time.sleep(0.1)
    proc.terminate()
    raise RuntimeError("chrome opened no endpoint")


def page_ws_url(port):
    targets = json.loads(urllib.request.urlopen(
        f"http://127.0.0.1:{port}/json", timeout=5).read())
    for t in targets:
        if t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    raise RuntimeError("no page target")


class CDP:
    """The smallest CDP client that can navigate: send/recv by id, wait for
    the matching reply. No domain is enabled unless this code enables it."""

    def __init__(self, url):
        # suppress_origin: some chrome builds match the allowlist against an
        # ABSENT origin more permissively than a loopback one. Both --remote-
        # allow-origins=* and this are set so neither chrome version rejects.
        self.ws = websocket.create_connection(
            url, timeout=15, suppress_origin=True)
        self._id = 0

    def call(self, method, params=None):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps(
            {"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result")
            # events (Page.*, etc.) are ignored; we only block on the reply

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def wait_for(got, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if got:
            return got[0]
        time.sleep(0.1)
    return None


def state_d(flags, enable_runtime):
    """Raw CDP attach. Page domain to navigate; Runtime only if asked."""
    url, got, srv = serve()
    proc = None
    cdp = None
    try:
        proc, port = launch_with_port(flags)
        cdp = CDP(page_ws_url(port))
        cdp.call("Page.enable")
        if enable_runtime:
            cdp.call("Runtime.enable")
        cdp.call("Page.navigate", {"url": url})
        result = wait_for(got)
        if result is not None:
            result["runtime_enabled"] = enable_runtime
        return result
    finally:
        if cdp is not None:
            cdp.close()
        if proc is not None:
            proc.terminate()
            proc.wait(timeout=15)
        srv.shutdown()


def summarise(label, r):
    if r is None:
        return {"state": label, "error": "no result reported within 45s"}
    t = r["times_ms"]
    return {
        "state": label,
        "median_ms": round(statistics.median(t), 3),
        "min_ms": round(min(t), 3),
        "max_ms": round(max(t), 3),
        "ns_per_error": round(statistics.median(t) * 1e6 / ERRORS_PER_TRIAL, 1),
        "times_ms": [round(x, 3) for x in t],
        "stack_trace_limit": r["stack_trace_limit"],
        "prepare_stack_trace": r["has_prepare"],
    }


FLAGS = list(lib_shell.CHROME_FLAGS)
out = {
    "measurement": "sp2b-3-attach-vs-runtime",
    "binary": "chrome",
    "trials": TRIALS,
    "errors_per_trial": ERRORS_PER_TRIAL,
    "note": ("D = raw CDP attach, Page only, NO Runtime. "
             "E = same plus Runtime.enable. Compare both to measurement 2's "
             "A (24.6-25.8ms) and B (24.3-25.1ms). No Playwright: the agent "
             "that confounded measurement 2 is absent from both states here."),
    "states": [
        summarise("D raw CDP, Page only, no Runtime",
                  state_d(FLAGS, enable_runtime=False)),
        summarise("E raw CDP, Page + Runtime.enable",
                  state_d(FLAGS, enable_runtime=True)),
    ],
}
print(json.dumps(out, indent=2))
sys.exit(1 if any("error" in s for s in out["states"]) else 0)

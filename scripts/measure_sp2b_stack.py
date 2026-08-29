"""SP2b measurement 2: does Error/.stack construction cost betray an inspector?

SP2 verification item 6, and the second half of open decision D1. The claim in
the literature is that V8 captures richer stack information when an inspector
is attached, so timing many Error constructions separates a driven browser
from a real one. The spec asks for the raw numbers, not a verdict: "Expected:
distributions overlap. Record the raw numbers -- 'no difference' is not a
result without them."

THREE states, not two, because "an inspector is attached" is two different
things and conflating them would misattribute whatever difference appears:

  A  no --remote-debugging-port at all. No inspector infrastructure exists.
  B  the port is open, nothing connected. Infrastructure present, no client.
  C  the port is open and Playwright is connected, which enables the Runtime
     domain. This is how Camoucrome is actually driven today.

A vs B isolates the cost of the port existing. B vs C isolates the cost of a
client attaching. A two-state test would report their sum and let either be
blamed.

The page measures itself and reports over HTTP rather than through CDP. That
is what makes state A measurable at all: reading the result over CDP would
require attaching, which is the variable under test.
"""

import http.server
import json
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse

import lib_shell

TRIALS = 7
ERRORS_PER_TRIAL = 10000

PAGE = """<!doctype html><title>stack</title><script>
(async () => {
  const TRIALS = %d, N = %d;
  const times = [];
  for (let t = 0; t < TRIALS; t++) {
    const t0 = performance.now();
    let sink = 0;
    for (let i = 0; i < N; i++) {
      const e = new Error('probe');
      // Read .stack: construction alone may be lazy, and the documented
      // discriminator is the CAPTURE, which reading forces.
      sink += e.stack.length;
    }
    const t1 = performance.now();
    times.push(t1 - t0);
    if (sink < 0) console.log(sink);  // keep the optimiser honest
  }
  const payload = encodeURIComponent(JSON.stringify({
    times_ms: times,
    stack_trace_limit: Error.stackTraceLimit,
    has_prepare: typeof Error.prepareStackTrace,
  }));
  await fetch('/result?d=' + payload);
})();
</script>"""


def serve():
    """Serves the probe page and captures the one result it posts back."""
    got = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/result":
                q = urllib.parse.parse_qs(parsed.query)
                got.append(json.loads(q["d"][0]))
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


def wait_for(got, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if got:
            return got[0]
        time.sleep(0.1)
    return None


def state_a(binary, flags):
    """No debugging port. Nothing can attach; the page reports over HTTP."""
    url, got, srv = serve()
    profile = tempfile.mkdtemp(prefix="camou-stack-")
    proc = subprocess.Popen(
        [binary, "--no-sandbox", *flags, f"--user-data-dir={profile}", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        return wait_for(got)
    finally:
        proc.terminate()
        proc.wait(timeout=15)
        srv.shutdown()


def state_b(binary, flags):
    """Port open and page loaded, still no CDP client.

    --remote-debugging-port=0 opens the endpoint; nothing connects to it.
    That is the whole point of this state: the infrastructure exists and no
    CDP session is ever created.
    """
    url, got, srv = serve()
    profile = tempfile.mkdtemp(prefix="camou-stack-")
    proc = subprocess.Popen(
        [binary, "--no-sandbox", *flags, f"--user-data-dir={profile}",
         "--remote-debugging-port=0", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        return wait_for(got)
    finally:
        proc.terminate()
        proc.wait(timeout=15)
        srv.shutdown()


def state_c(binary, flags):
    """Port open and Playwright attached, which enables Runtime."""
    url, got, srv = serve()
    proc = None
    try:
        proc = lib_shell.launch(None, shell=binary, extra_flags=flags)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(
                f"http://127.0.0.1:{proc.cdp_port}")
            ctx = browser.contexts[0]
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            received = []
            page.on("console", lambda m: received.append(m.type))
            page.goto(url, wait_until="load")
            result = wait_for(got)
            if result is not None:
                result["console_channel_live"] = True
            return result
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)
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


BIN = lib_shell.CHROME
FLAGS = [f for f in lib_shell.CHROME_FLAGS]

out = {
    "measurement": "sp2b-2-stack-timing",
    "binary": "chrome",
    "trials": TRIALS,
    "errors_per_trial": ERRORS_PER_TRIAL,
    "states": [
        summarise("A no debugging port", state_a(BIN, FLAGS)),
        summarise("B port open, no client", state_b(BIN, FLAGS)),
        summarise("C port open, Playwright attached", state_c(BIN, FLAGS)),
    ],
}
print(json.dumps(out, indent=2))
sys.exit(1 if any("error" in s for s in out["states"]) else 0)

"""Off-state cost of the observer's renderer hooks, measured on the Windows host.

Arm A is a build without the observer, arm B one with `camou_observe = true` and the
category off. Both load verify_observe.TIMING from a loopback server, alternating
A, B, A, B; each run is a fresh browser with a fresh profile.

Pass rule, per metric: PASS iff abs(median(B) - median(A)) <= max(A) - min(A), that is
the shift is inside arm A's own run-to-run spread. At least 5 runs per arm and the same
metric names in both arms, else ValueError.

A run with a nonzero GPU crash count, or no result inside --run-timeout, is UNMEASURED:
it is repeated once, a second failure makes the whole measurement UNMEASURED.
Run it through scripts/windows/run-interactive.ps1 (session 1).

Exit: 0 PASS, 1 FAIL, 3 UNMEASURED.
"""
import argparse
import http.server
import json
import os
import re
import shlex
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time

MIN_RUNS = 5

# The send hooks' loop: fetch string, fetch Blob (the data-pipe reader path), WebSocket.
# __WSP__ is the lib_ws_server port. The page posts its result to /done, the loops to /sink.
POST_PAGE = """<!doctype html><script>
(async () => {
  const kib = 'x'.repeat(1024), blob = new Blob(['x'.repeat(65536)]);
  const t0 = performance.now();
  for (let i = 0; i < 500; i++) await fetch('/sink', {method: 'POST', body: kib});
  const t1 = performance.now();
  for (let i = 0; i < 200; i++) await fetch('/sink', {method: 'POST', body: blob});
  const t2 = performance.now();
  const ws = new WebSocket('ws://127.0.0.1:__WSP__/');
  await new Promise(r => ws.onopen = r);
  const ok = new Promise(r => ws.onmessage = r);
  const t3 = performance.now();
  for (let i = 0; i < 2000; i++) ws.send(kib);
  ws.send('done');
  await ok;
  const t4 = performance.now();
  await fetch('/done', {method: 'POST', body: JSON.stringify({post_500_ms: t1 - t0,
    post_blob_200_ms: t2 - t1, ws_2000_ms: t4 - t3})});
})();
</script>"""


def verdict(a_runs, b_runs):
    if set(a_runs) != set(b_runs):
        raise ValueError(f"metric sets differ: {sorted(a_runs)} vs {sorted(b_runs)}")
    out = {}
    for name in a_runs:
        a, b = a_runs[name], b_runs[name]
        if len(a) < MIN_RUNS or len(b) < MIN_RUNS:
            raise ValueError(f"{name}: need at least {MIN_RUNS} runs per arm, got {len(a)} and {len(b)}")
        shift = statistics.median(b) - statistics.median(a)
        rng = max(a) - min(a)
        out[name] = ("PASS" if abs(shift) <= rng else "FAIL", shift, rng)
    return out


def session_state(quser_text):
    """The STATE column of every `quser` row, nothing else (no user or session name)."""
    states = []
    for line in quser_text.splitlines()[1:]:
        m = re.search(r"\s(Active|Disc)\s", line + " ")
        if m:
            states.append(m.group(1))
    return ",".join(sorted(states)) or "none"


def read_session_state():
    p = subprocess.run(["quser"], capture_output=True, text=True)
    return session_state(p.stdout)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def remove_tree(path):
    for _ in range(20):  # Windows releases the profile a moment after the browser exits
        try:
            shutil.rmtree(path)
            return
        except OSError:
            time.sleep(0.5)
    shutil.rmtree(path, ignore_errors=True)


def kill_tree(proc):
    if os.name == "nt":  # only the tree this script started
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.kill()
    try:
        proc.wait(30)
    except subprocess.TimeoutExpired:
        pass


def one_run(exe, extra, page, gpu_gate, run_timeout):
    """(metrics dict, None) or (None, reason) when the run is UNMEASURED."""
    done, result = threading.Event(), {}
    ws = None
    if "__WSP__" in page:
        import lib_ws_server
        ws, ws_port, _ = lib_ws_server.start()
        page = page.replace("__WSP__", str(ws_port))

    class H(http.server.BaseHTTPRequestHandler):
        def _send(self, body, ctype):
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._send(page if self.path == "/timing.html" else "", "text/html")

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            if self.path == "/sink":
                self.rfile.read(n)
                self._send("", "text/plain")
                return
            result.update(json.loads(self.rfile.read(n) or b"{}"))
            self._send("", "text/plain")
            done.set()

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    tmp = tempfile.mkdtemp(prefix="camoucrome-cost-")
    proc = None
    try:
        cdp = free_port()
        # --user-data-dir first: Windows Chrome takes the first one
        argv = [exe, f"--user-data-dir={tmp}", "--no-first-run", "--no-default-browser-check",
                f"--remote-debugging-port={cdp}", *extra,
                f"http://127.0.0.1:{server.server_port}/timing.html"]
        env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}
        proc = subprocess.Popen(argv, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not done.wait(run_timeout):
            return None, f"no result within {run_timeout} s"
        crashes = gpu_gate.read_port(cdp)
        if crashes != 0:
            return None, f"GPU crash count {crashes}"
        return dict(result), None
    finally:
        if proc:
            kill_tree(proc)
        server.shutdown()
        server.server_close()
        if ws:
            ws.shutdown()
            ws.server_close()
        remove_tree(tmp)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--a", required=True, help="chrome.exe of arm A (no observer)")
    ap.add_argument("--b", required=True, help="chrome.exe of arm B (observer built, category off)")
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--b-extra", default="", help="extra browser arguments for arm B (the RED run). Pass it as --b-extra='--x ...' when the value starts with --, and use forward slashes in paths: shlex.split drops backslashes")
    ap.add_argument("--loops", choices=["timing", "post"], default="timing")
    ap.add_argument("--run-timeout", type=int, default=120)
    args = ap.parse_args(argv)

    import gpu_gate
    import verify_observe
    gpu_gate.require_interactive()
    page = verify_observe.TIMING if args.loops == "timing" else POST_PAGE
    b_extra = shlex.split(args.b_extra)
    runs = {"A": {}, "B": {}}
    state0 = None
    try:
        for i in range(args.runs):
            for arm, exe, extra in (("A", args.a, []), ("B", args.b, b_extra)):
                state = read_session_state()
                state0 = state0 or state
                if state != state0:
                    print("UNMEASURED session state changed", flush=True)
                    return 3
                for attempt in (1, 2):
                    res, why = one_run(exe, extra, page, gpu_gate, args.run_timeout)
                    if res is not None:
                        break
                    print(f"run {i} {arm} UNMEASURED attempt {attempt}: {why}", flush=True)
                else:
                    print("RESULT UNMEASURED", flush=True)
                    return 3
                print(f"run {i} {arm} " + " ".join(f"{k}={v:.2f}" for k, v in res.items()), flush=True)
                for k, v in res.items():
                    runs[arm].setdefault(k, []).append(v)
    except KeyboardInterrupt:
        print("RESULT UNMEASURED interrupted", flush=True)
        return 3
    print(f"session state {state0}", flush=True)
    v = verdict(runs["A"], runs["B"])
    for name, (res, shift, rng) in v.items():
        print(f"{name} {res} shift={shift:.2f} a_range={rng:.2f}")
    ok = all(r == "PASS" for r, _, _ in v.values())
    print("RESULT PASS" if ok else "RESULT FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

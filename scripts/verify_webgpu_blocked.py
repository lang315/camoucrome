#!/usr/bin/env python3
"""webgpu-blocked on the Windows host: `webGpu:blocked` makes navigator.gpu.requestAdapter() resolve null.

The box has no GPU (every adapter is null there), so a box-only run measures nothing. One host run, through
run-interactive.ps1 in session 1, launches three arms from a loopback page (a secure context):

  stock  the frozen stock chrome (CAMOU_STOCK_APP), a seeded profile
  F0     the fork, no config
  FB     the fork under a generated Windows identity with webGpu:blocked = true

  1  F0: requestAdapter() is non-null in the window and in a dedicated worker (the RED control: it proves the
     check can see an adapter; a null here is UNMEASURED, never a PASS for row 2)
  2  FB: null in both, and the promise resolves (no rejection)
  3  FB's minimum of 30 requests is >= 0.8 x F0's minimum (the null comes through the real round trip)
  4  FB: UNMASKED_RENDERER_WEBGL equals the claim in the window and in a worker OffscreenCanvas
  5  FB: Object.getOwnPropertyNames(GPU.prototype) and requestAdapter.toString() equal stock's
  6  WebNN (record only): navigator.ml and createContext({deviceType: "gpu"}) in stock, F0 and FB
  7  FB: the console warning text (record only; read from the browser's log file)

Every row is PASS, FAIL or UNMEASURED. A GPU process crash count above 0 (gpu_gate), a missing report, or a null
adapter in F0 is UNMEASURED (exit 3). --selftest feeds canned readings through rows() and needs no browser.
Windows only."""
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

PAGE_TIMEOUT_S = 120
IDENTITY_SEED = 1000
REQUESTS = 30
LATENCY_FLOOR = 0.8
CONSOLE_TEXT = "Failed to create WebGPU Context Provider"

PAGE = """<!doctype html><meta charset=utf-8><title>webgpu-blocked</title><body><script>
const N = %d;
const probe = `
async function adapterProbe(g) {
  const t = []; let res, rej = null;
  for (let i = 0; i < %d; i++) {
    const t0 = performance.now();
    try { res = await g.requestAdapter(); } catch (e) { rej = String(e); }
    t.push(performance.now() - t0);
  }
  return { isNull: res === null, rej, min: Math.min(...t) };
}
function renderer(c) {
  const gl = c.getContext('webgl');
  if (!gl) return null;
  const e = gl.getExtension('WEBGL_debug_renderer_info');
  return e ? gl.getParameter(e.UNMASKED_RENDERER_WEBGL) : null;
}`;
(0, eval)(probe);
async function ml() {
  const o = { exists: typeof navigator.ml !== 'undefined', ctx: null };
  if (o.exists) {
    try { await navigator.ml.createContext({ deviceType: 'gpu' }); o.ctx = 'resolved'; }
    catch (e) { o.ctx = 'rejected ' + e.name; }
  }
  return o;
}
(async () => {
  const r = { errors: [] };
  try {
    r.protoNames = Object.getOwnPropertyNames(GPU.prototype);
    r.reqToString = GPU.prototype.requestAdapter.toString();
    r.win = await adapterProbe(navigator.gpu);
    r.winRenderer = renderer(document.createElement('canvas'));
    const src = probe + `self.onmessage = async () => {
      self.postMessage({ w: await adapterProbe(navigator.gpu), renderer: renderer(new OffscreenCanvas(8, 8)) }); };`;
    const w = new Worker(URL.createObjectURL(new Blob([src], { type: 'text/javascript' })));
    const got = await new Promise((ok, no) => { w.onmessage = e => ok(e.data); w.onerror = e => no(new Error(e.message));
                                                 w.postMessage(0); setTimeout(() => no(new Error('worker timeout')), 60000); });
    r.worker = got.w; r.workerRenderer = got.renderer;
    r.ml = await ml();
  } catch (e) { r.errors.push(String(e)); }
  await fetch('/result', { method: 'POST', body: JSON.stringify(r) });
})();
</script></body>""" % (REQUESTS, REQUESTS)


def adapter_ok(reading):
    return bool(reading) and not reading.get("errors") and reading.get("win") and reading.get("worker")


def rows(readings, claim, logs=None):
    """[(row name, verdict, why)]: verdict True/False, or None (UNMEASURED) with the reason. `readings` maps arm -> the page's
    report (None when it never reported) plus a "crash" count from gpu_gate; `claim` is FB's webGl:renderer."""
    out = []
    unm = {}
    for arm in ("stock", "F0", "FB"):
        r = readings.get(arm)
        if r is None or r.get("errors"):
            unm[arm] = f"{arm}: no reading (no report, or a page error)"
        elif r.get("crash") != 0:
            unm[arm] = f"{arm}: gpu-crash={r.get('crash')} (a non-zero or unreadable count measured nothing GPU-backed)"
    f0 = readings.get("F0")
    r1 = "1 F0 (no key): requestAdapter() non-null in the window and in a dedicated worker"
    if "F0" in unm:
        out.append((r1, None, unm["F0"]))
    else:
        both = not f0["win"]["isNull"] and not f0["worker"]["isNull"]
        out.append((r1, True if both else None, None if both else "F0 adapter is null: this host cannot show an adapter"))
    red_control = out[0][1] is True
    fb = readings.get("FB")
    r2 = "2 FB (webGpu:blocked): null in the window and the worker, both resolve (no rejection)"
    if "FB" in unm or not red_control:
        why = unm.get("FB") or "row 1 is not PASS, so a null here proves nothing"
        out += [(r2, None, why)]
    else:
        out.append((r2, fb["win"]["isNull"] and fb["worker"]["isNull"] and not fb["win"]["rej"] and not fb["worker"]["rej"], None))
    r3 = f"3 FB latency: min of {REQUESTS} requests >= {LATENCY_FLOOR} x F0's min (window)"
    if "FB" in unm or "F0" in unm or not red_control:
        out.append((r3, None, unm.get("FB") or unm.get("F0") or "row 1 is not PASS"))
    else:
        out.append((r3, fb["win"]["min"] >= LATENCY_FLOOR * f0["win"]["min"], None))
    r4 = "4 FB: UNMASKED_RENDERER_WEBGL equals the claim in the window and in a worker OffscreenCanvas"
    if "FB" in unm:
        out.append((r4, None, unm["FB"]))
    elif not fb.get("winRenderer") or not fb.get("workerRenderer"):
        out.append((r4, None, "no WEBGL_debug_renderer_info reading (WebGL unavailable)"))
    else:
        out.append((r4, fb["winRenderer"] == claim == fb["workerRenderer"], None))
    r5 = "5 FB: GPU.prototype own names and requestAdapter.toString() equal stock's"
    if "FB" in unm or "stock" in unm:
        out.append((r5, None, unm.get("FB") or unm.get("stock")))
    else:
        out.append((r5, fb["protoNames"] == readings["stock"]["protoNames"]
                    and fb["reqToString"] == readings["stock"]["reqToString"], None))
    return out


def notes(readings, logs):
    lines = []
    for arm in ("stock", "F0", "FB"):
        r = readings.get(arm) or {}
        lines.append(f"6 WebNN {arm}: {json.dumps(r.get('ml'), sort_keys=True)}")
    lines.append(f"7 console text with the key: {'present' if CONSOLE_TEXT in (logs or {}).get('FB', '') else 'absent'} "
                 f"({CONSOLE_TEXT!r})")
    lines.append(f"  latency min ms: " + ", ".join(
        f"{a}={((readings.get(a) or {}).get('win') or {}).get('min')}" for a in ("stock", "F0", "FB")))
    return lines


def selftest():
    """The RED the brief names: a null adapter in F0 makes row 1 UNMEASURED, and rows 2 and 3 with it."""
    def arm(null, mn, ren="R", crash=0):
        side = {"isNull": null, "rej": None, "min": mn}
        return {"win": side, "worker": dict(side), "winRenderer": ren, "workerRenderer": ren,
                "protoNames": ["a", "b"], "reqToString": "function requestAdapter() { [native code] }",
                "ml": {"exists": False}, "errors": [], "crash": crash}
    good = {"stock": arm(False, 10), "F0": arm(False, 10), "FB": arm(True, 9)}
    v = {n: ok for n, ok, _ in rows(good, "R")}
    assert list(v.values()) == [True] * 5, v
    nullf0 = dict(good, F0=arm(True, 10))
    assert [ok for _, ok, _ in rows(nullf0, "R")][:3] == [None, None, None], "a null F0 adapter must be UNMEASURED"
    assert rows(dict(good, FB=arm(True, 9, crash=1)), "R")[1][1] is None, "a GPU crash must be UNMEASURED"
    assert rows(dict(good, FB=arm(False, 9)), "R")[1][1] is False, "a non-null adapter under the key must FAIL"
    assert rows(dict(good, FB=arm(True, 1)), "R")[2][1] is False, "a too-fast null must FAIL the latency row"
    assert rows(good, "other")[3][1] is False, "a renderer that is not the claim must FAIL"
    assert rows(dict(good, FB={**arm(True, 9), "protoNames": ["a"]}), "R")[4][1] is False
    assert rows(dict(good, stock=None), "R")[4][1] is None
    print("selftest: PASS")
    return 0


class _Server(http.server.ThreadingHTTPServer):
    results = None


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.server.results.append(json.loads(self.rfile.read(n) or b"{}"))
        self.send_response(204)
        self.end_headers()


def free_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main(argv):
    if "--selftest" in argv[1:]:
        return selftest()
    import gpu_gate
    import lib_shell
    import measure_step2 as m2
    from camoucrome import launcher
    from measure_timing_parity import _kill_tree

    gpu_gate.require_interactive()
    stock_exe = os.path.join(os.environ.get("CAMOU_STOCK_APP") or m2.STOCK_APP, "chrome.exe")
    fork_exe = lib_shell.CHROME
    for exe in (stock_exe, fork_exe):
        if not os.path.isfile(exe):
            print(f"UNMEASURED: no browser at {exe}")
            return 3
    server = _Server(("127.0.0.1", 0), _Handler)
    server.results = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    ident = m2.identity(IDENTITY_SEED)
    cfg = dict(ident["config"], **{"webGpu:blocked": True})
    claim = cfg.get("webGl:renderer")
    logs = {}

    def launch(arm):
        server.results = []
        port = free_port()
        logfile = tempfile.mktemp(prefix="wgb-log-")
        dbg = [f"--remote-debugging-port={port}", "--enable-logging", f"--log-file={logfile}"]
        if arm == "stock":
            udd = m2.SEED.fresh_copy()
            argv_ = [stock_exe, *launcher.BASE_ARGS, f"--user-data-dir={udd}", *dbg]
            env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}
        elif arm == "F0":
            udd = tempfile.mkdtemp(prefix="wgb-")
            argv_ = [fork_exe, *launcher.BASE_ARGS, f"--user-data-dir={udd}", *dbg]
            env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}
        else:
            udd = tempfile.mkdtemp(prefix="wgb-")
            lo = ident["launch"]
            args = launcher.build_args(tuple(lo["window"]) if lo.get("window") else None, lo.get("dpr"),
                                       lo.get("args", []), False, udd, launcher.accept_lang_of(cfg),
                                       position=tuple(lo["position"]) if lo.get("position") else None)
            argv_ = [fork_exe] + [x for x in args if x != "--remote-debugging-pipe"] + dbg
            env = launcher.build_env(cfg, fontconfig=launcher.fontconfig_for(cfg, None, None, fork_exe))
        proc = subprocess.Popen(argv_ + [url], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + PAGE_TIMEOUT_S
            while not server.results and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.5)
            if not server.results:
                return None
            reading = server.results[0]
            reading["crash"] = gpu_gate.read_port(port)  # after the page reported: the attach cannot touch the reading
            return reading
        finally:
            _kill_tree(proc.pid)
            time.sleep(1.0)
            try:
                logs[arm] = open(logfile, encoding="utf-8", errors="replace").read()
            except OSError:
                logs[arm] = ""
            if arm == "stock":
                m2.SEED.drop(udd)
            else:
                launcher.remove_dir(udd)

    readings = {}
    with m2.seeded_control(stock_exe):
        for arm in ("stock", "F0", "FB"):
            readings[arm] = launch(arm)
            print(f"      {arm}: {json.dumps({k: v for k, v in (readings[arm] or {}).items() if k != 'protoNames'}, sort_keys=True)}",
                  flush=True)
    verdicts = rows(readings, claim)
    for line in notes(readings, logs):
        print("      " + line)
    unm = False
    for name, ok, why in verdicts:
        if ok is None:
            unm = True
            print(f"UNMEASURED  {name}: {why}")
        else:
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if any(ok is False for _, ok, _ in verdicts):
        return 1
    return 3 if unm else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

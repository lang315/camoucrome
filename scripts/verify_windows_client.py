"""Windows: the Python client's own launch, sandboxed, carrying a chunked identity.

Every probe-based verification passes --no-sandbox (camoucrome.probe adds it),
so on Windows none of them exercises what a user's camoucrome.launch() does: a
sandboxed renderer, whose environment CreateFilteredEnvironment() strips to seven
variables unless the windows-sandbox-env patch lets CAMOU_* through. And a
generated identity does not fit one environment string: a Windows one is ~37 KB,
past CONFIG_CHUNK_CHARS, so it travels as CAMOU_CONFIG_1..N and the renderer
must find every chunk. verify_windows_sandbox_env.py measured the sandbox with a
one-key config that never chunks; this is the shape users actually send.

K1 the generated Windows identity goes out as CAMOU_CONFIG_1..N, N >= 2, and no
   CAMOU_CONFIG -- without this every other row could pass on an unchunked config
K2 launched through camoucrome.launch() with no --no-sandbox (read back from the
   browser's own command line) under strict
K3 navigator.hardwareConcurrency in the page is the configured 3. The key is
   the identity's LAST, so it sits in the last chunk; under strict a lost or
   reordered chunk is unparseable JSON and the renderer cannot report it
K4 a dedicated worker reports the same 3 (conventions rule 3)
K5 control: the same sandboxed launch without config reports the machine's
   own value, not 3, so K3 cannot pass on a value from anywhere but the config
G2-G4, N2-N4 K2-K4 again through the Go and the Node client: their probes run
   with --sandbox --strict --config @file (the identity is past Windows'
   32767-char command line) against a page that writes both values into #o

Run on the Windows host under the client's venv, from the scripts directory:
  $env:CAMOU_OUT='D:\\camou-win\\chromium\\src\\out\\Release'
  $env:CAMOU_CLIENT='D:\\camou-win\\tree'
  $env:CAMOU_GO_PROBE, $env:CAMOU_DRIVER, $env:PLAYWRIGHT_NODEJS_PATH as for
  verify_sp6b_driver.py (the Go probe built from client/go/cmd/camoucrome-probe)
  D:\\camou-win\\client-venv\\Scripts\\python.exe verify_windows_client.py
"""
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading

from lib_shell import CHROME as EXE, layout

HOME, PY, NODE, CLIENT, FONTS_DIR = layout()
sys.path.insert(0, str(CLIENT / "client" / "python"))
from camoucrome import gen, launch, launcher  # noqa: E402
from camoucrome.probe import browser_argv  # noqa: E402
from patchright.sync_api import sync_playwright  # noqa: E402

SPOOFED = 3
EXPECTED = 11
PAGE = b"<!doctype html><title>client</title>"
# The Go and Node probes read #o once the page loads; it appears only when the
# worker has answered, and the probe's locator waits for it.
REPORT = b"""<!doctype html><title>client</title><script>
const w = new Worker(URL.createObjectURL(new Blob(
  ['self.postMessage(navigator.hardwareConcurrency)'], {type: 'text/javascript'})));
w.onmessage = e => {
  const o = document.createElement('pre');
  o.id = 'o';
  o.textContent = JSON.stringify({main: navigator.hardwareConcurrency, worker: e.data});
  document.body.appendChild(o);
};
</script><body></body>"""
# The same names and defaults as verify_sp6b_driver.py.
GO_PROBE = os.environ.get("CAMOU_GO_PROBE", f"{HOME}/camoucrome-go/camoucrome-probe")
DRIVER_PATCHRIGHT = os.environ.get("CAMOU_DRIVER", f"{HOME}/camoucrome-driver")
NODE = os.environ.get("PLAYWRIGHT_NODEJS_PATH", f"{DRIVER_PATCHRIGHT}/node")
NODE_PROBE = os.environ.get("CAMOU_NODE_PROBE", str(CLIENT / "client" / "node" / "probe.js"))
PROBES = {
    "G": [GO_PROBE, "--driver-dir", DRIVER_PATCHRIGHT, "--label", "go"],
    "N": [NODE, NODE_PROBE, "--driver", os.path.join(DRIVER_PATCHRIGHT, "package"), "--label", "node"],
}
# Copied from verify_windows_sandbox_env.py, which copied verify_sp0.py:9-16.
WORKER_HC = """
() => new Promise(resolve => {
  const src = 'self.postMessage(navigator.hardwareConcurrency)';
  const url = URL.createObjectURL(new Blob([src], {type: 'text/javascript'}));
  const w = new Worker(url);
  w.onmessage = e => resolve(e.data);
})
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = REPORT if self.path == "/report" else PAGE
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def read(pw, url, config):
    """(argv, main value, worker value, error) from one sandboxed client launch."""
    try:
        ctx = launch(pw, EXE, config=config, strict=config is not None)
    except Exception as e:
        return [], None, None, f"{type(e).__name__}: {str(e).splitlines()[0]}"
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, wait_until="load")
        argv = browser_argv(EXE)
        return argv, page.evaluate("navigator.hardwareConcurrency"), page.evaluate(WORKER_HC), None
    except Exception as e:
        return browser_argv(EXE), None, None, f"{type(e).__name__}: {str(e).splitlines()[0]}"
    finally:
        ctx.close()


def read_probe(cmd, url, config_file):
    """(argv, main value, worker value, error) from one sandboxed Go or Node launch."""
    done = None
    try:
        done = subprocess.run(cmd + ["--executable", EXE, "--url", url + "report", "--config",
                                     "@" + config_file, "--strict", "--sandbox"],
                              capture_output=True, text=True, timeout=180,
                              env=dict(os.environ, PLAYWRIGHT_NODEJS_PATH=NODE))
        out = json.loads(done.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as e:
        tail = done.stderr.strip().splitlines()[-1:] if done else []
        return [], None, None, f"{type(e).__name__}: {str(e).splitlines()[0]} {tail}"
    return out["argv"] or [], out["report"]["main"], out["report"]["worker"], None


def main():
    config = gen.generate(os="windows", seed=1)
    config.pop("navigator.hardwareConcurrency", None)
    config["navigator.hardwareConcurrency"] = SPOOFED  # last key, last chunk
    env = launcher.build_env(config)
    chunks = sorted(k for k in env if k.startswith("CAMOU_CONFIG_") and k[13:].isdigit())

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"
    with sync_playwright() as pw:
        argv, main_hc, worker_hc, err = read(pw, url, config)
        _, real, _, err_real = read(pw, url, None)
    fd, config_file = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(config, f)
        probed = {k: read_probe(cmd, url, config_file) for k, cmd in PROBES.items()}
    finally:
        os.remove(config_file)
    srv.shutdown()

    results, notes = {}, []
    results["K1"] = len(chunks) >= 2 and "CAMOU_CONFIG" not in env
    notes.append(f"K1: {len(json.dumps(config))} chars -> {len(chunks)} chunks, "
                 f"CAMOU_CONFIG present={'CAMOU_CONFIG' in env}")
    results["K2"] = bool(argv) and "--no-sandbox" not in argv
    notes.append(f"K2: argc={len(argv)} --no-sandbox={'--no-sandbox' in argv}{'; ' + err if err else ''}")
    results["K3"] = main_hc == SPOOFED
    notes.append(f"K3: main -> {main_hc!r} (expect {SPOOFED})")
    results["K4"] = worker_hc == SPOOFED
    notes.append(f"K4: worker -> {worker_hc!r} (expect {SPOOFED})")
    results["K5"] = real is not None and real != SPOOFED
    notes.append(f"K5: no config -> {real!r} (expect anything but {SPOOFED})"
                 f"{'; ' + err_real if err_real else ''}")

    for k, (p_argv, p_main, p_worker, p_err) in probed.items():
        results[f"{k}2"] = bool(p_argv) and "--no-sandbox" not in p_argv
        notes.append(f"{k}2: argc={len(p_argv)} --no-sandbox={'--no-sandbox' in p_argv}"
                     f"{'; ' + p_err if p_err else ''}")
        results[f"{k}3"] = p_main == SPOOFED
        notes.append(f"{k}3: main -> {p_main!r} (expect {SPOOFED})")
        results[f"{k}4"] = p_worker == SPOOFED
        notes.append(f"{k}4: worker -> {p_worker!r} (expect {SPOOFED})")

    for n in notes:
        print("note:", n)
    if len(results) != EXPECTED:
        sys.exit(f"expected {EXPECTED} rows, built {len(results)}")
    for k, ok in results.items():
        print(f"{k}: {'PASS' if ok else 'FAIL'}")
    print(f"{sum(results.values())} PASS {EXPECTED - sum(results.values())} FAIL")
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()

"""SP6b driver contract (A4 #1): the CDP driver never sends Runtime.enable,
leaves no trace in the main world, adds no forbidden flag, and does not move
the stack-timing signal SP2 D1 measured. One verify, one probe page, several
drivers -- the stock ones are the RED rows and must fail, the patchright ones
must pass. Run on the box under ~/camoucrome-verify/venv.

The page's own script (main world, synchronous, so a --dump-dom run captures
it too) writes the report into #o; each probe command reads that text through
the DOM, which every world shares. Nothing is read through evaluate(),
because patchright evaluates in an isolated world and playwright-go cannot
choose a world per call -- measured 2026-09-10: a global set via evaluate was
invisible to a main-world script.

Per driver:
  C1 protocol log (DEBUG=pw:protocol on the driver) has 0 Runtime.enable and
     at least MIN_METHODS sends (a silenced logger cannot pass vacuously)
  C2 Object.keys(window) equals the no-driver baseline (--dump-dom, no CDP
     client at all), so no binding or init-script global is visible
  C3 navigator.webdriver is false, as in the baseline
  C4 browser argv EQUALS launcher.json's expected set (plus the profile dir
     and the probe's --no-sandbox): the launcher ignores Playwright's default
     args, and absence of the forbidden flags alone would let a new default
     (a --disable-features list moves feature state) slip in
  C5 median of 7x10000 `new Error().stack` within TIMING_TOLERANCE of the
     baseline (median of BASELINE_RUNS launches; D1: Runtime.enable costs +21%)
  C6 the probe registers add_init_script("window.__camou_init = 1") before
     navigating. Measured: BOTH drivers run it in the main world (that is
     what a caller asks for -- never add_init_script anything a page could
     enumerate; patchright's evaluate is the isolated-world path). The
     contract is that nothing of the driver's OWN appears:
     Object.getOwnPropertyNames(window).length == baseline + exactly 1 (own
     names catch a non-enumerable binding that keys() misses). SP2 4.2's
     "isolated world not observable from the main world", as far as a
     driver's own machinery is concerned.
Verdict: every patchright row passes C1-C6; every stock row fails C1 (RED).
C2 and C6 pass on the stock rows too: the browser-level SP2 closures hold
against stock Playwright, which is SP6's threat model; C1 and C5 are what
only the driver closes.
"""
import html
import http.server
import json
import os
import pathlib
import statistics
import subprocess
import sys
import tempfile
import threading

HOME = os.path.expanduser("~")
EXE = os.environ.get("CAMOU_EXE", f"{HOME}/chromium/src/out/Default/chrome")
VENV = os.environ.get("CAMOU_VENV", f"{HOME}/camoucrome-verify/venv")
VENV_STOCK = os.environ.get("CAMOU_VENV_STOCK", f"{HOME}/camoucrome-verify/venv-stock")
GO_PROBE = os.environ.get("CAMOU_GO_PROBE", f"{HOME}/camoucrome-go/camoucrome-probe")
DRIVER_PATCHRIGHT = os.environ.get("CAMOU_DRIVER", f"{HOME}/camoucrome-driver")
DRIVER_STOCK = os.environ.get("CAMOU_DRIVER_STOCK", f"{HOME}/camoucrome-driver-stock")
NODE = os.environ.get("PLAYWRIGHT_NODEJS_PATH", f"{DRIVER_PATCHRIGHT}/node")
# Repo layout first; on the box the sweep copy lives outside the repo, so
# fall back to the shipped client tree (or CAMOU_CONTRACT).
_CONTRACT_PATHS = [
    os.environ.get("CAMOU_CONTRACT", ""),
    str(pathlib.Path(__file__).resolve().parent.parent / "settings" / "launcher.json"),
    f"{HOME}/camoucrome-client/settings/launcher.json",
]
CONTRACT = json.loads(pathlib.Path(next(p for p in _CONTRACT_PATHS if p and os.path.exists(p))).read_text())
FORBIDDEN_FLAGS = CONTRACT["browser_argv_must_not_contain"]
EXPECTED_ARGS = set(CONTRACT["browser_argv_expected"]["args"])
HEADLESS_SELF_ADDED = set(CONTRACT["browser_argv_expected"]["headless_self_added"]["args"])
MIN_METHODS = 20
TIMING_TOLERANCE = 0.15  # D1's Runtime.enable signal is +21%; run-to-run noise on the box is ~5-10%
BASELINE_RUNS = 3

PAGE = b"""<!doctype html><title>driver</title><pre id="o"></pre><script>
const TRIALS = 7, N = 10000, times = [];
for (let t = 0; t < TRIALS; t++) {
  const t0 = performance.now(); let sink = 0;
  for (let i = 0; i < N; i++) sink += (new Error('probe')).stack.length;
  times.push(performance.now() - t0);
  if (sink < 0) console.log(sink);
}
document.getElementById('o').textContent = JSON.stringify({
  windowKeys: Object.keys(window),
  ownNames: Object.getOwnPropertyNames(window).length,
  initScript: typeof window.__camou_init,
  webdriver: navigator.webdriver,
  timesMs: times,
  stackTraceLimit: Error.stackTraceLimit,
  hasPrepare: typeof Error.prepareStackTrace,
  ua: navigator.userAgent,
});
</script>"""


def serve():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_port}/", srv


def baseline_once(url):
    """No CDP client at all: the browser dumps the DOM after load."""
    prof = tempfile.mkdtemp(prefix="camoucrome-base-")
    out = subprocess.run([EXE, "--headless=new", "--no-sandbox", "--no-first-run",
                          "--no-default-browser-check", "--disable-gpu",
                          f"--user-data-dir={prof}", "--dump-dom", url],
                         capture_output=True, text=True, timeout=120).stdout
    start = out.index('<pre id="o">') + len('<pre id="o">')
    return json.loads(html.unescape(out[start:out.index("</pre>", start)]))


def baseline(url):
    """BASELINE_RUNS launches; the timing reference is the median of their
    medians (one run wobbles 5-10% on the box), the key list must agree."""
    runs = [baseline_once(url) for _ in range(BASELINE_RUNS)]
    keys = {tuple(r["windowKeys"]) for r in runs}
    assert len(keys) == 1, f"baseline window keys differ between runs: {keys}"
    base = dict(runs[0])
    base["timesMs"] = [statistics.median(r["timesMs"]) for r in runs]
    return base


DRIVERS = [
    # (label, expected, command)
    ("python-stock", "RED", [f"{VENV_STOCK}/bin/python3", "-m", "camoucrome.probe",
                             "--driver", "stock", "--executable", EXE]),
    ("python-patchright", "GREEN", [f"{VENV}/bin/python3", "-m", "camoucrome.probe",
                                    "--driver", "patchright", "--executable", EXE]),
    ("go-stock", "RED", [GO_PROBE, "--driver-dir", DRIVER_STOCK, "--label", "go-stock",
                         "--executable", EXE]),
    ("go-patchright", "GREEN", [GO_PROBE, "--driver-dir", DRIVER_PATCHRIGHT,
                                "--label", "go-patchright", "--executable", EXE]),
]


def run_probe(cmd, url):
    env = dict(os.environ, DEBUG="pw:protocol", PLAYWRIGHT_NODEJS_PATH=NODE)
    for k in list(env):
        if k.startswith("CAMOU_CONFIG") or k.startswith("CAMOU_PRESET"):
            del env[k]
    p = subprocess.run(cmd + ["--url", url], capture_output=True, text=True,
                       timeout=300, env=env)
    if p.returncode != 0:
        return None, p.stderr[-800:]
    return json.loads(p.stdout), p.stderr


def check(label, result, log, base):
    rep = result["report"]
    rows = {}
    sends = log.count('"method":"')
    runtime_enable = log.count('"method":"Runtime.enable"')
    rows["C1 no Runtime.enable, logger alive"] = (
        runtime_enable == 0 and sends >= MIN_METHODS,
        f"Runtime.enable={runtime_enable} sends={sends}")
    # The probe's own init-script global is accounted for by C6.
    extra = sorted(set(rep["windowKeys"]) - set(base["windowKeys"]) - {"__camou_init"})
    missing = sorted(set(base["windowKeys"]) - set(rep["windowKeys"]))
    rows["C2 Object.keys(window) == no-driver baseline"] = (
        not extra and not missing, f"extra={extra} missing={missing}")
    rows["C3 navigator.webdriver false"] = (
        rep["webdriver"] is False, f"webdriver={rep['webdriver']}")
    argv = result["argv"] or []
    hits = [f for f in FORBIDDEN_FLAGS if any(a.startswith(f) for a in argv)]
    got = {a for a in argv[1:] if not a.startswith("--user-data-dir=") and a != "--no-sandbox"}
    expected = EXPECTED_ARGS | (HEADLESS_SELF_ADDED if "--headless=new" in got else set())
    unexpected = sorted(got - expected)
    absent = sorted(expected - got)
    rows["C4 argv == launcher.json expected set"] = (
        bool(argv) and not hits and not unexpected and not absent,
        f"hits={hits} unexpected={unexpected[:6]}{'...' if len(unexpected) > 6 else ''} absent={absent} argc={len(argv)}")
    # Measured 2026-09-10: BOTH drivers run a user's add_init_script in the
    # main world (typeof number) -- by design, that is what the caller asked
    # for. What must not appear is anything of the driver's own: own-name
    # count == baseline + exactly the probe's one global (own names catch a
    # non-enumerable binding that keys() misses).
    rows["C6 no driver-owned global; only the probe's own init script"] = (
        rep["initScript"] == "number" and rep["ownNames"] == base["ownNames"] + 1,
        f"typeof __camou_init={rep['initScript']} ownNames={rep['ownNames']} baseline={base['ownNames']}")
    med = statistics.median(rep["timesMs"])
    bmed = statistics.median(base["timesMs"])
    rows[f"C5 stack timing within {int(TIMING_TOLERANCE*100)}% of baseline"] = (
        med <= bmed * (1 + TIMING_TOLERANCE),
        f"median={med:.1f}ms baseline={bmed:.1f}ms ({(med/bmed-1)*100:+.0f}%)")
    return rows


def main():
    url, srv = serve()
    base = baseline(url)
    print(f"baseline (no driver): {len(base['windowKeys'])} window keys, webdriver={base['webdriver']}, "
          f"stack median {statistics.median(base['timesMs']):.1f} ms, ua ...{base['ua'][-28:]}")
    verdict = True
    for label, expected, cmd in DRIVERS:
        result, log = run_probe(cmd, url)
        if result is None:
            print(f"FAIL  {label}: probe did not run: {log}")
            verdict = False
            continue
        rows = check(label, result, log, base)
        allpass = all(ok for ok, _ in rows.values())
        c1 = rows["C1 no Runtime.enable, logger alive"][0]
        if expected == "GREEN":
            ok = allpass
        else:  # RED row: the stock driver must be caught by C1
            ok = not c1
        verdict &= ok
        print(f"{'PASS' if ok else 'FAIL'}  {label} (expected {expected}; ua ...{result['report']['ua'][-28:]})")
        for name, (r, note) in rows.items():
            print(f"      {'ok  ' if r else 'FAIL'} {name}: {note}")
    srv.shutdown()
    print("ALL_PASS" if verdict else "FAIL")
    sys.exit(0 if verdict else 1)


if __name__ == "__main__":
    main()

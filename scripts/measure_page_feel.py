#!/usr/bin/env python3
"""Page feel: does a humanized move cost the page CPU that a real mouse does not? Host only (Windows, session 1), not run in CI.

A page can count in a SharedArrayBuffer worker while the pointer moves; a real mouse costs it nothing. The pump of a humanized move
waits for each sample on its own thread and spins for about 1 ms in 8 (the 1.2 ms lead of camoucfg::kPacerLeadMicroseconds), so on a host
with few free cores that CPU is taken from the page. This measures the page's counting throughput during the move phase against its own
idle phase, per run, and compares an arm with the stock control (ctl125) and with -15.

It reuses the input-probe harness unchanged: the page is scripts/input_probe/page.html plus a counter worker, served with COOP/COEP
(cross-origin isolation, which SharedArrayBuffer needs); the worker's count is sampled every 50 ms into the page's own log as
{t: "spin", cnt, tms, ph}, and the harness's rows ignore it. The judge of the input rows is not touched.

  python measure_page_feel.py run --stock-exe PATH --fork-exe PATH --out DIR [--runs 6] [--arms ctl125,human] [--workers N]
  python measure_page_feel.py report DIR [DIR ...]       # one DIR per binary; the first holds ctl125

--workers: counter workers in the page (default: the logical CPUs, so that every core is busy and the pump's spin takes time from a
counter). With free cores the cost is invisible, which is the honest answer for such a host; the report prints the effect size next to
the control's spread, never only a verdict. Verdicts: PASS, FAIL, UNMEASURED (the control's spread is wider than the effect could be
judged, fewer than 4 runs, or a run without windows)."""
import argparse
import http.server
import json
import pathlib
import statistics
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import input_probe_rows as R  # noqa: E402

MIN_RUNS = 4
MIN_WINDOWS = 8            # 50 ms windows inside a phase before it is a rate
TOL_FLOOR = 0.02           # the smallest tolerance on the throughput ratio: 2 % of the idle rate
SPREAD_K = 3               # tolerance = max(floor, SPREAD_K x sd of the control's run ratios)

WORKER_JS = r"""
// page feel: counter workers on a SharedArrayBuffer, sampled every 50 ms into the log
(function () {
  const N = __WORKERS__;
  if (typeof SharedArrayBuffer === 'undefined') { L.push({n: seq++, t: 'spin', ts: 0, now: performance.now(), cnt: -1, tms: 0, ph: PH, tr: true}); return; }
  const sab = new SharedArrayBuffer(8 * N);
  const arr = new BigInt64Array(sab);
  const src = 'onmessage = e => { const a = new BigInt64Array(e.data.sab); let n = 0; for (;;) { n++; if ((n & 1023) === 0) Atomics.store(a, e.data.i, BigInt(n)); } }';
  const url = URL.createObjectURL(new Blob([src], {type: 'text/javascript'}));
  for (let i = 0; i < N; i++) new Worker(url).postMessage({sab, i});
  setInterval(() => {
    let sum = 0;
    for (let i = 0; i < N; i++) sum += Number(Atomics.load(arr, i));
    L.push({n: seq++, t: 'spin', ts: performance.now(), now: performance.now(), cnt: sum, tms: performance.now(), ph: PH, tr: true});
    dirty = true;
  }, 50);
})();
"""


def page_with_worker(workers=0):
    """The probe page with the counter worker appended inside its script. workers 0: one per logical CPU of the page's machine."""
    page = (HERE / "input_probe" / "page.html").read_text(encoding="utf-8")
    assert page.rstrip().endswith("</script>"), "the probe page no longer ends with its script"
    i = page.rstrip().rindex("</script>")
    n = str(int(workers)) if workers else "(navigator.hardwareConcurrency || 4)"
    return page[:i] + WORKER_JS.replace("__WORKERS__", n) + page[i:]


def isolate_headers():
    """Every response carries COOP and COEP (the harness's server has no hook for headers): process-wide, for this script only."""
    orig = http.server.BaseHTTPRequestHandler.end_headers

    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        orig(self)
    http.server.BaseHTTPRequestHandler.end_headers = end_headers


def rates(snap, phase):
    """[(count per ms)] of the 50 ms windows that lie inside `phase` (both ends tagged with it)."""
    sp = [e for e in snap["ev"] if e.get("t") == "spin" and e.get("cnt", -1) >= 0]
    out = []
    for a, b in zip(sp, sp[1:]):
        if a["ph"] == phase and b["ph"] == phase and b["tms"] > a["tms"]:
            out.append((b["cnt"] - a["cnt"]) / (b["tms"] - a["tms"]))
    return out


def ratio(snap):
    """Throughput during the move phase over the same run's idle phase, or None."""
    idle, move = rates(snap, "idle"), rates(snap, "move")
    if len(idle) < MIN_WINDOWS or len(move) < MIN_WINDOWS or statistics.mean(idle) <= 0:
        return None
    return statistics.mean(move) / statistics.mean(idle)


def load(d, arm):
    out = []
    for p in sorted(pathlib.Path(d).glob(arm + "-*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if rec.get("unmeasured") or not rec.get("snap"):
            continue
        r = ratio(rec["snap"])
        if r is not None:
            out.append(r)
    return out


def judge(ctl, arm):
    """(verdict, text). PASS: the arm's mean ratio is within the tolerance of the control's; FAIL: the whole interval of the
    difference lies beyond it; else UNMEASURED (the pooled-difference rule of input_probe_rows.judge)."""
    if len(ctl) < MIN_RUNS or len(arm) < MIN_RUNS:
        return "UNMEASURED", "n ctl %d, arm %d (need %d)" % (len(ctl), len(arm), MIN_RUNS)
    tol = max(TOL_FLOOR, SPREAD_K * statistics.pstdev(ctl))
    d, lo, hi = R.pool_diff(ctl, arm)
    text = "diff %+.4f [%+.4f, %+.4f] tol %.4f (ctl mean %.4f sd %.4f, arm mean %.4f)" % (
        d, lo, hi, tol, statistics.mean(ctl), statistics.pstdev(ctl), statistics.mean(arm))
    if abs(d) <= tol and (hi - lo) <= 2 * tol:
        return "PASS", text
    if lo > tol or hi < -tol:
        return "FAIL", text
    return "UNMEASURED", text


def cmd_report(a):
    dirs = [pathlib.Path(d) for d in a.dirs]
    ctl = load(dirs[0], "ctl125")
    print("page-feel throughput ratio (move phase / idle phase, per run); tolerance max(%.2f, %d x control sd)" % (TOL_FLOOR, SPREAD_K))
    print("  ctl125 (%s): %s" % (dirs[0], ["%.4f" % x for x in ctl]))
    worst = 0
    for d in dirs:
        for arm in ("rawh", "human", "raw"):
            vals = load(d, arm)
            if not vals:
                continue
            v, text = judge(ctl, vals)
            print("  %-6s %-9s %-11s %s" % (arm, d.name, v, text))
            worst = max(worst, {"PASS": 0, "UNMEASURED": 3, "FAIL": 1}[v])
    return worst


def cmd_run(a):
    import measure_input_probes as M
    isolate_headers()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="page-feel-"))
    (tmp / "input_probe").mkdir()
    (tmp / "input_probe" / "page.html").write_text(page_with_worker(a.workers), encoding="utf-8")
    M.HERE = tmp        # serve() reads input_probe/page.html from here
    argv = ["run", "--stock-exe", a.stock_exe, "--fork-exe", a.fork_exe, "--out", a.out, "--runs", str(a.runs), "--arms", a.arms]
    if a.fork_version:
        argv += ["--fork-version", a.fork_version]
    return M.main(argv)


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--stock-exe", required=True)
    r.add_argument("--fork-exe", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--runs", type=int, default=6)
    r.add_argument("--arms", default="ctl125,human")
    r.add_argument("--fork-version", default=None)
    r.add_argument("--workers", type=int, default=0, help="counter workers (default: the logical CPUs; fixed in the page copy)")
    p = sub.add_parser("report")
    p.add_argument("dirs", nargs="+")
    a = ap.parse_args(argv)
    return cmd_run(a) if a.cmd == "run" else cmd_report(a)


if __name__ == "__main__":
    sys.exit(main())

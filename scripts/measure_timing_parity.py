#!/usr/bin/env python3
"""Timing parity (spec 2026-11-13-timing-parity-design.md): does the fork's timing differ from stock Chrome's,
from page script, on the same Windows host?

  P  workload ratios (build optimisation): each workload's time over the regexp replace's, JIT side against C++ side.
  G  spoofed getter cost (port item B6): a getter's ns per read against an untouched control getter, window and worker,
     plus the first read in a fresh page and a fresh worker.

Arms: S stock (frozen copy, seeded profile), S2 stock again (the RED), F the fork with a generated Windows identity,
FH the same identity claiming the host's core count (no CPU pin), F0 the fork with no config, V a vanilla Chromium snapshot. Every arm is spawned directly (`chrome.exe --user-data-dir
<dir> <url>`), with no driver attached: the page POSTs its result to a local server, and a CDP connection is made only
AFTER the result is in, to read chrome://gpu's crash count (every arm carries the same --remote-debugging-port).

  python measure_timing_parity.py run --arms S,F,F0,V --launches 6 --out DIR [--plant WORKLOAD] ...
  python measure_timing_parity.py report DIR

Run on the host in session 1 through scripts/windows/run-interactive.ps1, in the client venv. The pure parts (verdicts,
page generation, result parsing, tables) are tested by test_measure_timing_parity.py."""
import argparse
import datetime
import http.server
import json
import os
import pathlib
import re
import statistics
import subprocess
import sys
import tempfile
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

# Camoufox's constants (browser/tests/playwright/patches/getter-cost-parity.py); change one only with this host's
# S-against-S spread as the reason.
SLOWER_FACTOR = 2.0
FASTER_FACTOR = 2.0
MIN_GAP_NS = 30.0
P_FACTOR = 1.15            # starts at the spec's 1.15; set from S-against-S before the real run
FIRST_READ_MS = 1.0
FIRST_READ_TIMES = 3.0
PAGE_TIMEOUT_S = 300
MIN_READS = 100000          # loops of at least 1e5 reads (performance.now() is 5 us at best)
MIN_FVM_GB = 8.0

# ---- what the page times ----

# settings/keys.json dot-keys whose page expression is not the key itself
KEY_EXPR = {"window.outerWidth": "outerWidth", "window.outerHeight": "outerHeight",
            "window.screenX": "screenX", "window.screenY": "screenY"}
# Untouched getters: no patch and no addition names onLine (grep in the PR), so the config is never read behind it.
# The bindings generator hook of the observer sits under every attribute, the control included, which is what the
# control's scaling is for.
WINDOW_CONTROL = "navigator.onLine"
WORKER_CONTROL = "navigator.onLine"

SYNTHETIC_WINDOW = [
    "navigator.userAgentData.brands", "navigator.userAgentData.platform", "navigator.userAgentData.mobile",
    "Intl.DateTimeFormat().resolvedOptions().timeZone", "new Date().getTimezoneOffset()", "devicePixelRatio",
    "A.sampleRate", "A.baseLatency", "A.outputLatency", "A.destination.maxChannelCount",
    "speechSynthesis.getVoices()", "M.matches",   # A: an AudioContext, M: matchMedia('(pointer: fine)'), built once
]
SYNTHETIC_WORKER = [
    "navigator.userAgentData.brands", "navigator.userAgentData.platform", "navigator.userAgentData.mobile",
    "Intl.DateTimeFormat().resolvedOptions().timeZone", "new Date().getTimezoneOffset()",
]
FIRST_READS = {"window": ["navigator.hardwareConcurrency", "screen.width"],
               "worker": ["navigator.hardwareConcurrency", "navigator.language"]}

# name -> group. JIT side: the denominators (not PGO'd; irregexp compiles to native code on x64). C++ side: Blink and
# V8's C++ runtime. sort_builtin is a snapshot builtin: labelled, outside both groups.
WORKLOAD_GROUP = {
    "int": "jit", "float": "jit", "regexp": "jit",
    "json_parse": "cpp", "json_stringify": "cpp", "structured_clone": "cpp", "text_codec": "cpp",
    "dom_append": "cpp", "inner_html": "cpp", "query_selector_all": "cpp", "computed_style": "cpp", "canvas2d": "cpp",
    "gcs_read": "cpp", "style_set": "cpp", "layout_read": "cpp",   # computed_style split: getComputedStyle alone, style write alone, forced layout alone
    "sort_builtin": "builtin",
}


def workload_names():
    return list(WORKLOAD_GROUP)


def _dot_keys():
    keys = json.loads((ROOT / "settings" / "keys.json").read_text(encoding="utf-8"))["keys"]
    return [k["key"] for k in keys if "." in k["key"]]


def window_getters():
    return [KEY_EXPR.get(k, k) for k in _dot_keys()] + SYNTHETIC_WINDOW + [WINDOW_CONTROL]


def worker_getters():
    return [k for k in _dot_keys() if k.startswith("navigator.")] + SYNTHETIC_WORKER + [WORKER_CONTROL]


def page_spec(arm, plant=None):
    return json.dumps({"arm": arm, "plant": plant, "window": window_getters(), "worker": worker_getters(),
                       "first": FIRST_READS})


# One page. Phase order: first reads in this fresh page; the fresh worker's first reads and its getters (G worker) run
# in the worker, started before P; then P; then G window. The result goes back by POST, never by evaluate.
_PAGE = r"""<!doctype html><meta charset=utf-8><title>timing</title><body><script>
const SPEC = JSON.parse(decodeURIComponent(location.hash.slice(1)));
const MIN_READS = __MIN_READS__;
const clk = () => performance.now();
function benchG(exprs, setup, ctx) {            // shared by the window and the worker: serialised with toString()
  eval(setup);
  const out = {};
  const mk = (e) => new Function('A', 'M', 'N', 'let x; const t = performance.now(); for (let i = 0; i < N; i++) { x = (' + e + '); } const d = performance.now() - t; self.__s = x; return d;');
  const empty = new Function('A', 'M', 'N', 'let x; const t = performance.now(); for (let i = 0; i < N; i++) { x = i; } const d = performance.now() - t; self.__s = x; return d;');
  const A = ctx.A, M = ctx.M;
  const fast = (f, N) => { let b = Infinity; let rounds = 0; const t0 = performance.now();
    while (rounds < 7 && (rounds < 3 || performance.now() - t0 < 1500)) { b = Math.min(b, f(A, M, N)); rounds++; } return b; };
  for (const e of exprs) {
    let f, v;
    try { v = (new Function('A', 'M', 'return (' + e + ');'))(A, M); f = mk(e); f(A, M, 10); } catch (err) { out[e] = null; continue; }
    if (v === undefined) { out[e] = undefined; continue; }
    let N = MIN_READS;
    while (N < 5e7 && f(A, M, N) < 25) N *= 4;
    out[e] = Math.max(0, fast(f, N) - fast(empty, N)) * 1e6 / N;
  }
  return out;
}
const WORKER_SRC = 'const MIN_READS = ' + MIN_READS + '; const benchG = ' + benchG.toString() + ';' +
  'onmessage = (ev) => { const s = ev.data; const first = {};' +
  ' for (const e of s.first) { let f = null; try { f = new Function("return (" + e + ");"); } catch (x) {} const t = performance.now(); let v, ok = true; try { v = f(); } catch (x) { ok = false; } const d = performance.now() - t; first[e] = !ok ? null : v === undefined ? undefined : d; }' +
  ' postMessage({first: first, g: benchG(s.worker, "", {A: null, M: null})}); };';

function workloads(plant) {
  const J = JSON.stringify(Array.from({length: 40}, (_, i) => ({id: i, name: 'item' + i, tags: ['a', 'b', 'c'], v: i * 1.5, nested: {x: i, y: [i, i + 1]}})));
  const O = JSON.parse(J);
  const S = 'The quick brown fox jumps over the lazy dog 0123456789 '.repeat(40);
  const H = '<div class="a"><span>x</span><ul><li>1</li><li>2</li><li>3</li></ul><p>some <b>text</b> here</p></div>'.repeat(10);
  const box = document.createElement('div');
  box.style.cssText = 'position:absolute;left:-9999px;top:0;width:200px;height:200px;overflow:hidden';
  document.body.appendChild(box);
  const tree = document.createElement('div');
  for (let i = 0; i < 200; i++) { const d = document.createElement('div'); d.className = 'k' + (i % 5); d.textContent = i; tree.appendChild(d); }
  box.appendChild(tree);
  const target = document.createElement('div'); target.style.cssText = 'width:10px;height:10px'; box.appendChild(target);
  const cv = document.createElement('canvas'); cv.width = 256; cv.height = 256; const cx = cv.getContext('2d');
  const arr = Array.from({length: 500}, (_, i) => (i * 7919) % 1009);
  let sink;
  const W = {
    int: (n) => { let x = 0; for (let i = 0; i < n; i++) x = (x + i * 7) | 0; sink = x; },
    float: (n) => { let x = 0.5; for (let i = 0; i < n; i++) x = x * 1.0000001 + Math.sin(i) * 1e-9; sink = x; },
    regexp: (n) => { const s = 'the quick brown fox 12345 jumps'; let r; for (let i = 0; i < n; i++) r = s.replace(/[aeiou]\d?/g, '_'); sink = r; },
    json_parse: (n) => { for (let i = 0; i < n; i++) sink = JSON.parse(J); },
    json_stringify: (n) => { for (let i = 0; i < n; i++) sink = JSON.stringify(O); },
    structured_clone: (n) => { for (let i = 0; i < n; i++) sink = structuredClone(O); },
    text_codec: (n) => { const te = new TextEncoder(), td = new TextDecoder(); for (let i = 0; i < n; i++) sink = td.decode(te.encode(S)); },
    dom_append: (n) => { let p = document.createElement('div'); for (let i = 0; i < n; i++) { if (i % 500 === 0) p = document.createElement('div'); p.appendChild(document.createElement('span')); } sink = p; },
    inner_html: (n) => { const e = document.createElement('div'); for (let i = 0; i < n; i++) e.innerHTML = H; sink = e; },
    query_selector_all: (n) => { for (let i = 0; i < n; i++) sink = tree.querySelectorAll('.k3'); },
    computed_style: (n) => { for (let i = 0; i < n; i++) { target.style.height = (i & 1 ? 11 : 12) + 'px'; sink = getComputedStyle(target).height; sink = target.offsetHeight; } },
    gcs_read: (n) => { for (let i = 0; i < n; i++) sink = getComputedStyle(target).height; },
    style_set: (n) => { for (let i = 0; i < n; i++) target.style.height = (i & 1 ? 11 : 12) + 'px'; },
    layout_read: (n) => { for (let i = 0; i < n; i++) { sink = target.offsetHeight; } },
    canvas2d: (n) => { for (let i = 0; i < n; i++) { cx.fillStyle = i & 1 ? '#f60' : '#06f'; cx.beginPath(); cx.arc((i * 37) % 256, (i * 91) % 256, 6, 0, 7); cx.fill(); cx.fillRect((i * 13) % 250, (i * 29) % 250, 5, 5); } },
    sort_builtin: (n) => { for (let i = 0; i < n; i++) sink = arr.slice().sort((a, b) => a - b); },
  };
  if (plant && W[plant]) { const f = W[plant]; W[plant] = (n) => { f(n); f(n); }; }   // test-only slowdown: twice the work
  return W;
}
function benchP(W) {
  const out = {};
  for (const name of Object.keys(W)) {
    const f = W[name];
    f(2);
    let n = 8;
    while (n < 1e9 && (() => { const t = clk(); f(n); return clk() - t; })() < 15) n *= 2;
    let best = Infinity;
    for (let r = 0; r < 9; r++) { const t = clk(); f(n); best = Math.min(best, clk() - t); }
    out[name] = best * 1e6 / n;
  }
  return out;
}

(async () => {
  const res = {arm: SPEC.arm, plant: SPEC.plant, crossOriginIsolated: self.crossOriginIsolated, errors: [], worker_ok: false,
               first: {window: {}, worker: {}}, p: {}, g_window: {}, g_worker: {}};
  try {
    for (const e of SPEC.first.window) {                 // 1. first reads, fresh page, before anything else
      let f = null; try { f = new Function('return (' + e + ');'); } catch (x) {}   // built before the clock starts
      const t = clk(); let v, ok = true; try { v = f(); } catch (x) { ok = false; }
      const d = clk() - t;
      res.first.window[e] = !ok ? null : v === undefined ? undefined : d;
    }
    const w = new Worker(URL.createObjectURL(new Blob([WORKER_SRC])));   // 2. fresh worker: its first reads, then its getters
    const wr = new Promise((ok, no) => { w.onmessage = (ev) => ok(ev.data); w.onerror = (ev) => no(new Error('worker error')); setTimeout(() => no(new Error('worker timeout')), 120000); });
    w.postMessage({first: SPEC.first.worker, worker: SPEC.worker});
    let wdata = null;
    try { wdata = await wr; } catch (err) { res.errors.push(String(err)); }
    if (wdata) { res.first.worker = wdata.first; res.g_worker = wdata.g; res.worker_ok = true; }
    res.p = benchP(workloads(SPEC.plant));               // 3. P
    const A = new (self.AudioContext || self.webkitAudioContext)();
    const M = matchMedia('(pointer: fine)');
    res.g_window = benchG(SPEC.window, '', {A, M});      // 4. G window
    try { A.close(); } catch (x) {}
  } catch (err) { res.errors.push(String(err && err.stack || err)); }
  fetch('/result', {method: 'POST', body: JSON.stringify(res)});
})();
</script></body>"""


def page_html():
    return _PAGE.replace("__MIN_READS__", str(MIN_READS))


# ---- pure statistics and verdicts ----

def median_over(runs, key):
    """name -> median over launches of the figure, ignoring launches that have none (None / undefined)."""
    names = []
    for r in runs:
        names += [n for n in (r.get(key) or {}) if n not in names]
    out = {}
    for n in names:
        vals = [r[key][n] for r in runs if isinstance(r.get(key), dict) and isinstance(r[key].get(n), (int, float))]
        out[n] = statistics.median(vals) if vals else None
    return out


def ratios(p):
    """Each workload's time over the regexp replace's. Camoufox's denominator: irregexp compiles to native code on x64
    (JIT side, not PGO'd). The spec's integer loop is no denominator: V8 reduces it to ~0.5 ns in stock and the fork
    and leaves ~3.8 ns in the vanilla snapshot (other V8 version), so every ratio over it moved 7x between arms."""
    base = p.get("regexp")
    return {k: v / base for k, v in p.items() if k != "regexp" and isinstance(v, (int, float)) and base}


def p_verdict(stock, fork, factor=P_FACTOR):
    """GAP when the fork's median is outside the stock launches' range AND differs from stock's median by more than
    `factor` (either way); else OK; UNMEASURED with no launches on a side."""
    if not stock or not fork:
        return "UNMEASURED"
    s, f = statistics.median(stock), statistics.median(fork)
    outside = f < min(stock) or f > max(stock)
    far = max(f / s, s / f) > factor if s > 0 and f > 0 else True
    return "GAP" if outside and far else "OK"


def verdict(s, c, stock_base, camou_base):
    """Camoufox's rule: (slower, faster) for one getter. s and c are stock's and the fork's cost; stock_base and
    camou_base each browser's control cost. The fork's cost is scaled by stock_base / camou_base."""
    scaled = c * stock_base / camou_base
    slower = scaled > SLOWER_FACTOR * s and scaled - s >= MIN_GAP_NS
    faster = FASTER_FACTOR * c / camou_base < s / stock_base and s - c >= MIN_GAP_NS
    return slower, faster


def g_verdict(s, c, stock_base, camou_base):
    if None in (s, c, stock_base, camou_base) or not stock_base or not camou_base:
        return "UNMEASURED"
    if max(camou_base / stock_base, stock_base / camou_base) > SLOWER_FACTOR and abs(camou_base - stock_base) >= MIN_GAP_NS:
        return "FAIL-control"          # the browsers are not comparable here (either way: a much cheaper control inflates the scaling)
    slower, faster = verdict(s, c, stock_base, camou_base)
    return "FAIL-slower" if slower else "FAIL-faster" if faster else "PASS"


def first_read_verdict(stock_ms, fork_ms):
    if stock_ms is None or fork_ms is None:
        return "UNMEASURED"
    return "FAIL" if fork_ms > FIRST_READ_MS and fork_ms > FIRST_READ_TIMES * stock_ms else "PASS"


def parse_result(raw):
    """(record, None) or (None, why): a launch the page did not finish is UNMEASURED, never a pass. A missing worker
    block is the worst case (a worker row that never ran must not read as PASS)."""
    if not isinstance(raw, dict) or not all(k in raw for k in ("arm", "p", "g_window", "g_worker", "first", "worker_ok")):
        return None, "result is missing blocks"
    if not raw.get("worker_ok"):
        return None, "the dedicated worker did not report (worker rows UNMEASURED)"
    if not raw.get("crossOriginIsolated"):
        return None, "page was not crossOriginIsolated (timer resolution is 100 us)"
    if raw.get("errors"):
        return None, "page errors: " + "; ".join(str(e)[:120] for e in raw["errors"])
    if not raw["p"] or not raw["g_window"]:
        return None, "empty P or G block"
    return raw, None


def compare(stock_runs, other_runs, p_factor=P_FACTOR):
    """Rows of P (ratios), G (getters) and first reads for `other_runs` against `stock_runs`."""
    rows = {"p": [], "g": [], "first": []}
    sr = [ratios(r["p"]) for r in stock_runs]
    orr = [ratios(r["p"]) for r in other_runs]
    names = []
    for r in sr + orr:
        names += [n for n in r if n not in names]
    for n in names:
        sv = [r[n] for r in sr if n in r]
        ov = [r[n] for r in orr if n in r]
        group = WORKLOAD_GROUP.get(n, "pair")
        rows["p"].append({"name": n, "group": group, "stock": sv, "other": ov, "verdict": p_verdict(sv, ov, p_factor)})
    for where, key, ctl in (("window", "g_window", WINDOW_CONTROL), ("worker", "g_worker", WORKER_CONTROL)):
        s, o = median_over(stock_runs, key), median_over(other_runs, key)
        sb, ob = s.get(ctl), o.get(ctl)
        for n in list(s) + [k for k in o if k not in s]:    # a row missing on one side is UNMEASURED, never dropped
            v = g_verdict(s.get(n), o.get(n), sb, ob)
            if n == ctl and v != "FAIL-control":
                v = "control"
            rows["g"].append({"where": where, "name": n, "stock": s.get(n), "other": o.get(n), "stock_ctl": sb, "other_ctl": ob,
                              "verdict": v})
    for where in ("window", "worker"):
        s = median_over([{"x": r["first"][where]} for r in stock_runs], "x")
        o = median_over([{"x": r["first"][where]} for r in other_runs], "x")
        for n in list(s) + [k for k in o if k not in s]:
            rows["first"].append({"where": where, "name": n, "stock": s.get(n), "other": o.get(n),
                                  "verdict": first_read_verdict(s.get(n), o.get(n))})
    return rows


# ---- tables ----

def fmt(v, nd=1):
    return "-" if v is None else f"{v:.{nd}f}"


def render(arm, rows):
    out = [f"\n== {arm} against S ==", "P  ratio over the regexp replace (median [min, max] over launches)",
           f"{'workload':24s} {'group':8s} {'S':>22s} {arm:>22s}  verdict"]
    for r in rows["p"]:
        def cell(v):
            return f"{statistics.median(v):7.3f} [{min(v):.3f},{max(v):.3f}]" if v else "-"
        out.append(f"{r['name']:24s} {r['group']:8s} {cell(r['stock']):>22s} {cell(r['other']):>22s}  {r['verdict']}")
    out.append("\nG  getter cost, ns per read (median over launches of the fastest round)")
    out.append(f"{'scope':7s} {'getter':52s} {'S':>9s} {arm:>9s}  verdict")
    for r in rows["g"]:
        out.append(f"{r['where']:7s} {r['name'][:52]:52s} {fmt(r['stock']):>9s} {fmt(r['other']):>9s}  {r['verdict']}")
    out.append("\nFirst read in a fresh page / worker, ms (median over launches)")
    for r in rows["first"]:
        out.append(f"{r['where']:7s} {r['name']:36s} {fmt(r['stock'], 3):>9s} {fmt(r['other'], 3):>9s}  {r['verdict']}")
    return "\n".join(out)


def totals(rows):
    gap = sum(r["verdict"] == "GAP" for r in rows["p"])
    fail = sum(r["verdict"].startswith("FAIL") for r in rows["g"]) + sum(r["verdict"] == "FAIL" for r in rows["first"])
    unm = sum(r["verdict"] == "UNMEASURED" for r in rows["p"] + rows["g"] + rows["first"])
    return gap, fail, unm


def load_run(run_dir):
    """arm -> [measured launch records]; the unmeasured launches (arm -> [reason]) beside them."""
    ok, bad = {}, {}
    for f in sorted(pathlib.Path(run_dir).glob("launch-*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("unmeasured"):
            bad.setdefault(d["arm"], []).append(d["unmeasured"])
        else:
            ok.setdefault(d["arm"], []).append(d["result"])
    return ok, bad


def report_cmd(a):
    ok, bad = load_run(a.dir)
    ref = a.ref
    if ref not in ok:
        print(f"UNMEASURED: no measured launch of the reference arm {ref}")
        return 3
    print(f"launches measured: {', '.join(f'{k} {len(v)}' for k, v in ok.items())}")
    for arm, reasons in bad.items():
        print(f"UNMEASURED launches of {arm}: {len(reasons)} ({'; '.join(sorted(set(reasons)))})")
    code = 0
    for arm in bad:
        if arm not in ok and arm != ref:
            print(f"\n{arm}: UNMEASURED, no launch measured")
            code = 3
    for arm, runs in ok.items():
        if arm == ref:
            continue
        rows = compare(ok[ref], runs, a.p_factor)
        print(render(arm, rows))
        gap, fail, unm = totals(rows)
        print(f"\n{arm}: {gap} GAP, {fail} FAIL, {unm} UNMEASURED rows")
        code = max(code, 3 if unm else 1 if gap or fail else 0)
    return code


# ---- host side: serving and launching (not unit-tested; it needs the host) ----

class _Server(http.server.ThreadingHTTPServer):
    results = None


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = page_html().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")      # crossOriginIsolated: 5 us timers
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers["Content-Length"])
        self.server.results.append(json.loads(self.rfile.read(n)))
        self.send_response(204)
        self.end_headers()


def _free_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _fvm_gb():
    p = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "(Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory/1MB"],
                       capture_output=True, text=True, timeout=60)
    return float(p.stdout.strip() or "0")


def _cpu_load():
    p = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "(Get-CimInstance Win32_Processor | Measure-Object LoadPercentage -Average).Average"],
                       capture_output=True, text=True, timeout=60)
    try:
        return float(p.stdout.strip())
    except ValueError:
        return None


def session_active(text):
    """True when `query session` output shows session 1 (the owner's) Active."""
    return bool(re.search(r"\s1\s+Active\b", text or ""))


def _session_text():
    return subprocess.run(["query", "session"], capture_output=True, text=True, timeout=60).stdout


BUILD_LOCK = "$HOME/actions-runner/_work/camoucrome/camoucrome/scripts/build_lock.sh"


def lock_problem(text):
    """Why the box's build lock says a build may run (its `status` output), or None when it is free."""
    first = (text or "").strip().splitlines()[:1]
    return None if first and first[0].strip() == "free" else f"build_lock is not free: {first[0].strip() if first else 'unreadable'}"


def _busy():
    """Why this launch cannot be trusted, or None: another browser or a build is running (a Windows process, or a
    WSL build, which Windows cannot see: the build lock says)."""
    lock = subprocess.run(["wsl.exe", "-d", "Ubuntu-24.04", "-u", "lang", "--", "bash", "-c", f"bash {BUILD_LOCK} status timing-parity"],
                          capture_output=True, text=True, timeout=60)
    if lock_problem(lock.stdout):
        return lock_problem(lock.stdout)
    p = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in "
                        "'chrome','siso','ninja','clang-cl' } | Select-Object -ExpandProperty ProcessName) -join ','"],
                       capture_output=True, text=True, timeout=60)
    if p.stdout.strip():
        return f"another process is running: {p.stdout.strip()}"
    fvm = _fvm_gb()
    if fvm < MIN_FVM_GB:
        return f"FVM {fvm:.1f} GB under {MIN_FVM_GB:.0f}"
    return None


def _kill_tree(pid):
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)   # PID-scoped, never by name


def _find_chrome(d):
    d = pathlib.Path(d)
    hits = [d / "chrome.exe"] + sorted(d.rglob("chrome.exe"))
    for h in hits:
        if h.is_file():
            return str(h)
    raise SystemExit(f"UNMEASURED: no chrome.exe under {d}")


def run_cmd(a):
    import gpu_gate
    import measure_step2 as m2
    from camoucrome import launcher, pin

    gpu_gate.require_interactive()
    arms = a.arms.split(",")
    stock_exe = os.path.join(a.stock_app or os.environ.get("CAMOU_STOCK_APP") or m2.STOCK_APP, "chrome.exe")
    fork_exe = os.path.join(a.fork_dir, "chrome.exe") if a.fork_dir else os.environ.get("CAMOU_FORK_EXE")
    exe_of = {"S": stock_exe, "S2": stock_exe, "F": fork_exe, "F0": fork_exe, "FH": fork_exe,
              "V": _find_chrome(a.snapshot_dir) if "V" in arms and a.snapshot_dir else None}
    for arm in arms:
        if arm not in exe_of:
            sys.exit(f"unknown arm {arm}")
        if not exe_of[arm]:
            sys.exit(f"arm {arm}: no executable (--fork-dir / CAMOU_FORK_EXE / --snapshot-dir)")
    if a.plant and "S2" not in arms:
        sys.exit("--plant slows the S2 arm: add S2 to --arms")
    out_dir = pathlib.Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = out_dir / run_id
    run_dir.mkdir()
    versions = {arm: m2.exe_version(exe) for arm, exe in exe_of.items() if exe and arm in arms}
    (run_dir / "run.json").write_text(json.dumps({"arms": arms, "launches": a.launches, "versions": versions,
                                                  "plant": a.plant, "min_reads": MIN_READS}, indent=1), encoding="utf-8")
    print(f"run {run_dir}; versions {versions}", flush=True)

    server = _Server(("127.0.0.1", 0), _Handler)
    server.results = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/"

    def launch_one(arm, i):
        why = _busy() or (None if session_active(_session_text()) else "session 1 is not Active")
        rec = {"arm": arm, "i": i, "fvm_gb": None, "cpu_load": None}
        if why:
            rec["unmeasured"] = why
            return rec
        rec["fvm_gb"], rec["cpu_load"] = round(_fvm_gb(), 1), _cpu_load()
        port = _free_port()
        own_seed = arm in ("S", "S2")
        udd = m2.SEED.fresh_copy() if own_seed else tempfile.mkdtemp(prefix="timing-parity-")
        crash = tempfile.mkdtemp(prefix="timing-parity-crash-")
        url = base + "#" + __import__("urllib.parse").parse.quote(page_spec(arm, a.plant if arm == "S2" else None))
        env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}
        argv = [exe_of[arm], *launcher.BASE_ARGS, f"--user-data-dir={udd}", f"--remote-debugging-port={port}"]
        saved = None
        try:
            if arm in ("F", "FH"):
                ident = m2.identity(a.seed_base + i)
                cfg, lo = ident["config"], ident["launch"]
                if arm == "FH":     # the same identity, claiming the host's core count: no pin, so the pin and the build tell apart
                    cfg = {**cfg, "navigator.hardwareConcurrency": os.cpu_count()}
                args = launcher.build_args(tuple(lo["window"]) if lo.get("window") else None, lo.get("dpr"),
                                           lo.get("args", []), False, udd, launcher.accept_lang_of(cfg),
                                           position=tuple(lo["position"]) if lo.get("position") else None)
                argv = [exe_of[arm]] + [x for x in args if x != "--remote-debugging-pipe"] + [f"--remote-debugging-port={port}"]
                env = launcher.build_env(cfg, fontconfig=launcher.fontconfig_for(cfg, None, None, exe_of[arm]), crash_dir=crash)
                n = launcher.effective_keys(cfg).get("navigator.hardwareConcurrency")
                rec["claimed_hc"], rec["host_cpus"] = n, os.cpu_count()
                if isinstance(n, int) and not isinstance(n, bool) and n >= 1:
                    saved, chosen = _pin_self(pin, n)
                    rec["pin_mask"] = sorted(chosen) if chosen else None
            server.results = []
            proc = subprocess.Popen(argv + [url], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if saved is not None:
                pin.set_mask(os.getpid(), saved)       # restored right after the spawn; the browser keeps the pin
                saved = None
            deadline = time.monotonic() + PAGE_TIMEOUT_S
            while not server.results and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.5)
            if not server.results:
                rec["unmeasured"] = "the page never reported" + (f" (exit {proc.returncode})" if proc.poll() is not None else "")
                return rec
            res, why = parse_result(server.results[0])
            crashes = gpu_gate.read_port(port)             # after the result: the only CDP connection of the launch
            if not session_active(_session_text()):
                rec["unmeasured"] = "session 1 left Active during the launch"
            elif crashes != 0:
                rec["unmeasured"] = f"gpu-crash={'unknown' if crashes is None else crashes}"
            elif why:
                rec["unmeasured"] = why
            else:
                rec["result"] = res
            return rec
        finally:
            if saved is not None:
                pin.set_mask(os.getpid(), saved)
            try:
                _kill_tree(proc.pid)
            except UnboundLocalError:
                pass
            time.sleep(1.0)
            launcher.remove_dir(crash)
            if own_seed:
                m2.SEED.drop(udd)
            else:
                launcher.remove_dir(udd)

    def go():
        for i in range(a.launches):
            for arm in arms:
                rec = launch_one(arm, i)
                (run_dir / f"launch-{arm}-{i:02d}.json").write_text(json.dumps(rec), encoding="utf-8")
                print(f"{arm}/{i}: {'UNMEASURED ' + rec['unmeasured'] if rec.get('unmeasured') else 'ok'}", flush=True)

    try:
        if any(x in arms for x in ("S", "S2")):
            with m2.seeded_control(stock_exe):
                go()
        else:
            go()
    finally:
        server.shutdown()
    print(f"launches written to {run_dir}")
    return 0


def _pin_self(pin, n):
    """Pin this process to n random CPUs of the ones it may use, so a child spawned now inherits the mask (the same
    rule as camoucrome.pin: a claim of N cores is enforced by affinity). Returns (the mask to restore, the mask set), or (None, None)."""
    import random
    allowed = sorted(pin.get_mask(os.getpid()) or [])
    if not allowed or n >= len(allowed):
        return None, None
    saved, chosen = set(allowed), set(random.SystemRandom().sample(allowed, n))
    pin.set_mask(os.getpid(), chosen)
    return saved, chosen


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--arms", default="S,F,F0,V")
    r.add_argument("--launches", type=int, default=6)
    r.add_argument("--out", required=True)
    r.add_argument("--stock-app")
    r.add_argument("--fork-dir")
    r.add_argument("--snapshot-dir")
    r.add_argument("--plant", help="test-only: slow this workload down in the S2 arm")
    r.add_argument("--seed-base", type=int, default=1000, help="the fork's identity seed is this plus the launch number")
    t = sub.add_parser("report")
    t.add_argument("dir")
    t.add_argument("--ref", default="S")
    t.add_argument("--p-factor", type=float, default=P_FACTOR)
    a = ap.parse_args(argv)
    return run_cmd(a) if a.cmd == "run" else report_cmd(a)


if __name__ == "__main__":
    sys.exit(main())

"""SP2d client verify (spec section 6): the click helper (A) and the launch flag
(B) of the Python, Node and Go clients, driven live against the fork with
humanize on, a Windows claim and a fixed seed. 30 rows:
A1-A7 for each client (21), B1-B4 for Python and Node (8), G1 for Go (1).

Each row launches the client's probe (`--scenario ROW --url URL --config JSON`),
which loads a page served from 127.0.0.1, performs the row's actions and prints
{"log": <the page's #o>, "error": null|str, "wrapper_hits": int, "extra": ...}.
The page logs `wheel` [t, deltaY], `scroll` [t, scrollY] and `click`
[offsetX, offsetY, id, t, scrollY] itself, so every verdict reads what the
page saw, never what the client claims. The probe's DEBUG=pw:protocol stderr
is the driver's protocol log (A2/A3/A5 count DOM.scrollIntoViewIfNeeded in it).

Run on the box under ~/camoucrome-verify/venv (CAMOU_CLIENT, PYTHONPATH,
CAMOU_GO_PROBE, CAMOU_DRIVER_NODE as for verify_sp6b_driver.py). Node needs a
patchright-core 1.62.3 dir (CAMOU_DRIVER_NODE): on 1.62.1 its geometry runs
in the main world. Exit 0 only when all EXPECTED rows ran and passed.
"""
import http.server
import importlib.util
import json
import math
import os
import pathlib
import subprocess
import sys
import threading

from lib_shell import CHROME as EXE, layout

HOME, PY, NODE_DEFAULT, CLIENT, _ = layout()
GO_PROBE = os.environ.get("CAMOU_GO_PROBE", f"{HOME}/camoucrome-go/camoucrome-probe")
DRIVER = os.environ.get("CAMOU_DRIVER", f"{HOME}/camoucrome-driver")
DRIVER_NODE = os.environ.get("CAMOU_DRIVER_NODE", f"{HOME}/camoucrome-driver-node")
NODE = os.environ.get("PLAYWRIGHT_NODEJS_PATH", f"{DRIVER}/node")
NODE_PROBE = os.environ.get("CAMOU_NODE_PROBE", str(CLIENT / "client" / "node" / "probe.js"))
TABLES = pathlib.Path(os.environ.get(
    "CAMOU_CLICK_TABLES", str(CLIENT / "client" / "python" / "camoucrome" / "_click_tables.py")))

EXPECTED = 7 * 3 + 4 * 2 + 1
CONFIG = json.dumps({"humanize:enabled": True, "humanize:seed": 12345,
                     "ua:osInfo": "Windows NT 10.0; Win64; x64", "ua:platform": "Windows"})
MIN_METHODS = 20      # a silenced protocol logger must not pass the A2/A3/A5 counts vacuously
CENTRE_TOL = 0.5      # the brief's "exactly the centre (60, 20) +- 0.5"
MAX_CENTRE_OF_20 = 5  # a 120x40 button, sd ~2.6 x 1.9 px: ~3% of correct clicks round to the centre

_spec = importlib.util.spec_from_file_location("click_tables", TABLES)
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)

# ---------------------------------------------------------------- pages
SCRIPT = """<script>
const L = {wheel: [], scroll: [], click: [], late: [], hooks: {rects: 0, clientLeft: 0}, selftest: null};
const o = document.getElementById('o');
// Main-world hooks for A7: the helper's geometry must never call these here.
const H = L.hooks, grc = Element.prototype.getClientRects, cl = Object.getOwnPropertyDescriptor(Element.prototype, 'clientLeft');
Element.prototype.getClientRects = function () { H.rects++; return grc.apply(this, arguments); };
Object.defineProperty(Element.prototype, 'clientLeft', {get() { H.clientLeft++; return cl.get.call(this); }, configurable: true});
document.body.getClientRects(); document.body.clientLeft;
L.selftest = [H.rects, H.clientLeft]; H.rects = 0; H.clientLeft = 0;  // the hooks count, then start from 0
let lastWheel = 0;
function sync() {
  L.scrollY = scrollY; L.vh = innerHeight; L.vw = innerWidth;
  const t = document.getElementById('t');
  if (t) { const r = t.getBoundingClientRect(); L.t = [r.top, r.height]; }
  o.textContent = JSON.stringify(L);
}
addEventListener('wheel', (e) => {
  const now = performance.now();
  // A5: the sticky header goes away at the first wheel after a >1.5 s pause, which only a
  // failed trial click (2 s timeout) followed by a corrective burst produces.
  const hdr = document.getElementById('hdr');
  if (hdr && lastWheel && now - lastWheel > 1500) { hdr.style.visibility = 'hidden'; L.late.push(now); }
  lastWheel = now;
  L.wheel.push([now, e.deltaY]); sync();
}, {capture: true, passive: true});
addEventListener('scroll', () => { L.scroll.push([performance.now(), scrollY]); sync(); });
// Clicks that reach the target (bubble phase). Playwright's trial click dispatches real events that its
// hit-target interceptor stops at window capture, so a bubble listener counts the clicks a page acts on;
// L.cap counts what an earlier-registered window capture listener sees (trial clicks included).
L.cap = 0;
addEventListener('click', (e) => { if (e.isTrusted) L.cap++; }, true);
document.addEventListener('click', (e) => {
  if (!e.isTrusted) return;
  L.click.push([e.offsetX, e.offsetY, e.target.id || e.target.className, performance.now(), scrollY]); sync();
});
setInterval(sync, 100); sync();
%s
</script>"""
BTN = "position:absolute;border:0;padding:0;"
# The brief's 40% header covers the oracle's landing band, but the helper stops at the first position
# where the whole target is visible (landing 0.23 and 0.69 of the viewport on the same build), so a header
# shorter than the viewport lets the trial pass half the time. This one covers every visible position.
HDR_H = "calc(100vh - 2px)"


def page(body, extra_js=""):
    return ("<!doctype html><meta charset=utf-8><style>body{margin:0}</style><pre id=o hidden></pre>"
            + body + (SCRIPT % extra_js)).encode()


PAGES = {
    "/a1": page(f'<button id=t style="{BTN}left:300px;top:200px;width:120px;height:40px"></button>'),
    "/a2": page(f'<div style="height:5000px"></div><button id=t style="{BTN}left:300px;top:3000px;width:120px;height:40px"></button>'),
    "/a3": page(f'<div style="height:10000px"></div><button id=t style="{BTN}left:300px;top:9000px;width:120px;height:40px"></button>'),
    # outer page cannot scroll; the button is 2000 px down inside a 300 px box that is narrower than
    # the wheel's random x (>= 10% of the viewport), so a wheel never reaches the box
    "/a4": page('<style>html,body{overflow:hidden;height:100%}</style>'
                '<div style="position:absolute;left:0;top:100px;width:60px;height:300px;overflow:auto">'
                f'<div style="position:relative;height:2200px"><button id=t style="{BTN}left:0;top:2000px;width:40px;height:20px"></button></div></div>'),
    "/a5": page(f'<div id=hdr style="position:sticky;top:0;height:{HDR_H};background:#c00;z-index:2"></div>'
                f'<div style="height:5000px"></div><button id=t style="{BTN}left:300px;top:3000px;width:120px;height:40px"></button>'),
    "/a6": page(f'<button class=dup style="{BTN}left:300px;top:100px;width:120px;height:40px"></button>'
                f'<button class=dup style="{BTN}left:300px;top:160px;width:120px;height:40px"></button>',
                f"setTimeout(() => {{ const b = document.createElement('button'); b.id = 'late'; "
                f"b.style.cssText = '{BTN}left:300px;top:240px;width:120px;height:40px'; document.body.append(b); }}, 1000);"),
}
PAGES["/b"] = PAGES["/a1"]
ROW_PAGE = {"A1": "/a1", "A2": "/a2", "A3": "/a3", "A4": "/a4", "A5": "/a5", "A6": "/a6", "A7": "/a1",
            "B1": "/a1", "B2": "/a1", "B3": "/a1", "B4": "/a1", "G1": "/a1", "stock-missing": "/a6"}


def serve():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = PAGES.get(self.path.split("?")[0])
            self.send_response(200 if body else 404)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body or b"")))
            self.end_headers()
            self.wfile.write(body or b"")

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_port}", srv


# ---------------------------------------------------------------- probes
PROBES = {
    "python": [PY, "-m", "camoucrome.probe", "--driver", "patchright", "--executable", EXE],
    "node": [NODE, NODE_PROBE, "--driver", f"{DRIVER_NODE}/package", "--label", "node", "--executable", EXE],
    "go": [GO_PROBE, "--driver-dir", DRIVER, "--label", "go", "--executable", EXE],
}


def run_probe(client, row, base):
    """-> (result dict or None, protocol-log text, why-not)."""
    env = dict(os.environ, DEBUG="pw:protocol", PLAYWRIGHT_NODEJS_PATH=NODE)
    for k in list(env):
        if k.startswith("CAMOU_CONFIG") or k.startswith("CAMOU_PRESET"):
            del env[k]
    cmd = PROBES[client] + ["--scenario", row, "--url", base + ROW_PAGE[row], "--config", CONFIG]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return None, "", f"probe did not run: {e}"
    try:
        res = json.loads(p.stdout)
        if "log" not in res:
            raise ValueError
    except ValueError:
        # origin/main probes have no --scenario: argparse/flag rejects it, or the sp6b flow runs instead
        return None, p.stderr, f"unknown scenario {row} (probe rc={p.returncode}): {(p.stderr or p.stdout)[-300:]!r}"
    return res, p.stderr, None


# ---------------------------------------------------------------- checks
def sdi(plog):
    return plog.count('"method":"DOM.scrollIntoViewIfNeeded"')


def centred(c):
    return abs(c[0] - 60) <= CENTRE_TOL and abs(c[1] - 20) <= CENTRE_TOL


def off_centre(clicks, n, tid="t"):
    """A1's criteria for n helper clicks: all on the button, more than one distinct
    point, and not (nearly) all at the centre."""
    pts = {(c[0], c[1]) for c in clicks}
    on = len(clicks) == n and all(c[2] == tid for c in clicks)
    cen = sum(centred(c) for c in clicks)
    ok = on and len(pts) > 1 and cen <= MAX_CENTRE_OF_20 * n // 20
    return ok, f"clicks={len(clicks)}/{n} on#{tid}={on} distinct={len(pts)} at_centre={cen} ids={sorted({c[2] for c in clicks})}"


def wheel_vs_scroll(log):
    s = sum(w[1] for w in log["wheel"])
    return abs(s - log["scrollY"]) <= 1, f"sum(deltaY)={s:g} scrollY={log['scrollY']:g} wheels={len(log['wheel'])}"


def one_click(log, tid="t"):
    return len(log["click"]) == 1 and log["click"][0][2] == tid, f"clicks={[c[2] for c in log['click']]}"


def both(*rs):
    return all(r[0] for r in rs), "; ".join(r[1] for r in rs)


def alive(plog):
    n = plog.count('"method":"')
    return n >= MIN_METHODS, f"protocol sends={n}"


def row_A1(client, res, plog, ctx):
    return off_centre(res["log"]["click"], 20)


def row_A2(client, res, plog, ctx):
    log = res["log"]
    frac = log["t"][0] / log["vh"]
    tol = 50 / log["vh"]  # a burst is whole 100 px notches: the planner's rounding
    # The helper stops at the first position where the whole element is visible, so the final
    # fraction lies between the oracle's shallowest landing (never scrolled past it) and the
    # bottom edge; measured 0.23 (the landing band) and 0.69 (stopped early) on the same build.
    lo, hi = T.LANDING[0], (log["vh"] - log["t"][1]) / log["vh"]
    return both(one_click(log), wheel_vs_scroll(log), alive(plog),
                (sdi(plog) == 0, f"DOM.scrollIntoViewIfNeeded={sdi(plog)}"),
                (len(log["wheel"]) >= 1 and lo - tol <= frac <= hi + 1e-6,
                 f"landing={frac:.3f} of vh={log['vh']} in [LANDING[0]={lo:.3f} -{tol:.3f}, fully visible {hi:.3f}] (oracle band [{lo:.3f},{T.LANDING[20]:.3f}])"))


def row_A3(client, res, plog, ctx):
    log = res["log"]
    sd = sum(w[1] for w in log["wheel"])
    return both(one_click(log), alive(plog),
                (len(log["wheel"]) == T.MAX_NOTCHES, f"wheel events={len(log['wheel'])} sum(deltaY)={sd:g} want {T.MAX_NOTCHES}"),
                (sdi(plog) >= 1, f"fallback click scrolled by the driver: DOM.scrollIntoViewIfNeeded={sdi(plog)}"))


def row_A4(client, res, plog, ctx):
    log = res["log"]
    w = len(log["wheel"])
    if client == "go":  # Go's geometry has no nested-scroller detection (spec 4, 2026-10-18): bounded by the no-progress stop
        bound = T.NO_PROGRESS_BURSTS * math.ceil(max(T.BURST))
        return both(one_click(log), (w <= bound, f"outer wheel events={w} <= {T.NO_PROGRESS_BURSTS} bursts x {math.ceil(max(T.BURST))} notches = {bound} (Go: no nested-scroller detection, no-progress stop)"))
    return both(one_click(log), (w == 0, f"outer wheel events={w}"))


def row_A5(client, res, plog, ctx):
    log = res["log"]
    ck = log["click"][0][3] if log["click"] else None
    late_before = bool(log["late"]) and ck is not None and log["late"][0] < ck
    return both(one_click(log), wheel_vs_scroll(log), alive(plog),
                (sdi(plog) == 0, f"DOM.scrollIntoViewIfNeeded={sdi(plog)}"),
                # a wheel after a >1.5 s pause can only follow a trial click that burned its 2 s timeout
                (len(log["late"]) == 1 and late_before, f"corrective bursts after the failed trial={len(log['late'])} before the click={late_before}"))


def row_A6(client, res, plog, ctx):
    log, ex, st = res["log"], res["extra"], ctx["stock"][client]
    ids = [c[2] for c in log["click"]]
    return both((ids == ["late"], f"late button clicked: {ids}"),
                (ex["missing"] is not None and "Timeout 500ms" in ex["missing"] and ex["missing"] == st["missing"],
                 f"missing-selector error == stock: {ex['missing'] == st['missing']} helper={str(ex['missing'])[:50]!r} stock={str(st['missing'])[:50]!r}"),
                (ex["strict"] is not None and "strict mode violation" in ex["strict"] and ex["strict"] == st["strict"],
                 f"strict-violation error == stock: {ex['strict'] == st['strict']} helper={str(ex['strict'])[:50]!r} stock={str(st['strict'])[:50]!r}"))


def row_A7(client, res, plog, ctx):
    log = res["log"]
    h = log["hooks"]
    return both((all(n >= 1 for n in log["selftest"]), f"hooks fire when called (self-test getClientRects/clientLeft)={log['selftest']}"),
                (h["rects"] == 0 and h["clientLeft"] == 0, f"main-world calls after 5 helper clicks: getClientRects={h['rects']} clientLeft={h['clientLeft']}"),
                (len(log["click"]) == 5, f"clicks={len(log['click'])}"))


def row_B1(client, res, plog, ctx):
    return both(off_centre(res["log"]["click"], 20), (res["wrapper_hits"] == 20, f"wrapper_hits={res['wrapper_hits']} want 20"))


def row_B2(client, res, plog, ctx):
    parts = []
    for key in ("direct", "plain"):
        cl = res["extra"][key]["click"]
        parts.append((len(cl) == 3 and all(centred(c) for c in cl), f"{key}: {[(c[0], c[1]) for c in cl]}"))
    return both(*parts, (res["wrapper_hits"] == 0, f"wrapper_hits={res['wrapper_hits']}"))


def row_B3(client, res, plog, ctx):
    cl = res["log"]["click"]
    return both((len(cl) == 2, f"clicks={len(cl)} (position, force; the trial dispatches none)"),
                (len(cl) == 2 and abs(cl[0][0] - 5) <= CENTRE_TOL and abs(cl[0][1] - 5) <= CENTRE_TOL, f"position click at {cl[0][:2] if cl else None} want (5, 5)"),
                (len(cl) == 2 and centred(cl[1]), f"force click at {cl[1][:2] if len(cl) > 1 else None} want the centre"),
                (res["wrapper_hits"] == 0, f"wrapper_hits={res['wrapper_hits']}"))


def row_B4(client, res, plog, ctx):
    ex = res["extra"]
    return both(*[(ex[k] is not None and "humanize:enabled" in ex[k], f"{k}: {str(ex[k])[:70]!r}") for k in ("nohumanize", "false")])


def row_G1(client, res, plog, ctx):
    cl = res["log"]["click"]
    return both(off_centre(cl[:20], 20), (len(cl) == 23 and all(centred(c) for c in cl[20:]), f"plain Click() at {[(c[0], c[1]) for c in cl[20:]]} want the centre"))


ROWS = [(c, r, f) for r, f in (("A1", row_A1), ("A2", row_A2), ("A3", row_A3), ("A4", row_A4), ("A5", row_A5),
                               ("A6", row_A6), ("A7", row_A7)) for c in ("python", "node", "go")]
ROWS += [(c, r, f) for r, f in (("B1", row_B1), ("B2", row_B2), ("B3", row_B3), ("B4", row_B4)) for c in ("python", "node")]
ROWS += [("go", "G1", row_G1)]


def main():
    assert len(ROWS) == EXPECTED, (len(ROWS), EXPECTED)
    base, srv = serve()
    stock = {}
    ran = passed = 0
    only = os.environ.get("ONLY")  # debugging: "A1:python,A5:go" runs those rows; the exit code is then 1
    for client, row, check in ROWS:
        if only and f"{row}:{client}" not in only.split(","):
            continue
        if row == "A6" and client not in stock:  # stock click() messages, the same probe with plain clicks
            res, _, why = run_probe(client, "stock-missing", base)
            stock[client] = res["extra"] if res and res["error"] is None else {"missing": None, "strict": None}
            if not res or res["error"]:
                print(f"note  {client} stock-missing did not run: {why or res['error']}")
        res, plog, why = run_probe(client, row, base)
        ran += 1
        if res is None:
            ok, note = False, why
        elif res["error"]:
            ok, note = False, f"probe error: {res['error'][:300]}"
        else:
            try:
                ok, note = check(client, res, plog, {"stock": stock})
            except (KeyError, TypeError, IndexError) as e:
                ok, note = False, f"malformed probe output: {e!r}"
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {row:3} {client:6} {note}", flush=True)
        if not ok and res and res.get("log") and res["log"].get("click"):
            print(f"      first clicks [offsetX, offsetY, id, t, scrollY]: {json.dumps(res['log']['click'][:4])}")
    srv.shutdown()
    print(f"{passed}/{ran} rows passed (expected {EXPECTED})")
    sys.exit(0 if ran == EXPECTED and passed == EXPECTED and not only else 1)


if __name__ == "__main__":
    main()

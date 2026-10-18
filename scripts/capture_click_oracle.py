"""SP2d oracle: how a real person clicks, against stock Chrome driven over CDP.

Arms (each writes baselines/human-click-2026-10/<arm>.json):
  mac --session N [--device mouse|trackpad]  the owner clicks in Chrome on the Mac
  win                                        the owner clicks in stock Chrome on the Windows host
  red                                        stock Chrome on the host clicked over CDP (must FAIL the gate)
The files hold clicks and scrolls only: no UA string, OS version, path or time
zone (public repo). Runs where winhost.py runs (win, red) or on the Mac (mac).
Importable core: knots, summarize, gate, pack_js_equivalent, unpack."""
import argparse
import base64
import gzip
import http.server
import json
import math
import pathlib
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

OUT = pathlib.Path(__file__).resolve().parent.parent / "baselines" / "human-click-2026-10"
CHROME_MAC = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
GRID_MS = 15.625

PAGE = """<!doctype html><meta charset=utf-8>
<body style="margin:0;font:14px sans-serif;user-select:none"><pre id=o style="position:fixed;right:8px;bottom:0;margin:0">0</pre><script>
const P = new URLSearchParams(window.PARAMS || location.search), N = +P.get('n') || 110, S = +P.get('s') || 0;
const SIZES = [16, 20, 24, 32, 40, 48, 64, 80, 96, 128, 160, 192, 224, 256, 288, 320];
const log = {clicks: [], scrolls: [], chrome_major: (navigator.userAgentData?.brands || [])
  .filter(b => b.brand === 'Google Chrome').map(b => +b.version)[0] || 0};
let cur = null, el = null;
const o = document.getElementById('o');
function next() {
  if (log.clicks.length >= N) return S ? scrollTask(0) : finish();
  const W = SIZES[Math.floor(Math.random() * SIZES.length)];
  el = document.createElement('div');
  Object.assign(el.style, {position: 'fixed', width: W + 'px', height: W + 'px', border: '1px solid #222',
    background: '#4a8', left: Math.random() * (innerWidth - W - 4) + 'px', top: Math.random() * (innerHeight - W - 4) + 'px'});
  setTimeout(() => { document.body.appendChild(el); const r = el.getBoundingClientRect();
    cur = {t_show: performance.now(), moves: [], rect: [r.left, r.top, r.width, r.height], size: W}; }, 500 + Math.random() * 1000);
}
addEventListener('pointermove', e => { if (cur) cur.moves.push([e.timeStamp, e.clientX, e.clientY,
  e.getCoalescedEvents().length, e.clientX % 1, e.clientY % 1]); }, {passive: true});
const rec = e => ({t: e.timeStamp, x: e.clientX, y: e.clientY, trusted: e.isTrusted,
  pointerType: e.pointerType || 'mouse', button: e.button, detail: e.detail});
addEventListener('pointerdown', e => { if (cur && e.target === el) cur.down = rec(e); });
addEventListener('pointerup', e => { if (cur && cur.down) { cur.up = rec(e); cur.moves = cur.moves.slice(-200);
  log.clicks.push(cur); cur = null; el.remove(); o.textContent = log.clicks.length + '/' + N; next(); } });
function scrollTask(i) {
  if (i >= S) return finish();
  scrollTo(0, 0);
  const pad = document.createElement('div'); pad.style.height = '6000px'; document.body.appendChild(pad);
  const t = document.createElement('button'); t.textContent = 'click me'; Object.assign(t.style,
    {position: 'absolute', top: '3000px', left: '40%', width: '160px', height: '48px'});
  document.body.appendChild(t);
  const s = {wheels: [], scrolls: [], vh: innerHeight};
  const w = e => s.wheels.push([e.timeStamp, e.deltaY, e.deltaMode]);
  const sc = () => s.scrolls.push([performance.now(), scrollY]);
  addEventListener('wheel', w, {passive: true}); addEventListener('scroll', sc, {passive: true});
  t.onclick = () => { s.landing = t.getBoundingClientRect().top / innerHeight;
    removeEventListener('wheel', w); removeEventListener('scroll', sc);
    log.scrolls.push(s); pad.remove(); t.remove(); scrollTask(i + 1); };
}
async function finish() {
  o.textContent = 'done';
  const raw = JSON.stringify(log);
  const gz = new Response(new Blob([raw]).stream().pipeThrough(new CompressionStream('gzip')));
  const b = new Uint8Array(await gz.arrayBuffer()); let s = ''; for (const c of b) s += String.fromCharCode(c);
  window.packed = btoa(s);
  window.done = true;  // after packed: a reader that sees done can read packed
  if (location.protocol === 'http:') fetch('/log', {method: 'POST', body: raw});
}
next();
</script>"""

WAIT_DONE = r"""
for ($i = 0; $i -lt 540; $i++) {
  Cdp-Send $ws @{ id = 100 + $i; method = "Runtime.evaluate"; params = @{ expression = "window.done === true"; returnByValue = $true } }
  $m = $null; for ($j = 0; $j -lt 10 -and -not ($m -and $m.Contains('"id":' + (100 + $i) + ',')); $j++) { $m = Cdp-Recv $ws 2000 }
  if ($m -and $m.Contains('"value":true')) { break }
  Start-Sleep -Seconds 1
}
"""

CDP_TIMEOUT_S = 540 + 120  # WAIT_DONE budget + Chrome startup/teardown margin; cdp_eval defaults to 180
RED_N = 40  # spec: 40 CDP clicks; the red page runs with n=RED_N so it finishes
RED_CLICKS = r"""
$id = 1000
for ($k = 0; $k -lt %d; $k++) {
  Start-Sleep -Milliseconds 1600   # the page shows the next target after 0.5-1.5 s
  Cdp-Send $ws @{ id = $id; method = "Runtime.evaluate"; params = @{ expression = "(() => { const e = [...document.querySelectorAll('div')].pop(); if (!e) return null; const r = e.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()"; returnByValue = $true } }
  $m = $null; for ($j = 0; $j -lt 10 -and -not ($m -and $m.Contains('"id":' + $id + ',')); $j++) { $m = Cdp-Recv $ws 2000 }
  $id++
  $pt = ($m | ConvertFrom-Json).result.result.value
  if (-not $pt) { continue }
  foreach ($t in "mouseMoved", "mousePressed", "mouseReleased") {
    Cdp-Send $ws @{ id = $id; method = "Input.dispatchMouseEvent"; params = @{ type = $t; x = $pt[0]; y = $pt[1]; button = "left"; clickCount = 1 } }
    for ($j = 0; $j -lt 10; $j++) { $m = Cdp-Recv $ws 2000; if ($m -and $m.Contains('"id":' + $id + ',')) { break } }
    $id++
  }
}
""" % RED_N + WAIT_DONE


def knots(values):
    v = sorted(values)

    def pct(p):
        k = (len(v) - 1) * p / 100
        lo = math.floor(k)
        return v[lo] + (v[min(lo + 1, len(v) - 1)] - v[lo]) * (k - lo)
    return [pct(p) for p in range(0, 100, 5)] + [pct(99)]


def _derive(c):
    hold = c["up"]["t"] - c["down"]["t"]
    before = [m for m in c["moves"] if m[0] <= c["down"]["t"]]
    dwell = c["down"]["t"] - before[-1][0] if before and c["down"]["t"] - before[-1][0] <= 1000 else None
    px, py = c["down"]["x"], c["down"]["y"]
    x, y, w, h = c["rect"]
    cx, cy = x + w / 2, y + h / 2
    ref = [m for m in before if 40 <= c["down"]["t"] - m[0] <= 200]
    ax, ay = 1.0, 0.0
    if ref:
        dx, dy = px - ref[0][1], py - ref[0][2]
        d = math.hypot(dx, dy)
        if d >= 1:
            ax, ay = dx / d, dy / d
    ox, oy = px - cx, py - cy
    after_show = [mv for mv in before if mv[0] >= c["t_show"]]
    fitts = None
    if after_show:  # distance from the first move after the target appeared, and the time to press
        fitts = [math.hypot(px - after_show[0][1], py - after_show[0][2]), c["size"], c["down"]["t"] - after_show[0][0]]
    return {"hold": hold, "dwell": dwell, "size": c["size"], "fitts": fitts,
            "along": ox * ax + oy * ay, "across": -ox * ay + oy * ax, "ox": ox, "oy": oy}


def ks(a, b):
    """Two-sample Kolmogorov-Smirnov statistic D (reported, not gated)."""
    a, b = sorted(a), sorted(b)
    i = j = 0
    d = 0.0
    while i < len(a) and j < len(b):
        if a[i] <= b[j]:
            i += 1
        else:
            j += 1
        d = max(d, abs(i / len(a) - j / len(b)))
    return d


def _fit(per_size):
    xs, ys = zip(*per_size)
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs) or 1.0
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return {"a": max(my - b * mx, 0.0), "b": max(b, 0.0)}


def gate(clicks, grid_check):
    if not clicks:
        return ["no clicks"]
    d = [_derive(c) for c in clicks]
    holds = [x["hold"] for x in d]
    dwells = [x["dwell"] for x in d if x["dwell"] is not None]
    problems = []
    if statistics.median(holds) < 20:
        problems.append(f"hold median {statistics.median(holds):.1f} ms < 20")
    if not dwells or statistics.median(dwells) < 20:
        problems.append(f"dwell median {statistics.median(dwells) if dwells else 0:.1f} ms < 20")
    if len({round(h, 1) for h in holds}) < 30:
        problems.append("fewer than 30 distinct hold values")
    if not all(c["down"]["pointerType"] == "mouse" and c["down"]["trusted"] for c in clicks):
        problems.append("a click is not a trusted mouse press")
    big = [x for x in d if x["size"] >= 48]
    if len(big) < 2 or statistics.pstdev([x["ox"] for x in big]) <= 1:
        problems.append("offset SD on targets >= 48 px is not above 1 px")
    if grid_check:
        on_grid = sum(1 for h in holds if abs(h - GRID_MS * round(h / GRID_MS)) <= 1)
        if on_grid / len(holds) >= 0.5:
            problems.append(f"{on_grid}/{len(holds)} holds on the 15.6 ms grid")
    return problems


def summarize(arms):
    mac = {k: v for k, v in arms.items() if k.startswith("mac-")}
    d, scrolls = [], []
    for name in sorted(mac):
        d += [_derive(c) for c in mac[name]["clicks"][10:]]
        scrolls += mac[name].get("scrolls", [])
    by_size = {}
    for x in d:
        by_size.setdefault(x["size"], []).append(x)
    pooled, carry = [], []
    for size in sorted(by_size):
        carry += by_size[size]
        if len(carry) >= 4:
            pooled.append(carry)
            carry = []
    if carry and pooled:
        pooled[-1] += carry
    off = {axis: _fit([(statistics.fmean(x["size"] for x in g), statistics.pstdev(x[axis] for x in g)) for g in pooled])
           for axis in ("along", "across")}
    off["xy_corr"] = statistics.correlation([x["ox"] for x in d], [x["oy"] for x in d]) if len(d) > 2 else 0.0
    holds = [x["hold"] for x in d]
    out = {"n_clicks": len(d), "n_sessions": len(mac),
           "hold_ms": knots(holds), "dwell_ms": knots([x["dwell"] for x in d if x["dwell"] is not None]),
           "offset": off, "lag1": statistics.correlation(holds[:-1], holds[1:]) if len(holds) > 3 else 0.0,
           "fitts": [x["fitts"] for x in d if x["fitts"]], "scroll": None, "win": None}
    if "win" in arms:
        w = [_derive(c) for c in arms["win"]["clicks"][10:]]
        moves = [mv for c in arms["win"]["clicks"] for mv in c["moves"]]
        out["win"] = {"n_clicks": len(w), "hold_ms": knots([x["hold"] for x in w]),
                      "ks_hold_vs_mac": ks([x["hold"] for x in w], holds),
                      "fractional_share": sum(1 for mv in moves if mv[4] or mv[5]) / max(len(moves), 1)}
    if scrolls:
        bursts, pauses = [], []
        for s in scrolls:
            ws = s["wheels"]
            groups = [[ws[0]]] if ws else []
            for a, b in zip(ws, ws[1:]):
                if b[0] - a[0] <= 150:
                    groups[-1].append(b)
                else:
                    pauses.append(b[0] - a[0])
                    groups.append([b])
            bursts += [max(1, round(sum(abs(e[1]) for e in g) / 100)) for g in groups]
        out["scroll"] = {"landing": knots([s["landing"] for s in scrolls]),
                         "burst": knots(bursts), "pause": knots(pauses or [200.0])}
    return out


def pack_js_equivalent(data):
    return base64.b64encode(gzip.compress(json.dumps(data).encode())).decode()


def unpack(packed):
    return json.loads(gzip.decompress(base64.b64decode(packed)))


def run_mac(n, s):
    done = threading.Event()
    box = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            box["log"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(204)
            self.end_headers()
            done.set()

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    prof = tempfile.mkdtemp(prefix="camou_click_")
    p = subprocess.Popen([CHROME_MAC, f"--user-data-dir={prof}", "--no-first-run", "--no-default-browser-check",
                          f"http://127.0.0.1:{srv.server_port}/?n={n}&s={s}"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        done.wait()  # no timeout; Ctrl-C aborts
    finally:
        p.kill()
        srv.shutdown()
        shutil.rmtree(prof, ignore_errors=True)
    return box["log"]


def run_cdp(params, act_ps):
    import winhost
    packed = winhost.cdp_eval(PAGE.replace("<body", "<script>window.PARAMS=%s</script><body" % json.dumps(params), 1),
                              expression="window.packed || ''", wait_ms=1000, window_style="Normal",
                              args=["--window-position=0,0", "--window-size=1280,900"], act_ps=act_ps, timeout=CDP_TIMEOUT_S)
    if not packed:
        sys.exit("page never produced a packed log (done not reached)")
    return unpack(packed)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("arm", choices=["mac", "win", "red"])
    ap.add_argument("--session", type=int, default=1, help="mac only: session number, file mac-s<N>.json")
    ap.add_argument("--device", choices=["mouse", "trackpad"], default="mouse", help="mac only")
    ap.add_argument("--n", type=int, default=110, help="mac only: clicks (win=50, red=%d fixed)" % RED_N)
    ap.add_argument("--s", type=int, default=5, help="mac only: scroll tasks")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.arm == "mac":
        log = run_mac(a.n, a.s)
        doc = {"platform": "mac", "chrome_major": log["chrome_major"], "device": a.device,
               "clicks": log["clicks"], "scrolls": log["scrolls"]}
        problems = gate(doc["clicks"][10:], grid_check=False)
        name = f"mac-s{a.session}.json"
    elif a.arm == "win":
        log = run_cdp("n=50&s=0", WAIT_DONE)
        doc = {"platform": "win", "chrome_major": log["chrome_major"], "clicks": log["clicks"], "scrolls": []}
        problems = gate(doc["clicks"][10:], grid_check=True)
        doc["gate"] = problems  # recorded, not fatal: the RDP timer grid is a finding
        name = "win.json"
    else:
        log = run_cdp(f"n={RED_N}&s=0", RED_CLICKS)
        doc = {"platform": "win", "chrome_major": log["chrome_major"], "clicks": log["clicks"], "scrolls": []}
        problems = gate(doc["clicks"], grid_check=True)
        doc["gate"] = problems
        name = "red.json"
    (OUT / name).write_text(json.dumps(doc))
    print(f"{name}: {len(doc['clicks'])} clicks, gate {'PASS' if not problems else 'FAIL'}")
    for p in problems:
        print("  -", p)
    if a.arm == "red" and not problems:
        sys.exit("red arm passed the gate: a gate that passes on CDP proves nothing")
    if a.arm == "mac" and problems:
        sys.exit(1)


if __name__ == "__main__":
    main()

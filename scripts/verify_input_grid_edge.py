"""Verifies input fixes I3 (device-pixel lattice, gated by input:deviceGrid) and I4 (humanize stays inside the viewport).

Driven over a raw websocket (Input and Runtime.evaluate only, no Runtime.enable), chrome headless at
--force-device-scale-factor=1.25, window 800x600 (IGE_WINDOW=WxH overrides). Every row is gated on the page's
devicePixelRatio == 1.25 and visualViewport.scale == 1, else UNMEASURED. Eight rows, each with its expected count; a row
that cannot run is UNMEASURED, never PASS; any non-PASS row exits 1.

  1 gate: no input:deviceGrid, humanize off: 30 awaited moves with fractional CSS px reach the page unchanged
    (clientX/clientY equal what was sent) -- an unconfigured build forwards the stock event.
  2 I3, key true, humanize off: 30 moves -> exactly 30 pointermoves, ONE fractional part of clientX*dpr per axis, and it
    is a lattice fraction (a multiple of .25 at dsf 1.25: frac(-dsf*o) for an integer DIP view origin o).
  3 I3, key true, humanize on: 3 long moves -> >= 30 pointermoves, the same lattice fraction per axis as row 2 (the path's
    interior is on the end point's lattice).
  4 I4 (a), the Blink half, humanize off, no key: a CDP move to (-0.5, ih/2) after one inside -> exactly one pointermove
    with clientX -0.5 and one mousemove with clientX -1: a point in (-1, 0) reaches the page.
  5 I4 (b), key true, humanize on, 50 legs x = +3 <-> x = -3: 0 pointermove/mousemove/pointerover/mouseover outside
    [0, innerWidth) x [0, innerHeight), exits == 50 (outbound legs), pointerover re-enters == 50 (return legs).
  6 I4 guard: 4 edge legs (centre -> 40 px past each edge): 0 outside events, >= 20 pointermoves seen.
  9 = row 5 with no input:deviceGrid (raw interior points).
  7 I4 exit signature: each of those 4 legs ends pointerout,pointerleave,mouseout,mouseleave, relatedTarget null.
  8 I3 right edge, key true, a window whose innerWidth has a point just inside the edge that the plain snap puts outside
    (iw 803: 802.9 -> 803.2): the page gets the lattice point one step inside (802.4), and no exit.

Row 2 also asserts the modal fractions from the page's own geometry: in this headless window the content sits at
(ow - iw) / 2 across and oh - ih down in its root window, so frac(clientX*dpr) = frac(-dsf*(ow-iw)/2) and
frac(clientY*dpr) = frac(-dsf*(oh-ih)) (measured 2026-11-21: 143 down -> .25, 0 across -> 0). An origin-blind snap gives 0 on
both and FAILs.

RED-capable: 1 (a build that snaps without the key), 2 and 3 (no snap, or an origin-blind one), 8 (no keep-inside), 9 (the old
PointIsWithinContents test lets raw x in (-1, 0) through; 5 passes on the old test too, because the lattice zero is exact). 4 is a guard of the Blink half and
passes before and after; 6 and 7 are guards. What this cannot see: W vs innerWidth, the window frame and the view's
origin in its window on Windows -- the host rerun only. The inline page replaces scripts/input_probe/page.html.

Pure checks: `--self-test`.

Box command (clean env, chrome from CAMOU_OUT):
  ~/camoucrome-verify/venv/bin/python3 scripts/verify_input_grid_edge.py
"""
import contextlib
import json
import os
import random
import statistics
import sys
import time
import urllib.parse

import verify_sp2e as base

DSF = 1.25
FLAGS = ["--remote-allow-origins=*", "--enable-logging=stderr", "--force-device-scale-factor=%s" % DSF,
         "--window-size=" + os.environ.get("IGE_WINDOW", "800,600")]
HUM = {"humanize:enabled": True, "humanize:minTime": 80, "humanize:maxTime": 250}  # long paths: many frames, many events
HUM_GRID = {**HUM, "input:deviceGrid": True}
HUM_CROSS_RAW = {"humanize:enabled": True, "humanize:minTime": 40, "humanize:maxTime": 80}  # 100 legs, unsnapped points
HUM_CROSS = {**HUM_CROSS_RAW, "input:deviceGrid": True}
GRID = {"input:deviceGrid": True}
EPS = 0.02  # device px: float noise of x*dpr

PAGE = ("<!doctype html><body style='margin:0;height:3000px'><script>"
        "window.__log=[];"
        "const P=['pointermove','mousemove','pointerover','mouseover','pointerout','mouseout'];"
        "const L=['pointerleave','mouseleave'];"
        "const rec=e=>__log.push({t:e.type,x:e.clientX,y:e.clientY,rt:e.relatedTarget===null});"
        "for(const t of P)addEventListener(t,rec,{capture:true,passive:true});"
        "for(const t of L)document.addEventListener(t,e=>{if(e.target===document.documentElement)rec(e)},true);"
        "</script>")

results, notes = {}, []
R1 = "1 gate: no key, humanize off: fractional CSS px reach the page unchanged"
R2 = "2 I3 key, humanize off: 30 moves, one lattice fraction per axis"
R3 = "3 I3 key, humanize on: >= 30 pointermoves on the same lattice"
R4 = "4 I4a humanize off: a move to x = -0.5 gives one pointermove at -0.5 and one mousemove at -1"
R5 = "5 I4b humanize: 50 crossings of x = 0, 0 outside events, 50 exits, 50 re-enters"
R6 = "6 I4 guard: 4 edge legs, 0 outside events, >= 20 pointermoves seen"
R7 = "7 I4 exit: 4 exits, each pointerout,pointerleave,mouseout,mouseleave, relatedTarget null"
R8 = "8 I3 right edge: a point inside the edge whose plain snap is outside lands one lattice step inside"
R9 = "9 I4b humanize, no key: 50 crossings of x = 0 with raw interior points, 0 outside events, 50 exits, 50 re-enters"
ROWS = [R1, R2, R3, R4, R5, R6, R7, R8, R9]
EXIT = ["pointerout", "pointerleave", "mouseout", "mouseleave"]


def circ(a, b):
    d = abs(a - b) % 1.0
    return min(d, 1 - d)


def fractions(vals, dpr):
    """(share of values off the axis's modal fractional device-pixel part, that modal part in [0, 1))."""
    fr = [(v * dpr) % 1.0 for v in vals]
    mode = statistics.mode(round(f, 3) for f in fr)
    return sum(circ(f, mode) > EPS for f in fr) / len(fr), mode % 1.0


def lattice_fraction(mode, dsf=DSF):
    """A view at integer DIP origin o has clientX*dpr fractions frac(-dsf*o): at 1.25 a multiple of .25."""
    return any(circ(mode, k * 0.25) <= EPS for k in range(4)) if dsf == 1.25 else True


def outside(events, iw, ih):
    kinds = ("pointermove", "mousemove", "pointerover", "mouseover")
    return [e for e in events if e["t"] in kinds and not (0 <= e["x"] < iw and 0 <= e["y"] < ih)]


def exits(events):
    """The type sequences ending at each relatedTarget-null mouseleave."""
    out = []
    for i, e in enumerate(events):
        if e["t"] == "mouseleave" and e["rt"]:
            j = i
            while j > 0 and events[j - 1]["t"] in EXIT:
                j -= 1
            out.append(([x["t"] for x in events[j:i + 1]], e["rt"]))
    return out


def self_test():
    off, mode = fractions([100.0, 108.8, 117.6], 1.25)
    assert off == 0.0 and mode == 0.0
    off, mode = fractions([100.37, 108.8, 117.6, 120.1], 1.25)
    assert off > 0.0
    _, m = fractions([(k + 0.25) / 1.25 for k in range(1, 20)], 1.25)  # a view origin of 87: .25
    assert abs(m - 0.25) < 1e-3 and lattice_fraction(m) and not lattice_fraction(0.1)
    ev = [{"t": "pointermove", "x": 5, "y": 5, "rt": False}, {"t": "pointermove", "x": 800, "y": 5, "rt": False},
          {"t": "pointerout", "x": 900, "y": 5, "rt": False}, {"t": "mousemove", "x": -0.3, "y": 5, "rt": False}]
    assert len(outside(ev, 800, 600)) == 2  # x == iw and x in (-1, 0) are outside; an out event is not a move
    seq = [{"t": t, "x": 0, "y": 0, "rt": True} for t in EXIT]
    assert exits(seq) == [(EXIT, True)]
    assert exits(seq[:3]) == []


@contextlib.contextmanager
def browser(config, window=None):
    import lib_shell
    flags = FLAGS if window is None else FLAGS[:-1] + ["--window-size=" + window]
    proc, primed = lib_shell.launch_and_prime(
        lambda: lib_shell.launch(json.dumps(config) if config else None, shell=lib_shell.CHROME,
                                 extra_flags=lib_shell.CHROME_FLAGS + flags), prime_page)
    proc.primed = primed
    try:
        yield proc
    finally:
        lib_shell.shutdown(proc)


def prime_page(proc):
    t = next(t for t in base.targets(proc) if t.get("type") == "page")
    c = base.Cdp(t["webSocketDebuggerUrl"])
    c.call("Page.navigate", {"url": "data:text/html," + urllib.parse.quote(PAGE)})
    end = time.monotonic() + 10
    while base.ev(c, "typeof window.__log") != "object":
        if time.monotonic() > end:
            raise RuntimeError("page did not load")
        time.sleep(0.1)
    base.move(c, 100.0, 200.0)  # a move needs a known previous position to be humanized
    time.sleep(0.3)
    base.ev(c, "window.__log = []")
    return c, t["id"]


def meta(c):
    m = base.ev(c, "({dpr: devicePixelRatio, iw: innerWidth, ih: innerHeight, ow: outerWidth, oh: outerHeight, scale: visualViewport.scale})")
    if m["dpr"] != DSF or m["scale"] != 1:
        raise RuntimeError("UNMEASURED: devicePixelRatio %s, page scale %s (need %s and 1)" % (m["dpr"], m["scale"], DSF))
    return m


def take(c, kinds):
    ev = base.log(c)
    base.ev(c, "window.__log = []")
    return [e for e in ev if e["t"] in kinds]


def rnd_points(rng, n):
    return [(rng.uniform(50, 700) + 0.37, rng.uniform(50, 400) + 0.61) for _ in range(n)]


def judge(name, ok, note):
    results[name] = "PASS" if ok else "FAIL"
    print("      %s" % note)


def unmeasured(names, exc):
    for n in names:
        results[n] = "UNMEASURED"
    notes.append("%s: %r" % (", ".join(n.split()[0] for n in names), exc))


def run_moves(config, pts):
    with browser(config) as proc:
        c, _ = base.open_page(proc)
        m = meta(c)
        for x, y in pts:
            base.move(c, x, y)
        time.sleep(0.3)
        return m, take(c, ("pointermove",))


def grid_rows():
    rng = random.Random(7)
    pts = rnd_points(rng, 30)
    try:
        m, pm = run_moves(None, pts)
    except Exception as exc:  # noqa: BLE001
        unmeasured([R1], exc)
    else:
        same = len(pm) == 30 and all(abs(e["x"] - x) < 1e-3 and abs(e["y"] - y) < 1e-3 for e, (x, y) in zip(pm, pts))
        judge(R1, same, "row1 n=%d first sent %s got %s" % (len(pm), pts[0], (pm[0]["x"], pm[0]["y"]) if pm else None))
    frac = None
    try:
        m, pm = run_moves(GRID, pts)
    except Exception as exc:  # noqa: BLE001
        unmeasured([R2], exc)
    else:
        (ox, fx), (oy, fy) = fractions([e["x"] for e in pm], m["dpr"]), fractions([e["y"] for e in pm], m["dpr"])
        frac = (fx, fy)
        ex, ey = (-DSF * (m["ow"] - m["iw"]) / 2) % 1.0, (-DSF * (m["oh"] - m["ih"])) % 1.0
        judge(R2, len(pm) == 30 and ox == 0 and oy == 0 and circ(fx, ex) <= EPS and circ(fy, ey) <= EPS,
              "row2 n=%d dpr=%s off_share x=%.2f y=%.2f modal fraction x=%.3f y=%.3f, from the page's geometry x=%.3f y=%.3f" % (
                  len(pm), m["dpr"], ox, oy, fx, fy, ex, ey))
    try:
        m, pm = run_moves(HUM_GRID, [(600.37, 150.61), (200.37, 380.61), (650.37, 350.61)])
    except Exception as exc:  # noqa: BLE001
        unmeasured([R3], exc)
    else:
        (ox, fx), (oy, fy) = fractions([e["x"] for e in pm], m["dpr"]), fractions([e["y"] for e in pm], m["dpr"])
        judge(R3, len(pm) >= 30 and ox == 0 and oy == 0 and frac is not None and circ(fx, frac[0]) <= EPS and circ(fy, frac[1]) <= EPS,
              "row3 n=%d off_share x=%.2f y=%.2f modal fraction x=%.3f y=%.3f (row 2: %s)" % (len(pm), ox, oy, fx, fy, frac))


def blink_half_row():
    try:
        with browser(None) as proc:
            c, _ = base.open_page(proc)
            m = meta(c)
            base.move(c, 300.0, m["ih"] / 2)
            time.sleep(0.2)
            take(c, ("pointermove",))
            base.move(c, -0.5, m["ih"] / 2)
            time.sleep(0.3)
            ev = base.log(c)
    except Exception as exc:  # noqa: BLE001
        unmeasured([R4], exc)
        return
    pm = [e for e in ev if e["t"] == "pointermove" and e["x"] < 0]
    mm = [e for e in ev if e["t"] == "mousemove" and e["x"] < 0]
    judge(R4, len(pm) == 1 and abs(pm[0]["x"] + 0.5) < 1e-3 and len(mm) == 1 and mm[0]["x"] == -1,
          "row4 pointermove<0 %s mousemove<0 %s" % ([e["x"] for e in pm], [e["x"] for e in mm]))


def crossing_row(config, name):
    try:
        with browser(config) as proc:
            c, _ = base.open_page(proc)
            m = meta(c)
            y = float(round(m["ih"] / 2))
            base.move(c, 3.0, y)
            time.sleep(0.2)
            take(c, ("pointermove",))
            base.ev(c, "window.__log = []")
            for _ in range(50):
                base.move(c, -3.0, y)
                base.move(c, 3.0, y)
            time.sleep(0.4)
            ev = base.log(c)
    except Exception as exc:  # noqa: BLE001
        unmeasured([name], exc)
        return
    out = outside(ev, m["iw"], m["ih"])
    left = [e for e in out if e["x"] < 0]
    ex = [s for s, rt in exits(ev) if s == EXIT and rt]
    overs = [e for e in ev if e["t"] == "pointerover"]
    judge(name, not out and len(ex) == 50 and len(overs) == 50,
          "row5/9 outside=%d (left %d, values %s) exits=%d pointerovers=%d" % (
              len(out), len(left), sorted({round(e["x"], 2) for e in out})[:6], len(ex), len(overs)))


def right_edge_row():
    """A point just inside the right edge whose plain lattice snap lands at or past it (iw 803: 802.9 -> 803.2). innerWidth
    follows the window width unevenly, so launch widths until one has such a point; none within the range is UNMEASURED."""
    ev = m = want = None
    try:
        for width in range(796, 812):
            with browser(GRID, window="%d,600" % width) as proc:
                c, _ = base.open_page(proc)
                m = meta(c)
                ox = (m["ow"] - m["iw"]) / 2
                v = m["iw"] - 0.1
                plain = round((v + ox) * DSF) / DSF - ox
                if plain < m["iw"]:
                    continue
                want = plain - 1 / DSF  # one lattice step inside
                y = float(round(m["ih"] / 2))
                base.move(c, 300.0, y)
                time.sleep(0.2)
                take(c, ("pointermove",))
                base.ev(c, "window.__log = []")
                base.move(c, v, y)
                time.sleep(0.3)
                ev = base.log(c)
                break
        if ev is None:
            raise RuntimeError("UNMEASURED: no window width 796..811 has a point inside the right edge that snaps out")
    except Exception as exc:  # noqa: BLE001
        unmeasured([R8], exc)
        return
    pm = [e for e in ev if e["t"] == "pointermove"]
    judge(R8, len(pm) == 1 and abs(pm[0]["x"] - want) < 1e-3 and not outside(ev, m["iw"], m["ih"]) and not exits(ev),
          "row8 iw=%s sent %.1f want %.1f got %s" % (m["iw"], m["iw"] - 0.1, want, [e["x"] for e in pm]))


def edge_rows():
    try:
        with browser(HUM_GRID) as proc:
            c, _ = base.open_page(proc)
            m = meta(c)
            w, h = m["iw"], m["ih"]
            cx, cy = w / 2, h / 2
            for tx, ty in [(w + 40, cy), (-40, cy), (cx, h + 40), (cx, -40)]:
                base.move(c, cx, cy)
                time.sleep(0.2)
                base.move(c, tx, ty)
                time.sleep(0.3)
            ev = take(c, ("pointermove", "mousemove", "pointerover", "mouseover", "pointerout", "mouseout",
                          "pointerleave", "mouseleave"))
    except Exception as exc:  # noqa: BLE001
        unmeasured([R6, R7], exc)
        return
    out = outside(ev, m["iw"], m["ih"])
    moves = [e for e in ev if e["t"] == "pointermove"]
    judge(R6, len(moves) >= 20 and not out,
          "row6 pointermoves=%d iw=%s ih=%s outside=%d %s" % (len(moves), m["iw"], m["ih"], len(out), out[:6]))
    ex = exits(ev)
    judge(R7, len(ex) == 4 and all(s == EXIT and rt for s, rt in ex), "row7 exits=%s" % ex)


def main():
    if sys.argv[1:2] == ["--self-test"]:
        self_test()
        print("self-test ok")
        return 0
    grid_rows()
    blink_half_row()
    crossing_row(HUM_CROSS, R5)
    crossing_row(HUM_CROSS_RAW, R9)
    edge_rows()
    right_edge_row()
    for r in ROWS:
        print("%-10s %s" % (results.get(r, "UNMEASURED"), r))
    for n in notes:
        print("      " + n)
    return 0 if all(results.get(r) == "PASS" for r in ROWS) else 1


if __name__ == "__main__":
    sys.exit(main())

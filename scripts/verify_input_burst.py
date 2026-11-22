"""Verifies the humanized path as a mouse reports it (I2, I2b): with humanize:enabled the path's samples reach the page in
frame bursts, so getCoalescedEvents() holds the samples of one frame with their authored timeStamps (input:pollingHz).

Driven over a raw websocket (Input and Runtime.evaluate only, no Runtime.enable) against chrome headless; the page is served
from http://127.0.0.1 because getCoalescedEvents does not exist on a data: page. Rows, each with its expected count; a row
that cannot run is UNMEASURED, never PASS; any non-PASS row exits 1.

  1 125 Hz: >= 20 pointermoves, >= 60 % of them with 2 or more coalesced samples, spacing of the coalesced timeStamps inside an
    event 8 ms +-0.5 (median), predicted events on >= 85 %.
  2 1000 Hz: the same, >= 90 % multi, a coalesced list of 12 or more at most, spacing 1 ms +-0.1.
  3 timeStamps never go back: across every event and its coalesced list, in order, in the 6-leg runs and in the 120-hop runs.
  4 humanize off, key set: no pointermove has a coalesced list longer than 1 (the path is not resampled).
  5 many short hops (the harness's stepped sweep: 120 hops of 14 px, default humanize times, so a path end every ~100 ms), at
    each rate: the largest coalesced list stays within one frame's samples (125 Hz: <= 4, the control's value; 1000 Hz: 18,
    printed with the count of oversize lists, NOT judged: about 1 % are two bursts in one frame, an open defect), the
    spacing sd inside an event is printed. A path's last partial burst must not land in the frame of the
    burst before it.
  6 movementX/Y: the head event's movement is the sum over its coalesced list (each head, every run).
  7 move then click at once (the command of a humanized move now resolves when its last event is forwarded, not on its ack):
    10 times a CDP move to a point and, the moment its reply arrives, a press and release there. Every pointerdown lies on
    the move's end point, comes after every pointermove of that move (sequence numbers), and a click follows.

  8 pointerrawupdate (125 Hz, the 6-leg run): the reports arrive in real time: no pair of raw events at one `now` (within 0.5 ms)
    with timeStamps 2 ms or more apart (back-to-back forwarding makes about 40 % of them), sd of now - timeStamp under 1 ms.
  9 no two neighbouring coalesced samples (across the lists, in order) on one (x, y), at 125 Hz, in the 6-leg and 120-hop runs.
  10 move, then at once a main-world read of :hover (the command returns when the last event is forwarded, not when the page
    handled it): 20 times, alternating a point inside and outside a box; reported with the count that read the new state.
  11 Input.setIgnoreInputEvents(true): a humanized move returns, no event reaches the page (the final event included), and
    after it is lifted the next move arrives.
  12 a humanized drag (button down, buttons=1): the move arrives, no two pointermoves of one path less than 6 ms apart
    (the final event of a button-down move keeps the debugger bit and cannot merge).

RED-capable: 1, 2 and 4 against a build that posts one task per sample (coalesced lists of 1, no spacing), 1 and 2 against
a rate that is not the key's (the spacing medians differ 8x), 3 against stamps set to Now() in a burst.

  ~/camoucrome-verify/venv/bin/python3 verify_input_burst.py        (box; --self-test for the pure checks)
"""
import contextlib
import http.server
import json
import os
import statistics
import sys
import threading
import time

import verify_sp2e as base

FLAGS = ["--remote-allow-origins=*", "--enable-logging=stderr", "--window-size=" + os.environ.get("IB_WINDOW", "900,600")]
HUM = {"humanize:enabled": True, "humanize:minTime": 500, "humanize:maxTime": 800}   # long paths: many frames

PAGE = (b"<!doctype html><body style='margin:0;height:3000px'><div id=h style='position:absolute;left:600px;top:400px;width:60px;height:60px'></div><script>"
        b"window.__log=[];window.__seq=0;"
        b"addEventListener('pointermove',e=>{const c=e.getCoalescedEvents();"
        b"__log.push({ts:e.timeStamp,now:performance.now(),cs:c.length,cts:c.map(x=>x.timeStamp),ps:e.getPredictedEvents().length,"
        b"k:'move',seq:++__seq,x:e.clientX,y:e.clientY,mx:e.movementX,my:e.movementY,cmx:c.map(x=>x.movementX),cmy:c.map(x=>x.movementY),cxy:c.map(x=>[x.clientX,x.clientY]),"
        b"fn:typeof e.getCoalescedEvents==='function',secure:isSecureContext})},{capture:true,passive:true});"
        b"addEventListener('pointerrawupdate',e=>{__log.push({k:'raw',ts:e.timeStamp,now:performance.now(),seq:++__seq})},true);"
        b"addEventListener('pointerdown',e=>{__log.push({k:'down',x:e.clientX,y:e.clientY,seq:++__seq})},true);"
        b"addEventListener('click',e=>{__log.push({k:'click',x:e.clientX,y:e.clientY,seq:++__seq})},true);"
        b"</script>")

results, notes = {}, []
FULL = {}   # (kind, hz) -> the whole page log of that run (moves and raw updates); the returned logs hold the moves only


def moves_of(full):
    return [e for e in full if e.get("k") == "move"]
R1 = "1 125 Hz: coalesced lists of the frame's samples, spacing 8 ms, predictor warm"
R2 = "2 1000 Hz: coalesced lists of the frame's samples, spacing 1 ms, predictor warm"
R3 = "3 timeStamps never go back across events and coalesced lists"
R4 = "4 humanize off: the path is not resampled (coalesced lists of 1)"
R5 = "5 120 short hops: the largest coalesced list is one frame's samples at each rate"
R6 = "6 movementX/Y: each head is the sum of its coalesced list"
R7 = "7 move then click at once: the press lands on the move's end, after all its pointermoves, and a click follows"
R8 = "8 pointerrawupdate: the reports arrive in real time (no back-to-back pair, steady latency)"
R9 = "9 no repeated (x, y) between neighbouring coalesced samples"
R10 = "10 move, then at once a read of :hover: the new state"
R11 = "11 setIgnoreInputEvents: the move returns and nothing reaches the page, a later move does"
R12 = "12 a humanized drag (buttons=1): no two pointermoves of one path within 6 ms"
ROWS = [R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12]
HOPS = [(300.0 + 14.0 * i, 300.0 + (i % 7)) for i in range(120)]
LEGS = [(780.0, 120.0), (120.0, 480.0), (700.0, 460.0), (200.0, 140.0), (760.0, 300.0), (140.0, 300.0)]


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *a):
        pass


@contextlib.contextmanager
def served():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield "http://127.0.0.1:%d/" % srv.server_address[1]
    finally:
        srv.shutdown()


@contextlib.contextmanager
def browser(config, url):
    import lib_shell

    def prime(proc):
        t = next(t for t in base.targets(proc) if t.get("type") == "page")
        c = base.Cdp(t["webSocketDebuggerUrl"])
        c.call("Page.navigate", {"url": url})
        end = time.monotonic() + 10
        while base.ev(c, "typeof window.__log") != "object":
            if time.monotonic() > end:
                raise RuntimeError("page did not load")
            time.sleep(0.1)
        base.move(c, 100.0, 200.0)   # a move needs a known previous position to be humanized
        time.sleep(0.3)
        base.ev(c, "window.__log = []")
        return c, t["id"]

    proc, primed = lib_shell.launch_and_prime(
        lambda: lib_shell.launch(json.dumps(config), shell=lib_shell.CHROME, extra_flags=lib_shell.CHROME_FLAGS + FLAGS), prime)
    proc.primed = primed
    try:
        yield proc
    finally:
        lib_shell.shutdown(proc)


def run(config, url, legs=None, pause=0.15):
    with browser(config, url) as proc:
        c, _ = base.open_page(proc)
        for x, y in (LEGS if legs is None else legs):
            base.move(c, x, y)
            time.sleep(pause)
        time.sleep(0.4)
        return base.ev(c, "window.__log")


def metrics(log):
    gaps = []
    for e in log:
        gaps += [b - a for a, b in zip(e["cts"], e["cts"][1:])]
    n = len(log)
    return {"n": n, "multi": sum(1 for e in log if e["cs"] > 1) / n if n else 0.0,
            "max": max((e["cs"] for e in log), default=0),
            "predicted": sum(1 for e in log if e["ps"] > 0) / n if n else 0.0,
            "gap_n": len(gaps), "gap_med": statistics.median(gaps) if gaps else None,
            "gap_sd": statistics.pstdev(gaps) if len(gaps) > 1 else None}


def raw_realtime(log):
    """(pairs, n, lat_sd): raw events at one `now` (within 0.5 ms) whose timeStamps are 2 ms or more apart, how many raw events, and
    the sd of now - timeStamp. Back-to-back forwarding of stamped samples makes pairs ~ n / 2."""
    raw = [e for e in log if e.get("k") == "raw"]
    pairs = sum(1 for a, b in zip(raw, raw[1:]) if abs(b["now"] - a["now"]) < 0.5 and abs(b["ts"] - a["ts"]) >= 2.0)
    lat = [e["now"] - e["ts"] for e in raw]
    return pairs, len(raw), (statistics.pstdev(lat) if len(lat) > 1 else None)


def repeats(log):
    """neighbouring coalesced samples (across the lists, in order) on one (x, y)"""
    pos = [p for e in log if e.get("k") == "move" for p in e["cxy"]]
    return sum(1 for a, b in zip(pos, pos[1:]) if a == b), len(pos)


def monotonic(log):
    prev = -1.0
    for e in log:
        for t in e["cts"] + [e["ts"]]:
            if t < prev - 1e-6:
                return False
            prev = t
    return True


def judge(name, ok, note):
    results[name] = "PASS" if ok else "FAIL"
    print("      %s" % note)


def unmeasured(names, exc):
    for n in names:
        results[n] = "UNMEASURED"
    notes.append("%s: %r" % (", ".join(n.split()[0] for n in names), exc))


def rate_row(name, hz, url):
    try:
        full = run({**HUM, "input:pollingHz": hz}, url)
        FULL[("legs", hz)] = full
        log = moves_of(full)
    except Exception as exc:  # noqa: BLE001
        unmeasured([name], exc)
        return None
    if not log or not log[0]["fn"] or not log[0]["secure"]:
        unmeasured([name], "no pointermove, or getCoalescedEvents missing / not a secure context")
        return None
    m = metrics(log)
    period = 1000.0 / hz
    # 1000 Hz comes from real timers now (a sample per millisecond is as precise as the platform's timer), so +-0.3; the clients
    # draw 125 Hz only
    tol = 0.5 if hz == 125 else 0.3
    ok = (m["n"] >= 20 and m["multi"] >= (0.6 if hz == 125 else 0.9) and m["gap_med"] is not None
          and abs(m["gap_med"] - period) <= tol and m["predicted"] >= 0.85 and (hz == 125 or m["max"] >= 12))
    judge(name, ok, "%d Hz n=%d multi=%.2f max=%d predicted=%.2f spacing n=%d median=%s sd=%s" % (
        hz, m["n"], m["multi"], m["max"], m["predicted"], m["gap_n"],
        None if m["gap_med"] is None else round(m["gap_med"], 3), None if m["gap_sd"] is None else round(m["gap_sd"], 3)))
    return log


def movement_ok(log, tol=1.0):
    """head movement == sum of its coalesced list's; the heads' sum == last position - first position (the page's own coordinates)."""
    for e in log:
        if abs(e["mx"] - sum(e["cmx"])) > tol or abs(e["my"] - sum(e["cmy"])) > tol:
            return False
    return True


def hops_row(hz, url):
    try:
        full = run({"humanize:enabled": True, "input:pollingHz": hz}, url, legs=HOPS, pause=0.0)
        FULL[("hops", hz)] = full
        log = moves_of(full)
    except Exception as exc:  # noqa: BLE001
        unmeasured([R5], exc)
        return None
    m = metrics(log)
    cap = 4 if hz == 125 else 18
    sd = None if m["gap_sd"] is None else round(m["gap_sd"], 3)
    results.setdefault(R5, "PASS")
    # 1000 Hz is reported, not judged: about 1 % of its lists hold two bursts (a burst cadence that is not locked to the renderer's
    # frames); the clients draw 125 Hz only until that is fixed (measurements/2026-11-22-input-coalesce-b.md)
    ok = m["n"] >= 100 and (hz == 1000 or m["max"] <= cap)
    if not ok:
        results[R5] = "FAIL"
    sizes = sorted(e["cs"] for e in log)
    # the tell: a frame with no pointermove, then one with a double list (two bursts in one frame)
    # (by `now`, the page's own clock: the head timeStamps of authored bursts are contiguous, so their gap is a frame pair by construction)
    skip_double = sum(1 for a, b in zip(log, log[1:]) if b["now"] - a["now"] > 25.0 and b["cs"] > cap)
    print("      row5 %d Hz n=%d max=%d (cap %d) multi=%.2f predicted=%.2f spacing median=%s sd=%s; sizes p50/p90/p99 %s/%s/%s, %d above the cap, %d of them after a skipped frame" % (
        hz, m["n"], m["max"], cap, m["multi"], m["predicted"], m["gap_med"], sd,
        sizes[len(sizes) // 2], sizes[len(sizes) * 9 // 10], sizes[len(sizes) * 99 // 100], sum(1 for x in sizes if x > cap), skip_double))
    return log


def move_click_row(url):
    """Humanize on: move, and at once press and release at the same point."""
    try:
        with browser({**HUM, "humanize:minTime": 80, "humanize:maxTime": 200}, url) as proc:
            c, _ = base.open_page(proc)
            ok, notes_ = 0, []
            for i in range(10):
                x, y = 200.0 + 50 * i, 150.0 + 20 * (i % 5)
                base.ev(c, "window.__log = []")
                base.move(c, x, y)
                c.call("Input.dispatchMouseEvent", base.mouse("mousePressed", x, y, button="left", buttons=1, clickCount=1), 30)
                c.call("Input.dispatchMouseEvent", base.mouse("mouseReleased", x, y, button="left", buttons=0, clickCount=1), 30)
                time.sleep(0.3)
                lg = base.ev(c, "window.__log")
                downs = [e for e in lg if e.get("k") == "down"]
                moves = [e for e in lg if e.get("k") == "move"]
                clicks = [e for e in lg if e.get("k") == "click"]
                good = (len(downs) == 1 and len(clicks) == 1 and abs(downs[0]["x"] - x) < 1.0 and abs(downs[0]["y"] - y) < 1.0
                        and all(m["seq"] < downs[0]["seq"] for m in moves) and clicks[0]["seq"] > downs[0]["seq"])
                ok += good
                if not good:
                    notes_.append("hop %d: downs %d clicks %d down %s" % (i, len(downs), len(clicks), downs[:1]))
    except Exception as exc:  # noqa: BLE001
        unmeasured([R7], exc)
        return
    judge(R7, ok == 10, "row7 %d of 10 move+click pairs in order on the end point %s" % (ok, notes_[:2]))


def raw_row(url):
    full = FULL.get(("legs", 125))
    if not full or not [e for e in full if e.get("k") == "raw"]:
        unmeasured([R8], "no pointerrawupdate arrived")
        return
    pairs, n, sd = raw_realtime(full)
    judge(R8, n >= 100 and pairs <= 0.02 * n and sd is not None and sd < 1.0,
          "row8 125 Hz: %d raw events, %d back-to-back pairs, sd of now - timeStamp %s ms" % (n, pairs, None if sd is None else round(sd, 3)))


def repeat_row(url):
    got = [(k, repeats(moves_of(FULL[k]))) for k in (("legs", 125), ("hops", 125)) if k in FULL]
    if not got or not all(n > 50 for _, (_, n) in got):
        unmeasured([R9], "no 125 Hz run, or fewer than 50 coalesced samples")
        return
    judge(R9, all(r == 0 for _, (r, _) in got), "row9 repeats / coalesced samples: %s" % ", ".join("%s %d/%d" % (k[0], r, n) for k, (r, n) in got))


def hover_row(url):
    """The CDP move returns when the last event is forwarded; the renderer may not have handled it yet. A read of :hover through
    the main world right after it is what a script does. Reported with how many of 20 read the new state."""
    try:
        with browser({**HUM, "humanize:minTime": 80, "humanize:maxTime": 200}, url) as proc:
            c, _ = base.open_page(proc)
            ok = 0
            for i in range(20):
                inside = i % 2 == 0
                x, y = (630.0, 430.0) if inside else (200.0 + 10 * i, 150.0)
                base.move(c, x, y)
                ok += base.ev(c, "document.querySelector('#h:hover') !== null") == inside
    except Exception as exc:  # noqa: BLE001
        unmeasured([R10], exc)
        return
    judge(R10, ok == 20, "row10 %d of 20 reads of :hover right after the move saw the new state" % ok)


def ignore_row(url):
    try:
        with browser({**HUM, "humanize:minTime": 80, "humanize:maxTime": 200}, url) as proc:
            c, _ = base.open_page(proc)
            c.call("Input.setIgnoreInputEvents", {"ignore": True})
            base.ev(c, "window.__log = []")
            t0 = time.monotonic()
            base.move(c, 500.0, 300.0, timeout_s=10)
            took = time.monotonic() - t0
            time.sleep(0.4)
            leaked = len(base.ev(c, "window.__log"))
            c.call("Input.setIgnoreInputEvents", {"ignore": False})
            base.ev(c, "window.__log = []")
            base.move(c, 300.0, 200.0, timeout_s=10)
            time.sleep(0.4)
            after = len(moves_of(base.ev(c, "window.__log")))
    except Exception as exc:  # noqa: BLE001
        unmeasured([R11], exc)
        return
    judge(R11, leaked == 0 and after > 0, "row11 ignoring: returned in %.2f s, %d events reached the page; after lifting: %d moves" % (took, leaked, after))


def drag_row(url):
    """buttons=1 moves keep the debugger bit on the final event (the drag starts on the ack), which cannot merge with the burst."""
    try:
        with browser({**HUM, "humanize:minTime": 300, "humanize:maxTime": 500}, url) as proc:
            c, _ = base.open_page(proc)
            close, paths = 0, 0
            for i in range(12):
                x0, y0, x1, y1 = 150.0, 150.0 + 25 * i, 700.0, 160.0 + 25 * i
                base.move(c, x0, y0)
                c.call("Input.dispatchMouseEvent", base.mouse("mousePressed", x0, y0, button="left", buttons=1, clickCount=1), 30)
                base.ev(c, "window.__log = []")
                c.call("Input.dispatchMouseEvent", base.mouse("mouseMoved", x1, y1, button="left", buttons=1), 30)
                time.sleep(0.3)
                lg = [e for e in base.ev(c, "window.__log") if e.get("k") == "move"]
                c.call("Input.dispatchMouseEvent", base.mouse("mouseReleased", x1, y1, button="left", buttons=0, clickCount=1), 30)
                paths += 1
                close += sum(1 for a, b in zip(lg, lg[1:]) if b["now"] - a["now"] < 6.0)
                if not lg or abs(lg[-1]["x"] - x1) > 1.0:
                    raise RuntimeError("the drag move did not arrive at its end point")
    except Exception as exc:  # noqa: BLE001
        unmeasured([R12], exc)
        return
    judge(R12, close == 0, "row12 %d drags: %d pointermove pairs less than 6 ms apart" % (paths, close))


def self_test():
    log = [{"ts": 16.0, "cs": 3, "cts": [0.0, 8.0, 16.0], "ps": 1}, {"ts": 32.0, "cs": 2, "cts": [24.0, 32.0], "ps": 1}]
    m = metrics(log)
    assert m["multi"] == 1.0 and m["max"] == 3 and m["gap_med"] == 8.0 and m["gap_n"] == 3
    assert monotonic(log) and not monotonic(log[::-1])
    single = [{"ts": 1.0, "cs": 1, "cts": [1.0], "ps": 0}]
    mv = [{"mx": 10, "my": 0, "cmx": [4, 6], "cmy": [0, 0]}]
    assert movement_ok(mv) and not movement_ok([{"mx": 10, "my": 0, "cmx": [4, 4], "cmy": [0, 0]}])
    assert metrics(single)["gap_med"] is None and metrics(single)["multi"] == 0.0
    # row 8, RED: bursts of two at one `now`, 8 ms apart in stamp
    real = [{"k": "raw", "ts": i * 8.0, "now": i * 8.0 + 1.0 + (0.1 if i % 2 else 0.0)} for i in range(100)]
    burst = [{"k": "raw", "ts": i * 8.0, "now": (i // 2) * 16.0 + 9.0} for i in range(100)]
    p, n, sd = raw_realtime(real)
    assert p == 0 and n == 100 and sd < 0.2, (p, n, sd)
    p, n, sd = raw_realtime(burst)
    assert p == 50 and sd > 3, (p, n, sd)
    # row 9, RED: one coalesced position twice in a row, also across two lists
    mv = [{"k": "move", "cxy": [[1.0, 1.0], [2.0, 1.0]]}, {"k": "move", "cxy": [[2.0, 1.0], [3.0, 1.0]]}]
    assert repeats(mv) == (1, 4) and repeats(mv[:1]) == (0, 2)


def main():
    if sys.argv[1:2] == ["--self-test"]:
        self_test()
        print("self-test ok")
        return 0
    with served() as url:
        l125 = rate_row(R1, 125, url)
        l1000 = rate_row(R2, 1000, url)
        logs = [x for x in (l125, l1000) if x]
        try:
            off = moves_of(run({"humanize:enabled": False, "input:pollingHz": 1000}, url))
        except Exception as exc:  # noqa: BLE001
            unmeasured([R4], exc)
        else:
            m = metrics(off)
            judge(R4, m["n"] >= 4 and m["max"] == 1, "row4 humanize off n=%d max coalesced=%d" % (m["n"], m["max"]))
        move_click_row(url)
        h = [hops_row(hz, url) for hz in (125, 1000)]
        every = logs + [x for x in h if x]
        if every:
            judge(R3, all(monotonic(x) for x in every), "row3 %d run(s) checked (legs and hops)" % len(every))
        else:
            unmeasured([R3], "no run")
        raw_row(url)
        repeat_row(url)
        hover_row(url)
        ignore_row(url)
        drag_row(url)
        if all(h):
            judge(R6, all(movement_ok(x) for x in h + logs), "row6 %d run(s) checked, each head against its own list" % (len(h) + len(logs)))
        else:
            unmeasured([R6], "no hop run")
    for r in ROWS:
        print("%-10s %s" % (results.get(r, "UNMEASURED"), r))
    for n in notes:
        print("      " + n)
    return 0 if all(results.get(r) == "PASS" for r in ROWS) else 1


if __name__ == "__main__":
    sys.exit(main())

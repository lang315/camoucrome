"""Verifies the Cursory port (SP2e): the humanized mouse path and the shared
input scheduler, driven over a raw websocket (no Runtime.enable; Input and
Runtime.evaluate only).

Eleven rows, each with its expected count. A row that cannot run reports
UNMEASURED, never PASS; any non-PASS row exits 1. Each row launches its own
browser. Pure checks live in sp2e_analysis.py (`--self-test` runs them with no
browser).

  RED-capable: 1, 4, 10, 11 (stock path / old queue: one event per move, no
  ordering; the old code let a cap-refused or zero-length move overtake the
  queue as an immediate stock event -- rows 10 and 11 fail on it).
  Guard-only: 2, 3, 5-9. Rows 2 and 3 bound the new path only (they also fail
  on stock, but say nothing about the old queue); 5-9 pass either way and are
  evidence that nothing broke, not that the patch works.

Box command (clean env, under scripts/build_lock.sh):
  env -i HOME="$HOME" PATH="$PATH" PYTHONPATH="$PYTHONPATH" \\
    CAMOU_CLIENT="$CAMOU_CLIENT" CAMOU_FONTS_DIR="$CAMOU_FONTS_DIR" \\
    ~/camoucrome-verify/venv/bin/python3 scripts/verify_sp2e.py
"""
import contextlib
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

import sp2e_analysis as an

WIN = {"ua:osInfo": "Windows NT 10.0; Win64; x64", "ua:platform": "Windows"}
HUM = {"humanize:enabled": True}  # default bounds 80..1200 ms
PRIME = (100.0, 200.0)

PAGE = ("<!doctype html><body style='margin:0;height:40000px'><script>"
        "window.__log=[];"
        "addEventListener('mousemove',e=>__log.push({k:'m',x:e.clientX,y:e.clientY,t:e.timeStamp}),true);"
        "addEventListener('wheel',e=>__log.push({k:'w',x:e.clientX,y:e.clientY,t:e.timeStamp}),"
        "{capture:true,passive:true});</script>")

results, notes = {}, []


def row(name, ok, note=""):
    results[name] = "PASS" if ok else "FAIL"
    if note and not ok:
        notes.append("%s: %s" % (name, note))


def unmeasured(name, err):
    results[name] = "UNMEASURED"
    notes.append("%s: %r" % (name, err))


class Cdp:
    """Raw CDP over websocket-client. send() does not wait; recv_until() does."""

    def __init__(self, url):
        import websocket
        self.ws = websocket.create_connection(url, timeout=15, suppress_origin=True)
        self.n = 0
        self.arrived = []  # reply ids in arrival order

    def send(self, method, params=None):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params or {}}))
        return self.n

    def recv_until(self, ids, timeout_s):
        """(replies by id, closed). Stops when every id answered, on timeout or on close."""
        import websocket
        want, got, closed = set(ids), {}, False
        end = time.monotonic() + timeout_s
        while want - set(got):
            left = end - time.monotonic()
            if left <= 0:
                break
            self.ws.settimeout(left)
            try:
                msg = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                break
            except websocket.WebSocketConnectionClosedException:
                closed = True
                break
            if "id" in msg:
                got[msg["id"]] = msg
                self.arrived.append(msg["id"])
        return got, closed

    def call(self, method, params=None, timeout_s=15):
        i = self.send(method, params)
        got, _ = self.recv_until([i], timeout_s)
        if i not in got:
            raise RuntimeError("no reply to %s within %ss" % (method, timeout_s))
        return got[i]

    def close(self):
        self.ws.close()


@contextlib.contextmanager
def browser(config):
    import lib_shell
    proc = lib_shell.launch(json.dumps(config) if config else None, shell=lib_shell.CHROME,
                            extra_flags=lib_shell.CHROME_FLAGS + ["--remote-allow-origins=*"])
    try:
        yield proc
    finally:
        lib_shell.shutdown(proc)


def targets(proc):
    return json.loads(urllib.request.urlopen(
        "http://127.0.0.1:%d/json" % proc.cdp_port, timeout=5).read())


def alive(proc):
    try:
        return bool(targets(proc))
    except Exception:  # noqa: BLE001
        return False


def open_page(proc):
    """(Cdp on the page target, target id) with PAGE loaded and the primer move done."""
    t = next(t for t in targets(proc) if t.get("type") == "page")
    c = Cdp(t["webSocketDebuggerUrl"])
    c.call("Page.navigate", {"url": "data:text/html," + urllib.parse.quote(PAGE)})
    end = time.monotonic() + 10
    while ev(c, "typeof window.__log") != "object":
        if time.monotonic() > end:
            raise RuntimeError("page did not load")
        time.sleep(0.1)
    move(c, *PRIME)  # a move needs a known previous position to be humanized
    time.sleep(0.2)
    ev(c, "window.__log = []")
    return c, t["id"]


def ev(c, expr):
    r = c.call("Runtime.evaluate", {"expression": expr, "returnByValue": True})
    return r["result"]["result"].get("value")


def mouse(kind, x, y, **kw):
    return {"type": kind, "x": x, "y": y, "button": "none", **kw}


def move_params(x, y):
    return mouse("mouseMoved", x, y)


def wheel_params(x, y, dy):
    return mouse("mouseWheel", x, y, deltaX=0, deltaY=dy)


def move(c, x, y, timeout_s=70):
    return c.call("Input.dispatchMouseEvent", move_params(x, y), timeout_s)


def wait_last_at(c, x, y, timeout_s=3):
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        last = ev(c, "__log.length ? __log[__log.length-1] : null")
        if last and last["x"] == x and last["y"] == y:
            return True
        time.sleep(0.1)
    return False


def log(c):
    return ev(c, "window.__log") or []


def dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


R1 = "1 humanize, 600 px move: >=10 mousemoves, ends exactly at target, timeStamps strictly increasing, span 59.2-1200 ms (80 ms path minus the unposted first gap)"
R2 = "2 humanize, 3 px move: >=2 mousemoves, page span 59.2-1200 ms (floor 80 minus first gap), no NaN"
R3 = "3 humanize, 600 px move: median inter-event gap 8-25 ms"
R4 = "4 un-awaited move, wheel(0,300), move: log is exactly [moves, 3 wheel notches, moves], no interleaving"
R5 = "5 flood of 200 un-awaited moves: browser alive, 200/200 replies within 60 s, events arrive"
R6 = "6 target closed 100 ms into a 1 s move: pending command resolves (no hang), browser still answers"
R7 = "7 hostile bounds (900/100, -5/0, max=1e9): path ends at target within 10 s cap + 1 s margin, browser alive"
R8 = "8 no config: 3 mouseMoved calls give exactly 3 mousemoves (1 each)"
R9 = "9 verify_sp2c.py (Windows-claim wheel) exits 0"
R10 = "10 overflow keeps order: 14 un-awaited moves (1 s each, past the 10 s cap): 14/14 final events in submission order, last event is target 13"
R11 = "11 zero-length move waits for the queue: its event is in the tail after the path, its reply after the first reply"
EXPECTED = 11


def rows_1_2_3():
    try:
        with browser(HUM) as proc:
            c, _ = open_page(proc)
            tgt = (PRIME[0] + 600, PRIME[1])
            move(c, *tgt)
            ok_end = wait_last_at(c, *tgt)
            e1 = log(c)
            ev(c, "window.__log = []")
            tgt2 = (tgt[0] + 3, tgt[1])
            move(c, *tgt2)
            wait_last_at(c, *tgt2)
            e2 = log(c)
    except Exception as exc:  # noqa: BLE001
        for r in (R1, R2, R3):
            unmeasured(r, exc)
        return
    t1 = [e["t"] for e in e1]
    row(R1, len(e1) >= 10 and ok_end and an.strictly_increasing(t1) and an.span_in_bounds(t1, an.VISIBLE_MIN_MS, an.MAX_TIME_MS)
        and dist((e1[0]["x"], e1[0]["y"]), PRIME) <= 0.15 * 600,
        "n=%d end=%s span=%.0f first=%s" % (len(e1), ok_end, an.span(t1), e1[:1]))
    t2 = [e["t"] for e in e2]
    nan = any(v != v for e in e2 for v in (e["x"], e["y"]))
    row(R2, len(e2) >= 2 and an.span_in_bounds(t2, an.VISIBLE_MIN_MS, an.MAX_TIME_MS) and not nan,
        "n=%d span=%.0f nan=%s" % (len(e2), an.span(t2), nan))
    st = an.gap_stats(t1)
    print("      gaps (600 px): %s" % json.dumps(st))
    row(R3, st["n"] >= 2 and 8 <= st["median"] <= 25, json.dumps(st))


def row4():
    try:
        with browser({**HUM, **WIN}) as proc:
            c, _ = open_page(proc)
            ids = [c.send("Input.dispatchMouseEvent", move_params(500, 400)),
                   c.send("Input.dispatchMouseEvent", wheel_params(500, 400, 300)),
                   c.send("Input.dispatchMouseEvent", move_params(*PRIME))]
            got, _ = c.recv_until(ids, 30)
            time.sleep(0.5)
            events = [(e["k"], e["t"]) for e in log(c)]
    except Exception as exc:  # noqa: BLE001
        return unmeasured(R4, exc)
    viol = an.order_violations(events)
    row(R4, len(got) == 3 and not viol,
        "replies=%d violations=%s kinds=%s" % (len(got), viol, "".join(k for k, _ in events)))


def row5():
    try:
        with browser(HUM) as proc:
            c, _ = open_page(proc)
            ids = [c.send("Input.dispatchMouseEvent",
                          move_params(100 + (i % 2) * 500, 200 + i % 7)) for i in range(200)]
            got, _ = c.recv_until(ids, 60)
            ok_alive = alive(proc)
            n = len(log(c)) if ok_alive and len(got) == 200 else 0
    except Exception as exc:  # noqa: BLE001
        return unmeasured(R5, exc)
    row(R5, ok_alive and len(got) == 200 and n > 0,
        "alive=%s replies=%d events=%d" % (ok_alive, len(got), n))


def row6():
    try:
        with browser({"humanize:enabled": True, "humanize:minTime": 1000,
                      "humanize:maxTime": 1000}) as proc:
            c, tid = open_page(proc)
            ver = json.loads(urllib.request.urlopen(
                "http://127.0.0.1:%d/json/version" % proc.cdp_port, timeout=5).read())
            b = Cdp(ver["webSocketDebuggerUrl"])
            b.call("Target.createTarget", {"url": "about:blank"})  # keep a target alive
            i = c.send("Input.dispatchMouseEvent", move_params(700, 200))
            time.sleep(0.1)
            b.call("Target.closeTarget", {"targetId": tid})
            got, closed = c.recv_until([i], 10)
            resolved = bool(got) or closed
            how = "reply" if got else ("connection closed" if closed else "HANG")
            ok_alive = "targetInfos" in b.call("Target.getTargets").get("result", {})
    except Exception as exc:  # noqa: BLE001
        return unmeasured(R6, exc)
    row(R6, resolved and ok_alive, "pending command: %s, browser answers=%s" % (how, ok_alive))


def row7():
    # Dropping the bounds' sanity: swapped, negative and absurd values must
    # still end at the target within the 10 s duration cap (kMaxDurationMs) plus margin.
    cfgs = ({"humanize:minTime": 900, "humanize:maxTime": 100},
            {"humanize:minTime": -5, "humanize:maxTime": 0},
            {"humanize:maxTime": 1000000000})
    bad = []
    for cfg in cfgs:
        try:
            with browser({**HUM, **cfg}) as proc:
                c, _ = open_page(proc)
                tgt = (500.0, 400.0)
                t0 = time.monotonic()
                move(c, *tgt, timeout_s=20)
                took = time.monotonic() - t0
                at = wait_last_at(c, *tgt)
                if not (at and took <= (an.HARD_CAP_MS / 1000 + 1) and alive(proc)):
                    bad.append("%s at=%s took=%.1fs" % (cfg, at, took))
        except Exception as exc:  # noqa: BLE001
            return unmeasured(R7, exc)
    row(R7, not bad, "; ".join(bad))


def row8():
    try:
        with browser(None) as proc:
            c, _ = open_page(proc)
            counts = []
            for x in (300.0, 500.0, 200.0):
                ev(c, "window.__log = []")
                move(c, x, 300.0)
                time.sleep(0.3)
                counts.append(len(log(c)))
    except Exception as exc:  # noqa: BLE001
        return unmeasured(R8, exc)
    row(R8, counts == [1, 1, 1], "per-move counts %s" % counts)


def row9():
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        r = subprocess.run([sys.executable, os.path.join(here, "verify_sp2c.py")],
                           capture_output=True, text=True, timeout=600)
    except Exception as exc:  # noqa: BLE001
        return unmeasured(R9, exc)
    row(R9, r.returncode == 0, "rc=%d tail=%s" % (r.returncode, r.stdout[-300:]))


def row10():
    cfg = {**HUM, "humanize:minTime": 1000, "humanize:maxTime": 1000}
    targets = [100 + 40 * i for i in range(14)]
    try:
        with browser(cfg) as proc:
            c, _ = open_page(proc)
            ids = [c.send("Input.dispatchMouseEvent", move_params(float(x), 200.0))
                   for x in targets]
            got, _ = c.recv_until(ids, an.REPLY_DEADLINE_S)
            time.sleep(0.5)
            xs = [e["x"] for e in log(c)]
    except Exception as exc:  # noqa: BLE001
        return unmeasured(R10, exc)
    viol = an.final_order_violations(xs, [float(x) for x in targets])
    row(R10, len(got) == 14 and not viol,
        "replies=%d/14 within %.1fs violations=%s" % (len(got), an.REPLY_DEADLINE_S, viol))


def row11():
    tgt = (PRIME[0] + 600, PRIME[1])
    try:
        with browser(HUM) as proc:
            c, _ = open_page(proc)
            i1 = c.send("Input.dispatchMouseEvent", move_params(*tgt))
            i2 = c.send("Input.dispatchMouseEvent", move_params(*tgt))  # zero-length from tgt
            got, _ = c.recv_until([i1, i2], 20)
            time.sleep(0.5)
            events = [(e["x"], e["y"], e["t"]) for e in log(c)]
            order = list(c.arrived)
    except Exception as exc:  # noqa: BLE001
        return unmeasured(R11, exc)
    viol = an.tail_violations(events, tgt)
    row(R11, len(got) == 2 and not viol and an.reply_before(order, i1, i2),
        "replies=%d order=%s violations=%s" % (len(got), order, viol))


def main():
    if sys.argv[1:2] in (["--self-test"], ["--dry-parse"]):
        an.self_test()
        print("self-test ok")
        return 0
    rows_1_2_3()
    for f in (row4, row5, row6, row7, row8, row9, row10, row11):
        f()
    for name in sorted(results, key=lambda n: int(n.split()[0])):
        print("%-10s %s" % (results[name], name))
    if len(results) != EXPECTED:
        notes.append("expected %d rows, found %d" % (EXPECTED, len(results)))
    for n in notes:
        print("      " + n)
    return 0 if len(results) == EXPECTED and all(v == "PASS" for v in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())

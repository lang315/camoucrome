"""Verifies SP2d dwell, hold and the ordered queue for humanized mouse events.

With humanize:enabled, InputHandler holds a mousedown back until a drawn dwell
(after the last move) has passed, and a mouseup until a drawn hold (after the
press), in order. Without it, a click's press and release are back to back.

Driven with page.click / page.mouse.* (one Input.dispatchMouseEvent per call).
Bounds come from _click_tables and human_math with the config's seed, so the
numbers are the browser's, not copies of them. Every row states what it saw.
"""

import http.server
import json
import os
import signal
import statistics
import subprocess
import sys
import threading
import time

from playwright.sync_api import sync_playwright

from camoucrome import _click_tables as T
from camoucrome import human_math

import lib_shell

SEED = 12345
HUM = {"humanize:enabled": True, "humanize:seed": SEED}
S_H = human_math.profile_scale(SEED, "hold")
S_D = human_math.profile_scale(SEED, "dwell")
MAX_HOLD, MAX_DWELL = 400.0, 600.0  # kMaxHoldMs, kMaxDwellMs (human_input_tables.h)
# Per-click upper bounds: the browser draws at most the table's last knot (x scale), and the
# page-measured delta adds the lateness of the delayed drain task plus timeStamp coarsening.
# 15 ms left 1.6-6 ms margins on the top-5% draw in 4 of 4 runs; 30 ms covers CI load.
# The medians, D2 and H2 carry the RED power, not these maxima.
SLACK_MS = 30.0
D2_MAX_MS = 20.0  # down() after a pause returns with no extra dwell
H3_TIMEOUT_S = 45

PAGE = """<!doctype html><body style="margin:0"><button id=b
style="position:absolute;left:300px;top:300px;width:120px;height:40px">b</button><script>
window.__l = [];
for (const type of ['mousemove', 'mousedown', 'mouseup', 'click', 'dblclick'])
  addEventListener(type, e => __l.push({type, t: e.timeStamp, x: e.clientX, y: e.clientY,
    detail: e.detail}), true);
</script>"""
NAV_PAGE = PAGE.replace("<button id=b", "<button id=b onmousedown=\"location.href='/other'\"")


def session(config, actions, flags=(), premove=False, page_html=PAGE, url=None):
    """actions(page) -> value; returns (value, err). No initial mouse move unless asked."""
    proc = None
    try:
        proc = lib_shell.launch(json.dumps(config) if config else None, shell=lib_shell.CHROME,
                                extra_flags=lib_shell.CHROME_FLAGS + list(flags))
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{proc.cdp_port}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            if url:
                page.goto(url)
            else:
                page.set_content(page_html)
            if premove:
                page.mouse.move(300, 300)
            return actions(page), None
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)


def log(page):
    return page.evaluate("window.__l")


def stats(events):
    """(holds, dwells) per click: down -> next up, and down - the last move before it."""
    holds, dwells = [], []
    last_move = None
    for i, e in enumerate(events):
        if e["type"] == "mousemove":
            last_move = e["t"]
        elif e["type"] == "mousedown":
            if last_move is not None:
                dwells.append(e["t"] - last_move)
            up = next((u for u in events[i + 1:] if u["type"] == "mouseup"), None)
            if up:
                holds.append(up["t"] - e["t"])
    return holds, dwells


def clicks(n):
    def act(page):
        for _ in range(n):
            page.mouse.move(10, 10)
            page.click("#b")
        return stats(log(page))
    return act


results, notes = {}, []


def row(name, ok, note=None):
    results[name] = bool(ok)
    if note and not ok:
        notes.append(f"{name}: {note}")


def med(xs):
    return statistics.median(xs) if xs else float("nan")


class _Page(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = (NAV_PAGE if self.path == "/" else "<!doctype html><title>other</title>other").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if sys.argv[1:2] == ["--nav"]:
    # argv: --nav <bfcache|nobfcache> <hum|none>. Prints how click() ended.
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Page)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    flags = ["--disable-features=BackForwardCache"] if sys.argv[2] == "nobfcache" else []

    def nav(page):
        try:
            page.click("#b", timeout=30000)
            return "ok"
        except Exception as exc:  # noqa: BLE001 - the class name is the result
            return type(exc).__name__

    out, err = session(HUM if sys.argv[3] == "hum" else None, nav, flags,
                       url=f"http://127.0.0.1:{srv.server_address[1]}/")
    print(json.dumps({"returned": True, "result": out if not err else "session:" + type(err).__name__}))
    sys.exit(0)

H0 = "H0 no config: ten clicks, median hold and median dwell < 5 ms"
H1 = "H1 humanize: 40 clicks, holds within the table's bounds, median in [p10, p90]"
D1 = "D1 humanize: the same 40 clicks, dwells within the table's bounds, median in [p10, p90]"
H2 = "H2 humanize: click(delay=600) holds 600 +- 20 ms"
D2 = "D2 humanize: mouse.down() after a 700 ms pause returns with no extra dwell"
H3 = "H3 humanize: a mousedown that navigates ends click() as with no config (bfcache on and off)"
H4 = "H4 humanize: dblclick is down, up, down, up, dblclick once"

got, err = session(None, clicks(10))
if err:
    row(H0, False, repr(err))
else:
    holds, dwells = got
    row(H0, len(holds) == 10 and med(holds) < 5 and med(dwells) < 5,
        f"hold med {med(holds):.1f} dwell med {med(dwells):.1f} n={len(holds)}")
    print(f"H0 measured: hold median {med(holds):.2f} ms, dwell median {med(dwells):.2f} ms")

got, err = session(HUM, clicks(40))
if err:
    row(H1, False, repr(err))
    row(D1, False, repr(err))
else:
    holds, dwells = got
    hk, dk = T.HOLD_MS, T.DWELL_MS
    hmax = min(hk[20] * S_H, MAX_HOLD) + SLACK_MS
    dmax = min(dk[20] * S_D, MAX_DWELL) + SLACK_MS
    hlo, hhi = hk[2] * S_H, hk[18] * S_H
    dlo, dhi = dk[2] * S_D, dk[18] * S_D
    print(f"H1 measured: hold median {med(holds):.1f} ms, max {max(holds):.1f}; "
          f"bounds median [{hlo:.1f}, {hhi:.1f}], max {hmax:.1f}")
    print(f"D1 measured: dwell median {med(dwells):.1f} ms, max {max(dwells):.1f}; "
          f"bounds median [{dlo:.1f}, {dhi:.1f}], max {dmax:.1f}")
    row(H1, len(holds) == 40 and max(holds) <= hmax and hlo <= med(holds) <= hhi,
        f"n={len(holds)} med={med(holds):.1f} max={max(holds):.1f} bounds=[{hlo:.1f},{hhi:.1f}] max<={hmax:.1f}")
    row(D1, len(dwells) == 40 and max(dwells) <= dmax and dlo <= med(dwells) <= dhi,
        f"n={len(dwells)} med={med(dwells):.1f} max={max(dwells):.1f} bounds=[{dlo:.1f},{dhi:.1f}] max<={dmax:.1f}")


def delay600(page):
    page.click("#b", delay=600)
    return stats(log(page))[0]


got, err = session(HUM, delay600)
row(H2, not err and len(got) == 1 and abs(got[0] - 600) <= 20, repr(err) if err else f"holds={got}")


def pause_then_down(page):
    page.mouse.move(360, 320)
    page.wait_for_timeout(700)
    t0 = time.monotonic()
    page.mouse.down()
    elapsed = (time.monotonic() - t0) * 1000
    page.mouse.up()
    ev = log(page)
    mv = [e["t"] for e in ev if e["type"] == "mousemove"]
    dn = [e["t"] for e in ev if e["type"] == "mousedown"]
    return elapsed, (dn[0] - mv[-1]) if dn and mv else None


got, err = session(HUM, pause_then_down)
if err:
    row(D2, False, repr(err))
else:
    elapsed, gap = got
    print(f"D2 measured: down() took {elapsed:.1f} ms, press {gap} ms after the last move")
    row(D2, gap is not None and gap >= 700 and elapsed <= D2_MAX_MS, f"elapsed={elapsed:.1f} gap={gap}")


def nav_row(arm, cfg):
    """A child process in its own group: a hung click must be a timeout here, not a hang."""
    child = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--nav", arm, cfg],
                             stdout=subprocess.PIPE, text=True, start_new_session=True)
    try:
        out, _ = child.communicate(timeout=H3_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.communicate()
        return {"returned": False}
    try:
        return json.loads(out.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return {"returned": True, "result": "unparsed:" + out[-200:]}


h3 = []
for arm in ("bfcache", "nobfcache"):
    base, hum = nav_row(arm, "none"), nav_row(arm, "hum")
    h3.append((arm, base, hum))
    print(f"H3 {arm}: no config {base}, humanize {hum}")
row(H3, all(h["returned"] and b["returned"] and h["result"] == b["result"]
            and not str(h["result"]).startswith(("session:", "unparsed:")) for _, b, h in h3),
    json.dumps(h3))


def dbl(page):
    page.dblclick("#b")
    return [e["type"] for e in log(page) if e["type"] not in ("mousemove", "click")]


got, err = session(HUM, dbl)
row(H4, not err and got == ["mousedown", "mouseup", "mousedown", "mouseup", "dblclick"],
    repr(err) if err else str(got))

EXPECTED = 7
for name in sorted(results):
    print(f"{'PASS' if results[name] else 'FAIL'}  {name}")
if len(results) != EXPECTED:
    notes.append(f"expected {EXPECTED} rows, found {len(results)}")
for n in notes:
    print(f"      {n}")
sys.exit(0 if len(results) == EXPECTED and all(results.values()) else 1)

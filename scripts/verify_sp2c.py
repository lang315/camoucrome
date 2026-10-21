"""Verifies SP2c: with humanize:enabled and a claimed Windows, a CDP mouseWheel
reaches the page as whole notches (one event per notch, the per-notch shape
measured in baselines/chrome-8078-wheel.json, 18-60 ms apart); without either
it is stock's single event.

Driven with page.mouse.wheel, one Input.dispatchMouseEvent per call, like
verify_sp2b. Every row states its count. Animation is not asserted here:
whether chrome on Linux animates pixel-unit wheels says nothing about Windows
(spec section 4); the host-native arm owns that.
"""

import http.server
import json
import os
import signal
import subprocess
import sys
import threading

from playwright.sync_api import sync_playwright

import lib_shell

NOTCH_PX = 100  # baselines/chrome-8078-wheel.json real1 dy[0]
WIN = {"ua:osInfo": "Windows NT 10.0; Win64; x64", "ua:platform": "Windows"}
MAC = {"ua:osInfo": "Macintosh; Intel Mac OS X 10_15_7", "ua:platform": "macOS"}
HUMANIZE = {"humanize:enabled": True}
ROW8_TIMEOUT_S = 45  # launch + 5 notches (<= 240 ms) + navigation, with headroom

PAGE = """<!doctype html><body style="margin:0;height:40000px;width:40000px"><script>
window.__w = [];
addEventListener('wheel', e => __w.push({dx: e.deltaX, dy: e.deltaY, mode: e.deltaMode,
  wdx: e.wheelDeltaX, wdy: e.wheelDeltaY, t: e.timeStamp}), {passive: true});
</script>"""


def session(config, actions, flags=()):
    """actions(page) -> value; returns (value, err)."""
    proc = None
    try:
        proc = lib_shell.launch(json.dumps(config) if config else None, shell=lib_shell.CHROME,
                                extra_flags=lib_shell.CHROME_FLAGS + list(flags))
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{proc.cdp_port}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            page.set_content(PAGE)
            page.mouse.move(300, 300)
            return actions(page), None
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)


def wheel_then_read(*deltas):
    def act(page):
        out = []
        for dx, dy in deltas:
            page.evaluate("window.__w = []")
            page.mouse.wheel(dx, dy)
            page.wait_for_timeout(300)
            out.append(page.evaluate("window.__w"))
        return out
    return act


def notch_ok(e, sx, sy):
    return (e["mode"] == 0 and e["dx"] == sx * NOTCH_PX and e["dy"] == sy * NOTCH_PX
            and e["wdx"] == -120 * sx and e["wdy"] == -120 * sy)


def gaps(events):
    return [b["t"] - a["t"] for a, b in zip(events, events[1:])]


results, notes = {}, []


def row(name, ok, note=None):
    results[name] = bool(ok)
    if note and not ok:
        notes.append(f"{name}: {note}")


class _Page(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if sys.argv[1:2] == ["--nav"]:
    # same: same-document target (about:blank). xsite: 127.0.0.1 -> localhost,
    # a cross-site navigation that swaps the frame's widget (the old one may
    # sit in the back/forward cache). xsite-nobfcache: same, but the old
    # widget is destroyed, so the last notch meets a dead widget.
    kind = sys.argv[2]
    srv = http.server.ThreadingHTTPServer(("", 0), _Page)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]

    def nav(page):
        """A 5-notch wheel with a navigation 10 ms in: the command may succeed
        or error (both allowed), then the browser must still answer."""
        target = "about:blank"
        if kind != "same":
            page.goto(f"http://127.0.0.1:{port}/")
            page.mouse.move(300, 300)
            target = f"http://localhost:{port}/"
        page.evaluate(f"setTimeout(() => location.href = '{target}', 10)")
        try:
            page.mouse.wheel(0, 500)
        except Exception:  # noqa: BLE001 - an error is an allowed outcome; a hang is not
            pass
        page.wait_for_timeout(500)
        return page.evaluate("location.href") == target

    flags = ["--disable-features=BackForwardCache"] if kind == "xsite-nobfcache" else []
    arrived, err = session({**HUMANIZE, **WIN}, nav, flags)
    print(json.dumps({"returned": True, "alive": bool(arrived) and not err}))
    sys.exit(0)

R1 = "1 no config: wheel(0,300) is one event of deltaY 300"
R2 = "2 humanize+Windows: wheel(0,300) is 3 notch events, 18-60 ms apart"
R3 = "3 humanize+Windows: wheel(0,0)=stock count, (0,40)=1 notch, (-250,0)=3 notches on X"
R4 = "4 humanize+macOS: wheel(0,300) is stock's single event"
R5 = "5 humanize, nothing claimed (Linux build): wheel(0,300) is stock's single event"
R6 = "6 no new window keys and WheelEvent accessors native under humanize+Windows"
R7 = "7 humanize+Windows: two back-to-back wheel(0,300) give 6 events, timeStamps increasing"
R8 = "8 humanize+Windows: navigating away mid-sequence neither hangs nor kills the browser"
R9 = "9 humanize+Windows at DSF 2: wheel(0,300) is 3 notch events of deltaY 100"
R10 = "10 humanize+Windows: cross-site navigation mid-sequence neither hangs nor kills the browser"
R11 = "11 same as 10 with the back/forward cache off (the last notch meets a dead widget)"

stock, err = session(None, wheel_then_read((0, 300), (0, 0)))
if err:
    row(R1, False, repr(err))
    stock_zero = None
else:
    w300, stock_zero = stock
    row(R1, len(w300) == 1 and w300[0]["dy"] == 300, json.dumps(w300))

got, err = session({**HUMANIZE, **WIN}, wheel_then_read((0, 300), (0, 0), (0, 40), (-250, 0)))
if err:
    row(R2, False, repr(err))
    row(R3, False, repr(err))
else:
    w300, w0, w40, wx = got
    g = gaps(w300)
    row(R2, len(w300) == 3 and all(notch_ok(e, 0, 1) for e in w300) and all(15 <= x <= 75 for x in g),
        f"n={len(w300)} gaps={g} ev={json.dumps(w300)}")
    row(R3, stock_zero is not None and len(w0) == len(stock_zero)
        and len(w40) == 1 and notch_ok(w40[0], 0, 1)
        and len(wx) == 3 and all(notch_ok(e, -1, 0) for e in wx),
        f"w0={w0} stock0={stock_zero} w40={w40} wx={wx}")

for name, cfg in ((R4, {**HUMANIZE, **MAC}), (R5, HUMANIZE)):
    got, err = session(cfg, wheel_then_read((0, 300)))
    row(name, not err and len(got[0]) == 1 and got[0][0]["dy"] == 300, repr(err) if err else json.dumps(got))

KEYS = ("JSON.stringify([Object.keys(window).length, ['deltaX','deltaY','deltaMode','wheelDeltaY'].map(k => "
        "Object.getOwnPropertyDescriptor(WheelEvent.prototype, k) ? Function.prototype.toString.call("
        "Object.getOwnPropertyDescriptor(WheelEvent.prototype, k).get || (() => {})) : 'own:' + k)])")
base, err1 = session(None, lambda page: page.evaluate(KEYS))
hum, err2 = session({**HUMANIZE, **WIN}, lambda page: page.evaluate(KEYS))
row(R6, not err1 and not err2 and base == hum and "[native code]" in hum, f"{base} vs {hum}")


def back_to_back(page):
    page.evaluate("window.__w = []")
    page.mouse.wheel(0, 300)
    page.mouse.wheel(0, 300)
    page.wait_for_timeout(300)
    return page.evaluate("window.__w")


got, err = session({**HUMANIZE, **WIN}, back_to_back)
row(R7, not err and len(got) == 6 and all(x > 0 for x in gaps(got)), repr(err) if err else json.dumps(got))


def nav_row(kind):
    """A navigation row in a child process with its own process group: a hung
    wheel command must show up as a timeout, not hang this script. SIGALRM
    inside Playwright's sync loop wedges the connection instead of
    interrupting it (seen RED 2026-10-17: the whole verify hung until killed)."""
    child = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--nav", kind],
                             stdout=subprocess.PIPE, text=True, start_new_session=True)
    try:
        out, _ = child.communicate(timeout=ROW8_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)  # the child's chrome is in its group
        child.communicate()
        return {"returned": False, "alive": None}
    try:
        return json.loads(out.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return {"returned": True, "alive": None, "child_out": out[-300:]}


for name, kind in ((R8, "same"), (R10, "xsite"), (R11, "xsite-nobfcache")):
    got = nav_row(kind)
    row(name, got == {"returned": True, "alive": True}, json.dumps(got))

# DSF 2: CDP wheel deltas are CSS px (input_handler.cc does not scale them) and
# Blink divides a wheel's delta by the page scale, so each notch must still
# reach the page as kWindowsNotchCssPx.
# At DSF 2 the headless viewport is 500x137 CSS px, so (300, 300) is off-page
# (stock gets no event there either); wheel at (100, 100).
def wheel_at_100(page):
    page.mouse.move(100, 100)
    return wheel_then_read((0, 300))(page)


got, err = session({**HUMANIZE, **WIN}, wheel_at_100, ["--force-device-scale-factor=2"])
row(R9, not err and len(got[0]) == 3 and all(notch_ok(e, 0, 1) for e in got[0]),
    repr(err) if err else json.dumps(got))

EXPECTED = 11
for name in sorted(results, key=lambda n: int(n.split()[0])):
    print(f"{'PASS' if results[name] else 'FAIL'}  {name}")
if len(results) != EXPECTED:
    notes.append(f"expected {EXPECTED} rows, found {len(results)}")
for n in notes:
    print(f"      {n}")
sys.exit(0 if len(results) == EXPECTED and all(results.values()) else 1)

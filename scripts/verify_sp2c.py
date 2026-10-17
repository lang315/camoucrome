"""Verifies SP2c: with humanize:enabled and a claimed Windows, a CDP mouseWheel
reaches the page as whole notches (one event per notch, the per-notch shape
measured in baselines/chrome-8037-wheel.json, 18-60 ms apart); without either
it is stock's single event.

Driven with page.mouse.wheel, one Input.dispatchMouseEvent per call, like
verify_sp2b. Every row states its count. Animation is not asserted here:
whether chrome on Linux animates pixel-unit wheels says nothing about Windows
(spec section 4); the host-native arm owns that.
"""

import json
import os
import signal
import subprocess
import sys

from playwright.sync_api import sync_playwright

import lib_shell

NOTCH_PX = 100  # baselines/chrome-8037-wheel.json real1 dy[0]
WIN = {"ua:osInfo": "Windows NT 10.0; Win64; x64", "ua:platform": "Windows"}
MAC = {"ua:osInfo": "Macintosh; Intel Mac OS X 10_15_7", "ua:platform": "macOS"}
HUMANIZE = {"humanize:enabled": True}
ROW8_TIMEOUT_S = 45  # launch + 5 notches (<= 240 ms) + navigation, with headroom

PAGE = """<!doctype html><body style="margin:0;height:40000px;width:40000px"><script>
window.__w = [];
addEventListener('wheel', e => __w.push({dx: e.deltaX, dy: e.deltaY, mode: e.deltaMode,
  wdx: e.wheelDeltaX, wdy: e.wheelDeltaY, t: e.timeStamp}), {passive: true});
</script>"""


def session(config, actions):
    """actions(page) -> value; returns (value, err)."""
    proc = None
    try:
        proc = lib_shell.launch(json.dumps(config) if config else None, shell=lib_shell.CHROME,
                                extra_flags=lib_shell.CHROME_FLAGS)
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


if sys.argv[1:] == ["--row8"]:
    def nav(page):
        """A 5-notch wheel with a navigation 10 ms in: the command may succeed
        or error (both allowed), then the browser must still answer."""
        page.evaluate("setTimeout(() => location.href = 'about:blank', 10)")
        try:
            page.mouse.wheel(0, 500)
        except Exception:  # noqa: BLE001 - an error is an allowed outcome; a hang is not
            pass
        page.wait_for_timeout(500)
        return page.evaluate("1 + 1") == 2

    alive, err = session({**HUMANIZE, **WIN}, nav)
    print(json.dumps({"returned": True, "alive": bool(alive) and not err}))
    sys.exit(0)

R1 = "1 no config: wheel(0,300) is one event of deltaY 300"
R2 = "2 humanize+Windows: wheel(0,300) is 3 notch events, 18-60 ms apart"
R3 = "3 humanize+Windows: wheel(0,0)=stock count, (0,40)=1 notch, (-250,0)=3 notches on X"
R4 = "4 humanize+macOS: wheel(0,300) is stock's single event"
R5 = "5 humanize, nothing claimed (Linux build): wheel(0,300) is stock's single event"
R6 = "6 no new window keys and WheelEvent accessors native under humanize+Windows"
R7 = "7 humanize+Windows: two back-to-back wheel(0,300) give 6 events, timeStamps increasing"
R8 = "8 humanize+Windows: navigating away mid-sequence neither hangs nor kills the browser"

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


def row8():
    """Row 8 in a child process with its own process group: a hung wheel
    command must show up as a timeout, not hang this script. SIGALRM inside
    Playwright's sync loop wedges the connection instead of interrupting it
    (seen RED 2026-10-17: the whole verify hung until killed)."""
    child = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--row8"],
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


got = row8()
row(R8, got == {"returned": True, "alive": True}, json.dumps(got))

EXPECTED = 8
for name in sorted(results):
    print(f"{'PASS' if results[name] else 'FAIL'}  {name}")
if len(results) != EXPECTED:
    notes.append(f"expected {EXPECTED} rows, found {len(results)}")
for n in notes:
    print(f"      {n}")
sys.exit(0 if len(results) == EXPECTED and all(results.values()) else 1)

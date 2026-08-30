"""Verifies the SP2b Task 3 hook: a CDP-injected mouse MOVE, when
humanize:enabled is set, follows Task 2's synthesized path instead of
teleporting straight to the target.

Three criteria, driven with Playwright's page.mouse.move (steps=1, its
default -- one call, one `Input.dispatchMouseEvent` CDP command; anything
more than one CDP command per move would be Playwright's own client-side
interpolation, not the browser-side hook this file exists to prove):

  1. un-configured: a move produces exactly one mousemove DOM event.
  2. configured (humanize:enabled): the same kind of move produces MORE
     than one, the last one landing on the target.
  3. configured: the mousemove events trace the path spatially -- their
     x-coordinates span a real fraction of the start-to-target distance,
     rather than clustering at the target. A synchronous burst coalesces
     to events at the endpoint; real async delivery spreads them along the
     path. (The generator's timing non-uniformity is proven stably by the
     Task 2 unit test, not by a wall-clock assertion here.)

Each session performs two page.mouse.move calls, not one. InjectMouseEvent's
humanization only ever triggers for a move with a KNOWN previous position --
the brief's own safety property, since there is nothing to draw a path FROM
on a widget's very first move. A single move from a fresh page therefore
cannot expose criteria 2/3 regardless of configuration. The first move
(PRIME) establishes that previous position; window.__moves is cleared
before the second (TARGET), so only the move under test is counted. The
un-configured run performs the same two-move shape (criterion 1 measures
the TARGET move, same as 2/3), so the shape itself doesn't advantage either
side.

Structured like verify_sp2.py, and for the same reason: a fault in one
session must become a FAIL line rather than a traceback that discards every
result already collected.
"""

import json
import sys

from playwright.sync_api import sync_playwright

import lib_shell

# min/maxTime per the brief's own example. steps is the hook's concern, not
# this script's -- nothing here asserts a step count.
HUMANIZE = json.dumps({"humanize:enabled": True, "humanize:minTime": 40,
                       "humanize:maxTime": 120})

# Comfortably inside a headless chrome window's default viewport, far enough
# apart that a bowed path is visually and numerically distinct from a
# straight line.
PRIME = (100.0, 120.0)
TARGET = (420.0, 260.0)

INSTALL_LISTENER = """() => {
  window.__moves = [];
  window.addEventListener('mousemove', (e) => {
    window.__moves.push({x: e.clientX, y: e.clientY, t: e.timeStamp});
  });
}"""


def run(config):
    """One `chrome` session: prime, clear, move to TARGET, collect its events.

    Returns (events, err). `events` is the list the page recorded for the
    TARGET move only -- the primer's own event(s) are deliberately excluded
    by clearing window.__moves between the two moves (see module docstring).
    """
    proc = None
    try:
        proc = lib_shell.launch(config, shell=lib_shell.CHROME,
                                extra_flags=lib_shell.CHROME_FLAGS)
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(
                f"http://127.0.0.1:{proc.cdp_port}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("about:blank", wait_until="load")
            page.evaluate(INSTALL_LISTENER)
            page.mouse.move(*PRIME, steps=1)
            page.evaluate("window.__moves = []")
            page.mouse.move(*TARGET, steps=1)
            # humanize:maxTime tops out at 120ms (HUMANIZE above); this is
            # generous headroom for the whole path to have been delivered
            # and processed by the renderer before reading the recording
            # back.
            page.wait_for_timeout(1000)
            events = page.evaluate("window.__moves")
        return events, None
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)


results = {}
notes = []

C1 = "1 un-configured move produces exactly one mousemove"
C2 = "2 humanize:enabled move produces more than one mousemove, ending at the target"
C3 = "3 humanize:enabled events trace the path, not just the endpoint"

events, err = run(None)
if err is not None:
    results[C1] = False
    notes.append(f"criterion 1 session: {type(err).__name__}: {err}")
else:
    results[C1] = len(events) == 1

events, err = run(HUMANIZE)
if err is not None:
    results[C2] = False
    results[C3] = False
    notes.append(f"criteria 2/3 session: {type(err).__name__}: {err}")
else:
    n = len(events)
    results[C2] = (n > 1 and events[-1]["x"] == TARGET[0]
                   and events[-1]["y"] == TARGET[1])
    # Criterion 3 asserts the events TRACE THE PATH rather than clustering at
    # the target. The earlier form -- "inter-event timeStamps are not all
    # equal" -- was too weak: OS scheduler jitter satisfies it for any n>=3
    # even for a robotic generator, so it did not discriminate what it
    # claimed (whole-branch review, Minor). Spatial spread does: a synchronous
    # burst coalesces to events clustered at the target (x-span ~0), while
    # real async delivery spreads them from near the start toward the target.
    # Position-based, so it does not hinge on wall-clock timing precision.
    # The generator's TIMING non-uniformity is proven separately and stably by
    # MouseTrajectoriesTest.InterPointTimingIsNotUniform (Task 2).
    if n < 2:
        results[C3] = False
        notes.append("criterion 3: fewer than two events, no path to trace")
    else:
        x_span = max(e["x"] for e in events) - min(e["x"] for e in events)
        path_dx = abs(TARGET[0] - PRIME[0])  # 320 for (100 -> 420)
        results[C3] = x_span > path_dx * 0.3  # > ~96px of the 320px path
        if not results[C3]:
            notes.append(f"criterion 3: events clustered, x_span={x_span:.0f} "
                         f"of path {path_dx:.0f} -- not traced along the path")

EXPECTED = 3  # criteria 1, 2, 3

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")

# Checked AFTER the print loop, not before -- same reasoning as verify_sp2.py:
# raising on a count mismatch would discard results already in hand and
# print nothing.
if len(results) != EXPECTED:
    notes.append(
        f"expected {EXPECTED} criteria in `results`, found {len(results)}: "
        "a criterion was added or removed without updating EXPECTED")

for note in notes:
    print(f"      {note}")

sys.exit(0 if results and len(results) == EXPECTED and all(results.values())
         else 1)

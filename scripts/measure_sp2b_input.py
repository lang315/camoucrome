"""SP2b measurement 4: is CDP-synthesized mouse input already isTrusted?

SP2 verification item 9, and open decision D3. Section 4.4 argues that
`Input.dispatchMouseEvent` should already produce `isTrusted === true` events,
because CDP injects into the browser process via `RenderWidgetHostImpl` and
travels the normal input path -- unlike `dispatchEvent` from page JS, which
never leaves the renderer's script context. That is stated as an assumption
to verify, not a fact: "If item 9 finds a readable field that differs from
hardware input, the decision flips and input_handler.cc needs patching."

This measures three things on the shipping `chrome` build:

  1. isTrusted on a CDP-synthesized click (Playwright's page.mouse.click,
     which is Input.dispatchMouseEvent under the hood -- driving through
     Playwright IS driving through that CDP method for this question).
  2. The full pointerdown -> mousedown -> pointerup -> mouseup -> click
     sequence and order actually produced.
  3. Every other readable field on each event: screenX/Y, clientX/Y, button,
     buttons, detail, pointerId, pointerType, isPrimary -- plus a screen-
     bounds sanity check on screenX/Y (SP2 section 5 ties synthesized coords
     to SP4 screen geometry; SP4 has not landed on this checkout, so this
     only checks the coordinates are plausible for the CURRENT, unspoofed
     screen, not that they match a spoofed one).

The mandatory control: the SAME handlers, on the SAME element, also record a
page-JS dispatchEvent() click -- the KNOWN isTrusted === false case. If the
CDP click and the page-JS click report the same isTrusted, the listener is
not reading the flag and every number here must be discarded. This is why
both are captured through the identical recording path rather than two
different probes.

Several repetitions of each are run in the same browser session (not just
one) to rule out isTrusted being a flake rather than a stable read.
"""

import json
import statistics
import sys

import lib_shell
from playwright.sync_api import sync_playwright

REPS = 5

PAGE = """<!doctype html><title>trusted-input</title>
<style>#target{position:fixed;top:150px;left:150px;width:200px;height:100px;background:#333}</style>
<div id="target"></div>
<script>
window.__events = [];
const EVENT_TYPES = ['pointerdown','mousedown','pointerup','mouseup','click'];
const target = document.getElementById('target');
function record(e) {
  window.__events.push({
    type: e.type,
    isTrusted: e.isTrusted,
    screenX: e.screenX, screenY: e.screenY,
    clientX: e.clientX, clientY: e.clientY,
    button: e.button, buttons: e.buttons,
    detail: e.detail,
    pointerId: 'pointerId' in e ? e.pointerId : null,
    pointerType: 'pointerType' in e ? e.pointerType : null,
    isPrimary: 'isPrimary' in e ? e.isPrimary : null,
  });
}
for (const t of EVENT_TYPES) target.addEventListener(t, record);
window.__reset = () => { window.__events = []; };
// The control: a full down/up/click sequence built with dispatchEvent from
// page JS, on the SAME handlers. This is the textbook isTrusted === false
// case -- it never touches the browser process's input pipeline at all.
window.__dispatchJS = (x, y) => {
  const base = {bubbles: true, cancelable: true, view: window,
                clientX: x, clientY: y, screenX: x, screenY: y};
  target.dispatchEvent(new PointerEvent('pointerdown',
    {...base, pointerId: 1, pointerType: 'mouse', isPrimary: true, button: 0, buttons: 1}));
  target.dispatchEvent(new MouseEvent('mousedown', {...base, button: 0, buttons: 1}));
  target.dispatchEvent(new PointerEvent('pointerup',
    {...base, pointerId: 1, pointerType: 'mouse', isPrimary: true, button: 0, buttons: 0}));
  target.dispatchEvent(new MouseEvent('mouseup', {...base, button: 0, buttons: 0}));
  target.dispatchEvent(new MouseEvent('click', {...base, button: 0, buttons: 0, detail: 1}));
};
</script>"""

TARGET_X, TARGET_Y = 250, 200  # center of #target in viewport (CSS) pixels


def run():
    proc = lib_shell.launch(None, shell=lib_shell.CHROME, extra_flags=lib_shell.CHROME_FLAGS)
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{proc.cdp_port}")
            ctx = browser.contexts[0]
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.set_content(PAGE, wait_until="load")

            screen = page.evaluate(
                "() => ({width: window.screen.width, height: window.screen.height, "
                "windowScreenX: window.screenX, windowScreenY: window.screenY})")

            cdp_reps = []
            for _ in range(REPS):
                page.evaluate("window.__reset()")
                page.mouse.click(TARGET_X, TARGET_Y)
                cdp_reps.append(page.evaluate("window.__events"))

            js_reps = []
            for _ in range(REPS):
                page.evaluate("window.__reset()")
                page.evaluate(f"window.__dispatchJS({TARGET_X}, {TARGET_Y})")
                js_reps.append(page.evaluate("window.__events"))

            return screen, cdp_reps, js_reps
    finally:
        lib_shell.shutdown(proc)


def in_bounds(x, y, screen):
    # No SP4 screen-geometry patch exists on this checkout yet, so this
    # checks plausibility against the CURRENT (unspoofed) screen only.
    return 0 <= x <= screen["width"] and 0 <= y <= screen["height"]


def summarise(label, reps, screen):
    sequences = [[e["type"] for e in rep] for rep in reps]
    trusted_flags = [[e["isTrusted"] for e in rep] for rep in reps]
    all_trusted = [t for rep in trusted_flags for t in rep]
    bounds = [
        in_bounds(e["screenX"], e["screenY"], screen)
        for rep in reps for e in rep
    ]
    return {
        "label": label,
        "reps": len(reps),
        "sequences_per_rep": sequences,
        "sequence_stable": len(set(tuple(s) for s in sequences)) == 1,
        "isTrusted_per_event_all_reps": all_trusted,
        "isTrusted_stable": len(set(all_trusted)) == 1,
        "isTrusted": all_trusted[0] if all_trusted else None,
        "screenXY_in_bounds_all_events": all(bounds) if bounds else None,
        "fields_first_rep": reps[0] if reps else [],
    }


def main():
    try:
        screen, cdp_reps, js_reps = run()
    except Exception as exc:  # noqa: BLE001 - a harness fault, not a measurement outcome
        print(json.dumps({"measurement": "sp2b-4-trusted-input", "error": str(exc)}, indent=2))
        sys.exit(1)

    cdp = summarise("CDP click (page.mouse.click -> Input.dispatchMouseEvent)", cdp_reps, screen)
    js = summarise("page-JS dispatchEvent click (control, KNOWN isTrusted=false)", js_reps, screen)

    control_valid = (
        cdp["isTrusted_stable"] and js["isTrusted_stable"]
        and cdp["isTrusted"] != js["isTrusted"]
        and js["isTrusted"] is False
    )

    out = {
        "measurement": "sp2b-4-trusted-input",
        "binary": "chrome",
        "reps": REPS,
        "screen": screen,
        "cdp_click": cdp,
        "control_page_js_click": js,
        "control_valid": control_valid,
    }
    print(json.dumps(out, indent=2))
    sys.exit(0 if control_valid else 1)


if __name__ == "__main__":
    main()

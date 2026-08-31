"""Verifies the SP4a screen dimension + depth spoof: with the seven
screen.* config keys set, screen.width/height/availWidth/availHeight/
availLeft/availTop/colorDepth honor the configured values, and
screen.pixelDepth always mirrors colorDepth. Unconfigured, every one of
these reports the real host values unchanged (rule 5).

One criterion, driven with Playwright's sync API over content_shell's CDP
via lib_shell.session -- the same shape as verify_sp1b.py, a fault in any
one session becomes a FAIL line, never a traceback that discards results
already collected. screen.* is not SecureContext-gated, so no echo_server /
localhost origin is needed here; navigate_to is left at the default (the
initial about:blank page), same as verify_sp0.py.

  S1a screen dimensions + depth: with the seven screen.* keys configured
     (width 1920, height 1080, availWidth 1920, availHeight 1040,
     availLeft 0, availTop 0, colorDepth 30), a page reads EXACTLY that
     tuple for width/height/availWidth/availHeight/availLeft/availTop/
     colorDepth, and pixelDepth === colorDepth (30, not the stock 24 --
     colorDepth carries both, no separate pixelDepth key exists).
     Unconfigured, every one of the eight values is a plain number,
     pixelDepth still mirrors colorDepth (the stock invariant, unrelated to
     configuration), and the real (unconfigured) colorDepth and availHeight
     do NOT coincide with the configured 30 / 1040 -- the discriminating
     check that makes RED non-vacuous: an unhooked build reporting the real
     screen could otherwise pass by accident if the real box happened to
     already report 30-bit colour or a 1040px available height. availLeft /
     availTop are NOT required to discriminate: a real headless display is
     very likely already at (0, 0), so an equal real/configured value there
     is expected, not a sign the hook is missing.

RED-FIRST: run this against a stock/unpatched content_shell (no
Screen::GetRect / Screen::colorDepth edit) and S1a FAILS -- the configured
tuple does not appear; the browser reports the real host screen instead
(recorded in the notes, which is the "stock baseline" this criterion's
unconfigured half checks against on every later run: it is captured live
in this same run, exactly as verify_sp1b.py's `base` is, not read back from
a persisted file). colorDepth 30 and availHeight 1040 are chosen because
they cannot coincidentally match a real display (24-bit colour and a
taller-than-1040 available height are the universal real values), so the
RED failure is guaranteed rather than accidental.

Out of scope here: media_values.cc (CSS device-width/height etc., Task 3)
and screen_orientation.cc (Task 4) are separate criteria in separate
scripts; this file only reads the screen.* Web API surface Task 2 patches.
"""

import json
import sys

import lib_shell

READ_JS = """() => ({
  width: screen.width,
  height: screen.height,
  availWidth: screen.availWidth,
  availHeight: screen.availHeight,
  availLeft: screen.availLeft,
  availTop: screen.availTop,
  colorDepth: screen.colorDepth,
  pixelDepth: screen.pixelDepth,
})"""

CONFIG = json.dumps({
    "screen.width": 1920,
    "screen.height": 1080,
    "screen.availWidth": 1920,
    "screen.availHeight": 1040,
    "screen.availLeft": 0,
    "screen.availTop": 0,
    "screen.colorDepth": 30,
})

# The exact configured tuple every leaf must equal, including pixelDepth --
# there is no separate pixelDepth key, so it is expected to mirror colorDepth.
WANT = {
    "width": 1920,
    "height": 1080,
    "availWidth": 1920,
    "availHeight": 1040,
    "availLeft": 0,
    "availTop": 0,
    "colorDepth": 30,
    "pixelDepth": 30,
}


def read(config):
    """One content_shell session. Returns (obj, err); any fault becomes a
    FAIL, never a traceback."""
    vals, err = lib_shell.session(config, [READ_JS])
    if err is not None:
        return None, err
    return vals[0], None


def failed(obj, err):
    return obj is None or err is not None


def errtxt(obj, err):
    return f"{type(err).__name__}: {err}" if err is not None else "no value"


results = {}
notes = []

base, base_e = read(None)
cfg, cfg_e = read(CONFIG)

S1A = ("S1a screen dims+depth: configured tuple exact incl. pixelDepth==colorDepth; "
       "unconfigured real numbers, pixelDepth==colorDepth, and discriminating")

if failed(base, base_e) or failed(cfg, cfg_e):
    results[S1A] = False
    notes.append(f"S1a: base={errtxt(base, base_e)} configured={errtxt(cfg, cfg_e)}")
else:
    mismatches = {k: {"got": cfg[k], "want": want} for k, want in WANT.items()
                  if cfg[k] != want}
    configured_ok = not mismatches
    pixel_eq_color_configured = cfg["pixelDepth"] == cfg["colorDepth"]

    real_ok = all(isinstance(base[k], (int, float)) and not isinstance(base[k], bool)
                  for k in WANT)
    pixel_eq_color_real = base["pixelDepth"] == base["colorDepth"]
    # Real host values must not coincide with the configured colorDepth /
    # availHeight, or a RED (unhooked) run could pass by accident.
    discriminating = (base["colorDepth"] != WANT["colorDepth"] and
                       base["availHeight"] != WANT["availHeight"])

    results[S1A] = (configured_ok and pixel_eq_color_configured and real_ok and
                     pixel_eq_color_real and discriminating)
    notes.append(f"S1a unconfigured (stock) tuple: {base!r}")
    notes.append(f"S1a configured tuple: {cfg!r}")
    if not results[S1A]:
        notes.append(
            f"S1a: configured_ok={configured_ok} mismatches={mismatches} "
            f"pixel_eq_color(configured)={pixel_eq_color_configured} "
            f"real_all_numbers={real_ok} pixel_eq_color(real)={pixel_eq_color_real} "
            f"discriminating(real colorDepth!=30 and real availHeight!=1040)={discriminating}")

EXPECTED = 1

for name, passed in sorted(results.items()):
    print(f"{'PASS' if passed else 'FAIL'}  {name}")

if len(results) != EXPECTED:
    notes.append(f"expected {EXPECTED} criteria, found {len(results)}")

for note in notes:
    print(f"      {note}")

if results and len(results) == EXPECTED and all(results.values()):
    print("ALL_PASS")
    sys.exit(0)
print("FAIL")
sys.exit(1)

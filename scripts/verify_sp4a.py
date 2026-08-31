"""Verifies the SP4a screen dimension + depth spoof: with the seven
screen.* config keys set, screen.width/height/availWidth/availHeight/
availLeft/availTop/colorDepth honor the configured values, and
screen.pixelDepth always mirrors colorDepth. Unconfigured, every one of
these reports the real host values unchanged (rule 5). It also verifies
that screen.orientation.type/.angle are DERIVED from the spoofed
screen.width/height (Task 4's ScreenOrientation change) rather than a
separate, independently-settable surface.

Four criteria (S1a for the screen.* Web API, S1b for the CSS device-* media
features it must agree with, S2 for orientation derived from spoofed dims,
S3 for a stray non-existent config key being ignored), each driven with
Playwright's sync API over content_shell's CDP via lib_shell.session -- the
same shape as verify_sp1b.py, a fault in any one session becomes a FAIL
line, never a traceback that discards results already collected. screen.*
is not SecureContext-gated, so no echo_server / localhost origin is needed
here; navigate_to is left at the default (the initial about:blank page),
same as verify_sp0.py.

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

  S1b CSS device-width/device-height agreement: with screen.width/height
     configured to 1920/1080 (the same CONFIG as S1a), matchMedia
     '(device-width: 1920px)' and '(device-height: 1080px)' both match, the
     wrong-value probes '(device-width: 1280px)' / '(device-height: 800px)'
     both do NOT match, and a matchMedia query built from the live
     screen.width value itself matches -- CSS device-* and JS screen.* can
     never read two different numbers. This is what MediaValues::
     CalculateDeviceWidth/Height (Task 3) closes; Task 2's screen.cc alone
     leaves CSS reading the real host size while JS reads the spoofed one.

S1b is RED-FIRST the same way, but against media_values.cc: with Task 2's
screen.cc applied and Task 3's media_values.cc NOT yet, dw1920/dh1080/agree
are all false, because CSS device-width/height still evaluate against the
real host rect (e.g. a 1x1 headless screen) while screen.width/height
already read 1920/1080 -- the exact two-surface contradiction Task 3 closes.

  S2 orientation derives from spoofed dims: with only screen.width/height
     configured (1920x1080, a wider-than-tall pair), screen.orientation.type
     reads 'landscape-primary' and .angle reads 0; with the pair swapped
     (1080x1920, taller-than-wide), type reads 'portrait-primary' and angle
     still reads 0. There is no screen.orientation config key -- Task 4
     derives the value from width/height alone, so this is the only way to
     drive it.

S2 is RED-FIRST against screen_orientation.cc before Task 4's edit: type()/
angle() return the stored type_/angle_ (whatever ScreenOrientationController
set from the real host display), not a value derived from the configured
1920x1080 pair, so with a headless host that is not already exactly
1920x1080-shaped landscape, S2 fails.

  S3 stray config key is ignored: adding a bogus "screen.orientation":
     "portrait-primary" entry alongside width:1920/height:1080 does not
     change screen.orientation.type -- it still reads 'landscape-primary',
     derived from the dims. There is no such config key; camoucfg's
     UnrecognisedKeys() surfaces it as unrecognised (a load-time hard-reject
     is SP5a's validator, out of SP4a scope), but Task 4's derivation must
     not accidentally special-case or honor it either.

S3 is RED-FIRST for the same reason S2 is: pre-Task-4, type() reads the
stored type_ regardless of any screen.* config, so it reflects the real host
display rather than 'landscape-primary', and the stray key is moot because
nothing derives from width/height at all yet.
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

MEDIA_JS = """() => ({
  dw1920: matchMedia('(device-width: 1920px)').matches,
  dwWrong: matchMedia('(device-width: 1280px)').matches,
  dh1080: matchMedia('(device-height: 1080px)').matches,
  dhWrong: matchMedia('(device-height: 800px)').matches,
  agree: matchMedia('(device-width: ' + screen.width + 'px)').matches,
})"""

# Every leaf's expected value with the same CONFIG as S1a (screen.width:1920,
# screen.height:1080) applied.
MEDIA_WANT = {
    "dw1920": True,
    "dwWrong": False,
    "dh1080": True,
    "dhWrong": False,
    "agree": True,
}

ORIENTATION_JS = """() => ({
  type: screen.orientation.type,
  angle: screen.orientation.angle,
})"""

# S2: only width/height set (landscape pair, then the same pair swapped to
# portrait). No screen.orientation key exists -- orientation is derived.
CONFIG_LANDSCAPE = json.dumps({
    "screen.width": 1920,
    "screen.height": 1080,
})

CONFIG_PORTRAIT = json.dumps({
    "screen.width": 1080,
    "screen.height": 1920,
})

# S3: same landscape pair as CONFIG_LANDSCAPE, plus a bogus key that names no
# real config surface. Must be ignored -- derivation from dims wins.
CONFIG_STRAY_KEY = json.dumps({
    "screen.width": 1920,
    "screen.height": 1080,
    "screen.orientation": "portrait-primary",
})


def read(config):
    """One content_shell session. Returns (obj, err); any fault becomes a
    FAIL, never a traceback."""
    vals, err = lib_shell.session(config, [READ_JS])
    if err is not None:
        return None, err
    return vals[0], None


def read_media(config):
    """Same shape as read(), for the matchMedia device-*/screen.width probes."""
    vals, err = lib_shell.session(config, [MEDIA_JS])
    if err is not None:
        return None, err
    return vals[0], None


def read_orientation(config):
    """Same shape as read(), for screen.orientation.type/.angle."""
    vals, err = lib_shell.session(config, [ORIENTATION_JS])
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

media, media_e = read_media(CONFIG)

S1B = ("S1b CSS device-width/height agree with screen.width/height: matchMedia "
       "device-width:1920/device-height:1080 true, wrong values false, agree true")

if failed(media, media_e):
    results[S1B] = False
    notes.append(f"S1b: configured={errtxt(media, media_e)}")
else:
    media_mismatches = {k: {"got": media[k], "want": want}
                         for k, want in MEDIA_WANT.items() if media[k] != want}
    results[S1B] = not media_mismatches
    notes.append(f"S1b configured matchMedia tuple: {media!r}")
    if not results[S1B]:
        notes.append(f"S1b: mismatches={media_mismatches}")

land, land_e = read_orientation(CONFIG_LANDSCAPE)
port, port_e = read_orientation(CONFIG_PORTRAIT)

S2 = ("S2 screen.orientation derives from spoofed dims: 1920x1080 -> "
      "landscape-primary/0, 1080x1920 -> portrait-primary/0")

if failed(land, land_e) or failed(port, port_e):
    results[S2] = False
    notes.append(f"S2: landscape={errtxt(land, land_e)} portrait={errtxt(port, port_e)}")
else:
    land_ok = land["type"] == "landscape-primary" and land["angle"] == 0
    port_ok = port["type"] == "portrait-primary" and port["angle"] == 0
    results[S2] = land_ok and port_ok
    notes.append(f"S2 landscape config (1920x1080) orientation: {land!r}")
    notes.append(f"S2 portrait config (1080x1920) orientation: {port!r}")
    if not results[S2]:
        notes.append(f"S2: land_ok={land_ok} port_ok={port_ok}")

stray, stray_e = read_orientation(CONFIG_STRAY_KEY)

S3 = ("S3 stray 'screen.orientation' config key is ignored: derivation from "
      "dims wins (1920x1080 + stray key -> landscape-primary, not the "
      "stray's portrait-primary)")

if failed(stray, stray_e):
    results[S3] = False
    notes.append(f"S3: configured={errtxt(stray, stray_e)}")
else:
    results[S3] = stray["type"] == "landscape-primary"
    notes.append(f"S3 stray-key config orientation: {stray!r}")
    if not results[S3]:
        notes.append(f"S3: got type={stray['type']!r} want 'landscape-primary'")

EXPECTED = 4

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

"""Verifies the SP4-fonts Task 2 metric-probe gate: with "fonts:list"
configured, an unlisted but host-PRESENT specific font-family can no longer be
detected via canvas measureText -- it resolves exactly as the generic fallback
would, in both the window and a dedicated Worker/OffscreenCanvas -- while a
listed family and the CSS generics themselves render unchanged.

Three criteria, driven with Playwright's sync API over content_shell's CDP via
lib_shell.session -- the same shape as verify_sp1b.py: a fault in a session
becomes a FAIL line, never a traceback that discards results already
collected. No echo_server/secure-context origin is needed -- measureText and
Worker/OffscreenCanvas are not [SecureContext]-gated, so every session runs on
content_shell's default about:blank page (session()'s navigate_to=None).

  F1 window probe: with LISTED_FAMILY (present on the host, in fonts:list)
     and UNLISTED_FAMILY (present on the host, NOT in fonts:list) requested
     with a "monospace" fallback, measureText('mmmmwwwwiiii') for LISTED_FAMILY
     stays DISTINCT from the pure-fallback width (the real face still renders);
     for UNLISTED_FAMILY it now EQUALS the fallback width exactly (the host
     face is hidden by the gate, so the request falls through to the generic
     fallback in the CSS family list).
  F2 generics render: the TRUE CSS generic keywords serif and monospace
     (unquoted -- see note below) measure DIFFERENT widths, both non-zero,
     under the SAME fonts:list config as F1. This proves the gate -- which
     only applies to `!font_family.FamilyIsGeneric()` families -- never
     touches a generic, even while a restrictive allowlist is active.
  F3 worker parity: the identical listed/unlisted/fallback measurement, taken
     inside a dedicated Worker via OffscreenCanvas (no DOM canvas available
     off-main-thread), reproduces F1's own correctness verdict in the worker
     (listed distinct from fallback, unlisted equals fallback) AND matches the
     window's F1 numbers exactly -- the gate lives in
     FontCache::Get().GetFontData(), a path both CSSFontSelector (window) and
     OffscreenFontSelector (worker) share, so there is no window-only or
     worker-only inconsistency to exploit. F3 asserts the worker's OWN
     correctness, not bare parity: pre-patch, window and worker both leak the
     unlisted family IDENTICALLY, so a parity-only check would read GREEN even
     though nothing is actually blocked -- exactly the "guard that only
     answers the question it was asked" trap this repo's CLAUDE.md warns
     about. F3 checks both, so it cannot pass by the two sides agreeing to be
     equally wrong.

QUOTING NOTE (why F1/F3 quote their family names but F2 does not): a
font-family value is only parsed as one of the five CSS-generic keywords when
UNQUOTED; a quoted string ('"serif"') is a specific/non-generic family literal
requesting a real font named that. Empirically, on this Linux host, fontconfig
independently aliases the strings "serif"/"sans-serif"/"monospace" to real
installed faces even when Blink asks for them as ordinary (non-generic, quoted)
family names -- so a version of F2 built on the SAME quoted w() helper as F1
happens to pass unpatched, but goes RED after this patch lands: the gate would
then treat quoted "serif"/"monospace" as ordinary specific families, see they
are absent from fonts:list, and block them too, collapsing both to the same
fallback width. F2 therefore measures the true UNQUOTED generic keywords
directly (wu()), which the CSS parser tags FamilyIsGeneric()==true and the
gate unconditionally skips -- the correct way to prove generics are
unaffected. (Caught empirically with scratch probes against this task's
baseline build before writing this file -- not asserted from spec reading
alone.)

RED-FIRST: run this against the current (unpatched) content_shell and F1 goes
RED -- UNLISTED_FAMILY's measured width differs from the fallback in BOTH the
window and the worker, because the host face still resolves with no gate to
stop it. F2 already PASSES unpatched (generics were never gated). After both
selector edits land and content_shell rebuilds, all three go GREEN.
"""

import json
import sys

import lib_shell

# Two REAL families confirmed present on the build host (`fc-list : family`):
# LISTED_FAMILY goes in the fonts:list config (stays visible); UNLISTED_FAMILY
# does not (gets hidden). Both are ordinary proportional/sans faces, not
# monospace ones, so their rendered width is expected to differ from the
# monospace generic's fallback width pre-patch -- the RED signal F1 needs.
LISTED_FAMILY = "DejaVu Sans"
UNLISTED_FAMILY = "Ubuntu"

CONFIG = json.dumps({"fonts:list": [LISTED_FAMILY]})

# w(): requests `family` (quoted -- a specific, non-generic family literal)
# with a trailing unquoted `monospace` fallback. Used for LISTED_FAMILY,
# UNLISTED_FAMILY and the F1/F3 "mono" reference measurement (see the
# QUOTING NOTE above for why "mono" measured this way is still a valid
# reference: its own quoted-literal lookup is gate-blocked post-patch same as
# any other unlisted name, and it falls through to the identical trailing
# unquoted `monospace` generic either way, so the number is patch-invariant).
#
# wu(): requests `family` UNQUOTED -- the true CSS generic keyword path,
# FamilyIsGeneric()==true, never touched by the gate. Used only for F2.
WINDOW_JS = """() => {
  function w(family){
    const c = document.createElement('canvas').getContext('2d');
    c.font = '40px "' + family + '", monospace';
    return c.measureText('mmmmwwwwiiii').width;
  }
  function wu(family){
    const c = document.createElement('canvas').getContext('2d');
    c.font = '40px ' + family;
    return c.measureText('mmmmwwwwiiii').width;
  }
  return {
    listed: w('%s'),
    unlisted: w('%s'),
    mono: w('monospace'),
    serif_generic: wu('serif'),
    monospace_generic: wu('monospace'),
  };
}""" % (LISTED_FAMILY, UNLISTED_FAMILY)

# F3: identical listed/unlisted/mono measurement inside a dedicated Worker.
# WorkerGlobalScope has no DOM, so no <canvas> -- OffscreenCanvas is the
# off-main-thread equivalent, backed by OffscreenFontSelector::GetFontData
# rather than CSSFontSelector::GetFontData.
WORKER_JS = """() => new Promise((resolve, reject) => {
  const src = `self.onmessage = () => {
    function w(family){
      const c = new OffscreenCanvas(300, 60).getContext('2d');
      c.font = '40px "' + family + '", monospace';
      return c.measureText('mmmmwwwwiiii').width;
    }
    try {
      self.postMessage({ok: true, listed: w('%s'), unlisted: w('%s'), mono: w('monospace')});
    } catch (e) { self.postMessage({ok: false, err: String(e)}); }
  };`;
  try {
    const wk = new Worker(URL.createObjectURL(
      new Blob([src], {type: 'text/javascript'})));
    wk.onmessage = (e) => resolve(e.data);
    wk.onerror = (e) => reject(new Error(e.message || 'worker error'));
    wk.postMessage('go');
  } catch (e) { reject(e); }
})""" % (LISTED_FAMILY, UNLISTED_FAMILY)


def failed(obj, err):
    return obj is None or err is not None


def errtxt(obj, err):
    return f"{type(err).__name__}: {err}" if err is not None else "no value"


# One session, one fonts:list config, two expressions: the window read (F1+F2)
# and the worker read (F3). A fault becomes (None, exc), never a traceback that
# discards results already collected.
vals, err = lib_shell.session(CONFIG, [WINDOW_JS, WORKER_JS])
if err is not None:
    win, worker = None, None
    win_e = worker_e = err
else:
    win, worker = vals[0], vals[1]
    win_e = worker_e = None

results = {}
notes = []

F1 = "F1 window probe: listed family distinct from fallback; unlisted family equals fallback (hidden)"
F2 = "F2 generics render: serif != monospace generics, both non-zero, under an active fonts:list"
F3 = "F3 worker parity: OffscreenCanvas reproduces F1's verdict AND matches the window's F1 numbers"

# --- F1 ---
if failed(win, win_e):
    results[F1] = False
    notes.append(f"F1: window probe {errtxt(win, win_e)}")
else:
    listed_distinct = win["listed"] != win["mono"]
    unlisted_hidden = win["unlisted"] == win["mono"]
    mono_nonzero = win["mono"] > 0
    results[F1] = listed_distinct and unlisted_hidden and mono_nonzero
    notes.append(
        f"F1 measured: listed({LISTED_FAMILY!r})={win['listed']!r} "
        f"unlisted({UNLISTED_FAMILY!r})={win['unlisted']!r} mono={win['mono']!r}")
    if not results[F1]:
        notes.append(
            f"F1: listed_distinct(listed!=mono)={listed_distinct} "
            f"unlisted_hidden(unlisted==mono)={unlisted_hidden} mono_nonzero={mono_nonzero}")

# --- F2 ---
if failed(win, win_e):
    results[F2] = False
    notes.append(f"F2: window probe {errtxt(win, win_e)}")
else:
    serif = win["serif_generic"]
    mono_g = win["monospace_generic"]
    distinct = serif != mono_g
    nonzero = serif > 0 and mono_g > 0
    results[F2] = distinct and nonzero
    notes.append(f"F2 measured (unquoted generics): serif={serif!r} monospace={mono_g!r}")
    if not results[F2]:
        notes.append(f"F2: distinct(serif!=monospace)={distinct} both_nonzero={nonzero}")

# --- F3 ---
if failed(win, win_e) or failed(worker, worker_e):
    results[F3] = False
    notes.append(f"F3: window={errtxt(win, win_e)} worker={errtxt(worker, worker_e)}")
elif not worker.get("ok", False):
    results[F3] = False
    notes.append(f"F3: worker measurement threw: {worker.get('err')!r}")
else:
    # The worker's OWN correctness verdict -- same shape as F1, evaluated on
    # the worker's own numbers. Required so F3 cannot pass merely because the
    # worker and window agree while BOTH leak the unlisted family (the RED
    # state pre-patch): parity alone is blind to that.
    worker_listed_distinct = worker["listed"] != worker["mono"]
    worker_unlisted_hidden = worker["unlisted"] == worker["mono"]
    listed_match = worker["listed"] == win["listed"]
    unlisted_match = worker["unlisted"] == win["unlisted"]
    mono_match = worker["mono"] == win["mono"]
    results[F3] = (worker_listed_distinct and worker_unlisted_hidden and
                   listed_match and unlisted_match and mono_match)
    notes.append(
        f"F3 worker measured: listed={worker['listed']!r} unlisted={worker['unlisted']!r} "
        f"mono={worker['mono']!r}")
    if not results[F3]:
        notes.append(
            f"F3: worker_listed_distinct(listed!=mono)={worker_listed_distinct} "
            f"worker_unlisted_hidden(unlisted==mono)={worker_unlisted_hidden} "
            f"listed_match={listed_match} unlisted_match={unlisted_match} mono_match={mono_match}")

EXPECTED = 3

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

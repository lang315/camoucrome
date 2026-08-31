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
  F4 availability non-probe (Task 3): document.fonts.check() -- which for a
     plain, non-generic family routes through
     FontSelector::IsPlatformFamilyMatchAvailable ->
     FontCache::IsPlatformFamilyMatchAvailable -> GetFontPlatformData(),
     entirely bypassing Task 2's FontFallbackList gate -- is measured directly
     to see whether it can distinguish UNLISTED_FAMILY (host-present, hidden
     by the metric gate) from a font name that plainly does not exist. F4
     asserts NO observable difference, on two independent axes: (a)
     checkUnlisted == checkAbsent, in both a fonts:list-configured session and
     an unconfigured (stock) one -- check() cannot tell "present but hidden"
     from "never existed"; (b) the full {checkUnlisted, checkListed,
     checkAbsent} triple is IDENTICAL between the configured and stock
     sessions -- turning fonts:list on introduces no new observable behaviour
     on this path at all. This is Task 2's own scenario probed through a
     different predicate, RED-first exactly like F1-F3, but the RED-first
     result was negative (see the note below): F4 is therefore a standing
     regression assertion, not a before/after gate check, and NO Blink code
     was changed for it -- see the note below for why.

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

F4 RED-FIRST FINDING (Task 3, no gate added): probed empirically against the
CURRENT content_shell (Task 2's gate already landed) with a scratch script
before writing this criterion. Measured, with fonts:list=[LISTED_FAMILY]:
  checkUnlisted (UNLISTED_FAMILY, host-present, hidden by the metric gate) = True
  checkListed   (LISTED_FAMILY)                                            = True
  checkAbsent   ("NoSuchFontXYZ123", does not exist on the host)           = True
and identically True/True/True with NO CAMOU_CONFIG at all (stock). F4 could
NOT be made RED: check() answers the same for a real-but-hidden family and a
font name that flatly does not exist, configured or not. Reading
FontFaceSet::check (font_face_set.cc:229-266) explains why this is not a
coincidence: for a plain, non-generic family with no matching @font-face rule
on the page, IsPlatformFamilyMatchAvailable's return value never reaches the
result either way --
  * True  -> `continue` (family treated as satisfied, loop moves on)
  * False -> `font_face_cache->Get(...)` returns null (nothing was ever
    registered under this name) -> the `face && ...` guard is false -> the
    loop ALSO just continues
so `check()` returns true regardless of what the platform-match predicate
answers, for any family string a page did not itself register via
@font-face. Gating IsPlatformFamilyMatchAvailable would change a return value
that this call site provably discards -- an untestable no-op guard, which
this task's brief explicitly says not to ship. No Blink file was modified for
Task 3; F4 stands as a regression assertion (see its body below) that this
stays true and that configuring fonts:list adds no new observable behaviour
on this path.
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

# F4: document.fonts.check() against the same three families -- the unlisted
# (host-present, gate-hidden) family, the listed one, and a name that plainly
# does not exist on the host. Run once inside the fonts:list-configured
# session (with WINDOW_JS/WORKER_JS) and once more in a separate, unconfigured
# (stock, CAMOU_CONFIG unset) session -- F4 compares both.
CHECK_JS = """() => ({
  checkUnlisted: document.fonts.check('40px "%s"'),
  checkListed:   document.fonts.check('40px "%s"'),
  checkAbsent:   document.fonts.check('40px "NoSuchFontXYZ123"'),
})""" % (UNLISTED_FAMILY, LISTED_FAMILY)


def failed(obj, err):
    return obj is None or err is not None


def errtxt(obj, err):
    return f"{type(err).__name__}: {err}" if err is not None else "no value"


# One session, one fonts:list config, three expressions: the window read
# (F1+F2), the worker read (F3), and the configured check() read (F4). A fault
# becomes (None, exc), never a traceback that discards results already
# collected.
vals, err = lib_shell.session(CONFIG, [WINDOW_JS, WORKER_JS, CHECK_JS])
if err is not None:
    win, worker, chk = None, None, None
    win_e = worker_e = chk_e = err
else:
    win, worker, chk = vals[0], vals[1], vals[2]
    win_e = worker_e = chk_e = None

# F4's second half: the SAME check() read taken in a fresh, unconfigured
# (stock, no CAMOU_CONFIG) session -- a separate launch, since config is fixed
# per-session.
stock_vals, stock_err = lib_shell.session(None, [CHECK_JS])
if stock_err is not None:
    chk_stock, chk_stock_e = None, stock_err
else:
    chk_stock, chk_stock_e = stock_vals[0], None

results = {}
notes = []

F1 = "F1 window probe: listed family distinct from fallback; unlisted family equals fallback (hidden)"
F2 = "F2 generics render: serif != monospace generics, both non-zero, under an active fonts:list"
F3 = "F3 worker parity: OffscreenCanvas reproduces F1's verdict AND matches the window's F1 numbers"
F4 = "F4 availability non-probe: check() can't tell unlisted-present from absent; fonts:list changes nothing it reports"

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

# --- F4 ---
if failed(chk, chk_e) or failed(chk_stock, chk_stock_e):
    results[F4] = False
    notes.append(f"F4: configured={errtxt(chk, chk_e)} stock={errtxt(chk_stock, chk_stock_e)}")
else:
    # (a) not a probe: check() answers the SAME for the unlisted (gate-hidden,
    # host-present) family as for a name that plainly does not exist -- in
    # both the configured and the stock session.
    not_a_probe_configured = chk["checkUnlisted"] == chk["checkAbsent"]
    not_a_probe_stock = chk_stock["checkUnlisted"] == chk_stock["checkAbsent"]
    # (b) no new surface: turning fonts:list on changes nothing check() reports.
    no_new_surface = chk == chk_stock
    results[F4] = not_a_probe_configured and not_a_probe_stock and no_new_surface
    notes.append(f"F4 measured: configured={chk!r} stock={chk_stock!r}")
    if not results[F4]:
        notes.append(
            f"F4: not_a_probe_configured(checkUnlisted==checkAbsent)={not_a_probe_configured} "
            f"not_a_probe_stock={not_a_probe_stock} "
            f"no_new_surface(configured==stock)={no_new_surface}")

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

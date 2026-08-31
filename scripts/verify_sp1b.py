"""Verifies the SP1b navigator scalar/near-constant substitution: platform
(N1), appVersion (N2), deviceMemory (N3), the six near-constants (N4),
maxTouchPoints (N5), worker platform parity (N6), and language/languages (N7).
With the matching navigator.* key configured, a page reads EXACTLY the
configured value; unconfigured, it reads the real computed value unchanged
(rule 5) -- and the six near-constants keep real Chrome's fixed strings until an
explicit expert override sets one.

Seven criteria, driven with Playwright's sync API over content_shell's CDP via
lib_shell.session -- the same shape as verify_sp3b.py, a fault in any one
session becomes a FAIL line, never a traceback that discards results already
collected. No SwiftShader: these are navigator scalars, no GL context involved.

  N1 platform: with navigator.platform="Win32", navigator.platform === "Win32";
     unconfigured -> a non-empty real string (recorded).
  N2 appVersion: with navigator.appVersion set, it matches exactly;
     unconfigured -> the real (non-empty) UA-derived string.
  N3 deviceMemory: with navigator.deviceMemory set to a valid bucket that is
     NOT the box's real value, navigator.deviceMemory === that value;
     unconfigured -> a positive number. navigator.deviceMemory is
     [SecureContext]-gated, so every session navigates to a localhost origin
     (127.0.0.1 is potentially-trustworthy) rather than about:blank, where it
     is undefined. content_shell returns the box's UN-bucketed physical memory
     (e.g. 32) rather than the spec's {0.25,0.5,1,2,4,8} bucket that the browser
     process applies in shipping Chrome; the override path is unaffected and the
     configured value is chosen so it cannot coincide with that real number.
  N4 near-constants: UNCONFIGURED, appCodeName==="Mozilla", appName==="Netscape",
     product==="Gecko", productSub==="20030107", vendor==="Google Inc.",
     vendorSub===""; and CONFIGURED, all six keys (appCodeName/appName/product/
     productSub/vendor/vendorSub) are individually reflected.
  N5 maxTouchPoints: with navigator.maxTouchPoints=5, navigator.maxTouchPoints
     === 5 (hooked in NavigatorEvents::maxTouchPoints, core/events/); the
     unconfigured value is recorded. NOT deferred -- maxTouchPoints is a clean
     single accessor, so this is a real pass.
  N6 worker platform parity: a DEDICATED worker reads self.navigator.platform
     (WorkerNavigator has no platform() of its own, so it resolves through
     NavigatorBase::platform()); with navigator.platform="Win32" set it reads
     "Win32", equal to the window. RED against a build without the
     NavigatorBase::platform() hook, where the worker leaks the real host
     platform (e.g. "Linux x86_64") while the window is already spoofed -- the
     self-introduced coherence tell this criterion closes.
  N7 language/languages: with navigator.language="fr-FR" and
     navigator.languages=["fr-FR","fr","en"], navigator.language === "fr-FR" and
     navigator.languages deep-equals that list, and two consecutive reads of
     navigator.languages return the same contents (the override is populated into
     the cached member, so languages() returns a stable reference across calls);
     unconfigured -> navigator.languages is a non-empty array whose first element
     equals navigator.language (the real Accept-Languages, unchanged).

RED-FIRST: run this against a stock/SP3b content_shell (no SP1b edit) and the
configured cases N1-N5 FAIL -- the required red evidence. N6 is RED against a
build carrying the four window-path SP1b edits but NOT the
NavigatorBase::platform() hook: the window is already spoofed, so the worker
leaking the real host platform is the coherence tell N6 exists to catch. N7 is
RED against the Task-2 binary (no navigator_language.cc hook): the configured
language/languages are ignored and the real host locale leaks. The configured
deviceMemory (N3) is deliberately a bucket the build box does not report, so a
real (unhooked) read cannot coincidentally match it.

Out of scope here: the "Request tablet site" desync command (Task 4,
browser_commands.cc) is a chrome/browser menu command, not a page-reachable
surface -- content_shell has no chrome/browser UI, so unlike every criterion
above there is no CDP call that can drive it, the same way SP3a's C9
screen-unchanged criterion has to name a surface (the composited screen) a
page script has no API to read and reach for an out-of-band check instead;
here there is no out-of-band check available either, so this task is verified
by reading the diff (an early return before SetAndroidOsForTabletSite) and a
clean compile of chrome/browser/ui, not by a runtime criterion. Coherence
between navigator.languages and SP1a's Accept-Language header (a different
key) is the profile generator's job, not enforced by these hooks.
"""

import json
import sys

import echo_server
import lib_shell

# One read of every leaf this task touches, so a single session both checks its
# own criterion and proves the configured key did not disturb the others.
READ_JS = """() => ({
  platform: navigator.platform,
  appVersion: navigator.appVersion,
  deviceMemory: navigator.deviceMemory,
  maxTouchPoints: navigator.maxTouchPoints,
  appCodeName: navigator.appCodeName,
  appName: navigator.appName,
  product: navigator.product,
  productSub: navigator.productSub,
  vendor: navigator.vendor,
  vendorSub: navigator.vendorSub,
})"""

N1_PLATFORM = "Win32"
N2_APPVERSION = "5.0 (Windows NT 10.0; Win64; x64)"
# A valid web bucket the build box (high-RAM) does not report; the box's real
# value is captured by the unconfigured read below and asserted != this, so the
# RED run cannot pass N3 by coincidence.
N3_DEVICEMEMORY = 2
N5_MAXTOUCHPOINTS = 5
# N7: a locale distinct from the build box's real one, with a multi-entry list
# whose first element equals navigator.language (the coherent shape a generator
# emits). The RED (unhooked) read leaks the host locale, which is not fr-FR.
N7_LANGUAGE = "fr-FR"
N7_LANGUAGES = ["fr-FR", "fr", "en"]

# Real Chrome's fixed near-constant strings, identical on every platform.
NEAR_CONSTANT_DEFAULTS = {
    "appCodeName": "Mozilla",
    "appName": "Netscape",
    "product": "Gecko",
    "productSub": "20030107",
    "vendor": "Google Inc.",
    "vendorSub": "",
}

# One config that overrides all six near-constants at once, each to a distinct
# non-default value, so N4 exercises the CONFIGURED direction for every one of
# them (M1) rather than vendor alone. The config key is "navigator.<prop>" and
# the read property is that same <prop>.
NEAR_CONSTANT_OVERRIDES = {
    "navigator.appCodeName": "CamouCodeName",
    "navigator.appName": "CamouAppName",
    "navigator.product": "CamouProduct",
    "navigator.productSub": "20200101",
    "navigator.vendor": "Camou Test Vendor",
    "navigator.vendorSub": "camou-sub",
}

# N6: a dedicated worker reports self.navigator.platform. WorkerNavigator has no
# platform() override, so this resolves through NavigatorBase::platform() -- the
# shared path the fix hooks. Reads the window's platform in the same probe so
# the assertion is worker === window === configured, not just a bare literal.
WORKER_PLATFORM_JS = """() => new Promise((resolve, reject) => {
  const src = `self.onmessage = () => {
    try { self.postMessage({worker: self.navigator.platform}); }
    catch (e) { self.postMessage({worker: 'err:' + e}); }
  };`;
  try {
    const w = new Worker(URL.createObjectURL(
      new Blob([src], {type: 'text/javascript'})));
    w.onmessage = (e) => resolve({main: navigator.platform, worker: e.data.worker});
    w.onerror = (e) => reject(new Error(e.message || 'worker error'));
    w.postMessage('go');
  } catch (e) { reject(e); }
})"""

# N7: language + languages in one read, plus a second read of languages so the
# stability of the returned list (a stable cached-member reference) is checked
# in the same session -- two consecutive reads must carry identical contents.
LANGUAGES_JS = """() => ({
  language: navigator.language,
  languages: navigator.languages,
  languages_again: navigator.languages,
})"""


def read(config, base_url):
    """One content_shell session on the localhost origin. Returns (obj, err);
    any fault becomes a FAIL, never a traceback."""
    vals, err = lib_shell.session(config, [READ_JS], navigate_to=base_url)
    if err is not None:
        return None, err
    return vals[0], None


def read_worker(config, base_url):
    """One session that spawns a dedicated worker and returns {main, worker}
    platform strings. A broken worker path leaves the probe promise unresolved,
    which lib_shell.session turns into an (obj=None, err) FAIL, not a hang."""
    vals, err = lib_shell.session(config, [WORKER_PLATFORM_JS], navigate_to=base_url)
    if err is not None:
        return None, err
    return vals[0], None


def read_langs(config, base_url):
    """One session that reads language + languages (twice). Returns (obj, err);
    any fault becomes a FAIL, never a traceback."""
    vals, err = lib_shell.session(config, [LANGUAGES_JS], navigate_to=base_url)
    if err is not None:
        return None, err
    return vals[0], None


results = {}
notes = []

# A localhost origin so navigator.deviceMemory (SecureContext) is exposed; the
# other leaves are origin-independent. The empty Accept-CH list is fine -- this
# task reads none of the UA client hints.
BASE_URL, _headers_for, _stop = echo_server.start([])
try:
    # Unconfigured baseline (feeds N1-N5 real-value checks and N4 defaults).
    base, base_e = read(None, BASE_URL)

    # Configured sessions, one focused key each (N4 sets all six at once).
    p, p_e = read(json.dumps({"navigator.platform": N1_PLATFORM}), BASE_URL)
    a, a_e = read(json.dumps({"navigator.appVersion": N2_APPVERSION}), BASE_URL)
    d, d_e = read(json.dumps({"navigator.deviceMemory": N3_DEVICEMEMORY}), BASE_URL)
    v, v_e = read(json.dumps(NEAR_CONSTANT_OVERRIDES), BASE_URL)
    m, m_e = read(json.dumps({"navigator.maxTouchPoints": N5_MAXTOUCHPOINTS}), BASE_URL)
    # N6: worker platform parity with the window's spoofed platform.
    w6, w6_e = read_worker(json.dumps({"navigator.platform": N1_PLATFORM}), BASE_URL)
    # N7: language + languages configured together (the coherent shape); plus the
    # unconfigured baseline so the real language==languages[0] invariant is checked.
    base_lg, base_lg_e = read_langs(None, BASE_URL)
    lg, lg_e = read_langs(
        json.dumps({"navigator.language": N7_LANGUAGE,
                    "navigator.languages": N7_LANGUAGES}), BASE_URL)
finally:
    _stop()

N1 = "N1 navigator.platform: configured exact; unconfigured real non-empty string"
N2 = "N2 navigator.appVersion: configured exact; unconfigured real non-empty string"
N3 = "N3 navigator.deviceMemory: configured exact; unconfigured a positive number (SecureContext)"
N4 = "N4 near-constants: six Chrome defaults intact unconfigured; all six configured reflected"
N5 = "N5 navigator.maxTouchPoints: configured exact (hooked, not deferred); unconfigured recorded"
N6 = "N6 worker navigator.platform: dedicated worker sees the spoofed platform (equal to the window)"
N7 = "N7 navigator.language/languages: configured exact & stable; unconfigured language is languages[0]"


def failed(obj, err):
    return obj is None or err is not None


def errtxt(obj, err):
    return f"{type(err).__name__}: {err}" if err is not None else "no value"


# --- N1 platform ---
if failed(base, base_e) or failed(p, p_e):
    results[N1] = False
    notes.append(f"N1: base={errtxt(base, base_e)} configured={errtxt(p, p_e)}")
else:
    real = base["platform"]
    exact = p["platform"] == N1_PLATFORM
    real_ok = isinstance(real, str) and len(real) > 0
    results[N1] = exact and real_ok
    notes.append(f"N1 unconfigured platform={real!r}; configured={p['platform']!r}")
    if not results[N1]:
        notes.append(f"N1: exact={exact} (got {p['platform']!r}, want {N1_PLATFORM!r}) "
                     f"real_non_empty={real_ok}")

# --- N2 appVersion ---
if failed(base, base_e) or failed(a, a_e):
    results[N2] = False
    notes.append(f"N2: base={errtxt(base, base_e)} configured={errtxt(a, a_e)}")
else:
    real = base["appVersion"]
    exact = a["appVersion"] == N2_APPVERSION
    real_ok = isinstance(real, str) and len(real) > 0
    results[N2] = exact and real_ok
    notes.append(f"N2 unconfigured appVersion={real!r}")
    if not results[N2]:
        notes.append(f"N2: exact={exact} (got {a['appVersion']!r}, want {N2_APPVERSION!r}) "
                     f"real_non_empty={real_ok}")

# --- N3 deviceMemory ---
if failed(base, base_e) or failed(d, d_e):
    results[N3] = False
    notes.append(f"N3: base={errtxt(base, base_e)} configured={errtxt(d, d_e)}")
else:
    real = base["deviceMemory"]
    exact = d["deviceMemory"] == N3_DEVICEMEMORY
    # content_shell returns un-bucketed physical memory, so the real value is
    # only required to be a positive number, not a spec bucket.
    real_ok = isinstance(real, (int, float)) and not isinstance(real, bool) and real > 0
    # The configured value must differ from the box's real value, or a RED
    # (unhooked) read could match N3_DEVICEMEMORY by coincidence.
    discriminating = real != N3_DEVICEMEMORY
    results[N3] = exact and real_ok and discriminating
    notes.append(f"N3 unconfigured deviceMemory={real!r} (content_shell un-bucketed); "
                 f"configured={d['deviceMemory']!r}")
    if not results[N3]:
        notes.append(f"N3: exact={exact} real_is_positive_number={real_ok} "
                     f"discriminating(real!=configured)={discriminating}")

# --- N4 near-constants ---
if failed(base, base_e) or failed(v, v_e):
    results[N4] = False
    notes.append(f"N4: base={errtxt(base, base_e)} configured={errtxt(v, v_e)}")
else:
    default_mismatches = {k: base[k] for k, want in NEAR_CONSTANT_DEFAULTS.items()
                          if base[k] != want}
    defaults_ok = not default_mismatches
    # Configured direction for ALL SIX near-constants (M1), not vendor alone.
    override_mismatches = {}
    for key, want in NEAR_CONSTANT_OVERRIDES.items():
        prop = key.split(".", 1)[1]
        if v[prop] != want:
            override_mismatches[prop] = {"got": v[prop], "want": want}
    overrides_ok = not override_mismatches
    results[N4] = defaults_ok and overrides_ok
    if not defaults_ok:
        notes.append(f"N4: near-constant defaults changed: {default_mismatches}")
    if not overrides_ok:
        notes.append(f"N4: configured overrides not reflected: {override_mismatches}")
    if results[N4]:
        notes.append("N4 defaults intact (Mozilla/Netscape/Gecko/20030107/Google Inc./'') "
                     "and all six configured overrides reflected")

# --- N5 maxTouchPoints ---
if failed(base, base_e) or failed(m, m_e):
    results[N5] = False
    notes.append(f"N5: base={errtxt(base, base_e)} configured={errtxt(m, m_e)}")
else:
    real = base["maxTouchPoints"]
    exact = m["maxTouchPoints"] == N5_MAXTOUCHPOINTS
    discriminating = real != N5_MAXTOUCHPOINTS
    results[N5] = exact and discriminating
    notes.append(f"N5 unconfigured maxTouchPoints={real!r}; configured={m['maxTouchPoints']!r}")
    if not results[N5]:
        notes.append(f"N5: exact={exact} (got {m['maxTouchPoints']!r}, want {N5_MAXTOUCHPOINTS}) "
                     f"discriminating(real!=configured)={discriminating}")

# --- N6 worker platform parity ---
if failed(w6, w6_e):
    results[N6] = False
    notes.append(f"N6: worker probe {errtxt(w6, w6_e)}")
else:
    worker_ok = w6["worker"] == N1_PLATFORM
    main_ok = w6["main"] == N1_PLATFORM
    parity = w6["worker"] == w6["main"]
    results[N6] = worker_ok and main_ok and parity
    notes.append(f"N6 worker platform={w6['worker']!r} window platform={w6['main']!r}")
    if not results[N6]:
        notes.append(f"N6: worker=={N1_PLATFORM!r}? {worker_ok}; window=={N1_PLATFORM!r}? {main_ok}; "
                     f"parity(worker==window)? {parity}")

# --- N7 language / languages ---
if failed(base_lg, base_lg_e) or failed(lg, lg_e):
    results[N7] = False
    notes.append(f"N7: base={errtxt(base_lg, base_lg_e)} configured={errtxt(lg, lg_e)}")
else:
    lang_exact = lg["language"] == N7_LANGUAGE
    langs_exact = lg["languages"] == N7_LANGUAGES
    # Two consecutive reads must carry identical contents (stable reference).
    stable = lg["languages"] == lg["languages_again"]
    real_langs = base_lg["languages"]
    real_ok = isinstance(real_langs, list) and len(real_langs) > 0
    # Unconfigured invariant: navigator.language is the first of navigator.languages.
    coherent = real_ok and base_lg["language"] == real_langs[0]
    results[N7] = lang_exact and langs_exact and stable and coherent
    notes.append(f"N7 unconfigured language={base_lg['language']!r} languages={real_langs!r}; "
                 f"configured language={lg['language']!r} languages={lg['languages']!r}")
    if not results[N7]:
        notes.append(f"N7: lang_exact={lang_exact} langs_exact={langs_exact} stable={stable} "
                     f"unconfigured_coherent(language==languages[0])={coherent}")

EXPECTED = 7

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

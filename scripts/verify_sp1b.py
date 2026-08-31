"""Verifies the SP1b navigator scalar/near-constant substitution: platform
(N1), appVersion (N2), deviceMemory (N3), the six near-constants (N4), and
maxTouchPoints (N5). With the matching navigator.* key configured, a page reads
EXACTLY the configured value; unconfigured, it reads the real computed value
unchanged (rule 5) -- and the six near-constants keep real Chrome's fixed
strings until an explicit expert override sets one.

Five criteria, driven with Playwright's sync API over content_shell's CDP via
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
     vendorSub===""; and one CONFIGURED example (navigator.vendor) is reflected.
  N5 maxTouchPoints: with navigator.maxTouchPoints=5, navigator.maxTouchPoints
     === 5 (hooked in NavigatorEvents::maxTouchPoints, core/events/); the
     unconfigured value is recorded. NOT deferred -- maxTouchPoints is a clean
     single accessor, so this is a real pass.

RED-FIRST: run this against a stock/SP3b content_shell (no SP1b edit) and the
configured cases N1-N5 FAIL -- the required red evidence. The configured
deviceMemory (N3) is deliberately a bucket the build box does not report, so a
real (unhooked) read cannot coincidentally match it.

Out of scope here (other SP1b tasks): navigator.language/languages (Task 3) and
the "Request tablet site" desync command (Task 4). Coherence between these
leaves and SP1a's UA/Accept-Language is the profile generator's job (different
keys), not enforced by these hooks.
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
N4_VENDOR = "Camou Test Vendor"
N5_MAXTOUCHPOINTS = 5

# Real Chrome's fixed near-constant strings, identical on every platform.
NEAR_CONSTANT_DEFAULTS = {
    "appCodeName": "Mozilla",
    "appName": "Netscape",
    "product": "Gecko",
    "productSub": "20030107",
    "vendor": "Google Inc.",
    "vendorSub": "",
}


def read(config, base_url):
    """One content_shell session on the localhost origin. Returns (obj, err);
    any fault becomes a FAIL, never a traceback."""
    vals, err = lib_shell.session(config, [READ_JS], navigate_to=base_url)
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

    # Configured sessions, one focused key each.
    p, p_e = read(json.dumps({"navigator.platform": N1_PLATFORM}), BASE_URL)
    a, a_e = read(json.dumps({"navigator.appVersion": N2_APPVERSION}), BASE_URL)
    d, d_e = read(json.dumps({"navigator.deviceMemory": N3_DEVICEMEMORY}), BASE_URL)
    v, v_e = read(json.dumps({"navigator.vendor": N4_VENDOR}), BASE_URL)
    m, m_e = read(json.dumps({"navigator.maxTouchPoints": N5_MAXTOUCHPOINTS}), BASE_URL)
finally:
    _stop()

N1 = "N1 navigator.platform: configured exact; unconfigured real non-empty string"
N2 = "N2 navigator.appVersion: configured exact; unconfigured real non-empty string"
N3 = "N3 navigator.deviceMemory: configured exact; unconfigured a positive number (SecureContext)"
N4 = "N4 near-constants: six Chrome defaults intact unconfigured; one configured (vendor) reflected"
N5 = "N5 navigator.maxTouchPoints: configured exact (hooked, not deferred); unconfigured recorded"


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
    vendor_configured = v["vendor"] == N4_VENDOR
    results[N4] = defaults_ok and vendor_configured
    if not defaults_ok:
        notes.append(f"N4: near-constant defaults changed: {default_mismatches}")
    if not vendor_configured:
        notes.append(f"N4: configured vendor got {v['vendor']!r}, want {N4_VENDOR!r}")
    if results[N4]:
        notes.append("N4 defaults intact (Mozilla/Netscape/Gecko/20030107/Google Inc./'') "
                     "and configured vendor reflected")

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

EXPECTED = 5

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

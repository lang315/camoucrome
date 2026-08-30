"""Verifies the SP3b WebGL vendor/renderer string substitution: with
webGl:/webGl2: vendor+renderer configured, a page reading the UNMASKED_*
strings through the WEBGL_debug_renderer_info extension gets EXACTLY the
configured values, the two namespaces stay separated, and an unconfigured
build returns a stable SwiftShader baseline.

Three criteria, driven with Playwright's sync API over content_shell's CDP,
the same shape as verify_sp3a.py -- a fault in any one session becomes a FAIL
line, never a traceback that discards results already collected. All sessions
run under SwiftShader (--use-angle=swiftshader --enable-unsafe-swiftshader) so
the GL context, and therefore the unmasked strings, are host-independent and
reproducible (SP3 spec Section 6).

  V1 baseline stable: with NO config, getParameter(UNMASKED_RENDERER=0x9246)
     and (UNMASKED_VENDOR=0x9245) on a webgl context are identical across two
     launches. (Also captures the SwiftShader baseline strings that V2/V3 then
     prove are absent from spoofed output.)
  V2 substitute (webgl): with webGl:renderer/webGl:vendor set, a webgl context
     returns EXACTLY those two strings, and the SwiftShader baseline strings
     appear NOWHERE in a full getParameter sweep.
  V3 both namespaces: a webgl2 context with webGl2:renderer/webGl2:vendor
     returns those; a webgl context is UNAFFECTED by webGl2: keys (returns
     baseline); and a webgl2 context is UNAFFECTED by webGl: keys (baseline).

RED-FIRST: run this against a stock/SP3a content_shell (no SP3b edit) and V2/V3
FAIL while V1 passes -- the required red evidence. The unmasked strings are only
readable after gl.getExtension('WEBGL_debug_renderer_info'); a session that
cannot get the extension is a FAIL (not a fake pass), matching verify_sp3a's C6
discipline.
"""

import json
import sys

from playwright.sync_api import sync_playwright

import lib_shell

# SwiftShader gives a stable, host-independent GL context so the unmasked
# strings are reproducible; --enable-unsafe-swiftshader is required on current
# Chromium for the fallback to engage at all (SP3 spec Section 6).
GL_FLAGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]

# Distinct, realistic spoof strings per namespace so cross-namespace isolation
# is unambiguous (a webgl2 leak of the webgl value, or vice versa, is visible).
V2_RENDERER = "NVIDIA GeForce RTX 4090"
V2_VENDOR = "Google Inc. (NVIDIA)"
V3_RENDERER = "AMD Radeon RX 7900 XTX"
V3_VENDOR = "Google Inc. (AMD)"

V2CFG = json.dumps({"webGl:renderer": V2_RENDERER, "webGl:vendor": V2_VENDOR})
V3CFG = json.dumps({"webGl2:renderer": V3_RENDERER, "webGl2:vendor": V3_VENDOR})

# Reads the two unmasked strings on the requested context type, plus a full
# sweep of every string-returning (and a broad set of other) getParameter
# pnames JSON-stringified, so a baseline string leaking through ANY parameter
# is caught. Returns {err} if the context or the debug extension is
# unavailable -- never a silent pass.
PROBE = """(type) => {
  const c = document.createElement('canvas'); c.width = 16; c.height = 16;
  const gl = c.getContext(type);
  if (!gl) return { err: 'no-context:' + type };
  const ext = gl.getExtension('WEBGL_debug_renderer_info');
  if (!ext) return { err: 'no-debug-renderer-info-ext' };
  const UNMASKED_VENDOR = 0x9245, UNMASKED_RENDERER = 0x9246;
  const vendor = gl.getParameter(UNMASKED_VENDOR);
  const renderer = gl.getParameter(UNMASKED_RENDERER);
  // A broad pname sweep. Only string-returning pnames can leak a driver
  // string, but we stringify every value so any leak, wherever it surfaces,
  // is a substring hit. Unsupported pnames throw INVALID_ENUM -> caught.
  const pnames = [
    0x1F00, 0x1F01, 0x1F02, 0x8B8C,           // VENDOR, RENDERER, VERSION, SL_VERSION
    0x9245, 0x9246,                           // UNMASKED_VENDOR, UNMASKED_RENDERER
    0x0D33, 0x8869, 0x8DFB, 0x8DFC, 0x8B4D,   // MAX_TEXTURE_SIZE, MAX_VERTEX_ATTRIBS, ...
    0x846E, 0x846D, 0x0BA2, 0x0C22, 0x8B4C,   // ALIASED ranges, viewport, color, ...
    0x1F03, 0x8073, 0x851C, 0x84E8, 0x8B9A,   // EXTENSIONS, MAX_3D..., MAX_CUBE, RENDERBUFFER, ...
  ];
  const sweep = {};
  for (const p of pnames) {
    try {
      const v = gl.getParameter(p);
      sweep['0x' + p.toString(16)] =
        (v && typeof v === 'object' && v.length !== undefined)
          ? Array.from(v) : v;
    } catch (e) { sweep['0x' + p.toString(16)] = 'ERR'; }
  }
  return { vendor, renderer, sweep: JSON.stringify(sweep) };
}
"""


def probe(config, ctx_type):
    """One content_shell session under SwiftShader. Runs PROBE for ctx_type
    ('webgl' or 'webgl2'). Returns (value, err); any fault becomes a FAIL."""
    proc = None
    try:
        proc = lib_shell.launch(config, extra_flags=GL_FLAGS)
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(
                f"http://127.0.0.1:{proc.cdp_port}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("about:blank", wait_until="load")
            return page.evaluate(PROBE, ctx_type), None
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)


results = {}
notes = []

# --- V1: baseline stability (two unconfigured webgl launches) + a webgl2
#         baseline for the V3 cross-isolation checks. ---
b1, b1e = probe(None, "webgl")
b2, b2e = probe(None, "webgl")
bw2, bw2e = probe(None, "webgl2")

# --- V2: webGl: substitution on a webgl context. ---
v2, v2e = probe(V2CFG, "webgl")

# --- V3: webGl2: substitution + cross-namespace isolation. ---
v3g2, v3g2e = probe(V3CFG, "webgl2")        # webgl2 + webGl2: -> spoofed
v3g1x, v3g1xe = probe(V3CFG, "webgl")       # webgl  + webGl2: -> baseline
v2g2x, v2g2xe = probe(V2CFG, "webgl2")      # webgl2 + webGl:  -> baseline

V1 = "V1 unconfigured unmasked strings stable across two launches"
V2 = "V2 webGl:vendor/renderer substituted exactly; baseline absent from sweep"
V3 = "V3 webGl2: substituted; namespaces isolated (webgl<->webgl2)"


def ok(v):
    return v is not None and "err" not in v


base_r = base_v = None      # webgl baseline
base_r2 = base_v2 = None    # webgl2 baseline

# --- V1 ---
if not ok(b1) or not ok(b2):
    results[V1] = False
    for tag, val, err in (("b1", b1, b1e), ("b2", b2, b2e)):
        if not ok(val):
            notes.append(f"V1 {tag}: {val.get('err') if val else f'{type(err).__name__}: {err}'}")
else:
    base_r, base_v = b1["renderer"], b1["vendor"]
    stable = b1["renderer"] == b2["renderer"] and b1["vendor"] == b2["vendor"]
    results[V1] = stable
    if not stable:
        notes.append(f"V1: launch1=({b1['vendor']!r},{b1['renderer']!r}) "
                     f"launch2=({b2['vendor']!r},{b2['renderer']!r})")
    else:
        notes.append(f"V1 baseline: vendor={b1['vendor']!r} renderer={b1['renderer']!r}")

if ok(bw2):
    base_r2, base_v2 = bw2["renderer"], bw2["vendor"]
else:
    notes.append(f"V1 webgl2 baseline: {bw2.get('err') if bw2 else f'{type(bw2e).__name__}: {bw2e}'}")

# --- V2 ---
if not ok(v2):
    results[V2] = False
    notes.append(f"V2: {v2.get('err') if v2 else f'{type(v2e).__name__}: {v2e}'}")
elif base_r is None:
    results[V2] = False
    notes.append("V2: no V1 baseline to check sweep against")
else:
    exact = v2["renderer"] == V2_RENDERER and v2["vendor"] == V2_VENDOR
    absent = base_r not in v2["sweep"] and base_v not in v2["sweep"]
    results[V2] = exact and absent
    if not results[V2]:
        notes.append(f"V2: exact={exact} (got vendor={v2['vendor']!r} "
                     f"renderer={v2['renderer']!r}) baseline_absent={absent}")

# --- V3 ---
v3_parts = []
v3_reasons = []

if not ok(v3g2):
    v3_parts.append(False)
    v3_reasons.append(f"webgl2+webGl2: {v3g2.get('err') if v3g2 else f'{type(v3g2e).__name__}: {v3g2e}'}")
else:
    exact2 = v3g2["renderer"] == V3_RENDERER and v3g2["vendor"] == V3_VENDOR
    absent2 = (base_r2 is None) or (base_r2 not in v3g2["sweep"] and base_v2 not in v3g2["sweep"])
    v3_parts.append(exact2 and absent2)
    if not (exact2 and absent2):
        v3_reasons.append(f"webgl2 spoof exact={exact2} baseline_absent={absent2} "
                          f"(got vendor={v3g2['vendor']!r} renderer={v3g2['renderer']!r})")

# webgl context must be UNAFFECTED by webGl2: keys -> equals webgl baseline
if not ok(v3g1x) or base_r is None:
    v3_parts.append(False)
    v3_reasons.append(f"webgl+webGl2: {v3g1x.get('err') if ok(v3g1x) is False and v3g1x else f'{type(v3g1xe).__name__}: {v3g1xe}' if not ok(v3g1x) else 'no baseline'}")
else:
    iso1 = v3g1x["renderer"] == base_r and v3g1x["vendor"] == base_v
    v3_parts.append(iso1)
    if not iso1:
        v3_reasons.append(f"webgl leaked webGl2: got vendor={v3g1x['vendor']!r} "
                          f"renderer={v3g1x['renderer']!r} (expected baseline)")

# webgl2 context must be UNAFFECTED by webGl: keys -> equals webgl2 baseline
if not ok(v2g2x) or base_r2 is None:
    v3_parts.append(False)
    v3_reasons.append(f"webgl2+webGl: {v2g2x.get('err') if not ok(v2g2x) and v2g2x else f'{type(v2g2xe).__name__}: {v2g2xe}' if not ok(v2g2x) else 'no webgl2 baseline'}")
else:
    iso2 = v2g2x["renderer"] == base_r2 and v2g2x["vendor"] == base_v2
    v3_parts.append(iso2)
    if not iso2:
        v3_reasons.append(f"webgl2 leaked webGl: got vendor={v2g2x['vendor']!r} "
                          f"renderer={v2g2x['renderer']!r} (expected baseline)")

results[V3] = all(v3_parts) and len(v3_parts) == 3
for r in v3_reasons:
    notes.append(f"V3: {r}")

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

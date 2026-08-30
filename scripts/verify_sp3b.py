"""Verifies the SP3b WebGL substitution: the unmasked vendor/renderer strings
(V1-V3) plus the numeric/array getParameter table and blockIfNotDefined
fail-closed behaviour (V4-V5). With webGl:/webGl2: keys configured, a page
reads EXACTLY the configured values, the two namespaces stay separated, and an
unconfigured build returns a stable SwiftShader baseline.

Five criteria, driven with Playwright's sync API over content_shell's CDP,
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
  V4 parameter table: with webGl:parameters set, getParameter returns the
     configured value with the JS type stock returns for that pname -- an int
     (MAX_TEXTURE_SIZE) as a number, an int array (MAX_VIEWPORT_DIMS) as an
     Int32Array, a float range (ALIASED_LINE_WIDTH_RANGE) as a Float32Array.
  V5 fail-closed: with webGl:parameters:blockIfNotDefined true, a blockable but
     unconfigured pname (MAX_TEXTURE_SIZE) returns null AND raises INVALID_ENUM
     exactly like a real unsupported enum; with the flag false the same call
     returns the host value.

RED-FIRST: run this against a stock/SP3a content_shell (no SP3b edit) and
V2-V5 FAIL while V1 passes -- the required red evidence. The unmasked strings
are only readable after gl.getExtension('WEBGL_debug_renderer_info'); a session
that cannot get the extension is a FAIL (not a fake pass), matching
verify_sp3a's C6 discipline.
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

# V4: the getParameter table. Decimal pname keys mirror GLParamFrom's
# base::NumberToString(pname). MAX_TEXTURE_SIZE (int scalar), MAX_VIEWPORT_DIMS
# (int array -> Int32Array), ALIASED_LINE_WIDTH_RANGE (float range ->
# Float32Array). The line range [1, 2048] is deliberately unlike any real GL's
# (which is [1, 1]) so V4 is unambiguously red on a build without the table.
V4CFG = json.dumps({"webGl:parameters": {
    "3379": 16384,               # 0x0D33 MAX_TEXTURE_SIZE  (host: 8192)
    "3386": [16384, 16384],      # 0x0D3A MAX_VIEWPORT_DIMS (host: 8192,8192)
    "33902": [1, 2048],          # 0x846E ALIASED_LINE_WIDTH_RANGE (host: 1,1)
}})

# V5: fail-closed. MAX_TEXTURE_SIZE is blockable (NOT in the always-present
# exclude set) and left undefined, so blockIfNotDefined must null it out and
# raise INVALID_ENUM. With the flag false the same read returns the host value.
V5_PNAME = 0x0D33
V5_BLOCK_CFG = json.dumps({"webGl:parameters:blockIfNotDefined": True})
V5_OPEN_CFG = json.dumps({"webGl:parameters:blockIfNotDefined": False})

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

# V4: read the three configured pnames and report each value's exact JS type
# (a typed array must arrive as Int32Array / Float32Array, not a plain array).
PROBE_V4 = """(type) => {
  const c = document.createElement('canvas'); c.width = 16; c.height = 16;
  const gl = c.getContext(type);
  if (!gl) return { err: 'no-context:' + type };
  const read = (p) => {
    const v = gl.getParameter(p);
    const arr = (v && typeof v === 'object' && v.length !== undefined)
      ? Array.from(v) : null;
    return { value: arr !== null ? arr : v, type: typeof v,
             int32: v instanceof Int32Array, float32: v instanceof Float32Array };
  };
  return { max_texture: read(0x0D33), max_viewport: read(0x0D3A),
           line_range: read(0x846E) };
}
"""

# V5: read one pname and report both the returned value and the GL error it
# raised, so a fail-closed null can be distinguished from -- and checked to
# match -- a real unsupported-enum null (both null + INVALID_ENUM).
PROBE_PARAM = """(args) => {
  const c = document.createElement('canvas'); c.width = 16; c.height = 16;
  const gl = c.getContext(args.type);
  if (!gl) return { err: 'no-context:' + args.type };
  while (gl.getError() !== gl.NO_ERROR) {}   // drain any pre-existing error
  const v = gl.getParameter(args.pname);
  const glError = gl.getError();
  const arr = (v && typeof v === 'object' && v.length !== undefined)
    ? Array.from(v) : null;
  return { isNull: v === null, value: arr !== null ? arr : v,
           glError, INVALID_ENUM: gl.INVALID_ENUM };
}
"""


def probe_with(config, probe_js, arg):
    """One content_shell session under SwiftShader. Runs probe_js(arg) in the
    page. Returns (value, err); any fault becomes a FAIL, never a traceback."""
    proc = None
    try:
        proc = lib_shell.launch(config, extra_flags=GL_FLAGS)
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(
                f"http://127.0.0.1:{proc.cdp_port}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("about:blank", wait_until="load")
            return page.evaluate(probe_js, arg), None
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)


def probe(config, ctx_type):
    """Runs the V1-V3 unmasked-string PROBE for ctx_type ('webgl'|'webgl2')."""
    return probe_with(config, PROBE, ctx_type)


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

# --- V4: numeric/array parameter table on a webgl context. ---
v4, v4e = probe_with(V4CFG, PROBE_V4, "webgl")

# --- V5: blockIfNotDefined fail-closed (block) vs open on a webgl context. ---
v5b, v5be = probe_with(V5_BLOCK_CFG, PROBE_PARAM,
                       {"type": "webgl", "pname": V5_PNAME})
v5o, v5oe = probe_with(V5_OPEN_CFG, PROBE_PARAM,
                       {"type": "webgl", "pname": V5_PNAME})

V1 = "V1 unconfigured unmasked strings stable across two launches"
V2 = "V2 webGl:vendor/renderer substituted exactly; baseline absent from sweep"
V3 = "V3 webGl2: substituted; namespaces isolated (webgl<->webgl2)"
V4 = "V4 parameter table: int number + Int32Array + Float32Array as configured"
V5 = "V5 blockIfNotDefined: unconfigured pname -> null+INVALID_ENUM; open -> host"


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

# --- V4: parameter table types ---
if not ok(v4):
    results[V4] = False
    notes.append(f"V4: {v4.get('err') if v4 else f'{type(v4e).__name__}: {v4e}'}")
else:
    mt, mv, lr = v4["max_texture"], v4["max_viewport"], v4["line_range"]
    c_int = mt["type"] == "number" and mt["value"] == 16384
    c_i32 = mv["int32"] and mv["value"] == [16384, 16384]
    c_f32 = lr["float32"] and lr["value"] == [1, 2048]
    results[V4] = c_int and c_i32 and c_f32
    if not results[V4]:
        notes.append(f"V4: int={c_int}(type={mt['type']} value={mt['value']!r}) "
                     f"int32={c_i32}(is={mv['int32']} value={mv['value']!r}) "
                     f"float32={c_f32}(is={lr['float32']} value={lr['value']!r})")

# --- V5: blockIfNotDefined fail-closed vs open ---
if not ok(v5b) or not ok(v5o):
    results[V5] = False
    for tag, val, err in (("block", v5b, v5be), ("open", v5o, v5oe)):
        if not ok(val):
            notes.append(f"V5 {tag}: {val.get('err') if val else f'{type(err).__name__}: {err}'}")
else:
    blocked = v5b["isNull"] and v5b["glError"] == v5b["INVALID_ENUM"]
    opened = (not v5o["isNull"]) and isinstance(v5o["value"], (int, float))
    results[V5] = blocked and opened
    if not results[V5]:
        notes.append(f"V5: blocked={blocked} (isNull={v5b['isNull']} "
                     f"glError={v5b['glError']:#x} want_INVALID_ENUM={v5b['INVALID_ENUM']:#x}) "
                     f"opened={opened} (open value={v5o['value']!r})")

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

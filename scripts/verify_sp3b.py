"""Verifies the SP3b WebGL substitution: the unmasked vendor/renderer strings
(V1-V3), the numeric/array getParameter table and blockIfNotDefined
fail-closed behaviour (V4-V5), the supported-extension whitelist (V6), the
shader precision formats (V7), and the context attributes (V8). With
webGl:/webGl2: keys configured, a page
reads EXACTLY the configured values, the two namespaces stay separated, and an
unconfigured build returns a stable SwiftShader baseline.

Eight criteria, driven with Playwright's sync API over content_shell's CDP,
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
  V6 extension whitelist: with webGl:supportedExtensions set,
     getSupportedExtensions() returns EXACTLY that list, an in-list extension
     is gettable (gate true-branch), and a real out-of-list extension
     (WEBGL_debug_renderer_info) is refused by getExtension (the list and
     getExtension share one gate, so they cannot disagree). Covered on webgl2.
  V7 shader precision: with webGl:shaderPrecisionFormats set, the configured
     (VERTEX_SHADER, HIGH_FLOAT) pair returns the spoofed rangeMin/rangeMax/
     precision; with blockIfNotDefined true an unlisted-but-valid pair returns
     null, and with the flag absent that pair falls back to the host value.
     Covered on webgl2.
  V8 context attributes: with webGl:contextAttributes set,
     getContextAttributes() reflects each configured field (antialias,
     powerPreference, preserveDrawingBuffer); a field left unconfigured (alpha)
     keeps its real boolean value (rule 5). Covered on webgl2.

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
# SHELL_FLAGS first: extra_flags REPLACES lib_shell's default flag list, and
# without --ozone-platform=headless content_shell opens the WSLg X display,
# whose connection drops mid-run ("X connection error received"; the probe
# then sees "Target page, context or browser has been closed"). Measured
# 2026-09-10: V2-V8 failed that way, and passed with the flag restored.
GL_FLAGS = lib_shell.SHELL_FLAGS + [
    "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]

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

# WebGL2 variants: the table + blockIfNotDefined must be proven on a webgl2
# context too. WebGL2's getParameter has its OWN generic-lookup glue (not a
# shared code path with WebGL1 -- only the two pure helpers are shared), so a
# webgl-only V4/V5 would leave that glue unexercised. Same pnames, webGl2: keys.
V4CFG2 = json.dumps({"webGl2:parameters": {
    "3379": 16384, "3386": [16384, 16384], "33902": [1, 2048],
}})
V5_BLOCK_CFG2 = json.dumps({"webGl2:parameters:blockIfNotDefined": True})
V5_OPEN_CFG2 = json.dumps({"webGl2:parameters:blockIfNotDefined": False})

# V6: the supported-extension whitelist. A configured webGl:supportedExtensions
# list is authoritative -- getSupportedExtensions() returns EXACTLY it, an
# in-list extension is gettable, and a real extension NOT in the list
# (WEBGL_debug_renderer_info) is reported unsupported by getExtension (the list
# and getExtension share one gate, so they cannot disagree). The names are real
# WebGL trackers so the in-list getExtension returns a live object; the webgl2
# list is distinct so a namespace leak would be visible.
V6_EXTS = ["EXT_texture_filter_anisotropic", "OES_element_index_uint"]
V6_EXTS2 = ["EXT_texture_filter_anisotropic", "EXT_color_buffer_float"]
V6CFG = json.dumps({"webGl:supportedExtensions": V6_EXTS})
V6CFG2 = json.dumps({"webGl2:supportedExtensions": V6_EXTS2})

# V7: shader precision formats. VERTEX_SHADER (0x8B31=35633) + HIGH_FLOAT
# (0x8DF2=36338) is configured to an unmistakable [100,100,20] (a real GL
# reports [127,127,23] for highp float) so the read is unambiguously spoofed.
# blockIfNotDefined nulls an unlisted-but-valid pair (VERTEX_SHADER, LOW_FLOAT);
# without it that pair falls back to the real value.
V7_KEY = "35633:36338"
V7_VALUE = [100, 100, 20]
V7CFG = json.dumps({"webGl:shaderPrecisionFormats": {V7_KEY: V7_VALUE}})
V7CFG_BLOCK = json.dumps({
    "webGl:shaderPrecisionFormats": {V7_KEY: V7_VALUE},
    "webGl:shaderPrecisionFormats:blockIfNotDefined": True,
})
V7CFG2 = json.dumps({"webGl2:shaderPrecisionFormats": {V7_KEY: V7_VALUE}})
V7CFG2_BLOCK = json.dumps({
    "webGl2:shaderPrecisionFormats": {V7_KEY: V7_VALUE},
    "webGl2:shaderPrecisionFormats:blockIfNotDefined": True,
})

# V8: context attributes. getContextAttributes() reflects each configured
# field; a field left unconfigured keeps its real value (rule 5). antialias
# false / preserveDrawingBuffer true / powerPreference high-performance are the
# spoof; alpha is deliberately UNCONFIGURED so it must equal the unconfigured
# (real) value. preserveDrawingBuffer (real default false) and powerPreference
# (real default "default") are the unambiguous RED discriminators; antialias
# may already be false under SwiftShader. The webGl2: key proves the namespace.
V8_ATTRS = {"antialias": False, "powerPreference": "high-performance",
            "preserveDrawingBuffer": True}
V8CFG = json.dumps({"webGl:contextAttributes": V8_ATTRS})
V8CFG2 = json.dumps({"webGl2:contextAttributes": V8_ATTRS})

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

# V6: the full getSupportedExtensions() list, whether an in-list extension is
# gettable (gate true-branch), and whether a real out-of-list extension is
# refused (gate false-branch -> null). Both share one C++ gate.
PROBE_EXT = """(cfg) => {
  const c = document.createElement('canvas'); c.width = 16; c.height = 16;
  const gl = c.getContext(cfg.type);
  if (!gl) return { err: 'no-context:' + cfg.type };
  const list = gl.getSupportedExtensions();
  return {
    list,
    inListNonNull: gl.getExtension(cfg.inList) !== null,
    omittedIsNull: gl.getExtension('WEBGL_debug_renderer_info') === null,
  };
}
"""

# V7: read the configured (VERTEX_SHADER, HIGH_FLOAT) format and an unlisted
# but valid (VERTEX_SHADER, LOW_FLOAT) format. The configured pair must carry
# the spoofed ints; the unlisted pair is null under blockIfNotDefined and a
# real (non-null) object otherwise.
PROBE_PREC = """(cfg) => {
  const c = document.createElement('canvas'); c.width = 16; c.height = 16;
  const gl = c.getContext(cfg.type);
  if (!gl) return { err: 'no-context:' + cfg.type };
  const d = gl.getShaderPrecisionFormat(gl.VERTEX_SHADER, gl.HIGH_FLOAT);
  const other = gl.getShaderPrecisionFormat(gl.VERTEX_SHADER, gl.LOW_FLOAT);
  return {
    defined: d ? { rangeMin: d.rangeMin, rangeMax: d.rangeMax,
                   precision: d.precision } : null,
    otherIsNull: other === null,
  };
}
"""

# V8: read back the honored context attributes. Reports the three spoofed
# fields plus alpha (left unconfigured, so it must equal the unconfigured run)
# and alpha's JS type, so a non-boolean or a changed unset field is caught.
PROBE_ATTRS = """(type) => {
  const c = document.createElement('canvas'); c.width = 16; c.height = 16;
  const gl = c.getContext(type);
  if (!gl) return { err: 'no-context:' + type };
  const a = gl.getContextAttributes();
  if (!a) return { err: 'no-attributes:' + type };
  return {
    antialias: a.antialias, powerPreference: a.powerPreference,
    preserveDrawingBuffer: a.preserveDrawingBuffer,
    alpha: a.alpha, alphaType: typeof a.alpha,
  };
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

# --- V4: numeric/array parameter table on webgl AND webgl2 contexts. ---
v4, v4e = probe_with(V4CFG, PROBE_V4, "webgl")
v4_2, v4_2e = probe_with(V4CFG2, PROBE_V4, "webgl2")

# --- V5: blockIfNotDefined fail-closed (block) vs open on webgl AND webgl2. ---
v5b, v5be = probe_with(V5_BLOCK_CFG, PROBE_PARAM,
                       {"type": "webgl", "pname": V5_PNAME})
v5o, v5oe = probe_with(V5_OPEN_CFG, PROBE_PARAM,
                       {"type": "webgl", "pname": V5_PNAME})
v5b_2, v5b_2e = probe_with(V5_BLOCK_CFG2, PROBE_PARAM,
                           {"type": "webgl2", "pname": V5_PNAME})
v5o_2, v5o_2e = probe_with(V5_OPEN_CFG2, PROBE_PARAM,
                           {"type": "webgl2", "pname": V5_PNAME})

# --- V6: extension whitelist on webgl AND webgl2 contexts. ---
v6, v6e = probe_with(V6CFG, PROBE_EXT,
                     {"type": "webgl", "inList": V6_EXTS[0]})
v6_2, v6_2e = probe_with(V6CFG2, PROBE_EXT,
                         {"type": "webgl2", "inList": V6_EXTS2[0]})

# --- V7: shader precision formats + blockIfNotDefined on webgl AND webgl2. ---
v7, v7e = probe_with(V7CFG, PROBE_PREC, {"type": "webgl"})
v7b, v7be = probe_with(V7CFG_BLOCK, PROBE_PREC, {"type": "webgl"})
v7_2, v7_2e = probe_with(V7CFG2, PROBE_PREC, {"type": "webgl2"})
v7b_2, v7b_2e = probe_with(V7CFG2_BLOCK, PROBE_PREC, {"type": "webgl2"})

# --- V8: context attributes on webgl AND webgl2, each with its unconfigured
#         baseline so an unset field (alpha) can be proven unchanged. ---
v8base, v8basee = probe_with(None, PROBE_ATTRS, "webgl")
v8base2, v8base2e = probe_with(None, PROBE_ATTRS, "webgl2")
v8, v8e = probe_with(V8CFG, PROBE_ATTRS, "webgl")
v8_2, v8_2e = probe_with(V8CFG2, PROBE_ATTRS, "webgl2")

V1 = "V1 unconfigured unmasked strings stable across two launches"
V2 = "V2 webGl:vendor/renderer substituted exactly; baseline absent from sweep"
V3 = "V3 webGl2: substituted; namespaces isolated (webgl<->webgl2)"
V4 = "V4 parameter table (webgl+webgl2): int + Int32Array + Float32Array as configured"
V5 = "V5 blockIfNotDefined (webgl+webgl2): unconfigured pname -> null+INVALID_ENUM; open -> host"
V6 = "V6 supportedExtensions (webgl+webgl2): list is exactly the whitelist; in-list ext gettable; out-of-list ext refused"
V7 = "V7 shaderPrecisionFormats (webgl+webgl2): configured pair spoofed; blockIfNotDefined nulls unlisted pair, else host"
V8 = "V8 contextAttributes (webgl+webgl2): configured antialias/powerPreference/preserveDrawingBuffer reflected; unset alpha unchanged & boolean"
V9 = "V9 worker parity: a WebGL hook fires identically on a dedicated-worker OffscreenCanvas context, not just the main thread"


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

# --- V4: parameter table types (webgl AND webgl2) ---
def v4_checks(r):
    if not ok(r):
        return False, "probe failed"
    mt, mv, lr = r["max_texture"], r["max_viewport"], r["line_range"]
    c_int = mt["type"] == "number" and mt["value"] == 16384
    c_i32 = mv["int32"] and mv["value"] == [16384, 16384]
    c_f32 = lr["float32"] and lr["value"] == [1, 2048]
    return (c_int and c_i32 and c_f32,
            f"int={c_int}(type={mt['type']} value={mt['value']!r}) "
            f"int32={c_i32}(value={mv['value']!r}) "
            f"float32={c_f32}(value={lr['value']!r})")

v4_1_ok, v4_1_why = v4_checks(v4)
v4_2_ok, v4_2_why = v4_checks(v4_2)
results[V4] = v4_1_ok and v4_2_ok
if not results[V4]:
    notes.append(f"V4 webgl: {v4_1_why} | webgl2: {v4_2_why}")

# --- V5: blockIfNotDefined fail-closed vs open (webgl AND webgl2) ---
def v5_checks(vb, vbe, vo, voe):
    if not ok(vb) or not ok(vo):
        bad = vb if not ok(vb) else vo
        err = vbe if not ok(vb) else voe
        return False, (bad.get('err') if bad else f"{type(err).__name__}: {err}")
    blocked = vb["isNull"] and vb["glError"] == vb["INVALID_ENUM"]
    opened = (not vo["isNull"]) and isinstance(vo["value"], (int, float))
    return blocked and opened, (f"blocked={blocked}(isNull={vb['isNull']} "
                                f"glError={vb['glError']:#x}) opened={opened}"
                                f"(value={vo['value']!r})")

v5_1_ok, v5_1_why = v5_checks(v5b, v5be, v5o, v5oe)
v5_2_ok, v5_2_why = v5_checks(v5b_2, v5b_2e, v5o_2, v5o_2e)
results[V5] = v5_1_ok and v5_2_ok
if not results[V5]:
    notes.append(f"V5 webgl: {v5_1_why} | webgl2: {v5_2_why}")


# --- V6: the whitelist governs both getSupportedExtensions and getExtension ---
def v6_checks(r, expected):
    if not ok(r):
        return False, (r.get("err") if r else "probe failed")
    exact = sorted(r["list"]) == sorted(expected)
    return (exact and r["inListNonNull"] and r["omittedIsNull"],
            f"exact={exact}(got={r['list']!r}) "
            f"in_list_gettable={r['inListNonNull']} "
            f"omitted_null={r['omittedIsNull']}")


v6_1_ok, v6_1_why = v6_checks(v6, V6_EXTS)
v6_2_ok, v6_2_why = v6_checks(v6_2, V6_EXTS2)
results[V6] = v6_1_ok and v6_2_ok
if not results[V6]:
    notes.append(f"V6 webgl: {v6_1_why} | webgl2: {v6_2_why}")


# --- V7: configured pair spoofed; block nulls unlisted pair, open falls back ---
SPOOFED = {"rangeMin": 100, "rangeMax": 100, "precision": 20}


def v7_checks(vc, vce, vb, vbe):
    if not ok(vc) or not ok(vb):
        bad, err = (vc, vce) if not ok(vc) else (vb, vbe)
        return False, (bad.get("err") if bad else f"{type(err).__name__}: {err}")
    spoofed = vc["defined"] == SPOOFED
    open_fallback = not vc["otherIsNull"]      # no block -> unlisted pair real
    blocked = vb["otherIsNull"]                # block -> unlisted pair null
    still_spoofed = vb["defined"] == SPOOFED   # block never touches the listed pair
    return (spoofed and open_fallback and blocked and still_spoofed,
            f"spoofed={spoofed}(got={vc['defined']!r}) "
            f"open_fallback={open_fallback} blocked={blocked} "
            f"still_spoofed={still_spoofed}")


v7_1_ok, v7_1_why = v7_checks(v7, v7e, v7b, v7be)
v7_2_ok, v7_2_why = v7_checks(v7_2, v7_2e, v7b_2, v7b_2e)
results[V7] = v7_1_ok and v7_2_ok
if not results[V7]:
    notes.append(f"V7 webgl: {v7_1_why} | webgl2: {v7_2_why}")


# --- V8: configured fields reflected; an unset field (alpha) stays a boolean
#         equal to its unconfigured value (rule 5). vc = configured run, vb =
#         unconfigured baseline for the same context type. ---
def v8_checks(vc, vce, vb, vbe):
    if not ok(vc) or not ok(vb):
        bad, err = (vc, vce) if not ok(vc) else (vb, vbe)
        return False, (bad.get("err") if bad else f"{type(err).__name__}: {err}")
    reflected = (vc["antialias"] is False and
                 vc["powerPreference"] == "high-performance" and
                 vc["preserveDrawingBuffer"] is True)
    unset_ok = vc["alphaType"] == "boolean" and vc["alpha"] == vb["alpha"]
    return reflected and unset_ok, (
        f"reflected={reflected}(antialias={vc['antialias']!r} "
        f"powerPreference={vc['powerPreference']!r} "
        f"preserveDrawingBuffer={vc['preserveDrawingBuffer']!r}) "
        f"unset_alpha_ok={unset_ok}(alpha={vc['alpha']!r} "
        f"baseline_alpha={vb['alpha']!r})")


v8_1_ok, v8_1_why = v8_checks(v8, v8e, v8base, v8basee)
v8_2_ok, v8_2_why = v8_checks(v8_2, v8_2e, v8base2, v8base2e)
results[V8] = v8_1_ok and v8_2_ok
if not results[V8]:
    notes.append(f"V8 webgl: {v8_1_why} | webgl2: {v8_2_why}")

# --- V9: worker parity. A WebGL getParameter hook must fire identically on a
#         dedicated-worker OffscreenCanvas context (config is env-inherited,
#         and the hook resolves the scope via Host()->GetTopExecutionContext()
#         -> the worker global, not GetDocument()). Closes the SP3b whole-branch
#         "WebGL-in-worker parity unverified" gap. ---
PROBE_WORKER = """(arg) => new Promise((resolve, reject) => {
  const readMain = () => {
    const gl = document.createElement('canvas').getContext('webgl');
    return gl ? gl.getParameter(0x0D33) : 'no-gl';  // MAX_TEXTURE_SIZE
  };
  const src = `self.onmessage = () => {
    try { const gl = new OffscreenCanvas(16, 16).getContext('webgl');
      self.postMessage({worker: gl ? gl.getParameter(0x0D33) : 'no-gl'}); }
    catch (e) { self.postMessage({worker: 'err:' + e}); }
  };`;
  try {
    const w = new Worker(URL.createObjectURL(
      new Blob([src], {type: 'text/javascript'})));
    w.onmessage = (e) => resolve({main: readMain(), worker: e.data.worker});
    w.onerror = (e) => reject(new Error(e.message || 'worker error'));
    w.postMessage('go');
  } catch (e) { reject(e); }
})"""
V9CFG = json.dumps({"webGl:parameters": {"3379": 16384}})  # host reports 8192
v9, v9e = probe_with(V9CFG, PROBE_WORKER, None)
if not ok(v9):
    results[V9] = False
    notes.append(f"V9: {v9.get('err') if v9 else f'{type(v9e).__name__}: {v9e}'}")
else:
    # both threads must see the spoofed 16384 (hence differ from host 8192);
    # a worker seeing 8192 would prove the hook does not reach worker scope.
    results[V9] = v9.get("main") == 16384 and v9.get("worker") == 16384
    if not results[V9]:
        notes.append(f"V9: main={v9.get('main')!r} worker={v9.get('worker')!r} "
                     "(worker must equal the spoofed 16384, not host 8192)")

EXPECTED = 9

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

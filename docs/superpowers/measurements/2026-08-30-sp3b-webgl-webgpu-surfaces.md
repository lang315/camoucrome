# SP3b WebGL + WebGPU surface measurements

Measured 2026-08-30 against `~/chromium/src` (HEAD `a727b57805`), read-only `git grep`.
Resolves the SP3 spec §3/§4.1 interception points for the WebGL half (SP3b), which
the canvas half (SP3a) did not touch. Line numbers supersede spec §3's (pinned to
`0e8d4a9268`); most drifted +3.

## WebGL — `webgl_rendering_context_base.cc`

| Surface | Method | Line (spec) |
|---|---|---|
| Numeric/string/array parameter table | `WebGLRenderingContextBase::getParameter(ScriptState*, GLenum pname)` | 3993 (3990) |
| Unmasked renderer / vendor | `case WebGLDebugRendererInfo::kUnmaskedRendererWebgl` / `kUnmaskedVendorWebgl` inside getParameter | 4204 / 4213 (4201/4210) |
| Context attributes | `getContextAttributes()` | 3785 (3782) |
| Shader precision | `getShaderPrecisionFormat()` | 4490 (4487) |
| Extension list | `getSupportedExtensions()` | 4527 (4524) |

**getParameter return typing.** A large `switch (pname)` returning through
`WebGLAny(script_state, value)` and typed helpers `GetIntParameter`,
`GetUnsignedIntParameter`, `GetWebGLFloatArrayParameter`, `GetInt64Parameter`, etc.
The Camoufox port intercepts at the TOP of the function (before the switch) with a
generic config lookup keyed by raw `pname`, returning early when the config carries
that pname — mirror that. The typed-array params (`ALIASED_LINE_WIDTH_RANGE`,
`MAX_VIEWPORT_DIMS`, ...) must be rebuilt with the correct JS array type via the
same helpers, so a spoofed array arrives as a Float32Array/Int32Array, not a plain
Array.

**WebGL1 vs WebGL2 — TWO interception points.**
`WebGL2RenderingContextBase::getParameter` (`webgl2_rendering_context_base.cc:4839`)
has its OWN switch for WebGL2-only pnames and, for anything it does not handle,
delegates to `WebGLRenderingContextBase::getParameter` at `:5053`. So a shared
pname read from a WebGL2 context passes through the WebGL2 switch first, then the
base. Both entry points need the hook, and the `isWebGL2` discriminator selects the
`webGl:` vs `webGl2:` key prefix. (SP3a's canvas hooks did not touch either.)

## WebGPU — `modules/webgpu/gpu_adapter.cc` (SP3 §4.1 obligation, in SP3b scope)

`GPUAdapter` reads the real `wgpu::AdapterInfo info` (`:62`) and populates members:
`vendor_ = String::FromUtf8(info.vendor)` (`:98`), `architecture_` (`:99`), plus
device/description. `CreateAdapterInfoForAdapter()` (`:126`) builds the
page-visible `GPUAdapterInfo` from those members (two `MakeGarbageCollected<
GPUAdapterInfo>` sites, `:133`/`:147`, a compat/full branch); `GPUAdapter::info()`
(`:190`) returns it. `GPUAdapterInfo` getters (`gpu_adapter_info.h`) are
`vendor()/architecture()/device()/description()`.

Interception: substitute `vendor_`/`architecture_`/device/description at population
(`:98`) — everything downstream (GPUAdapterInfo, info()) inherits — keyed by the
SAME `webGl:` config so WebGPU adapter identity agrees with the WebGL strings
(spec §5 invariant). Confirm which of the two GPUAdapterInfo branches a normal page
hits before wiring.

## New camoucfg capability required

`webGl:parameters` / `webGl2:parameters` is a **map keyed by GL enum → typed value**
(int, double, bool, string, or numeric array), not a scalar key. The current
camoucfg reads only scalar keys (`GetString/GetInt32/GetDouble/GetBool/GetStringList`
over a flat `key`). SP3b's first task must add a nested-map accessor (Camoufox's
`MaskConfig::GLParam(pname, isWebGL2)` returning a `variant`), living in camoucfg so
the getParameter hook consults it. `blockIfNotDefined` (a per-namespace bool, a
deliberate rule-5 exception per spec §4.5) rides alongside.

## Consequence for the plan

Structural claims hold. SP3b is larger than SP3a and should split:
- **SP3b-i**: the config-map capability + `webGl:vendor`/`renderer` strings +
  parameter table + `blockIfNotDefined`, WebGL1 + WebGL2. The core GL profile spoof.
- **SP3b-ii**: `supportedExtensions` + `shaderPrecisionFormats` + `contextAttributes`
  + WebGPU adapter coherence + the renderer↔vendor all-or-nothing parse-time
  rejection (spec §5). Final split TBD at planning.

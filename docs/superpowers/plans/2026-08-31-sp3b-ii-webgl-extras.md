# SP3b-ii — WebGL extensions, shader precision, context attributes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the three remaining page-visible WebGL surfaces config-controllable — the supported-extension list, shader precision formats, and context attributes — for both WebGL1 and WebGL2, at the Blink accessor level.

**Architecture:** SP3b-i already added the `GLParam`/`GLVendor`/`GLRenderer`/`GLBlockIfNotDefined` config layer and the getParameter hooks. SP3b-ii adds three more config accessors (`GLExtensions` via the existing string-list reader, `GLShaderPrecision`, `GLContextAttr`) and hooks `getSupportedExtensions`/`IsSupported`, `getShaderPrecisionFormat`, and `getContextAttributes`. Blink edits extend the existing `patches/sp3b-webgl-profile.patch`.

**Tech Stack:** C++17 (Chromium/Blink), GN/gtest, Python+Playwright verify.

## Global Constraints

- C++/Blink only, never injected JS. Keys namespaced (`webGl:`/`webGl2:`, colon). `EveryKeyIsNamespaced` + `EveryDeclaredConstantIsInAllKeys` (two hand-lists in keys.h + keys_unittest.cc's `declared` literal) must stay green — every new key in BOTH, size bumped.
- Rule 5: absent config → real value. `shaderPrecisionFormats` gets a `blockIfNotDefined` per-namespace flag (rule-5 exception, same rationale as parameters, spec §4.5); extensions and contextAttributes do NOT.
- `getSupportedExtensions` returning a config list also governs `IsSupported`/`getExtension` — if a config list is set, an extension NOT in it must report unsupported (Camoufox's `GetStringList` non-empty → that IS the whitelist). Otherwise `getExtension('X')` could hand back an object for an extension the list omits — an incoherence.
- `IsWebGL2()` selects the `webGl:` vs `webGl2:` namespace at every hook (WebGL2 has its own overrides for some of these — confirm per method).
- Extend `patches/sp3b-webgl-profile.patch` via the index-baseline method SP3b-i established (webgl file's git index holds the SP3a baseline; `git diff` yields SP3b-only; webgl2's index is stock). Regenerate `git diff -- <webgl.cc> <webgl2.cc>`, verify 0 SP3a contamination (`grep -c 'readPixels buffer|PerturbRgbaFromConfig'` = 0). apply.sh already lists it.
- `scripts/check_additions_build.py` + `check_checkout_sync.sh` green. `<random>` not relevant.

**Out of scope (→ SP3b-iii):** WebGPU adapter coherence (gpu_adapter.cc) and the renderer↔vendor / WebGL↔WebGPU parse-time coherence validator (spec §5). SP3b-ii exposes the last WebGL knobs; SP3b-iii enforces cross-surface coherence.

**Build/verify environment:** see the SP3b-i plan + `docs/superpowers/measurements/2026-08-30-sp3b-webgl-webgpu-surfaces.md`. WSL checkout as user `lang`; `components_unittests` for camoucfg; `content_shell` + `verify_sp3b.py` (extend it) from `~/camoucrome-verify` under SwiftShader.

---

## File Structure

- `additions/camoucfg/keys.h` + `keys_unittest.cc` — MODIFY: add extension/shaderPrecision/contextAttributes keys (+ `webGl2:` + the shaderPrecision block flag).
- `additions/camoucfg/gl_params.h` / `gl_params.cc` + `mask_config_internal.{h,cc}` — MODIFY: add `GLShaderPrecision(scope, shadertype, precisiontype, is_webgl2)` → `optional<array<int,3>>` and `GLContextAttr(scope, is_webgl2)` → the attributes dict (or per-field getters). Extensions reuse the existing `GetStringList`.
- `additions/camoucfg/gl_params_unittest.cc` — MODIFY: tests for the two new accessors.
- Blink (checkout only → extends `patches/sp3b-webgl-profile.patch`): `webgl_rendering_context_base.cc`, `webgl2_rendering_context_base.cc`.
- `scripts/verify_sp3b.py` — MODIFY: add V6 (extensions), V7 (shader precision), V8 (context attributes); bump EXPECTED to 8.

---

### Task 1: config keys + `GLShaderPrecision` / `GLContextAttr` accessors

**Files:** Modify keys.h, keys_unittest.cc, gl_params.h/.cc, mask_config_internal.h/.cc, gl_params_unittest.cc, BUILD.gn (no new files).

**Interfaces:**
- Consumes: the `internal::ParsedConfig()` + `base::DictValue` pattern from SP3b-i.
- Produces keys: `kWebGlExtensions="webGl:supportedExtensions"` (+`webGl2:`), `kWebGlShaderPrecision="webGl:shaderPrecisionFormats"` (+`webGl2:`), `kWebGlShaderPrecisionBlock="webGl:shaderPrecisionFormats:blockIfNotDefined"` (+`webGl2:`), `kWebGlContextAttrs="webGl:contextAttributes"` (+`webGl2:`). (8 keys.)
- Produces accessors:
  - `std::optional<std::array<int, 3>> camoucfg::GLShaderPrecision(const ConfigScope&, uint32_t shadertype, uint32_t precisiontype, bool is_webgl2);` — reads the `webGl:shaderPrecisionFormats` map keyed by the string `"<shadertype>:<precisiontype>"` (decimal), value `[rangeMin, rangeMax, precision]`.
  - `bool camoucfg::GLShaderPrecisionBlock(const ConfigScope&, bool is_webgl2);`
  - `const base::Value::Dict* camoucfg::GLContextAttrs(const ConfigScope&, bool is_webgl2);` — returns the `webGl:contextAttributes` dict (or nullptr); callers read individual bool/string fields. (Keep the same internal-injectable split: `internal::GLShaderPrecisionFrom(dict, ...)`, `internal::GLContextAttrsFrom(dict, is_webgl2)`.)

- [ ] **Step 1: Write failing tests** (extend gl_params_unittest.cc)

```cpp
TEST(GLParamsTest, ReadsShaderPrecision) {
  auto cfg = Parse(R"({"webGl:shaderPrecisionFormats":{"35633:36338":[127,127,23]}})");
  // 35633 VERTEX_SHADER, 36338 HIGH_FLOAT
  auto v = internal::GLShaderPrecisionFrom(cfg, 35633, 36338, false);
  ASSERT_TRUE(v.has_value());
  EXPECT_EQ((*v)[0], 127); EXPECT_EQ((*v)[2], 23);
  EXPECT_FALSE(internal::GLShaderPrecisionFrom(cfg, 35633, 36338, true).has_value());  // webGl2 unset
  EXPECT_FALSE(internal::GLShaderPrecisionFrom(Parse("{}"), 35633, 36338, false).has_value());
}

TEST(GLParamsTest, ShaderPrecisionRejectsMalformed) {
  // wrong-length or non-int array -> nullopt, not a partial/garbage array
  EXPECT_FALSE(internal::GLShaderPrecisionFrom(
      Parse(R"({"webGl:shaderPrecisionFormats":{"1:2":[1,2]}})"), 1, 2, false).has_value());
  EXPECT_FALSE(internal::GLShaderPrecisionFrom(
      Parse(R"({"webGl:shaderPrecisionFormats":{"1:2":[1,2,"x"]}})"), 1, 2, false).has_value());
}

TEST(GLParamsTest, ReadsContextAttrs) {
  auto cfg = Parse(R"({"webGl:contextAttributes":{"antialias":false,"powerPreference":"high-performance"}})");
  const base::Value::Dict* d = internal::GLContextAttrsFrom(cfg, false);
  ASSERT_NE(d, nullptr);
  EXPECT_EQ(d->FindBool("antialias"), std::optional<bool>(false));
  EXPECT_EQ(*d->FindString("powerPreference"), "high-performance");
  EXPECT_EQ(internal::GLContextAttrsFrom(cfg, true), nullptr);  // webGl2 unset
}
```

- [ ] **Step 2: Run → compile-fail RED** (`unittests 'GLParamsTest.*'`; functions undeclared).

- [ ] **Step 3: Implement `internal::GLShaderPrecisionFrom` / `GLShaderPrecisionBlockFrom` / `GLContextAttrsFrom`** in mask_config_internal.cc:

```cpp
std::optional<std::array<int,3>> GLShaderPrecisionFrom(
    const base::DictValue& cfg, uint32_t st, uint32_t pt, bool is_webgl2) {
  const base::Value::Dict* m = cfg.FindDict(
      is_webgl2 ? "webGl2:shaderPrecisionFormats" : "webGl:shaderPrecisionFormats");
  if (!m) return std::nullopt;
  const base::Value* v = m->Find(base::NumberToString(st) + ":" +
                                 base::NumberToString(pt));
  if (!v || !v->is_list() || v->GetList().size() != 3) return std::nullopt;
  std::array<int,3> out{};
  for (int i = 0; i < 3; ++i) {
    if (!v->GetList()[i].is_int()) return std::nullopt;
    out[i] = v->GetList()[i].GetInt();
  }
  return out;
}
bool GLShaderPrecisionBlockFrom(const base::DictValue& cfg, bool is_webgl2) {
  return cfg.FindBool(is_webgl2 ? "webGl2:shaderPrecisionFormats:blockIfNotDefined"
                                : "webGl:shaderPrecisionFormats:blockIfNotDefined")
      .value_or(false);
}
const base::Value::Dict* GLContextAttrsFrom(const base::DictValue& cfg, bool is_webgl2) {
  return cfg.FindDict(is_webgl2 ? "webGl2:contextAttributes" : "webGl:contextAttributes");
}
```
Public one-line wrappers in gl_params.cc over `ParsedConfig()`. Add the 8 keys to keys.h (both hand-lists, size bump). Extensions need no new accessor — the existing `GetStringList(scope, keys::kWebGlExtensions)` serves.

- [ ] **Step 4: Run → GREEN** (`unittests 'GLParamsTest.*:CamoucfgKeysTest.*'`), then `check_additions_build.py` PASS. Commit: `feat(sp3b): shaderPrecision/contextAttributes/extension keys + accessors`.

---

### Task 2: `getSupportedExtensions` + `getShaderPrecisionFormat` hooks

**Files:** Modify (checkout) webgl_rendering_context_base.cc (+ webgl2 if it overrides these); Modify scripts/verify_sp3b.py, patches/sp3b-webgl-profile.patch.

**Measure-then-implement.**

- [ ] **Step 1: Locate** `getSupportedExtensions()` (measured :4527, returns `std::optional<Vector<String>>`) and `IsSupported`/`ExtensionSupportedAndAllowed`; and `getShaderPrecisionFormat()` (returns `WebGLShaderPrecisionFormat*`). Confirm whether WebGL2 overrides either (likely inherits the base — verify).

- [ ] **Step 2: Extend verify_sp3b.py** — V6 extensions: with `{"webGl:supportedExtensions":["EXT_a","OES_b"]}`, `gl.getSupportedExtensions()` returns EXACTLY that list, and `gl.getExtension('SOME_REAL_EXT_NOT_IN_LIST')` returns null (whitelist coherence). V7 shaderPrecision: with a config entry for (VERTEX_SHADER, HIGH_FLOAT), `gl.getShaderPrecisionFormat(...)` returns the configured rangeMin/rangeMax/precision; with `blockIfNotDefined` true and an unlisted pair, returns null. RED-first on the Task-1/SP3b-i binary (V6/V7 fail).

- [ ] **Step 3: Implement.**
  - `getSupportedExtensions`: if `GetStringList(scope, kWebGl*Extensions)` non-empty, return that Vector<String> (converted) instead of the enumerated set. `IsSupported`/`getExtension`: when a config list is set, return supported only if the extension name is in the list (so `getExtension` agrees).
  - `getShaderPrecisionFormat(shadertype, precisiontype)`: if `GLShaderPrecision(scope, shadertype, precisiontype, IsWebGL2())` set, return `MakeGarbageCollected<WebGLShaderPrecisionFormat>(...)` (confirm ctor) with the 3 configured ints; else if `GLShaderPrecisionBlock(scope, IsWebGL2())`, return nullptr; else real.

- [ ] **Step 4: Build + verify GREEN (V1-V7); re-extract patch (index-baseline); regression verify_sp3a ALL_PASS.** Commit: `feat(sp3b): spoof WebGL supportedExtensions + shaderPrecisionFormats`.

---

### Task 3: `getContextAttributes` hook

**Files:** Modify (checkout) webgl_rendering_context_base.cc; Modify scripts/verify_sp3b.py, patches/sp3b-webgl-profile.patch.

- [ ] **Step 1: Extend verify_sp3b.py** — V8: with `{"webGl:contextAttributes":{"antialias":false,"powerPreference":"high-performance","preserveDrawingBuffer":true}}`, `gl.getContextAttributes()` reflects each configured field; unset fields keep their real value. RED-first.

- [ ] **Step 2: Implement** — in `getContextAttributes()`, after `result = ToWebGLContextAttributes(CreationAttributes())` and the depth/stencil/antialias adjustments, apply config overrides: for each field present in `GLContextAttrs(scope, IsWebGL2())`, call the matching `result->set*` (bool fields: alpha/depth/stencil/antialias/premultipliedAlpha/preserveDrawingBuffer/failIfMajorPerformanceCaveat/desynchronized/xrCompatible; `powerPreference` string → the `V8GLPowerPreference` enum: "default"/"low-power"/"high-performance"). Absent fields untouched (rule 5). Get the ExecutionContext via `Host()->GetTopExecutionContext()`.

- [ ] **Step 3: Build + verify GREEN (V1-V8); re-extract patch; regression verify_sp3a ALL_PASS + camoucfg unit green.** Commit: `feat(sp3b): spoof WebGL contextAttributes`.

---

## Self-Review

- Spec §3 extensions/shaderPrecision/contextAttributes → Tasks 2, 3; §4.5 shaderPrecision blockIfNotDefined → Task 2 (default false). WebGPU + §5 coherence → SP3b-iii (out-of-scope stated).
- Placeholder scan: config accessors carry complete code; Blink glue is measure-then-implement with interception point + config call + the exact set/ctor to use, matching SP3b-i's proven style. The `WebGLShaderPrecisionFormat` ctor and the `powerPreference` enum symbol are the two live-tree confirmations the implementer must make.
- Type consistency: `GLShaderPrecision`→`optional<array<int,3>>`, `GLShaderPrecisionBlock`→`bool`, `GLContextAttrs`→`const Dict*`; extensions via existing `GetStringList`. `IsWebGL2()` at every hook.
- Coherence ceiling: the extension whitelist governs both `getSupportedExtensions` AND `getExtension`/`IsSupported` (else a list-omitted extension still hands back an object — a tell); this is called out in Global Constraints and is Task 2's explicit obligation, not deferred.

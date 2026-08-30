# SP3b-i — WebGL profile: vendor/renderer strings + parameter table

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the WebGL unmasked vendor/renderer strings and the numeric/array parameter table controllable from config, for both the WebGL1 and WebGL2 namespaces, substituted at the Blink accessor level so the page cannot tell.

**Architecture:** A new `//components/camoucfg` accessor reads `webGl:parameters` (and `webGl2:parameters`) as a pname→typed-value map plus the `webGl:vendor`/`webGl:renderer` string shorthands and a per-namespace `blockIfNotDefined` flag. `WebGLRenderingContextBase::getParameter` (and the `WebGL2RenderingContextBase::getParameter` override) consult it at the top of the function, before the real GL query, returning the configured value with the correct JS type. Blink edits are checkout-only, extracted to `patches/sp3b-webgl-profile.patch`.

**Tech Stack:** C++17 (Chromium/Blink), GN/gtest, Python+Playwright verify (`lib_shell`).

## Global Constraints

- Spoofing happens at the C++/Blink level, never via injected JavaScript.
- Config keys are namespaced: `webGl:` and `webGl2:` are synthetic (colon). `keys.h`'s `EveryKeyIsNamespaced` and `EveryDeclaredConstantIsInAllKeys` (a hand-maintained `declared` literal in `keys_unittest.cc` — NOT reflection; adding keys REQUIRES updating that literal too, or the test goes red) must both stay green.
- **`blockIfNotDefined` is a deliberate exception to rule 5** (spec §4.5): per-namespace, defaults false. When true and a parameter is unlisted, `getParameter` returns the same error/null a real context returns for an unsupported enum, rather than the host's real value — a *partial* GL profile is more detectable than a complete one or none. Defaults false, so the rule-5 fallback (absent config → real value) holds unless the operator opts out.
- **Coherence (spec §5):** `webGl:renderer` and `webGl:vendor` are bound all-or-nothing (a renderer without its vendor is invalid) — but that parse-time rejection is **SP3b-ii's** job (the coherence validator), not this task. SP3b-i exposes the knobs; it does not enforce the pairing.
- A spoofed array parameter (`MAX_VIEWPORT_DIMS`, `ALIASED_LINE_WIDTH_RANGE`, ...) must arrive in JS as the correct typed array (Int32Array / Float32Array), not a plain Array — use the same `WebGLAny` / `Get*Parameter` typing the stock switch uses.
- WebGL1 and WebGL2 are TWO interception points: `WebGLRenderingContextBase::getParameter` (webgl_rendering_context_base.cc:3993) and `WebGL2RenderingContextBase::getParameter` (webgl2_rendering_context_base.cc:4839, delegates unhandled pnames to the base at :5053). The `IsWebGL2()` discriminator on the context selects the `webGl:` vs `webGl2:` key prefix.
- `<random>` banned (not relevant here — this is value substitution, no PRNG).
- `scripts/check_additions_build.py` and `scripts/check_checkout_sync.sh` must stay green.

**Out of scope for SP3b-i (→ SP3b-ii):** `webGl:supportedExtensions`, `webGl:shaderPrecisionFormats`, `webGl:contextAttributes`, WebGPU adapter coherence, and the renderer↔vendor all-or-nothing parse-time rejection.

**Build/verify environment:** see `docs/superpowers/measurements/2026-08-30-sp3-blink-surfaces.md` and the SP3a plan's env note — WSL checkout `/home/lang/chromium/src` as user `lang`, `components_unittests` for camoucfg tests, `content_shell` for the browser, verify from `~/camoucrome-verify` (Playwright 1.55.0). WebGL verify needs SwiftShader: `--use-angle=swiftshader --enable-unsafe-swiftshader`.

---

## File Structure

- `additions/camoucfg/keys.h` + `keys_unittest.cc` — MODIFY: add `webGl:`/`webGl2:` key constants; bump `kAllKeys` and the test's `declared` literal.
- `additions/camoucfg/gl_params.h` / `gl_params.cc` — CREATE: `GLParam(scope, pname, is_webgl2)` returning a typed variant read from the `webGl:parameters` map, plus `GLString(scope, key)` for vendor/renderer and `GLBlockIfNotDefined(scope, is_webgl2)`.
- `additions/camoucfg/gl_params_unittest.cc` — CREATE: map lookup by pname, type dispatch, namespace split, blockIfNotDefined, absent→nullopt.
- `additions/camoucfg/mask_config_internal.{h,cc}` — MODIFY: add `FindParamsMap`/typed nested-dict lookup if the existing `Get*From` cannot reach a nested dict (see Task 1 Step 3).
- `additions/camoucfg/BUILD.gn` — MODIFY: add `gl_params.{cc,h}` + `gl_params_unittest.cc`.
- Blink (checkout only → `patches/sp3b-webgl-profile.patch`): `third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc`, `third_party/blink/renderer/modules/webgl/webgl2_rendering_context_base.cc`, and `modules/webgl/BUILD.gn` (already deps `//components/camoucfg` from SP3a — confirm; no change if present).
- `scripts/verify_sp3b.py` — CREATE.
- `scripts/apply.sh` — MODIFY: append `patches/sp3b-webgl-profile.patch` LAST.

---

### Task 1: `webGl:` keys + the `GLParam` config-map accessor

**Files:**
- Modify: `additions/camoucfg/keys.h`, `additions/camoucfg/keys_unittest.cc`, `additions/camoucfg/BUILD.gn`
- Create: `additions/camoucfg/gl_params.h`, `additions/camoucfg/gl_params.cc`, `additions/camoucfg/gl_params_unittest.cc`

**Interfaces:**
- Consumes: `camoucfg::GlobalScope()`, `ConfigScope`, the parsed `base::Value::Dict` config (via `mask_config`/`mask_config_internal`).
- Produces:
  - keys `kWebGlVendor="webGl:vendor"`, `kWebGlRenderer="webGl:renderer"`, `kWebGl2Vendor="webGl2:vendor"`, `kWebGl2Renderer="webGl2:renderer"`, `kWebGlParameters="webGl:parameters"`, `kWebGl2Parameters="webGl2:parameters"`, `kWebGlParamsBlock="webGl:parameters:blockIfNotDefined"`, `kWebGl2ParamsBlock="webGl2:parameters:blockIfNotDefined"`.
  - `using GLValue = std::variant<int64_t, double, bool, std::string, std::vector<double>>;`
  - `std::optional<GLValue> camoucfg::GLParam(const ConfigScope& scope, uint32_t pname, bool is_webgl2);` — looks up the decimal string of `pname` inside the `webGl:parameters` (or `webGl2:`) map; returns the typed value, or nullopt if the map or the pname is absent.
  - `std::optional<std::string> camoucfg::GLString(const ConfigScope& scope, uint32_t pname_kind, bool is_webgl2);` where `pname_kind` selects renderer vs vendor — OR two thin wrappers `GLRenderer(scope,is_webgl2)`/`GLVendor(scope,is_webgl2)` returning the `webGl:renderer`/`webGl:vendor` shorthand. (Pick the two-wrapper form; it reads better at the call site.)
  - `bool camoucfg::GLBlockIfNotDefined(const ConfigScope& scope, bool is_webgl2);`

- [ ] **Step 1: Write the failing tests** (`gl_params_unittest.cc`)

Config is injected the way `mask_config_unittest.cc` does it — build a `base::Value::Dict` from JSON via `internal::ParseConfig`, and have the accessor read from an injected dict. **Design the accessors to take the dict (or scope) so they are unit-testable without the process-global config**: mirror the `internal::Get*From(const base::DictValue&, key)` pattern — put the real logic in `internal::GLParamFrom(const base::DictValue& cfg, uint32_t pname, bool is_webgl2)` and make the public `GLParam(scope, ...)` a one-line wrapper over `Config()`. Then the unit test exercises `internal::GLParamFrom` against a hand-built dict, exactly as `GettersTest` exercises `GetInt32From`.

```cpp
#include "components/camoucfg/gl_params.h"
#include "components/camoucfg/mask_config_internal.h"
#include "base/values.h"
#include "testing/gtest/include/gtest/gtest.h"
namespace camoucfg { namespace {

base::Value::Dict Parse(std::string_view json) {
  return internal::ParseConfig(json, /*strict=*/false);
}

TEST(GLParamsTest, ReadsIntFromParameterMap) {
  auto cfg = Parse(R"({"webGl:parameters":{"3379":16384}})");  // MAX_TEXTURE_SIZE
  auto v = internal::GLParamFrom(cfg, 3379, /*is_webgl2=*/false);
  ASSERT_TRUE(v.has_value());
  ASSERT_TRUE(std::holds_alternative<int64_t>(*v));
  EXPECT_EQ(std::get<int64_t>(*v), 16384);
}

TEST(GLParamsTest, ReadsFloatArrayFromParameterMap) {
  auto cfg = Parse(R"({"webGl:parameters":{"33902":[1.0,1024.0]}})");  // ALIASED_LINE_WIDTH_RANGE
  auto v = internal::GLParamFrom(cfg, 33902, false);
  ASSERT_TRUE(v.has_value());
  ASSERT_TRUE(std::holds_alternative<std::vector<double>>(*v));
  EXPECT_EQ(std::get<std::vector<double>>(*v).size(), 2u);
}

TEST(GLParamsTest, ReadsStringFromParameterMap) {
  auto cfg = Parse(R"({"webGl:parameters":{"7936":"WebKit"}})");  // VENDOR
  auto v = internal::GLParamFrom(cfg, 7936, false);
  ASSERT_TRUE(std::holds_alternative<std::string>(*v));
}

TEST(GLParamsTest, NamespaceSplit) {
  auto cfg = Parse(R"({"webGl:parameters":{"3379":16384},"webGl2:parameters":{"3379":32768}})");
  EXPECT_EQ(std::get<int64_t>(*internal::GLParamFrom(cfg, 3379, false)), 16384);
  EXPECT_EQ(std::get<int64_t>(*internal::GLParamFrom(cfg, 3379, true)), 32768);
}

TEST(GLParamsTest, AbsentIsNullopt) {
  auto cfg = Parse(R"({"webGl:parameters":{"3379":16384}})");
  EXPECT_FALSE(internal::GLParamFrom(cfg, 9999, false).has_value());
  EXPECT_FALSE(internal::GLParamFrom(Parse("{}"), 3379, false).has_value());
}

TEST(GLParamsTest, BlockIfNotDefined) {
  auto cfg = Parse(R"({"webGl:parameters:blockIfNotDefined":true})");
  EXPECT_TRUE(internal::GLBlockFrom(cfg, false));
  EXPECT_FALSE(internal::GLBlockFrom(cfg, true));   // webGl2 not set
  EXPECT_FALSE(internal::GLBlockFrom(Parse("{}"), false));  // default false
}

}}  // namespaces
```

- [ ] **Step 2: Run to verify it fails**

Sync + build (see SP3a plan env; use the `pushcfg`/`unittests` helper pattern).
Run: `unittests 'GLParamsTest.*'`
Expected: FAIL to compile — `gl_params.h` / `internal::GLParamFrom` do not exist.

- [ ] **Step 3: Implement `internal::GLParamFrom` / `GLBlockFrom`** (`mask_config_internal.{h,cc}`)

The parsed config is a `base::Value::Dict`. A namespaced key like `"webGl:parameters"` is a flat dict key whose value is a nested dict. Read it with `cfg.FindDict("webGl:parameters")`, then look up the pname's DECIMAL STRING key inside, dispatching on the found `base::Value`'s type:

```cpp
// mask_config_internal.cc
std::optional<GLValue> GLParamFrom(const base::Value::Dict& cfg,
                                   uint32_t pname, bool is_webgl2) {
  const base::Value::Dict* params =
      cfg.FindDict(is_webgl2 ? "webGl2:parameters" : "webGl:parameters");
  if (!params) return std::nullopt;
  const base::Value* v = params->Find(base::NumberToString(pname));
  if (!v) return std::nullopt;
  switch (v->type()) {
    case base::Value::Type::INTEGER: return GLValue(int64_t{v->GetInt()});
    case base::Value::Type::DOUBLE:  return GLValue(v->GetDouble());
    case base::Value::Type::BOOLEAN: return GLValue(v->GetBool());
    case base::Value::Type::STRING:  return GLValue(v->GetString());
    case base::Value::Type::LIST: {
      std::vector<double> out;
      for (const base::Value& e : v->GetList()) {
        if (e.is_int()) out.push_back(e.GetInt());
        else if (e.is_double()) out.push_back(e.GetDouble());
        else return std::nullopt;  // heterogeneous/garbage list
      }
      return GLValue(std::move(out));
    }
    default: return std::nullopt;
  }
}

bool GLBlockFrom(const base::Value::Dict& cfg, bool is_webgl2) {
  return cfg.FindBool(is_webgl2 ? "webGl2:parameters:blockIfNotDefined"
                                : "webGl:parameters:blockIfNotDefined")
      .value_or(false);
}
```

Declare both in `mask_config_internal.h`, and define `GLValue` in `gl_params.h` (included by the internal header, or define `GLValue` in the internal header and re-export). Keep `GLValue` in ONE place.

- [ ] **Step 4: Implement the public accessors** (`gl_params.h` / `gl_params.cc`)

```cpp
// gl_params.cc
std::optional<GLValue> GLParam(const ConfigScope&, uint32_t pname, bool is_webgl2) {
  return internal::GLParamFrom(Config(), pname, is_webgl2);
}
std::optional<std::string> GLVendor(const ConfigScope& s, bool is_webgl2) {
  return GetString(s, is_webgl2 ? keys::kWebGl2Vendor : keys::kWebGlVendor);
}
std::optional<std::string> GLRenderer(const ConfigScope& s, bool is_webgl2) {
  return GetString(s, is_webgl2 ? keys::kWebGl2Renderer : keys::kWebGlRenderer);
}
bool GLBlockIfNotDefined(const ConfigScope&, bool is_webgl2) {
  return internal::GLBlockFrom(Config(), is_webgl2);
}
```
(`Config()` is the file-local accessor in `mask_config.cc`; expose it to `gl_params.cc` the same way the other public getters reach it — either move these into `mask_config.cc` or add a narrow internal `const base::Value::Dict& internal::ParsedConfig()` used by both. Prefer the latter so `gl_params.cc` does not duplicate the singleton.)

- [ ] **Step 5: Add the 8 keys** to `keys.h` (with a `webGl:`/`webGl2:` comment block mirroring the `canvas:` block), bump `kAllKeys` size by 8 and list them, AND add all 8 to the `declared` literal in `keys_unittest.cc:EveryDeclaredConstantIsInAllKeys` (the SP3a Task-1 lesson: that test is two hand-lists, not reflection). Wire `gl_params.{cc,h}` + `gl_params_unittest.cc` into `BUILD.gn`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `unittests 'GLParamsTest.*:CamoucfgKeysTest.*'`
Expected: PASS (GLParamsTest 6 + CamoucfgKeysTest 5). Then `python3 scripts/check_additions_build.py` → PASS.

- [ ] **Step 7: Commit**

```bash
git add additions/camoucfg/keys.h additions/camoucfg/keys_unittest.cc \
  additions/camoucfg/gl_params.h additions/camoucfg/gl_params.cc \
  additions/camoucfg/gl_params_unittest.cc additions/camoucfg/mask_config_internal.h \
  additions/camoucfg/mask_config_internal.cc additions/camoucfg/mask_config.cc \
  additions/camoucfg/BUILD.gn
git commit -m "feat(sp3b): webGl:/webGl2: keys + GLParam config-map accessor"
```

---

### Task 2: WebGL vendor/renderer string substitution

**Files:**
- Modify (checkout only): `third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc`
- Create: `scripts/verify_sp3b.py`; Create: `patches/sp3b-webgl-profile.patch`; Modify: `scripts/apply.sh`

**Interfaces:**
- Consumes: `camoucfg::GLVendor/GLRenderer(scope, is_webgl2)`, `camoucfg::GLParam` (Task 1); `camoucfg::ScopeFor` (`blink_scope.h`).

**Measure-then-implement (like SP3a's Blink tasks): confirm the exact API on the live checkout before writing glue.**

- [ ] **Step 1: Locate the unmasked cases + the WebGL2 discriminator**

In `getParameter` (webgl_rendering_context_base.cc:3993), the cases `WebGLDebugRendererInfo::kUnmaskedRendererWebgl` (:4204) and `kUnmaskedVendorWebgl` (:4213). Confirm how the context knows it is WebGL2 (`IsWebGL2()` member, or `Version()`), since a WebGL2 context reading these delegates to this base method — the base case must select `webGl2:` when `IsWebGL2()`.

- [ ] **Step 2: Write `scripts/verify_sp3b.py`** (model on verify_sp3a.py + SP3 spec §6 items 1–3)

Launch content_shell with SwiftShader (`--use-angle=swiftshader --enable-unsafe-swiftshader`). Criteria:
- V1 baseline stable: with no config, `getParameter(0x9246)`/`(0x9245)` (unmasked renderer/vendor) identical across two launches.
- V2 vendor+renderer substitute: with `webGl:renderer`/`webGl:vendor` set, both return exactly the configured strings, and the SwiftShader baseline strings appear nowhere in a full `getParameter` sweep JSON.
- V3 both namespaces: repeat V2 on a `webgl2` context with `webGl2:` keys; confirm a `webgl` context is unaffected by `webGl2:` keys and vice versa.
RED-FIRST: run against stock → V2/V3 FAIL.

- [ ] **Step 3: Implement** — in the two unmasked cases, before the real query, return the configured string:

```cpp
case WebGLDebugRendererInfo::kUnmaskedRendererWebgl:
  if (auto* ec = Host()->GetTopExecutionContext()) {
    if (auto v = camoucfg::GLRenderer(camoucfg::ScopeFor(ec), IsWebGL2()))
      return WebGLAny(script_state, String::FromUTF8(*v));
    if (auto p = camoucfg::GLParam(camoucfg::ScopeFor(ec),
                                   /*UNMASKED_RENDERER_WEBGL*/0x9246, IsWebGL2());
        p && std::holds_alternative<std::string>(*p))
      return WebGLAny(script_state, String::FromUTF8(std::get<std::string>(*p)));
  }
  [...existing real query...]
```
(The `GLParam` fallback lets a profile that sets only the parameter table — with `0x9245`/`0x9246` entries — still spoof, mirroring Camoufox's #44 fix. Vendor case is symmetric with `0x9245`.) Add `#include "components/camoucfg/gl_params.h"` + `blink_scope.h`.

- [ ] **Step 4: Build + verify GREEN** (`contentshell`; `verify_sp3b.py` → V1–V3 pass). Extract patch (`git diff -- webgl_rendering_context_base.cc > patch`), wire apply.sh LAST.

- [ ] **Step 5: Commit** — `feat(sp3b): spoof WebGL unmasked vendor/renderer strings (both namespaces)`

---

### Task 3: WebGL parameter table + blockIfNotDefined

**Files:**
- Modify (checkout only): `webgl_rendering_context_base.cc`, `webgl2_rendering_context_base.cc`
- Modify: `scripts/verify_sp3b.py`, `patches/sp3b-webgl-profile.patch`

**Interfaces:**
- Consumes: `camoucfg::GLParam`, `camoucfg::GLBlockIfNotDefined` (Task 1).

- [ ] **Step 1: Extend verify_sp3b.py** — V4 parameter table: set an int (`MAX_TEXTURE_SIZE` 0x0D33), a two-int array (`MAX_VIEWPORT_DIMS` 0x0D3A), and confirm each returns the configured value with the correct JS type (an array arrives as a typed array, `instanceof Int32Array`). V5 fail-closed: with `webGl:parameters:blockIfNotDefined` true and a pname omitted, `getParameter(thatEnum)` returns null and raises the same GL error a real unsupported enum raises; with the flag false, the same call returns the host value. RED-first on stock.

- [ ] **Step 2: Implement the generic lookup** at the TOP of `WebGLRenderingContextBase::getParameter` (after the `isContextLost()` guard, before the switch) AND at the top of `WebGL2RenderingContextBase::getParameter`:

```cpp
if (auto* ec = Host()->GetTopExecutionContext()) {
  const auto scope = camoucfg::ScopeFor(ec);
  // UNMASKED_RENDERER/VENDOR are handled by their dedicated cases (Task 2) and
  // must NOT be shadowed here, or setting them via the table would bypass the
  // per-context path -- the Camoufox #44 trap. Skip them.
  if (pname != 0x9246 && pname != 0x9245) {
    if (auto v = camoucfg::GLParam(scope, pname, IsWebGL2())) {
      // dispatch the variant to the correct WebGLAny / typed-array builder
      return BuildSpoofedParam(script_state, *v);  // int64->WebGLAny, double->WebGLAny,
                                                    // bool->WebGLAny, string->WebGLAny,
                                                    // vector<double>->Int32Array or
                                                    // Float32Array per the pname's real type
    }
    if (camoucfg::GLBlockIfNotDefined(scope, IsWebGL2()) && IsBlockablePname(pname))
      return ScriptValue::CreateNull(script_state->GetIsolate());  // fail closed
  }
}
```
`BuildSpoofedParam` and the array-type decision are the measure-then-implement part: determine, per pname, whether the stock switch returns a Float32Array or Int32Array (the measurement doc lists the helpers: `GetWebGLFloatArrayParameter` vs an int array), and build the matching type from `vector<double>`. `IsBlockablePname` excludes the pnames a real context always answers (the spec §6.5 note) — carry Camoufox's block list of the array/range pnames that are always present. Keep the WebGL2 override's insertion identical (shared helper in an anonymous namespace or a static free function so it is not copy-pasted divergently).

- [ ] **Step 3: Build + verify GREEN** (V1–V5). Re-extract the patch across both webgl files. Regression: `verify_sp3a.py` still ALL_PASS (WebGL readPixels canvas noise must be unaffected — different code path), camoucfg unit suite green.

- [ ] **Step 4: Commit** — `feat(sp3b): spoof WebGL parameter table + blockIfNotDefined (both namespaces)`

---

## Self-Review

- Spec §3 WebGL vendor/renderer/parameters/blockIfNotDefined → Tasks 2, 3; §4.5 blockIfNotDefined exception → Task 3 (defaults false). §5 renderer↔vendor coherence → explicitly deferred to SP3b-ii (stated). Extensions/precision/attributes/WebGPU → SP3b-ii (out-of-scope stated).
- Placeholder check: the camoucfg accessor (Task 1) carries complete code; the Blink glue (Tasks 2/3) is measure-then-implement with the interception point, config call, and typed-return approach given — matching SP3a's Blink tasks. `BuildSpoofedParam`'s per-pname array-type table is the one genuine measurement the implementer must complete against the live switch.
- Type consistency: `GLParam` → `optional<GLValue>` (variant int64/double/bool/string/vector<double>); `GLVendor`/`GLRenderer` → `optional<string>`; `GLBlockIfNotDefined` → `bool`. Used identically across tasks. `IsWebGL2()` selects the namespace at every call.
- Known ceiling: the parameter table is keyed by raw pname decimal strings (Camoufox-compatible); an operator hand-writing a garbage type for a pname (e.g. a string for `MAX_TEXTURE_SIZE`) gets that garbage returned — SP3b-ii's coherence validator, not this task, is where profile sanity is enforced. `BuildSpoofedParam` should defensively fall back to the real query if the variant type cannot match the pname's expected JS type, rather than returning a wrong-typed value.

# SP3a — Canvas readback noise + shared DeriveDelta primitive

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the canvas readback hash controllable from config by applying deterministic per-session noise to pixels as they leave the canvas (never at draw time), built on a surface-agnostic `DeriveDelta` primitive that SP4 will reuse for audio and font-metric jitter.

**Architecture:** Three pure, unit-tested primitives in `//components/camoucfg` (`DeriveDelta`, `DeriveUnit`, `PerturbRgba`) plus a thin config-reading wrapper (`PerturbRgbaFromConfig`). Six Blink readback sites — four snapshot callers and two direct-read chokepoints, all located in `measurements/2026-08-30-sp3-blink-surfaces.md` — call only the wrapper. The config read and its defaults live in exactly one place; the Blink glue never reads a key directly. Blink edits are checkout-only, extracted to `patches/sp3a-canvas-noise.patch`.

**Tech Stack:** C++17 (Chromium/Blink), GN/gtest, Python+Playwright verify script (`lib_shell`).

## Global Constraints

- Spoofing happens at the C++/Blink level, never via injected JavaScript. (00-conventions rule 1.)
- **Determinism is the single most important property.** Reading the same canvas twice must yield byte-identical bytes; a script that hashes a canvas twice and gets two hashes has learned the browser is lying. (§4.3.)
- Noise is applied **on readback only, never at draw time.** What is composited to the screen stays byte-identical to stock. (§4.2.)
- Absent config → real value: with no `canvas:seed`, every readback path is byte-identical to a stock `content_shell`. Canvas has **no** `blockIfNotDefined` — that flag is WebGL-only. (00-conventions rule 5.)
- Accessors stay native: `HTMLCanvasElement.prototype.toDataURL` etc. still stringify to `[native code]`, and `Object.keys(window)` is unchanged vs stock. (00-conventions rule 2.)
- A worker reports the same values as its window, structurally, via environment inheritance — no IPC. (00-conventions rule 3, §4.4.)
- `<random>` is banned in the tree; PRNG is hand-rolled (SplitMix64 finalizer). (Precedent: `mouse_trajectories.cc`.)
- Config keys are namespaced: `canvas:` is a synthetic namespace (colon), no bare `canvas` key. `keys.h`'s `EveryKeyIsNamespaced` and `EveryDeclaredConstantIsInAllKeys` invariants must both stay green.
- `scripts/check_additions_build.py` (BUILD.gn sources ⊇ files) and `scripts/check_checkout_sync.sh` (checkout tree == `additions/`) must stay green.
- §7.3 is **decided**: position-based `DeriveDelta`; the canvas content hash is folded into the per-canvas seed *at the applier* so per-drawing shift and reread-determinism both hold. Camoucrome does **not** match Camoufox's byte output.

**Out of scope for SP3a (deliberate, YAGNI-checked against the reference):** `canvas:aaOffset` / `canvas:aaCapOffset`. The spec §3 lists them, but Camoufox's `canvas-spoofing.patch` readback perturbation (`CanvasSeedManager::Perturb`) uses only seed/density/strength — there is no anti-alias-offset readback mechanism to port. Adding keys for an unimplemented mechanism violates rule-5's "no knob without an effect." Revisit only if a real anti-aliasing tell is measured. Also out of scope: WebGL `readPixels` string/parameter spoofing and WebGPU coherence (SP3b); audio/font-metric call sites (SP4 — but the `DeriveDelta` primitive they consume ships here).

---

## File Structure

- `additions/camoucfg/keys.h` — MODIFY: add three `canvas:` key constants; bump `kAllKeys`.
- `additions/camoucfg/derive.h` / `derive.cc` — MODIFY: add `DeriveDelta` and `DeriveUnit` (the shared, surface-agnostic primitives) + their internal hash core.
- `additions/camoucfg/derive_unittest.cc` — MODIFY: determinism, bound, domain-independence, purity(=cross-process) tests.
- `additions/camoucfg/canvas_noise.h` / `canvas_noise.cc` — CREATE: `PerturbRgba` (pure applier, content-hash fold) + `PerturbRgbaFromConfig` (config wrapper).
- `additions/camoucfg/canvas_noise_unittest.cc` — CREATE: reread-determinism, off-when-seed-0, alpha untouched, density/strength effect, per-drawing shift, sanitization.
- `additions/camoucfg/BUILD.gn` — MODIFY: add `canvas_noise.{cc,h}` to the library and `canvas_noise_unittest.cc` to `unit_tests`.
- Blink (checkout only, extracted to `patches/sp3a-canvas-noise.patch`):
  - `third_party/blink/renderer/core/html/canvas/html_canvas_element.cc` — snapshot callers (`:1256`, `:1312`, `:1923` region).
  - `third_party/blink/renderer/core/offscreencanvas/offscreen_canvas.cc` — `convertToBlob` caller (`:386` region).
  - `third_party/blink/renderer/modules/canvas/canvas2d/base_rendering_context_2d.cc` — `getImageDataInternal` (`:358`).
  - `third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc` — `readPixels`/`ReadPixelsHelper` (`:5273`/`:5284`).
- `scripts/verify_sp3a.py` — CREATE: CDP/Playwright determinism + off-by-default + full-coverage + worker-parity + screen-unchanged + native-accessor checks.
- `scripts/apply.sh` — MODIFY: append `patches/sp3a-canvas-noise.patch` LAST in `PATCHES`.

**Build/verify environment** (all Blink tasks): the Windows/WSL build box, `~/chromium/src` (HEAD `a727b57805`). Reach the checkout as user `lang`: SSH lands in PowerShell, so route through `wsl -d Ubuntu-24.04 -u lang bash -lc "..."`, and to survive PowerShell+bash quoting, base64-encode the bash body (`echo <b64> | base64 -d | bash`). camoucfg unit tests: `autoninja -C out/Default components/camoucfg:unit_tests` then run the gtest binary filtered. Browser: `autoninja -C out/Default content_shell`; WebGL/GPU is irrelevant to canvas 2D noise, but launch headful under xvfb if a check needs a real raster path. A cold browser build is ~40 min, incremental ~5 min (ccache on); **after any VM teardown, `touch` the edited `.cc` and confirm ninja reports a non-zero step count — a stale `.o` newer than the `.cc` yields a silent "0 steps" no-op build.**

---

### Task 1: `canvas:` config keys

**Files:**
- Modify: `additions/camoucfg/keys.h`
- Test: `additions/camoucfg/keys_unittest.cc` (existing `EveryDeclaredConstantIsInAllKeys` and `EveryKeyIsNamespaced` cover this automatically — no new test needed)

**Interfaces:**
- Consumes: nothing.
- Produces: `camoucfg::keys::kCanvasSeed` = `"canvas:seed"`, `kCanvasNoiseDensity` = `"canvas:noiseDensity"`, `kCanvasNoiseStrength` = `"canvas:noiseStrength"`.

- [ ] **Step 1: Run the keys unit tests to confirm the current green baseline**

Reach the checkout (see "Build/verify environment"). First sync `additions/` into the checkout (`scripts/apply.sh` is for a clean tree; for an incremental edit just `cp additions/camoucfg/keys.h <checkout>/components/camoucfg/keys.h`), then:

Run: `autoninja -C out/Default components/camoucfg:unit_tests && ./out/Default/components_camoucfg_unittests --gtest_filter='Keys*'`
Expected: PASS, and note the current count (baseline before your change).

- [ ] **Step 2: Add the three key constants**

In `additions/camoucfg/keys.h`, after the `kShowCursor` block and before the `kAllKeys` array, add:

```cpp
// The canvas readback-noise knobs, in their own synthetic `canvas:` namespace
// -- none mirrors a JS property path. `canvas:` is a pure namespace with no
// bare `canvas` key, the same shape as `ua:` and `humanize:` above. A page
// never reads these; they steer noise applied as pixels leave the canvas.
//
// aaOffset / aaCapOffset from the SP3 spec §3 table are deliberately absent:
// the reference (Camoufox canvas-spoofing.patch) applies no anti-alias offset
// on readback, so there is no mechanism for those keys to steer. Adding them
// would be a knob with no effect, which rule 5 forbids.
inline constexpr char kCanvasSeed[] = "canvas:seed";
inline constexpr char kCanvasNoiseDensity[] = "canvas:noiseDensity";
inline constexpr char kCanvasNoiseStrength[] = "canvas:noiseStrength";
```

- [ ] **Step 3: Add them to `kAllKeys` and bump its size**

Change the array declaration size from `14` to `17`, and add the three constants to the initializer list after `kShowCursor`:

```cpp
inline constexpr std::array<std::string_view, 17> kAllKeys = {
    kUaOsInfo,
    kNavigatorHardwareConcurrency,
    kNavigatorUserAgent,
    kUaPlatform,
    kUaPlatformVersion,
    kUaArchitecture,
    kUaBitness,
    kUaModel,
    kUaMobile,
    kUaWow64,
    kHumanizeEnabled,
    kHumanizeMinTime,
    kHumanizeMaxTime,
    kShowCursor,
    kCanvasSeed,
    kCanvasNoiseDensity,
    kCanvasNoiseStrength,
};
```

- [ ] **Step 4: Run the keys unit tests — they must stay green**

Copy the edited `keys.h` into the checkout, then:

Run: `autoninja -C out/Default components/camoucfg:unit_tests && ./out/Default/components_camoucfg_unittests --gtest_filter='Keys*'`
Expected: PASS. `EveryDeclaredConstantIsInAllKeys` proves the three new constants are in `kAllKeys` and nothing is orphaned; `EveryKeyIsNamespaced` proves each contains a `:` or `.` — `canvas:seed` etc. pass. If `EveryDeclaredConstantIsInAllKeys` fails, you forgot to bump `17` or missed a list entry.

- [ ] **Step 5: Commit**

```bash
git add additions/camoucfg/keys.h
git commit -m "feat(sp3a): add canvas:seed/noiseDensity/noiseStrength config keys"
```

---

### Task 2: `DeriveDelta` / `DeriveUnit` shared primitive

**Files:**
- Modify: `additions/camoucfg/derive.h`, `additions/camoucfg/derive.cc`
- Test: `additions/camoucfg/derive_unittest.cc`

**Interfaces:**
- Consumes: nothing (pure functions; no config).
- Produces:
  - `int32_t camoucfg::DeriveDelta(uint64_t seed, std::string_view domain, uint64_t index, int32_t bound)` — deterministic signed delta in `[-|bound|, +|bound|]`; `bound == 0` → `0`.
  - `double camoucfg::DeriveUnit(uint64_t seed, std::string_view domain, uint64_t index)` — deterministic double in `[0, 1)`.

- [ ] **Step 1: Write the failing tests**

Append to `additions/camoucfg/derive_unittest.cc` (inside the existing `namespace camoucfg { namespace {`):

```cpp
// DeriveDelta / DeriveUnit are pure: no config, no state. That purity is the
// cross-process reproducibility guarantee (§6 item 13) -- a renderer, a worker
// in its own process, and a unit test all get the same value from the same
// arguments -- so it is tested here as "same args, same result".

TEST(DeriveDeltaTest, IsDeterministic) {
  for (uint64_t i = 0; i < 50; ++i) {
    EXPECT_EQ(DeriveDelta(1234, "canvas", i, 3),
              DeriveDelta(1234, "canvas", i, 3));
    EXPECT_EQ(DeriveUnit(1234, "canvas", i), DeriveUnit(1234, "canvas", i));
  }
}

TEST(DeriveDeltaTest, StaysWithinBound) {
  for (uint64_t i = 0; i < 1000; ++i) {
    int32_t d = DeriveDelta(99, "canvas", i, 4);
    EXPECT_GE(d, -4);
    EXPECT_LE(d, 4);
  }
  // A negative bound is treated by magnitude, not left to signed modulo.
  for (uint64_t i = 0; i < 1000; ++i) {
    int32_t d = DeriveDelta(99, "canvas", i, -4);
    EXPECT_GE(d, -4);
    EXPECT_LE(d, 4);
  }
}

TEST(DeriveDeltaTest, ZeroBoundIsZero) {
  for (uint64_t i = 0; i < 20; ++i)
    EXPECT_EQ(DeriveDelta(7, "canvas", i, 0), 0);
}

TEST(DeriveDeltaTest, CoversTheFullRange) {
  // Bound 1 must actually produce -1, 0 and +1 across indices, or the range
  // mapping is stuck. A degenerate "always 0" passes IsDeterministic and
  // StaysWithinBound; this catches it.
  bool saw_neg = false, saw_zero = false, saw_pos = false;
  for (uint64_t i = 0; i < 300; ++i) {
    switch (DeriveDelta(5, "canvas", i, 1)) {
      case -1: saw_neg = true; break;
      case 0: saw_zero = true; break;
      case 1: saw_pos = true; break;
    }
  }
  EXPECT_TRUE(saw_neg && saw_zero && saw_pos);
}

TEST(DeriveDeltaTest, DomainsAreUncorrelated) {
  // §6 item 13: two surfaces sharing a seed must not produce the same
  // sequence. Assert the three domains disagree at most indices for one seed.
  int canvas_audio_diff = 0, canvas_font_diff = 0;
  for (uint64_t i = 0; i < 500; ++i) {
    if (DeriveDelta(42, "canvas", i, 127) != DeriveDelta(42, "audio", i, 127))
      ++canvas_audio_diff;
    if (DeriveDelta(42, "canvas", i, 127) !=
        DeriveDelta(42, "fontmetric", i, 127))
      ++canvas_font_diff;
  }
  EXPECT_GT(canvas_audio_diff, 450);
  EXPECT_GT(canvas_font_diff, 450);
}

TEST(DeriveDeltaTest, DifferentSeedsDiffer) {
  int diff = 0;
  for (uint64_t i = 0; i < 500; ++i)
    if (DeriveDelta(1, "canvas", i, 127) != DeriveDelta(2, "canvas", i, 127))
      ++diff;
  EXPECT_GT(diff, 450);
}

TEST(DeriveUnitTest, StaysInUnitInterval) {
  for (uint64_t i = 0; i < 1000; ++i) {
    double u = DeriveUnit(3, "canvas-gate", i);
    EXPECT_GE(u, 0.0);
    EXPECT_LT(u, 1.0);
  }
}

TEST(DeriveUnitTest, IsRoughlyUniform) {
  // A gate that clusters would make canvas density meaningless. Assert the
  // mean of many draws is near 0.5 -- loose bounds, this is a smoke test not
  // a statistics suite.
  double sum = 0;
  const int n = 5000;
  for (uint64_t i = 0; i < static_cast<uint64_t>(n); ++i)
    sum += DeriveUnit(11, "canvas-gate", i);
  double mean = sum / n;
  EXPECT_GT(mean, 0.45);
  EXPECT_LT(mean, 0.55);
}
```

- [ ] **Step 2: Run the tests to verify they fail**

Copy `derive_unittest.cc` into the checkout and build.
Run: `autoninja -C out/Default components/camoucfg:unit_tests && ./out/Default/components_camoucfg_unittests --gtest_filter='DeriveDeltaTest.*:DeriveUnitTest.*'`
Expected: FAIL to **compile** — `DeriveDelta` / `DeriveUnit` are undeclared.

- [ ] **Step 3: Declare the primitives in `derive.h`**

In `additions/camoucfg/derive.h`, add `#include <cstdint>` to the includes, and before the closing `}  // namespace camoucfg` add:

```cpp
// A deterministic signed delta in [-|bound|, +|bound|]. A pure function of its
// arguments: the same (seed, domain, index, bound) yields the same value in
// any process with no shared state -- that purity is exactly the cross-process
// reproducibility that lets canvas readback, a worker's OffscreenCanvas, and
// (SP4) audio and font-metric jitter all reproduce one config's noise. `domain`
// ("canvas", "audio", "fontmetric") separates surfaces that share a seed so
// their sequences do not correlate. `index` is any stable integer the caller
// can reproduce -- a flattened pixel offset, an audio sample number, a glyph
// id. bound == 0 returns 0; a negative bound is taken by magnitude.
int32_t DeriveDelta(uint64_t seed, std::string_view domain, uint64_t index,
                    int32_t bound);

// A deterministic double in [0, 1), same purity contract as DeriveDelta.
// Canvas uses it as the per-channel density gate; SP4 surfaces reuse it for
// any reproduce-across-processes probability decision.
double DeriveUnit(uint64_t seed, std::string_view domain, uint64_t index);
```

- [ ] **Step 4: Implement in `derive.cc`**

In `additions/camoucfg/derive.cc`, add `#include <cstdint>` and `#include <cstdlib>` to the includes. Add an anonymous-namespace helper block (extend the existing `namespace { ... }`) with the hash core, and add the two function definitions before `}  // namespace camoucfg`:

```cpp
// SplitMix64 finalizer (Vigna 2015), used as a stateless mixer of one 64-bit
// word. mouse_trajectories.cc has a twin, but that one is a stateful *stream*
// object; this is a stateless function. Two 3-line finalizers are not worth a
// shared header -- extract one only if a third caller appears.
uint64_t Mix64(uint64_t z) {
  z += 0x9E3779B97F4A7C15ULL;
  z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
  z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
  return z ^ (z >> 31);
}

// FNV-1a 64 of the (short) domain string, so "canvas", "audio", "fontmetric"
// seed uncorrelated streams from a single config seed.
uint64_t DomainHash(std::string_view domain) {
  uint64_t h = 0xCBF29CE484222325ULL;
  for (char c : domain) {
    h ^= static_cast<uint8_t>(c);
    h *= 0x100000001B3ULL;
  }
  return h;
}

// One pseudo-random 64-bit word for (seed, domain, index). Mix64(index) first
// so adjacent indices don't produce trivially related inputs before the outer
// mix.
uint64_t Draw(uint64_t seed, std::string_view domain, uint64_t index) {
  return Mix64(seed ^ DomainHash(domain) ^ Mix64(index));
}
```

and, in the `camoucfg` namespace:

```cpp
int32_t DeriveDelta(uint64_t seed, std::string_view domain, uint64_t index,
                    int32_t bound) {
  if (bound == 0) {
    return 0;
  }
  const uint64_t b = static_cast<uint64_t>(
      std::abs(static_cast<int64_t>(bound)));
  const uint64_t span = 2 * b + 1;  // -b .. +b inclusive
  const uint64_t r = Draw(seed, domain, index) % span;
  return static_cast<int32_t>(static_cast<int64_t>(r) - static_cast<int64_t>(b));
}

double DeriveUnit(uint64_t seed, std::string_view domain, uint64_t index) {
  // Top 53 bits map exactly onto a double's mantissa, as in mouse_trajectories.
  return (Draw(seed, domain, index) >> 11) * 0x1.0p-53;
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Copy `derive.h`, `derive.cc` into the checkout and build.
Run: `autoninja -C out/Default components/camoucfg:unit_tests && ./out/Default/components_camoucfg_unittests --gtest_filter='DeriveDeltaTest.*:DeriveUnitTest.*'`
Expected: PASS (8 tests).

- [ ] **Step 6: Commit**

```bash
git add additions/camoucfg/derive.h additions/camoucfg/derive.cc additions/camoucfg/derive_unittest.cc
git commit -m "feat(sp3a): add DeriveDelta/DeriveUnit shared noise primitive"
```

---

### Task 3: `PerturbRgba` applier + `PerturbRgbaFromConfig` wrapper

**Files:**
- Create: `additions/camoucfg/canvas_noise.h`, `additions/camoucfg/canvas_noise.cc`, `additions/camoucfg/canvas_noise_unittest.cc`
- Modify: `additions/camoucfg/BUILD.gn`

**Interfaces:**
- Consumes: `DeriveDelta`, `DeriveUnit` (Task 2); `GetUint32`, `GetDouble`, `GetInt32`, `ConfigScope` (`mask_config.h`); `keys::kCanvasSeed`, `kCanvasNoiseDensity`, `kCanvasNoiseStrength` (Task 1).
- Produces:
  - `void camoucfg::PerturbRgba(uint8_t* data, size_t length, uint64_t seed, double density, int32_t strength)` — pure in-place applier; `seed == 0` is a no-op.
  - `void camoucfg::PerturbRgbaFromConfig(uint8_t* data, size_t length, const ConfigScope& scope)` — reads the three keys (defaults density `0.0005`, strength `1`), calls `PerturbRgba`; absent/zero `canvas:seed` → no-op.

- [ ] **Step 1: Write the failing tests**

Create `additions/camoucfg/canvas_noise_unittest.cc`:

```cpp
// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/canvas_noise.h"

#include <cstdint>
#include <numeric>
#include <vector>

#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg {
namespace {

// A deterministic non-uniform RGBA buffer to perturb. Uniform buffers hash to
// the same content and hide content-dependence bugs, so vary the bytes.
std::vector<uint8_t> Scene(size_t pixels) {
  std::vector<uint8_t> v(pixels * 4);
  for (size_t i = 0; i < v.size(); ++i)
    v[i] = static_cast<uint8_t>((i * 37 + 11) & 0xFF);
  return v;
}

TEST(PerturbRgbaTest, SameInputsGiveSameOutput) {
  // The determinism guarantee: two readbacks of one canvas are byte-identical.
  auto a = Scene(64), b = Scene(64);
  PerturbRgba(a.data(), a.size(), /*seed=*/12345, /*density=*/0.5, /*strength=*/2);
  PerturbRgba(b.data(), b.size(), 12345, 0.5, 2);
  EXPECT_EQ(a, b);
}

TEST(PerturbRgbaTest, SeedZeroIsNoOp) {
  auto a = Scene(64), orig = Scene(64);
  PerturbRgba(a.data(), a.size(), /*seed=*/0, 0.5, 2);
  EXPECT_EQ(a, orig);  // byte-identical to stock when spoof is off
}

TEST(PerturbRgbaTest, DensityZeroIsNoOp) {
  auto a = Scene(64), orig = Scene(64);
  PerturbRgba(a.data(), a.size(), 12345, /*density=*/0.0, 2);
  EXPECT_EQ(a, orig);
}

TEST(PerturbRgbaTest, ActuallyChangesSomePixels) {
  auto a = Scene(256), orig = Scene(256);
  PerturbRgba(a.data(), a.size(), 12345, /*density=*/0.5, 2);
  EXPECT_NE(a, orig) << "high density left every pixel untouched";
}

TEST(PerturbRgbaTest, AlphaChannelNeverChanges) {
  auto a = Scene(256), orig = Scene(256);
  PerturbRgba(a.data(), a.size(), 12345, /*density=*/1.0, 4);
  for (size_t i = 3; i < a.size(); i += 4)
    EXPECT_EQ(a[i], orig[i]) << "alpha byte " << i << " was perturbed";
}

TEST(PerturbRgbaTest, DeltaStaysWithinStrength) {
  auto a = Scene(256), orig = Scene(256);
  PerturbRgba(a.data(), a.size(), 12345, /*density=*/1.0, /*strength=*/3);
  for (size_t i = 0; i < a.size(); ++i) {
    if ((i & 3u) == 3u) continue;  // alpha untouched
    int d = static_cast<int>(a[i]) - static_cast<int>(orig[i]);
    EXPECT_GE(d, -3);
    EXPECT_LE(d, 3);
  }
}

TEST(PerturbRgbaTest, DifferentDrawingsGetDifferentNoiseFields) {
  // Content-hash fold (§7.3 decision A): the SAME seed on two DIFFERENT
  // drawings must diverge, so an attacker cannot map the field once and
  // subtract it from every later readback. Build two scenes differing in one
  // early byte (inside the 1024-byte content-hash window) and perturb both
  // with one seed; the noise fields must differ somewhere.
  auto a = Scene(256);
  auto b = Scene(256);
  b[0] ^= 0xFF;  // change content within the hashed prefix
  auto a_orig = a, b_orig = b;
  PerturbRgba(a.data(), a.size(), 777, 0.5, 2);
  PerturbRgba(b.data(), b.size(), 777, 0.5, 2);
  // Compare the deltas, not the pixels (b started one byte different).
  bool fields_differ = false;
  for (size_t i = 1; i < a.size(); ++i) {  // skip the byte we changed
    int da = static_cast<int>(a[i]) - static_cast<int>(a_orig[i]);
    int db = static_cast<int>(b[i]) - static_cast<int>(b_orig[i]);
    if (da != db) { fields_differ = true; break; }
  }
  EXPECT_TRUE(fields_differ) << "noise field ignores content; map-and-subtract "
                               "would defeat it";
}

TEST(PerturbRgbaTest, ShortBufferIsNoOp) {
  std::vector<uint8_t> tiny = {1, 2, 3};  // length < 4
  auto orig = tiny;
  PerturbRgba(tiny.data(), tiny.size(), 12345, 1.0, 2);
  EXPECT_EQ(tiny, orig);
}

}  // namespace
}  // namespace camoucfg
```

- [ ] **Step 2: Run to verify it fails**

Add `canvas_noise_unittest.cc` to the `unit_tests` `source_set` in `BUILD.gn` (see Step 4) and add a placeholder empty header so it compiles-to-link-fail? No — expect a **compile** failure: `canvas_noise.h` does not exist.
Run: `autoninja -C out/Default components/camoucfg:unit_tests`
Expected: FAIL — `canvas_noise.h` not found.

- [ ] **Step 3: Create `canvas_noise.h`**

```cpp
// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_CANVAS_NOISE_H_
#define COMPONENTS_CAMOUCFG_CANVAS_NOISE_H_

#include <cstddef>
#include <cstdint>

#include "components/camoucfg/mask_config.h"

namespace camoucfg {

// Applies deterministic readback noise to a tightly-packed 8-bit RGBA buffer,
// in place. A pure function of its arguments: the same (bytes, seed, density,
// strength) yields the same output, so a page reading the same canvas twice
// sees identical pixels and cannot detect the noise by re-rendering. This is
// the single most important property in SP3 (§4.3).
//
//   - seed == 0 is a no-op: the buffer is left byte-identical to stock, which
//     is how "no canvas:seed -> real value" (rule 5) is honoured.
//   - A content hash of the buffer is folded into the seed, so two different
//     drawings get different noise fields (an attacker cannot map the field
//     once and subtract it from every later readback), while a re-read of the
//     same drawing reproduces exactly (§7.3 decision A).
//   - RGB channels only; every 4th byte (alpha) is left untouched.
//   - `density` in [0, 1] is the fraction of RGB channels gated for
//     perturbation; density <= 0 or length < 4 is a no-op.
//   - `strength` bounds the per-channel delta: values land in
//     [-strength, +strength], clamped into [0, 255].
//
// Noise is applied on READBACK only, never at draw time -- callers pass a copy
// of the pixels leaving the canvas, never the canvas's own store.
void PerturbRgba(uint8_t* data, size_t length, uint64_t seed, double density,
                 int32_t strength);

// Reads canvas:seed / canvas:noiseDensity / canvas:noiseStrength from `scope`
// and calls PerturbRgba. This is the ONE place the canvas keys and their
// defaults (density 0.0005, strength 1) are read; every Blink readback site
// calls only this, never a key directly. Absent or zero canvas:seed is a
// no-op.
void PerturbRgbaFromConfig(uint8_t* data, size_t length,
                           const ConfigScope& scope);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_CANVAS_NOISE_H_
```

- [ ] **Step 4: Create `canvas_noise.cc` and wire `BUILD.gn`**

`additions/camoucfg/canvas_noise.cc`:

```cpp
// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/canvas_noise.h"

#include <algorithm>
#include <optional>
#include <string>

#include "components/camoucfg/derive.h"
#include "components/camoucfg/keys.h"

namespace camoucfg {
namespace {

// FNV-1a 64 over the first min(length, 1024) bytes. The 1024-byte window is
// Camoufox's (HashContent), chosen so the hash is cheap yet content-sensitive:
// enough to distinguish drawings without walking a multi-megabyte buffer.
uint64_t ContentHash(const uint8_t* data, size_t length) {
  constexpr size_t kMaxBytes = 1024;
  const size_t n = std::min(length, kMaxBytes);
  uint64_t h = 0xCBF29CE484222325ULL;
  for (size_t i = 0; i < n; ++i) {
    h ^= data[i];
    h *= 0x100000001B3ULL;
  }
  return h;
}

}  // namespace

void PerturbRgba(uint8_t* data, size_t length, uint64_t seed, double density,
                 int32_t strength) {
  if (seed == 0 || data == nullptr || length < 4 || density <= 0.0) {
    return;
  }
  // Fold content into the seed: same drawing reproduces, different drawings
  // diverge. seed != 0 is already guaranteed; if the XOR lands on 0 the mixer
  // still behaves, so no special case is needed.
  const uint64_t eseed = seed ^ ContentHash(data, length);
  for (size_t i = 0; i < length; ++i) {
    if ((i & 3u) == 3u) {
      continue;  // skip alpha
    }
    if (DeriveUnit(eseed, "canvas-gate", i) >= density) {
      continue;  // channel not selected this session
    }
    const int32_t delta = DeriveDelta(eseed, "canvas", i, strength);
    int32_t v = static_cast<int32_t>(data[i]) + delta;
    data[i] = static_cast<uint8_t>(v < 0 ? 0 : (v > 255 ? 255 : v));
  }
}

void PerturbRgbaFromConfig(uint8_t* data, size_t length,
                           const ConfigScope& scope) {
  const std::optional<uint32_t> seed = GetUint32(scope, keys::kCanvasSeed);
  if (!seed || *seed == 0) {
    return;  // spoof off -> byte-identical to stock (rule 5)
  }
  const double density =
      GetDouble(scope, keys::kCanvasNoiseDensity).value_or(0.0005);
  const int32_t strength =
      GetInt32(scope, keys::kCanvasNoiseStrength).value_or(1);
  PerturbRgba(data, length, static_cast<uint64_t>(*seed), density, strength);
}

}  // namespace camoucfg
```

In `additions/camoucfg/BUILD.gn`, add to the `static_library("camoucfg")` `sources` list (keep alphabetical-ish, next to the other canvas entry):

```
    "canvas_noise.cc",
    "canvas_noise.h",
```

and to the `source_set("unit_tests")` `sources`:

```
    "canvas_noise_unittest.cc",
```

- [ ] **Step 5: Run the tests to verify they pass**

Copy `canvas_noise.{h,cc}`, `canvas_noise_unittest.cc`, `BUILD.gn` into the checkout and build.
Run: `autoninja -C out/Default components/camoucfg:unit_tests && ./out/Default/components_camoucfg_unittests --gtest_filter='PerturbRgbaTest.*'`
Expected: PASS (8 tests).

- [ ] **Step 6: Run the full camoucfg unit suite + additions-build check**

Run: `./out/Default/components_camoucfg_unittests`
Expected: PASS (all prior tests + the new DeriveDelta/DeriveUnit/PerturbRgba ones).
Run (on the Mac, repo root): `python3 scripts/check_additions_build.py`
Expected: PASS — `canvas_noise.cc/.h/_unittest.cc` are now listed in `BUILD.gn`; an unlisted new file fails this check.

- [ ] **Step 7: Commit**

```bash
git add additions/camoucfg/canvas_noise.h additions/camoucfg/canvas_noise.cc \
        additions/camoucfg/canvas_noise_unittest.cc additions/camoucfg/BUILD.gn
git commit -m "feat(sp3a): add PerturbRgba applier + PerturbRgbaFromConfig wrapper"
```

---

### Task 4: Blink snapshot-path integration (toDataURL / toBlob / convertToBlob)

**Files:**
- Modify (checkout only): `third_party/blink/renderer/core/html/canvas/html_canvas_element.cc`, `third_party/blink/renderer/core/offscreencanvas/offscreen_canvas.cc` — plus whatever single flat-buffer encode point Step 1 locates.
- Create: `scripts/verify_sp3a.py`
- Create: `patches/sp3a-canvas-noise.patch` (extracted at Step 7)
- Modify: `scripts/apply.sh`

**Interfaces:**
- Consumes: `camoucfg::PerturbRgbaFromConfig(uint8_t*, size_t, const ConfigScope&)` (Task 3); `camoucfg::ScopeFor(blink::ExecutionContext*)` (`blink_scope.h`).
- Produces: the extracted patch (Task 5 appends to it).

**Approach note:** SP3a Blink work is measure-then-implement, exactly as SP2b's input_handler task was. The interception target is known to the *file* but not to the exact API line; locate it on the live checkout before writing glue, and let `verify_sp3a.py` + review prove it — do not assume the line numbers below are current.

- [ ] **Step 1: Locate the narrowest snapshot→flat-buffer point**

On the checkout, read the four callers from the measurement doc and follow where the `StaticBitmapImage` they get from `PaintRenderingResultsToSnapshot` becomes a flat RGBA/BGRA byte buffer for encoding (candidate: `ImageDataBuffer` in `third_party/blink/renderer/platform/graphics/image_data_buffer.*`, which both `toDataURL` and `toBlob`/`convertToBlob` construct before handing pixels to an image encoder).

Decision rule:
- **If** a single flat-buffer point (e.g. `ImageDataBuffer`'s pixel pointer just before encode) provably serves `toDataURL`, `toBlob`, AND `convertToBlob` — perturb there once. Fewer sites, one structural chokepoint.
- **Else** perturb at each of the four callers on the `StaticBitmapImage`'s pixels (read into an N32/RGBA buffer, perturb, wrap back with `UnacceleratedStaticBitmapImage::Create`).

Write one paragraph in the report naming the point you chose and the evidence it covers all three APIs (which callers reach it). This is the §4.2 "back the claim with enumeration, not code-reading" obligation.

- [ ] **Step 2: Write the failing verification (`scripts/verify_sp3a.py`)**

Model it on `scripts/verify_sp2b.py` (Playwright sync API, `lib_shell`, `CAMOU_CONFIG` injection, one FAIL line per criterion never a traceback). It draws a fixed non-trivial scene onto a `<canvas>` (gradients + shapes + text so content varies), then asserts:

```
Criterion 1 (determinism, HIGHEST PRIORITY): with canvas:seed set, toDataURL()
  called twice in the same document returns byte-identical strings.
Criterion 2 (spoof visible): with canvas:seed set, toDataURL() differs from the
  same scene rendered by a stock run (no CAMOU_CONFIG).
Criterion 3 (off by default): with NO canvas:seed, toDataURL() is byte-identical
  to the stock run -- diff the two directly.
Criterion 4 (toBlob agrees): toBlob() output, read back, is deterministic across
  two calls and differs from stock, same as toDataURL.
```

Config: `CANVAS = json.dumps({"canvas:seed": 987654321})`. Reuse `lib_shell` to launch the binary with and without that env. Structure each check to emit `PASS`/`FAIL <criterion>` and an `ALL_PASS`/`FAIL` summary line, like verify_sp2b.

- [ ] **Step 3: Run the verification against the UNMODIFIED browser to confirm it fails**

Build stock `content_shell` (no Blink edits yet) and run `verify_sp3a.py` against it.
Expected: Criterion 1 may pass trivially (stock is already deterministic), but **Criterion 2 and 4 FAIL** (no spoof: seeded output equals stock) — proving the checks can go red before the feature exists. Record the output.

- [ ] **Step 4: Implement the snapshot-path perturbation**

At the point chosen in Step 1, gate on config and perturb the flat RGBA/BGRA buffer:

```cpp
// Camoucrome canvas readback noise. No-op when canvas:seed is unset/zero, so
// stock output is byte-identical (rule 5). Applied on the snapshot copy only,
// never the canvas store, so screen output is unchanged (§4.2).
camoucfg::PerturbRgbaFromConfig(pixel_ptr, byte_length,
                                camoucfg::ScopeFor(execution_context));
```

Resolve `execution_context` from the site (the canvas element's / OffscreenCanvas's `GetExecutionContext()` / `GetTopExecutionContext()`; in a worker this is the worker global scope, which is how worker parity comes for free — §4.4). Add `#include "components/camoucfg/canvas_noise.h"` and `#include "components/camoucfg/blink_scope.h"`. **If the buffer is BGRA rather than RGBA, that is fine** — `PerturbRgba` is channel-agnostic for RGB and only special-cases every 4th byte (alpha), which is byte 3 in both orderings.

- [ ] **Step 5: Build and re-run the verification**

`touch` the edited files, `autoninja -C out/Default content_shell` (confirm non-zero steps), run `verify_sp3a.py`.
Expected: `ALL_PASS` — all four criteria green.

- [ ] **Step 6: Add a degenerate mutant proof (like SP2b Task 2/3)**

Temporarily change `PerturbRgbaFromConfig` to ignore the seed (hardcode a fixed constant so content-fold is bypassed and every readback is identical regardless of scene) OR make the interception apply to the canvas store (draw-time) instead of the copy; rebuild; run `verify_sp3a.py`; confirm a specific criterion goes red (Criterion 2 for the first mutant; a to-be-added screen-unchanged criterion for the second — see Task 5). Restore, rebuild, confirm green. Record both outputs. This proves the verification actually exercises the property.

- [ ] **Step 7: Extract the patch and wire `apply.sh`**

From the checkout, diff the touched Blink files against the pre-SP3a base and write `patches/sp3a-canvas-noise.patch` (same extraction procedure as `patches/sp2b-humanized-cursor.patch`). Dry-run it with the invocation the build uses:

Run: `git -C <checkout-copy-at-base> apply --3way patches/sp3a-canvas-noise.patch` (or the `patch -p1 --dry-run` form if that is the project's applier) — confirm it reconstructs byte-identically.
Then append to `scripts/apply.sh` `PATCHES` array, LAST:
```
  "$ROOT/patches/sp3a-canvas-noise.patch"
```

- [ ] **Step 8: Commit**

```bash
git add scripts/verify_sp3a.py patches/sp3a-canvas-noise.patch scripts/apply.sh
git commit -m "feat(sp3a): perturb snapshot readback (toDataURL/toBlob/convertToBlob)"
```

---

### Task 5: Blink direct-read integration + full coverage / parity / screen verification

**Files:**
- Modify (checkout only): `third_party/blink/renderer/modules/canvas/canvas2d/base_rendering_context_2d.cc` (`getImageDataInternal`, `:358`), `third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc` (`readPixels`/`ReadPixelsHelper`, `:5273`/`:5284`).
- Modify: `scripts/verify_sp3a.py` (add criteria 5–10), `patches/sp3a-canvas-noise.patch` (extend).

**Interfaces:**
- Consumes: `camoucfg::PerturbRgbaFromConfig`, `camoucfg::ScopeFor` (as Task 4).
- Produces: the complete SP3a feature.

- [ ] **Step 1: Extend the verification with the remaining §6 criteria**

Add to `verify_sp3a.py`:

```
Criterion 5 (getImageData determinism): getImageData over the same rect twice
  returns identical bytes; seeded output differs from stock. (Item 6.)
Criterion 6 (readPixels determinism): a WebGL readPixels of a fixed scene twice
  returns identical bytes; seeded differs from stock. (Software GL is fine.)
Criterion 7 (full coverage): one page exercises toDataURL, toBlob, getImageData,
  readPixels, OffscreenCanvas.convertToBlob, and convertToBlob-in-worker; each
  seeded output differs from that path's stock output. (Item 8 -- the
  structural defence; update on every rebase.)
Criterion 8 (worker parity): a scene rendered on an OffscreenCanvas in a
  DEDICATED worker and the same scene in the document read back to identical
  bytes; repeat with a SHARED worker (own process -> exercises the
  env-inheritance claim, §4.4). (Item 7.)
Criterion 9 (screen unchanged): a DevTools-protocol screenshot (Page.captureScreenshot,
  NOT a canvas readback) of the rendered canvas is identical between seeded and
  stock builds -- proves noise is at readback, not draw time. (Item 10.)
Criterion 10 (accessors native): HTMLCanvasElement.prototype.toDataURL and
  CanvasRenderingContext2D.prototype.getImageData still stringify to
  "[native code]", and Object.keys(window) is unchanged vs stock. (Item 11.)
```

- [ ] **Step 2: Run against the Task-4 browser (snapshot path only) to confirm the new criteria fail where expected**

Expected: Criteria 5 and 6 FAIL (getImageData/readPixels not yet perturbed → seeded == stock); Criterion 9 should already PASS (snapshot noise is on the copy). Record output.

- [ ] **Step 3: Implement the direct-read perturbation**

In `getImageDataInternal` (after the pixels are copied into the `ImageData`'s buffer, before it is returned): perturb the `ImageData`'s backing `uint8_t*` (RGBA8, `data->data()` / the `SkImageInfo` size). In `ReadPixelsHelper` (after the copy into the caller's ArrayBufferView, but only for the default framebuffer per Camoufox's note — a user FBO is app-owned data, not a fingerprint surface): perturb the destination buffer. Same two-line gate as Task 4:

```cpp
camoucfg::PerturbRgbaFromConfig(dst_bytes, dst_length,
                                camoucfg::ScopeFor(execution_context));
```

`readPixels` may hand back a non-RGBA/UNSIGNED_BYTE format (e.g. float). `PerturbRgba` assumes 8-bit RGBA; **guard the readPixels site to only perturb when format/type is RGBA/UNSIGNED_BYTE** (the fingerprinting-relevant case), leaving exotic formats untouched. Note this guard in the report.

- [ ] **Step 4: Build, run the full verification**

`touch`, `autoninja -C out/Default content_shell` (non-zero steps), run `verify_sp3a.py`.
Expected: `ALL_PASS` — all ten criteria green. If Criterion 8 (worker parity) fails, the worker resolved a different scope/seed than the document — check `ScopeFor` returns the same config in both (it should: env-inherited `CAMOU_CONFIG`).

- [ ] **Step 5: Mutant proof for the screen-unchanged criterion**

Temporarily move ONE perturb call to draw time (perturb the canvas store instead of the readback copy); rebuild; confirm Criterion 9 (screen unchanged) goes red; restore; rebuild; confirm green. Record output. (Task 4's Step 6 covered the seed/content mutant; this closes item 10's guard.)

- [ ] **Step 6: Re-extract the patch, dry-run, run the sync checks**

Re-extract `patches/sp3a-canvas-noise.patch` from all touched Blink files. Dry-run apply → byte-identical reconstruction.
Run (Mac): `bash scripts/check_checkout_sync.sh` (or the project's sync check) → checkout Blink edits match the patch.
Run: `python3 scripts/check_additions_build.py` → still green.

- [ ] **Step 7: Full regression — every suite green**

Run the camoucfg unit suite and every existing verify script that a canvas change could touch:
Run: `./out/Default/components_camoucfg_unittests` → PASS (incl. new tests).
Run: `verify_sp0.py`, `verify_sp1a.py`, `verify_sp1a_chrome.py`, `verify_sp2.py`, `verify_sp2b.py`, `verify_sp5a.py`, `run_coherence_tests.sh` → all PASS (SP3a must not regress them).
Expected: all green. Record the counts.

- [ ] **Step 8: Commit**

```bash
git add scripts/verify_sp3a.py patches/sp3a-canvas-noise.patch
git commit -m "feat(sp3a): perturb direct-read readback (getImageData/readPixels) + full verify"
```

---

## Self-Review

**Spec coverage (§ of the SP3 design):**
- §3 canvas config keys → Task 1 (seed/density/strength; aaOffset/aaCapOffset explicitly deferred with reason).
- §4.2 chokepoints (snapshot vs direct-read) → Tasks 4/5, targets fixed by the measurement doc.
- §4.3 determinism + `derive_delta` primitive + `noise` wrapper → Task 2 (`DeriveDelta`/`DeriveUnit`), Task 3 (`PerturbRgba` folds content into seed).
- §4.4 worker parity (free via env inheritance) → Task 5 Criterion 8.
- §5 canvas↔readPixels same seed → both call `PerturbRgbaFromConfig` reading one `canvas:seed`; Criterion 7 exercises both.
- §6 verification items: 6→C1/C5, 7→C8, 8→C7, 9→C3, 10→C9, 11→C10, 13→Task 2 `DomainsAreUncorrelated`. Items 1–5,12 are WebGL/WebGPU → SP3b, correctly absent.
- §7.3 decided (position-based, content-fold) → Task 3.

**Placeholder scan:** every code step carries complete code except the Blink glue in Tasks 4/5, which is measure-then-implement by design (the exact pixel-buffer API is a checkout fact, as SP2b's input_handler was) — the plan gives the target file, the config gate, the exact camoucfg call, the decision rule, and a red-first verification, which is the most a from-the-Mac plan can pin without the tree. This is called out, not hidden.

**Type consistency:** `DeriveDelta(uint64_t,string_view,uint64_t,int32_t)->int32_t`, `DeriveUnit(uint64_t,string_view,uint64_t)->double`, `PerturbRgba(uint8_t*,size_t,uint64_t,double,int32_t)->void`, `PerturbRgbaFromConfig(uint8_t*,size_t,const ConfigScope&)->void` — used identically in every task that references them. Keys `kCanvasSeed`/`kCanvasNoiseDensity`/`kCanvasNoiseStrength` consistent. `seed` is `uint32` in config (`GetUint32`), widened to `uint64` at the one call in `PerturbRgbaFromConfig`.

**Known ceiling (ponytail):** the density gate calls `DeriveUnit` for every RGB channel even at the default density 0.0005 (one hash per channel; the second hash `DeriveDelta` fires only ~1/2000). A 4K canvas readback is ~24M channels → ~24M hashes. If a readback-latency tell is ever measured, gate in blocks or stride; not pre-optimised here.

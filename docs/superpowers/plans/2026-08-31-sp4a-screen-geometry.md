# SP4a — Screen / monitor geometry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drive the monitor-identity surfaces — `screen.*` dimensions/avail/depth, CSS `device-width`/`device-height`, and `screen.orientation` — from Camoucrome config at the Blink C++ level, coherently, with no injected JavaScript.

**Architecture:** Every read follows the SP0 hook pattern — compute the real value, then let config override it *last* (authoritative over the host display / DevTools), no-op when the key is absent. `screen.width` (JS, `Screen::GetRect`) and CSS `device-width` (`MediaValues::CalculateDeviceWidth`) read the **same** key so they can never diverge — the spec's headline two-place invariant. `screen.orientation` is **derived** from the spoofed dimensions (no key of its own) so it cannot contradict them.

**Tech Stack:** Chromium/Blink C++ (`third_party/blink/renderer`), the `//components/camoucfg` config layer (existing `GetUint32` accessor — **no new accessor**), GN build, Playwright 1.55.0 + content_shell CDP for verification.

**Measurement basis:** `docs/superpowers/measurements/2026-08-31-sp4a-screen-surfaces.md` (HEAD `a727b57805`). Read it — it has the choke points, the resolved open decisions, and the monitor-only scope decision.

## Global Constraints

- **Spoofing is C++/Blink only. Never inject JavaScript.** (Project invariant.)
- **SP0 hook pattern, every site:** real value first, config override LAST, no-op when the key is absent:
  `if (std::optional<uint32_t> v = camoucfg::GetUint32(camoucfg::ScopeFor(context), camoucfg::keys::kScreen...)) { /* use *v */ }`
- **No new camoucfg accessor.** Both choke points read `uint32` keys through the existing `camoucfg::GetUint32`. SP4a adds only new *keys*.
- **The two-place invariant is binding:** `Screen::GetRect` (non-available width/height) and `MediaValues::CalculateDeviceWidth/Height` MUST read `keys::kScreenWidth` / `kScreenHeight` — the identical constants — so JS `screen.width` and CSS `device-width` are the same value by construction.
- **`screen.orientation` has NO config key.** It is derived from the spoofed dims. Adding an orientation key would create the second source of truth the derivation exists to prevent.
- **`pixelDepth` has NO key.** `Screen::pixelDepth()` already returns `colorDepth()`; spoofing `colorDepth` carries it. One key, never two that can disagree.
- **Config override is authoritative over the host display AND over any DevTools/`Emulation` override** — the override goes last, after the real read.
- **Keys are DOTTED** (`screen.width` etc.) — a dotted key asserts it mirrors a real JS property path exactly.
- **Dead-code / `-Werror`:** this Chromium builds with `-Wunreachable-code-aggressive -Werror`. Do not leave a superseded body below an early return.
- **SP4a reports what it is told; it does not clamp or choose.** `availHeight < height` and `avail ≤ screen` coherence is the config author's / SP5a validator's job, not a clamp here (spec §8).

**Build/test harness:** the WSL checkout is `~/chromium/src` (HEAD `a727b57805`); reach it through the sourced helper `buildpc.sh` (`runwsl`, `pushcfg`, `pushto`, `pullfile`, `unittests`, `contentshell`, `verify`). `additions/camoucfg/*` files are **copied** into `<checkout>/components/camoucfg/` (push with `pushcfg`); Blink files are **edited in the checkout**, then extracted back to `patches/` with `pullfile` + `git diff`. After any code change confirm the build reports **NON-ZERO** steps (a stale `.o` gives a silent 0-step no-op with stale results). The two `CoherenceValidatorTest` cases are env-driven and FAIL bare — exclude them from plain `components_unittests` filters.

**SSH master:** if `runwsl` returns "Permission denied" / "Connection refused" / hangs, the ssh master dropped. A subagent must report **BLOCKED "ssh master down"** immediately and stop — no retry loop; the controller holds the password and re-establishes it.

---

### Task 1: Config keys — `screen.*`

**Files:**
- Modify: `additions/camoucfg/keys.h` (add 7 constants; grow `kAllKeys` 45 → 52)
- Modify: `additions/camoucfg/keys_unittest.cc` (add the 7 to the `declared` literal)
- Test: `additions/camoucfg/keys_unittest.cc` (`CamoucfgKeysTest.*`)

**Interfaces:**
- Produces: `camoucfg::keys::kScreenWidth`, `kScreenHeight`, `kScreenAvailWidth`, `kScreenAvailHeight`, `kScreenAvailLeft`, `kScreenAvailTop`, `kScreenColorDepth` — all `inline constexpr char[]`, values `"screen.width"`, `"screen.height"`, `"screen.availWidth"`, `"screen.availHeight"`, `"screen.availLeft"`, `"screen.availTop"`, `"screen.colorDepth"`. Tasks 2–4 consume these.

- [ ] **Step 1: Add the constants to `keys.h`.** Insert immediately after the `kNavigatorVendorSub` line (currently the last navigator constant, ~line 214), before the `// Every key above.` comment:

```cpp

// screen.* monitor-geometry overrides (SP4a). Dotted, mirroring the real JS
// property paths. The monitor is decoupled from the browser window, so these
// spoof coherently against a truthful (smaller) viewport.
//
// There is deliberately no screen.pixelDepth key: pixelDepth() returns
// colorDepth() in Blink and in every real browser, so kScreenColorDepth carries
// it -- a second key is a second source of truth that can disagree. There is
// likewise no screen.orientation key: orientation is derived from the spoofed
// width/height (SP4a Task 4), never overridden.
inline constexpr char kScreenWidth[] = "screen.width";
inline constexpr char kScreenHeight[] = "screen.height";
inline constexpr char kScreenAvailWidth[] = "screen.availWidth";
inline constexpr char kScreenAvailHeight[] = "screen.availHeight";
inline constexpr char kScreenAvailLeft[] = "screen.availLeft";
inline constexpr char kScreenAvailTop[] = "screen.availTop";
inline constexpr char kScreenColorDepth[] = "screen.colorDepth";
```

- [ ] **Step 2: Grow `kAllKeys`.** Change `std::array<std::string_view, 45>` to `std::array<std::string_view, 52>`, and add the seven constants at the end of the initializer list, just before the closing `};` (after `kNavigatorVendorSub,`):

```cpp
    kScreenWidth,
    kScreenHeight,
    kScreenAvailWidth,
    kScreenAvailHeight,
    kScreenAvailLeft,
    kScreenAvailTop,
    kScreenColorDepth,
```

- [ ] **Step 3: Add the seven to the `declared` literal in `keys_unittest.cc`.** In `EveryDeclaredConstantIsInAllKeys`'s `declared` set (after `kNavigatorVendorSub,`), add:

```cpp
      kScreenWidth, kScreenHeight, kScreenAvailWidth, kScreenAvailHeight,
      kScreenAvailLeft, kScreenAvailTop, kScreenColorDepth,
```

- [ ] **Step 4: Push + build + run the key tests.** From the Mac repo root:

```bash
source <scratchpad>/buildpc.sh
pushcfg keys.h && pushcfg keys_unittest.cc
unittests 'CamoucfgKeysTest.*'
```

Expected: BUILD reports non-zero steps; `CamoucfgKeysTest.EveryDeclaredConstantIsInAllKeys`, `.EveryKeyIsUnique`, `.EveryKeyIsNamespaced`, `.MetadataKeysAreAllRealKeys` all PASS. (`EveryKeyIsNamespaced` accepts the `.` in `screen.width`; `EveryKeyIsUnique` confirms 52 distinct.)

- [ ] **Step 5: Commit.**

```bash
git add additions/camoucfg/keys.h additions/camoucfg/keys_unittest.cc
git commit -m "feat(sp4a): add screen.* geometry config keys"
```

---

### Task 2: `Screen::GetRect` + `colorDepth` — screen dimensions & depth

**Files:**
- Modify (in checkout): `third_party/blink/renderer/core/frame/screen.cc` (`GetRect`, `colorDepth`)
- Create (Mac repo): `scripts/verify_sp4a.py` (criterion **S1a**; model the launch/CDP boilerplate on the existing `scripts/verify_sp1b.py`)

**Interfaces:**
- Consumes: `camoucfg::keys::kScreenWidth/Height/AvailWidth/AvailHeight/AvailLeft/AvailTop/ColorDepth` (Task 1).
- Produces: JS `screen.width/height/availWidth/availHeight/availLeft/availTop/colorDepth/pixelDepth` honor config. `pixelDepth == colorDepth` always.

**Context:** `core/BUILD.gn` already deps `//components/camoucfg` (line 411) — no BUILD.gn edit here. `Screen::GetExecutionContext()` exists (`screen.cc`). Add the includes if not already present:
`#include "components/camoucfg/mask_config.h"`, `#include "components/camoucfg/blink_scope.h"`, `#include "components/camoucfg/keys.h"`.

- [ ] **Step 1: Write criterion S1a in `scripts/verify_sp4a.py` (RED-first).** Model the harness on `scripts/verify_sp1b.py`. With config `{"screen.width":1920,"screen.height":1080,"screen.availWidth":1920,"screen.availHeight":1040,"screen.availLeft":0,"screen.availTop":0,"screen.colorDepth":30}`, evaluate in the page and assert:

```js
({
  width: screen.width, height: screen.height,
  availWidth: screen.availWidth, availHeight: screen.availHeight,
  availLeft: screen.availLeft, availTop: screen.availTop,
  colorDepth: screen.colorDepth, pixelDepth: screen.pixelDepth
})
// expect: width 1920, height 1080, availWidth 1920, availHeight 1040,
//         availLeft 0, availTop 0, colorDepth 30, pixelDepth 30 (== colorDepth)
```

Also assert the **stock-fallback** shape for this criterion: with **no** `CAMOU_CONFIG`, every one of these equals what the frozen stock baseline reports (capture/compare the same way `verify_sp1b.py` does).

- [ ] **Step 2: Run S1a against the current (unpatched) content_shell — expect RED.** Confirm the configured values do NOT yet appear (stock reports the host's real screen, not 1920×1080/depth 30). This proves the criterion can fail.

- [ ] **Step 3: Patch `Screen::GetRect`.** Insert the override right after `gfx::Rect rect = available ? screen_info.available_rect : screen_info.rect;` and before the physical-pixels quirk, so the quirk applies to the spoofed rect exactly as it does to the real one:

```cpp
  // Camoucrome (SP4a): config override, authoritative over the host display.
  // Same keys media_values.cc reads, so JS screen.* and CSS device-* agree.
  ExecutionContext* camou_ctx = GetExecutionContext();
  const camoucfg::ConfigScope& camou_scope = camoucfg::ScopeFor(camou_ctx);
  if (available) {
    if (std::optional<uint32_t> v =
            camoucfg::GetUint32(camou_scope, camoucfg::keys::kScreenAvailLeft))
      rect.set_x(static_cast<int>(*v));
    if (std::optional<uint32_t> v =
            camoucfg::GetUint32(camou_scope, camoucfg::keys::kScreenAvailTop))
      rect.set_y(static_cast<int>(*v));
    if (std::optional<uint32_t> v =
            camoucfg::GetUint32(camou_scope, camoucfg::keys::kScreenAvailWidth))
      rect.set_width(static_cast<int>(*v));
    if (std::optional<uint32_t> v =
            camoucfg::GetUint32(camou_scope, camoucfg::keys::kScreenAvailHeight))
      rect.set_height(static_cast<int>(*v));
  } else {
    if (std::optional<uint32_t> v =
            camoucfg::GetUint32(camou_scope, camoucfg::keys::kScreenWidth))
      rect.set_width(static_cast<int>(*v));
    if (std::optional<uint32_t> v =
            camoucfg::GetUint32(camou_scope, camoucfg::keys::kScreenHeight))
      rect.set_height(static_cast<int>(*v));
  }
```

- [ ] **Step 4: Patch `Screen::colorDepth`.** Add the override after the `if (!DomWindow()) return unknown_color_depth;` guard, before the `return GetScreenInfo().depth == 0 ? ...`:

```cpp
  // Camoucrome (SP4a): config override. pixelDepth() returns colorDepth(), so
  // this one key carries both -- no separate pixelDepth key exists.
  if (std::optional<uint32_t> v = camoucfg::GetUint32(
          camoucfg::ScopeFor(GetExecutionContext()),
          camoucfg::keys::kScreenColorDepth)) {
    return *v;
  }
```

- [ ] **Step 5: Build content_shell + run S1a — expect GREEN.**

```bash
contentshell    # confirm NON-ZERO steps
# copy verify_sp4a.py into ~/camoucrome-verify, then:
verify verify_sp4a.py
```

Expected: S1a PASS (1920/1080/1920/1040/0/0/30/30) AND the bare-config fallback equals the stock baseline.

- [ ] **Step 6: Commit** (Blink files live only in the checkout; commit the verify script on the Mac).

```bash
git add scripts/verify_sp4a.py
git commit -m "test(sp4a): verify screen dimension + depth spoof (S1a)"
```

Record for patch extraction in Task 5: `screen.cc` is now edited in the checkout.

---

### Task 3: `MediaValues::CalculateDeviceWidth/Height` — CSS `device-*` agreement

**Files:**
- Modify (in checkout): `third_party/blink/renderer/core/css/media_values.cc` (`CalculateDeviceWidth`, `CalculateDeviceHeight`)
- Modify (Mac repo): `scripts/verify_sp4a.py` (add criterion **S1b**)

**Interfaces:**
- Consumes: `camoucfg::keys::kScreenWidth`, `kScreenHeight` — the **same** constants Task 2 reads.
- Produces: CSS `matchMedia('(device-width: Npx)')` and `(device-height: …)` agree byte-for-byte with `screen.width/height`.

**Context:** `core/BUILD.gn` already deps camoucfg. `CalculateDeviceWidth(LocalFrame* frame)` — obtain the scope from `frame->DomWindow()` (a `LocalDOMWindow`, which is an `ExecutionContext`). Add the camoucfg includes to `media_values.cc` if absent.

- [ ] **Step 1: Add criterion S1b to `verify_sp4a.py` (RED-first).** With the same config as S1a (`screen.width:1920, screen.height:1080`), assert:

```js
({
  dw1920: matchMedia('(device-width: 1920px)').matches,   // expect true
  dwWrong: matchMedia('(device-width: 1280px)').matches,  // expect false
  dh1080: matchMedia('(device-height: 1080px)').matches,  // expect true
  dhWrong: matchMedia('(device-height: 800px)').matches,  // expect false
  agree: matchMedia('(device-width: ' + screen.width + 'px)').matches // expect true
})
```

- [ ] **Step 2: Run S1b against the current content_shell (screen.cc patched from Task 2, media_values NOT yet) — expect RED.** `device-width:1920` is `false` and `agree` is `false`, because CSS still reads the host's real width while JS reads 1920 — exactly the two-surface contradiction this task closes.

- [ ] **Step 3: Patch `CalculateDeviceWidth`.** Insert after `int device_width = screen_info.rect.width();` and before the physical-pixels quirk:

```cpp
  // Camoucrome (SP4a): same key as Screen::width(), so CSS device-width can
  // never diverge from JS screen.width.
  if (std::optional<uint32_t> v = camoucfg::GetUint32(
          camoucfg::ScopeFor(frame->DomWindow()), camoucfg::keys::kScreenWidth)) {
    device_width = static_cast<int>(*v);
  }
```

- [ ] **Step 4: Patch `CalculateDeviceHeight`** identically, after `int device_height = screen_info.rect.height();`, reading `keys::kScreenHeight` into `device_height`.

- [ ] **Step 5: Build + run S1a and S1b — expect GREEN.**

```bash
contentshell
verify verify_sp4a.py
```

Expected: S1a still PASS, S1b PASS (`dw1920`/`dh1080`/`agree` true; the two `Wrong` false).

- [ ] **Step 6: Commit.**

```bash
git add scripts/verify_sp4a.py
git commit -m "test(sp4a): verify CSS device-* agrees with screen.* (S1b)"
```

Record: `media_values.cc` now edited in the checkout.

---

### Task 4: `ScreenOrientation` — derive type/angle from spoofed dims

**Files:**
- Modify (in checkout): `third_party/blink/renderer/modules/screen_orientation/screen_orientation.cc` (`type()`, `angle()`; add a private derivation helper)
- Modify (in checkout): `third_party/blink/renderer/modules/screen_orientation/screen_orientation.h` (declare the helper)
- Modify (in checkout): `third_party/blink/renderer/modules/screen_orientation/BUILD.gn` (add camoucfg dep)
- Modify (Mac repo): `scripts/verify_sp4a.py` (criteria **S2**, **S3**)

**Interfaces:**
- Consumes: `camoucfg::keys::kScreenWidth`, `kScreenHeight`.
- Produces: `screen.orientation.type`/`.angle` derived from the spoofed dims when both are configured; real display value otherwise.

**Context:** `modules/screen_orientation/BUILD.gn` does NOT yet dep camoucfg (unlike `core`); this task adds it. `ScreenOrientation` has `ExecutionContext* GetExecutionContext() const`. Derivation rule (from the measurement doc): both `screen.width` and `screen.height` present → `width > height ? landscape-primary : portrait-primary`, angle `0`; if either absent, fall through to the real `type_`/`angle_`.

- [ ] **Step 1: Add criteria S2 and S3 to `verify_sp4a.py` (RED-first).**

S2 — two configs:
```js
// config {screen.width:1920, screen.height:1080}:
({ type: screen.orientation.type, angle: screen.orientation.angle })
// expect: type 'landscape-primary', angle 0
// config {screen.width:1080, screen.height:1920}:
// expect: type 'portrait-primary', angle 0
```

S3 — a bogus orientation key is not honored (there is no such key):
```js
// config {screen.width:1920, screen.height:1080, "screen.orientation":"portrait-primary"}:
screen.orientation.type
// expect: 'landscape-primary' -- derived from dims, the stray key ignored.
// (Existing camoucfg::UnrecognisedKeys() surfaces it as unrecognised; the
//  load-time hard-reject is SP5a's validator, out of SP4a scope.)
```

- [ ] **Step 2: Run S2/S3 against the current content_shell — expect RED.** With 1920×1080 configured, `screen.orientation.type` still reflects the host display (e.g. from the controller), not derived — so S2/S3 fail.

- [ ] **Step 3: Add camoucfg dep to `screen_orientation/BUILD.gn`.** In the `blink_modules_sources("screen_orientation")` `deps = [ ... ]`, add:

```gn
    "//components/camoucfg",
```

- [ ] **Step 4: Declare the helper in `screen_orientation.h`.** In the private section of `class ScreenOrientation`, add:

```cpp
  // Camoucrome (SP4a): derived orientation from spoofed screen.width/height,
  // or nullopt when the dims are not both configured.
  std::optional<display::mojom::blink::ScreenOrientation>
  CamoucromeDerivedOrientation() const;
```

- [ ] **Step 5: Implement the helper + rewrite `type()`/`angle()` in `screen_orientation.cc`.** Add the camoucfg includes (`mask_config.h`, `blink_scope.h`, `keys.h`). Replace the existing `type()` and `angle()` bodies:

```cpp
std::optional<display::mojom::blink::ScreenOrientation>
ScreenOrientation::CamoucromeDerivedOrientation() const {
  const camoucfg::ConfigScope& scope =
      camoucfg::ScopeFor(GetExecutionContext());
  std::optional<uint32_t> w =
      camoucfg::GetUint32(scope, camoucfg::keys::kScreenWidth);
  std::optional<uint32_t> h =
      camoucfg::GetUint32(scope, camoucfg::keys::kScreenHeight);
  if (!w || !h)
    return std::nullopt;
  return *w > *h
             ? display::mojom::blink::ScreenOrientation::kLandscapePrimary
             : display::mojom::blink::ScreenOrientation::kPortraitPrimary;
}

V8OrientationType ScreenOrientation::type() const {
  if (std::optional<display::mojom::blink::ScreenOrientation> derived =
          CamoucromeDerivedOrientation()) {
    return V8OrientationType(OrientationTypeToV8Enum(*derived));
  }
  return V8OrientationType(OrientationTypeToV8Enum(type_));
}

uint16_t ScreenOrientation::angle() const {
  if (CamoucromeDerivedOrientation())
    return 0;  // primary orientation of either axis sits at 0 degrees.
  return angle_;
}
```

- [ ] **Step 6: Build + run the full script (S1a, S1b, S2, S3) — expect GREEN.**

```bash
contentshell
verify verify_sp4a.py
```

Expected: S2 PASS (landscape-primary/0 and portrait-primary/0), S3 PASS (stray key ignored), S1a/S1b still PASS.

- [ ] **Step 7: Commit.**

```bash
git add scripts/verify_sp4a.py
git commit -m "test(sp4a): verify screen.orientation derives from spoofed dims (S2,S3)"
```

Record: `screen_orientation.cc`, `screen_orientation.h`, `screen_orientation/BUILD.gn` now edited in the checkout.

---

### Task 5: Extract patch, wire apply.sh, full verify + regression

**Files:**
- Create (Mac repo): `patches/sp4a-screen.patch` (extracted from the checkout: `screen.cc`, `media_values.cc`, `screen_orientation.cc`, `screen_orientation.h`, `screen_orientation/BUILD.gn`)
- Modify (Mac repo): `scripts/apply.sh` (append the sp4a patch, LAST in order)
- Modify (Mac repo): `scripts/verify_sp4a.py` (add criteria **S4** no-new-surface, **S5** full stock-fallback)

**Interfaces:**
- Consumes: all Task 2–4 checkout edits.
- Produces: `patches/sp4a-screen.patch` applying cleanly after the existing chain; `verify_sp4a.py` S1a–S5 all pass configured, and all values equal stock when bare.

- [ ] **Step 1: Add S4 (no new observable surface) to `verify_sp4a.py`.** Against the stock baseline, assert `Object.keys(window)` and `Object.keys(navigator)` are byte-identical to stock, and that each touched accessor still reports native:

```js
[
  Object.getOwnPropertyDescriptor(Screen.prototype,'width').get.toString(),
  Object.getOwnPropertyDescriptor(Screen.prototype,'colorDepth').get.toString(),
].map(s => s.includes('[native code]'))   // expect [true, true]
```

- [ ] **Step 2: Add S5 (full stock fallback).** Run the entire criterion set with **no** `CAMOU_CONFIG` and assert every screen/orientation/device value equals the frozen stock baseline (spec verify item 17).

- [ ] **Step 3: Extract the patch from the checkout.** For each edited Blink file, pull it and diff against its pristine `git show HEAD:<path>` — or simpler, run `git diff` in the checkout scoped to the five paths and pull the result:

```bash
runwsl "cd \$HOME/chromium/src && git diff -- \
  third_party/blink/renderer/core/frame/screen.cc \
  third_party/blink/renderer/core/css/media_values.cc \
  third_party/blink/renderer/modules/screen_orientation/screen_orientation.cc \
  third_party/blink/renderer/modules/screen_orientation/screen_orientation.h \
  third_party/blink/renderer/modules/screen_orientation/BUILD.gn" > /tmp/sp4a.diff
# then pull /tmp/sp4a.diff (written on the checkout) to patches/sp4a-screen.patch
```

Confirm the patch touches **only** those five files and contains zero contamination from other in-flight SPs (`git diff` scoped to the paths guarantees this).

- [ ] **Step 4: Verify the patch applies cleanly on a pristine tree.** The repo applies patches with `git apply --3way` (`scripts/apply.sh`). Confirm sp4a applies after the existing chain (sp0 → sp1a → sp5a → sp2a → sp2b → sp3a → sp3b → sp1b → **sp4a**):

```bash
runwsl "cd \$HOME/chromium/src && git stash && git apply --3way --check <all prior patches> patches/sp4a-screen.patch; git stash pop"
```

(Or the project's `scripts/apply.sh` dry-run path.) Append the sp4a patch line to `scripts/apply.sh` LAST.

- [ ] **Step 5: Full SP4a verify — GREEN configured, GREEN bare.**

```bash
verify verify_sp4a.py            # S1a,S1b,S2,S3,S4,S5 ALL_PASS
```

- [ ] **Step 6: Regression — the prior SPs still pass.**

```bash
unittests 'CamoucfgKeysTest.*:AssembleRawConfigTest.*:ParseConfigTest.*:ParseConfigDeathTest.*:GettersTest.*:MaskConfigTest.*:DeriveTest.*:DeriveDeltaTest.*:DeriveUnitTest.*:PerturbRgbaTest.*:MouseTrajectoriesTest.*'
verify verify_sp1b.py            # N1-N8 ALL_PASS
verify verify_sp3a.py            # 10/10
verify verify_sp3b.py            # V1-V9
```

Expected: all green — SP4a touches disjoint files, so no regression.

- [ ] **Step 7: Commit.**

```bash
git add patches/sp4a-screen.patch scripts/apply.sh scripts/verify_sp4a.py
git commit -m "feat(sp4a): screen/monitor geometry spoof — patch, apply wiring, full verify"
```

---

## Self-Review

- **Spec coverage:** SP4a delivers spec §3.1 screen.*/device-*/orientation and verify items 1 (S1a+S1b), 2 (S2+S3), 16 (S4), 17 (S5). Items 3 (full inner≤outer≤avail≤screen), 4–15 belong to later SP4 slices / other SPs. `availHeight < height` reporting is faithful; its *enforcement* is SP5a (documented, §8).
- **Type consistency:** `kScreenWidth`/`kScreenHeight` are read by the identical constant in both `screen.cc` and `media_values.cc` (the binding invariant). `GetUint32` returns `std::optional<uint32_t>`; every site casts to `int` for `gfx::Rect`/`device_width`. `CamoucromeDerivedOrientation()` returns `std::optional<display::mojom::blink::ScreenOrientation>`, consumed by both `type()` and `angle()`.
- **No placeholders:** every code step shows the exact code; every run step shows the command and expected result.
- **No new accessor, no new JS:** all reads via existing `camoucfg::GetUint32`; all edits are C++/Blink.

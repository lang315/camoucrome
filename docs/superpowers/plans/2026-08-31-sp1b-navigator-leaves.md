# SP1b — navigator leaf accessors + languages

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the renderer-side `navigator.*` identity leaves controllable from config — `platform`, `appVersion`, `deviceMemory`, `maxTouchPoints`, `language`/`languages`, and the near-constants — and disable the "Request tablet site" command that desynchronises one surface from the chosen fingerprint.

**Architecture:** Each Blink leaf accessor reads its config key (real value first, config override last, no-op when absent — the SP0 `hardwareConcurrency` pattern) via the existing `camoucfg::Get*` API. No new camoucfg accessor. All target Blink files are pristine, so the patch is a clean `git diff HEAD`.

**Tech Stack:** C++17 (Chromium/Blink), GN/gtest, Python+Playwright verify (`lib_shell`).

## Global Constraints

- C++/Blink only, never injected JS. Config keys are DOTTED `navigator.*` (they mirror real JS property paths exactly — the `kNavigatorHardwareConcurrency` precedent). `EveryKeyIsNamespaced` accepts a `.`; `EveryDeclaredConstantIsInAllKeys` needs every new key in BOTH `kAllKeys` (size bumped) and the `declared` literal in `keys_unittest.cc`.
- Rule 5: absent key → the real computed value, unchanged. Config override is applied LAST (authoritative over any CDP/DevTools emulation), exactly as SP0's hardwareConcurrency hook does.
- **SP1 must NOT parse a user-agent string locally.** The claimed OS is derived once in `derive.{h,cc}` (`ClaimedOs`); SP1b populates inputs (`navigator.platform`) and, where it needs the OS, consumes that — it does not re-derive.
- Near-constants (`appCodeName`/`appName`/`product`/`productSub`/`vendor`/`vendorSub`) default to real Chrome's fixed strings and change only under an explicit expert override — spoofing them while claiming Chrome is an instant tell.
- Languages are two-channel: `navigator.languages` (this task) must be kept coherent with SP1a's `Accept-Language` header by the profile generator (different keys); document the coupling, do not try to unify the keys here.
- The scalar hook resolves scope via `camoucfg::ScopeFor(GetExecutionContext())` (works in workers too — the SP3b worker-parity result confirms this idiom reaches worker scope). Include `components/camoucfg/{blink_scope.h,keys.h,mask_config.h}`; `core/BUILD.gn` already deps `//components/camoucfg`.
- `scripts/check_additions_build.py` + `check_checkout_sync.sh` green.

**Out of scope:** the state flags `doNotTrack`/`cookieEnabled`/`onLine`/`pdfViewerEnabled` (real user/environment settings, not fingerprint identity — spoofing them is odd and low-value; revisit only if a coherence need is measured). UA string / userAgentData / Accept-Language (SP1a, shipped). Cross-surface coherence enforcement (SP5).

**Build/verify env:** see the SP3b plans. WSL checkout as user `lang`; `components_unittests` for camoucfg; `content_shell` + a new `scripts/verify_sp1b.py` from `~/camoucrome-verify`. SP1b needs no SwiftShader (no GL).

---

## File Structure

- `additions/camoucfg/keys.h` + `keys_unittest.cc` — MODIFY: add the `navigator.*` keys.
- Blink (checkout only → `patches/sp1b-navigator-leaves.patch`, a NEW patch): `core/frame/navigator.cc` (platform + near-constants on `Navigator`), `core/frame/navigator_id.cc` (appVersion + near-constants on `NavigatorID`), `core/frame/navigator_device_memory.cc` (deviceMemory), `core/frame/navigator_language.cc` (language/languages), and `chrome/browser/ui/browser_commands.cc` (disable tablet-site). Possibly `core/frame/navigator.cc` maxTouchPoints once located.
- `scripts/verify_sp1b.py` — CREATE.
- `scripts/apply.sh` — MODIFY: append `patches/sp1b-navigator-leaves.patch` LAST.

---

### Task 1: `navigator.*` config keys

**Files:** Modify `additions/camoucfg/keys.h`, `additions/camoucfg/keys_unittest.cc`.

**Interfaces:**
- Produces: `kNavigatorPlatform="navigator.platform"`, `kNavigatorAppVersion="navigator.appVersion"`, `kNavigatorDeviceMemory="navigator.deviceMemory"`, `kNavigatorMaxTouchPoints="navigator.maxTouchPoints"`, `kNavigatorLanguage="navigator.language"`, `kNavigatorLanguages="navigator.languages"`, `kNavigatorAppCodeName`, `kNavigatorAppName`, `kNavigatorProduct`, `kNavigatorProductSub`, `kNavigatorVendor`, `kNavigatorVendorSub` (all `"navigator.<name>"`).

- [ ] **Step 1: Baseline** — `unittests 'CamoucfgKeysTest.*'` green; note the current `kAllKeys` size.
- [ ] **Step 2: Add the key constants** to `keys.h` with a `navigator.*` comment block (dotted keys mirror real JS property paths; near-constants are expert-override-only). 12 new keys.
- [ ] **Step 3: Add all 12 to `kAllKeys` (bump size) AND the `declared` literal in `keys_unittest.cc`.**
- [ ] **Step 4:** `unittests 'CamoucfgKeysTest.*'` → PASS (`EveryDeclaredConstantIsInAllKeys`/`EveryKeyIsNamespaced` prove the dotted keys are wired). `python3 scripts/check_additions_build.py` → PASS.
- [ ] **Step 5: Commit** — `feat(sp1b): navigator.* config keys`.

---

### Task 2: scalar overrides — platform, appVersion, deviceMemory, maxTouchPoints, near-constants

**Files (checkout):** `core/frame/navigator.cc`, `core/frame/navigator_id.cc`, `core/frame/navigator_device_memory.cc`. Create `scripts/verify_sp1b.py`, `patches/sp1b-navigator-leaves.patch`; modify `scripts/apply.sh`.

**Interfaces:** Consumes the Task-1 keys + `camoucfg::GetString/GetDouble/GetInt32(scope, key)` + `camoucfg::ScopeFor(GetExecutionContext())`.

**Measure-then-implement** (confirm the exact accessor signatures + how each returns its real value on the live checkout).

- [ ] **Step 1: Write `scripts/verify_sp1b.py`** (model on verify_sp3b's structure — Playwright sync + `lib_shell` + `CAMOU_CONFIG`, one FAIL line per criterion). Criteria:
  - N1 platform: with `navigator.platform` set, `navigator.platform === "<configured>"`; unset → a plausible real value (non-empty string).
  - N2 appVersion: with `navigator.appVersion` set, matches; unset → real.
  - N3 deviceMemory: with `navigator.deviceMemory` set (e.g. `8`), `navigator.deviceMemory === 8`; unset → real (a number in {0.25,0.5,1,2,4,8}).
  - N4 near-constants default to Chrome's real strings when unset (`appCodeName==="Mozilla"`, `product==="Gecko"`, `vendor==="Google Inc."`, `productSub==="20030107"`, `appName==="Netscape"`, `vendorSub===""`), and to the configured value when set.
  - N5 maxTouchPoints (only if located — see Step 3): configured value reflected; else record as a deferred gap, do NOT fake-pass.
  RED-first: run against a stock/SP3b content_shell → N1-N4 FAIL where config is set.
- [ ] **Step 2: Implement platform** in `Navigator::platform()` (`navigator.cc:58`): before the DevTools `platform_override` block, if `camoucfg::GetString(camoucfg::ScopeFor(GetExecutionContext()), keys::kNavigatorPlatform)` is set, return it (config wins over the DevTools override). Add the camoucfg includes.
- [ ] **Step 3: Implement the rest.** `NavigatorID::appVersion()` (`navigator_id.cc:55`) + the near-constants (`appCodeName`/`appName`/`product` there; `productSub`/`vendor`/`vendorSub` in `navigator.cc`) → each `GetString(...)`-overrides-real. `NavigatorDeviceMemory::deviceMemory()` (`navigator_device_memory.cc:14`) → `GetDouble(..., kNavigatorDeviceMemory)` overrides the approximated value (return as `float`). **maxTouchPoints:** locate its implementation first (`git grep -n "maxTouchPoints" third_party/blink/renderer/` — likely `NavigatorMaxTouchPoints`/a pointer path). If found and simple, hook it with `GetInt32(..., kNavigatorMaxTouchPoints)`; if it lives in a screen/device path that is not a clean single accessor, STOP and report it as a deferred gap for a follow-up rather than forcing it.
- [ ] **Step 4: Build + verify GREEN** (`contentshell`; `verify_sp1b.py` N1-N4 pass, N5 pass-or-deferred). Extract `patches/sp1b-navigator-leaves.patch` = `git diff HEAD -- <the touched files>` (all pristine, so this is SP1b-only; grep 0 for any sp3a/sp3b/sp0 marker to be safe). Wire apply.sh LAST.
- [ ] **Step 5: Commit** — `feat(sp1b): spoof navigator platform/appVersion/deviceMemory/near-constants`.

---

### Task 3: `navigator.language` / `navigator.languages`

**Files (checkout):** `core/frame/navigator_language.cc`. Modify `scripts/verify_sp1b.py`, `patches/sp1b-navigator-leaves.patch`.

- [ ] **Step 1: Extend verify_sp1b.py** — N6: with `{"navigator.language":"fr-FR","navigator.languages":["fr-FR","fr","en"]}`, `navigator.language==="fr-FR"` and `navigator.languages` deep-equals `["fr-FR","fr","en"]`; unset → real (`navigator.languages` a non-empty array, `navigator.language` its first element). RED-first.
- [ ] **Step 2: Implement.** `NavigatorLanguage::language()` (`:39`) → `GetString(..., kNavigatorLanguage)` overrides. `NavigatorLanguage::languages()` (`:43`, returns `const Vector<String>&`) → if `GetStringList(..., kNavigatorLanguages)` is non-empty, return a Vector<String> built from it. **Caching caution:** `languages()` may cache into a member (`languages_` / `NavigatorLanguage` stores a cached vector) — confirm how the real value is stored/returned and make the override integrate with (or bypass) that cache so it is stable across calls and matches `language()`. If the cache makes a clean override awkward, override at the point the cache is populated. Add camoucfg includes.
  Add a comment: coherence with SP1a's `Accept-Language` header is the profile generator's job (different keys) — not enforced here.
- [ ] **Step 3: Build + verify GREEN (N1-N6); re-extract patch; commit** — `feat(sp1b): spoof navigator.language/languages`.

---

### Task 4: disable "Request tablet site"

**Files (checkout):** `chrome/browser/ui/browser_commands.cc`. Modify `scripts/verify_sp1b.py` (or note it is not page-verifiable), `patches/sp1b-navigator-leaves.patch`.

- [ ] **Step 1: Implement.** In `ToggleRequestTabletSite()` (`browser_commands.cc:2809`), make it a no-op (early return) in this build — the command lets a user desync one surface (Android tablet UA) from the chosen fingerprint. Prefer the minimal change: early-return at the top of `ToggleRequestTabletSite` (leaving `SetAndroidOsForTabletSite` defined but uncalled), with a comment citing the SP1 spec's reasoning. Do NOT route `kOsOverrideForTabletSite` through config — the point is to remove the desync capability, not make it configurable.
- [ ] **Step 2: Verify.** This is a browser-menu command, not page-reachable, so `verify_sp1b.py` cannot exercise it via CDP. Verify by (a) build succeeds, (b) a code assertion in the report that the function early-returns before `SetAndroidOsForTabletSite`. Note in verify_sp1b.py's docstring that the tablet-site disable is build/inspection-verified, not page-verified (like SP3a's screen-unchanged rationale for what a page can't reach).
- [ ] **Step 3: Re-extract patch (now includes browser_commands.cc); confirm apply.sh; regression: verify_sp3a/verify_sp3b still pass (SP1b touches unrelated files); camoucfg unit green. Commit** — `feat(sp1b): disable Request-tablet-site desync command`.

---

## Self-Review

- Spec items 5 (platform/appVersion/scalars), 6 (deviceMemory/maxTouchPoints), 7 (languages), 9 (near-constants) → Tasks 2,3; the tablet-site bypass → Task 4. State flags explicitly out-of-scope (stated). No UA parsing (platform is a direct key, not derived).
- Placeholder scan: the SP0 hook pattern is complete code; each Blink hook is measure-then-implement with the exact site + key + accessor given. maxTouchPoints is explicitly conditional (locate-or-defer, no fake-pass) — the one genuinely unverified surface.
- Type consistency: `GetString`→platform/appVersion/language/near-constants; `GetDouble`→deviceMemory; `GetInt32`→maxTouchPoints; `GetStringList`→languages. `ScopeFor(GetExecutionContext())` at every site.
- Known ceiling: near-constants are exposed as knobs but default to Chrome's real strings; the plan does not enforce "don't set them incoherently" (expert-override, generator's job). Languages↔Accept-Language coherence is the generator's job (documented, two different keys).

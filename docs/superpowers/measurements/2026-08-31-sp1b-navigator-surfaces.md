# SP1b navigator-surface measurements

Measured 2026-08-31 against `~/chromium/src` (HEAD `a727b57805`), read-only `git grep`.
SP1b is the Blink-side leaf accessors + languages (SP1 spec §"What the producer
patch cannot cover"); SP1a (browser-process UA producer) is already shipped.

## Scalar-hook template (SP0, already in the checkout)

`NavigatorBase::hardwareConcurrency()` in
`third_party/blink/renderer/core/execution_context/navigator_base.cc` is the
pattern every SP1b scalar hook mirrors — real value first, config override LAST
(authoritative over CDP emulation), no-op when the key is absent (rule 5):

```cpp
if (std::optional<uint32_t> configured = camoucfg::GetUint32(
        camoucfg::ScopeFor(GetExecutionContext()),
        camoucfg::keys::kNavigatorHardwareConcurrency)) {
  value = *configured;
}
```
Includes: `components/camoucfg/{blink_scope.h,keys.h,mask_config.h}`. `core/BUILD.gn`
already deps `//components/camoucfg`. Read via existing `GetString/GetUint32/GetDouble/
GetStringList` — **SP1b needs NO new camoucfg accessor**, only new keys.

## SP1b surfaces (all pristine in the checkout → clean `git diff HEAD` patch, no
index-baseline separation needed)

| Surface | Hook site | Notes |
|---|---|---|
| `navigator.platform` | `Navigator::platform()` `core/frame/navigator.cc:58` | Already has a `platform_override` slot (:64, DevTools). Hook config here — config wins over the DevTools override. Avoids touching `navigator_base.cc` (which SP0 already edits), so no shared-file separation. |
| `navigator.appVersion` | `NavigatorID::appVersion()` `core/frame/navigator_id.cc:55` | UA-adjacent, computed separately. |
| near-constants: `appCodeName`/`appName`/`product`/`productSub`/`vendor`/`vendorSub` | `navigator_id.cc:47,51,86` + `navigator.cc` | Real Chrome fixed strings (Mozilla/Netscape/Gecko/20030107/Google Inc./empty). Default to those; expert override only — spoofing them while claiming Chrome is a tell. |
| `navigator.deviceMemory` | `NavigatorDeviceMemory::deviceMemory()` `core/frame/navigator_device_memory.cc:14` | Returns `ApproximatedDeviceMemory::GetApproximatedDeviceMemory()` (float, GDPR-bucketed 0.25..8). |
| `navigator.language` / `languages` | `NavigatorLanguage::language()` `:39` / `languages()` `:43` `core/frame/navigator_language.cc` | Two-channel: must agree with SP1a's Accept-Language. Different keys (`navigator.languages` vs `headers.Accept-Language`); cross-channel coherence is the profile generator's job (document it). |
| `navigator.maxTouchPoints` | **UNLOCATED** — not in `core/frame/*.cc`; spec says declared in `core/events/navigator_events.idl`, impl unverified. | Locate during implementation (likely a screen/pointer path) or defer with a note. |

## Producer bypass SP1b owns: disable "Request tablet site"

`ToggleRequestTabletSite()` `chrome/browser/ui/browser_commands.cc:2809` →
`SetAndroidOsForTabletSite()` `:2828` → builds a UA with hardcoded
`kOsOverrideForTabletSite = "Linux; Android 9; Chrome tablet"` (`:273`, used `:2837`)
BELOW SP1a's substitution point. Not page-reachable (menu command, needs a human
click; CDP never reaches it) and internally coherent, BUT it lets a user desync one
surface from the chosen fingerprint. Spec's decision: **disable the command in
Camoucrome** (same reasoning as presenting-as-Chrome), not route it through the config.

## Keys (new, `navigator.` DOTTED — they mirror real JS property paths exactly)

`navigator.platform`, `navigator.appVersion`, `navigator.deviceMemory`,
`navigator.language`, `navigator.languages`, `navigator.maxTouchPoints`, plus the
near-constant keys. `keys.h` already has `kNavigatorHardwareConcurrency` (dotted) as
precedent; add these to `kAllKeys` + the `declared` literal.

## Consequence for the plan

SP1b is smaller and cleaner than SP3b: no new accessor, pristine target files (clean
patch), all renderer-side + fully verifiable in content_shell. Split candidate:
- **Task 1**: keys.
- **Task 2**: scalar overrides (platform, appVersion, deviceMemory, maxTouchPoints,
  near-constants) + verify.
- **Task 3**: languages (language/languages, coherence note) + verify.
- **Task 4**: disable tablet-site command + verify (small; could fold into 2).

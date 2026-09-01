# SP4-timezone/locale Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `CAMOU_CONFIG` drive a coherent timezone + locale override at the Blink C++ level, so a standalone (non-CDP) launch spoofs `Intl`/`Date` timezone and locale — including in workers — exactly as the native CDP path does.

**Architecture:** Reuse Chromium's existing native controllers — `blink::TimeZoneController::SetTimeZoneOverride` and `blink::LocaleController::SetLocaleOverride` (the same C++ mechanisms CDP `Emulation.set{Timezone,Locale}Override` drive; page-invisible, worker-covering). Read `timezone:id` and `locale:tag` from `//components/camoucfg` once per renderer at `CoreInitializer::Initialize()` and apply them. `locale:tag` falls back to SP1b's `navigator.language` for coherence. NOT a reimplementation of Camoufox's Firefox-engine rewrite.

**Tech Stack:** Chromium/Blink C++, `//components/camoucfg`, GN, Playwright verify over content_shell CDP.

## Global Constraints

- All spoofing at the C++/Blink level, NEVER injected JS. (project invariant)
- SP0 hook pattern: real value first, config override applied only when the key is present; no-op when absent (rule 5). Both keys absent → real OS timezone/locale.
- Config-key naming: dot mirrors a JS property path; colon names a synthetic namespace. Bare words are BANNED (`EveryKeyIsNamespaced` test requires `.` or `:`). Use `timezone:id` and `locale:tag`.
- Keys registry triple-consistency: every key in (1) `keys.h` constant, (2) `kAllKeys` array + `std::array<…, N>` size, (3) `declared` set in `keys_unittest.cc`. Count 61 → 63.
- Reuse the native controllers; do not reimplement. `TimeZoneController::SetTimeZoneOverride` returns an RAII handle that MUST be kept alive for the process lifetime (store in a `static base::NoDestructor<...>`); destroying it clears the override. `LocaleController::instance().SetLocaleOverride(locale, /*is_claiming_override=*/true)` holds its own singleton state (no handle).
- Coherence (user scope decision 2026-09-01): `locale:tag` present wins; `locale:tag` absent + SP1b `navigator.language` present → derive the Intl locale from `navigator.language`.
- `camoucfg::GetString(scope, key)` → `std::optional<std::string>`. `ScopeFor(nullptr)` is safe (returns GlobalScope; CAMOU_CONFIG is process-wide). SP1b key `kNavigatorLanguage` = `"navigator.language"`.
- No `BUILD.gn` change: `core/BUILD.gn` already deps `//components/camoucfg`; `timezone_controller.h` + `locale_controller.h` are in the same `core` target.
- Verify apparatus: launch content_shell with `CAMOU_CONFIG` and **no CDP override**, assert coherence in the main frame AND a `Worker`. Pre-hook that is UTC/en-US (RED); post-hook it matches the configured tz/locale (GREEN). Baselines use `--capture-baseline`.
- Blink files live only in the checkout; edit via `pullfile`/`pushto`; extract to `patches/` in the final task. Confirm NON-ZERO build steps after each change.

---

### Task 1: Config keys `timezone:id` + `locale:tag`

**Files:**
- Modify: `additions/camoucfg/keys.h` (add 2 constants, grow `kAllKeys` 61→63)
- Modify: `additions/camoucfg/keys_unittest.cc` (add 2 to `declared` set)

**Interfaces:**
- Produces: `camoucfg::keys::kTimezoneId` = `"timezone:id"`, `kLocaleTag` = `"locale:tag"`. Task 2 reads these.

- [ ] **Step 1: Add the two constants after `kMediaDevicesSpeakers` in `keys.h`**

```cpp
// Timezone + locale overrides (SP4-timezone/locale). Synthetic namespaces
// (bare `timezone`/`locale` are banned by EveryKeyIsNamespaced) -> colon.
// timezone:id is an IANA id (e.g. "America/New_York"); locale:tag is a BCP-47
// tag (e.g. "fr-FR"). Both absent => real OS values (rule 5). These drive the
// native blink::TimeZoneController / blink::LocaleController.
inline constexpr char kTimezoneId[] = "timezone:id";
inline constexpr char kLocaleTag[] = "locale:tag";
```

- [ ] **Step 2: Grow the array size to 63 and append to `kAllKeys`**

Change `inline constexpr std::array<std::string_view, 61> kAllKeys = {` to `63`. Append after `kMediaDevicesSpeakers,`:

```cpp
    kMediaDevicesSpeakers,
    kTimezoneId,
    kLocaleTag,
};
```

- [ ] **Step 3: Add the two to the `declared` set in `keys_unittest.cc`**

After the `kMediaDevices...` block:

```cpp
      kMediaDevicesEnabled, kMediaDevicesMicros, kMediaDevicesWebcams,
      kMediaDevicesSpeakers,
      kTimezoneId, kLocaleTag,
  };
```

- [ ] **Step 4: Push camoucfg + build/run the keys tests**

```bash
source /private/tmp/.../scratchpad/buildpc.sh   # the session harness
pushcfg keys.h
pushcfg keys_unittest.cc
unittests 'CamoucfgKeysTest.*'
```
Expected: `BUILD_DONE` with a NON-ZERO step count, all `CamoucfgKeysTest.*` PASS. `EveryDeclaredConstantIsInAllKeys` enforces the 63/array/declared triple.

- [ ] **Step 5: Commit**

```bash
git add additions/camoucfg/keys.h additions/camoucfg/keys_unittest.cc
git commit -m "feat(sp4-tz-locale): add timezone:id and locale:tag keys"
```

---

### Task 2: CoreInitializer hook — config-drive TimeZoneController + LocaleController

**Files:**
- Modify (checkout only): `third_party/blink/renderer/core/core_initializer.cc`
- Create (Mac, for verify): `scripts/verify_sp4_tzlocale.py`

**Interfaces:**
- Consumes: `camoucfg::keys::kTimezoneId`, `kLocaleTag`, `kNavigatorLanguage`.

- [ ] **Step 1: Write the failing verify script `scripts/verify_sp4_tzlocale.py`**

Drives content_shell with `CAMOU_CONFIG` and NO CDP. Reads main + a Blob `Worker`. Criteria:
- **T1 (timezone, main):** config `{"timezone:id":"America/New_York"}` → main `Intl.DateTimeFormat().resolvedOptions().timeZone == "America/New_York"` and `getTimezoneOffset()` is 240 or 300 (DST-dependent, non-zero).
- **T2 (timezone, worker):** same config → worker `timeZone == "America/New_York"`.
- **T3 (locale, main):** config `{"locale:tag":"fr-FR"}` → main `resolvedOptions().locale == "fr-FR"` and `Intl.NumberFormat().format(1234567.89)` contains the fr grouping (a non-`,`/non-`.`-grouped result, i.e. `!== "1,234,567.89"`).
- **T4 (locale, worker):** same config → worker `locale == "fr-FR"`.
- **T5 (fallback):** config `{"navigator.language":"fr-FR"}` and NO `locale:tag` → main `resolvedOptions().locale == "fr-FR"` (Intl derives from navigator.language).
- **T6 (no-op absent):** config `{}` → main `timeZone` and `locale` equal the stock baseline captured with `--capture-baseline` (rule 5).

```python
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell

MAIN = r"""(() => ({
  tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
  offset: new Date().getTimezoneOffset(),
  locale: Intl.DateTimeFormat().resolvedOptions().locale,
  num: new Intl.NumberFormat().format(1234567.89),
}))()"""

WORKER = r"""(async () => {
  try {
    const src = `postMessage({tz: Intl.DateTimeFormat().resolvedOptions().timeZone, locale: Intl.DateTimeFormat().resolvedOptions().locale});`;
    const w = new Worker(URL.createObjectURL(new Blob([src], {type:'application/javascript'})));
    return await new Promise((res) => { w.onmessage = (e)=>res(e.data); setTimeout(()=>res({error:'timeout'}),3000); });
  } catch(e) { return {error:String(e)}; }
})()"""

BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sp4_tzlocale_baseline.json")

def run(config):
    vals, err = lib_shell.session(config, [MAIN, WORKER], navigate_to="about:blank")
    if err: raise err
    return {"main": vals[0], "worker": vals[1]}

def cfg(d): return json.dumps(d)

def main():
    if "--capture-baseline" in sys.argv:
        b = run(None)
        with open(BASELINE,"w") as f: json.dump(b,f)
        print("baseline:", json.dumps(b)); return
    r = {}
    a = run(cfg({"timezone:id":"America/New_York"}))
    r["T1"] = a["main"]["tz"]=="America/New_York" and a["main"]["offset"] in (240,300)
    r["T2"] = a["worker"].get("tz")=="America/New_York"
    b = run(cfg({"locale:tag":"fr-FR"}))
    r["T3"] = b["main"]["locale"]=="fr-FR" and b["main"]["num"]!="1,234,567.89"
    r["T4"] = b["worker"].get("locale")=="fr-FR"
    c = run(cfg({"navigator.language":"fr-FR"}))
    r["T5"] = c["main"]["locale"]=="fr-FR"
    d = run(cfg({}))
    with open(BASELINE) as f: base=json.load(f)
    r["T6"] = d["main"]["tz"]==base["main"]["tz"] and d["main"]["locale"]==base["main"]["locale"]
    EXPECTED=6
    for k in ("T1","T2","T3","T4","T5","T6"): print(f"{k}: {'PASS' if r[k] else 'FAIL'}")
    n=sum(r.values()); print(f"{n}/{EXPECTED} " + ("ALL_PASS" if n==EXPECTED else "FAIL"))
    sys.exit(0 if n==EXPECTED else 1)

if __name__=="__main__": main()
```

- [ ] **Step 2: Capture baseline + run RED-first**

```bash
pushfile scripts/verify_sp4_tzlocale.py "$VERIFY/verify_sp4_tzlocale.py"
verify verify_sp4_tzlocale.py --capture-baseline
verify verify_sp4_tzlocale.py
```
Expected RED: T1–T5 FAIL (config unread → stock UTC/en-US), T6 PASS. Record it.

- [ ] **Step 3: Add the hook in `core_initializer.cc`**

Add includes (near the existing includes):
```cpp
#include "base/no_destructor.h"
#include "components/camoucfg/blink_scope.h"
#include "components/camoucfg/keys.h"
#include "components/camoucfg/mask_config.h"
#include "third_party/blink/renderer/core/inspector/locale_controller.h"
```
(`timezone_controller.h` is already included — the file calls `TimeZoneController::Init()`.)

In `CoreInitializer::Initialize()`, immediately AFTER the `TimeZoneController::Init();` line:

```cpp
  // SP4-timezone/locale: drive the native timezone/locale overrides from
  // CAMOU_CONFIG so a standalone (non-CDP) launch is coherent, incl. workers.
  {
    const camoucfg::ConfigScope& camou_scope = camoucfg::ScopeFor(nullptr);
    if (std::optional<std::string> tz =
            camoucfg::GetString(camou_scope, camoucfg::keys::kTimezoneId);
        tz && !tz->empty()) {
      auto result =
          TimeZoneController::SetTimeZoneOverride(String::FromUTF8(*tz));
      // Keep the RAII handle alive for the whole process (never clear).
      static base::NoDestructor<
          std::unique_ptr<TimeZoneController::TimeZoneOverride>>
          kTimeZoneHandle(std::move(result.handle));
    }
    std::string locale;
    if (std::optional<std::string> l =
            camoucfg::GetString(camou_scope, camoucfg::keys::kLocaleTag);
        l && !l->empty()) {
      locale = *l;
    } else if (std::optional<std::string> nl = camoucfg::GetString(
                   camou_scope, camoucfg::keys::kNavigatorLanguage);
               nl && !nl->empty()) {
      locale = *nl;
    }
    if (!locale.empty()) {
      LocaleController::instance().SetLocaleOverride(
          String::FromUTF8(locale), /*is_claiming_override=*/true);
    }
  }
```

- [ ] **Step 4: Build content_shell + run verify GREEN**

```bash
contentshell   # confirm NON-ZERO steps
verify verify_sp4_tzlocale.py
```
Expected: `6/6 ALL_PASS`. If content_shell CRASHES at startup (early-timing on the LocaleController isolate/scheduler path), report it — the fallback is to relocate the block to first-frame init (e.g. `LocalDOMWindow` construction) reading the same config; note the relocation in the report.

- [ ] **Step 5: Commit the Mac-side verify script**

```bash
git add scripts/verify_sp4_tzlocale.py
git commit -m "test(sp4-tz-locale): verify_sp4_tzlocale T1-T6 (config-driven tz/locale)"
```

---

### Task 3: Extract patch, wire apply.sh, regression

**Files:**
- Create: `patches/sp4-tz-locale.patch`
- Modify: `scripts/apply.sh` (append LAST)

**Interfaces:**
- Consumes: the checkout edit from Task 2 (`core_initializer.cc`).

- [ ] **Step 1: Extract the one-file diff to `patches/sp4-tz-locale.patch`**

```bash
runwsl "cd $CHECKOUT && git diff -- third_party/blink/renderer/core/core_initializer.cc" > patches/sp4-tz-locale.patch
```
Confirm the patch contains ONLY `core_initializer.cc` and is non-empty.

- [ ] **Step 2: Round-trip verify (patch == working tree)**

```bash
runwsl "cd $CHECKOUT && git checkout -- third_party/blink/renderer/core/core_initializer.cc"
pushto patches/sp4-tz-locale.patch /tmp/sp4-tz-locale.patch
runwsl "cd $CHECKOUT && git apply --3way /tmp/sp4-tz-locale.patch && echo APPLY_OK"
contentshell   # NON-ZERO steps
verify verify_sp4_tzlocale.py   # 6/6 ALL_PASS
```

- [ ] **Step 3: Wire apply.sh LAST**

In `scripts/apply.sh`, append after `"$ROOT/patches/sp4-media.patch"`:
```bash
  "$ROOT/patches/sp4-media.patch"
  "$ROOT/patches/sp4-tz-locale.patch"
)
```

- [ ] **Step 4: Full regression (record every count)**

```bash
unittests 'CamoucfgKeysTest.*:AssembleRawConfigTest.*:ParseConfigTest.*:ParseConfigDeathTest.*:GettersTest.*:MaskConfigTest.*:DeriveTest.*:DeriveDeltaTest.*:DeriveUnitTest.*:PerturbRgbaTest.*:MouseTrajectoriesTest.*'
verify verify_sp4_tzlocale.py   # 6/6
verify verify_sp4_media.py      # 4/4
verify verify_sp4_audio.py      # 12/12
verify verify_sp4_fonts.py      # 7/7
verify verify_sp4a.py           # 6/6
verify verify_sp1b.py           # 8/8
```
Expected: camoucfg all PASS (63 keys), all prior verifies unchanged. If any verify errors with a missing baseline, run it once with `--capture-baseline` then re-run (note it).

- [ ] **Step 5: Commit**

```bash
git add patches/sp4-tz-locale.patch scripts/apply.sh
git commit -m "feat(sp4-tz-locale): config-driven timezone/locale override — patch + apply wiring"
```

---

## Self-Review notes

- **Spec coverage:** timezone (measurement §1) → key `timezone:id` + `SetTimeZoneOverride`; locale (§1) → key `locale:tag` + `SetLocaleOverride` with navigator.language fallback. Worker coverage inherited from the native controllers (§3 P2). navigator.language stays SP1b's.
- **Type consistency:** `SetTimeZoneOverride` → `TimeZoneOverrideResult{status, handle}`; handle held in a `static base::NoDestructor`. `SetLocaleOverride(String, bool)` → error `String` (ignored; init-time best-effort).
- **Timing risk** is the one open implementation question — Task 2 Step 4 makes RED-first the gate and names the fallback location.
- **Interactions** (measurement §5): single-owner override means the launcher must route tz/locale through CAMOU_CONFIG, not also via Playwright `timezone_id`/`locale`. Not a code task — a launcher-integration note.

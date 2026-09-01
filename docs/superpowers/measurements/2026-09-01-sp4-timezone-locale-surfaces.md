# SP4-timezone/locale surfaces measurement (2026-09-01)

Checkout HEAD `a727b57805`, `out/Default` content_shell.

Unlike fonts/audio/media, Chromium **already has** the C++ machinery to spoof
timezone and locale coherently — `TimeZoneController` and `LocaleController`,
the same mechanisms CDP `Emulation.setTimezoneOverride` / `setLocaleOverride`
(and thus Playwright's `timezoneId` / `locale` context options) drive. Both are
page-invisible C++. The only gap is that camoucrome's config layer does not
drive them, so a standalone `CAMOU_CONFIG` launch (the build-tester, or any
non-CDP client) leaks the real OS timezone/locale. This slice closes that gap by
reusing the native controllers — it does NOT reimplement Camoufox's
Firefox-engine rewrite.

---

## 1. Surfaces

**Timezone** (all driven by ICU default timezone + V8):
- `Intl.DateTimeFormat().resolvedOptions().timeZone`
- `Date.prototype.getTimezoneOffset()`
- `Date` string rendering (`toString`, incl. the localized TZ display name)

**Locale** (driven by ICU default locale + V8 `Intl`):
- `Intl.DateTimeFormat().resolvedOptions().locale`
- `Intl.NumberFormat` / `DateTimeFormat` / `Collator` formatting (separators,
  currency, sort order)

**Out of this slice:** `navigator.language` / `navigator.languages` are already
spoofed by SP1b (keys `navigator.language` / `navigator.languages`,
`navigator_base.cc`). They are the Accept-Language surface, distinct from the
ICU/Intl locale — but they must stay COHERENT with it (see §4).

---

## 2. Native machinery (reused, not reimplemented)

- **`TimeZoneController`** (`core/timezone/timezone_controller.cc`).
  `static TimeZoneOverrideResult SetTimeZoneOverride(const String& tz)` — RAII:
  the override lives as long as the returned `handle` (unique_ptr) is alive;
  destroying it calls `ClearTimeZoneOverride`. Global, single-owner (a second
  concurrent override returns `kAlreadyInEffect`). Internally
  `icu::TimeZone::adoptDefault` + notify V8 main isolate + **`CallOnAllWorkerThreads`**
  — workers are covered. `Init()` is called from `CoreInitializer::Initialize()`
  (`core_initializer.cc:175`).
- **`LocaleController`** (`core/inspector/locale_controller.cc`).
  `LocaleController::instance().SetLocaleOverride(const String& locale, bool is_claiming_override)`
  — process-wide singleton (no handle to hold). Sets `base::i18n::SetDefaultIcuLocale`
  + notifies every main-thread isolate and **every worker thread**. Returns `""`
  on success, an error string otherwise (`"Another locale override is already in
  effect"` / `"Invalid locale name"`). Takes ONE BCP-47 tag.

Both are what `InspectorEmulationAgent` calls for CDP; reusing them means the
config path inherits their proven coherence and worker coverage.

---

## 3. Empirical (content_shell)

| probe | timeZone | offset | Intl locale | NumberFormat(1234567.89) |
|---|---|---|---|---|
| **P0 stock** (no config, no CDP) | UTC | 0 | en-US | `1,234,567.89` |
| **P1 `CAMOU_CONFIG {timezone, locale:*}`** | UTC | 0 | en-US | `1,234,567.89` |
| **P2 CDP `setTimezoneOverride`+`setLocaleOverride`** | America/New_York | 240 | fr-FR | `1 234 567,89` |

- **P1 = the gap.** Setting `timezone` / `locale:*` in `CAMOU_CONFIG` changes
  nothing — nothing reads those keys. Main frame AND a `Worker` both still report
  UTC / en-US. A standalone binary leaks the real OS values.
- **P2 = the reusable target.** The native override is fully coherent: DST-aware
  offset (240 = EDT), localized TZ display name (`heure normale de l'Est
  nord-américain`), fr number grouping (`1 234 567,89`) and currency (`5,00 $US`),
  and the **Worker** inherits all of it (`America/New_York` + `fr-FR`). This is
  the quality the config path must reach without needing a CDP client.

---

## 4. Port design (this slice)

Drive the native controllers from `CAMOU_CONFIG` at `CoreInitializer::Initialize()`,
immediately after `TimeZoneController::Init()` (the earliest per-renderer point;
runs once per renderer process, before page scripts and workers):

```cpp
const camoucfg::ConfigScope& scope = camoucfg::ScopeFor(nullptr);
// Timezone
if (auto tz = camoucfg::GetString(scope, camoucfg::keys::kTimezoneId);
    tz && !tz->empty()) {
  auto r = TimeZoneController::SetTimeZoneOverride(String::FromUTF8(*tz));
  // Keep the RAII handle alive for the whole process (never clear).
  static base::NoDestructor<std::unique_ptr<TimeZoneController::TimeZoneOverride>>
      kHandle(std::move(r.handle));
}
// Locale: explicit locale:tag wins; else fall back to SP1b navigator.language
std::string locale;
if (auto l = camoucfg::GetString(scope, camoucfg::keys::kLocaleTag);
    l && !l->empty()) {
  locale = *l;
} else if (auto nl = camoucfg::GetString(scope, camoucfg::keys::kNavigatorLanguage);
           nl && !nl->empty()) {
  locale = *nl;  // single primary tag (navigator.languages is the list)
}
if (!locale.empty()) {
  LocaleController::instance().SetLocaleOverride(String::FromUTF8(locale),
                                                 /*is_claiming_override=*/true);
}
```

- **Keys (colon namespace — bare `timezone`/`locale` are banned by the
  `EveryKeyIsNamespaced` test):** `timezone:id` (IANA id, e.g.
  `"America/New_York"`), `locale:tag` (BCP-47, e.g. `"fr-FR"`). The `locale:`
  namespace already exists in Camoufox (`locale:language/region/script`);
  `locale:tag` is the assembled single tag Chromium's `LocaleController` wants.
  Keys 61 → 63.
- **Coherence-by-default (user scope decision):** `locale:tag` absent + SP1b
  `navigator.language` set → the Intl override derives from `navigator.language`,
  so a config that only spoofs `navigator.language` does not split-brain (Intl
  en-US vs navigator fr-FR). Explicit `locale:tag` wins.
- **Rule 5 no-op:** both keys absent → no override, real OS values (P0).
- **No BUILD.gn change:** `core/BUILD.gn` already deps `//components/camoucfg`;
  `timezone_controller.h` and `locale_controller.h` are in the same `core`
  target.

**Timing (RED-first must validate):** `CoreInitializer::Initialize()` is the
earliest hook. `SetTimeZoneOverride`/`SetLocaleOverride` both set the ICU default
(always safe) and best-effort-notify existing isolates; new isolates created
later inherit the ICU default. If the very-early call crashes on a not-yet-ready
main-thread scheduler/isolate, relocate to first-frame init and note it. The
Task-2 verify launches with `CAMOU_CONFIG` and **no CDP**, asserting coherence in
main + worker — this is the RED (pre-hook: UTC/en-US) → GREEN gate.

---

## 5. Interactions & residual (documented)

- **CDP-vs-config override conflict (IMPORTANT for the launcher layer).** The
  timezone override is single-owner: if the config claims it at init, a later
  Playwright/CDP `timezoneId` (`Emulation.setTimezoneOverride`) returns
  `kAlreadyInEffect` and is silently rejected. `LocaleController` likewise returns
  `"Another locale override is already in effect"` for a second claim. This is the
  correct precedence (CAMOU_CONFIG is camoucrome's source of truth), but the
  Python/launcher layer must route timezone/locale through `CAMOU_CONFIG` and NOT
  also set Playwright's `timezone_id`/`locale` context options, or those calls
  fail. Document in the launcher integration.
- **Operator coherence:** a spoofed `locale:tag=fr-FR` with no `timezone:id`
  leaves a UTC clock in a French browser — a mild tell. With the fingerprint
  preset layer both come together; document that timezone and locale should be
  set as a coherent pair (and ideally consistent with the proxy's IP geolocation,
  which is the proxy layer's concern, not Blink's).
- **`navigator.languages` (the list) vs the single Intl tag:** Intl uses one
  primary tag; the fallback reads `navigator.language` (singular). If a config
  sets `navigator.languages` but not `navigator.language`, the Intl fallback is
  empty — acceptable (explicit `locale:tag` or `navigator.language` is the
  intended input). Noted.

---

## 6. Slice scope summary

| surface | this slice |
|---|---|
| Intl timezone + Date offset/render | **spoof** — config-drive `TimeZoneController`, key `timezone:id` |
| Intl locale + NumberFormat/DateTimeFormat/Collator | **spoof** — config-drive `LocaleController`, key `locale:tag` (fallback navigator.language) |
| worker coverage | inherited from the native controllers (measured, P2) |
| `navigator.language(s)` | already SP1b — kept coherent via the locale fallback |
| CDP/Playwright timezone_id/locale | route through CAMOU_CONFIG instead (single-owner conflict) — launcher note |

# SP4-battery surfaces measurement (2026-09-02)

Checkout HEAD `a727b57805`, `out/Default` content_shell.

`navigator.getBattery()` → `BatteryManager` exposes `charging`, `level`,
`chargingTime`, `dischargingTime` — a low-entropy but real fingerprint (a
laptop's fractional `level` and finite `dischargingTime` are a device tell; the
API is deprecated/removed in some browsers but present in Chromium behind a
secure context). This slice config-drives the four getters (the Camoufox
pattern) so the preset layer can supply coherent battery values.

---

## 1. Stock behavior (content_shell, secure origin)

`navigator.getBattery` is `[SecureContext]`-gated — **undefined on
`about:blank`**; drive over the `127.0.0.1` echo_server origin
(`isSecureContext===true`). Stock there:

```json
{ "charging": true, "level": 1, "chargingTime": 0, "dischargingTime": Infinity }
```

This is the "plugged in, fully charged" default of a machine with no battery
(the build box / a desktop). It is already a coherent DESKTOP profile — a
desktop scraper wants exactly this. The entropy to control is the LAPTOP case: a
real laptop reports `level` < 1, `charging` varying, and a finite
`dischargingTime`, which a fingerprint preset needs to set coherently.

## 2. Blink choke point

`third_party/blink/renderer/modules/battery/battery_manager.cc` — four trivial
getters over the cached `battery_status_`:

```cpp
bool   BatteryManager::charging()        { return battery_status_.Charging(); }
double BatteryManager::chargingTime()    { return battery_status_.charging_time().InSecondsF(); }
double BatteryManager::dischargingTime() { return battery_status_.discharging_time().InSecondsF(); }
double BatteryManager::level()           { return battery_status_.Level(); }
```

## 3. Port design

SP0 hook pattern per getter — real value first, config override LAST, no-op when
the key is absent:

```cpp
double BatteryManager::level() {
  if (std::optional<double> v = camoucfg::GetDouble(
          camoucfg::ScopeFor(GetExecutionContext()),
          camoucfg::keys::kBatteryLevel)) {
    return *v;
  }
  return battery_status_.Level();
}
```
and likewise `charging()` via `GetBool(kBatteryCharging)`, `chargingTime()` via
`GetDouble(kBatteryChargingTime)`, `dischargingTime()` via
`GetDouble(kBatteryDischargingTime)`.

- **Keys (colon namespace `battery:`, matching Camoufox):** `battery:charging`
  (bool), `battery:level` (double), `battery:chargingTime` (double),
  `battery:dischargingTime` (double). Keys 70 → 74.
- **Rule 5:** each key absent → the real `battery_status_` value (stock desktop
  default). Independent per getter (setting only `battery:level` leaves the other
  three real).
- **`dischargingTime` = Infinity** is the desktop default; JSON has no Infinity,
  so the config value is a FINITE laptop value — to keep Infinity (plugged in),
  omit the key (rule 5 → real Infinity).
- **BUILD dep:** `modules/battery/BUILD.gn` likely needs `//components/camoucfg`
  added (first camoucrome hook in that module — mirror sp4-media/sp4-voices).
- **`onchargingchange`/`onlevelchange` events** fire from real `DidUpdateData`
  (backend-driven). On the no-battery build box no updates arrive, so the getters
  (which config overrides) are the whole page-visible surface. Event *timing* on a
  real device is a deeper surface, deferred (battery-ii).

## 4. Coherence & residual (documented)

- **Coherence:** `level`/`charging`/`chargingTime`/`dischargingTime` must be
  mutually consistent (e.g. `charging:true` ⇒ `dischargingTime` typically
  Infinity and `chargingTime` finite; `charging:false` ⇒ `chargingTime` Infinity
  and `dischargingTime` finite). The operator/preset supplies a coherent tuple;
  not enforced here.
- **Level precision tell:** a suspiciously round `level` (e.g. exactly 1.0 or 0.5)
  on a "laptop" profile is a mild tell; presets should use realistic fractional
  values. Documented.
- **Event timing (battery-ii):** `onchargingchange`/`onlevelchange` are not
  synthesized; a probe watching for updates over time sees none (static). Deeper
  surface, deferred.

## 5. Slice scope summary

| surface | this slice |
|---|---|
| `charging` / `level` / `chargingTime` / `dischargingTime` getters | **config override** — SP0 per-getter, keys `battery:charging/level/chargingTime/dischargingTime` |
| `onchargingchange` / `onlevelchange` timing | defer (battery-ii) |
| tuple coherence | operator/preset responsibility |

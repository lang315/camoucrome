# SP4-geo surfaces measurement (2026-09-02)

Checkout HEAD `a727b57805`, `out/Default` content_shell.

`navigator.geolocation.getCurrentPosition()` / `watchPosition()` expose the
device's latitude/longitude/accuracy — a high-value location fingerprint (and a
coherence signal against the proxy's IP geolocation + the spoofed timezone).
Like timezone/locale/webrtc, Chromium already has a native, page-invisible
override; the camoucrome gap is that the config layer does not drive it. This
slice config-drives a position **synthesis** at the Blink level so a standalone
(non-CDP) launch reports the configured position — even with no geolocation
backend — while still respecting the permission model.

---

## 1. Stock behavior (content_shell, secure origin)

`getCurrentPosition` over the `127.0.0.1` echo_server (geolocation is
secure-context only, `isSecureContext===true`):

- **P0 stock (no config, no CDP):** error **code 3 (TIMEOUT)**, "Timeout
  expired". content_shell auto-grants the permission (no code-1 PERMISSION_DENIED)
  but has no geolocation backend, so no position ever arrives → the request
  times out.
- **P1 CDP `Emulation.setGeolocationOverride {lat,lon,accuracy}`:** full success —
  `48.8566 / 2.3522 / 25`. Chromium's native override (browser-process
  `GeolocationContext::SetOverride`, what CDP + Playwright's `geolocation` context
  option drive) **synthesizes** a position and satisfies the request with no
  backend. This is the reusable target quality.

## 2. Blink choke point

`third_party/blink/renderer/core/geolocation/geolocation.cc` (geolocation lives
in `core/`, not `modules/`):

- `getCurrentPosition`/`watchPosition` → `UpdateGeolocationState()`:
  `EnsureGeolocationConnection()` (binds mojo + drives the permission request),
  and only once permission is granted and `!updating_`, calls
  `QueryNextPosition(); updating_ = true;`.
- `QueryNextPosition()` (line ~677): `geolocation_->QueryNextPosition(BindOnce(&OnPositionUpdated, …))`
  — the mojo hanging-get to the browser backend.
- `OnPositionUpdated(GeopositionResultPtr)` (~682): on a position,
  `ValidateGeoposition` then `last_position_ = CreateGeoposition(...)` +
  `PositionChanged()` → `MakeSuccessCallbacks()` → `RunSuccessCallback` on
  one-shots + watchers. `updating_` is reset to false.
- `ValidateGeoposition`: requires `latitude ∈ [-90,90]`, `longitude ∈ [-180,180]`,
  `accuracy ≥ 0`, `!timestamp.is_null()`.

`QueryNextPosition` is the single point where every request (getCurrentPosition
AND watchPosition, after the permission grant) reaches the backend.

## 3. Port design

Intercept `QueryNextPosition()`: when `geolocation:latitude` AND
`geolocation:longitude` are both configured, synthesize a
`device::mojom::blink::GeopositionResult` from config and deliver it via the
existing `OnPositionUpdated` path — **posting** it (not calling inline) — instead
of the mojo hanging-get:

```cpp
void Geolocation::QueryNextPosition() {
  const camoucfg::ConfigScope& scope = camoucfg::ScopeFor(GetExecutionContext());
  std::optional<double> lat =
      camoucfg::GetDouble(scope, camoucfg::keys::kGeolocationLatitude);
  std::optional<double> lon =
      camoucfg::GetDouble(scope, camoucfg::keys::kGeolocationLongitude);
  if (lat && lon) {
    auto position = device::mojom::blink::Geoposition::New();
    position->latitude = *lat;
    position->longitude = *lon;
    position->accuracy =
        camoucfg::GetDouble(scope, camoucfg::keys::kGeolocationAccuracy)
            .value_or(100.0);
    position->timestamp = base::Time::Now();
    auto result = device::mojom::blink::GeopositionResult::NewPosition(
        std::move(position));
    GetExecutionContext()
        ->GetTaskRunner(TaskType::kMiscPlatformAPI)
        ->PostTask(FROM_HERE,
                   blink::BindOnce(&Geolocation::OnPositionUpdated,
                                   WrapWeakPersistent(this), std::move(result)));
    return;
  }
  geolocation_->QueryNextPosition(
      blink::BindOnce(&Geolocation::OnPositionUpdated, WrapPersistent(this)));
}
```

Why this shape:
- **Backend-independent.** Synthesizes the position, so `getCurrentPosition`
  succeeds even on content_shell (fixes the P0 timeout) and never leaks a real
  device position on a real deploy.
- **Posted, not inline.** `QueryNextPosition` is called from `UpdateGeolocationState`
  as `QueryNextPosition(); updating_ = true;`. Calling `OnPositionUpdated`
  synchronously would set `updating_ = false` and then the caller would set it
  back to `true`, wedging the flag; posting delivers on a clean task (mirroring
  the async mojo callback) and avoids re-entrancy.
- **Watcher re-arm loop — the trap, and the fix (whole-branch correction).** An
  earlier draft of this doc claimed the synth "delivers once, no loop" — that was
  WRONG. `OnPositionUpdated`'s tail runs `if (HasListeners()) UpdateGeolocationState();`,
  which for a standing `watchPosition` re-arms `QueryNextPosition()`. The mojo
  path there is a hanging-get that only resolves on an actual position change, but
  the synth resolves INSTANTLY every re-arm → an infinite instant loop (main-thread
  CPU burn + a flood of identical callbacks + a timing tell). `getCurrentPosition`
  is unaffected (its one-shot notifier is removed → `HasListeners()` false →
  `StopUpdating`). Fix: a `camou_geo_delivered_` flag — reset at each request entry
  (`getCurrentPositionForBindings` / `watchPositionForBindings`), set after the
  first synth post, and checked at the top of the config branch so a re-arm
  returns quietly. A stationary config position thus fires **once** per request and
  then stays quiet — exactly like a real stationary device (whose hanging-get never
  resolves again). Verified by G5 (a standing `watchPosition` fires exactly once).
- **Starvation follow-on (second correction).** The delivered-flag's quiet-return
  leaves `updating_` stuck `true` (no `OnPositionUpdated` fires to reset it, and
  `UpdateGeolocationState` sets it `true` after every `QueryNextPosition`). That
  starves any request issued while a watch still stands: a `getCurrentPosition`
  (or a second `watchPosition`) then hits `if (!updating_)` == false → its query
  is skipped → it hangs forever (getCurrentPosition's default timeout is
  Infinity). A ~10-line probe (`watchPosition` then `getCurrentPosition`) would
  hang where stock Chrome resolves — a tell. Fix: a `HasCamouGeoConfig()` helper
  gates a `updating_ = false` reset (alongside the delivered-flag reset) at both
  request entry points — safe because the config synth path never issues a real
  mojo query, so no outstanding query can be double-invoked, and CAMOU_CONFIG is
  process-static so the gate never flips mid-session. A fresh request then
  re-issues `QueryNextPosition` and gets its synth delivery; a bounded duplicate
  callback to the standing watch is harmless. Verified by G6 (getCurrentPosition
  during a standing watchPosition resolves with the config coords, no hang).
- **Permission-respecting (deliberate divergence from Camoufox).** `QueryNextPosition`
  is only reached after `EnsureGeolocationConnection` has driven the permission
  request to *granted*. So a page whose geolocation permission was DENIED still
  gets the error (coherent); we do NOT auto-grant. Camoufox bypasses the Firefox
  prompt (`RegisterRequestWithPrompt`); in Chromium that is a browser-process
  concern and, more importantly, a denied-then-position mismatch is itself a tell.
  Auto-grant, if wanted, belongs in the launcher/policy layer, not here.
- **`ValidateGeoposition` satisfied**: config lat/long are range-checked by the
  operator's config; `accuracy` defaults to `100.0` (≥ 0); `timestamp = Now()`
  (non-null).

Keys (colon namespace `geolocation:`, matching Camoufox): `geolocation:latitude`,
`geolocation:longitude` (both required to activate), `geolocation:accuracy`
(double, default 100.0). Keys 67 → 70. No BUILD.gn change — `core/geolocation`
compiles under the monolithic `core` target which already deps
`//components/camoucfg`.

## 4. Coherence & residual (documented)

- **Position ↔ timezone ↔ IP-geo coherence:** the configured lat/long should match
  the spoofed `timezone:id` and the proxy's IP geolocation (a Paris position with
  a New York clock or a Tokyo exit IP is a tell). Operator/preset responsibility.
- **Accuracy default (100 m):** a fixed default is a mild round-number tell if the
  operator sets lat/long but not accuracy. Camoufox derives accuracy from the
  coordinate decimal precision; that derivation is a follow-on (geo-ii). Operators
  should set `geolocation:accuracy` to a realistic value.
- **No auto-grant:** if geolocation permission is denied, `getCurrentPosition`
  errors as normal — the spoof only applies once granted (§3). Auto-grant is a
  launcher/policy concern.
- **`altitude`/`heading`/`speed`/`altitudeAccuracy`** are left at the mojom
  bad-sentinels → JS `null`, matching a typical network-geolocation fix (no
  altitude/heading). Coherent.
- **No positional jitter; timestamp advances (residual, geo-ii).** The synthesized
  coords are byte-identical on every delivery while `timestamp` is a fresh `Now()`
  each query. Real GPS/network fixes drift slightly between `watchPosition`
  callbacks. This is NOT a Camoucrome-specific tell: it is byte-identical to CDP
  `Emulation.setGeolocationOverride` (fixed coords, fresh timestamp), the override
  every Playwright/Puppeteer user emits. Jitter synthesis is deferred to geo-ii
  alongside the accuracy-precision derivation.
- **Out-of-range config → silent timeout (residual, operator-facing, geo-ii /
  SP5a).** A config `latitude=91` (or `accuracy<0`) fails `ValidateGeoposition`
  inside the posted `OnPositionUpdated`, which returns before both the callback and
  the `HasListeners` re-arm → no callback, no error → the request times out; state
  recovers on the next request (the entry resets cover it). Not page-weaponizable
  (a probe cannot inject config), but it silently disables geolocation for a
  mistyped config. Recommend range-checking these keys in the SP5a coherence
  validator (they postdate it).
- **Visibility race (residual, not weaponizable, no fix).** If the page hides in the
  sub-ms window between the synth `PostTask` and the task running, the posted
  `OnPositionUpdated` drops the update (the hidden-page guard) while
  `camou_geo_delivered_` stays true, so visibility-regain does not re-synthesize
  and a request can time out where stock would recover. Page JS cannot control its
  own visibility, so no probe can weaponize it; the symptom is a rare timeout, not
  a leak. No code fix — patching the hidden-drop path would expand the diff for a
  non-adversarial sub-ms window.
- **`is_precise`** is left at its mojom default. It is an internal
  `ApproximateGeolocation` accuracy-mode field, not surfaced on the JS
  `GeolocationCoordinates` interface — not a page-side tell.

## 5. Slice scope summary

| surface | this slice |
|---|---|
| `getCurrentPosition` / `watchPosition` coords | **synthesize** — config `geolocation:latitude/longitude/accuracy` at `QueryNextPosition`, delivered via `OnPositionUpdated` |
| permission | respected (spoof only post-grant; no auto-grant) |
| accuracy decimal-precision derivation | defer (geo-ii) — fixed 100 m default |
| position ↔ timezone ↔ IP-geo coherence | operator/preset responsibility |

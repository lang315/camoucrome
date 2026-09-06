# geo-ii watchPosition re-fire cadence measurement (2026-09-06)

Checkout HEAD `a727b57805`, `out/Default` content_shell. Follow-on to
[sp4-geo](2026-09-02-sp4-geo-surfaces.md). The roadmap named this slice
"positional jitter"; the measurement below reframes it — the real tell is not
that successive fixes are byte-identical, it is that **there are no successive
fixes at all**.

## 1. The tell (RED), and why it is NOT jitter

sp4-geo synthesizes a position at `Geolocation::QueryNextPosition` and, via
`camou_geo_delivered_`, delivers it **once per arm** then suppresses the re-arm
(to avoid a busy-loop). So a standing `watchPosition` gets **one** callback and
then silence forever.

Real Chrome re-fires a stationary `watchPosition` periodically:
- `GeolocationImpl::OnLocationUpdate` (`services/device/geolocation/geolocation_impl.cc`)
  stores `current_result_` and, if a `QueryNextPosition` is pending, reports it —
  **with no dedup on unchanged coordinates.** Every provider update reaches the page.
- The network location provider re-emits a position on each WiFi scan
  (`network_location_provider.cc`, `is_new_data_available_`), i.e. at the WiFi
  poll interval.
- `wifi_data_provider_chromeos.cc` gives the stationary backoff curve:
  `kDefaultPollingInterval = 10s` (results differ), `kNoChangePollingInterval =
  2 min` (one no-change), `kTwoNoChangePollingInterval = 10 min` (steady state).
  A stationary device therefore re-fires at ~10s, then ~2min, then ~10min.

So the discriminators, in order:
1. **Does `watchPosition` fire more than once?** Stock fork: NO (the tell + a
   functional gap — a page waiting for a 2nd callback waits forever). Real Chrome:
   YES.
2. **Do successive fixes carry fresh timestamps?** Real Chrome: yes (each poll).
3. **Do coordinates drift?** For a *stationary* device: **NO** — the geolocation
   service returns the same geocoded position for the same WiFi environment; only
   the timestamp advances. **This is why "jitter" is the wrong lever:** a fixed
   configured position represents a stationary device, and drifting its
   coordinates would wrongly imply movement — less coherent, not more. Coordinate
   jitter is deferred (it models motion, and modeling a stationary provider's
   meters-scale noise without a real capture is the rejected accuracy-derive trap
   in a new coat).

## 2. Blink flow (the hook)

`third_party/blink/renderer/core/geolocation/geolocation.cc`:
- `OnPositionUpdated(result)` → `PositionChanged()` (→ `MakeSuccessCallbacks`,
  notifies watchers) → `if (HasListeners()) UpdateGeolocationState()`.
- `UpdateGeolocationState()` → (permission granted && `!updating_`) →
  `QueryNextPosition(); updating_ = true;`. **This re-arm is the repeat
  mechanism** — real Chrome answers each re-armed query when the next poll lands;
  the fork suppresses it.
- A `getCurrentPosition` notifier is one-shot: after it fires, `HasListeners()`
  is false → `StopUpdating()` → no re-arm. So getCurrentPosition naturally stays
  single-shot; only `watchPosition` re-arms.

## 3. Port design (this slice, folded into sp4-geo.patch)

Replace the deliver-once `camou_geo_delivered_` bool with a
`camou_geo_delivery_count_` int and re-deliver on each re-arm at the stationary
backoff cadence:

```cpp
// QueryNextPosition, config path:
if (HasCamouGeoConfig()) {
  base::TimeDelta delay = CamouGeoRefireDelay(camou_geo_delivery_count_);
  // count 0 -> ~immediate (CDP-quality first fix); 1 -> 10s; 2 -> 2min; >=3 -> 10min.
  ++camou_geo_delivery_count_;
  GetTaskRunner()->PostDelayedTask(
      FROM_HERE,
      BindOnce(&Geolocation::OnPositionUpdated, WrapWeakPersistent(this),
               SynthesizePosition(/*timestamp=*/Now())),  // fresh ts each fire
      delay);
  return;
}
```

- **Fresh timestamp every delivery** (`Now()` at synthesis time in the task).
- **Identical coordinates** (stationary-coherent; no jitter).
- **Delay breaks the busy-loop** the old bool solved — the re-arm no longer
  tight-loops; it waits the poll interval.
- **Cadence uses Chrome's real constants** (10s / 2min / 10min), so a page timing
  callback intervals sees a real stationary curve, not an invented one.
- **Counter resets** at `getCurrentPositionForBindings` / `watchPositionForBindings`
  entry (same spots the old bool reset), so each fresh request starts the curve over.
- **getCurrentPosition** stays single-shot (count 0, one delivery, no re-arm).
- **clearWatch mid-interval:** a queued delayed task may fire once after the watch
  is cleared; `WrapWeakPersistent` + the `HasListeners()`-gated re-arm make it a
  harmless no-op delivery that then stops (documented, not guarded further).

## 4. Verification plan

`scripts/verify_geo_ii_cadence.py`, secure origin (127.0.0.1 echo_server), a
`watchPosition` over a ~14s window (long enough for the first re-fire at 10s):

- **GC-REFIRE:** `watchPosition` fires **>= 2** times in the window. RED (stock
  fork): exactly 1. GREEN: >= 2.
- **GC-TIMESTAMP:** the 2nd callback's `timestamp` is strictly greater than the
  1st (each delivery is a fresh fix, not a replay).
- **GC-STATIONARY:** the 2nd callback's `coords.latitude/longitude` equal the
  1st's exactly (stationary; no jitter tell).
- **GC-INTERVAL:** the gap between callback 1 and 2 is ~10s (within a tolerance
  band, e.g. 8-13s) — matches `kDefaultPollingInterval`.
- **GC-ONESHOT:** a `getCurrentPosition` in the same session fires exactly once
  (the re-fire is watch-only; regression guard for sp4-geo's single-shot path).
- **GC-NODOUBLE:** a `getCurrentPosition` issued at t=2s during a standing watch
  must not spawn a parallel re-fire chain. Count the watch's callbacks over 15s:
  a single chain is `<= 3` (watch ~0s, the shared gCP delivery ~2s, re-fire
  ~12s); two chains add the un-cancelled ~10s fire → 4+. RED on the first
  implementation (which used a fire-and-forget `PostDelayedTask`): 4. GREEN with
  the cancelable `TaskHandle`: 3. (Found by the whole-slice review.)

The 2min / 10min backoff stages are not directly testable (too slow for a verify
run); they are covered by code inspection against the named Chrome constants.
This is a "cadence took effect + one in-flight chain" gate. **What it does NOT
cover** (per this repo's rule 3 — a green gate is not evidence about what it
cannot see): the tab hide/unhide visibility path (not JS-triggerable headless) —
that trigger of the parallel-chain bug is closed by the same `StopUpdating()`
cancel that GC-NODOUBLE exercises through `clearWatch`, argued by inspection; and
the exact 2min/10min stage timing.

## 5. Residual / out of scope

- **Coordinate jitter (the original roadmap framing): deferred, and probably
  never for a stationary position** — it would imply motion the configured fixed
  position does not represent. If a future slice models a *moving* profile it
  belongs there, fit to a real capture, not here.
- **Exact backoff timing on non-ChromeOS platforms** — the constants read are the
  ChromeOS provider's; `GenericWifiPollingPolicy` mirrors them. Matching the
  10s/2min/10min shape is the coherence target, not per-platform micro-timing.
- **Exact-regularity residual.** Re-fires land at exactly 10000/120000/600000 ms
  with zero jitter, while real WiFi polls jitter around their interval. Far milder
  than the deliver-once tell it replaces, and left as-is: adding timing jitter is
  the same "model a distribution without a capture" risk the coordinate jitter was
  deferred for. A page timing precise inter-callback gaps could still note the
  suspiciously exact 10s.
- **Single-in-flight-chain invariant.** The re-fire is a cancelable `TaskHandle`
  (`camou_geo_refire_task_`), cancelled before each re-post in `QueryNextPosition`
  and in `StopUpdating()`. This is load-bearing: any path that clears `updating_`
  without cancelling (a request entry reset, or `StopUpdating` on tab hide /
  clearWatch / `ContextDestroyed`) would otherwise let the next re-arm post a
  second self-perpetuating chain and degrade the cadence to N× — the opposite of
  this slice's goal. (The first implementation had this bug; see §4 GC-NODOUBLE.)
- **maximumAge / cached-position interactions** unchanged from sp4-geo.

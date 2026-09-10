# SP7 D3 / A3 #4 — seeded Chrome vs the fork's defaults, measured — 2026-09-10

D3 (`specs/2026-08-26-sp7-phone-home-removal-design.md`) rejected a baked-in
seed and named "a per-instance seed derived from configuration" as SP5b's
long-term answer, with the rule *measure before building*. This is the
measurement. Roadmap A3 #4.

## 1. What was compared, and the two confounds

| | seeded Chrome | the fork |
|---|---|---|
| binary | Google Chrome `151.0.7922.138`, the user's Mac, `--headless=new` | `out/Default/chrome` on the box, no config, `--headless=new` |
| OS | macOS | Linux (WSL2) |
| feature state | live Finch seed | compiled defaults (`disable_fieldtrial_testing_config=true`, no seed fetch) |

The Mac's Chrome is two milestones behind the pin and on a different OS, and
neither can be changed from here (no way to update the user's browser; no
stock Chrome 153 for Linux on the box). A clean measurement needs stock
Chrome 153 on the same OS as the fork build. This was the closest reachable,
and every delta below is attributed to one of: OS, milestone, or seed.

Probe: a `file://` page dumping `Object.getOwnPropertyNames(Navigator.prototype)`,
`Object.getOwnPropertyNames(window)`, and the Privacy Sandbox surfaces.

## 2. Result

| surface | seeded Chrome 151 (Mac) | fork 153 (Linux) |
|---|---|---|
| `Navigator.prototype` members | 83 | 81 |
| `window` own properties | 1237 | 1223 |

`Navigator.prototype` only in the fork: `cpuPerformance` — upstream at the
pin (`navigator_cpu_performance.idl`, last commit `507c6ee3e2`, no patch
touches it). Only in Chrome 151: `bluetooth`, `canShare`, `share` — Web Bluetooth and
Web Share, macOS-only.

`window` only in the fork: `HTMLCameraElement`, `HTMLMicrophoneElement`, `NodeRange`, `OpaqueRange`, `PermissionsPolicy` — none named by any
patch or addition, so upstream additions between 151 and 153. Only in
Chrome 151: `BarcodeDetector`, `Bluetooth`, `BluetoothCharacteristicProperties`, `BluetoothDevice`, `BluetoothRemoteGATTCharacteristic`, `BluetoothRemoteGATTDescriptor`, `BluetoothRemoteGATTServer`, `BluetoothRemoteGATTService`, `BluetoothUUID`, `FontData`, `SharedStorage`, `SharedStorageAppendMethod`, `SharedStorageClearMethod`, `SharedStorageDeleteMethod`, `SharedStorageModifierMethod`, `SharedStorageSetMethod`, `SharedStorageWorklet`, `queryLocalFonts`, `sharedStorage` — Bluetooth and `queryLocalFonts`/`FontData`
and `BarcodeDetector` are macOS-only; the `SharedStorage*` family is the one
candidate for a seed delta, settled below.

| Privacy Sandbox probe | seeded Chrome 151 | fork 153 |
|---|---|---|
| `joinAdInterestGroup` | True | True |
| `runAdAuction` | True | True |
| `browsingTopics` | True | True |
| `sharedStorage` | True | False |
| `fencedFrame` | True | True |
| `attributionReporting` | False | False |
| `privateAggregation` | False | False |
| `adAuctionComponents` | True | True |
| `cookieDeprecationLabel` | False | False |
| `deprecatedReplaceInURN` | True | True |
| `createAuctionNonce` | True | True |

**The single feature-state delta is milestone, not seed.** `window.sharedStorage`
is gated by the Blink runtime feature `SharedStorageAPI` (`base_feature: "none"`).
At tag `151.0.7922.138` its `runtime_enabled_features.json5` entry has
`status: "stable"`; at the pin `153.0.8010.36` it has no status (off by
default, and the IDL now carries `DeprecateAs=SharedStorageAPIAll`). The
fork with `--enable-blink-features=SharedStorageAPI` reports it `true`,
so the gate is exactly that flag. The only study naming it in
`fieldtrial_testing_config.json` (`SharedStorageDeprecation`) *disables*
it, so neither the testing config nor a seed would turn it on at 153.

Attributable to the seed: **nothing** in this probe set. Protected Audience
(`joinAdInterestGroup`, `runAdAuction`, `adAuctionComponents`,
`createAuctionNonce`, `deprecatedReplaceInURN`), Topics and fenced frames
are on in both; `attributionReporting`, `privateAggregation` and
`cookieDeprecationLabel` absent in both.

## 3. Disposition: A3 #4 deferred, with this measurement

A per-instance seed needs a catalogue of real studies and their population
splits to draw group assignments from, and that only comes from a captured
seed at the claimed milestone. Assigning groups from an invented
distribution is the same fabrication class as an invented GPU table (A3 #2).
With no seed-attributable delta observed and no detector observed probing
feature state, D3's own rule holds: not built.

Two things unblock it: a captured real seed on the pinned milestone as the
study source, or an observed detector checking feature state. Either
reopens this with the measurement above as its RED baseline.

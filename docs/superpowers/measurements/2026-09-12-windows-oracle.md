# Windows oracle: the fork's Windows identity against real Chrome 153

Spec: `specs/2026-09-12-windows-oracle-design.md`. Plan:
`plans/2026-09-12-windows-oracle.md`. Direction from the user: Windows first.

## 1. The measurement

`scripts/capture_host_oracle.py` renders one page on stock Google Chrome
153.0.8010.36 on the box's Windows 10 host — headed through the host CDP
helper (`winhost.cdp_eval`) and headless — and stores 229 leaves: window
keys and property names, `Navigator.prototype`, 56 navigator members by
type or value, client hints, screen, 29 media queries, Intl, AudioContext,
an OfflineAudioContext fingerprint, voices, WebGPU, 14 codec answers,
MediaCapabilities, 17 permission states, keyboard layout, storage, heap,
media devices, canvas hashes, `document.fonts.check`, error-stack shape and
prototype counts (`baselines/chrome-8010-stock-oracle-windows.json`).
`scripts/verify_host_oracle.py` renders the same page in the fork under
`gen.py --os windows --seed 1` and prints every leaf that differs;
identity- and machine-bound leaves are compared for shape only.

The page emits progressively into a hidden element and finally into `#o`
(the probe reads `#o` once it is non-empty, which the first version tripped
over: it read a partial report). Headless stock differs from headed stock on
its own — 22 voices vs 3, permission queries that never resolve — so the
headed capture is the oracle.

## 2. First run: 20 differences in 229 leaves

| leaf | stock Windows | fork (Windows claim, before) | verdict |
|---|---|---|---|
| `userAgentData.brands` | Google Chrome / Not_A Brand / Chromium | Chromium / Not_A Brand | fork's: a Chromium-branded build has no product brand |
| `navigator.share`, `canShare` | function | absent | fork's: WebShare is compiled in only for Android/ChromeOS/Win/Mac |
| `navigator.bluetooth` + `Bluetooth*` (8 interfaces) | present | absent | fork's: WebBluetooth's json5 status excludes Linux |
| `queryLocalFonts`, `FontData`, `permissions.query({name:"local-fonts"})` | function, interface, `prompt` | absent, absent, TypeError | fork's: sp4-fonts switched FontAccess off outright |
| `speechSynthesis.getVoices()` | Microsoft David (default), Mark, Zira; en-US | `[]` | fork's: the generator never emitted `voices:list` |
| `AudioContext.sampleRate` | 48000 | 44100 | residual: the box's real output rate; sp4-audio decided not to spoof it (buffer-length coherence) |
| canvas text / shape hashes | — | differ | expected: font files and rasterizer differ; `canvas:seed` noise makes every user unique anyway |
| `(pointer)`, `(hover)`, `(any-*)` | none / no hover | fine / hover | host artefact: the PC has no mouse attached; a desktop with input says what the fork derives |
| `navigator.keyboard.getLayoutMap()` | empty | `KeyA → a` … | host artefact: no keyboard attached |
| `__camou_init` in `Object.keys(window)`, prototype count +1 | — | present | the probe's own init-script marker (patchright's `add_init_script` lands in the main world; the driver verify excludes it too) |
| WebGPU `requestAdapter()` | `null` (headed and headless, temp profile) | `null` | nothing to match |

Everything else — 209 leaves: client hints (platform `Windows`, `10.0.0`,
x86/64, wow64 false, formFactors Desktop), `navigator.platform` and the
rest, screen shape, media queries other than pointer/hover, Intl, codec
answers (proprietary pairs included), MediaCapabilities, permission states,
`document.fonts.check`, error-stack shape, prototype counts — matched.

## 3. What changed

- **`ua:brand`** (86th key, string). `GetUserAgentBrandList` in
  `embedder_support` adds a product brand only under `!CHROMIUM_BRANDING`;
  with the key set it uses the claimed brand, and Chromium's own
  `GenerateBrandVersionList` + `ShuffleBrandList` then give the stock order
  for the same seed (the major version). The generator emits `Google Chrome`
  for every identity. Same producer for `navigator.userAgentData` and the
  `Sec-CH-UA*` headers; `verify_sp1a_chrome.py` still 34/34 (its
  unconfigured rows compare a build against itself). Key group
  `kUaMetadataKeys` grew to eight, so a brand-only config is a half-config
  like the rest.
- **Claim-gated runtime features.** In `ChromeContentRendererClient::
  RenderThreadStarted`, beside Chromium's own compile-time `EnableWebShare`,
  a Windows or macOS claim (`camoucfg::ClaimedOs`) enables `WebShare`,
  `WebBluetooth` and `FontAccess`; a Linux claim keeps Linux's shape.
  `chrome/renderer` gained the `//components/camoucfg` dep and DEPS grant
  (`gn check`, `checkdeps` both clean).
- **Font Access with the claimed host's faces.** The json5 entry keeps
  status `""` (the interface is off until the claim gate) but gets
  `base_feature_status: "enabled"`, because the generated base::Feature
  followed the status and `queryLocalFonts()` threw "Font Access feature is
  not supported" even with the interface present. Key **`fonts:local`**
  (87th, string_list of `postscript\tfull\tfamily\tstyle`): after the real
  permission flow, `FontAccess::DidGetEnumerationResponse` resolves with the
  configured faces instead of the host enumeration (which would have listed
  the bundle). The generator emits the 186 faces captured on the Windows
  host (`families.Windows.faces`, `capture_fonts_list.py --names`), sorted by
  PostScript name as stock returns them.
- **Voices.** `settings/voices.json` holds the stock headed list;
  `gen.voices_keys` emits it under a Windows claim.

## 4. Rows (`verify_host_oracle.py`, box `out/Default/chrome`, 2026-09-12)

| row | result |
|---|---|
| O1 generated Windows identity vs stock Windows Chrome: **0 differences in 229 leaves** outside the named set (five pointer/hover leaves and four keyboard leaves — the host has no input devices; the probe marker; `audio.sampleRate`) | PASS |
| O2 RED, a Linux claim: `navigator.share` / `bluetooth` absent, the eight `Bluetooth*` interfaces and `queryLocalFonts` absent — the gate follows the claim, not the build (before the json5 `copied_from_base_feature_if: "overridden"` line, an enabled base feature had switched `queryLocalFonts` on for every claim: the RED caught it) | PASS |
| O3 `queryLocalFonts()`: with the prompt denied (headless) → `[]`, as stock resolves on denial; with `local-fonts` granted and a click for activation → exactly the 186 manifest faces in PostScript order, none of the bundle's | PASS |
| O4 the brand list from both producers: `Sec-CH-UA` and `Sec-CH-UA-Full-Version-List` request headers (browser process, read at an echo server after `Accept-CH`) == `navigator.userAgentData.brands` / `fullVersionList` (renderer) == the host's stock list in stock order (`Google Chrome`, `Not_A Brand`, `Chromium`). RED with `ua:brand` left out: both headers carry `"Chromium";v="153", "Not_A Brand";v="8"` and the row fails | PASS |
| `verify_sp1a_chrome.py` (headers + `userAgentData` against the pristine build) | 34 PASS |
| `verify_sp2.py`, `verify_sp2b.py`, `verify_sp4_voices.py` 5/5, `verify_sp4_fonts.py`, `verify_fonts_bundle.py` 17/17, `verify_sp6b_generator.py` N=3 (15/15, the three new keys under strict), `verify_ua_halfconfig_reject.py`, `run_coherence_tests.sh` 7/7 (15) | all PASS |
| `components_unittests`, every camoucfg suite in the tree except the per-process coherence one (21 suites by name; `kUaMetadataKeys` went 7 → 8) | SUCCESS: all tests passed |
| `gn check` `//chrome/renderer:*`, `//third_party/blink/renderer/modules/font_access:*`; `checkdeps` on both | OK |

Box tip `1ae7cdb240 windows-oracle` (new patch stem: `user_agent_utils.cc`,
`chrome_content_renderer_client.cc` + `chrome/renderer/{BUILD.gn,DEPS}`,
`font_access.cc` + its `BUILD.gn`, the json5 entry); export gate empty.

## 5. Residuals, named

- `fonts:local` under a macOS claim was `[]` until the Mac's faces were
  recaptured (`capture_fonts_list.py --where mac`, 409 faces): a granted
  `queryLocalFonts()` would have listed nothing, a manufactured tell. The
  generator now emits the key only when the manifest has faces for the
  claimed OS (real enumeration otherwise, rule 5) and `test_gen` asserts
  both lists are non-empty and sorted. The macOS list itself is unmeasured
  against a Mac (skipped by direction).
- `voices:list` is the en-US host's three voices for every Windows identity,
  including a `fr-FR` locale claim; a per-locale voices table is the fix.
- The Linux-claim sub-run (O2) showed `uadHigh.platformVersion` empty from
  the pool: out of scope for this slice.
- The probe marker: `__camou_init` in the main world's `Object.keys(window)`
  is the driver contract's C6 measured again (`verify_sp6b_driver.py`:
  patchright's `add_init_script` lands in the main world; a caller must
  never add one a page could enumerate). The oracle excludes it by name.

- `AudioContext.sampleRate`: 48000 on the host, 44100 on the box; sp4-audio's
  decision stands (spoofing the rate desyncs buffer lengths).
- **Erratum 2026-09-12:** `navigator.share()` with a user gesture on the
  fork did not hang, it **killed the renderer** (the broker has no Linux
  `ShareService` binder; `ReportNoBinderForInterface`). Fixed in
  `windows-behaviour` (`measurements/2026-09-12-windows-behaviour.md`); the
  seventh cut ships the defect. Without a gesture it rejects
  `NotAllowedError` as stock. `navigator.bluetooth.getAvailability()` reports
  the box's BlueZ answer. Presence is what pages enumerate; behaviour past
  the first call is unmeasured here.
- The oracle host has no mouse, keyboard or WebGPU adapter: those leaves are
  excluded by name, not measured. A desktop host would turn them into rows.
- The brand list follows the claim on every OS (the generator always emits
  `Google Chrome`); a Chromium-only brand list is reachable by leaving
  `ua:brand` out.

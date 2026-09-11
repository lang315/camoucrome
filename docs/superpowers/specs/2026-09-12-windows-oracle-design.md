# Windows oracle: the fork's Windows identity measured against real Chrome — design

Date: 2026-09-12. The user's direction: Windows first, macOS skipped.

## 1. The oracle

`scripts/capture_host_oracle.py` renders one page on stock Google Chrome
153.0.8010.36 on the box's Windows 10 host (headed through the host CDP
client, and headless) and stores every cheap page-visible surface a
fingerprinter enumerates: `Object.keys(window)`, `getOwnPropertyNames(window)`
(minus `on*`/`webkit*`), `Navigator.prototype`, 56 navigator properties by
type or value, client hints (low and high entropy), screen, 29 media queries,
Intl, AudioContext properties and an OfflineAudioContext fingerprint, voices,
WebGPU adapter, 14 codec answers, MediaCapabilities, 17 permission states,
keyboard layout, storage estimate, heap limit, media devices, two canvas
hashes, `document.fonts.check`, error-stack shape and prototype counts →
`baselines/chrome-8010-stock-oracle-windows.json`. `scripts/verify_host_oracle.py`
renders the same page in the fork under a **generated** Windows identity
(`gen.py --os windows --seed N`) and prints every leaf that differs; values
that follow the identity or the machine (screen, cores, memory, zone,
languages, quota, heap, latencies, hashes, device ids, GPU strings) are
compared for shape only. The first run (2026-09-12) gave **20 differences
in 229 leaves**; this spec closes the ones that are the fork's and names
the rest.

## 2. What the diff said, and what each becomes

| difference (fork vs stock Windows) | cause | decision |
|---|---|---|
| `userAgentData.brands` (and `Sec-CH-UA*`): stock `Google Chrome / Not_A Brand / Chromium`, fork `Chromium / Not_A Brand` | `GetUserAgentBrandList` adds the product brand only under `!CHROMIUM_BRANDING` | **key `ua:brand`** (string): when set, the brand list is generated with it as the product brand — Chromium's own `GenerateBrandVersionList` + `ShuffleBrandList` then yield the stock order for the same seed (major version). Absent → real (Chromium). The generator emits `"Google Chrome"` for every identity (the pool's brands carry it). Same code feeds `navigator.userAgentData` and the headers. |
| `navigator.share` / `canShare` absent | `chrome_content_renderer_client.cc` enables `WebShare` only on Android/ChromeOS/Win/Mac at compile time | **claim-gated runtime features**: in `ChromeContentRendererClient::RenderThreadStarted` (the same place), enable `WebShare` when `camoucfg::ClaimedOs` is Windows or Mac (the real branch stays for real Win/Mac builds). A Linux claim keeps Linux's real absence (rule 5). |
| `navigator.bluetooth` + 8 `Bluetooth*` interfaces absent | `WebBluetooth` json5 status per OS: Win/Mac stable, default experimental | same place: `WebRuntimeFeatures::EnableFeatureFromString("WebBluetooth", true)` under a Windows/macOS claim (Linux has the BlueZ backend, so the browser side exists; `getAvailability()` reports the box's real answer) |
| `queryLocalFonts` + `FontData` absent, `permissions.query({name:"local-fonts"})` throws | sp4-fonts disabled `FontAccess` outright | **presence back, content from config**: enable `FontAccess` under a Windows/macOS claim (the real permission flow stays: user activation, `local-fonts` prompt); a new key **`fonts:local`** (string_list of `postscriptName\tfullName\tfamily\tstyle`) replaces the enumeration result in `FontAccess::DidGetEnumerationResponse` when present, so a granted query lists the claimed host's 188 faces, never the bundle's. The generator emits it from the manifest's captured faces (`families.<os>.faces`, added by `capture_fonts_list.py --names`). Absent key → real enumeration (rule 5). |
| `speechSynthesis.getVoices()` `[]` vs 3 Microsoft voices | the generator never emitted `voices:list` | the generator emits the stock Windows headed list (David default, Mark, Zira; en-US, localService true) under a Windows claim, captured into `settings/voices.json` from the oracle. |
| `AudioContext.sampleRate` 44100 vs 48000 | the box's real output rate; sp4-audio decided not to spoof (buffer-length coherence) | **named residual**, unchanged: the number is recorded. |
| canvas text/shape hashes differ | fonts (Selawik vs Segoe UI) and rasterizer; `canvas:seed` noise makes every user unique anyway | recorded, not a row. |
| `(pointer)`/`(hover)`/keyboard map | the host has no mouse or keyboard attached (headless PC); a desktop with input says `fine`/`hover`, which the fork derives | host artefact: excluded from the diff with the reason. |
| `__camou_init` in `Object.keys(window)` | the probe's own init-script marker (patchright's `add_init_script` lands in the main world; `verify_sp6b_driver.py` already excludes it) | excluded; noted as the probe's artefact, not the fork's. |

## 3. Rules kept

- No JS: every change is C++ (`embedder_support`, `chrome/renderer`,
  `blink/modules/font_access`) or generator data.
- Rule 5: every new key absent → real value; claim-gated features follow
  `ClaimedOs`, which is derived (no new key).
- Rule 4: `ua:brand` needs no invariant (a string beside an already-claimed
  version); `fonts:local` gets no invariant either (its absence is the real
  enumeration, its presence is data). `fonts:local` faces are the captured
  host's, the same host the family list came from.
- Bad config never crashes: an ill-formed `fonts:local` line is skipped.
- Worker parity: `navigator.userAgentData` in a worker reads the same
  producer (already measured in SP1a); `share`/`bluetooth`/`queryLocalFonts`
  are window-only interfaces on stock too.

## 4. Verification

`verify_host_oracle.py` becomes the row: **O1** zero differences outside the
named ignore set (host artefacts, identity-bound, probe marker) under a
generated Windows identity; **O2 RED** the same page under a *Linux* claim
still shows the Linux shape (no `share`, no `bluetooth`, Chromium-only
brands) — the gate follows the claim, not the build; **O3** a granted
`queryLocalFonts()` (Playwright `grant_permissions(["local-fonts"])`, with
user activation) lists exactly the manifest's Windows faces, sorted by
PostScript name as stock does, and none of the bundle's; **O4** `Sec-CH-UA`
/ `Sec-CH-UA-Full-Version-List` request headers carry the three brands in
stock order (`verify_sp1a_chrome.py` re-run: its stock baseline is
Chromium-branded content_shell, so its brand row is re-based on the host
oracle). Regressions: the sp2a/sp1a/sp4-voices/sp4-fonts verifies, fonts
bundle 17/17, coherence 7/7.

## 5. Closed by fact / out of scope

Windows 11 family list (no host); `sampleRate` (decision recorded); WebGPU
adapter (`requestAdapter()` returns null on the host both headed and
headless with a temp profile — measured, nothing to match); macOS
(skipped by direction).

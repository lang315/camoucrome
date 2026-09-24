# 2026-09-24 whole-project review: triage

Four reviewers covered four areas: the config layer, the patches, scripts/CI, and the clients. Each finding in this file was checked against the source or against the fork binary before it was accepted.

- **Binary under test:** `~/chromium/src/out/Default/content_shell`, built from branch `camoucrome/main` tip `ada4cdcfa4`.
- **Probe:** `probe_review.py`, run with `lib_shell.session` in `~/camoucrome-verify`.

Verdicts:

- **CONFIRMED**: reproduced on the binary, or read in the code with no remaining doubt.
- **REFUTED**: the claim is false.
- **LATENT**: the mechanism is real, but no shipped input reaches it.
- **OPEN**: a redesign is needed, not a fix.

The scripts, CI and client rows are tracked separately in the tooling section below.

## Config layer and patches

| # | Finding | Verdict | Evidence |
|---|---|---|---|
| 1 | `GetUint32From` rejects numbers above 2^31−1, because JSONReader stores them as doubles. The clients draw seeds from 1 to 0xFFFFFFFF, so each seed family (canvas, audio, media) is off in about 50% of launches. | CONFIRMED | Probe: `canvas:seed 4000000000` gives **0** noised pixels out of 4096. The control, `canvas:seed 12345`, gives 3930. |
| 2 | Canvas noise is keyed by byte index within the readback buffer plus a hash of its first 1 KB, not by the pixel's position in the canvas. | CONFIRMED | Probe: `getImageData(0,0,16,16)` and `getImageData(5,5,1,1)` disagree on the same pixel (`subrect_consistent:false`). |
| 3 | Noise is applied to RGB where alpha is 0. | CONFIRMED | Probe: a blank 32×32 canvas has 738 pixels with alpha 0 and non-zero RGB. Stock has 0. |
| 4 | The content-hash window is only 1 KB. | CONFIRMED (by reading) | `canvas_noise.cc:22-30`. Folded into the redesign of #2. |
| 5 | `copyToChannel` followed by `copyFromChannel` does not return the written data. | CONFIRMED | Probe: with `audio:seed 12345`, 128 of 128 samples differ. Stock: 0. |
| 6 | FontAccess is off unless the claim is Windows or macOS. | CONFIRMED | The pristine Linux Chrome capture at the pin (`baselines/chrome-507c6ee3e2-stock-ua.json`) has `queryLocalFonts` in `window_keys`. Probe with no config: `typeof queryLocalFonts === "undefined"`. The windows-oracle comment "not on Linux" is wrong. |
| 7 | Preset merge is per key: an explicit `ua:platform` leaves the preset's `ua:osInfo` in place, and `ClaimedOs` reads osInfo first. | CONFIRMED (by reading) | `mask_config_internal.cc:233` and `derive.cc:161`. |
| 8 | An explicit `null` key replaces a valid preset value. | CONFIRMED (by reading) | `DictValue::Merge`. |
| 9 | Canvas strength and density are unbounded; strength near INT_MAX makes the signed int add undefined behaviour. | CONFIRMED (by reading) | `canvas_noise.cc:54`, `derive.cc:184`. |
| 10 | With invalid explicit config plus a preset, the log says "all spoofing is disabled", but the preset still applies. | CONFIRMED (by reading) | `ParseConfig`'s message versus the `ParsedConfig` merge. |
| 11 | The validator's `CheckFitsWithin` silently skips `1920.0`-style doubles. | CONFIRMED (by reading) | Fixed with #1: the same getter. |
| 12 | Only `"default"` is kept verbatim; Windows also exposes `"communications"`. | CONFIRMED | `media/audio/audio_device_description.cc:19` `kCommunicationsDeviceId[] = "communications"`. |
| 13 | `KeyIsSet` and `gl_params` read `ParsedConfig()` directly and ignore the scope. | LATENT | One global config today. |
| 14 | A preset's `gpu.parameters` is copied into both the webGl and webGl2 tables, so WebGL2-only pnames can answer in WebGL1. | LATENT | The shipped preset has 13 pnames, none WebGL2-only (checked for 0x8073, 0x88FF, 0x8A2F, 0x8B4A, 0x9122, 0x8D57, 0x8CDF). |
| 15 | Humanized mouse: the final real event keeps its dispatch-time timestamp, which is older than the synthetic moves before it. | CONFIRMED (by reading) | `sp2b` `ForwardHumanizedMouseEventCompletion` never re-stamps; the synthetic moves are stamped `Now()` when they fire. |
| 16 | The `tz-locale` fallback reads only `navigator.language`. | CONFIRMED | Probe: with `navigator.languages:["de-DE","de"]`, `navigator.language` is `de-DE` but Intl reports `en-US`. |
| 17 | WebGL extension whitelist: `getSupportedExtensions` returns the config list as-is, while `getExtension` goes through the tracker. | CONFIRMED | Probe: a whitelisted name that has no tracker is listed, yet `getExtension` returns null. By reading: a listed name returns true before the real support check, so an extension the GPU lacks is handed out as a live object. |
| 18 | `battery:charging false` gives `chargingTime 0`. | CONFIRMED | Probe: `{"charging":false,"chargingTime":"0"}`. A discharging device reports Infinity. |
| 19 | `navigator.maxTouchPoints -1` reaches the page. | CONFIRMED | Probe: `mtp:-1`. The key is declared int32; negative values must be rejected. |
| 20 | With media enabled, before permission there are 3 blank `audioinput` entries. | CONFIRMED | Probe: `["audioinput::","audioinput::","audioinput::","videoinput::","audiooutput::"]`. Stock shows at most one entry per kind before permission. |
| 21 | `lib_shell.evaluate` uses stock Playwright, which sends `Runtime.enable`. | REFUTED as a defect | The verify harness measures values, not detection. `measure_sp2b_stack.py` does not use `lib_shell`; its state C *deliberately* includes a connected Playwright (see its docstring). The CLAUDE.md rule governs the shipped clients, which use patchright. |
| 22 | Synthetic media IDs are not mapped back, so `getUserMedia({deviceId:{exact}})` fails. | OPEN | Needs a reverse map in the browser process. |
| 23 | `readPixels` noise skips user framebuffers and ignores `PACK_ROW_LENGTH`/skip settings. | OPEN | Part of the canvas redesign (#2). |
| 24 | Geolocation position posted before the permission check. | OPEN | Not reproduced yet. |
| 25 | WebGPU adapter info is not spoofed. | OPEN | Already on the roadmap (2026-09-14 notes). |
| 26 | `screenX` versus the MouseEvent screen offset; `measureText` jitter versus layout. | OPEN | These are design trade-offs of window-geometry and metric-jitter. |

## Tooling (scripts, CI, clients)

Each finding was reproduced locally, and each fix got a test that failed before it (details in the working-tree diff).

| ID | Finding | Verdict / fix |
|---|---|---|
| S1 | CI steps ran `bash -e` without pipefail, so `cmd \| tail` hid failures | CONFIRMED (`bash -e -c 'false \| tail -1'` → 0). Fixed with `defaults: run: shell: bash` (pipefail). `run()`'s `grep \| head` got `\|\| true` so a FAILED row still sets `rc=1`. The unit-test step writes to a file. Suite collection now matches `TEST_F`. |
| S2 | `cp … \|\| true` hid failed copies; rsync ran without `--delete` | CONFIRMED. The masking is removed. `--delete` applies to `client/` only; `baselines/` holds box-local captures. |
| S3 | The sync gate never compared `patches/` with the branch, and a `git diff` against a missing branch read as PASS | CONFIRMED. The gate now hashes each commit's diff exactly as `export.sh` writes it and compares against `patches/` and `series`. A failed `git diff` is a FAIL. Checked here against the box: a tampered `sp4-battery.patch` gives rc=1, restored gives rc=0. |
| S4 | `apply.sh` printed "done" when the series was empty or missing | CONFIRMED. It now fails, and asserts `applied N/N`. |
| S5 | The `gen_keys` literal-key regex was blind to `GetX(ScopeFor(ctx), "k")` and to multi-line calls | CONFIRMED (3 of 7 new tests failed first). It found a real hit, `sp0-config-layer.patch:70`, whose line sp1a removes later. The check now looks at what the whole series adds, and still reports that hit when sp1a is left out of the series. |
| S6 | `package.py` accepted a component build by default and a deps list without the binary | CONFIRMED. Fixed; 10/10 tests. |
| S7 | `export.sh` `git diff` depended on user config | Already pinned at HEAD (`--no-ext-diff --no-color --src-prefix/--dst-prefix`); confirmed on a repo with `diff.noprefix`. |
| S8 | `winhost.py` built PowerShell double-quoted strings from JSON, and `Get-Process .CommandLine` does not exist on PS 5.1 | CONFIRMED. Now uses `ps_quote()` single-quoted literals and `Get-CimInstance Win32_Process`. Only the script text is tested; no PowerShell on the Mac. |
| S9 | The oracle, behaviour and fonts-bundle verifies passed on `n == len(results)` | CONFIRMED. They now use fixed expected row counts (4 / 1 in the `--config` sub-run, 14, 17). |
| C1, C5 | The Node client never chunked `CAMOU_CONFIG`; no client chunked `CAMOU_PRESET` | CONFIRMED. All three clients now chunk both (Node by code point, Go by rune). |
| C2 | Accept-Language ignored the preset's locale | CONFIRMED. The clients now read the effective keys (preset expanded as `preset_loader.cc` does, explicit config on top). |
| C3 | `has_touch` / `is_mobile` were not forbidden | CONFIRMED. Added to Python, Node and the contract. Go has no such options. |
| C4 | The temporary profile was never removed | CONFIRMED. It is removed on close and on a failed launch. |
| C6 | `gen.py` silently returned no profiles when pip-installed | CONFIRMED. It now raises an `ImportError` that names the path and `CAMOUCROME_ROOT`. |
| C7 | A Go typed-nil config was sent as `CAMOU_CONFIG=null` | CONFIRMED. Fixed. |
| C8 | Bad input was handled differently across clients | CONFIRMED. All three now reject a non-object config and a non-list `navigator.languages`. |
| C9 | The claimed OS was derived differently in each client | CONFIRMED. All three now mirror `derive.cc` `ClaimedOs` over the effective keys. |
| C10, C11 | An inherited `FONTCONFIG_FILE` was kept; a missing `.conf` went unchecked | CONFIRMED. The inherited value is dropped; a missing `.conf` is an error. |
| C12 | The Go chunk test used only ASCII | CONFIRMED. There is now a UTF-8 validity test, which goes RED under byte slicing. |
| C13 | Go `Launch` wiring is untested | OPEN: there is no seam to fake playwright-go. The Python and Node fake-driver tests cover the same contract. |
| C14 | The `verify_sp6b_driver` probes run with no config | OPEN: fixing it needs a re-measure on the box. |
| C15 | The probes pick the first `/proc` match | OPEN: the same applies. |

## Fixes (config layer and patches)

The fixes were committed on `camoucrome/main` as fixups and autosquashed into their owning slices, so there is still one commit per patch (36 commits above the pin). `camoucrome/main-pre-review` keeps the old tip, `ada4cdcfa4`. The patches were regenerated with `export.sh`.

| # | Fix | Where |
|---|---|---|
| 1, 11 | `GetUint32From` accepts whole-number doubles in [0, 2^32). `GetInt32From` accepts whole-number doubles in int32 range. | `mask_config_internal.cc` (`IntegralIn`) |
| 2, 3, 4, 9 | Canvas noise is now `PerturbRgbaAt`. getImageData sub-rects are measured (R2). That toDataURL/toBlob agree with getImageData is shown **by reading only**: both paths hash the same canonical RGBA snapshot and key the noise by the same position, but a page cannot decode the PNG without re-noising, so no row measures it. Each pixel's noise depends only on seed, absolute canvas (x, y) and channel, combined with `CanvasStateHash` of the whole canvas (a strided sample of at most 65536 pixels, cached per `SkImage::uniqueID`). Only opaque pixels change. Strength is clamped to [0, 255] and density to [0, 1]. The Blink call sites go through `camoucfg::PerturbCanvasPixels` (the new `:canvas_readback` target, which is the only piece that depends on Skia). | `canvas_noise.cc`, `canvas_readback.cc`, sp3a |
| 5 | `copyToChannel` noises the buffer's existing contents and sets the one-shot guard *before* writing, so samples the page writes read back exactly. | sp4-audio |
| 6 | FontAccess is restored to its stock status: the json5 file is identical to the pin, and FontAccess is dropped from the claim gate. `fonts:local` still answers when set. When it is absent, the real enumeration is filtered through the `fonts:list` allowlist. | sp4-fonts, windows-oracle |
| 7 | `OverridePresetGroups`: an explicit member of the OS pair or of the locale triple re-derives the whole preset group from the explicit value. | `preset_loader.cc` |
| 8 | An explicit `null` is dropped before the merge. | `MergeExplicitOverPreset` |
| 10 | The log line no longer claims "all spoofing is disabled" when a preset still applies. | `ParseConfig` |
| 12 | The `"communications"` sentinel is kept verbatim, like `"default"`. | `device_ids.cc` |
| 15 | The final humanized event is re-stamped `Now()`. | sp2b |
| 16 | The Intl locale falls back to `navigator.languages[0]`. | sp4-tz-locale |
| 17 | The extension list is intersected with the real set, and `getSupportedExtensions` uses the same gate as `getExtension`. | sp3b |
| 18 | `charging:false` gives `chargingTime` Infinity, and `charging:true` gives `dischargingTime` Infinity (derived, no key). | sp4-battery |
| 19 | `maxTouchPoints` is read with `GetUint32`, and its type in `keys.json` is now `uint32`. | sp1b |
| 20 | Before a grant, at most one blank entry per kind, matching stock `TranslateMediaDeviceInfoArray` in `content/browser/media/media_devices_util.cc:191`. | sp4-media |

### Evidence

**Unit tests.** 10 new or changed tests failed first. They failed on behaviour, not compilation, because the new functions were first added with the old behaviour:

```
FAILED CanvasStateHashTest.SeesLateContentAndIsDeterministic
FAILED DeviceIdsTest.CommunicationsSentinelIsPreserved
FAILED GettersTest.Uint32AcceptsTheFullUnsignedRange
FAILED MergeOverPresetTest.ExplicitNullKeepsThePresetValue
FAILED OverridePresetGroupsTest.{ExplicitLanguageRederivesTheList, ExplicitLanguagesRederivesLocale, ExplicitOsInfoRederivesPlatform, ExplicitPlatformRederivesOsInfo}
FAILED PerturbRgbaAtTest.{NonOpaquePixelsAreUntouched, SubRectAgreesWithFullRead}
```

After the fix, every camoucfg suite except CoherenceValidatorTest passes, 131 of 131. `CoherenceValidatorTest` runs through `run_coherence_tests.sh`: 7/7 PASS.

**Build and header checks.**

- `gn check`: "Header dependency check OK" for camoucfg, blink core, modules/canvas, battery and font_access.
- `checkdeps`: exit 0 for camoucfg and the three canvas directories.

**Browser verify.** `scripts/verify_review_2026_09_24.py` gives 12/12 ALL_PASS on content_shell. The RED values for rows R1–R4 and R6–R11 are in the table above; R6 was first measured on `about:blank`, which is not a secure context.

**Slice verifies re-run on the fixed binary:**

- Unchanged and passing: sp0, sp1b, sp2b, sp3a, sp3b, webgl_capability_identity, webgl_pairing, audio_ii, phantom, sp4_battery 5/5, sp4_tzlocale 6/6, d_pointer_touch 5/5, sp5a, sp5b_preset 7/7, sp5b_domain, metric_jitter 11/11, fonts_ii, ua_halfconfig_reject.
- Expectations updated because the old ones encoded the fingerprint:
  - `verify_sp4_media` M1/M3, 4/4: before a grant, one entry per kind.
  - `verify_media_ii` M1, 13/13: same change.
  - `verify_sp4_audio` A7, ALL_PASS: page-written samples read back exactly.
  - `verify_webgl_profile` W2/W3, 4/4: the expected extension set is profile ∩ host.
  - `verify_sp4_fonts` F5–F7: `queryLocalFonts` present, as stock.

**Round trip.**

- `git apply --cached` of all 31 patches onto the pin's tree gives a tree 0 diff lines away from the branch (camoucfg excluded, since it is copied).
- The additions from `export.sh` byte-match the edited additions.

### Trade-off accepted with #17

The WebGL profile list can only narrow what the host GPU really has. On the SwiftShader box, the Windows profile loses 3 WebGL1 and 6 WebGL2 extensions, and the macOS profile loses 4 and 8, for example `KHR_parallel_shader_compile` and `WEBGL_blend_func_extended`. The alternative was handing out objects for extensions the GPU lacks.

## CI verify set on the fixed binary and redeployed clients

The clients, scripts and settings were deployed to the box the way `build-verify.yml` deploys them, and the Go probe was rebuilt. Every script exited 0:

- `verify_sp1a_chrome`: PASS
- `verify_sp4_voices`: 5/5
- `verify_fonts_bundle`: 17/17
- `verify_host_oracle`: 4/4
- `verify_windows_behaviour`: 14/14
- `verify_sp6b_generator` (`CAMOU_GEN_N=2`): ALL_PASS
- `verify_sp6b_launcher`: ALL_PASS
- `verify_sp6b_driver`: ALL_PASS
- `verify_sp4_fonts`: ALL_PASS, with F5–F7 checking that `queryLocalFonts` is present as in stock

Local checks:

- `gen_keys.py --check`: PASS
- `check_additions_build.py`: PASS
- `gen_fontconfig.py --check`: PASS
- pytest (clients and fonts): 48 passed
- `go test`: ok
- node: 12/12
- tooling tests: 21 passed

## Found after the fixes: client and browser disagreed

The two workers applied different merge semantics:

- The `OverridePresetGroups` fix (#7) re-derives the whole preset group when an explicit key overrides one member.
- The clients (C2, C9) still merged preset and config key by key.

With preset `{os: macOS, locale: fr-FR}` and config `{ua:platform: Windows, navigator.language: ja-JP}`:

- **RED**, on the box, pre-fix client: the browser reported `Win32` / `["ja-JP","ja"]`, but the client sent `Accept-Language: fr-FR,fr;q=0.9` and chose the macOS fontconfig.
- **Fix:** all three clients' `effective_keys` now apply the same group rule before they read. Tests were updated in Python, Go and Node; each went RED first, then GREEN (pytest 48, `go test` ok, node 12/12).
- **GREEN, end to end:** `{"platform":"Win32","languages":["ja-JP","ja"],"al":"ja-JP,ja;q=0.9"}`.
- **Re-run afterwards:** `verify_sp6b_launcher` and `verify_sp6b_driver` both ALL_PASS.

## Font Access under a Linux claim

The generator emits no `fonts:list` and no `fonts:local` for `--os linux`; it does emit them for Windows (119 / yes) and macOS (960 / yes). So under a Linux claim, `queryLocalFonts()` lists the host's real faces, and only after the permission prompt. The CSS font gate shows the same host fonts under that claim, and `FONTCONFIG_FILE` is not set for Linux, so the bundle is not on the font path. The two surfaces agree: this is the rule-5 real-value fallback, not a new leak.

## Also open (review findings not fixed in this pass)

- **Android claim and touch** (d-pointer-touch): an Android claim forces `pointer: coarse` even when `maxTouchPoints` is absent, so it reports 0 touch points with a coarse pointer.
- **`package.py` stamps**: `branch_tip` and tree cleanliness are never validated, so a stale binary can get a fresh stamp (scripts #10).
- **`rebuild_branch.sh`**: it aborts mid-series, and its own guard then refuses to run again (scripts #14b).
- **Location of the camoucfg fixes**: they were committed as a fixup of `windows-behaviour-ii` (the tip), not of sp0 or sp5b. `export.sh` archives `components/camoucfg` from the tip, so the exported bytes are the same either way. Look there, not in sp0/sp5b.
- **CI pipefail (S1)**: only the local mechanism demo exists so far. The real GREEN is a `build-verify` run after this is pushed.

# Camoucrome completion roadmap (gap analysis against the SP map and Camoufox)

*Written 2026-09-09 from the tree at `806ac5f`. Program plan, not an
implementation plan: each item still gets measurement → scope decision → plan →
RED-first SDD, exactly as every shipped slice did. Per-slice residuals of the
SP4 arc are NOT re-derived here — they live in
[`2026-09-02-followon-roadmap.md`](2026-09-02-followon-roadmap.md), which is
exhausted for the current harness.*

## 0. What "complete" means

Camoufox's user-facing contract, restated for Chromium: an operator installs a
client, gets a **generated, coherent** config, launches a **phone-home-free**
binary on Linux/Windows/macOS, drives it with **stock Playwright/CDP** without a
page being able to tell — and the fork stays on a **current Chromium milestone**
(the project never spoofs the browser version, so a stale pin is itself a tell).

Against that definition, the state of the sub-project map:

| SP | State | Evidence |
|---|---|---|
| SP0, SP1a, SP1b, SP2a, SP2b, SP3, SP4 (+ follow-ons), SP5a, SP5b-validator | shipped | 25 patches, 83 keys in `kAllKeys`, per-slice `verify_*.py` |
| SP7 | **codecs only** | `settings/build-args.gn` has 2 args; no patch touches variations/crash/metrics/updater/safe-browsing/API keys |
| SP5b catalogue + presets | **not started** | `settings/invariants.json` holds 4 entries; no `settings/presets/`, no `preset_loader` |
| SP6a | **partial** | `apply.sh` exists but checks no pin; no `export.sh`, no `upstream.env`, no `keys.json` codegen (invariants.json still says "SP6a will generate") |
| SP6b | **not started** | no packaging, no Windows/macOS build, no client, no CI |

So the remaining work is not more Blink surfaces. It is the four unstarted or
half-started SPs, plus the harness investments that unblock the residuals the
follow-on roadmap parked, plus a short list of Camoufox surfaces that have no
Chromium counterpart yet.

---

## A. Unstarted sub-projects (the real remaining work), in recommended order

### A1. SP7 — phone-home removal  (highest priority; correlation leak defeats every other SP)

Source: `specs/2026-08-26-sp7-phone-home-removal-design.md` §3/§4, D3/D4/D5.
All page-invisible except where noted, but a per-install identifier emitted from
two "unrelated" sessions links them regardless of fingerprint quality.

1. **`fieldtrial_testing_config.json` must not be applied** — **SHIPPED
   2026-09-09** (`4ae816a` feat, `0a7ddb6` test, `7f7f710` docs;
   `settings/build-args.gn` `disable_fieldtrial_testing_config =
   true`, `scripts/verify_sp7_fieldtrial.py`, measurement
   `2026-09-09-sp7-fieldtrial-config.md`). GN lever, not the switch;
   verified RED→GREEN on `content_shell` (which applies the config too, via
   `content/test/setup_field_trials.cc`) and by a control rebuild. Finding:
   the testing config had been hiding 13 Protected Audience members on
   `Navigator.prototype` (study `ProtectedAudienceDeprecation`); the compiled
   defaults expose them, and whether seeded Chrome stable does is unknown —
   **measure item for A3: capture `Object.getOwnPropertyNames(Navigator.
   prototype)` / `Object.keys(window)` from real Chrome stable on the claimed
   OS and diff.** Also surfaced that `verify_sp1a.py`'s baseline had been
   stale since sp4-fonts landed (`queryLocalFonts` removed by sp4-fonts's
   deliberate `FontAccess` flip, NOT upstream — first attributed wrongly,
   corrected the same day); recaptured with provenance.
2. **Variations / Finch seed fetch** — **measured-off 2026-09-09**, no patch:
   `IsFetchingEnabled()` (`variations_service.cc:271`) is false in a
   non-branded build unless `--variations-server-url` is passed, and
   `content_shell` builds no `VariationsService` at all. Driver constraint:
   never pass `--variations-server-url` (it also flips the testing-config
   answer in a build that still has it). Re-verify on the `chrome` target
   under B1 together with `X-Client-Data`. Resolved D3: no captured seed;
   per-instance seed is SP5b's later concern.
3. **Crash reporting / metrics** — **measured-off 2026-09-09**, no lever:
   `ChromeCrashReporterClient::GetCollectStatsConsent()` returns false in any
   non-`GOOGLE_CHROME_BRANDING` build and `kMetricsReportingEnabled` defaults
   false, so neither uploads (Crashpad still writes dumps locally). D4's GN
   guesses were wrong: `enable_crash_reporter` does not exist upstream and
   `enable_reporting` is the W3C Reporting API — page-observable, untouched.
4. **Component updater / GCM / ListAccounts / network time / omnibox AIM
   eligibility / spellcheck dictionary** — **SHIPPED 2026-09-09**
   (`b3e7ddd` feat, `d1266bb` test, `6b53b1e` docs; `patches/sp7-phone-home.patch`, 9 files; `scripts/verify_sp7_phonehome.py`;
   measurement `2026-09-09-sp7-phone-home.md`). Netlog of a fresh headless
   `chrome` on `about:blank`: 7 Google hosts in 75 s (RED) → `{}` (GREEN),
   four rounds. Auto-update (Omaha) is not built on Linux; Safe Browsing,
   Domain Reliability and API keys produced no traffic in the window and get
   their own measurement before any lever.
5. **Component payloads** (D5) — **MEASURED + DECIDED 2026-09-09**
   (`measurements/2026-09-09-sp7-components.md`): CRLSet / origin-trial keys
   are not page-observable; the tells are `hyphen-data` (`hyphens:auto`
   scrollWidth 152 here vs 60 on real Chrome), MediaEngagementPreload and
   SubresourceFilter (site-specific). Widevine is GN-off on this build, an A5
   licensing item. Mechanism decided: registration back on + `UpdateUrl()`
   choke kept + payloads pre-seeded into the profile dir — built in A5 when
   there is a payload to load.
6. Deliverables: `settings/build-args.gn` grows from 2 args to the full set;
   `patches/sp7-*.patch` for the source levers; a verify that launches the
   binary behind `scripts/echo_server.py`-style capture (or a local proxy) and
   asserts **zero** requests to Google endpoints carrying an install ID, plus the
   feature-state probe. **Harness note:** crash reporting, metrics, the
   updater and Safe Browsing live under `//chrome`; `content_shell` links none
   of them, so their verification needs the `chrome` target (B1). The
   field-trial item is the exception to check (see its Gate 0).

### A2. SP6a — pin, export, key registry, rebase  (tree at risk; version honesty)

Source: `specs/2026-08-26-sp6-build-packaging-design.md` §4.1, §4.2, §4.6.

1. **`upstream.env` + pin check in `apply.sh`** — **SHIPPED 2026-09-09**
   (`0d3f5b0`, pin corrected to `0e8d4a9268` the same day): `apply.sh` sources
   `upstream.env` and refuses any other HEAD; `CAMOU_PIN_OVERRIDE=1` warns and
   continues for the rebase drill. Positive path proven: all 26 patches applied
   clean onto a fresh worktree at the pin (70 files, 2655+/109−). The first
   attempt, on a worktree at `a727b57805`, conflicted on sp0 — which is how the
   pin mix-up was found.
2. **`scripts/export.sh`** — **SHIPPED 2026-09-09.** Branch `camoucrome/main`
   built on the box (worktree `/home/lang/camoumain`, 26 commits above the
   pin, subject == patch stem); `export.sh` regenerates `patches/*.patch`,
   `patches/series`, `additions/`, `settings/invariants.json` from it and
   `apply.sh` now reads `series`. First export reproduced all 26 hand-extracted
   patches byte-identically (gate empty); `apply.sh` on a fresh worktree at the
   pin reproduces the branch tree exactly. RED: a branch with non-stem subjects
   is refused before anything is deleted; a drift commit shows up as a new
   patch + a `series` line. Side effect of the branch diff: the box's
   `browser_commands.cc` "contamination" is sp1b's own hunk (no contamination),
   and the box's `input_handler.cc` was the known un-reviewed UAF rework
   (ledger) — restored to the reviewed blob `443c6f06c9` and rebuilt.
3. **Key registry codegen** — **SHIPPED 2026-09-09.** `settings/keys.json`
   (83 entries: name, key, type, doc carried verbatim from the old header) →
   `scripts/gen_keys.py` → `additions/camoucfg/keys.h`, committed rather than
   a GN action (no build-time python in the patch; `--check` is the drift
   gate). `--check` also holds the `declared` set in `keys_unittest.cc` to the
   JSON and rejects a string literal in the key position of any `Get*`/`HasKey`
   call (the §4.6 presubmit). RED ×3: stale header, missing `declared` name,
   literal key; duplicate key value asserts at load. Types (`string`, `uint32`,
   `int32`, `double`, `bool`, `string_list`, `list`, `dict`, `unsupported`) are
   the client validation table's input (A4). No call site moved.
4. **Rebase onto Chrome stable** — **SHIPPED 2026-09-10** (full sweep: 33
   content_shell + 5 chrome verifies, all green). Step 0 inverted the premise:
   the old pin's `chrome/VERSION` was `154.0.8026.0`, a Dev/Canary-only build
   number; stable was `153.0.8010.36`. Pin policy decided: the current stable
   **tag**, refreshed per milestone (`measurements/2026-09-09-sp6a-version-
   honesty.md`). Drill: 25/26 clean, one include-block conflict, 0 logic
   lines; `text_metrics.cc` unchanged so metric-jitter's mirror stands. New
   base built from scratch on the box (~4 h in chunks), true stock baseline
   captured (`baselines/content_shell-8010-stock-ua.json`, 235 window keys =
   the fork's 234 + `queryLocalFonts`, sp4-fonts's deliberate flip), stack
   rebuilt (164 steps), sweep 33/33 on content_shell (the one red is
   `verify_webrtc_ii_fakeip.py`, the rejected slice's RED record). Exported
   from `camoucrome/main-8010`: 10 patches re-cut (index/context lines; the
   one real change is the resolved include).

### A3. SP5b — invariant catalogue, presets, generator inputs

Source: `specs/2026-08-26-sp5-coherence-engine-design.md` §4.3–§4.5.

1. **Catalogue** — **first fill SHIPPED 2026-09-10**
   (`measurements/2026-09-10-sp5b-catalogue.md`): 4 → 9 entries, each with a
   mutation test — `navigator-language-heads-languages`,
   `locale-tag-matches-navigator-language`, `webgl2-vendor-agrees-with-webgl`,
   `webgl2-renderer-agrees-with-webgl`, `webgl-renderer-backend-fits-os`
   (Direct3D → Windows, Metal → macOS, everything else constrains nothing).
   Deferred with reasons in the doc §4: the two presence relations
   (`timezone:id` with `locale:tag`, `mediaDevices:seed` when enabled) need a
   `Presence` violation kind; geolocation ↔ timezone needs a zone table; DPR
   has no key; `Accept-Language` is a generator obligation. Spec §4.3's
   original list, for what remains:
   DPR (screen/window in CSS px at one DPR), locale/time
   (`navigator.language == languages[0]`, `locale:tag` ↔ `navigator.language`
   ↔ `Accept-Language`, `timezone:id` set with `locale:tag` — the tz-locale
   measurement §5 names these as operator-coherence tells), graphics
   (renderer ↔ vendor ↔ claimed OS; WebGPU adapter ↔ WebGL), audio/media
   (`mediaDevices:seed` non-zero when enabled, counts ≈ real), network (three UA
   channels agree). Each entry lands with its mutation test or it is
   documentation, not enforcement.
2. **WebGL profile database** — value coherence ("do the numeric limits match
   the claimed GPU") was deferred by the capability-identity slice to "the SP5
   profile database, not yet built". This is the Chrome analogue of Camoufox's
   `webgl_data.db` sampled by market share, but with **Chrome-shaped** strings
   (`ANGLE (NVIDIA, NVIDIA GeForce ... Direct3D11 vs_5_0 ps_5_0, D3D11)`) — a
   Firefox renderer string on a Chrome UA is the incoherence rule 4 forbids.
3. **Preset store + loader** — `settings/presets/chromium-<milestone>.json`,
   `additions/camoucfg/preset_loader.{h,cc}`: minimum identifying set, derived
   fields computed at load with the same helpers the validator uses, milestone
   policy on load.
4. **Per-instance variations seed derived from config** — the long-term answer
   SP7 D3 handed to SP5b once presets exist.

### A4. SP6b — driver / client

Source: SP6 §4.5, SP2 D1 resolution, tz-locale measurement §5.

1. **Adopt (not write) a CDP driver that honours the measured constraints**:
   never `Runtime.enable` (D1 — the only *measured* SP2 leak left is the +21%
   stack-timing signal under Runtime), page-agent scripts only in isolated
   worlds, no main-world `addScriptToEvaluateOnNewDocument`. patchright-style
   Playwright is the candidate. **Then actually run SP2's isolated-world
   verification items** (spec items owned by "SP6") — they are unmeasured:
   never executed against any driver, so "closed" is not yet a claim.
2. **Client package** — extend Camoufox's generator into a shared,
   target-parameterised core rather than fork it (SP6 recommendation). What
   ports as-is: `fix_navigator_arch`, `clamp_window_dimensions`,
   `clamp_window_position`, `fix_screen_no_taskbar`, `resample_screen_for_dpr1`,
   GeoIP → geo/tz/locale from the proxy exit, `StatisticalLocaleSelector`,
   font/voice subset per OS, `humanize` toggle, `block_images/webrtc/webgl`,
   `virtual_display`. What changes: BrowserForge `browser='chrome'`, Chrome UA /
   UA-CH brand generation, Chrome WebGL strings (A3.2), Chrome voice names.
3. **Launcher-layer duties the C++ deliberately left to it** (each is a tell if
   forgotten): size the window via `--window-size` / `Browser.setWindowBounds`
   so `innerWidth`/`clientWidth`/`outerWidth` cohere with `screen.*`;
   `--force-device-scale-factor` for DPR; route timezone/locale ONLY through
   `CAMOU_CONFIG` (a second Playwright `timezone_id`/`locale` fails with
   `kAlreadyInEffect`); `--user-data-dir` per identity; extension loading
   (`--load-extension`, uBO) — needs the `chrome` target; custom CA for MITM
   proxies.
4. **Later, not now:** remote server mode, multi-version manager, GUI — the
   `pkgman`/`multiversion`/`server`/`gui` modules are conveniences with no
   anti-detect content.

### A5. SP6b — packaging and builds

Source: SP6 §4.3, §4.4, §6.

1. **`scripts/package.py` from `--runtime-deps-list-file`**; portable
   `tar.xz`/`zip`, no installer, no launcher binary. Release build = full
   `chrome` target, non-component (a different build than the dev loop).
2. **Windows native build** (own checkout on `D:`, VS, serialised with WSL —
   the build scripts should refuse to run both) and **macOS build** (the Mac,
   Xcode). Chromium cannot cross-compile; this is the sharpest divergence from
   Camoufox's `multibuild.py`.
3. **Font bundles** — Camoufox ships Windows/macOS/Linux font sets +
   fontconfig so a Linux host can *have* the fonts a Windows UA implies.
   `fonts:list` today can only *hide* host fonts; a Linux host claiming Windows
   with no Segoe UI resolvable is a tell the allowlist cannot fix. This is a
   packaging deliverable plus a verify that every listed family actually
   resolves (`document.fonts.check` / layout width), plus hinting/AA posture.
4. **Cheap CI now** (SP6 says immediately): `check_additions_build.py`,
   `check_checkout_sync.sh`, the keys/invariants consistency unit test, a
   patch-applies-clean check against a pinned worktree. Full builds stay
   local/manual until a release cadence exists.
5. **Release stamp coherence** across platform archives; runtime-deps
   completeness check (SP6 §6.9/6.10).

---

## B. Harness investments (what unblocks the parked residuals)

The follow-on roadmap's closing line is "exhausted for the current harness".
The next lever is therefore the harness itself. Each row names what it unblocks.

| Harness | Unblocks |
|---|---|
| **B1. `chrome` target build on WSL** (slow loop, but one-time) | SP7 verification (A1); `window.chrome` shape (SP2 §4.7, deferred, now unblocked since D1 = "present as Chrome"); `Sec-CH-UA*` header + `userAgentData` channel verification (SP1a Task 8 — `content_shell` rebuilds `GetUserAgentMetadata` with `platform="Unknown"`, so the patched producer is **unverified end-to-end**); `navigator.plugins`/`pdfViewerEnabled` (Chrome has 5 PDF plugin entries, `content_shell` none); extension loading; `headless_shell`'s own `HeadlessChrome` token (SP2 D4 residual) |
| **B2. Stock same-revision build** | the `Object.getOwnPropertyNames(window)` diff — **non-negotiable rule 2 has never been verified**; SP2a deferred it pending a stock binary |
| **B3. Windows + macOS hosts** | fonts-ii codepoint/system fallback and native completeness (the #44 lessons); codec matrix on the target OS; packaging (A5.2) |
| **B4. Real network / STUN** | webrtc-ii public srflx address masking |
| **B5. Host that runs AudioWorklet** (headful or GPU-enabled) | audio-ii worklet input mask (design already written, unshipped blind) |
| **B6. Battery device** | battery-ii (rejected until measurable) |
| **B7. Decide SP2 D4: headless vs Xvfb vs both** | screen/fonts/pointer posture; Camoufox's answer is Xvfb (`virtual_display`), which also removes the headless-specific tells measured below (D3) |

---

## C. Decisions, not code

- **Codec distribution licensing** (SP7 D2 part 2) — building locally is
  settled; distributing H.264/AAC binaries is a legal/business call that gates
  A5 shipping anything.
- **CRLSet / Origin Trials refresh** (SP7 D5) — how bundled data ages.
- **SP7 D4 GN arg sites** — verify before writing into `build-args.gn`.
- **One client package or two** (SP6 open decision) — decide when the shared
  core is extracted, not before.
- **Pin policy** — release branch vs `main`-at-commit; rebase cadence.
- **Headless posture** (B7).

---

## D. Camoufox surfaces with no Camoucrome counterpart — triaged

Rule: a Camoufox key is not a Camoucrome task by itself. Each row carries one
label; only **gap (measure)** rows become work, and they start with a
measurement, never an implementation.

### Genuine gaps — measure first, then decide

| Camoufox | Chromium status | Task |
|---|---|---|
| `cssMedia:colorGamut`, `cssMedia:dynamicRange`, `cssMedia:prefersColorScheme` | not spoofed. All three are host/display-driven and unmeasured; `color-gamut` is OS-correlated in practice (wide-gamut displays cluster on macOS), so a headless Linux answer beside a spoofed UA is a candidate tell; `prefers-color-scheme` follows the host theme | measure `MediaValues` (sp4a already patched `media_values.cc` for `device-*`); derive from claimed OS where a derivation is defensible, key only what cannot be derived |
| `force-default-pointer` (`pointer`/`hover`/`any-pointer`) | unmeasured on `--headless=new` and under Xvfb | measure; a headless `pointer: none` beside `maxTouchPoints: 0` desktop UA is the #26-class tell |
| touchscreen coherence (`maxTouchPoints` ↔ `'ontouchstart' in window` ↔ `TouchEvent`) | `maxTouchPoints` is spoofed; TouchEvent feature detection is host-driven | measure; note the rule-2 tension (window keys must match the stock build *for the claimed device*, which a touch-capable claim changes) |
| `system-ui-font-spoofing`, CSS2 system font keywords (`caption`, `menu`, …) | `system-ui` resolves to the host's fontconfig default on Linux, not the claimed OS's UI font; a CreepJS probe | measure `LayoutTheme::SystemFont` / font cache; derive from claimed OS |
| bundled OS fonts + fontconfig | see A5.3 — the allowlist hides, it cannot add | packaging deliverable + resolve-verify |
| `showcursor` overlay | key `cursor:show` exists; the overlay was deferred in SP2b | small follow-on if a visible cursor matters for screencasts |
| `humanize` micro-tremor (`distortPoints`) | deferred by decision 2026-08-29 (smooth cubic sufficient vs basic bot detection) | revisit only against a behavioural-biometric threat model |
| addons (`addons`, uBO, `allowAddonNewtab`) | no extension support in `content_shell` | client-side `--load-extension` on the `chrome` target (A4.3, B1) |
| `certificatePaths` / `certificates` | client-side (NSS db / `--ignore-certificate-errors-spki-list`) | A4.3 |
| `webrtc:ipv4` / `webrtc:ipv6` (public srflx) | harness-gated (B4) | unchanged |

### Chromium-specific surfaces Camoufox never had — also measure (not in any spec yet)

`navigator.plugins` / `mimeTypes` / `pdfViewerEnabled` (B1); `Notification.permission`
vs `permissions.query({name:'notifications'})` mismatch under headless/automation;
`navigator.storage.estimate()` quota (derived from real disk size — a host-hardware
tell); `navigator.keyboard.getLayoutMap()` (host layout vs claimed locale);
`navigator.connection` (proxy-shaped RTT/downlink); `screen.isExtended` /
`getScreenDetails()` (sp4a left as an open audit); `matchMedia('(display-mode)')`.
Each is a measurement task: confirm the tell exists on the `chrome` target
before scoping a key.

### Covered under a different name or mechanism — no task

`headers.User-Agent`/`Accept-Language` (SP1a/SP1b) · `locale:language/region/
script/all` (`locale:tag`) · `webGl:*:blockIfNotDefined` (`kWebGl*Block`) ·
`media:spoof_codecs` (real codecs, SP7 D2 — stronger than a spoof) ·
`voices:blockIfNotDefined` (config list replaces the platform list) ·
`fonts:spacing_seed` (metric-jitter perturbs `TextMetrics`; DOM-width
enumeration is blocked by the allowlist instead) · `canvas:aaOffset/aaCapOffset`
(Firefox AA technique; `canvas:seed/noiseDensity/noiseStrength` is the Chromium
mechanism) · `screen:orientation/orientationAngle` and `screen.pixelDepth`
(derived, no key by rule) · `window.innerWidth/innerHeight`, `document.body.
client*`, `history.length`, `devicePixelRatio`, `scrollMin/Max` (launcher-layer
sizing, A4.3, decided in window-geometry) · `cross-process-storage`
(process-global config) · `trusted-automation-events` (`isTrusted` measured
correct, SP2 D3) · `debugger-invisible-to-content` (Chromium analogue measured;
resolved to the no-`Runtime.enable` driver constraint, D1) · `humanize:*`,
`cursor:show` keys exist.

### Deliberately rejected with a record — do not re-propose

Battery event synthesis; geo accuracy derivation; geo coordinate jitter for a
stationary position; fake-local-IP (`webrtc:localipv4/6`); the V8 inspector
patch; a captured variations seed. Rule 4 forbids manufacturing a slice to have
a next slice.

### Not applicable to Chromium, or headful-only

`navigator.oscpu`, `navigator.buildID` (Firefox-only) · `screen.pageX/YOffset` ·
`AudioContext:sampleRate` (kept real by the sp4-audio scope decision:
buffer-length coherence) · `allowMainWorld` / `disableWorldIsolation` /
`forceScopeAccess` / Juggler / `shadow-root-bypass` (Juggler-specific; the CDP
equivalent is the driver constraint in A4.1) · rebranding, About dialog, chrome
CSS, `disableTheming`, `no-css-animations`, `memorysaver`, search-engine
removal, addon pinning/private-mode (headful UI — SP7 §8 scopes these out) ·
`navigator.doNotTrack` / `cookieEnabled` / `onLine` / `globalPrivacyControl`
(state flags, not identity — SP1 decided; DNT/GPC are prefs the client can set)
· `[FORK]`-only modules (AccessObserver, tracking observer, Go launcher).

---

## E. Recommended order and the first slice

1. **B1 + A1** — build the `chrome` target once, then SP7. Correlation leaks
   defeat everything else, and `chrome` unblocks four other verifications for
   free.
2. **A2** — pin check, `export.sh`, registry codegen, then the rebase drill.
   Do this before the patch stack grows further; the version-honesty rule makes
   the rebase an anti-detect requirement, not hygiene.
3. **B2** — one stock build, run the `Object.getOwnPropertyNames(window)` diff.
   Cheapest way to falsify rule 2 across 25 patches at once. **content_shell
   half DONE 2026-09-10** as a by-product of the re-pin: pristine M153
   `content_shell` (`baselines/content_shell-8010-stock-ua.json`) vs the fork's
   build — window keys 235 vs 234, the delta is exactly `queryLocalFonts`
   (sp4-fonts's documented flip); `Navigator.prototype` 81 = 81. The `chrome`
   half is open (no fork-chrome window-keys capture exists yet).
4. **A3 → A4** — catalogue + Chrome WebGL profile DB + presets, then the client
   on top of them (the client has nothing to generate until A3 exists).
5. **A5** — packaging and the Windows/macOS hosts; licensing decision first.
6. **D gaps** — batch the four "measure first" rows (css media, pointer, touch,
   system-ui) as one SP4-style measurement pass on the `chrome` target; ship
   only what measures as a tell.
7. Harness-gated residuals (B3–B6) as their hosts appear.

**First slice: SP7 Task 1 — stop the field-trial testing config from being
compiled in (GN lever first, switch as fallback) and disable the variations
seed fetch**, RED-first against a feature-state probe and a network capture.
It is the spec's own top item and it is GN/config rather than Blink surgery.
Run its Gate 0 on `content_shell` first; stand up the `chrome` target (B1) as
soon as any SP7 item needs it, since that build pays for every B1 row
afterwards.

# Camoucrome follow-on roadmap (post-SP4 device-faking arc)

*Status updated 2026-09-06.*

> **Program plan, not a single implementation plan.** Each item below is its own
> slice and gets the established flow when executed: measure the WSL checkout →
> surface scope decisions (AskUserQuestion) → measurement doc + plan → SDD
> (fresh subagent per task, per-task review, whole-branch review) → secret-scan →
> push. This document orders and scopes them; it does NOT pre-write their
> implementation plans (each choke needs its own measurement first, exactly as
> every SP4 slice did).

**Goal:** Close the residual fingerprint surfaces deferred across the SP4 arc
(screen / fonts / audio / media / timezone-locale / webrtc-ip / voices / geo /
battery), plus the two standalone SPs those slices spun off (codec build-flag,
metric jitter).

**Status baseline (2026-09-06):** SP4 device-faking arc complete (9 slices shipped
`main`); `kAllKeys` now holds 82 keys. Every item here is sourced from a shipped
measurement doc's deferral section — no new surface was invented.

Six of the ten items below have since landed on `main`: **1 codec build-flag**,
**2 window-geometry**, **5 voices-ii**, **6 media-ii**, **7 metric-jitter**,
**8 audio-ii**. Three of those six are **partial** — voices-ii, media-ii and
audio-ii each shipped one slice and left a named, documented remainder. Still
open: **3 geo-ii**, **4 battery-ii**, **9 fonts-ii**, **10 webrtc-ii**, plus the
three partial remainders. Each item's `Status` cell and its `**Status:**` line
below name what landed; the residual detail lives in that slice's measurement
doc, not here.

---

## Priority table

| # | Slice | Status | Value | Effort | Risk | Layer | Depends on |
|---|---|---|---|---|---|---|---|
| 1 | **codec build-flag SP** | **shipped** 09-02 | ★★★ | S (heavy rebuild) | Low | GN / build config | — |
| 2 | **window-geometry** | **shipped** 09-02 | ★★☆ | S–M | Low | Blink core | sp4a (coherence) |
| 3 | **geo-ii** | open | ★☆☆ | S | Low | Blink core + SP5a | sp4-geo |
| 4 | **battery-ii** | open | ★☆☆ | S | Low | Blink modules | sp4-battery |
| 5 | **voices-ii** | **partial** 09-06 | ★★☆ | M | Low–Med | Blink modules | sp4-voices |
| 6 | **media-ii** | **partial** 09-05/09-06 | ★★☆ | M | Med | Blink modules (+browser) | sp4-media |
| 7 | **metric-jitter SP** | **shipped** 09-05 | ★★☆ | M | Med | Blink platform/fonts | sp3a seed (coherence) |
| 8 | **audio-ii** | **partial** 09-06 | ★★☆ | M–L | Med | Blink modules (render thread) | sp4-audio |
| 9 | **fonts-ii** | **partial** 09-06 | ★★★ | L | **High** | Blink platform/fonts | sp4-fonts |
| 10 | **webrtc-ii** | open | ★★☆ | L | **High** | libwebrtc / browser process | sp4-webrtc-ip |

Value = anti-detect impact × how commonly the surface is probed. Effort/Risk =
implementation depth + how host/platform/thread-sensitive it is.

## Recommended execution order (rationale)

Value-weighted, front-loading the quick high-value wins and staging the two
high-risk deep-surgery items last so they get dedicated focus:

*This ordering is preserved as written for the record. Waves A and C have been
executed, Wave B only in part (geo-ii and battery-ii were skipped over in favour
of voices-ii), and Wave D only its first item. See the `Status` column above for
what that leaves.*

**Wave A — highest value, lowest risk (do first):**
1. **codec build-flag SP** — the single biggest remaining tell (H.264/AAC/HEVC
   `canPlayType`/`isTypeSupported` = "not stock Chrome", probed by mainstream
   libraries, affects every session). It is a GN-args + rebuild change, not Blink
   surgery, so lowest risk despite the heavy build.
2. **window-geometry** — closes the coherence gap sp4a explicitly left (screen.*
   is spoofed but `outerWidth`/`screenX`/`innerWidth`/`document.body.clientWidth`/
   `history.length` still truthful). A getter cluster mirroring sp4a; quick.

**Wave B — low-effort residual polish (batch the small -ii's):**
3. **geo-ii**, 4. **battery-ii**, 5. **voices-ii** — small additions to
   already-built slices (accuracy derivation + jitter; event synthesis; pause/
   resume/boundary + generation token). Cheap, close named residual tells.

**Wave C — medium items:**
6. **media-ii** — post-permission label/id synthesis + the pre-permission
   phantom-webcam coherence (the sharper tell).
7. **metric-jitter SP** — its own technique (measureText/glyph jitter), coherent
   with the sp3a noise seed.

**Wave D — high-value, high-risk deep surgery (dedicated focus each):**
8. **audio-ii** — render-thread sample gating (AudioWorklet/ScriptProcessor).
9. **fonts-ii** — local() gating + codepoint/system fallback; **requires real
   Windows/macOS testing** (the #44 lessons: host- and platform-sensitive, a
   Linux-CI-only measurement proves nothing here).
10. **webrtc-ii** — fake-local-IP in the libwebrtc port allocator (browser
    process); the deepest surgery in the set.

---

## Per-slice scope

### 1. codec build-flag SP  (source: sp4-media §2.4)
- **Status: SHIPPED 2026-09-02** (`77d80ab`). `proprietary_codecs=true` and
  `ffmpeg_branding="Chrome"` are the canonical pair in `settings/build-args.gn`,
  applied and verified by `scripts/verify_sp7_codecs.py`. Not a patch — build
  configuration. Measurement: `2026-09-02-sp7-codec-buildflags.md`. The
  distribution/licensing question is recorded alongside the args and remains a
  packaging decision, not a build one.
- **Surface:** `HTMLMediaElement.canPlayType`, `MediaSource.isTypeSupported`,
  `MediaCapabilities.decodingInfo` — currently the Chromium-branding matrix
  (H.264/AAC/HEVC/Theora = `""`; real Chrome = `"probably"`), measured in
  sp4-media §2.2.
- **Fix:** GN args `proprietary_codecs=true ffmpeg_branding="Chrome"` (+ verify
  no license/`enable_platform_hevc` etc. gaps), then a full proprietary rebuild
  so the decoders genuinely exist — the matrix matches Chrome because the codecs
  are real, NOT a Blink lie (a lie diverges on actual playback → worse tell).
- **Not Blink; not a patch.** Touches `assets/base.mozconfig`-equivalent GN
  config / `multibuild.py` args. Verify by re-running the sp4-media codec probe:
  H.264/AAC → `"probably"`, MSE `isTypeSupported` → true, AND an actual `<video>`
  H.264 load succeeds (functional coherence).
- **Risk:** low (config), but confirm licensing posture and that the fork's
  distribution intent permits proprietary codecs. Heavy build (~cold 40 min).

### 2. window-geometry  (source: sp4a "Deferred to the window-geometry slice")
- **Status: SHIPPED 2026-09-02** (`fde4087`, `patches/window-geometry.patch`,
  verified W1–W7 by `scripts/verify_window_geometry.py`). Config-driven
  `window.outerWidth/outerHeight/screenX/screenY` — `screenLeft/screenTop` come
  along with `screenX/screenY`. The scope decisions taken: `innerWidth` /
  `clientWidth` / `devicePixelRatio` stay real (launcher-layer sizing),
  `history.length` stays truthful, and `getScreenDetails`/`isExtended` remain an
  open audit. Measurement: `2026-09-02-window-geometry-surfaces.md` §5.
- **Surface:** `window.outerWidth/outerHeight`, `window.screenX/screenY`
  (`screenLeft/screenTop`), `window.innerWidth/innerHeight`, `screen.availLeft/
  availTop` window-relative uses, and the low-entropy tail `document.body.clientWidth`
  / `history.length` noted in sp4a.
- **Choke:** `LocalDOMWindow`/`DOMWindow` geometry getters + `Screen` avail
  (sp4a touched `Screen::GetRect`; the window getters are separate). Config-drive
  from a `window:` namespace, coherent with the sp4a `screen.*` values (the
  window must fit inside the spoofed monitor).
- **Scope decision to surface:** how much of the window cluster + whether to tie
  outer/inner to the spoofed screen automatically. Effort S–M (getter cluster).

### 3. geo-ii  (source: sp4-geo §3/§4)
- **Accuracy decimal-precision derivation** (Camoufox-style: derive accuracy from
  the coordinate decimal places when `geolocation:accuracy` absent, instead of
  the fixed 100 m default).
- **Positional jitter** between `watchPosition` callbacks (real fixes drift; ours
  is byte-identical). Small per-callback delta from a seed.
- **Out-of-range config validation** — **SHIPPED 2026-09-06** as SP5b
  (`d9e8d51`, `additions/camoucfg/domain_validator.{h,cc}`, verified by
  `scripts/verify_sp5b_domain.py`; measurement
  `2026-09-06-sp5b-domain-validator.md`). Landed as a *generalized* single-key
  domain validator (a separate table + file, not the SP5a relational registry),
  populated so far with the geo range-checks only — an entry earns its place by
  mirroring a real downstream rejection (`ValidateGeoposition`), so the
  mechanism is generic but the table is geo-only until another such rejection is
  found. A mistyped `latitude=91` now logs loudly and refuses startup under
  `CAMOU_CONFIG_STRICT=1` instead of silently timing out. The other two geo-ii
  bullets above remain open.

### 4. battery-ii  (source: sp4-battery §4)
- **Event synthesis/timing:** `onchargingchange`/`onlevelchange` are not fired
  (static). Synthesize plausible transitions (e.g. slow `level` drift on
  discharge) from config so a probe watching over time sees realistic updates.
- **Choke:** `battery_manager.cc` `DidUpdateData`/the property update path.
  Effort S; low value (deprecated API).

### 5. voices-ii  (source: sp4-voices §4)
- **Status: PARTIAL, shipped 2026-09-06** (`a7316c6`, `patches/voices-ii.patch`,
  verified by `scripts/verify_voices_ii.py`). Landed: word `boundary` events on a
  fake voice, seeded jitter on the linear `end` timing, and the per-speak
  generation token that fixes the stale-timer early-`end` on utterance reuse.
  **Still open** (measurement `2026-09-06-voices-ii-surfaces.md` §4):
  `pause()`/`resume()` plus `speechSynthesis.paused` (needs a paused-state getter
  intercept and end/boundary timer save-restore — its own follow-on), the
  default-voice path, and voice-lang ↔ locale coherence (operator/preset
  responsibility).
- **pause()/resume()/boundary events** on a fake voice (currently go to the
  backend-less mojo and no-op → divergence from real Chrome).
- **Linear-`end`-timing jitter** — `end` fires at exactly `len/(cps·rate)`; add a
  small seeded jitter so the timing isn't a deterministic-formula tell.
- **Utterance-reuse generation token** — the stale-timer early-`end` when a page
  cancels then re-speaks the SAME utterance object (needs a per-speak generation
  id the delayed task checks).
- **default-voice path** — an utterance with `voice` unset takes the real path;
  decide whether to route it through the fake completion too. Effort M.

### 6. media-ii  (source: sp4-media §1.5/§1.5b)
- **Status: PARTIAL, shipped in two slices.** Slice 1, 2026-09-05 (`54eaba9`,
  `5a48835`, `7a45194`; `patches/media-ii-track.patch`; M1–M11): grant-aware
  synthesis of `deviceId`/`groupId`/`label` made consistent across
  `enumerateDevices` and `MediaStreamTrack.getSettings()`/`getCapabilities()`,
  via a `SyntheticDeviceId` helper folding seed + origin. Slice 2, 2026-09-06
  (`292a2bb`; `patches/phantom-webcam.patch`; P1–P6): a configured phantom webcam
  on a camera-less host now remaps `getUserMedia`'s `NO_HARDWARE` to
  `NotReadableError`, so the rejection no longer contradicts the enumerated count.
  **Still open (Slice 2b)** — measurements `2026-09-05-media-ii-getsettings-surfaces.md`
  §7/§7b and `2026-09-06-phantom-webcam-surfaces.md` §5: a phantom track that
  actually opens (browser-process work), pre-grant-N vs post-grant-M count
  coherence, `applyConstraints({deviceId: <synthetic>})` reverse-mapping,
  `InputDeviceInfo.getCapabilities()` returning `{}` on the enumerate side, and
  `selectAudioOutput()` / `ondevicechange`. Two operator notes carried out of
  Slice 1: set the configured counts ≈ real, and always set a non-zero
  `mediaDevices:seed` when `mediaDevices:enabled`.
- **Post-permission label/id synthesis:** `enumerateDevices` emits empty fields
  post-grant; `MediaStreamTrack.getSettings()/getCapabilities()` leak the REAL
  salted deviceId/groupId/label (the enumerate-vs-track incoherence the spoof
  *introduces*). Synthesize stable fake ids + labels, consistently across both.
- **Pre-permission phantom-webcam coherence** — a configured `webcams=1` on a
  camera-less host makes `getUserMedia({video:true})` reject while enumerate says
  a camera exists. Reconcile the count with getUserMedia success.
- **selectAudioOutput() / ondevicechange** — ungated real-device surfaces.
- Some of this reaches the browser-process device dispatcher. Effort M.

### 7. metric-jitter SP  (source: sp4-fonts deferral)
- **Status: SHIPPED 2026-09-05** (`67e7f81`, `6ea7d01`;
  `patches/metric-jitter.patch`; verified J1–J11 by
  `scripts/verify_metric_jitter.py`). Grid-preserving jitter on `width` and the
  `actualBoundingBox*` / `fontBoundingBox*` / baseline members, perturbing the
  source values rather than the derived ones, and reusing `canvas:seed` — no new
  config key. Deferred: the `emHeight*` and `getActualBoundingBox` /
  `getSelectionRects` / `getTextClusters` surfaces, all gated off by
  `RuntimeEnabled=ExtendedTextMetrics` in this build. **Rebase checklist item:**
  `MirroredBaseline` must be re-diffed against `GetFontBaseline` on every Chromium
  rebase — J11 runs on Linux and exercises only the fallback baseline branches, so
  an upstream formula change would desync the mirror silently. Measurement:
  `2026-09-05-metric-jitter-surfaces.md` §5/§6.
- **Surface:** `measureText().width` (+ `TextMetrics` extended box), glyph
  advance metrics — a canvas-adjacent, high-value font fingerprint distinct from
  the enumeration sp4-fonts blocked.
- **Design:** per-(font,string) deterministic sub-pixel width jitter, folded into
  the same seed discipline as the sp3a canvas noise (reread-stable). Its own SP
  because it is a *technique* (metric perturbation), not a getter override.
- **Choke:** the text-measurement path in `platform/fonts` / `core` layout.
  Effort M; risk med (coherence with rendered layout — jitter measurement without
  breaking actual text layout).

### 8. audio-ii  (source: sp4-audio residual §)
- **Status: PARTIAL, shipped 2026-09-06** (`4627ccd`, `patches/audio-ii.patch`,
  verified S1–S4 by `scripts/verify_audio_ii.py`). Landed: the ScriptProcessorNode
  input mask, which closes the render-thread path that bypassed sp4-audio's
  readback noise. **Deliberately not shipped:** the AudioWorklet input mask. The
  tell is structurally certain but unexercisable on this verify host, and shipping
  blind code that mutates the audio render thread every quantum would be an
  unverifiable spoof — the design is written out in
  `2026-09-06-audio-ii-surfaces.md` §5 (perturb the JS-facing copy in
  `CopyPortToArrayBuffers`, single string-literal domain to avoid a worklet-thread
  alloc, content-keyed never call-keyed) and waits on a harness that runs
  AudioWorklet. Also deferred: `DynamicsCompressorNode.reduction`.
- **AudioWorklet `process()` raw input + ScriptProcessorNode `onaudioprocess`** —
  render-thread sample access that bypasses the sp4-audio readback noise (a
  detector reading raw render-thread samples sees un-noised audio).
- **DynamicsCompressor.reduction** — an un-gated scalar readback.
- **Choke:** the render-thread audio buffers (real-time thread). **Its own slice
  because render-thread gating is thread-safety-sensitive** (the noise must be
  applied without violating the audio callback's real-time constraints).
  Effort M–L; risk med.

### 9. fonts-ii  (source: sp4-fonts whole-branch review)
- **local() src gating** — **PARTIAL, shipped 2026-09-06**
  (`patches/fonts-ii.patch`, verified by `scripts/verify_fonts_ii.py`;
  measurement `2026-09-06-fonts-ii-local-surfaces.md`). The real gate point is
  `LocalFontFaceSource::CreateFontData` / `IsLocalFontAvailable` (which call
  `FontCache::GetFontData` directly, upstream of the sp4-fonts `FontFallbackList`
  gate), not `SetStatus`. Gated on `fonts:list`, closing the mainstream
  `local("Family")` cross-method inconsistency (direct `absent` vs `local()`
  `present`), verified on Linux with a host-present font (DejaVu Sans) via
  `FontFace.status`. **Residuals:** `local("PostScript name")` of a *listed* font
  is over-blocked (family allowlist can't match a PS name — the #44 name path,
  measured by F-PSNAME); the `IsLoading()==true` async-lookup branch of gate 2 is
  defensive-by-reasoning, unexercised on the sync-lookup verify host; and native
  Win/mac completeness still needs the cross-platform harness below.
- **Codepoint / system fallback** — `SystemFindFontForChar` / `GlobalFontFallback`
  / `CommonFontFallback`, plus `LookupLocalFont`/`LookupInFaceNameLists` (matched
  by full/PostScript name), none gated by sp4-fonts.
- **CRITICAL constraint (the #44 lessons):** these paths are **host- and
  platform-sensitive**; a Linux-CI-only measurement proves nothing. This slice
  needs a real Windows and macOS test harness before any completeness claim.
  Effort L; risk HIGH. Do not start without the cross-platform test story.

### 10. webrtc-ii  (source: sp4-webrtc-ip §5)
- **Fake-local-IP** — rewrite host ICE candidate IPs to a configured plausible
  LAN IP (`webrtc:localipv4/localipv6`), stealthier than the current policy's
  empty-candidate-set (itself an anomaly). Requires libwebrtc port-allocator /
  mDNS-responder surgery in the browser/network process.
- **Force-mDNS-always-on** — close the media-permission local-IP leak
  unconditionally (a different lever from the ip-handling policy).
- **Choke:** `BasicPortAllocatorSession` / `MdnsResponderAdapter` (browser
  process, `third_party/webrtc` + `//content`). Effort L; risk HIGH (deepest
  surgery in the set; not a Blink patch).

---

## Cross-cutting notes

- **Two are NOT Blink patches:** codec (GN build config) and webrtc-ii (libwebrtc
  / browser process). They break the "one Blink patch per slice" rhythm — plan
  their build/test loops accordingly.
- **Two need out-of-Linux testing:** fonts-ii (host/platform-sensitive) and the
  codec build (verify the proprietary matrix on the actual target OS builds).
- **Coherence dependencies:** window-geometry ↔ sp4a screen; metric-jitter ↔ sp3a
  seed; geo-ii jitter ↔ the geo synth; media-ii ids must be stable+coherent
  across enumerate and track. Each slice's scope question should surface the tie.
- **SP5a coherence-validator additions:** geo range-checks (geo-ii) and any new
  numeric-range keys should extend the validator so a mistyped config fails loud
  rather than silently disabling a spoof.
- **Build harness:** all Blink items use the WSL checkout over the SSH master.
  Recommend setting up an SSH key + disabling password auth before a long
  multi-slice run to avoid the recurring password-auth lockouts (the master has
  been stable recently but the risk stands over a 10-slice program).

---

## Execution note

This roadmap is the ordering/scoping layer. Six items have landed (see the
`Status` column); what remains is **geo-ii** and **battery-ii** (both small, both
still unstarted), the three partial remainders (voices-ii `pause()`/`resume()`,
media-ii Slice 2b, the audio-ii AudioWorklet mask — that last one blocked on a
harness, not on effort), and the two high-risk deep-surgery items **fonts-ii** and
**webrtc-ii**, neither of which should start without its out-of-Linux test story.
Each still gets measurement doc → plan → SDD as usual. Do not batch-execute the
remainder autonomously; each carries its own scope decision the operator should
see.

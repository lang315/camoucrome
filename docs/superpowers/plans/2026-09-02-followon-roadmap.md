# Camoucrome follow-on roadmap (post-SP4 device-faking arc)

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

**Status baseline:** SP4 device-faking arc complete (keys 45→74; 9 slices shipped
`main`). Every item here is sourced from a shipped measurement doc's deferral
section — no new surface was invented.

---

## Priority table

| # | Slice | Value | Effort | Risk | Layer | Depends on |
|---|---|---|---|---|---|---|
| 1 | **codec build-flag SP** | ★★★ | S (heavy rebuild) | Low | GN / build config | — |
| 2 | **window-geometry** | ★★☆ | S–M | Low | Blink core | sp4a (coherence) |
| 3 | **geo-ii** | ★☆☆ | S | Low | Blink core + SP5a | sp4-geo |
| 4 | **battery-ii** | ★☆☆ | S | Low | Blink modules | sp4-battery |
| 5 | **voices-ii** | ★★☆ | M | Low–Med | Blink modules | sp4-voices |
| 6 | **media-ii** | ★★☆ | M | Med | Blink modules (+browser) | sp4-media |
| 7 | **metric-jitter SP** | ★★☆ | M | Med | Blink platform/fonts | sp3a seed (coherence) |
| 8 | **audio-ii** | ★★☆ | M–L | Med | Blink modules (render thread) | sp4-audio |
| 9 | **fonts-ii** | ★★★ | L | **High** | Blink platform/fonts | sp4-fonts |
| 10 | **webrtc-ii** | ★★☆ | L | **High** | libwebrtc / browser process | sp4-webrtc-ip |

Value = anti-detect impact × how commonly the surface is probed. Effort/Risk =
implementation depth + how host/platform/thread-sensitive it is.

## Recommended execution order (rationale)

Value-weighted, front-loading the quick high-value wins and staging the two
high-risk deep-surgery items last so they get dedicated focus:

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
- **Out-of-range config validation** — range-check `geolocation:latitude/longitude/
  accuracy` in the SP5a coherence validator (currently a mistyped `latitude=91`
  silently times out). Effort S.

### 4. battery-ii  (source: sp4-battery §4)
- **Event synthesis/timing:** `onchargingchange`/`onlevelchange` are not fired
  (static). Synthesize plausible transitions (e.g. slow `level` drift on
  discharge) from config so a probe watching over time sees realistic updates.
- **Choke:** `battery_manager.cc` `DidUpdateData`/the property update path.
  Effort S; low value (deprecated API).

### 5. voices-ii  (source: sp4-voices §4)
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
- **AudioWorklet `process()` raw input + ScriptProcessorNode `onaudioprocess`** —
  render-thread sample access that bypasses the sp4-audio readback noise (a
  detector reading raw render-thread samples sees un-noised audio).
- **DynamicsCompressor.reduction** — an un-gated scalar readback.
- **Choke:** the render-thread audio buffers (real-time thread). **Its own slice
  because render-thread gating is thread-safety-sensitive** (the noise must be
  applied without violating the audio callback's real-time constraints).
  Effort M–L; risk med.

### 9. fonts-ii  (source: sp4-fonts whole-branch review)
- **local() src gating** — `@font-face { src: local(X) }` reaches `SetStatus` via
  `FontFaceSet::InsertRuleFontFace`, un-gated; on native Win/mac the host font
  superset leaks (host-present fonts read as present even when the whitelist would
  hide them) — the direct-vs-local() cross-method inconsistency = a real
  anti-detect signature.
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

This roadmap is the ordering/scoping layer. To execute: take Wave A item 1
(codec build-flag SP) first — it is the highest-value, lowest-risk, and
independent — measure the GN/build path, surface the licensing/scope decision,
then measurement doc → plan → SDD as usual. Do not batch-execute all ten
autonomously; each carries its own scope decision the operator should see.

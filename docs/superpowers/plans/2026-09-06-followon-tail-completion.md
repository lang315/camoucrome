# Follow-on tail completion (subagent-driven)

Date: 2026-09-06. Directive: execute the four remaining follow-on directions, in
order, via the superpowers subagent-driven-development workflow. Box constraint:
one `out/Default`, so build+verify+round-trip are **serial** under the controller;
review is a fresh subagent per task, plus a final whole-branch review.

Global constraints (bind every task):
- All spoofing C++/Blink, never injected JS. Accessors stay `[native code]`;
  `Object.keys(window)` unchanged; worker parity for any surface on both.
- SP0 hook pattern: real value first, config override only when key present,
  no-op when absent, applied AFTER any `probe::Apply*` hook.
- Coherence over coverage (rule 4). A derived value gets NO new key.
- RED-first: every verify goes red against the pre-change binary; assert the
  expected value/count, not exit 0. Confirm NON-ZERO build steps.
- Patch round-trip for any `patches/` (existing-file) change; pure `additions/`
  needs none. Secret-scan before every commit; user drives pushes.

## Task 1 — geo-ii accuracy-derivation  — REJECTED 2026-09-06

Built, verified GREEN (RED-first, 5/5), reviewed, and **reverted**: the review +
advisor showed it is net-negative. Real `coords.accuracy` is method-based (Wi-Fi
~20-150 m), not derived from coordinate decimals; a flat 100 m is Wi-Fi-plausible
and the derived values (`11.132`, or a GPS-implying `1 m` floor on the dominant
Maps-paste input) are the tell — rule 4 forbids the trade. A measured dead-end,
like audio-ii's AudioWorklet and fonts-ii's PS-name path. The real geo-ii lever is
positional/accuracy JITTER across `watchPosition` readings (method-based drift),
left as a future slice. Original spec kept below for the record.

Derive `geolocation:accuracy` from coordinate decimal precision when the accuracy
key is ABSENT, instead of the fixed 100 m default (cm-precision coords next to a
round 100 m accuracy is incoherent). No new key — accuracy already has one; this
is the fallback when it is unset. Patches `sp4-geo` territory
(`core/geolocation/geolocation.cc`), so a round-trip.

- RED: config lat/long with many decimals, accuracy absent → current binary
  reports accuracy 100. GREEN: reports the derived (smaller) accuracy.
- Guard: accuracy PRESENT in config still wins (override beats derivation);
  accuracy absent AND coords absent → no synthesis (rule 5).
- Verify extends `scripts/verify_sp4_geo.py` pattern over echo_server.

## Task 2 — voices-ii pause/resume

`speechSynthesis.pause()/resume()` are no-ops on the fake-completion path
(`speech_synthesis.cc`, the file voices-ii already patches). A page that pauses
speech and still sees `boundary`/`end` fire on the original schedule is a tell.
Make pause freeze the fake timeline and resume continue it. Patches `voices-ii`
territory → round-trip; extract with `git diff $BASE` to exclude voices-ii hunks.

- Feasibility gate FIRST: confirm the fake path + pause/resume are observable on
  content_shell (SpeechSynthesis works on about:blank).
- RED: speak, `pause()` at T → events keep firing past T. GREEN: events stop at
  pause, resume after `resume()` shifted by the paused span.
- Guard: no double-fire, generation token still holds across pause/resume.

## Task 3 — webrtc-ii (feasibility + scope gate, then implement)  — SHIPPED 2026-09-06

**Outcome:** shipped as `patches/webrtc-ii.patch` (commit 7b3f992). The "deepest
surgery / libwebrtc" prediction below was WRONG: Gate 0 traced the media-permission
mDNS bypass to a SINGLE Blink `platform/p2p` conditional,
`FilteringNetworkManager::GetMdnsResponder()` — no libwebrtc, no browser-process
change. New bool key `webrtc:hideLocalIps` forces the mDNS responder on
unconditionally (overriding both the `ENUMERATION_ALLOWED` media-permission bypass
and the enterprise `!allow_mdns_obfuscation_` bypass), so host candidates emit
`.local` even under permission. Verify RED→GREEN: 2 raw / 0 `.local` → 0 raw / 2
`.local`. Review APPROVE, coherence net-positive. Residual: public srflx leak
harness-unverifiable; `.local`-under-permission is a mild shape tell; the coherent
fake-LAN-IP (`webrtc:localipv4`) stays deferred. See
[measurement](../measurements/2026-09-06-webrtc-ii-force-mdns.md).

Highest value (local-IP leak = deanonymization) but the deepest surgery:
`BasicPortAllocatorSession` / `MdnsResponderAdapter` in `third_party/webrtc` +
`//content` browser-process — no patch has touched libwebrtc before.

- **Gate 0 (blocking):** can a headless WSL content_shell even observe host ICE
  candidates via `RTCPeerConnection` (a data channel triggers gathering)? If the
  surface is unobservable here, STOP and record it as needing a real-network
  harness — do not grind libwebrtc blind.
- If observable: scope to the smallest verifiable lever (force-mDNS-always-on, or
  host-candidate IP rewrite from `webrtc:localipv4/localipv6`), decide the patch
  layer, feasibility-probe, then implement RED-first. This task may span multiple
  build cycles; treat its scope as its own decision once Gate 0 is known.

## Task 4 — consolidate  — 2026-09-06

- **DEPS gap was far bigger than one line.** Whole-renderer `checkdeps` found ~22
  latent violations (never surfaced — `.cc`-only builds skip checkdeps), because
  the renderer-wide grant list in `sp0-config-layer.patch`'s `renderer/DEPS`
  section only ever carried `blink_scope.h` + `mask_config.h`; every later slice's
  header (`keys.h` ×18, `canvas_noise.h`, `gl_params.h`, `audio_noise.h`,
  `device_ids.h`, `base/no_destructor.h`) was a live edit on the box that was
  NEVER captured into any patch. A clean `apply.sh` reconstruction would have
  produced a tree that fails checkdeps/presubmit. FIXED renderer-wide: all 7
  camoucfg headers + `base/no_destructor.h` added to the sp0 `renderer/DEPS`
  section (machine section-swap into `sp0-config-layer.patch`, `a`-index
  `d5142fdb5a` = true pristine, verified applies clean → 7+1 grants). Whole-renderer
  `checkdeps` now SUCCESS. This makes `webrtc-ii`'s per-dir `platform/p2p/DEPS`
  grant redundant → dropped, `webrtc-ii.patch` is now `.cc`-only. (`fonts`'
  per-dir grant left as harmless redundancy.)
- **Full from-scratch PRISTINE reconstruction deferred.** The box
  `/home/lang/chromium/src` is a hybrid (early slices committed at HEAD `a727b57805`
  + later slices as live edits), not a pristine Chromium checkout; a true
  from-scratch `apply.sh` run needs a fresh `gclient` checkout (hours + ~100GB),
  out of this session's reach. Achieved instead: both CHANGED patches
  (`sp0-config-layer` DEPS section, `webrtc-ii` `.cc`) verified apply cleanly to
  pristine; whole-renderer `checkdeps` SUCCESS; `gn check` OK. Task 4's changes are
  non-behavioral (DEPS = build-hygiene only; the `webrtc-ii` `.cc` is byte-identical),
  so no spoof regression is possible — `verify_webrtc_ii.py` re-run GREEN as a smoke
  check. The remaining gap is purely "does the whole patch stack apply+build from
  true zero," which only a fresh checkout can prove.
- README / roadmap / ledger reconciled; `.memsearch/` gitignored.

## Order & review

1 → 2 → 3 → 4. Each: measure RED → implement → **review subagent** → fix →
secret-scan → present for push. Final: whole-branch review subagent across the
tail before calling it done. Progress tracked in `.superpowers/sdd/progress.md`.

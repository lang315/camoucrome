# Windows behaviour II Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `AudioContext.sampleRate` follows the claimed host (48000) coherently through the audio service; voices measured on a Mac (191) close the macOS claim's silence; a measured Windows non-`en-US` row if the host can take a speech pack.

**Architecture:** one patch stem `windows-behaviour-ii` (`media/audio/audio_manager_base.{cc,h}` + `media/audio/{BUILD.gn,DEPS}`), key `audio:sampleRate` (89th), `settings/audio.json`, `settings/voices.json` macOS list, generator + tests, rows A1–A3 / V3 in `verify_windows_behaviour.py`, `audio.sampleRate` leaves the oracle's `KNOWN`.

**Tech Stack:** Chromium 153 pin, camoucfg getters (browser/audio-service process), patchright client, stock Chrome on this Mac and on the Windows host.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-09-12-windows-behaviour-ii-design.md`.
- Binary under test: `out/Default/chrome`.
- The host is left as found: any speech pack installed for a capture is removed after it.
- Export, never hand-extract.

---

### Task 1: measurements and data (Mac, host)

- [x] `scripts/capture_voices.py --where mac`: 191 voices, `sampleRate` 48000, `baseLatency` 0.00533 → `settings/voices.json` (`macOS` flat list, `measured` += macOS), `settings/audio.json` (macOS row).
- [x] `settings/audio.json` Windows row from the headed oracle baseline (48000, `baseLatency` 0.01).
- [x] Windows fr-FR: `Add-WindowsCapability Language.Speech~~~fr-FR` over ssh → "Access is denied" (0x80070005, admin but not elevated); an elevated scheduled task → the same denial. Task and result file removed; the row stays quoted.

### Task 2: key, generator, tests (Mac)

- [x] `kAudioSampleRate` / `audio:sampleRate` (int32) in `settings/keys.json`; `gen_keys.py` (89 keys); `declared` set.
- [x] `gen.audio_keys(platform)` from `audio.json`; `from_pool` emits it; `voices_keys` returns the flat macOS list regardless of locale.
- [x] `test_mac_voices_are_the_measured_list_and_sample_rate_follows_the_claim`; pytest green; `gen_keys.py --check` PASS.

### Task 3: the audio-service hook (box)

**Files (patch `windows-behaviour-ii`):** `media/audio/audio_manager_base.cc`, `media/audio/audio_manager_base.h`, `media/audio/BUILD.gn`, `media/audio/DEPS`.

- [x] `AudioManagerBase::GetOutputStreamParameters` returns `CamouOutputParameters(GetPreferredOutputStreamParameters(...))`; the static helper reads `kAudioSampleRate`, clamps 8000–192000, `set_sample_rate` when present and the params are valid.
- [x] `media/audio/DEPS` (`+components/camoucfg`), `media/audio/BUILD.gn` (`//components/camoucfg` in the `audio` target deps).
- [x] `autoninja -C out/Default chrome components_unittests` (non-zero steps); `gn check out/Default //media/audio:audio`; `checkdeps.py media/audio`.

### Task 4: verify (RED first)

- [x] Rows A1–A3, V3 in `verify_windows_behaviour.py`; A1's RED is the box's real 44100 under the Windows claim before the hook (the oracle's KNOWN line). 11/11 (the generator verify first hit E2BIG on macOS identities: both launchers now chunk `CAMOU_CONFIG_1..N`, the probe takes `--config @file`; 15/15 after).
- [x] `verify_host_oracle.py` with `audio.sampleRate` removed from `KNOWN`: 4/4, O1 now measures the rate. `verify_sp4_audio.py`, `verify_sp4_voices.py` 5/5, `verify_sp6b_generator.py` N=3, `CamoucfgKeysTest` (89).

### Task 5: export, docs, ninth cut

- [x] Commit on the box (`windows-behaviour-ii`), `export.sh`, gate empty, sync, `check_additions_build.py`.
- [x] Docs: measurement `2026-09-12-windows-behaviour-ii.md`; windows-oracle doc residual line closed; sp4-audio doc superseded note; roadmap row 8d; keys count in CLAUDE.md if named; ledger.
- [x] Release relink, `pkg9_job.sh`, `post_pkg.sh`; oracle 4/4 + behaviour 11/11 on the archived chrome; packaging doc ninth cut; commit, push, CI.

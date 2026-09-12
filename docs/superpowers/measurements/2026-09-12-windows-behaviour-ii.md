# Windows behaviour II — audio rate, measured voices — measurements

Slice `windows-behaviour-ii`, 2026-09-12. Spec
`specs/2026-09-12-windows-behaviour-ii-design.md`, plan
`plans/2026-09-12-windows-behaviour-ii.md`. Binary under test: the box's
`out/Default/chrome` through the patchright client.

## 1. `AudioContext.sampleRate` follows the claim, one layer down

sp4-audio left the rate alone because a Blink-only value desyncs from the
buffer lengths the audio service hands the renderer. The value is now set
where the renderer gets it: `AudioManagerBase::GetOutputStreamParameters`
(media/audio) passes its result through `CamouOutputParameters`, which
replaces the sample rate with **`audio:sampleRate`** (89th key, int32,
clamped 8000–192000) when present. The stream the renderer then opens at
that rate is bridged to the device's own rate by Chromium's
`AudioOutputResampler`, the stock path for any page asking for a rate the
device lacks. `media/audio` gained the `//components/camoucfg` dep and DEPS
grant (`gn check //media/audio:audio` OK, `checkdeps media/audio` SUCCESS).
Absent → the device's real rate (rule 5).

Data: `settings/audio.json`. Windows 48000 / `baseLatency` 0.01 from the
headed oracle baseline on the host; macOS 48000 / 0.00533 (256 frames)
measured on this Mac's stock Chrome 151 (`capture_voices.py --where mac`).
The generator emits the claimed host's rate; Linux gets no key.

| measurement (box, `out/Default/chrome`) | rate | baseLatency | frames |
|---|---|---|---|
| Windows claim (`audio:sampleRate` 48000) | 48000 | 0.010667 | 512 |
| key absent | 44100 (WSLg PulseAudio) | 0.011610 | 512 |
| Linux claim (no key) | 44100 | 0.011610 | 512 |

`baseLatency` = frames / rate in every row: the buffer count is the
device's, the rate is the claim's, nothing contradicts. The context reaches
`running` after `resume()` in a gesture and an `OfflineAudioContext`
oscillator render peaks at 1.0 (non-silent). The host's 480-frame
`baseLatency` 0.01 vs the box's 512 frames is the one remaining
difference, shape-only in the oracle (`audio.baseLatency`).

## 2. Voices measured

- **macOS: 191 voices** on this Mac (15.7.4, Chrome 151), Samantha
  default, `voiceURI == name`, `localService` true; macOS ships every
  language's voices at once, so `voices.json` carries one flat `macOS`
  list and `voices_keys("macOS", locale)` ignores the locale. A macOS
  claim on the box went from 0 voices (manufactured silence) to 191.
- **Windows fr-FR: not measured.** `Add-WindowsCapability
  Language.Speech~~~fr-FR` over ssh → "Access is denied" 0x80070005 (the
  session's admin token is not elevated); a `RunLevel Highest` scheduled
  task → the same denial. Task and result file removed, host as found; the
  `fr-FR` row stays quoted (Appendix A + the OneCore token list).
  `capture_voices.py --where winhost --locale fr-FR` is ready for an
  elevated console.

## 3. Rows

| row (`verify_windows_behaviour.py`, 2026-09-12) | result |
|---|---|
| S1, S1b, S2, S3, S4, V1, V2 (windows-behaviour, unchanged) | PASS |
| A1 Windows claim: `sampleRate` 48000, `baseLatency`×rate = 512 (integer), state `running`, offline render peak 1.0. **RED: 44100 before the hook** (the oracle's former KNOWN line) | PASS |
| A2 key absent: 44100, the device's real rate — the hook is config-gated | PASS |
| A3 Linux claim: 44100, equal to A2 | PASS |
| V3 macOS claim: 191 voices, Samantha default | PASS |
| **11 PASS 0 FAIL** | |
| `verify_host_oracle.py` with `audio.sampleRate` removed from `KNOWN`: O1 **0 DIFF, 229 same leaves**; O2–O4 | 4/4 |
| `verify_sp4_audio.py` | ALL_PASS |
| `verify_sp6b_generator.py` N=3 — **first run 12/15: every macOS identity failed with `spawn E2BIG`.** A macOS identity is now 138 KB (191 voices + 409 faces + 775 names) and both launchers put the whole config in one `CAMOU_CONFIG` string, past Linux's 128 KiB per-string cap (`MAX_ARG_STRLEN`). Fixed in both clients: a config over 30000 chars goes out as `CAMOU_CONFIG_1..N` (the reader `AssembleRawConfig` concatenates; numbered chunks win); the probe also takes `--config @file`. Contract `launcher.json` `env.config_chunks`. Re-run | 15/15 |
| `CamoucfgKeysTest` (89 keys), `gen_keys.py --check`, `check_additions_build.py`, client tests 28 | PASS |

Build: `out/Default` 193 steps, 1 m 45 s. Box tip `2b2173c602
windows-behaviour-ii`; export gate: the new patch (4 paths: `.cc`, `.h`,
`BUILD.gn`, `DEPS`) plus the intended data edits; 36 commits.

## 4. Residuals, named

- `baseLatency`: the host reports 480 frames (0.01 s), the box 512
  (0.01067 s). Frame count is the device's; a `audio:bufferFrames` key would
  close it, not done (shape-only leaf, no page-visible contradiction).
- Windows voices rows other than `en-US` remain quoted (§2).
- The macOS voices list is one Mac's (15.7.4, Chrome 151); Chrome 153 on a
  Mac was not available.
- The chunk size (30000 chars ≤ 120 KB UTF-8) is the clients' choice; the
  reader accepts any count. A Windows identity (37 KB) still goes out as one
  `CAMOU_CONFIG`; only macOS identities chunk today.

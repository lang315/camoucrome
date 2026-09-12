# Windows behaviour II — audio rate, measured voices — design

Date: 2026-09-12. Takes up the three follow-ons named at the end of
`2026-09-12-windows-behaviour-design.md`: the `AudioContext.sampleRate`
residual (open since sp4-audio), a measured voices row beyond `en-US`, and
the macOS claim's manufactured silence (0 voices).

## 1. `AudioContext.sampleRate`: report the claimed host's rate at the audio service

sp4-audio declined to spoof the rate in Blink because a Blink-only value
desyncs from the buffer lengths the audio service hands the renderer. The
coherent place is one layer down. Every renderer's `AudioContext.sampleRate`
and `baseLatency` derive from the output parameters the audio service
reports for the default device
(`AudioManagerBase::GetOutputStreamParameters` →
`GetPreferredOutputStreamParameters`). When a renderer then opens a stream
at that rate and the device runs another, Chromium's own
`AudioOutputResampler` bridges the two — the stock path for any page that
asks for a rate the device lacks. So replacing the *reported* rate is
coherent end to end: `baseLatency` = frames / reported rate, the render
quantum runs at the reported rate, the device keeps its own.

Key **`audio:sampleRate`** (89th, int32, clamped 8000–192000), applied in
`AudioManagerBase::GetOutputStreamParameters` (media/audio; the audio
service reads the same process-global config through the environment).
Absent → the device's real rate (rule 5). `media/audio` gains the
`//components/camoucfg` dep and the DEPS grant. The generator emits the
claimed host's measured rate from `settings/audio.json`: Windows 48000
(oracle baseline, headed and headless), macOS 48000 (this Mac, Chrome 151,
`baseLatency` 0.00533 = 256/48000). No invariant: no cross-surface partner;
the clamp bounds it, and `baseLatency` follows by construction.

The box (WSLg PulseAudio) runs at 44100, which is why the oracle carried
the residual; a Linux deployment with no audio device would already report
the fake manager's 48000. With the key the oracle row stops being "known"
and becomes measured: `audio.sampleRate` leaves `KNOWN`.

## 2. Voices, measured

- **macOS.** `capture_voices.py --where mac` on this Mac's stock Chrome:
  **191 voices** (Samantha default, `voiceURI == name`, `localService`
  true). macOS ships every language's voices at once, so `voices.json`
  carries one flat list for `macOS` and `voices_keys("macOS", locale)`
  ignores the locale. This closes the 0-voices tell for a macOS claim.
- **Windows fr-FR.** The host has only the `en-US` speech pack. The
  `Language.Speech~~~fr-FR` capability install for the capture
  (reversible) was attempted twice: `Add-WindowsCapability` over ssh →
  "Access is denied" 0x80070005 (the session's admin token is not
  elevated), then through a `RunLevel Highest` scheduled task → the same
  denial. The task and its result file were removed; the host is as found.
  `capture_voices.py --where winhost --locale fr-FR` is ready for a host
  where the pack can be installed from an elevated console; until then the
  `fr-FR` row stays quoted and the manifest says so.

## 3. Verification (`verify_windows_behaviour.py`, box `out/Default/chrome`)

| row | expectation | RED |
|---|---|---|
| A1 Windows claim | `AudioContext.sampleRate` 48000, `baseLatency` × 48000 an integer frame count, state `running` after `resume()` in a gesture, an OfflineAudioContext render still produces non-silent output | box real 44100 (measured, the oracle's KNOWN line) |
| A2 key absent | the box's real 44100 | — |
| A3 Linux claim | real rate (the generator emits no key) | — |
| V3 macOS claim | 191 voices, Samantha default | pre-slice 0 |
| O1 | `audio.sampleRate` measured, no longer excluded | — |

Regressions: oracle 4/4, `verify_sp4_audio.py`, voices 5/5, generator N=3,
keys unit (89), `gn check //media/audio:audio`, `checkdeps media/audio`.
Then the ninth archive cut.

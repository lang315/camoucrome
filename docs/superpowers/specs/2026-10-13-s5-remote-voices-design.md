# S5: remote speech voices — design

S5 comes from the step 2 baseline (`measurements/2026-10-step2-baseline.md` §4, finding 4; roadmap item S5). It covers only the voice half of S5. The other half has three parts:
- BrowserScan's "WebGL exception";
- BrowserScan's font count, 95 on the fork against 132 on stock;
- Pixelscan's time-zone flag.

The first two may be the session-0 GPU artefact that S4 found (folded into step2b). They are left to step2b's session-1 recapture and are out of scope here.

The pin is Chrome `154.0.8037.93`. Patch lines below were read from `patches/sp4-voices.patch` and `patches/voices-ii.patch` on `main` (`1318226`).

## Problem

Stock Chrome lists the platform's local voices, then 19 **Google network voices** with `localService: false`. This holds on Windows, measured in `baselines/chrome-8037-stock-oracle-windows.json` (headless and headed alike), and on macOS (stock Chrome 155 on the owner's Mac, 2026-10-13). The fork lists none of them, and CreepJS reports remote voices as `unsupported`. Every page can read `speechSynthesis.getVoices()`, so the gap is a direct tell.

The cause is data, not mechanism. `voices:list` (sp4-voices) already carries `localService`, and `IsCamouVoice` already routes every configured voice to the fake `speak()` path (voices-ii). But `settings/voices.json` has 0 remote voices:
- 49 Windows language-pack rows, Microsoft voices only;
- the macOS list, 191 local voices.

The macOS capture (`scripts/capture_voices.py --where mac`) missed the Google voices. The 2026-10-13 probe saw all 210 voices (191 local + 19 Google) arrive in one `voiceschanged`, 143–191 ms after load. Why the old capture lacked them is not known; it is moot: the local list is correct.

Adding the voices to the list alone would open a second tell. The fake `speak()` path treats every voice as local:
- `start` is posted at delay 0;
- one `boundary` fires per word;
- `end` follows at `chars / (12.5 * rate)` ± 15 %.

A Google voice behaves differently. The probe ran on stock Chrome 155 on the Mac, n = 1 per cell, volume 0, with `--autoplay-policy=no-user-gesture-required` (the probe's only flag):

| | local (Samantha) | Google US English |
|---|---|---|
| `start` after `speak()` | 14–16 ms | 402–1549 ms |
| `boundary` events | 8 (one per word) | **0** |
| `end`, 43 chars | 3.04–3.16 s | 4.27 s |
| 540 chars | not run | `error: interrupted` at 7.47 s, after `start` |
| `cancel()` 2.5 s in | not run | `start`, then `error: interrupted` |
| dead proxy | unchanged | list unchanged; `speak()` → `error: interrupted`, no `start` |
| no user activation | `error: not-allowed` | `error: not-allowed` |

Counting `boundary` events alone would tell a configured Google voice on the fork from stock.

## Goal and success criteria

A fork claiming Windows or macOS lists the 19 Google voices exactly as stock does: names byte-exact, `lang`, `voiceURI == name`, `localService: false`, `default: false`, after the local voices. `speak()` on one of them has stock's event shape:
- no `boundary`;
- `start` delayed within the measured band;
- `end`, `interrupted`, `cancel` and `pause`/`resume` as stock does them on the host.

No JavaScript is injected; the change lives in data, the generator and the existing Blink fake path.

Success is measured by four checks:
- `verify_voices_remote.py` reaches its expected count on WSL, with RED rows failing on `main`;
- the fork's `getVoices()` equals stock 154's on the Windows host, in session 1;
- the event sequence of `speak()` on the host matches stock's in kind, with timings inside the measured bands;
- the regressions below are unchanged.

## Design

### 1. Data (`settings/voices.json`)

- Add a top-level `"remote"` array: the 19 voices in stock's order, taken from `baselines/chrome-8037-stock-oracle-windows.json`. Names stay byte-exact, including the U+00A0 in the two Chinese names. Each entry has `localService: false` and `default: false`.
- The list is per Chrome, not per OS: the Mac (155) and host (154) lists are identical. So it is one table, not per platform.
- `$comment` gains three lines: where the list came from, that it is Chrome-branded (the Chromium pin has no such voices of its own), and that the earlier macOS capture lacked it.
- The macOS row needs no recapture. Stock Chrome 155 on the Mac (2026-10-13) listed 191 local voices equal in order to the committed row. `capture_voices.py` gains a settle wait and keeps remote voices out of the platform row, so a future capture cannot drop them or duplicate them.

### 2. Generator (`client/python/camoucrome/gen.py`)

`voices_keys(platform, locale)` returns the local row (unchanged selection rule) followed by `voices["remote"]`. Linux returns `{}` as today, because stock Chrome's Linux voice list was never captured. The Go and Node clients run `python -m camoucrome.gen`, so they need no change. `test_gen.py` asserts:
- the 19 remote voices follow the local ones;
- `default` stays on the first local voice only;
- the Linux case is still empty.

No new config key: the remote behaviour is derived from `localService`, which is already in each voice object. (A derived value gets no key; `keys.json` naming rule.)

### 3. Blink (`voices-ii.patch`, amended in its own commit)

In `SpeechSynthesis::StartSpeakingImmediately`'s fake branch, branch on the utterance voice's `localService()`. The local branch stays byte-identical. The remote branch differs in five ways:
- **No boundary loop.** `camou_pending_boundaries_ = 0`, so `MaybeFinishFakeSpeak` does not wait.
- **Delayed `start`.** It is posted at `remote_start` instead of 0. `remote_start` lies within W0's measured band and is spread by the existing FNV-1a jitter `unit` (text + voiceURI). That keeps a reread stable and adds no new hash.
- **`end`** at `remote_start + chars / (remote_cps * rate) * (1 + jitter)`. `remote_cps` is W0's measured rate for the Google voice, and the existing `voices:fakeCompletion:charsPerSecond` continues to drive the local branch only.
- **Length cut-off.** Only if W0 confirms one on the host: past the measured length or duration the task fires `error: interrupted` at the cut-off time, through the same generation-checked task path, instead of `end`. If W0 shows no cut-off on Windows, there is none.
- **`cancel()`, `pause()` and `resume()`** keep voices-ii's existing mechanics. If W0 shows the Google voice differs from local voices there (for example, `pause()` having no effect), the remote branch mirrors stock. Otherwise nothing changes.

The constants are `constexpr` in `speech_synthesis.cc`, next to `kFakePausePollInterval`. A comment cites the S5 measurement doc. They are not config: they describe Chrome's network voices, not the identity.

The `not-allowed` check sits in `speak()`, before the queue, so it is expected to cover the fake path already. A verify row checks this rather than assumes it.

`voices:fakeCompletion = false` still errors deterministically for both branches, as today.

### 4. Measurement first (W0, before any code)

The constants come from stock Chrome 154 on the Windows host, **in session 1**, through a temporary interactive scheduled task, `-UserId (whoami) -LogonType Interactive`. Session 0 crashes the GPU process once per launch (S4; evidence lands as `measurements/2026-10-12-s4-gpu-session0.md` with step2b). Each launch is gated on chrome://gpu `GPU process crash count` == 0.

The run is under `build_lock`, with n ≥ 10 per cell and volume 0, measuring "Google US English" against "Microsoft David":
1. `getVoices()` timeline: the number and timing of `voiceschanged` events, and the final list.
2. `speak()` events for 3 lengths (43, 200 and 540 chars) at rate 1. The 43-char case also runs at rate 2. Record event kinds, times and `charIndex`.
3. `cancel()` 1 s after `start`; `pause()` 1 s after `start`, then `resume()` 1 s later.
4. `speak()` without activation (`not-allowed`).

User activation comes from a CDP `Input.dispatchMouseEvent` click before the speaks, not from the autoplay flag, so the host argv stays the oracle's. Results go to the S5 measurement doc as distributions (min, median, max), with no device labels and no IPs.

Where the Mac (155) and host (154) differ, the host wins.

## Verification

- **WSL `content_shell`:** new `scripts/verify_voices_remote.py` with a fixed `EXPECTED` row count, driven through `lib_shell.session` with a Windows identity from `gen.py`:
  - R1: the list has the local row, then the 19 remote voices, byte-exact.
  - R2: a remote `speak()` fires 0 `boundary`.
  - R3: its `start` falls inside W0's band.
  - R4: its `end`/`interrupted` matches W0 for each length.
  - R5: `cancel()` gives `interrupted`.
  - R6: `pause()`/`resume()` behaves as W0 measured.
  - R7: without activation, `not-allowed`.
  - R8: a local voice still fires its boundaries (control).
  - **RED:** on `main` with the same identity, R1 fails (no remote voices). With the list but the old Blink path (a mutant that forces the remote branch off), R2 and R3 fail. Both REDs are run and recorded.
- **Windows host, session 1, fork `out\Release` against stock 154:**
  - the `getVoices()` lists are equal;
  - the event kinds of each `speak()` case are equal;
  - the timings fall inside stock's band.
  - The same host script with the fork on `main`'s build is its RED.
- **Regressions:**
  - `verify_sp4_voices`, `verify_voices_ii`, `verify_voices_pause`;
  - `verify_windows_behaviour` (voices per locale) and `verify_host_oracle`'s voices leaf;
  - `verify_sp6b_generator`, `client/python` tests;
  - `windows_verify_set.py green` 21/21, with O2's known FAIL unchanged.
- `gen_keys --check`, `check_additions_build`, `check_checkout_sync`, and `gn check` for `//third_party/blink/renderer/modules/speech`.

## Docs in the same PR

- `measurements/2026-10-s5-remote-voices.md`: W0's tables, the verify results, and the gaps.
- Roadmap (`plans/2026-10-02-long-term-roadmap.md`):
  - S3 and S3b marked merged (#32, #33);
  - S4 marked as the session-0 harness artefact folded into step2b;
  - S5's voice half DONE, with its other half pointing at step2b.

## Out of scope and gaps

- **Offline behaviour.** Stock's Google voices fail with `interrupted` when the network is down; the fork always "succeeds". A page that can see the network state can see the difference. This is documented, not faked.
- **Exact network timing.** The fork's `start` delay is a deterministic draw from a band, not a network round trip.
- **Linux.** Stock Chrome's voice list on Linux was never captured, so a Linux claim stays without voices, as today.
- **Pixelscan's time-zone flag** belongs to the proxy layer. BrowserScan's WebGL/font items are left to step2b.
- **Locale-dependence** of the 19-voice list was not tested beyond one Windows locale and one Mac locale. If W0 shows the list depends on the UI locale, this design returns to review before any code.

## Amendments made during execution (2026-10-13)

The measurements (`measurements/2026-10-s5-remote-voices.md` §2 and §4) changed four parts of §3. The owner ruled on each one.

1. **Rate.** Stock's remote duration does not scale as 1/rate. At rate 2 it takes 0.37× the rate-1 time.
   - A rate sweep (0.1–4) gave a curve, and the fork interpolates it log-log: 0.1 → 3.037, 0.25 → 2.512, 0.5 → 1.823, 0.75 → 1.338, 1 → 1, 1.5 → 0.582, 2 → 0.372.
   - Above rate 2, a Google voice never starts on stock. It fires no event until `cancel()`, which gives `interrupted`. The fork does the same.
   - The threshold inside (2, 2.25] is not measured.
2. **Pause.** A Google voice's `pause()`/`resume()` fire no `pause`/`resume` events on stock, and `speechSynthesis.paused` stays false, but `end` still moves by the paused time.
   - The remote branch keeps an end deadline, `camou_end_due_`, that each pause moves.
   - It keeps its own pause flag, `camou_paused_at_`, and leaves `is_paused_` alone.
3. **Cancel.** `cancel()` on any configured (fake) voice, local or remote, fired no event before S5; stock fires `error: interrupted` on both. S5 fixes it for both branches.
4. **Start draw.** Stock's start varies on every call. The remote start therefore mixes the speak's generation and clock into its hash, instead of the per-text FNV bits that §3 specified.
5. **No cut-off; no activation row.** 0/9 long speaks were cut on the host, so there is no cut-off code. Without activation, `content_shell` and CDP-driven stock both start a speak, so the activation row (R7) was dropped.

Out of scope, recorded as gaps: three gaps in the local fake path (§6 of the measurements), and the Linux voice list.

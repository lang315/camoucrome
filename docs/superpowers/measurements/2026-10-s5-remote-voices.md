# S5: remote speech voices — measurements

Spec: `specs/2026-10-13-s5-remote-voices-design.md`. Plan: `plans/2026-10-13-s5-remote-voices.md`.

## 1. Data

**Stock Chrome 155 on the owner's Mac, 2026-10-13.** This ran on stock Chrome with no fork; it was a throwaway probe, one launch online and one behind a dead proxy.

**What it listed.** `speechSynthesis.getVoices()` gave **210 voices**:
- 191 local voices. Their names and `lang` equal `settings/voices.json`'s macOS list, in order.
- 19 Google voices, `localService: false`, `default: false`, `voiceURI == name`. In order, `name` and `lang`, they equal the 19 in `baselines/chrome-8037-stock-oracle-windows.json` (stock 154 on the Windows host, headless and headed).

**When it arrived.** All 210 came in one `voiceschanged`, 143–191 ms after load, online and offline alike. The list is static, not fetched.

So the remote table is one list shared by every Chrome-branded OS build, and the committed macOS list needs no recapture.

## 2. Host: stock Chrome 154, session 1

**Setup.**
- Run on 2026-10-14, 10:01–10:26 ICT: stock Chrome 154.0.8037.93 on the build box's Windows host, headed, in the owner's interactive RDP session (session 1). It was launched through a temporary interactive scheduled task by `scripts/measure_remote_voices.py`.
- Two arms, interleaved: `stock`, and `stock-fr` (`--lang=fr`, voice list only). n = 10 each.
- Every arm launches with `--disable-background-timer-throttling --disable-renderer-backgrounding --disable-backgrounding-occluded-windows`. Without them, the page's timers on the RDP desktop stalled for more than 9 min (smoke runs). They move timer scheduling, not what the speech engine reports.
- Each speak is at volume 0, after one real CDP click (user activation; it took 1 click, sometimes 2).
- The text is `'The quick brown fox jumps over the lazy dog. '` repeated and cut to n characters.

**Gate.**
- RED: one launch run directly over sshd (session 0) read `GPU process crash count` 1 and was marked UNMEASURED. In session 0, speech does not work at all: the queue never starts, and only 3 voices are listed.
- Main run: crash count 0 on all 20 launches; 0 UNMEASURED, 0 errors.

**Voice list.**

| arm | list equals the baseline's 22 (3 local + 19 Google) | other |
|---|---|---|
| stock | 9/10 | 1/10 listed only the 3 local voices, still 3 at the end of the launch |
| stock-fr | 10/10 | the 19 Google voices are identical under `--lang=fr` |

- The Google voices arrive first (one `voiceschanged` with 19, at 2–17 ms), then the local 3 (at 14–34 ms).
- The list does not depend on the UI locale.
- It is volatile: one launch in ten never gets the Google voices. Step 2 saw the same ("stock's list differed between launches").

**`speak()` without activation.**
- `started` on every launch under patchright.
- On the Mac, with a plain launch and no CDP, the same speak gave `not-allowed`.
- So a CDP-driven page has activation here, or the check differs per platform. R7 stays a guard on the fork's own Blink check.

**Speak cells** (Google US English = remote, Microsoft David = local; n = 9 remote, the launch without Google voices has none; n = 10 local; ms from `speak()`):

| cell | event kinds (boundaries counted separately) | boundaries | start min / p10 / med / p90 / max | end − start (median) |
|---|---|---|---|---|
| remote 43, rate 1 | start end | 0 | 195 / 218 / 270 / 392 / 664 | 2961 (14.5 cps) |
| remote 200, rate 1 | start end | 0 | 173 / 209 / 265 / 369 / 427 | 12463 (16.0 cps) |
| remote 540, rate 1 | start end | 0 | 204 / 205 / 541 / 769 / 894 | 32963 (16.4 cps), **no cut-off** |
| remote 43, rate 2 | start end | 0 | 109 / 123 / 185 / 465 / 1226 | 1101 (0.37 × rate 1) |
| remote 200, cancel 1 s after start | start error:interrupted | 0 | 181 / 206 / 243 / 381 / 420 | error at +1006 |
| remote 200, pause 1 s after start, resume 1 s later | **start end** (no `pause`, no `resume` event) | 0 | 171 / 175 / 237 / 310 / 368 | 13456 (+993 vs no pause) |
| local 43, rate 1 | start end | 10 | 249 / 251 / 256 / 307 / 318 | 3458 (12.4 cps) |
| local 200, rate 1 | start end | 45 | 248 / 250 / 256 / 267 / 273 | 15696 (12.7 cps) |
| local 540, rate 1 | start end | 120 | 248 / 250 / 255 / 267 / 267 | 40574 (13.3 cps) |
| local 43, rate 2 | start end | 10 | 248 / 250 / 258 / 272 / 280 | 2426 (0.70 × rate 1) |
| local 200, cancel | start error:interrupted | 5 | 248 / 250 / 258 / 272 / 275 | error at +1014 |
| local 200, pause/resume | start pause resume end | 45 | 246 / 248 / 254 / 278 / 306 | 16334 (+638 vs no pause) |

Every duration varies by under 0.5 % across launches: the engine's timing is deterministic for a given text. Only `start` varies.

**Against the plan's rules (Task 1 Step 5).**
- `start_p10_ms` = 218, `start_p90_ms` = 392 (remote, 43 chars).
- `remote_cps` = 16.05 (200 chars).
- `cutoff_ms` = 0: 0/9 runs of 540 chars were cut. The Mac's `interrupted` at 7.5 s was not reproduced.
- **Rate: out of both bands.** r = 1101 / 2961 = 0.37, so neither `divide` (0.4–0.6) nor `ignore` (0.85–1.15) applies. Stop, per the plan.
- **Pause: the remote shape differs from the local one.** The remote voice fires no `pause`/`resume` events, but its `end` still moves by the paused second. The local voice fires both. Stop, per the plan.

**Existing gaps in the local fake path**, outside S5 and recorded for §6: stock's local voice starts at about 255 ms (the fork starts at about 0), and its rate-2 ratio is 0.70 (the fork divides by the rate, giving 0.5).

## 3. WSL rows (`verify_voices_remote.py`)

Filled by Tasks 3 and 4.

## 4. Host: fork against stock, session 1

Filled by Task 5.

## 5. Regressions

Filled by Tasks 4 and 5.

## 6. Gaps

Filled by Task 6.

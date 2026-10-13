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
- Run on 2026-10-13, 03:01–03:26 UTC: stock Chrome 154.0.8037.93 on the build box's Windows host, headed, in the owner's interactive RDP session (session 1). It was launched through a temporary interactive scheduled task by `scripts/measure_remote_voices.py`.
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

EXPECTED 9. Rows: R1, R2, R3, R4a, R4c, R4b, R5, R6, R8. R7 was dropped because it measured nothing: `content_shell` with `--autoplay-policy=user-gesture-required`, and patchright-driven stock 154, both start a speak without activation.

The duration rows compare `end − start` with the exact value the remote branch must produce: chars / 16.05 cps × rate^−1.43 × (1 + jitter). The jitter is the voices-ii FNV-1a of text + voiceURI, replicated in the script. The tolerance is 120 ms (R4a, R4c), 150 ms (R4b) and 250 ms (R6, which also includes the paused second).

| build (WSL `content_shell`) | data | result | failing rows |
|---|---|---|---|
| main (`1e1c03b5fe`), no S5 C++ | S5 branch | **2/9 FAIL** | R2: 9 boundaries; R3: start 4–7 ms; R4a/R4b/R4c: 12.5 cps, rate divided; R5: cancel fires no event (start, then nothing for 60 s); R6: pause/resume events fire, end +5 s off the prediction |
| main | main (`S5_ROOT`) | **1/9 FAIL** | R1: only the 3 local voices; R2–R6: no Google voice |

R1 and R8 pass on main + S5 data: the list comes from the data, and R8 is the control.

**After S5** (box `camoucrome/s5` = `b513ace5dc`: `camoucrome/main` + the S5 fixup in `voices-ii`; patch sha256 `b17363b4…`):

| build | result | detail |
|---|---|---|
| S5 | **9/9 ALL_PASS** | remote 43 chars: start 390 ms, 0 boundaries, end − start 2423 (predicted 2424); rate 2: 900 (900); 540 chars: 31549 (31547); cancel: start, error:interrupted at +1001; pause/resume: no pause/resume events, end − start 15037 (predicted 15036 = 14036 + the paused 1000) |
| S5 + test-only mutant (`remote` forced false; never committed) | **3/9 FAIL** | R2, R3, R4a, R4c, R4b, R6 FAIL; R1 (data), R5 (the cancel fix does not depend on the flag) and R8 pass |

The S5 build was rerun after export (`content_shell`, 8 steps) with the same 9/9.

**Review Focus checks** (one launch each): a remote speak of empty text fires `start`, `end`. With `voices:fakeCompletion` false, a remote speak fires only `error: synthesis-failed`.

R5 shows a **gap that predates S5**: `cancel()` on any configured (fake) voice, local or remote, fires no event, while stock fires `error: interrupted` on both (§2, 10/10). The owner ruled that S5 fixes it (2026-10-13).

## 4. Host: fork against stock, session 1

Filled by Task 5.

## 5. Regressions

**WSL, S5 build:**

| verify | result |
|---|---|
| `verify_sp4_voices` | 5/5 ALL_PASS |
| `verify_voices_ii` | 5/5 ALL_PASS |
| `verify_voices_pause` | no FAIL row (VP-RESUME-EVT, VP-STOP and VP-RESPEAK pass) |
| `verify_windows_behaviour` | 12/14. V1 and V3 FAIL in the harness only because they run `camoucrome.gen` from the box's client checkout (`~/camoucrome-client`, still on main). Pointing `CAMOU_CLIENT` at the branch tree breaks 11 unrelated rows (fonts, runtime). The two row expressions, evaluated on the branch's generator, are both true; `client/python` tests 54/54 cover the same lists. |

**Checks:**
- `gn check out/Default //third_party/blink/renderer/modules/speech:speech`: Header dependency check OK.
- `checkdeps` (speech): clean.
- Export gate: `check_checkout_sync` PASS, all 48 copied files identical. Only `patches/voices-ii.patch` changed.

**A build trap** (W6): the plan reset unchanged files' mtimes to `out/Default/args.gn`. That file was rewritten at 01:05 the same day, when the RCS arg was added to CI's tree, after most objects had been built. So the "reset" files were newer than their objects, and the post-export build started a full rebuild: 3166 objects in 53 min before it was stopped. Re-dating the same 154 files to the pin commit's time (2026-09-28) brought the next build to 8 steps. Reset against a timestamp older than every output, not against `args.gn`.

## 6. Gaps

**Remote voices, not faked:**
- **Offline.** Stock's Google voices end in `error: interrupted` without `start` when the network is down (Mac, dead proxy). The fork always "succeeds", so a page that can see the network state can see the difference.
- **The list is volatile on stock and constant on the fork.** 1 of 10 stock launches never got the Google voices (§2). The fork lists them on every launch.
- **Start delay.** The fork draws it deterministically from [218, 392] ms (per text and voice). Stock's is a network round trip, 109–1226 ms over 63 cells, with a long tail.
- **Duration.** The fork's duration for a given text is off stock's by the voices-ii jitter (±15 %). Both are deterministic per text, so the same text measures, for example, 2424 ms on the fork against 2961 ms on stock (43 chars). Only a page that already knows stock's number for that text can use it.
- **Unmeasured on stock:** `pause()` or `cancel()` inside the start delay (before `start`). The fork pauses silently and, on a cancel, fires `interrupted` without `start`.
- **Activation.** Whether a remote `speak()` without activation gives `not-allowed` was not measured on the host (patchright-driven pages start it). R7 was dropped.
- **Mac only:** Chrome 155 cut one 540-character speak at 7.5 s (n = 1). The host's stock 154 never did (0/9). The fork follows the host.

**The local fake path, before S5 and unchanged by it** (measured in §2):
- Stock's local voice starts at about 255 ms; the fork's at about 0.
- Stock's rate-2 duration is 0.70 × rate 1; the fork's is 0.5.
- Stock moves `end` by about 640 ms for a paused second; the fork's local path does not move it.

S5 fixed only the local `cancel()` shape.

**Other:**
- A Linux identity still lists no voices: stock Chrome's Linux list was never captured.
- `verify_windows_behaviour` V1/V3 read the box's client checkout, so they turn green in-harness only after merge (§5).

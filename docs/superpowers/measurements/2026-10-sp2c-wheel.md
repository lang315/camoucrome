# SP2c — how stock Chrome 154 delivers wheel notches (host oracle)

Spec: `docs/superpowers/specs/2026-10-17-sp2c-humanized-wheel-design.md` §2.
Plan: `docs/superpowers/plans/2026-10-17-sp2c-humanized-wheel.md` Task 1.
Data: `baselines/chrome-8037-wheel.json`, written by `scripts/capture_wheel_oracle.py`.

Run on 2026-10-17, 08:23–08:31 UTC, on the build box's Windows host. All arms ran in session 1 (the owner's RDP session, connected and unlocked). The GPU crash count read 0 on every arm.

| Host fact | Value |
|---|---|
| Chrome | `154.0.8037.93` (the pin's tag) |
| `WheelScrollLines` | 3 (the Windows default) |
| `AppliedDPI` | 96, i.e. 100 % scale |
| page `devicePixelRatio` | 1 on every arm |

## Arms

| arm | input | n_wheel | deltaY | wheelDeltaY | deltaMode | gaps (ms) | n_scroll | final scrollY |
|---|---|---|---|---|---|---|---|---|
| real1 | `SendInput` 1 notch | 1 | 100 | -120 | 0 | – | 1 | 100 |
| real3 | `SendInput` 3 notches, 40 ms apart | 3 | 100 ×3 | -120 ×3 | 0 | 42.9, 52.8 | 2 | 300 |
| real3_dsf1 | same, `--force-device-scale-factor=1` | 3 | 100 ×3 | -120 ×3 | 0 | 44.1, 41.4 | 3 | 300 |
| cdp100 | CDP `mouseWheel` deltaY 100 | 1 | 100 | -120 | 0 | – | 1 | 100 |
| cdp300 | CDP `mouseWheel` deltaY 300 | 1 | 300 | -120 | 0 | – | 1 | 300 |

Every event had `isTrusted: true`.

## RED gate

The real3 and cdp300 arms differ, so the probe measured something:
- event count: 3 against 1;
- `wheelDeltaY/deltaY`: -1.2 per event against -0.4.

The gate's third check also passed: scroll-event count, 2 against 1. **That difference is not animation.** No arm animated:
- every `scroll` event lands on a whole notch's offset;
- real1 and cdp100 each give exactly one `scroll`;
- real3's 2 or 3 scroll events are its notches, coalesced by frame.

So smooth scrolling was off in this session for real input as well as for CDP. Chrome may turn it off in a remote session; that is not established here. The spec's claim that "each one is animated" is therefore **unmeasured**. The fork's notches use the same `kScrollByPixel` units as a real notch, so they animate wherever stock does. That remains a host-native check on a non-RDP console, listed under Open.

One notch over CDP (`cdp100`) is already indistinguishable from one real notch. The tell is a multi-notch scroll delivered as one event, which is exactly what SP2c splits.

## Constants (used by Tasks 2–4)

| constant | value | from |
|---|---|---|
| `notch_css_px` | 100 | real1 `dy[0]` |
| `modes` | `[0]` (pixels) | real3 |
| `tracks_dpr` | unmeasured at 100 %: real3 and real3_dsf1 agree, but both run at DPR 1 | real3 vs real3_dsf1 |

Following plan Task 1 Step 9, the `tracks_dpr = false` formula is used: the browser-side delta is `100 × ScaleFactor()`, which Blink divides back to 100 CSS px. No invariant is added.

## Transport notes (for whoever reruns this)

- No ssh master was available on the Mac. The scripts were generated on the WSL box from the pushed branch; the generation is deterministic, and the real1 sha `FFB18EF9…` was identical on the Mac and the box. The host then copied them with `cmd /c wsl … cat > file`, checked each sha256, and ran them synchronously through sshgate.
- sshgate `stdin` larger than about 8 KB hung in `[Console]::In.ReadToEnd()`. A detached `Start-Process` dies when the ssh session ends.
- sshgate keeps 64 KiB of stdout and cuts the middle. Every arm's output was about 65.5 K, because `chrome://gpu`'s text is long. The page result comes early in the output and was intact. The `chrome://gpu` JSON line was cut, but each arm's `GPU process crash count : 0` line survived the cut. The GPU block was rebuilt from that surviving line before replaying the run through `capture_wheel_oracle.main()`.
- The first attempt, at 15:20, saw 0 wheel events. Session 1 was locked: `SetCursorPos` returned false and `SendInput` returned 0 with error 5. The run worked once the owner connected RDP.

## Verify (WSL `chrome`, `out/Default`)

Build-box tree on `camoucrome/main` at `3da17048d5` (`sp2c-humanized-wheel`, one commit above `0aec35868d`), 2026-10-17.

**Unit tests** (`components_unittests --gtest_filter='MouseTrajectoriesTest.*'`):
- RED, the test alone: `error: use of undeclared identifier 'QuantizeWheel'`.
- GREEN: a 15-step build, `[  PASSED  ] 10 tests.`
- Mutant: the clamp moved to `kMaxWheelNotches + 1`. `QuantizeWheelClampsAndRejectsNonFinite` FAILED. After restoring, 10 passed.

**`gn check out/Default //content/browser:browser`**: `Header dependency check OK`. `checkdeps.py content/browser/devtools/protocol`: `SUCCESS`. The hook's build was 49 steps.

**`verify_sp2c.py`**, 8 rows:

| run | result |
|---|---|
| before SP2c (chrome built from `0aec35868d`) | R2, R3, R7 FAIL; R1, R4, R5, R6, R8 PASS; rc 1 |
| SP2c | 8/8 PASS, rc 0 (run three times) |
| mutant `EffectiveOsIsWindows() → true` | R4 and R5 FAIL, every other row PASS |
| row-8 guard RED (the child waits 120 s instead of wheeling) | R8 FAIL `{"returned": false}` after 45 s; no Chrome left behind |

**Rows added after the final review**, giving 11 rows. All 11 PASS, rc 0.

| run | result |
|---|---|
| R9: DSF 2, `wheel(0,300)` at (100,100) | 3 events, each `deltaY 100` / `wheelDeltaY -120`, 300 px in total. Stock gives 1 event of `deltaY 300` at DSF 2, so the totals match. CDP wheel deltas are CSS px. The first form of the row wheeled at (300,300), which lies outside the 500×137 viewport at DSF 2, so stock got no event there either; probed and fixed. |
| R10: cross-site navigation (127.0.0.1 to localhost) mid-wheel, bfcache on | PASS |
| R11: the same with `--disable-features=BackForwardCache` | PASS |
| mutant: `ForwardWheelNotchCompletion`'s dead-widget branch never answers (`callback.release()`) | R8 and R11 FAIL with `{"returned": false}`, so both reach the dead-widget path. R10 still PASSES, because with bfcache on the old widget is still alive and acks. |

On the pin, stock CDP `wheel(0, 0)` delivers one zero-delta `wheel` event. Under SP2c that case keeps stock's path, and row 3 asserts the two match.

**Round trip.**
- The exported patch was re-applied with `git apply --3way` onto `HEAD~1`. `git diff --cached HEAD` printed 0 lines, and `gn check` passed.
- `check_checkout_sync.sh local`: `PASS all 48 copied files are identical in repo and checkout`.

**Not done.** The host-native arm: `chrome.exe` with `humanize:enabled` compared against this oracle, including animation on a console session. It needs a Windows rebuild, which is the owner's call.

## Open

- **Cadence.** The 18–60 ms band is Camoufox's. `SendInput` set this run's cadence (40 ms plus delivery), so it says nothing about a hand's.
- **DPR at other scales.** This host only runs at 100 %.
- **Animation.** Measure stock and fork on a console session, not RDP, with the host-native arm.

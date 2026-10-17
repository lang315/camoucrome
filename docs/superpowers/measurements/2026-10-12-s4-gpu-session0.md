# S4: fork instability on WebGPU, HEVC and CreepJS is a session-0 artefact (2026-10-12)

A spike, run on 2026-10-12. The spike edited nothing and built nothing; this doc and the fix came with step2b (`specs/2026-10-13-step2b-detectors-design.md`), which the owner folded S4 into on 2026-10-13.
Host: the build box's Windows host, with `out\Release\chrome.exe` (154.0.8037.93, S3b build) as the fork and stock Chrome 154.0.8037.93 as the control.
Lock `s4 spike` was held for the host runs, then released (status `free`). After the runs there were 0 chrome processes, and the temporary scheduled task was removed.
Scratch dir kept: `D:\camou-win\cn\s4` (`s4probe.py`, `s4bis.py`, `s4fac.py`, `s4log.py`, `s4sum.py`, `*.jsonl` + logs).

## Verdict

**This is a harness artefact, not a fork defect.** The host runs every measurement in **session 0**, where the browser is launched via `Win32_Process`/sshd. There the GPU process **crashes once on every launch**, stock included.

The crash sequence is:
1. `DCompositionCreateDevice3 failed: Access is denied`.
2. ANGLE `SwapChain11::reset` reports device lost.
3. `eglCreateWindowSurface` fails with `EGL_CONTEXT_LOST`.
4. The driver workaround `exit_on_context_lost` takes the process down (`GpuProcessHost: The GPU process crashed! Exit code: RESULT_CODE_GPU_EXIT_ON_CONTEXT_LOST`).
5. The GPU process relaunches.

This also corrects the brief: step 2 did **not** run headed in the console session. Its doc says "inside the SSH session", and sshgate-launched processes are in session 0 (`(Get-Process -Id $PID).SessionId` = 0). Every prior host measurement launched this way ran under this artefact.

A renderer whose GPU-backed queries hit the dying first GPU process keeps the empty answers for its whole life:
- HEVC `["", false]`;
- in rarer cases `requestAdapter() === null` and `getContext('webgl') === null`.

The fork's renderer lands in that window in about 17% of launches. Stock's lands in it in 0 of 80.

In the **interactive RDP session** (session 1, the owner's live `rdp-tcp` session, not the physical console), the GPU process never crashes: crash count 0 in 40 of 40 launches. There the fork is stable: 0 of 20 flips. Stock is too: 0 of 20.

## Probe

`s4probe.py` reuses `measure_step2`: `Arm`, `identity(1)`, `opened`, `serve`, `first_page`, `STOCK_APP`, and the client's `remove_dir`.

Per launch:
- **Setup.** A fresh profile. A local page served on 127.0.0.1.
- **Page reads.** At **t0** (≈60 ms after navigation start) and at **t3** (3.0 s):
  - `canPlayType` and `MediaSource.isTypeSupported` for the oracle's exact string `video/mp4; codecs="hev1.1.6.L93.B0"`;
  - `navigator.gpu.requestAdapter()`, capped at 15 s; recorded as `hw`, `fallback`, `null` or `timeout`, with its ms.
- **After the page.** The WebGL renderer class (swiftshader / warp / other, boolean only), then from `chrome://gpu`:
  - the feature status lines;
  - `GPU process crash count`;
  - log lines matching crash/exit/lost.
- **Host side.** The GPU-process argv flags (`--use-angle`, `--use-gl`, `--disable-gpu*`) and count, read through WMI, filtered by the profile dir.

Arms are interleaved round-robin.

**RED first** (`S4_RED=1`): fork with `--disable-gpu` reads HEVC `["", false]` at t0/t3, adapter `null`, WebGL `warp` and GPU argv `--use-angle=d3d11-warp-webgl`, and chrome://gpu reports everything as "Software only". The paired stock launch is all-green. So every field can fail and says so.

Deviation from the brief: two follow-up arms were added after the main run, a config bisection and an argv × config 2×2, plus an interactive-session run. The main run pointed at the config, the bisection did not single out a key, and the GPU crash log then pointed at the session.

## Rates

HEVC `probably` = `["probably", true]`. "adapter hw" = a non-fallback adapter. In **every** launch t0 equals t3, for both HEVC and the adapter: the answer never changes within a launch.

### Session 0 (how step 2 and every host verify run), main run

| arm | mode | n | HEVC probably (t0 = t3) | adapter hw (t0 = t3) | GPU crash count |
|---|---|---|---|---|---|
| stock | headless | 20 | 20/20 | 20/20 | 1 in 20/20 |
| stock | headed | 20 | 20/20 | 20/20 | 1 in 20/20 |
| fork (identity seed 1) | headless | 20 | **16/20** | 20/20 | 1 in 20/20 |
| fork (identity seed 1) | headed | 20 | **17/20** | **19/20** (+ WebGL null, same launch) | 1 in 20/20 |
| fork-bare (no config, no window/dpr) | headless | 10 | 10/10 | 10/10 | 1 |
| fork-bare | headed | 10 | 10/10 | 10/10 | 1 |
| stock-argv (stock + identity window/dpr) | headless | 10 | 10/10 | 10/10 | 1 |
| stock-argv | headed | 10 | 10/10 | 10/10 | 1 |

### Session 0, config bisection (fork, headless, identity window/dpr, 20 each)

| config | HEVC "" | adapter null |
|---|---|---|
| full identity (51 keys) | 8 | 0 |
| only-fonts (4 keys, the long font lists) | 7 | 0 |
| no-webgl | 5 | 1 |
| no-rest | 5 | 0 |
| only-rest (navigator, screen, window, ua, locale, tz, canvas) | 4 | 0 |
| no-fonts | 3 | 2 |
| no-media | 2 | 0 |
| only-webgl | 2 | 0 |
| min (`canvas:seed` only) | 1 | 0 |
| only-media | 1 | 0 |

### Session 0, argv × config 2×2 (fork, headless, 20 each)

| arm | HEVC "" | adapter null |
|---|---|---|
| fork-bare | 1 | 0 |
| fork + window/dpr | 7 | 1 |
| fork + `{canvas:seed}` | 5 | 0 |
| fork + both | 1 | 0 |
| stock + both | 0 | 0 |

**Session 0 totals:**
- **fork:** HEVC `""` in **59/340** (17%), adapter null in **5/340**.
- **stock:** **0/80** on both.

No single key group and neither factor is necessary: fork-bare flipped once, and fork + both only once. The rate moves with something launch-timing-like that the bisection cannot isolate at n=20. Larger configs trend higher (full 8, only-fonts 7, min 1), but the 2×2 contradicts a clean size effect.

### Interactive RDP session (scheduled task, LogonType Interactive, session 1)

| arm | mode | n | HEVC probably | adapter hw | GPU crash count | chrome://gpu WebGPU |
|---|---|---|---|---|---|---|
| stock | headless / headed | 10 / 10 | 20/20 | 20/20 | **0** in 20/20 | Hardware accelerated |
| fork (identity seed 1) | headless / headed | 10 / 10 | **20/20** | **20/20** | **0** in 20/20 | Hardware accelerated |

In session 0, chrome://gpu says `WebGPU: Hardware accelerated but at reduced performance` on both arms. In the RDP session it says `Hardware accelerated`.

## Diagnosis

**HEVC on Windows.**
1. `IsDecoderHevcProfileSupported` (`media/base/supported_types.cc:231-250`) answers from the supplemental decoder-profile cache.
2. In the renderer, `RenderMediaClient` fills that cache (`content/renderer/media/render_media_client.cc`):
   - Its constructor (`:95-116`) asks `InterfaceFactory::CreateVideoDecoder()->GetSupportedConfigs()` asynchronously. That answer comes from the GPU process's media service.
   - `IsDecoderSupportedVideoType` (`:164-183`) makes the same call synchronously if the async answer has not arrived.
   - If the decoder remote disconnects, `OnVideoDecoderDisconnected` (`:267-271`) records an **empty** config list.
   - `OnGetSupportedVideoDecoderConfigs` (`:281-291`) **latches**: it returns early once signaled.

So a renderer whose query was in flight to the GPU process that then exits with `EXIT_ON_CONTEXT_LOST` answers `""`/`false` for its whole life. That matches t0 = t3 = `""` in every flipped launch. `SetGpuFeatureInfoInternal` (`:340-363`) can only purge further; it never repopulates. The answer is racy at renderer start, not at page load. It is already `""` at t0 ≈ 60 ms.

**WebGPU.** The same race on the renderer's GPU channel: adapter `null` and WebGL `null` together in the same launches (5/340), both latched to t3. It is not the GPU blocklist: chrome://gpu feature status is identical on flipped and clean launches. It is not slowness either: adapter resolve was ≈50 ms where it succeeded, so the oracle's 5 s `gpu` cap is not the cause.

**Why the fork and not stock.** No fork patch touches GPU-process, viz, `media/gpu`, `media/mojo` or `content/browser/gpu` code:
- `sp3a-canvas-noise.patch`'s "webgpu" is one BUILD.gn context line;
- `windows-sandbox-env` only passes `CAMOU_*` through `FilterEnvironment`;
- `crashpad-no-dumps` only disables report writing.

The crash itself is identical on both binaries: same log lines, crash count 1 in every session-0 launch measured (~465: RED smoke, main, bisection, 2×2, log dump). What differs is how often the fork's renderer issues its GPU-side queries before the first GPU process dies. This is consistent with different startup timing:
- the fork is a non-official build (no PGO/LTO, `release-args.gn`);
- the fork parses config in the browser at `BrowserMainLoop::Init` (sp0/sp5a);
- launches with any config or window argv add work.

The exact timing difference was not measured. Launch argv per arm is as step 2 recorded: `--window-size`, `--force-device-scale-factor` and `--accept-lang` on the fork only. stock + window/dpr + config never flipped (0/40).

**CreepJS `rendering: 0% rgba noise`.** Not re-measured. It is the same cause by inference: a launch whose renderer lost the race has no WebGL context (WebGL null in 5/340). CreepJS's rendering/rgba checks then read nothing, so they report 0% noise and a different FP ID. Step 2 saw it in 1 of 3 headed runs, which fits a ~2-17% per-launch rate across its detector launches.

**Step 2 carries the artefact too.** Its baseline ran in session 0 (`2026-10-step2-baseline.md` §1: "inside the SSH session, on a 1024×768 desktop nobody sees"). The `gpu.*` rows on both arms therefore come from a relaunched GPU process. On the interactive desktop, chrome://gpu WebGPU status differs ("reduced performance" vs not). Whether `gpu.*` leaves (limits, features) also differ was not checked.

## Fix (step2b, no fork change)

Done in step2b: `scripts/windows/run-interactive.ps1` starts host runners in the interactive session, `winhost.py` wraps each of its launches the same way, and `scripts/gpu_gate.py` gates every host launch path on the crash count below (session 0 refused where no context exists). The recommendation as written on 2026-10-12:

1. **Run host measurements in the interactive session, not session 0.**
   - Launch the runner through a temporary scheduled task with `New-ScheduledTaskPrincipal -UserId (whoami) -LogonType Interactive`. This is measured here: crash count 0, 0/40 flips. Unregister the task afterwards.
   - `$env:USERDOMAIN\$env:USERNAME` does not resolve in the sshgate session; use `whoami`.
   - Trade-offs:
     - it needs the owner logged on (an RDP session that is disconnected or active);
     - headed windows appear on the owner's desktop;
     - the window is the real one, not 1024×768, so step 2's `win.outerMinusInner*` caveat changes.
2. **Make the harness refuse a crashed GPU process.**
   - Read `GPU process crash count` from chrome://gpu, as `s4probe.gpu_page` does.
   - Mark the run UNMEASURED when it is non-zero, in `measure_step2.py` and in any host verify that reads GPU-backed leaves.
   - Make it RED first: the session-0 launch above gives crash count 1 on every launch.
   - Trade-off: one extra page per launch (~1 s).
3. **Recapture the step 2 baseline in the interactive session.** Do it at the next host run, at the latest at the 156 re-pin (due 2026-10-20). Then reclassify step 2 §5 and §6.5 ("fork is unstable") as harness artefacts, not findings.

**Not recommended:**
- a fork-side HEVC/WebGPU spoof or a "re-query on GPU reconnect" patch. The latch is upstream behaviour that stock shows too, under the same crash with different timing. Patching it would make the fork differ from stock on any real machine whose GPU process dies at startup.
- `--disable-direct-composition` or similar argv: it moves page-visible surfaces and is a launch-argv tell.

## Gaps

- Why the fork's renderer loses the race more often than stock's: no trace was taken. The candidates are build shape (non-official) and config-parse time, but neither is measured.
- CreepJS was not re-run; its attribution is by inference.
- `gpu.*` oracle leaves were not compared between session 0 and the interactive session.
- Only the RDP session was measured, not the physical console. Both are interactive window stations, so the access-denied DirectComposition path should not apply to either, but only RDP is measured.
- During the session-1 run, headed windows appeared for about 3 minutes on the owner's active RDP desktop.
- Not checked: whether `verify_host_oracle`'s known O2 FAIL is a GPU-backed leaf, which would make it the same artefact. Worth a look.
- Only one generated identity (seed 1) was tried. The n=20 cells in the bisection are too small to rank key groups.

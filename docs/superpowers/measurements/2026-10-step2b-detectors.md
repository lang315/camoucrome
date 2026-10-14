# Step 2b at main: 20 detector pages, the session-0 fix, the fork against stock

Spec `specs/2026-10-13-step2b-detectors-design.md`, plan `plans/2026-10-13-step2b-detectors.md`.
Measured on 2026-10-13 on the build box's Windows host, in the owner's
interactive RDP session (session 1), with the owner connected. The S4
evidence that motivated the session move is `2026-10-12-s4-gpu-session0.md`.

The committed baseline is `step2b-main/rows.json` and `step2b-main/tables.md`,
both put through `measure_step2.py scrub`. Besides addresses, coordinates,
city, ISP and the user name, the scrub also replaced the host's country
(`<country>`) and time zone (`<host-zone>`): the repo is public (owner,
2026-10-14). Raw page text and screenshots stay
on the host (`D:\camou-win\cn\step2b`).

## 1. What was compared

| | control | fork |
|---|---|---|
| executable | `C:\Program Files\Google\Chrome\Application\chrome.exe` | `D:\camou-win\chromium\src\out\Release\chrome.exe` |
| version | 154.0.8037.93 | 154.0.8037.93 |
| source | stock, held at the pin | main `1318226`, change set re-applied (below) |
| config | none | `camoucrome.gen` Windows identity, seed 1 (seed 2 for linkability) |

- **Fork rebuild.**
  - The Windows tree was re-pointed to main without a fetch or sync, because the pin is unchanged.
  - Before the reset, 150 dirty paths were checked against main's change set (`miss=0`). After `apply.sh`, 156 (`rc=0`).
  - `out\Release`: `Build Succeeded: 9400 steps` in 2 h 44 m. The first attempt at the default 16 jobs died with `LLVM ERROR: out of memory`: the host's commit limit is 38.3 GB and WSL's VM holds about 24 GB of it. The rebuild ran at `-j 8`.
  - `out\Observe` was rebuilt the same way with `v8_enable_runtime_call_stats = true` added: 6148 steps, 1 h 46 m. That build is for E's arm 1.
- **Session.**
  - Every run went through `scripts/windows/run-interactive.ps1` (a temporary scheduled task, `-LogonType Interactive`), and every run recorded `session=1`.
  - The desktop was 1512×950 with RDP connected, smaller than the identity's 1920×1200 screen. So step 2's headed `win.outerMinusInner*` artefact persists.

## 2. The gates, RED and GREEN

Every host launch path now runs in the interactive session and is gated on
`chrome://gpu`'s `GPU process crash count` (`scripts/gpu_gate.py`).
Some launches give the harness no context or port to read that page from:
- `camoucrome.probe` and the client's own launches: host oracle O1/O2, and
  the set entries `verify_windows_client`, `verify_sp6b_launcher`,
  `verify_sp6b_driver`, `verify_sp6b_generator`, `verify_d_pointer_touch` and
  `verify_windows_fonts`;
- `winhost.dump_dom`.

There a session-id check stands in: S4 measured crash count 1 in every
session-0 launch and 0 in 40 of 40 session-1 launches. This deviates from the
spec's "a reader per launch path".

Since the final review, a standalone verify that printed an `UNMEASURED` line
exits 3 (`lib_shell`'s atexit, and the host oracle). `measure_step2 run` exits
1 when any detector site cell is UNMEASURED. `compare` exits 2 when it skipped
a cell.

**Session gate**, run in session 0 (sshgate directly). Every row refused with
`UNMEASURED session=0: …` and rc 3:

| path | result |
|---|---|
| `windows_verify_set.py green` | refused |
| `verify_host_oracle.py` | refused |
| `verify_s3_host.py` | refused |
| `measure_step2.py run` | refused |
| `winhost` (its PowerShell run unwrapped) | `SESSION=0` |

**Crash gate**, in session 0 with `CAMOU_ALLOW_SESSION0=1`, the RED:

| path | result |
|---|---|
| `lib_shell` (`verify_sp1b.py`) | 10 × `UNMEASURED gpu-crash=1` |
| `windows_verify_set.py --only verify_sp1b.py` | `BAD … UNMEASURED (10)`, `0/1 entries OK; 1 UNMEASURED`, rc 1 |
| host oracle O3/O4 | `UNMEASURED gpu-crash=1 (O3)` and `(O4)` |
| `verify_s3_host.py` | `UNMEASURED gpu-crash=2`, rc 3 |
| `measure_step2` noise | both cells `GpuCrashed: UNMEASURED gpu-crash=1`, tables `UNMEASURED` |
| `measure_step2` detectors (sannysoft) | `det.sannysoft = UNMEASURED`, `gpu_crash = 1`, no raw text kept |
| `winhost` CDP (unwrapped) | `GPU process crash count :1` |

The session-0 RED also caught a defect. `measure_step2`'s argv precondition
aborted the whole run on a gated launch. It now keeps the argv it read.

**GREEN in session 1**: `winhost` wrapped, `SESSION=1`, crash count 0, no
task or Chrome left behind.

The Windows set ran in session 1 three times:

| state | result |
|---|---|
| RDP disconnected ("Disc") | 17/21 |
| RDP connected (owner at the desktop) | 20/21, 0 UNMEASURED |
| control rerun in session 0 | the session-1 failures pass |

What the first session-1 runs found:
- **`verify_crash_dumps`**: its C1 crashes a renderer on purpose. After that, the gate's CDP connect hangs for more than 60 s. The verify now launches with `gpu_gate=False`; none of its rows is GPU-backed.
- **`verify_d_pointer_touch` V1** needs a host without a mouse, and every interactive session has one. By the owner's choice V1 prints NOT MEASURED there, and the set's entry declares `may_skip=("V1",)`.
- **Disconnected-session failures**:
  - `sandbox_env` A2: no audio endpoint, so the 44100 fallback;
  - `sp2b` criterion 3: mouse path events clustered;
  - `verify_s3_host` W1/W4/W6: stock lists no devices.
  All of these pass with RDP connected.
- **`sandbox_env` A2 still fails with RDP connected.** The RDP audio device runs at 44100, which is the same value as the no-device fallback that A2 excludes. Recorded here as an environment finding; the verify is unchanged.
- **O2** fails with the same message as on 2026-10-04 (`windows-oracle.patch` keeps share/bluetooth under a Linux claim). It is not the GPU artefact.

`verify_s3_host` with RDP connected: `7/7 ALL_PASS`.

## 3. Liveness: 20 of 24 pages

One headless stock load per page in session 1 on 2026-10-13 (the plan's
research), each launch at crash count 0. Four pages dropped:

| page | evidence |
|---|---|
| `kaliiiiiiiiii.github.io/brotector` | `Site not found · GitHub Pages` |
| `fingerprintjs.github.io/BotD/main` | `Site not found · GitHub Pages` |
| `arh.antoinevastel.com/bots/areyouheadless` | `502 Bad Gateway`, again at the recheck before the measurement |
| `demo.turnstile.workers.dev` | token `XXXX.DUMMY.TOKEN.XXXX` from 3 s on: a test sitekey that always passes |

`whoer.net` served Cloudflare's "Performing security verification" page to
headless stock. That is recorded as the `blocked` row, which every site
carries.

## 4. Each detector seen RED first

Two planted runs put stock Chrome in both arms and add one argument to the
"fork" arm. Any planted argument also shortens the planted arm's viewport by
56 px (headed 795→739, headless 485→429), probably through Chrome's
unsupported-flag infobar. A site that sees only that has seen the argv, not
the API.

| site | WebShare off | AutomationControlled off |
|---|---|---|
| sannysoft | `share`/`canShare` lines | viewport only |
| creepjs | properties 83→81 | headless scores |
| browserscan | — | authenticity 90% |
| pixelscan | — | headed: "No automated behavior detected" |
| rebrowser | viewport only | `navigatorWebdriver` |
| dbi_bot | — | `isBot`, `hasWebdriverTrue` |
| incolumitas | viewport only | `webDriver`, `webdriverPresent` |
| detect_headless | — | `Webdriver` |
| browserleaks_javascript | `share`/`canShare` lines | `webdriver false` |
| browserleaks_client_hints | viewport only | viewport only |
| iphey | — | "Everything is fine" |
| whoer | headed disguise 70% vs 100% | viewport only |
| amiunique | 83→81 properties | — |
| fingerprint_scan | — | headed bot score 15/100 |
| fingerprint_pro | headed: tampering, `anti_detect_browser: true` | headed: Bot not detected |
| browserleaks_canvas, _webgl, _webrtc, _fonts, _tls | — | — |

The last row's five pages are **blind to both plants**. Their tables are
printed but are not evidence of anything the plants touch.

## 5. Volatile

Two null runs (stock in both arms, every probe, 20 sites) set the noise floor.
The detector text was very noisy. The entries added to `VOLATILE` and
`VOLATILE_LINES`, each with a test, cover:
- network estimates;
- clocks, epoch and ISO times;
- TLS GREASE, JA3, JA4_o, `config_id` and `payload_length`;
- Fingerprint Pro's per-load ids, ML scores and visit counts;
- incolumitas' per-load TCP/IP fields;
- rebrowser's timings;
- bare numbers, hashes and booleans that a line diff cannot name;
- BrowserScan and whoer ad lines.

Pixelscan's own verdict lines ("inconsistent", "Masking detected") flipped
between two stock loads, so they count as volatile too: Pixelscan's verdict
is not a measurement here.

After calibration, `compare` of the two null runs reads `0 rows disagree
outside VOLATILE`. One site cell, rebrowser in null run 2 (fork/headless),
did not load and is listed as `SKIPPED`: `compare` now skips a site cell
that is UNMEASURED in either run, and lists it.

## 6. Three fork runs

| run | session | desktop | errors | unmeasured |
|---|---|---|---|---|
| 1 `20261013-161750` | RDP connected | 1512×950 | 0 | 0 |
| A `20261013-221129` | console | 1280×1024 | 0 | 0 |
| B `20261013-223445` (baseline) | console | 1280×1024 | 0 | 0 |

At 00:07 on 2026-10-14 the host rebooted unattended (no 1074 event). That
killed a second RDP run in its last cell. The owner then chose two fresh runs
in the console session, so that a pair shares one environment. Run 1 is kept
as a third reading.

`compare A B` gives **2 rows disagree outside VOLATILE**, both on Fingerprint
Pro, fork/headless:
- `Proxy Detection`: "Not detected" vs "residential proxy (confidence: low)";
- `Suspect Score`: 15 vs 21.

These are findings, not volatile. The service's low-confidence proxy verdict
on the fork flips between runs.

Stability (`stab.changed`) is empty for both arms in every run and mode.

## 7. Findings, fork against stock

Every fork-vs-stock row is labelled. A row is `expected` when it traces to an
identity key (UA, languages, window, deviceMemory, `audio:sampleRate`,
`canvas:seed`) or to SP2 (webdriver); each such row's reason is in
`step2_rows.EXPECTED`. What remains:

1. **CreepJS counts no remote voices on the fork** (`remote (0):
   unsupported`), where stock counts 19. This shows in all three runs and both
   modes. It is step 2's finding 4, still open. S5 (PR #37) addresses it.
2. **Fingerprint Pro "Browser Tampering: Yes"** on the fork:
   - run 1: both modes;
   - runs A and B: headless.
   Stock also reads "Yes" in run B headed, so the signal is partly the driver.
   The fork in headless mode is flagged where stock headless is not.
3. **Fingerprint Pro proxy and VPN.** The fork reads "VPN … timezone mismatch":
   the identity's `America/Chicago` against the host's IP. That is labelled
   expected, because a client pairs the identity with a matching proxy. The fork
   also reads a low-confidence "residential proxy" that flips run to run.
   Pixelscan headed says "Timezone spoofed" for the same reason.
4. **fingerprint_scan.** The fork prints `NotSupportedError`/`TIMEOUT` where
   stock lists Summarizer availability: an on-device AI API the fork build
   lacks.
5. **Fingerprint Pro headless** prints "Chromium-Based Browser Not Available"
   on the fork.

What favours the fork:
- **Bot scores.** fingerprint_scan bot score 100 → 20/100. iphey loses
  "Detected an automated browser environment signal".
- **Webdriver verdicts pass** on the fork: dbi_bot `isBot` false, rebrowser
  `navigatorWebdriver` pass, and incolumitas `webDriver`/`webdriverPresent` OK.
  Stock under the same driver fails each of these.
- **Shared fail.** incolumitas `WEBDRIVER` (fpscanner) FAILs on both arms
  alike.
- **Driver leaks not seen.** rebrowser's `runtimeEnableLeak`, `pwInitScripts`
  and `exposeFunctionLeak` pass or are not triggered on both arms.
- **Network.** JA4, HTTP/2 SETTINGS and header order are equal between the arms.

## 8. What step 2's §5 and §6.5 became

Step 2's "the fork is not stable across launches" (WebGPU, HEVC, CreepJS
rendering) was the session-0 GPU crash. In session 1 every reading matches
stock:
- `stab.changed` is empty;
- HEVC is `["probably", true]` on the fork;
- all 10 `gpu.*` leaves are present and equal to stock's.

`2026-10-step2-baseline.md` carries a note at §5, at finding 5, and at its
HEVC paragraph.

## 9. Rulings

1. 20 of 24 pages live; the four drops are in §3.
2. browserleaks rows are named with `_`, because `label_rows` reads a site
   from two dotted parts.
3. No page needed an `action` field.
4. A session check stands in for the crash count where a path offers no
   context (§2).
5. Every site gets a `blocked` row.
6. Per-load ids are volatile, not scrubbed.
7. `compare` skips a site cell UNMEASURED in either run, and lists it.
8. Bare numbers, hashes and booleans, and Pixelscan's verdict lines, are
   `VOLATILE_LINES`.
9. `verify_crash_dumps` opts out of the gate (`gpu_gate=False`).
10. `lib_shell`'s gate skips a browser that already exited.
11. `verify_d_pointer_touch` V1 is NOT MEASURED on a host with a mouse (owner,
    2026-10-13).
12. `sandbox_env` A2 in session 1 is left as an environment finding.
13. Both builds ran at `-j 8` after the OOM.
14. Fingerprint Pro's "timezone mismatch" is labelled expected; the reason is
    in §7. The owner confirmed this on 2026-10-14 and opened roadmap backlog
    item 13 (timezone and locale coherent with the exit IP).

# Step 2b: more public detectors, the Windows fork at main, the interactive session — design

Approved in brainstorming on 2026-10-13. Extends
`docs/superpowers/specs/2026-10-04-step2-measurement-design.md` (step 2) and
its runner `scripts/measure_step2.py`. Owner's choices: a findings table (not
a pass/fail gate); the fork's `out\Release` rebuilt at main; three groups of
sites added (automation detectors, fingerprint aggregators, commercial
anti-bot demos); built into `measure_step2.py`, not a new runner.

## Goal

Know what a wider set of public fingerprint and bot detectors say about the
fork at main, next to stock Chrome on the same host, through the same client.
The output is the step 2 tables for 24 detector pages, plus a verdict table,
measured in the owner's interactive session. Every finding becomes a backlog
entry; this slice fixes nothing.

## What changes since the step 2 baseline (2026-10-04)

- **The fork moved.** S2c, S3, S3b and observer A merged after the baseline;
  the Windows `out\Release` has not been rebuilt since.
- **The baseline carries a harness artefact.** Every step 2 launch ran in
  Windows session 0 (through sshgate/sshd/`Win32_Process`). There the GPU
  process crashes once per launch, in stock too
  (`DCompositionCreateDevice3` "Access is denied", then
  `RESULT_CODE_GPU_EXIT_ON_CONTEXT_LOST`, then a relaunch). A renderer that
  queries the GPU in that window latches an empty answer: HEVC `["",false]`,
  sometimes a null WebGPU adapter and WebGL. Session 0: fork 59/340 flips,
  stock 0/80. The interactive RDP session (session 1): crash count 0 in 40 of
  40 launches, 0/40 flips (S4 spike, 2026-10-12; raw data and
  `s4probe.py` on the host at `D:\camou-win\cn\s4`). Step 2's §5 and §6.5
  ("the fork is not stable") and its `gpu.*` rows are suspect.
- **Four detectors is a narrow view.** Only CreepJS and sannysoft saw step 2's
  planted difference; BrowserScan and Pixelscan were blind to it.

## Arms

Unchanged from step 2:

| arm | executable | config |
|---|---|---|
| control | `C:\Program Files\Google\Chrome\Application\chrome.exe`, stock, held at the pin `154.0.8037.93` | none |
| fork | `D:\camou-win\chromium\src\out\Release\chrome.exe`, rebuilt at main | `camoucrome.gen` Windows identity, seed 1, with its `window`/`dpr` |

Both through `camoucrome.launch()`, headed and headless, under the real
sandbox and the host GPU. The version and argv-parity preconditions stay as
they are.

## Sites

`DETECTORS` changes from a `{name: url}` dict to a list of
`Site(name, url, action=None, parser=None)`. 24 pages, each its own site (raw
file, line diff, table):

| group | name | url |
|---|---|---|
| step 2 | `sannysoft` | `https://bot.sannysoft.com/` |
| step 2 | `creepjs` | `https://abrahamjuliot.github.io/creepjs/` |
| step 2 | `browserscan` | `https://www.browserscan.net/` |
| step 2 | `pixelscan` | `https://pixelscan.net/fingerprint-check` |
| automation | `rebrowser` | `https://bot-detector.rebrowser.net/` |
| automation | `brotector` | `https://kaliiiiiiiiii.github.io/brotector/` |
| automation | `dbi_bot` | `https://deviceandbrowserinfo.com/are_you_a_bot` |
| automation | `incolumitas` | `https://bot.incolumitas.com/` |
| automation | `botd` | `https://fingerprintjs.github.io/BotD/main/` |
| automation | `detect_headless` | `https://infosimples.github.io/detect-headless/` |
| automation | `areyouheadless` | `https://arh.antoinevastel.com/bots/areyouheadless` |
| aggregator | `browserleaks.javascript` | `https://browserleaks.com/javascript` |
| aggregator | `browserleaks.canvas` | `https://browserleaks.com/canvas` |
| aggregator | `browserleaks.webgl` | `https://browserleaks.com/webgl` |
| aggregator | `browserleaks.webrtc` | `https://browserleaks.com/webrtc` |
| aggregator | `browserleaks.fonts` | `https://browserleaks.com/fonts` |
| aggregator | `browserleaks.client_hints` | `https://browserleaks.com/client-hints` |
| aggregator | `browserleaks.tls` | `https://browserleaks.com/tls` |
| aggregator | `iphey` | `https://iphey.com/` |
| aggregator | `whoer` | `https://whoer.net/` |
| aggregator | `amiunique` | `https://amiunique.org/fingerprint` |
| aggregator | `fingerprint_scan` | `https://fingerprint-scan.com/` |
| commercial | `fingerprint_pro` | `https://demo.fingerprint.com/playground` |
| commercial | `turnstile` | Cloudflare's public Turnstile demo page |

- **Liveness gate.** The plan loads every URL once in stock Chrome before any
  code depends on it. A page that does not load, or that waits for input the
  table does not name, is dropped from the table and the drop is recorded in
  the measurement doc. No URL is guessed: the Turnstile row gets its URL from
  that check, or is dropped.
- **`action`.** Only for a page that needs one, named from its first stock
  capture: a selector to click, or a condition to wait for. Turnstile waits
  until its widget leaves the loading state (passed, challenge shown, or
  failed), then reads it. Nothing solves a challenge.
- **Load rate.** One load per page per cell, no loop, no automatic retry. A
  re-run is a manual decision.

## Reading a page

- `settle()` as in step 2: the page's text once two reads 3 s apart agree
  outside `VOLATILE_LINES`, or `UNMEASURED` at the timeout.
- **Line diff, fork against control, for every site** (step 2's
  `line_diff`). Lines that change between runs of one arm go into
  `VOLATILE_LINES`, each with its reason and a test.
- **Key/value parser** only where the stock capture is a table that
  `parse_tabbed` or `parse_colon` already reads; registered in
  `rows.PARSERS`. The plan decides per site from the capture.
- **Verdict parser** for the sites that print a verdict: `rebrowser` (each
  test's pass/fail), `dbi_bot` (bot or human), `botd` (bot or not),
  `incolumitas` (its classification), `fingerprint_pro` (bot, tampering,
  VPN, incognito), `turnstile` (passed, challenge, failed: whether a token
  is present). Each parser's shape is fixed from the first stock capture,
  and its unit fixture copies that text (scrubbed). A parser that reads
  nothing returns no rows, and the verdict table prints `UNMEASURED` for it,
  never a silent pass.

## Output

- `tables.md` keeps step 2's per-probe tables and adds a **verdict table**:
  for every verdict site, the four cells (control/fork × headed/headless),
  whether or not they differ. Both arms flagged as a bot is a finding (a
  tell the driver or host gives both), which a fork-vs-control diff hides.
  A fork verdict that passes where stock under the driver is flagged is
  `expected` (SP2), as `oracle.nav.webdriver` is today.
- **`scrub()`** replaces the host's IP addresses, city, region, coordinates,
  ISP and ASN in rows and tables before anything is committed. Step 2 did
  this by hand; it is now a function with tests.
- Committed: `docs/superpowers/measurements/2026-10-step2b-detectors.md` and
  `docs/superpowers/measurements/step2b-main/{rows.json,tables.md}`, all
  scrubbed. Screenshots and raw text stay on the host.

## The interactive session

- The runner runs as a temporary scheduled task with
  `New-ScheduledTaskPrincipal -UserId (whoami) -LogonType Interactive`,
  started over sshgate, detached, writing a log file that is polled (sshgate
  caps a call at 600 s). The task is unregistered afterwards.
  `$env:USERDOMAIN\$env:USERNAME` does not resolve under sshgate; `whoami`
  does.
- The owner must be logged in over RDP and leave the desktop alone for the
  run: headed windows appear on it.
- **GPU gate.** Every cell reads `GPU process crash count` from
  `chrome://gpu` in the same browser after its probe (as `s4probe.gpu_page`
  does). Non-zero marks the cell `UNMEASURED`, with the count recorded. RED
  first: the same reader under session 0 reads 1.
- The run records the RDP desktop's size. If it is smaller than the claimed
  1920×1200 screen, the headed `win.outerMinusInner*` artefact of step 2
  persists and the doc says so.

## Also re-run: step 2's five probes

`oracle`, `noise`, `network`, `stability` and `linkability` run in the same
interactive run (about 20 minutes more). The doc lists which step 2 §5/§6
rows the session-1 run overturns. Re-ranking the backlog from them is
roadmap work, not this slice.

## RED first

| check | how | pass |
|---|---|---|
| noise floor | two `run --null` (stock in both arms) | `compare` of the two: 0 rows disagree outside VOLATILE; this calibrates `VOLATILE_LINES` for the new sites |
| listing sites see a change | `run --null --plant --disable-blink-features=WebShare` | the site shows a fork-only line or row |
| automation sites see a change | `run --null --plant --disable-blink-features=AutomationControlled` (stock in both arms; the arg goes to the "fork" arm only, so its `navigator.webdriver` drops to false while the control's stays true) | the site's verdict or a line differs |
| GPU gate | the reader in session 0 | crash count 1, cell `UNMEASURED` |

Both plants reuse `--null --plant`; no new flag. The plan greps the 154 tree
to confirm both runtime features exist and do what the row needs. A site
that sees neither plant is recorded **blind to plant** (as BrowserScan and
Pixelscan were in step 2): its table is printed but is not evidence.

## Unit tests (offline, pytest, run by `checks.yml`)

Each seen failing first:
- the site table: unique names, `https` URLs, every `parser` and `action`
  callable;
- each verdict parser on its scrubbed fixture;
- `scrub()`: IPv4, IPv6, city/region/coordinate/ISP/ASN fields, and that it
  leaves other text alone;
- the GPU crash-count reader on a saved `chrome://gpu` text;
- the verdict table, including `UNMEASURED`;
- the Turnstile `action`'s state reading on saved page text.

## Rebuilding the fork at main

The Windows source tree `D:\camou-win\chromium\src` is a bare working tree
(the change set applied, uncommitted) shared by `out\Release` and the
observer's `out\Observe`. The pin does not change, so the re-point is the
runbook §7 procedure without the fetch and sync:

1. **Preconditions, all three before the tree is touched:**
   - canvas acknowledges (message before, and after);
   - the owner has chosen how E's arms stay comparable (PR #36's open
     question): re-pointing the tree means the next `out\Observe` build is
     main, not the build E's arm 1 ran on;
   - every patch applied in the tree today is in main's `patches/series`
     (`windows-sandbox-env.patch` and `crashpad-no-dumps.patch` are, checked
     2026-10-13), so the reset discards nothing that main lacks.
2. Record the tree's state (the line count of `git status --porcelain
   -uall`) and `D:\camou-win\tree.commit`.
3. Take `scripts/build_lock.sh acquire step2b`.
4. Guard: `git rev-parse --show-toplevel` is the tree. Then `git reset --hard
   -q`, `git clean -fdq components/camoucfg`.
5. Refresh `D:\camou-win\tree` to main (`git archive` from the runner clone,
   as before) and write `tree.commit`.
6. `apply.sh` under `C:\Program Files\Git\bin\bash.exe`; gate: every patch
   applies.
7. `gn gen out\Release`; `autoninja -C out\Release chrome`, detached; record
   the non-zero step count and wall time.
8. Release the lock, message canvas.

The fork arm's version precondition then holds as before (`154.0.8037.93`).

## Operation

- The measurement holds `build_lock.sh` (owner `step2`) for the whole run, so
  no build loads the machine meanwhile.
- **Sequencing with CI.** CI on main refuses to start while the lock is
  held. If the owner merges PR #36 during the rebuild or the run, its CI
  waits. Either merge #36 and let its CI finish before the lock is taken, or
  run this first; the owner picks.
- **Schedule.** Measure at 154 now. At the 156 re-pin (due 2026-10-20) the
  same command recaptures it.

## Done when

- One command on the host, in the interactive session, produces every table
  for both arms in both modes.
- Two null runs agree under `compare`.
- Each site's RED is recorded (sees a plant, or blind to plant).
- The doc, rows and tables, scrubbed, are committed through a PR with the
  evidence. Not merged without the owner's approval.

## Out of scope

- Fixing anything the tables find.
- Solving or bypassing a challenge.
- An aggregate score.
- Re-ranking the backlog.
- `coveryourtracks.eff.org` (named once in brainstorming by mistake; not in
  the approved list).

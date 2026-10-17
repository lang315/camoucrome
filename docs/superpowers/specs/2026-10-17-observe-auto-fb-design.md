# Automated facebook recon (observer arms 1 and 3) — design

Status: approved by the owner on 2026-10-17. It builds on the tracking
observer (`2026-10-06-tracking-observer-design.md`), the Intl recipe
(`2026-10-13-observer-intl-rcs-design.md`) and step 2b's session-1 launch
(`2026-10-13-step2b-detectors-design.md`).

## Goal

A single command re-runs the facebook recon on the Windows host and judges
the result, with no manual step. It is meant to run after a re-pin or an
observer change. It answers one question: does the observer build still
measure facebook, and does it still see every surface group that facebook
read before? A second deliverable records the 2026-10-17 manual recon
(arms 1 to 3 with `-Intl`) as a measurement document.

## Owner rulings (2026-10-17)

- Scope: arm 1 (logged out) and arm 3 (logged in, restored from the backed-up
  profile). Each is one load with no input of any kind. Arm 2 (login) stays
  manual, because tooling never types credentials. Arm 4 is out, and so are
  Instagram and Threads.
- Verdict: **measured, and still seen.**
  - A run is judged only if it measured. Otherwise it is `UNMEASURED`.
  - It is `PASS` when every baseline surface group is still read more than 0
    times on the facebook site, and `FAIL` otherwise.
  - Count drift, new groups, new Intl built-ins and new hosts are `INFO`,
    never `FAIL`.
- This relaxes the rule that there are no automated runs on Meta sites. The
  relaxed rule is written where every session reads it (§7).

## 1. The 2026-10-17 measurement document

`docs/superpowers/measurements/2026-10-17-fb-observe-intl.md` records the
manual arms 1 to 3, run on 2026-10-17 between 10:11 and 10:22 ICT.

- **Build and launch.**
  - `out\Observe` at `1318226`, with `camou_observe = true` and
    `v8_enable_runtime_call_stats = true`.
  - `recon.ps1 -Intl`; the host copy's SHA256 is `561d3113…`.
  - Launched through `run-interactive.ps1` in session 1 (Active).
  - Closed by WM_CLOSE: arm 1 by tooling at 30 s, arms 2 and 3 by tooling
    after the owner said they were done. No CDP.
- **Coverage.** Trace span against netlog span per arm, and the buffer note.
- **Per-arm tables** of surface groups and members on `https://facebook.com`,
  side by side with 2026-10-07.
  - The 10-07 canvas and WebGL draw and state counts were lower bounds
    (before fast-call counting). These are exact.
  - The 10-07 arm 3 covered 58 s of 116 s. This one is complete.
- **Intl** built-ins per arm (new).
- **Requests:** total, `/ajax/bz`, hosts, and `.facebook.com` cookie names.
- **Findings and limits.**
  - Arm 3 made 0 `/ajax/bz` requests.
  - There is no GPU crash-count read on this path.
  - Each arm is one sample.
  - Arm 4, Instagram and Threads were skipped by the owner's ruling.

The numbers come from `observe_judge.py summary` (§3). That is committed code,
not a scratch script, so the doc's tables can be regenerated.

## 2. Launch: `observe-recon.ps1` gains an unattended mode

There are three new parameters. Without them the script behaves exactly as
it does today.

- `-Wait <s>`: after the browser appears, wait `<s>` seconds, then WM_CLOSE
  the windows of its own profile. This is `CloseMainWindow`, a graceful close,
  so the trace is written. Also print `CLOSED=<n> LEFT=<n>`. If the profile's
  processes are still alive 60 s after the close, stop them and print
  `LEFT=<n>`. A killed browser writes no trace, so the judge reads the run as
  `UNMEASURED`.
- `-FromProfile <dir>`: copy `<dir>` into the run's fresh profile before
  launch (robocopy `/E`). The source is never written.
- `-Out <dir>`: write the run under `<dir>\arm<N>` with its profile at
  `<dir>\profile-arm<N>`. The manual `facebook\arm<N>` directories are never
  touched.

The unattended mode also writes `run.json` beside `report.md`, with these
fields:
- `session` and `session_state` (from `quser`, for the script's own session);
- `wait_s`, `closed`, `left`;
- `report_rc`;
- `started` and `ended` (ICT).

## 3. `scripts/observe_judge.py`

Stdlib only. It imports `observe_report` (it is a sibling file on the host
and in the repo) and reads an arm directory: `trace.json`, `net.json`,
`cookies.db`, `run.json`.

- **`summary ARM_DIR`** prints JSON:
  - `groups`: group to calls on site `https://facebook.com`;
  - `members`: API to calls on the same site;
  - `intl`: built-in to calls, or `null` when blind;
  - `cookies`: `host:name` list;
  - `requests`: `total` and `ajax_bz`;
  - `coverage`: `trace_s`, `net_s` and `discarded`;
  - `run`: the `run.json` fields.

  It holds names and counts only. No URL query, id, value or script path
  goes in.
- **`baseline --arm N DIR [--arm N DIR ...] -o FILE`** writes a baseline.
  Per arm, the required groups are the groups with more than 0 calls in
  *every* given run of that arm. The per-run counts are kept for `INFO`.
- **`judge --baseline FILE --arm N DIR`** prints one row per check and exits
  with the worst result.

| verdict | exit | condition |
|---|---|---|
| `UNMEASURED` | 3 | `run.json` missing; `low_memory_kill`; `session != 1`; `session_state != Active`; `report_rc != 0`; `left > 0`; `trace_s < net_s - 5`; `discarded > 0` or buffer stats missing; `intl` is `null` (blind); arm 3 without cookies named `c_user` and `xs` (session expired: the owner logs in with `recon.ps1 -Site facebook -Arm 2 -Intl` and refreshes the backup); the GPU check (§5) fired |
| `FAIL` | 1 | a baseline required group, `intl` included, has 0 calls on the facebook site |
| `PASS` | 0 | every required group is still above 0 |
| `INFO` | — | count change against the baseline, new group, new Intl built-in, `/ajax/bz` and total requests |

If any check is `UNMEASURED`, the verdict is `UNMEASURED`. It is never `PASS`
or `FAIL`.

## 4. `scripts/windows/observe-auto.ps1`

This is the one command. It is run from a shell on the host: sshgate,
session 0. sshgate kills a foreground command at about 60 s, so it is
launched detached there (README "Unattended recon"; found 2026-10-17).

1. **Preconditions.**
   - `quser` must show the owner's session Active. `Disc` is not enough: a
     disconnected session may mark the window occluded, and the page would
     then be hidden.
   - Otherwise print `UNMEASURED no active session` and exit 3.
2. **Memory gate, not the build lock** (owner, 2026-10-17). The run takes no
   `build_lock`, so a build that holds the lock is never blocked by it.
   - A native Windows `ninja.exe` or `siso.exe` running means `UNMEASURED
     native build running`, exit 3. The Windows tree's builds at `-j 8` sit
     near the commit limit.
   - Windows commit headroom (`CommitLimit - Committed`) under 8 GB means
     `UNMEASURED low-memory <n> GB`, exit 3. WSL's VM holds about 24 GB of
     the 38.3 GB limit while it builds.
   - Both checks run again before arm 3.
   - **Watchdog during the run** (S5's condition): while the browser runs,
     `recon.ps1` polls headroom every 5 s. If headroom drops under 4 GB, it
     force-stops the profile's processes and writes `low_memory_kill: true`.
     The judge then reads the arm as `UNMEASURED low-memory`. WSL's VM grows
     on demand and peaks in link steps. An OOM-killed WSL compile costs the
     re-pin hours.
   - `run.json` records:
     - `headroom_launch_gb` and `headroom_min_gb`;
     - `wsl_build`, whether a WSL build was running (`build_lock.sh status`).
     Contention slows the page. The observer counts reads, not timing.
   - At most 10 host runs while a build holds the lock.
3. **Run directory.** Create `D:\camou-win\observe\auto\<yyyyMMdd-HHmmss>`.
4. **Arm 1.** Run, through `run-interactive.ps1`:
   `recon.ps1 -Site facebook -Arm 1 -Intl -Wait 30 -Out <run>`.
   Poll its log for `EXIT=`, with a 5 min timeout.
5. **Arm 3.** Run
   `recon.ps1 -Site facebook -Arm 3 -Intl -Wait 120 -FromProfile <backup> -Out <run>`.
   - The backup defaults to `D:\camou-win\observe\backup\fb-login-20261017`.
   - The timeout is 8 min.
6. **Judge.** Run `observe_judge.py judge` per arm against
   `D:\camou-win\observe\baseline-facebook.json`. Print the rows.
7. **Cleanup**, in `finally`.
   - Remove the temp scheduled tasks.
   - Delete the arm-3 profile copy and every `cookies.db` in the run. They
     hold session cookies. The cookie names are already in `summary`.
   - Keep `trace.json`, `net.json`, `report.md`, `run.json` and
     `summary.json`. They stay on the host.
8. **Exit** with the worst arm verdict.

Each invocation runs each arm exactly once. Nothing schedules it or repeats
it.

## 5. GPU crash signal

This launch has no CDP, so step 2b's `chrome://gpu` gate cannot run.
Candidate: launch with `--enable-logging --v=0`, so Chrome writes
`chrome_debug.log` in the profile, and look for the GPU process host's
unexpected-exit line.

- **RED first.** Launch arm 1 from session 0 with `CAMOU_ALLOW_SESSION0=1`,
  where S4 measured one GPU crash per launch. The log must show the line.
- If it does, the judge reads it and a hit is `UNMEASURED gpu-crash`.
- If no reliable line appears, drop the flag. The session gate is then the
  only guard, and the README and doc say so.

## 6. Baseline calibration

The manual 10-17 arm 3 had scrolling and the automated arm 3 has none. So the
baseline comes from automated runs, not from the manual ones.

1. Run `observe-auto.ps1` twice against an empty baseline, which requires no
   groups. Its verdict can be `PASS` or `UNMEASURED` only.
2. `observe_judge.py baseline` over both runs gives the required groups: the
   groups seen in both runs.
3. Sanity check: every required arm-3 group must also be seen in the manual
   10-17 arm 3. If one is missing, stop and investigate before trusting the
   baseline.
4. Commit the baseline as `docs/observer/baselines/facebook-auto.json`. It
   holds names and counts only. Install a copy on the host as
   `D:\camou-win\observe\baseline-facebook.json`.
5. Null test: each calibration run, judged against the committed baseline,
   is `PASS`.

## 7. Rule and documentation updates (so other sessions know)

- **`CLAUDE.md`** gets one bullet in Build & verify.
  - Automated facebook recon is allowed only through
    `scripts/windows/observe-auto.ps1`: arms 1 and 3, one load each, no input,
    no loops, never scheduled.
  - Arm 2 (login) is manual, by the owner.
  - The backup profile is never read for values, never copied off the host,
    and never committed.
  - The command needs the owner's session Active. It takes no
    `build_lock`, and it refuses when commit headroom is under 8 GB or a
    native Windows build is running.
- **`docs/superpowers/specs/2026-10-06-tracking-observer-design.md`**, Recon:
  add the 2026-10-17 exception beside the 2026-10-07 one.
- **`docs/observer/README.md`**: an "Unattended recon" section covering the
  command, verdicts, how to refresh an expired backup, and the host copies
  with their hashes.
- **`docs/observer/followups.md`**:
  - close "re-run arms on rebuilt `out\Observe`" for facebook;
  - close the RCS rebuild item;
  - record that Instagram and Threads were dropped by the owner.
- **Roadmap:** update the tracking-observer line.
- **Memory:** record the rule change and the backup location.

## 8. Testing

- **Unit (Mac and CI):** `scripts/test_observe_judge.py`, with fixtures built
  in the test as small trace, netlog, cookie-db and `run.json` files.
  - Cover every `UNMEASURED` cause, `FAIL` on a missing required group,
    `PASS`, `INFO` on drift, and baseline intersection.
  - Check that `summary` output holds no URL with a query, no cookie value
    and no script path.
  - Write each test first and watch it fail.
  - Add the file to `build-verify.yml`'s pytest list.
- **Host RED**, each run once, under the §4 memory gate:
  - the wrapper with the owner's session `Disc`, or none: `UNMEASURED no
    active session`;
  - arm 3 with `-FromProfile` pointing at a fresh logged-out profile:
    `UNMEASURED session expired`;
  - arm 1 without `-Intl`: `UNMEASURED blind`;
  - a baseline with a planted required group no run reads (`webgpu` in arm
    1): `FAIL`;
  - the §5 GPU RED.
- **Host GREEN:** the two calibration runs, then one judged run with
  `PASS` on both arms.
- **Gate RED:**
  - a planted 1000 GB headroom floor (a test-only `-MinHeadroomGB` parameter)
    must give `UNMEASURED low-memory`;
  - a process named `ninja.exe` (a copied `ping.exe` that sleeps) must give
    `UNMEASURED native build running`;
  - a planted watchdog floor (a test-only `-KillBelowGB 1000`) must
    force-stop the browser within 10 s and give `UNMEASURED low-memory`.

The host tests take no `build_lock` (§4). They can run during S5's WSL re-pin
build, but not during its native Windows build. The harness refuses that case
by itself.

## Data handling

- **Committed:** API names, counts, group names, built-in names, hosts,
  cookie names, run times and hashes.
- **Never committed:** traces, netlogs, `cookies.db`, profiles, cookie
  values, account ids, script URLs with queries, and anything from the
  backup.
- `summary.json` is safe by construction (§3), and a unit test asserts it.

## Out of scope

- Arm 2 automation and any credential handling.
- Scrolling or other synthetic input.
- Instagram, Threads, and arm 4.
- Scheduling, and repeated runs.
- Decoding `/ajax/bz`.
- Refreshing the backup automatically.

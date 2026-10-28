# Tracking observer — operator guide

An audit build that records, per site, which fingerprint surfaces a page reads
(Web IDL member, real call count, reading origin, top-level site) and what it
sends back (requests, cookie names). Observe-only. Design:
`docs/superpowers/specs/2026-10-06-tracking-observer-design.md`.

## Build

Add to the out dir's `args.gn` (never to `settings/build-args.gn`):

    camou_observe = true
    v8_enable_runtime_call_stats = true

The second arg compiles in V8's runtime call stats, which the Intl recipe below
reads; it rebuilds V8, not Blink (box, 2026-10-13: 1634 steps, 22 min).

`scripts/package.py` refuses such an out dir: an observer build is never a
release. With the arg off, the generated calls compile to nothing.

## Run

    chrome --user-data-dir=<fresh profile> \
      --trace-startup=-*,disabled-by-default-camou.observe \
      --trace-startup-format=json --trace-startup-file=<trace.json> \
      --trace-startup-duration=0 \
      --trace-startup-record-mode=record-as-much-as-possible \
      --log-net-log=<net.json>

Browse, then close the browser normally. The trace is written at shutdown; a
killed browser leaves no trace file. Use one fresh profile per site.

The `-*,` prefix matters: a filter listing only disabled-by-default categories
still enables every default category, which made traces tens to hundreds of MB
and carried unrelated browsing data.

**Intl recipe.** To also count Intl built-ins (`new Intl.DateTimeFormat`,
`resolvedOptions`, the `supportedLocalesOf` family, `toLocale*`), record with

    --trace-startup=-*,disabled-by-default-camou.observe,v8,disabled-by-default-v8.runtime_stats

The report's "V8 built-ins (Intl)" section then lists calls per site, entry
script and built-in. The entry script is the Blink `v8.run` script around the
V8 slice, else the one script of the observer events inside that slice, else
`(unknown)`: event handlers, timers, promise callbacks and module bodies have
no entry script of their own. Without the recipe, or on a build without the
arg, the section says `Intl: blind`, never zero. The recipe is opt-in because
`v8` is a busy default category and the call stats time every built-in call
(see Detectability). On Windows: `observe-recon.ps1 ... -Intl`.

On the Windows host the recon used `scripts/windows/observe-recon.ps1` (one
owner-driven arm: launch with the flags above, wait for the browser to close,
copy the cookie database, run the report) and `scripts/windows/observe-arm1.ps1`
(the tooling-launched logged-out arm, closed by one CDP `Browser.close`). They
hardcode that host's layout (`D:\camou-win\chromium\src\out\Observe\chrome.exe`,
`observe_report.py` in `D:\camou-win\observe`). `observe-recon.ps1` gained
`-Intl` on 2026-10-13 and an unattended mode on 2026-10-17. Since
2026-10-17, `D:\camou-win\observe` holds byte-exact copies of five repo
files:
- `recon.ps1` (`scripts/windows/observe-recon.ps1`);
- `observe-auto.ps1` (`scripts/windows/`);
- `run-interactive.ps1` (`scripts/windows/`);
- `observe_report.py` (`scripts/`);
- `observe_judge.py` (`scripts/`).

`arm1.ps1` (`scripts/windows/observe-arm1.ps1`) is the 2026-10-07 copy, and
`observe-auto.ps1` replaces it.

To check that the host copies match a commit, compare the output of
`Get-FileHash -Algorithm SHA256` on the five files with
`shasum -a 256` on the repo paths. On 2026-10-17 they were installed from
`raw.githubusercontent.com` at the branch head, and all five matched.

`--trace-startup-duration=0` (record until exit) is the documented setting for
`chrome` sessions closed normally. `scripts/verify_observe.py` instead uses
`--trace-startup-duration=20` on `content_shell`, because content_shell's
SIGTERM path wrote no trace; the duration timer flushes it.

`verify_observe.py` has 25 rows, including a hot loop of 100 000 `fillRect`
calls and `lineWidth` sets that V8 runs on its fast API path, three Intl
built-ins counted on the page and in its worker, and two arms that must report
Intl blind.

## Unattended recon (facebook)

The owner allowed this on 2026-10-17
(`docs/superpowers/specs/2026-10-17-observe-auto-fb-design.md`). From a
shell on the host:

    powershell -NoProfile -ExecutionPolicy Bypass -File D:\camou-win\observe\observe-auto.ps1

A run takes up to about 15 minutes. sshgate kills a foreground command at
about 60 s, before `RESULT` and before the command's cleanup (2026-10-17: a
profile copy, `cookies.db` and a scheduled task stayed behind). From
sshgate, launch it detached and poll its output file with calls that sleep
at most 58 s:

    $s = "powershell -NoProfile -ExecutionPolicy Bypass -File D:\camou-win\observe\observe-auto.ps1 *> 'D:\camou-win\observe\auto\<name>.out'; `"RC=`$LASTEXITCODE`" | Add-Content 'D:\camou-win\observe\auto\<name>.out'"
    $b = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($s))
    (Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine = "powershell -NoProfile -EncodedCommand $b"}).ProcessId

The `.out` file ends with `RESULT <verdict> <run dir>` and `RC=<exit>`.

What it runs:
- **Arm 1:** logged out, fresh profile, 30 s.
- **Arm 3:** a copy of the backed-up login
  `D:\camou-win\observe\backup\fb-login-20261017`, 120 s.

Each arm is one load of `https://www.facebook.com/` with `-Intl` and no
input. Each runs through `run-interactive.ps1` in the owner's session 1.
Never schedule or loop it. Arm 2 (the login) stays manual.

Before each arm it checks three gates, and a failed gate makes that arm
`UNMEASURED` without launching it:
- `quser` shows an `Active` session. `Disc` is not enough, because a
  disconnected session may mark the window occluded;
- no Windows `ninja` or `siso` process runs;
- commit headroom (`Win32_OperatingSystem.FreeVirtualMemory`) is at least
  8 GB. A WSL build holds most of the commit limit, so the command usually
  refuses while one runs.

It takes no `build_lock`. During an arm it polls headroom every 5 s and
force-stops the browser below 4 GB. Each arm is judged by
`observe_judge.py judge` against `D:\camou-win\observe\baseline-facebook.json`
(committed as `docs/observer/baselines/facebook-auto.json`). The command
prints one line per check, then `RESULT <verdict> <run dir>`, and exits with
the worst arm's code.

| verdict | exit | condition |
|---|---|---|
| `UNMEASURED` | 3 | `run.json` missing; `low_memory_kill`; `session != 1`; `session_state != Active`; `report_rc != 0`; `left > 0`; `trace_s < net_s - 5`; `discarded > 0` or buffer stats missing; `intl` is `null` (blind); arm 3 without cookies named `c_user` and `xs` (session expired); a GPU process crash line in the debug log; a failed gate; a timeout |
| `FAIL` | 1 | a baseline required group, `intl` included, has 0 calls on the facebook site |
| `PASS` | 0 | every required group is still above 0 |
| `INFO` | — | count change against the baseline, new group, new Intl built-in, `/ajax/bz` and total requests |

`<run dir>` is `D:\camou-win\observe\auto\<yyyyMMdd-HHmmss>`. The command
deletes the profile copies and `cookies.db` when it finishes. What stays on
the host:
- `arm<N>\trace.json`, `net.json`, `report.md`;
- `arm<N>\summary.json`, which holds names and counts only;
- `arm<N>.log`;
- `arm<N>\run.json`, with these keys:
  - `session`, `session_state`;
  - `wait_s`, `closed`, `left`;
  - `low_memory_kill`, `headroom_launch_gb`, `headroom_min_gb`;
  - `wsl_build`: the WSL build lock is held;
  - `gpu_exit_lines`: lines matching `GPU process exited unexpectedly` in
    `<profile>\chrome_debug.log`. On 2026-10-17 a launch in session 0
    logged 1 such line and a launch in session 1 logged 0, so this key
    detects the S4 crash;
  - `report_rc`, `started`, `ended`.

If `recon.ps1` throws, `arm<N>.log` gets `ERROR: <error record>` and its
script stack trace, then `EXIT=1`. The command echoes the `ERROR:` line
and the arm is `UNMEASURED` (`run.json missing`) at once, without waiting
out the arm's time limit.

A timeout stops the arm's scheduled task before it removes it: removing a
task leaves its running instance alive (host, 2026-10-17), and a late recon
would copy `cookies.db` after the cleanup. A judge that crashes or fails to
launch is `UNMEASURED`, never `FAIL` or `PASS`. A calibrated baseline with
no entry for the arm is a usage error. Against `{}` the judge adds
`INFO ... baseline requires 0 groups: PASS means measured only`.
`observe_judge.py baseline` refuses an unmeasured input with exit 2 and
writes no file.

**Baseline status.** Recalibrated on 2026-10-28 from two unattended runs on
the 156 `out\Observe` at 156.0.8078.48 (the release version), after the
2026-10-18 calibration on 156.0.8078.36. That build dates from 2026-10-22
and does not carry the change-set commits made after it (extension block,
WebRTC proxy policy, WebGL override timing, the GPU thread-cap validator,
the keyboard keys); none touch the observer or a facebook read surface.
The required groups are the same as before. Counts moved: arm 3
`layout-probe` fell from about 4100 and 3600 to about 3200 per load, and
its `canvas` from 8 to 2. The host file is
`D:\camou-win\observe\baseline-facebook.json`, and the committed copy
`docs/observer/baselines/facebook-auto.json` (the host's has CRLF line
ends). Arm 1 requires audio, canvas, intl, layout-probe, navigator,
screen, storage, webgl and webgpu. Arm 3 requires canvas, fonts, intl,
layout-probe, navigator, screen and storage. Arm 3's `fonts` is 1 call
per run, so a lone `FAIL fonts 0` may be one skipped call, not a change.
The owner decides whether to run again: tooling never re-runs on its
own. Recalibrate after a re-pin, and
whenever facebook's reads change for good. Measurements:
`docs/superpowers/measurements/2026-10-17-fb-observe-intl.md` §8.

**Expired login.** Arm 3 reports `session expired`. To refresh the backup:
1. The owner runs `recon.ps1 -Site facebook -Arm 2 -Intl -Force` and logs
   in by hand.
2. Run `robocopy D:\camou-win\observe\facebook\profile-arm2 <backup> /MIR`.
   This copies the whole profile, `Local State` included. The cookies are
   encrypted with that file's DPAPI-bound key, so a backup with a mismatched
   `Local State` reads as logged out.

**Recalibrating.** Spec §6:
1. Write `{}` to the host baseline.
2. Run the command twice.
3. Run `observe_judge.py baseline --arm 1 <run1>\arm1 --arm 1 <run2>\arm1
   --arm 3 <run1>\arm3 --arm 3 <run2>\arm3 -o <file>`. A group is required
   when both runs saw it.
4. Check that every required arm-3 group also appears in the manual
   2026-10-17 arm 3.
5. Commit the baseline, install it on the host, and judge both runs again:
   each must be `PASS`.

## Read

    cp <profile>/Default/Cookies /tmp/cookies.db
    python3 scripts/observe_report.py <trace.json> <net.json> --cookies /tmp/cookies.db

Per top-level site: surface group, API, reading origin, script, call count,
then a "Top scripts" table (each script's total calls and its three most-read
APIs); requests per host (query strings dropped); cookie names (values are
never read). The raw trace opens in https://ui.perfetto.dev.

The report's first line says whether the trace buffer (200 MB under
`record-as-much-as-possible`) discarded chunks. A full buffer stops the whole
trace while the browser keeps running, so the counts then cover only the start
of the session and are lower bounds; the netlog's requests are still complete.

Sections named `chrome://...` (the omnibox popup, the new-tab page) are
Chrome's own internal pages, not web content. Dedicated-worker reads carry no
site, so they land in a section named after the worker's origin (its
creator's), not under the page's top-level site.

`script` is the script at the top of the JavaScript stack when the API was
called, shown as host and path (query and fragment dropped). It separates a
page's own code from third-party scripts it includes as first-party code (for
example `connect.facebook.net/en_US/fbevents.js` under the page's origin). An
inline `<script>` reports its document's URL; code with no script (or `eval`
without a `sourceURL`) shows `(no script)`. A `blob:` or `data:` script shows as
`blob:` or `data:` alone (the rest is an object id or the code itself).

An event fires at the entry of the binding, before argument and receiver
checks, so a call that throws (for example a brand-check probe) still counts
as a read.

## Behaviour signals

Since the `observe-behaviour` patch the observer also reports (design:
`docs/superpowers/specs/2026-10-28-observer-behaviour-signals-design.md`):

- **Listener registrations by event type**, from every `addEventListener`
  overload and `on*` setter (`EventTarget.addEventListener[<type>] target=<interface>
  opts=<passive,capture,once>`), with the registering origin, site and script. A
  type is printed only if it is in the report's known set; any other type is
  counted under `[other]` and its name is never printed (a page can register any
  string).
- **Timing:** `Performance.now`, `requestAnimationFrame`, `setTimeout` and
  `setInterval`, with a calls-per-second figure per script.
- **Focus and visibility:** `Document.visibilityState`, `hidden`, the `webkit`
  forms and `hasFocus`.
- **Clipboard:** the `Clipboard` and `ClipboardItem` interfaces and
  `Document.execCommand`.
- **Motion and orientation:** the `DeviceMotionEvent` and `DeviceOrientationEvent`
  classes and the Generic Sensor classes.

A registration is counted, not how often the listener fires or what it does. A
duplicate registration still counts (the page asked), and an `on*` handler
re-assigned after its first assignment does not. With the category on, each
call adds about 2 to 4 microseconds, which `performance.now` timings include:
do not use the timing rows to judge timing detectability. Report groups:
`input-events`, `focus-visibility`, `clipboard`, `motion`, `timing`,
`listeners-other`.

## What it cannot see (silence is not safety)

- V8 built-ins `Date.prototype.getTimezoneOffset` (a CSA builtin) and `Math`;
  Intl only with the Intl recipe.
- CSS `@media` rules in stylesheets (only `matchMedia` is seen).
- Font enumeration through layout beyond the listed layout members.
- TLS/JA3, HTTP/2 framing, server-side computation.
- Values: a row says a page read `deviceMemory`, not what it got.
- Named and indexed access (`localStorage.foo`, `navigator.plugins[0]`) goes
  through interceptors and is not observed.
- Dispatch: how often a listener fires and what its handler does.
- `Date.now`, `performance.timeOrigin`, `PerformanceObserver`, `queueMicrotask`,
  `requestIdleCallback`, scroll offsets, `document.execCommand`'s command.

## Detectability

The observer is an audit tool, not a stealth mode. With the category off, each
allow-listed call costs one category check. With it on, each call writes a
trace event. Measured with only the observer category enabled (`-*,` filter),
content_shell on the build box, 200 000 `navigator.userAgent` reads and 300
`toDataURL` calls. This is a worst-case microbenchmark, not a page-load cost.
The numbers come from `scripts/verify_observe.py --timing`; its "off" row ran
with `blink,loading` tracing on and the observer category off, so it is not a
no-tracing baseline:

| category | `ua_200k_ms` | `todataurl_300_ms` |
|---|---|---|
| off | 88.5 | 29.6 |
| on | 512.1 | 30.6 |

A single run on 2026-10-08 (after the fast-call hook) measured off 75.6 /
29.5 ms and on 788.9 / 30.9 ms. The on-arm `navigator.userAgent` rise is
more than 10x what the hook's extra `HandleScope` and script-name copy cost,
and the off arm moved 15% the other way in the same session, so it is not
attributed to the hook; it needs repeated runs before replacing the numbers
above.

Three runs on 2026-10-13, on the build with `v8_enable_runtime_call_stats =
true`. `intl` is the Intl recipe. `trace_bytes` is the `timing.html` trace.

| recipe | `ua_200k_ms` | `todataurl_300_ms` | `trace_bytes` |
|---|---|---|---|
| off (`blink,loading`) | 92.9-94.7 | 29.1-30.3 | 244 830-247 911 |
| on | 854-884 | 32.9-33.6 | 52 533 915-52 535 207 |
| intl | 944-1006 | 31.8-34.1 | 52 548 451-52 550 560 |

The Intl recipe adds 8-14% to the on-arm getter loop. Its call stats time
every built-in and runtime call. It adds about 15 KB of `v8` events to this
page's trace. With the stats category off, the compiled-in counters cost one
flag check per C++ built-in: CI's browser verifies on this build matched
main's (2026-10-13).

Browse a site normally, on a release build, when staying hidden matters.

## Data handling

Traces, netlogs and profiles hold the operator's real browsing. Keep them on
the machine that made them. Commit only names, counts, hosts and
query-stripped paths. Ids inside a path (account ids, pixel ids, as in
`signals/config/<pixel-id>`) are redacted in committed data; the report prints
paths as they are, so redact before committing.

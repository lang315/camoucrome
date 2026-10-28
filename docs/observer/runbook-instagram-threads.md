# Instagram and Threads recon, arms 2 to 4: owner's runbook

Status: prepared 2026-10-28, not run. The owner does these arms **by hand**. Tooling never automates Meta beyond
`observe-auto.ps1`'s facebook arms 1 and 3 (owner's rule of 2026-10-17); this runbook adds no unattended launch, no
scheduler, no login automation and no loop. Tooling never types credentials and never reads the login profile for values.

Arm 1 (logged-out landing) already ran for both sites on the phase-1 build (2026-10-07) and was not analysed. Arms 2 to 4 are
what is left (`docs/observer/followups.md`).

## What each arm measures

| Arm | What the owner does | Profile |
|---|---|---|
| 1 | Logged-out landing, wait 30 s, close the browser. | fresh |
| 2 | Log in by hand, wait for the feed, close the browser. | fresh |
| 3 | Browse the feed about 2 minutes on arm 2's profile, close the browser. | arm 2's profile |
| 4 | Open a public third-party page that embeds the Meta Pixel or a social plugin, wait about 30 s, close the browser. Note the URL. | fresh |

Run them for `instagram` and for `threads` (account of the owner's choice; one account per site, owner-managed).

## Before the session (prerequisites)

1. **A build with the new hooks.** Arms 2 to 4 are only worth running on an `out\Observe` that carries the behaviour
   signals (#38: listeners by type, timing, focus, clipboard, motion) and, if built, the dispatch counts. That is the
   Windows 157 tree. Until it exists, a run answers the old fingerprint-read questions only. **Blocked on:** the Windows
   157 `out\Observe` (track A4). Ask click-camou for the slot; do not start before it.
2. **The recon launcher on the host is current.** `D:\camou-win\observe\recon.ps1` must be byte-equal to
   `scripts/windows/observe-recon.ps1` of main (`shasum -a 256` on both; `-Intl` needs `v8_enable_runtime_call_stats = true`
   in that build). Same for `D:\camou-win\observe\observe_report.py` against `scripts/observe_report.py`.
3. **The owner's interactive session is Active** (RDP or console, session 1). Run the commands from a PowerShell in that
   session, not from sshgate: a manual arm needs a visible window anyway.
4. **Headroom.** At least 8 GB commit headroom free, and no native Windows build running (the same gates as
   `observe-auto.ps1`). Check with Task Manager, Performance, Memory, "Committed".
5. **Time.** About 10 minutes per arm; 30 to 40 minutes for all four arms of one site.

## Commands (owner, in the interactive PowerShell)

    cd D:\camou-win\observe
    powershell -NoProfile -ExecutionPolicy Bypass -File .\recon.ps1 -Site instagram -Arm 1
    powershell -NoProfile -ExecutionPolicy Bypass -File .\recon.ps1 -Site instagram -Arm 2
    powershell -NoProfile -ExecutionPolicy Bypass -File .\recon.ps1 -Site instagram -Arm 3
    powershell -NoProfile -ExecutionPolicy Bypass -File .\recon.ps1 -Site instagram -Arm 4

Then the same four lines with `-Site threads`. Add `-Intl` to any line to also count Intl built-ins. A directory that
already holds files needs `-Force` (it deletes that arm's old files and, for arms 1, 2 and 4, its profile). Arm 3 refuses to
start until arm 2's profile exists.

Each command prints what to do in that arm, opens the browser headed on the right start page (arm 4: no start page, type
the URL), waits until the browser closes, then runs the report. **Close the window normally; do not kill it**, or no trace
is written.

## What you type, and what is never done

- The owner types the username and password in arm 2, and a two-factor code if asked. Nothing is typed by a tool.
- Do not log in on the profile of any other arm. Do not reuse a profile across sites.
- Do not run an arm twice in a row to "fix" a bad one without saying so: a repeat is a second measurement, written down as
  such (facebook's baseline took seven loads on purpose).
- No scheduled task, no loop, no unattended repeat.

## After each arm

The launcher leaves the files in `D:\camou-win\observe\<site>\arm<N>\`: `trace.json`, `net.json`, `cookies.db`, `report.md`.
These hold real browsing: they **stay on the host**, are never copied off and never committed (`README.md`, "Data
handling").

1. Read `report.md` on the host. Look first at the header: it must not say `discarded > 0` (a full buffer stops the trace and
   the arm is `UNMEASURED`, rerun it) and the Intl line must say what it measured or `blind`.
2. For the measurement doc, the only things that leave the host are names, counts, hosts and query-stripped paths, with
   ids redacted. Tell the controller session what you want in the doc and it reads `report.md` through sshgate with a
   script that prints only those fields.
3. If the profile of arm 2 holds a live login, treat the whole `profile-arm2` directory as secret: no backup copy leaves
   `D:\camou-win\observe`. Delete it when the measurement is done unless the owner wants a backed-up login for a later
   unattended arm (which would need its own owner decision and spec, as facebook's did).

## Baseline and judge

`observe_judge.py` judges against a per-site baseline (`baseline-facebook.json`). There is no Instagram or Threads
baseline. Arms 1 and 3 of these runs can calibrate one (as facebook's two unattended runs did), but a baseline from a
single manual load is not a calibration: the report says `INFO ... measured only`. Decide with the controller whether
these arms are discovery (no judge) or the start of a baseline; either way they are discovery on their first run.

## Open points for the controller

- Which build and which date: after the Windows 157 `out\Observe` exists (A4's precondition), not before.
- Whether the arms use `-Intl` (needs the RCS build; the Windows `out\Observe` was last rebuilt with it on 2026-10-13).
- Which accounts the owner uses; tooling needs no account detail and the doc records none.
- Whether the measurement doc gets a "committable summary" script for these sites (like the facebook inventory's
  aggregator). Not written yet: it needs no new tool if the report's tables are enough.

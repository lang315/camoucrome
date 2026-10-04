# Safe Browsing phone-home: measured, then closed (backlog item 4)

Roadmap backlog item 4. The re-pin to 154 (`2026-10-repin.md`, "P1: a new
external request on the 154 base") saw `safebrowsing.googleapis.com` once in
six `verify_sp7_phonehome` runs and called it intermittent. It is not
intermittent. It happens on every start; the 75 s window was too short to see
it most of the time.

## 1. Why one run in six

The first Safe Browsing list update is scheduled by
`SBUpdateProtocolManager` at a uniformly random delay between
`kTimerStartIntervalSecMin = 60` and `kTimerStartIntervalSecMax = 300` seconds
(`components/safe_browsing/core/browser/db/sb_update_protocol_manager.h:36-38`).
A 75 s window covers 15 of those 240 seconds, so it catches the fetch about
one start in sixteen. The request is `POST
https://safebrowsing.googleapis.com/v5/hashLists:batchGet`
(`v5_update_protocol_manager.cc:167`).

The switch `--safebrowsing-fast-initial-lists-update` (the string in
`safebrowsing_switches.cc:49`) narrows the delay to 10–20 s. The verify passes
it, so the fetch now lands in every window. The first draft used the name
`--sb-fast-initial-lists-update`, which Chrome does not know. Its "RED" run was
green, and that is how the wrong name was caught.

## 2. The lever

`patches/sp7-phone-home.patch` gains one hunk. In
`components/safe_browsing/core/common/safe_browsing_prefs.cc`, the
`prefs::kSafeBrowsingEnabled` default changes from `true` to `false`.

- This is the "No protection" setting that a real Chrome user can choose, the
  same kind of lever as the other nine in sp7 (a default the tree already
  supports). With it, `SafeBrowsingService` never starts the local database
  manager, so no list update is scheduled.
- Decided with the owner on 2026-10-04. The alternatives were:
  - keep Safe Browsing on and stop only the list fetch (`disable_auto_update`):
    a state no real user is in, and lookups would still go out;
  - a config key to choose: one more key, for no measured need.
- The cost, stated: no phishing or malware protection by default. A user with
  a kept profile can turn it back on in Settings.

On the box branch, the hunk was folded into the `sp7-phone-home` commit with
`--fixup` and `rebase --autosquash`. The branch is still 38 commits above the
pin, with the same subjects. `export.sh` changed `sp7-phone-home.patch` only
(+17 lines), and `check_checkout_sync.sh` reports "PASS all 41 copied files
are identical". The patch's sha256 is `7140164c…c769` on the box and in the
repo.

## 3. Results on Linux (`out/Default` chrome, WSL)

| run | P1 external hosts | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|
| RED, before the lever (4 runs: 75 s ×3, 30 s ×1) | `{"safebrowsing.googleapis.com": 1}` every time | PASS | PASS | PASS* | PASS |
| GREEN, with the lever (75 s ×3) | `{}` | PASS | PASS | PASS* | PASS |
| GREEN, 330 s window (beyond the 300 s timer maximum) | `{}` | PASS | PASS | PASS* | PASS |

\* The P4 rows in this table predate the P4 fix in §5, so they measured
nothing. P4 run on its own after the fix: `reused = True`, no
`x-client-data`, PASS.

Build: `2m02s Build Succeeded: 134 steps` for the lever, and `1m57s, 134
steps` again after a comment-only correction. `gn check` on
`//components/safe_browsing/core/common:safe_browsing_prefs`: "Header
dependency check OK".

The 330 s run also covers every other timer-driven caller in the 60–300 s
range. Nothing else appeared.

CI's browser verify list on the lever build is unchanged from `main`:
- `sp1a_chrome` PASS;
- `sp4_voices` 5/5;
- `fonts_bundle` 17/0;
- `host_oracle` 4/0;
- `windows_behaviour` 14/0;
- `sp6b_generator` ALL_PASS;
- `crash_dumps` 2/0;
- `sp7_fieldtrial` C4 PASS.

P5 (navigation premise): in every run, the netlog held the request to
`sb.test`, a non-IP name mapped to loopback. No navigation-time Safe Browsing
lookup appeared, even on the RED build. So the real-time lookup path is
**not** shown to phone home on this build. The lever closes it anyway, because
it gates the whole service, but that claim is not measured.

## 4. Results on Windows (`out\Release` chrome.exe 154, the host)

RED, before the lever (two runs):
- P1 `{"chromewebstore.googleapis.com": 1, "safebrowsing.googleapis.com": 1}`;
- P2, P3 and P5 PASS;
- P4 FAIL on the first run (a harness defect, §5) and PASS on the second, after
  the fix.

`chromewebstore.googleapis.com` appears only on Windows. It is not Safe
Browsing and is filed as its own item. See the roadmap.

Change loop (runbook §7):
1. Lock `windows backlog4`.
2. `git apply --include=components/safe_browsing/core/common/safe_browsing_prefs.cc`
   of the revised patch.
3. Prove the result: `git apply --check -R` of the whole revised patch exits
   0, so the tree carries all ten files exactly. The blob is `7bef349864`,
   the same as WSL.

Build: `28.47s Build Succeeded: 5 steps`.

GREEN, with the lever (two runs):
- P1 `{"chromewebstore.googleapis.com": 1}`, so Safe Browsing is gone in both
  runs;
- P2, P3, P4 and P5 PASS. P4 reused the profile (`reused = True`), and no
  `x-client-data` was seen.

`verify_sp7_phonehome` therefore still exits 1 on Windows, and its only
external host is the Web Store request. That request is the open item; it is
not part of this lever.

There was no regression on Windows. `windows_verify_set.py green` on the lever
build (tree `90064e7`) read `21/21 entries OK (green)`, EXIT 0, with the same
counts as PR #22. The host oracle's O2 is still the only known-failing row
(roadmap backlog 8).

**Blink relink on `out\Release`.** The roadmap deferred a Windows component
build until this was timed. The test: set the mtime of
`third_party/blink/renderer/core/frame/navigator.cc` (content hash
unchanged), then rebuild. Result: `38.38s Build Succeeded: 49 steps`. A
one-file Blink change relinks the release `chrome.dll` in under a minute on
the i7-10700, so a Windows component build buys nothing for iteration and is
not needed.

## 5. Two harness defects found on the way

**A truncated netlog scored FAIL, not "could not measure".** Two 75 s runs on
2026-10-04 left a netlog that did not parse, and the 30 s run's did. The old
repair appended `]}` to the whole document, which cannot close a file cut
inside the `polledData` line.
- `parse_hosts` now reads the log line by line: constants on line 1, one event
  per line after it. Only the last event line may fail to parse. A bad line
  anywhere else raises, and P1/P2/P5 then print `UNMEASURED` with exit 2.
- `scripts/test_verify_sp7_phonehome.py` (5 tests, added to CI's pytest list)
  pins the behaviour. Its polledData case failed on the old parser.

**P4 measured nothing on Linux and timed out on Windows.** P4 needs two launches
on one profile, so it passed `--user-data-dir` in `extra_flags`, next to the
one `lib_shell.launch()` appends. With two such flags, Chrome on Linux takes
the **last** and Chrome on Windows the **first**. Measured with both binaries:
`DevToolsActivePort` appeared in the second directory on Linux and the first
on Windows.
- On Linux, both launches therefore ran on fresh profiles, and "no
  `x-client-data` on launch 2" proved nothing. On Windows, `launch()` polled
  the wrong directory and timed out after 30 s.
- `launch()` now takes `user_data_dir=`, which replaces its own temp profile.
  `shutdown()` leaves that profile in place. Two checks in
  `test_lib_shell_launch.py` pin this (26 PASS). The default argv is
  unchanged.
- P4 now asserts its premise: `Local State` from launch 1 must exist before
  launch 2. That row went RED on Linux before the `launch()` change and GREEN
  after it.
- Not re-checked: `verify_media_ii.py`'s docstring cites a
  `shared_profile_probe.py` that "rotates even with a shared
  --user-data-dir". The probe is not in the repo, so whether it hit the same
  duplicate-flag trap is unknown.

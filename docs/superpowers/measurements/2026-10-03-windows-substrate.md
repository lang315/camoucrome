# Step 1: the Windows verify substrate (2026-10-03)

Recorded from the task reports of the slice. The plan is
`docs/superpowers/plans/2026-10-03-step1-windows-substrate.md`. Every command
and output below is quoted from those reports; nothing was re-run for this
document.

The Windows binary under test is the existing native build,
`D:\camou-win\chromium\src\out\Release\chrome.exe`, on the **old pin**
(`507c6ee3e2`, 153.0.8010.36). Nothing under `D:\camou-win\chromium\src` was
modified and no build was started.

Every command went through the sshgate MCP server (server `buildpc`). The ssh
session lands in Windows PowerShell 5; WSL scripts were passed base64-encoded.

## The host verify environment

The verify tree was copied from the runner clone at repo commit `ab0644c`
(`HEAD == origin/main`, `git status --porcelain` empty):

```
porcelain:[]
Name: playwright
Version: 1.55.0
HEAD ab0644c origin/main ab0644c
```

That `Version: 1.55.0` is the **build box's** playwright
(`/home/lang/camoucrome-verify/venv/bin/python3 -m pip show playwright`). The
host venv, made from Python 3.9.13 (`C:\Program Files\Python39\python.exe`; the
controller ran `& 'C:\Program Files\Python39\python.exe' -V` before the plan,
which printed `Python 3.9.13`):

```
$py='D:\camou-win\verify-venv\Scripts\python.exe'; & 'C:\Program Files\Python39\python.exe' -m venv D:\camou-win\verify-venv; ...; & $py -m pip install -q playwright==1.55.0; ...; & $py -m pip show playwright | Select-Object -First 2; & $py -c "import playwright; print(playwright.__file__)"
```

```
venv rc=0
pip-upgrade rc=0
playwright rc=0
Name: playwright
Version: 1.55.0
D:\camou-win\verify-venv\lib\site-packages\playwright\__init__.py
```

So the host and the box run the same playwright, 1.55.0. The verify tree is
`D:\camou-win\verify` (`scripts`, `settings`, `baselines`, `client`), and
`lib_shell` resolved these paths there, with `CAMOU_OUT` set to
`D:\camou-win\chromium\src\out\Release`:

```
D:\camou-win\chromium\src\out\Release\content_shell.exe
D:\camou-win\chromium\src\out\Release\chrome.exe
C:\Users\lang315.DESKTOP-UNVOE92\AppData\Local\Temp\camoucrome_verify_stderr.22272.log
Layout(home='C:\\Users\\lang315.DESKTOP-UNVOE92', py='C:\\Users\\lang315.DESKTOP-UNVOE92/camoucrome-verify/venv/bin/python3', node='C:\\Users\\lang315.DESKTOP-UNVOE92/camoucrome-driver/node', client=WindowsPath('C:/Users/lang315.DESKTOP-UNVOE92/camoucrome-client'), fonts_dir='C:\\Users\\lang315.DESKTOP-UNVOE92\\camoucrome-client\\fonts')
```

`SHELL` prints `content_shell.exe`, which does not exist in this release out
dir; the Windows verifications go through `CHROME`. With a bogus
`CAMOU_OUT=D:\no-such-out` the same call prints `D:\no-such-out\chrome.exe`
(computed, not checked: it proves the path follows the variable, not that the
file exists).

### The transport correction

The plan's premise was that WSL can write `/mnt/d`. **That is wrong on this
machine.** `/etc/wsl.conf` has `[automount] enabled=false` (set by the runner
hardening in `2026-10-repin.md`), so `/mnt/d` inside WSL is a plain directory
on the WSL ext4 disk, not the Windows D: drive. The probe that justified the
premise was the controller's pre-plan probe (before the plan was written; it is
not in the task reports): `test -d /mnt/d && echo yes` plus a touch-and-remove
of a file there. It passed while the files landed nowhere Windows could see:

```
Get-PSDrive: C, D, E exist on Windows.
Test-Path D:\camou-win\verify-venv -> True ; D:\camou-win\verify did not exist.
WSL: ls -ld /mnt/d/camou-win/verify -> drwxr-xr-x 6 lang lang ... Oct  3 06:21
WSL: ls /mnt/d -> camou-win          (only the dir step 2 created)
/etc/wsl.conf: [automount] enabled=false ; [interop] enabled=false
ls /mnt -> c d e wsl wslg   (empty mountpoints)
```

The working direction is **from Windows**, through the WSL UNC share, copying
what WSL staged:

```
$src='\\wsl.localhost\Ubuntu-24.04\mnt\d\camou-win\verify'; New-Item -ItemType Directory -Force D:\camou-win\verify | Out-Null; Copy-Item "$src\*" D:\camou-win\verify -Recurse -Force; "copy ok=$?"; ...
```

```
copy ok=True
...
files src/dst: 140 / 140
```

A stray `/mnt/d/camou-win/verify` remains inside WSL; it was not deleted.
Reachability of the UNC share was probed with a job and a timeout first,
because a bare UNC probe once hung a call. (The runner-hardening note in
`2026-10-repin.md` says `\\wsl.localhost\…` was not reachable from the ssh
session at that time; here it was. The reports do not explain the difference.)

## The first native green: `verify_sp2b.py`

Run from `D:\camou-win\verify\scripts` with the host venv's python. RED
control first, a `CAMOU_OUT` that points nowhere:

```
$env:CAMOU_OUT='D:\no-such-out'; & $py verify_sp2b.py 2>&1 | Select-Object -Last 6; "red exit=$LASTEXITCODE"
```

```
FAIL  1 un-configured move produces exactly one mousemove
FAIL  2 humanize:enabled move produces more than one mousemove, ending at the target
FAIL  3 humanize:enabled events trace the path, not just the endpoint
      criterion 1 session: FileNotFoundError: [WinError 2] The system cannot find the file specified
      criteria 2/3 session: FileNotFoundError: [WinError 2] The system cannot find the file specified
red exit=1
```

0 of 3, exit 1. Then the real `CAMOU_OUT`:

```
$env:CAMOU_OUT='D:\camou-win\chromium\src\out\Release'; & $py verify_sp2b.py 2>&1; "sp2b exit=$LASTEXITCODE"
```

```
PASS  1 un-configured move produces exactly one mousemove
PASS  2 humanize:enabled move produces more than one mousemove, ending at the target
PASS  3 humanize:enabled events trace the path, not just the endpoint
sp2b exit=0
```

3 of 3, exit 0. Criteria 2 and 3 can only pass if the configured behaviour
differs from criterion 1's unconfigured run, so `CAMOU_CONFIG` reached the
**browser process** for the humanize key. It is the browser process, not the
renderer: `patches/sp2b-humanized-cursor.patch` touches exactly two files,
`content/browser/devtools/protocol/input_handler.cc` and `.h`, and its three
config reads (`camoucfg::GetBool` / `GetInt32`, both with
`camoucfg::GlobalScope()`) are in that browser-process file. That is the one
key this proves, and only for that process.

## `tempfile.gettempdir()` replaced `/tmp`

`lib_shell.STDERR_LOG` is `%TEMP%\camoucrome_verify_stderr.<pid>.log`; the
filename embeds the PID. The first probe at the end of the combined call was
invalid for that reason (a fresh `python -c` has a new PID), so it is not
evidence. The listing taken after the runs:

```
=== temp logs
camoucrome_verify_stderr.23252.log      0 10/3/2026 1:30:44 PM
camoucrome_verify_stderr.3132.log     226 10/3/2026 1:30:42 PM
camoucrome_verify_stderr.4308.log       0 10/3/2026 1:30:39 PM
```

and the content of the 226-byte one:

```
=== log 3132
DevTools listening on ws://127.0.0.1:49789/devtools/browser/4e7dc248-7f67-4175-962f-69ea94f67a63
[9304:9892:1003/133042.066:ERROR:content\browser\gpu\gpu_process_host.cc:1054] GPU process exited unexpectedly: exit_code=34
```

A real log under the host's `%TEMP%`, non-empty, with the
`DevTools listening on` line the verifications read. The two 0-byte siblings
are launches that failed with `FileNotFoundError` or crashed before output.
The old hardcoded `/tmp` has no meaning on this host.

## `verify_sp7_fieldtrial.py`: exit 1

```
note: F1/F4 launch: FileNotFoundError: [WinError 2] The system cannot find the file specified
note: F2 launch: FileNotFoundError: [WinError 2] The system cannot find the file specified
note: F3: FileNotFoundError: [WinError 2] The system cannot find the file specified
note: C1: 'Applying FieldTrialTestingConfig' count = 0 (expect 0; RED build 1)
note: C2: chrome.exe exited during startup, code 3221225477
F1: FAIL
F2: FAIL
F3: FAIL
F4: FAIL
C1: PASS
C2: FAIL
C4: PASS
sp7 exit=1
```

Triage, per row. The classes: (a) the patch is absent, (b) a Linux-only
dependency, (c) a real Windows difference.

| Row | Verdict | Class | Cause |
|---|---|---|---|
| F1 | FAIL | (b) | needs `content_shell.exe`; a Windows release build has none (`[WinError 2]`) |
| F2 | FAIL | (b) | same |
| F3 | FAIL | (b) | same |
| F4 | FAIL | (b) | same |
| C1 | PASS | n/a | count 0 from a non-empty capture (C4 PASS on the same log), so not vacuous |
| C4 | PASS | n/a | `DevTools listening on` present in the 226-byte log |
| C2 | FAIL | **(c)** | see below |

F1-F4 say nothing about the fork; they are unmeasured on Windows.

**C2 is the only (c).**

- (a) is ruled out. The mechanism is not a source patch:
  `sp7-phone-home.patch` touches no variations or field-trial file; it is the
  GN arg `disable_fieldtrial_testing_config = true`, `out\Release\args.gn:19`.
  The guard `git diff --stat | Select-String 'field_trial|variations'` (and
  `git status --short` likewise) returned empty, which fits that, but it is not
  evidence of absence of the arg. The binary itself prints, with the flag:

  ```
  --enable-field-trial-config was passed, but the field trial testing config was excluded from the build.
  ```

- (b) is ruled out. C2 launches `chrome.exe`, which exists; the control run
  without the flag stays alive and prints `DevTools listening`.
- (c): the exclusion fires, and the process then terminates with `0xC0000005`
  (`STATUS_ACCESS_VIOLATION`) where Linux exits with code 1 (`puts` +
  `exit(1)` in `VariationsServiceClient::ExitWithMessage`). C2 asserts code 1,
  so it fails. Exit codes from three direct runs:

  ```
  run 1 exit=-1073741819
  run 2 exit=-1073741819
  run 3 exit=-1073741819
  ```

  `-1073741819` is `0xC0000005`, the same value as the script's `3221225477`.
  With the script's own run that is four runs, all the same. The cause of the
  access violation is not determined (it would need a crash dump or a
  debugger), and no stock-Chrome comparison exists, because stock builds
  include the testing config and never take this path. Filed as backlog item 5
  in the long-term roadmap.

The brief expected the RED error to name the missing binary. In `verify_sp2b.py`
it does not: the script catches the exception and prints only
`[WinError 2] The system cannot find the file specified`.

## The Windows tree's state for the next re-pin

`D:\camou-win\chromium\src` is at the pin and carries the change set as an
`apply.sh` application with no way back. Derived on the box from the repo at
`3d78ae2` (the series at that commit has 32 lines), compared with
`git status --porcelain -uall` on the host.

```
series-lines: 32 / sp0-config-layer.patch / sp1a-ua-producer.patch / sp5a-coherence-validator.patch
patched: 89 additions: 40
507c6ee3e2f3b2ca0e660547e5b9ea4820c67f4c   (HEAD of Windows tree)
total 130 ; [??] 41 ; [M ] 89 ; expected unique 129 ; dirty unique 130
git stash list: 0 ; cached stat: 89 files changed, 3020 insertions(+), 114 deletions(-)
```

**Path counts.** 130 dirty paths = 89 patched (staged) + 41 untracked. The 41 are
the 40 files of `additions/` plus `components/camoucfg/invariants.json`, which
`apply.sh` copies from `settings/invariants.json`
(`3d78ae2:scripts/apply.sh:39`). With additions mapped to `components/` the
only row the first comparison left over was `components/camoucfg/invariants.json`;
nothing was unexplained in either direction. Two traps cost time here:
PowerShell's `-like '??*'` treats `?` as a wildcard, so every line matched
(`90 / 90 / 0`, invalid), and `git status --porcelain` without `-uall`
collapses untracked directories (90 lines, not 130).

**New files, byte level.** `git hash-object --no-filters` against the blobs at
`3d78ae2`: **41 of 41 identical.**

**Patched files, byte level.** The pristine blobs of all 89 paths were taken
from the host (`git show HEAD:f`), copied to WSL, and the 32 old patches
applied in series with plain `git apply` (no error output). Result of
hashing the replay against the host's working files:

```
byte-compared 89 differing 0
```

**All 89 patched files are byte-identical** to the 32 old patches replayed on
the pristine pin.

**How the counts disagreed on three files.** Staged `diff --cached --numstat`
(89 files, +3020/-114) against the per-patch `git apply --numstat` sums at
`3d78ae2` (89 files, 14 of them touched by more than one patch): 86 identical,
3 differ.

| file | patches | staged (add/del) | summed per patch (add/del) |
|---|---|---|---|
| `browser_main_loop.cc` | 3 | 187/0 | 207/20 |
| `local_font_face_source.cc` | 2 | 36/0 | 38/2 |
| `speech_synthesis.cc` | 2 | 293/0 | 308/15 |

The net (add minus delete) is equal in each. The cause is summing across
patches: a line one patch adds and a later patch removes counts in both sums
but cancels in the working file. The replay above is what settles it; the
numstat comparison alone could only say that the counts were consistent with
that reading.

**GN args.** `out\Release\args.gn` was read whole (21 lines). Lines 8 to 19
equal `settings/release-args.gn`'s keys and values (compared by eye, not a
byte diff), plus `target_cpu = "x64"` at line 21. `is_component_build = false`
(line 9), `proprietary_codecs = true` (line 17),
`disable_fieldtrial_testing_config = true` (line 19).

**Git Bash.** Two `bash.exe` exist, and the `PATH` `bash` is the WSL launcher.
`& $p -c 'echo ok; uname -s; git --version; bash --version | head -1; command -v git'`:

```
bin\bash.exe:     ok / MINGW64_NT-10.0-19045 / git version 2.51.2.windows.1 / GNU bash, version 5.2.37(1)-release (x86_64-pc-msys) / /mingw64/bin/git
usr\bin\bash.exe: ok / git version 2.51.2.windows.1 / /cmd/git
                  stderr: uname: command not found, head: command not found
```

`usr\bin\bash.exe -l -c 'uname -s; head --version | head -1; command -v git'`
does find coreutils:

```
MSYS_NT-10.0-19045 / head (GNU coreutils) 8.32 / /cmd/git
```

Whether `apply.sh` runs under either was not measured.

The runbook section for all of this is section 7, "The Windows tree", of
`docs/superpowers/specs/repin-runbook.md`. Its eight code blocks were extracted from the document text and
run mechanically in one call, with the deviations `task-4-report.md` discloses:
PowerShell lines were joined with `; ` (sshgate refuses newlines), comment lines
were dropped, and the prose `--include=<path>` variant of `git apply` was not
re-run (it was used in an earlier round, for the 3 files, not in the all-89
replay): `dirty 130 expected 130` with an empty
`Compare-Object`, `checked 41 differing 0`, the same three DIFF rows above,
and `byte-compared 89 differing 0`.

## What this does not establish

- **The Windows component build.** `out\Default` was not built or timed; the
  tree has only the release build.
- **The change loop, end to end.** `apply.sh` and `rebuild_branch.sh` were
  deliberately never run in the Windows tree. The tree state above is read and
  compared, not changed. Edit, export and re-apply on Windows is unproven, as is
  whether they run under either Git Bash.
- **The Go and Node clients.** Only `lib_shell` and `verify_sp2b.py` ran. The
  clients under `client/` were copied (as part of the 140-file verify tree:
  scripts, settings, baselines and client; `client/` alone is 24 tracked files at
  `ab0644c`) and not executed.
- **Fonts on Windows.** Nothing here touches a font surface.
- **Every baseline-comparing verification.** The binary is 153.0.8010.36 and
  the Windows-relevant committed baselines describe 154.0.8037.93 (others do not:
  `baselines/chrome-0e8d4a9268-stock-ua.json` is 154.0.8026.0,
  `baselines/chrome-7922-stock-font-metrics-macos.json` is 151.0.7922.138, and
  `baselines/content_shell-sp0-stock-ua.json` is neither), so such a verification would
  differ on the Chrome version, not on the fork. Only behavior-asserting
  verifications ran, and of those, one: `verify_sp2b.py` passes; the other
  executed, `verify_sp7_fieldtrial.py`, fails at 4 rows for want of
  `content_shell.exe` and at C2 for the crash above.
- **`layout()`'s `py` and `node` fields.** They are Linux-shaped on the host:
  `.../camoucrome-verify/venv/bin/python3` and `.../camoucrome-driver/node`
  under the Windows home (no `Scripts\python.exe`, no `.exe`). They do not exist
  there, and nothing exercised in this slice spawns them. Anything that does
  will fail.
- **`launch()`'s "exited during startup" message naming the binary.** Proven on
  Linux, not on Windows. Through `verify_sp2b.py` a missing binary surfaces
  only as `[WinError 2] The system cannot find the file specified`, with no
  path. (`verify_sp7_fieldtrial.py` C2 did print
  `chrome.exe exited during startup, code 3221225477`, but that is a process
  that started and crashed, not a binary that is absent.)
- **`CAMOU_CONFIG` reaching the browser process beyond one key.** The humanize
  key in `sp2b` is the one exercised here; F3 (`navigator.hardwareConcurrency`)
  did not run.
- ~~**Any renderer-consumed key on Windows.**~~ **Closed the same day — see
  "The renderer under the real sandbox" below.** What this entry said when it was
  written stays true of `verify_sp2b.py` itself: the only renderer-side row in
  that part of the slice, F3, never ran, because a Windows release build has no
  `content_shell.exe`, and `launch()` hardcoded `--no-sandbox`
  (`scripts/lib_shell.py:282`), which bypasses the environment filter the
  project's only Windows-specific bug lived behind
  (`2026-09-24-review-triage.md:183`): Windows launches renderers and utilities
  with `SetFilterEnvironment(true)`, `CreateFilteredEnvironment()` strips every
  `CAMOU_*` variable, and `navigator.hardwareConcurrency` read the real 16 under
  the default sandbox and the spoofed 3 under `--no-sandbox`. So the argv that
  produced the `verify_sp2b.py` green is the one argv under which that bug is
  invisible, and the process it exercised is the one the filter never touched.
  That is why `launch()` gained a `sandbox` parameter and why the measurement
  below exists.
- **`CAMOU_EXE`.** The third knob PR #4 shipped. `CAMOU_OUT` and
  `tempfile.gettempdir()` were exercised on Windows; `CAMOU_EXE` was not.
- **"Closes" PR #4's caveat.** This slice is the first native green, not a
  closure of that caveat; everything above remains unverified on Windows.
- **Whether the access violation is the fork's.** Root cause is unknown; no
  crash dump was taken.

## The renderer under the real sandbox

Added later the same day. The section above says a Windows renderer-surface
verification needs a run without `--no-sandbox`, which `launch()` could not
produce. `launch()` and `session()` now take `sandbox=False`, and passing
`sandbox=True` omits the flag. The default keeps every earlier call's argv
byte-identical; `scripts/test_lib_shell_launch.py` freezes it and pins that
`--no-sandbox` is still `argv[1]` by default (19 PASS).

The first measurement with it, on the host, against the same 153 `chrome.exe`:

```
A no-sandbox + config: ([3], None)
B sandboxed + config: ([3], None)
C sandboxed, no config: ([16], None)
```

B is the row nothing committed could reach before. The `windows-sandbox-env`
patch holds under the real Windows sandbox: a renderer-consumed key reads the
configured value with the environment filter in force. C is why B means anything
— the same sandboxed launch with no config reports this machine's real 16, so B's
3 did not come from a hardcoded default, a stale profile, or this probe.

That is now a committed verification, `scripts/verify_windows_sandbox_env.py`,
whose W2 row *is* that control. Seen RED first, with `CAMOU_OUT` pointing at a
directory holding no binary:

```
note: W1: sandboxed + config -> None (expect 3); FileNotFoundError: [WinError 2] The system cannot find the file specified
note: W2: sandboxed, no config -> None (expect anything but 3); FileNotFoundError: [WinError 2] ...
note: W3: --no-sandbox + config -> None (expect 3); FileNotFoundError: [WinError 2] ...
W1: FAIL
W2: FAIL
W3: FAIL
0 PASS 3 FAIL
exit=1
```

then GREEN against the real build directory, and again on an immediate re-run, so
it is not an intermittently green check:

```
note: W1: sandboxed + config -> 3 (expect 3)
note: W2: sandboxed, no config -> 16 (expect anything but 3)
note: W3: --no-sandbox + config -> 3 (expect 3)
W1: PASS
W2: PASS
W3: PASS
3 PASS 0 FAIL
exit=0
```

### What this still does not establish

- ~~**Worker parity on Windows.**~~ **Added the same day.** Conventions rule 3
  requires a surface exposed to both a window and a worker to report identical
  values in both, and the September measurement did check a dedicated worker
  (`2026-09-24-review-triage.md:195`, `main=3 worker=3`). The script's first
  version read the main thread only, and said so rather than carrying an untested
  row. It now has two worker rows, measured below.
- **Any other renderer-consumed key.** One key is one key.
- **That the binary matches the tree.** `out\Release` was built 2026-09-25 while
  the tree's content matches the change set at `3d78ae2`. The byte comparison in
  §7 of the runbook is about the *tree*, not the binary, so a patch landing in
  the tree after that build would not appear in these results. What W1 shows is
  that the binary in `out\Release` contains a working fix, not that it contains
  every patch the tree now holds.
- **A transport trap, recorded because it bit once.** Copying the new
  `lib_shell.py` across with `Copy-Item` from a path that had failed to be
  written left a **zero-line** file in the host's verify tree, overwriting the
  working copy; it was restored from the `.bak` taken in the same call. Take the
  backup first and check the installed line count, which is why those numbers are
  in the transcript.

The host's verify tree is therefore no longer a clean copy of one commit: it is
`ab0644c` plus `scripts/lib_shell.py` and `scripts/verify_windows_sandbox_env.py`
from this branch.


### Worker parity, measured

On Windows a renderer and a dedicated worker are separate processes, so
`CreateFilteredEnvironment()` could reach one and not the other; a fix that
applied to only one of them would look correct from the main thread alone. Two
rows were added to `verify_windows_sandbox_env.py`, using the same blob-worker
probe as `verify_sp0.py:9-16`. Both expressions go through ONE session per case,
so the pair comes from the same process tree and the three launches did not
become five.

W4 is parity under the spoof. W5 is parity with no config at all, which is what
stops W4 passing because both values happen to be the spoofed number.

RED first, with `CAMOU_OUT` pointing at a directory holding no binary — note that
W5's `is not None` guard is what makes it fail rather than pass on two equal
`None`s:

```
note: W4: sandboxed + config, worker -> None (expect 3, and equal to main None)
note: W5: sandboxed, no config, worker -> None (expect equal to main None)
W1: FAIL
W2: FAIL
W3: FAIL
W4: FAIL
W5: FAIL
0 PASS 5 FAIL
exit=1
```

then against the real build directory, twice:

```
note: W1: sandboxed + config, main -> 3 (expect 3)
note: W2: sandboxed, no config, main -> 16 (expect anything but 3)
note: W3: --no-sandbox + config, main -> 3 (expect 3)
note: W4: sandboxed + config, worker -> 3 (expect 3, and equal to main 3)
note: W5: sandboxed, no config, worker -> 16 (expect equal to main 16)
W1: PASS
W2: PASS
W3: PASS
W4: PASS
W5: PASS
5 PASS 0 FAIL
exit=0
```

`main=3 worker=3` under the sandbox reproduces what September measured by hand
(`2026-09-24-review-triage.md:195`); `main=16 worker=16` unconfigured is the part
that was not measured then, and it is what makes the parity claim mean something
rather than being an artefact of both processes reading the same spoof.

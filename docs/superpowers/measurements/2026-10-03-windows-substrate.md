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
  include the testing config and never take this path. Filed as backlog item 6
  in the long-term roadmap (it was item 5 until "Crashpad on Windows" below
  inserted the dump finding ahead of it).

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
- **The Go and Node clients.** (The Python client ran later the same day — see
  "The Python client on Windows" below.) Only `lib_shell` and `verify_sp2b.py` ran. The
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
- ~~**`layout()`'s `py` and `node` fields.**~~ **`py` fixed the same day — see
  "The Python client on Windows" below; `node` still needs
  `PLAYWRIGHT_NODEJS_PATH` set on the host.** As written: they are Linux-shaped on the host:
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
- ~~**`CAMOU_EXE`.**~~ **Measured the same day — see "`CAMOU_EXE` on Windows"
  below.** The third knob PR #4 shipped; when this entry was written, `CAMOU_OUT`
  and `tempfile.gettempdir()` had been exercised on Windows and `CAMOU_EXE` had
  not.
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


## `CAMOU_EXE` on Windows

The third knob PR #4 shipped, and the last of the three unmeasured on Windows.
`lib_shell._binaries()` makes `CAMOU_EXE` win over `CAMOU_OUT` for chrome, and
deliberately not move `content_shell` with it, because `CAMOU_EXE` names one file
-- the chrome inside an extracted release archive, where no out directory exists.
Until now that was proven only by `scripts/test_lib_shell_launch.py` on a Mac,
which checks the strings `_binaries()` returns, not a browser that started.

Measured in both directions with `verify_windows_sandbox_env.py` as the
instrument, because its five rows need a working chrome and fail all together
without one:

```
=== GREEN: CAMOU_OUT bogus, CAMOU_EXE real -> EXE must win ===
CHROME = D:\camou-win\chromium\src\out\Release\chrome.exe
SHELL  = D:\no-such-out\content_shell.exe
5 PASS 0 FAIL
exit=0
=== RED: CAMOU_OUT real, CAMOU_EXE bogus -> EXE must still win ===
CHROME = D:\no-such\chrome.exe
0 PASS 5 FAIL
exit=1
```

The second run is the one that proves precedence rather than just use: a valid
`CAMOU_OUT` was available and was not taken, so `CAMOU_EXE` decides even when the
fallback would have worked. The first run's `SHELL` line is the third property,
measured on Windows for the first time: `CAMOU_EXE` left `content_shell` under the
bogus `CAMOU_OUT` instead of dragging it along.

With this, all three things PR #4 shipped -- `CAMOU_OUT`, `CAMOU_EXE` and
`tempfile.gettempdir()` -- have run against a real browser on Windows.


## Crashpad on Windows

Backlog item 6 ended on a question: does the `0xC0000005` access violation
produce a crashpad **upload**? If it did, it would be traffic, and traffic is
the axis that ranks Safe Browsing above everything else. Answered from the source
first, then on the host.

### No upload — but not for the reason the Linux analysis gave

`measurements/2026-09-09-sp7-phone-home.md:36-41` concluded crash upload is off
because `GetCollectStatsConsent()` returns false without
`GOOGLE_CHROME_BRANDING`. That is the **Linux** client. Windows has its own,
`chrome/app/chrome_crash_reporter_client_win.cc`, and it delegates:

```
bool ChromeCrashReporterClient::GetCollectStatsConsent() {
  return install_static::GetCollectStatsConsent();
}
```

`install_static::GetCollectStatsConsent()` (`chrome/install_static/install_util.cc`)
reads machine state: first `ReportingIsEnforcedByPolicy()` — a
`MetricsReportingEnabled` DWORD under `SOFTWARE\Policies\<product>` in HKLM,
then HKCU — and failing that a `usagestats` DWORD under the install's ClientState
key. On a managed Windows machine with that policy set, consent is **true**.

What actually prevents an upload is one level up and shared by every platform,
`components/crash/core/app/crash_reporter_client.cc:143-147`:

```
std::string CrashReporterClient::GetUploadUrl() {
#if BUILDFLAG(GOOGLE_CHROME_BRANDING) && defined(OFFICIAL_BUILD)
  return kDefaultUploadURL;
#else
  return std::string();
```

The fork is neither branded nor official (`settings/release-args.gn` keeps
`is_official_build` off on purpose), so the URL is empty and crashpad has nowhere
to send a report. One override exists and is worth knowing about:
`components/crash/core/app/crashpad_win.cc:100-105` replaces the URL with an
environment variable's value "for testing". It is operator-side, not
page-reachable.

On this host, all four policy locations are absent:

```
HKLM:\SOFTWARE\Policies\Chromium MetricsReportingEnabled = (absent)
HKCU:\SOFTWARE\Policies\Chromium MetricsReportingEnabled = (absent)
HKLM:\SOFTWARE\Policies\Google\Chrome MetricsReportingEnabled = (absent)
HKCU:\SOFTWARE\Policies\Google\Chrome MetricsReportingEnabled = (absent)
```

So item 6's rank stands: the access violation is not traffic.

### What it does do: a dump in the profile, holding the whole environment

The same crash, triggered once with a fresh throwaway profile:

```
exit code: 0xC0000005
files under the profile's Crashpad: 3
  <udd>\Crashpad\metadata  114
  <udd>\Crashpad\settings.dat  40
  <udd>\Crashpad\reports\df89f437-24f0-4882-8b54-166f660e06f3.dmp  191104
files under the default Crashpad before/after: 0 / 0
```

The dump lands in the profile named by `--user-data-dir`, not in the default
`%LOCALAPPDATA%\Chromium\User Data\Crashpad`.

Then the question that matters for this project: does that dump carry the
identity? Crashed again with a unique marker as a config value, then the dump
searched for it — as ASCII and as UTF-16LE, because the Windows environment
block is UTF-16:

```
exit code: 0xC0000005
dump bytes: 186864
marker as ASCII:    False
marker as UTF-16LE: True
the string CAMOU_CONFIG as UTF-16LE: True
the string CAMOU_CONFIG as ASCII:    False
context: 4= CAMOU_CONFIG={"ua:osInfo":"ZQXJ7731MARKER"} ChocolateyInstall=C:\ProgramData\
=== control: same crash, no CAMOU_CONFIG ===
control marker as UTF-16LE: False
```

The minidump holds the process's **whole environment block**: the configuration
verbatim, beside every host variable (`ChocolateyInstall` is the next entry). The
control rules out the marker coming from anywhere else.

The config is the identity. Every crashed profile therefore carries a plain-text
record of who it claimed to be next to the real machine's environment, which is
the cross-profile link the roadmap's "many identities on one machine" decision
must not have. Nothing about this is specific to the field-trial flag; that flag
is only a reliable trigger. Filed as backlog item 5, ranked below Safe Browsing
because it is not traffic. The levers and the one non-lever (scrubbing `CAMOU_*`
after parsing, which would break the `windows-sandbox-env` fix) are listed there.

Not measured: whether Linux dumps carry the environment too. Crashpad writes them
there (`2026-09-09-sp7-phone-home.md:40`). (Partly answered the same day — see
"Crash dumps go to a directory the client removes": one Linux renderer dump
did not contain the marker.)

The three throwaway profiles created for this, each holding a dump with the
host's whole environment, were deleted from the host afterwards; none remain.

### A cleanup gap found on the way

After the day's Windows verify runs, `%TEMP%` held 14 `camoucrome-verify-*`
profile directories and 12 `camoucrome_verify_stderr.*.log` files. The
directories were **empty** — no files, no dumps — so nothing leaked, but
`lib_shell.shutdown()`'s `shutil.rmtree(..., ignore_errors=True)` had removed
their contents and not the directories themselves, and `ignore_errors` hid that.
The likeliest cause is a child process still holding a handle when `rmtree`
runs, which Linux tolerates and Windows does not; it is not proven. Separately,
`launch()` creates the profile with `tempfile.mkdtemp()` before `Popen`, so a
`Popen` that raises — the bogus-`CAMOU_OUT` RED runs did exactly that — leaves
the directory behind on every platform. Both belong to Step 1's "temp directory
cleanup"; neither is fixed here. The 14 directories and 12 logs were removed.

## The Python client on Windows

Added later the same day. Every row before this one drove the browser through
`lib_shell`; this section is the first time `client/python` itself ran on the
Windows host, against the same 153 `chrome.exe`.

### Host setup

The client declares `requires-python >=3.10` and pins `patchright==1.62.3`;
the host's only interpreter was 3.9.13 (`verify-venv`), for which pip offers
patchright up to 1.60.1. Rather than run an off-pin driver, the official CPython
NuGet package was unpacked — no installer, no registry, no PATH change:

```
python 3.12.10  D:\camou-win\python312\tools\python.exe
                (nuget.org/api/v2/package/python/3.12.10,
                 SHA-256 0EB85C2DFCCCCF1B17352DE4C397F69194035B7D37149EACC16F1147D93DE3B8)
venv            D:\camou-win\client-venv
                patchright 1.62.3, browserforge 1.2.4, apify_fingerprint_datapoints 0.15.0,
                playwright 1.55.0 (the driver verify's stock RED row), pytest 9.1.1, tzdata 2026.4
tree            D:\camou-win\tree  (git archive of the branch, untarred in place;
                the client is `pip install -e` from it)
env             CAMOU_OUT=D:\camou-win\chromium\src\out\Release
                CAMOU_VENV=D:\camou-win\client-venv  CAMOU_VENV_STOCK=(same)
                CAMOU_CLIENT=D:\camou-win\tree
                PLAYWRIGHT_NODEJS_PATH=<client-venv>\Lib\site-packages\patchright\driver\node.exe
                PATH += C:\Program Files\Git\usr\bin   (openssl, for the launcher verify's L3)
```

### What broke, each seen failing first

| Where | On Windows | Fix |
|---|---|---|
| `camoucrome.probe.browser_argv` | listed `/proc`: every probe raised `FileNotFoundError` after the page had loaded, `verify_sp6b_launcher.py` **0 PASS 5 FAIL** | reads `Win32_Process`, splits with `CommandLineToArgvW`; `[]` where neither exists, as the docstring already claimed |
| `launch()`'s temp profile | the context's `close` event fires while the browser still writes its profile; `rmtree(ignore_errors=True)` left **3–193 files in every temp profile** the client created (21 client profiles after one afternoon). After `close()` returns, one `rmtree` succeeds in ~0.07 s (5 of 5) | `remove_dir` retries until the directory is gone, bounded at 10 s |
| `probe` on a failed `goto` | never reached `ctx.close()`, so the close event never fired and the profile stayed (a 152-file profile from the L3 RED row) | `try/finally` |
| `layout().py` | `<venv>/bin/python3` | `Scripts\python.exe` when `osname == "nt"` |
| `verify_sp6b_driver.py` Python rows | `{venv}/bin/python3` by hand | `layout()` |
| `verify_sp6b_driver.py` C4 | `absent=['--noerrdialogs', '--ozone-override-screen-size=800,600', '--ozone-platform=headless', '--use-angle=swiftshader-webgl']` | Linux-only; see below |
| `test_launcher.py` | compared a Windows path with a `/`-joined suffix | compares the whole path |
| `test_gen.py` zone table | `zoneinfo.available_timezones()` is empty on Windows without the `tzdata` package | skips and says why; with `tzdata` installed it runs and passes |

C4's four flags are not the driver's on either OS. `headless_mode_init.cc`
appends `--noerrdialogs` to the **in-process** command line on every platform,
and the ozone and ANGLE three inside `#if BUILDFLAG(IS_LINUX)`. Linux shows the
first because Chromium rewrites its process title from that command line; on
Windows `Win32_Process.CommandLine` is the one the driver passed. The strict-abort
crash keys below show the in-process addition directly (`"switch-6" =
"--noerrdialogs"` with `num-switches = 6`). So on Windows C4 compares the
contract's set alone, and the argv it reads has exactly 7 entries: the binary,
the contract's four, `--user-data-dir` and the probe's `--no-sandbox`.

### Results

```
pytest -q client/python/tests            39 passed
verify_sp6b_launcher.py                  5 PASS 0 FAIL   (L1-L5; RED above: 0 PASS 5 FAIL)
verify_sp6b_driver.py  python-stock      RED as required: C1 Runtime.enable=1, C5 +17/+21/+26% over three runs
                       python-patchright GREEN: C1-C6, C5 +0/+2/+2%
                       go-*, node-*      FAIL: probe did not run (no Go probe, no driver dirs on the host)
verify_windows_client.py                 5 PASS 0 FAIL
```

C5 is SP2 D1's stack-timing signal: on Windows, as on Linux, stock Playwright's
`Runtime.enable` is visible as about +20% on `new Error().stack`, and patchright
removes it.

### `verify_windows_client.py`: the launch a user actually makes

Every probe-based row passes `--no-sandbox` (the probe adds it), so none of them
exercises a user's `camoucrome.launch()` on Windows: a sandboxed renderer behind
`CreateFilteredEnvironment()`, and a generated identity too long for one
environment string. A Windows identity from `gen.generate` is 37387 characters,
past `CONFIG_CHUNK_CHARS`, so it travels as `CAMOU_CONFIG_1..2`. The
`windows-sandbox-env` patch passes `CAMOU_*` by prefix, so the chunks should
survive; `verify_windows_sandbox_env.py` measured only a one-key config that
never chunks.

```
note: K1: 37387 chars -> 2 chunks, CAMOU_CONFIG present=False
note: K2: argc=6 --no-sandbox=False
note: K3: main -> 3 (expect 3)
note: K4: worker -> 3 (expect 3)
note: K5: no config -> 16 (expect anything but 3)
5 PASS 0 FAIL
```

`navigator.hardwareConcurrency` is the identity's last key, so it sits in the
last chunk, and the launch is strict. RED, with `config_env` patched to drop the
last chunk: the browser refused to start (`camoucfg: configuration is not a JSON
object` then `Check failed: !strict`), **1 PASS 4 FAIL**, with only the
no-config control passing.

### What this does not establish

- **The Go and Node clients.** No Go probe was built and no driver directories
  exist on the host; their four rows fail for that reason alone. (They ran later the same day; see "The Go and Node clients on Windows" below.)
- **A crash dump in a client profile.** The strict-abort RED crashed the browser
  inside a temp profile, which was then removed; whether a dump was written there
  was not looked at. That is backlog item 5's territory.
- **Fonts.** `fontconfig_for` is not meaningful on Windows (Chrome there does not
  read fontconfig); with no `fonts` directory beside `chrome.exe` it sets nothing,
  and nothing here tested the case where one exists.
- **The verify scripts' own temp directories.** `verify_sp6b_driver.py`'s
  `--dump-dom` baselines (`camoucrome-base-*`, 191 files each) and
  `verify_sp6b_launcher.py`'s work directory are created and never removed, on
  every OS. Not the client's; not fixed here.
- **Two other hardcoded `bin/python3`s,** in `measure_sp7_components.py` and
  `verify_sp1a_chrome.py`. Neither ran here.

## Crash dumps go to a directory the client removes

Added later the same day: the client-side lever of backlog item 5. Chrome's
`GetCrashDumpLocation` takes `BREAKPAD_DUMP_LOCATION` from the environment before
falling back to `<user-data-dir>\Crashpad`
(`chrome/app/chrome_crash_reporter_client_win.cc:116-128`; the POSIX client reads
the same variable). All three clients now create a temp directory per launch,
point the variable at it, and remove it when the context closes or the launch
fails, for a kept profile as much as a temp one; the parent's value is never
inherited. The contract entry is `launch.crash_dumps`. Removal goes through the
same retry as the temp profile (`remove_dir`; Go's `removeDir`; Node's `fs.rm`
with `maxRetries`), because the close-event race above would otherwise leave the
directory, dumps included.

Measured through `camoucrome.launch()` with a **kept** profile, a config carrying
a marker (`{"ua:osInfo": "ZQXJ7731MARKER"}`), and a renderer crash mid-session
(`page.goto("chrome://crash")`), dumps searched 3 s later.

RED, the client before this change:

```
client redirects crash dumps: False
mid-session: kept profile dumps 1 marker True
mid-session: crash dirs 0 dumps 0 marker False
after close: kept profile dumps 1 | Crashpad dir in profile: True
```

So a **renderer** dump carries the identity too, not only the browser-process
crash measured above, and it outlives the session in the kept profile.

GREEN, three runs alike:

```
client redirects crash dumps: True
mid-session: kept profile dumps 0 marker False
mid-session: crash dirs 1 dumps 1 marker True
after close: kept profile dumps 0 | Crashpad dir in profile: False
after close: crash dirs left 0
```

The dump still exists while the browser runs — the marker is in it — but never
in the profile (which no longer gets a `Crashpad` directory at all), and the
directory holding it is gone after `close()`. `%TEMP%` held no `camoucrome*`
directory afterwards.

The same probe on the Linux box (154 `chrome`, `--no-sandbox`): `mid-session:
crash dirs 1 dumps 1`, `after close: crash dirs left 0`, no `Crashpad` in the
profile. The Linux renderer dump did **not** contain the marker, as ASCII or as
UTF-16 — one crash, one process type; it does not show that no Linux dump ever
carries the environment.

> **Amended 2026-10-03.** The Linux `after close: crash dirs left 0` was read
> too early. On Linux the browser re-creates both the crash dir and the temp
> profile after the close event removed them; see "The close event is too early
> on Linux" below. On Windows a temp-profile launch, with no crash, left 0 on
> main after a 3 s wait (same section). The kept-profile crash case above was
> not re-run with a wait.

### What this does not establish

- **A launch that does not go through a client.** `chrome.exe` started by hand,
  or by any other tool, still writes to `<profile>\Crashpad`. The C++ lever
  remained. (It was done the next day; see "The crashpad lever" below.)
- **A client process that dies.** If the Python, Go or Node process is killed,
  no close event runs and the crash directory stays in the temp directory,
  dumps included. Removing it then is the caller's job.
- **Go and Node on Windows.** Both are unit-tested and ran on the Linux box (the
  driver verify's six rows); neither ran on Windows, so Go's `removeDir` and
  Node's `fs.rm` retries are not measured against the race there. (They ran later the same day; see "The Go and Node clients on Windows" below.)
- **A browser-process crash during launch.** The failed-launch path removes the
  directory (unit-tested in all three clients); whether a dump was written
  first was not looked at.

## The close event is too early on Linux

Found while sweeping the hosts for leftover directories. The build box's `/tmp`
held 518 client temp profiles (`camoucrome-<random>`) and their crash dirs, the
newest written after the crash-dir change above merged. Each held the handful of
files a browser writes as it shuts down: `Local State`, `Default/Network
Persistent State`, `Default/Trust Tokens` and similar.

Traced in-process on the box, with the Python client and a temp profile:
`remove_dir` ran on the close event and both directories were gone right after
it. Three seconds later both existed again. The profile held 8 files, and the
crash dir was empty, re-created by crashpad. When `ctx.close()` returns, no
process names the profile in its argv (the crashpad handler names the crash dir
instead, so this check does not cover it), and both directories are already
back. A removal at that point stays final: 3 s later neither directory exists
(the counts below). The event fires while the browser is still shutting down.

All three clients now remove once on the event and again after the context's
own close returns. The event removal stays, because for a browser that crashed
or was killed the event arrives after the process is gone. Measured with a
small in-process repro per client: 3 temp-profile launches, `about:blank`,
close, wait 3 s, count what is left of the 6 directories created:

```
== main 3010c69
python | launches 3, dirs created 6, left 3 s after close: 6
node   | launches 3, dirs created 6, left 3 s after close: 6
go     | launches 3, dirs created 6, left 3 s after close: 6
== branch
python | launches 3, dirs created 6, left 3 s after close: 0
node   | launches 3, dirs created 6, left 3 s after close: 0
go     | launches 3, dirs created 6, left 3 s after close: 0
```

The same repro (temp profile, no crash) with the Python client on the Windows
host left 0 on main as well as on the branch. There, `remove_dir`'s retry loop runs for as long as the
browser holds its files, which lasts until the process exits, so the removal
that wins is already the final one. The leak was only ever measured on Linux.

### What this does not establish

- **A driver stopped without `close()`.** If `pw.stop()` or the end of a `with
  sync_playwright()` block takes the browser down, only the event removal runs,
  and on Linux that is the early one.
- **Go and Node on Windows.** Neither ran there yet. (They ran later the same day; see "The Go and Node clients on Windows" below.)

## The Go and Node clients on Windows

Three things kept them off the host, and none was in the clients themselves:

- **The probes read argv from `/proc` only.** On Windows the Node probe threw,
  and the Go probe returned no argv without any error. Both now read
  `Win32_Process` and split the command line with `CommandLineToArgvW`: Go
  through `syscall`, Node through PowerShell, which receives the script
  `-EncodedCommand` so no quoting has to survive. Like the Python probe, they
  skip a null command line and any `--type=` child.
- **The Go probe's source was never in the repo.** `client/go/.gitignore`
  matched its directory. The fix is in the close-race change.
- **playwright-go only accepts a driver whose `--version` contains `1.62.1`.**
  The driver bundled with patchright on the host is 1.62.3. The host now holds
  `D:\camou-win\driver-patchright` and `driver-stock`: the box's
  `patchright-core` and `playwright-core` 1.62.1 packages (pure JS), copied
  over UNC, each beside the `node.exe` (v24.18.1) from `client-venv`. Go is
  1.27.1, unpacked from go.dev's zip after its SHA-256 matched the published
  value.

Two unit tests built expected paths with `/`, one in Go and one in Node, and
failed on the separator alone. With those fixed, all three client suites pass
on the host: Go `ok`, Node `pass 14`, Python `42 passed`.

`verify_windows_client.py` now repeats K2-K4 through the Go and Node clients
(rows G2-G4 and N2-N4, 11 in all). Their probes run with `--sandbox --strict
--config @file`, because the 37 KB identity is past Windows' 32767-char command
line. The probes read a page that writes both values into `#o` once the worker
has answered.

```
note: G2: argc=6 --no-sandbox=False      note: N2: argc=6 --no-sandbox=False
note: G3: main -> 3 (expect 3)           note: N3: main -> 3 (expect 3)
note: G4: worker -> 3 (expect 3)         note: N4: worker -> 3 (expect 3)
11 PASS 0 FAIL
```

RED, using a copy of the tree in which the Go and Node clients drop the last
config chunk. Under strict the config is then unparseable, the browser exits,
and both probes fail. The Python K rows are untouched:

```
note: G2: argc=0 --no-sandbox=False; JSONDecodeError: ... <gracefully close end>
note: N2: argc=0 --no-sandbox=False; JSONDecodeError: ... <gracefully close end>
5 PASS 6 FAIL
```

`verify_sp6b_driver.py`, all six drivers on the host, prints `ALL_PASS`. The
stock rows fail C1 (`Runtime.enable=1`) and C5 (+21-22%), and the patchright
rows pass every check (C5 +4-6%). The log carries one `ConnectionAbortedError`
traceback, raised by the verify's own page server when a client dropped a
connection; no row depends on it. That run left 3 `camoucrome-base-*`
directories, the driver verify's own baseline profiles, which the scripts
cleanup change removes. It left no client profile and no crash dir.

### What this does not establish

- **Fonts.** No `FONTCONFIG_FILE` path was exercised on Windows. Fontconfig is a
  Linux mechanism.
- **The driver copies.** They are the box's packages, not a fresh install. A
  re-pin that moves patchright moves both hosts together.


## The crashpad lever

Backlog item 5's last piece: a launch that bypasses the clients, or a client
killed before its close event, still left a dump holding the identity.

### The lever the roadmap named would not have worked

The roadmap said "crashpad not initialising for the fork (`GetCrashDumpLocation`
returning empty)". The source says otherwise. In
`components/crash/core/app/crashpad_win.cc`, a false `GetCrashDumpLocation`
only leaves `database_path` empty; `StartHandler` still runs with it (line
151). The handler then fails to start, and a crash with no handler goes to
Windows Error Reporting. WER writes its own report outside the profile and may
upload it. That is worse than the problem being fixed.

What crashpad does provide is a per-process switch the handler honours on
every platform. In `handler/win/crash_report_exception_handler.cc:82`, the
whole report write sits inside
`if (client_options.crashpad_handler_behavior != TriState::kDisabled)`, and
the function returns the exception's termination code either way. Linux
honours the same switch (`handler/linux/capture_snapshot.cc:63`) and so does
macOS. Nothing in Chrome sets it explicitly
(`git grep set_crashpad_handler_behavior` outside `third_party/crashpad`
finds nothing).

`patches/crashpad-no-dumps.patch` sets it to `kDisabled` in
`InitializeCrashpadImpl`, right after the platform initialisation succeeds.
Every process that initialises crashpad runs that function, so browser,
renderer and GPU crashes are covered, and so is `DumpWithoutCrashing`. The
handler process still starts, the process still dies with its own exception
code, and WER is never involved. Only the file is gone.

### The measurement

`scripts/verify_crash_dumps.py` starts the browser through `lib_shell`, not a
client, with no `BREAKPAD_DUMP_LOCATION` and a marker in the config. It then
crashes it twice:
- **C1:** a renderer crash through `chrome://crash`; the browser must survive.
- **C2:** a browser crash through the DevTools `Browser.crash` command.
  Navigating to `chrome://inducebrowsercrashforrealz` does nothing under
  `--headless`. On the first draft that row read `NOT MEASURED`, never PASS.

After each crash it searches for new dump files, and for the marker as ASCII
and as UTF-16LE, in these places:
- the profile and `%TEMP%`;
- the default crash database;
- on Windows, `%LOCALAPPDATA%\CrashDumps` and both WER stores.

A row passes only if the crash is seen and nothing new is found.

| Binary | Run | C1 renderer | C2 browser (exit) |
|---|---|---|---|
| Linux 154, before the lever | RED | FAIL: 1 dump in `~/.config/chromium/Crash Reports/pending/`, marker 0 | FAIL: 1 dump, marker 0 (-6) |
| Linux 154, with the lever | GREEN, twice | PASS: 0 dumps | PASS: 0 dumps (-6) |
| Windows 153, the old binary | RED | FAIL: 1 dump in `<profile>\Crashpad\reports`, marker 1 | FAIL: 1 dump, marker 1 (`0x80000003`) |
| Windows 154, before the lever | RED | FAIL: 1 dump, marker 1 | FAIL: 1 dump, marker 1 (`0x80000003`) |
| Windows 154, with the lever | GREEN, twice | PASS: 0 dumps, marker 0 | PASS: 0 dumps, marker 0 (`0x80000003`) |

Two things the table shows beyond the fix:
- **Linux dumps do not land in the profile.** Launched without the variable,
  Linux `chrome` writes them to `~/.config/chromium/Crash Reports`, one
  database that **every profile on the host shares**. No Linux dump carried the
  marker, but the location alone linked profiles.
- **The exit code is unchanged** on both platforms. Seen from outside, a crash
  looks the same as before; only the file is missing.

The Linux build after the edit was 6 steps (22 s, component build). The Windows
rebuild with the lever on top of the full 154 build was **8 steps, 25.68 s**
(non-component `out\Release`).

### The Windows tree moved to 154 for this

`D:\camou-win\chromium\src` was on 153 with the old change set as a bare
working tree. An unattended run (`D:\camou-win\overnight.ps1`) did the
following:
1. Discarded the 153 working tree. It had been measured byte-identical to the
   `3d78ae2` change set the same day.
2. Fetched the 154 tag, checked it out and ran `gclient sync`.
3. Ran `apply.sh` from `main` under Git Bash: 32 of 32 patches, 130 dirty paths.
4. Built `chrome`: 57,101 steps, 5 h 31 m.
5. Ran RED, applied the lever patch, rebuilt, and ran GREEN twice.
6. Ran the client verifies.

The re-point procedure and its costs are in `specs/repin-runbook.md` §7.

The client verifies on the new binary, from the same run:
- `verify_windows_client.py`: 11 PASS 0 FAIL.
- `%TEMP%` held 0 `camoucrome-*` directories afterwards.
- `verify_sp6b_driver.py`: **FAIL** on one row. `go-patchright` C5 measured
  stack timing +22% against a 15% bound. In that same run `python-patchright`
  was -2% and `node-patchright` +9%, and it ran straight after 5.5 h of build.

Re-run three times the next morning with the host idle (CPU 1%), the driver
verify was ALL_PASS each time:

| Run | python-patchright C5 | go-patchright C5 | node-patchright C5 | stock rows C5 |
|---|---|---|---|---|
| 1 | +9% | +10% | +10% | +26%, +27%, +27% |
| 2 | +7% | +7% | +7% | +27%, +25%, +25% |
| 3 | +9% | +10% | +10% | +26%, +27%, +27% |

C5 measures a timing ratio, and on this host the patched drivers sit 5 to 8
points under its bound. A loaded machine can push one of them over, so C5 is
load-sensitive. The single FAIL is recorded here rather than dropped.


# Step 1 first slice: a Windows verify substrate on the build that already exists

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** run a committed verification natively against the fork's Windows
`chrome.exe`, and close the "not verified on Windows" caveat PR #4 shipped — with
no Chromium build.

**Architecture:** the Windows tree already holds a complete fork build at the
*old* pin (`chrome.dll` 315.6 MB, ProductVersion `153.0.8010.36`, built
2026-09-25). Chrome 156 reaches stable 2026-10-20, which is also when the re-pin
is due, and that re-pin rebuilds the Windows tree anyway. So this slice spends no
build hours: it stands up the host's verify environment and proves the plumbing
against the 153 binary, choosing a verification whose rows assert **behaviour**
rather than a captured baseline (a 153 binary cannot match a 154 baseline).

**Tech Stack:** Windows 10 host (PowerShell 5 over the sshgate MCP), Python
3.9.13 at `C:\Program Files\Python39`, playwright in a host venv, WSL2 Ubuntu
on the same machine for file transport through `/mnt/d`.

**Spec:** `docs/superpowers/plans/2026-10-02-long-term-roadmap.md`, "Step 1:
Windows foundation" (lines 145-179). This slice covers its first three bullets
(verification target `chrome.exe`, parametrised `lib_shell` run natively, the
beginning of a named Windows verify set) and the probe needed for its "Windows
change loop" bullet. It does **not** cover the Windows component build, the Go
and Node clients, fonts, or the GPU/audio process check.

## Global Constraints

- All fingerprint spoofing stays C++ at the Blink/browser level; nothing in this
  slice injects JavaScript into a page-visible scope.
- The build box and the Windows host are reached **only** through the sshgate
  MCP server `buildpc`. Never retry ssh password authentication to the box
  (fail2ban). Never write a password or token to a file.
- sshgate lands in **PowerShell 5**: `&&`, `$?` and `$(...)` are unusable, and a
  `command` containing a newline (U+000A) is refused. Pass bash to WSL as
  base64: `wsl -u lang -e bash -c "echo <b64> | base64 -d | bash"`.
- A call over ~120 s moves to the background and returns later; keep each call
  under that where possible, and never assume a timed-out call did nothing.
- The Windows tree stays on pin `507c6ee3e2` / 153.0.8010.36 for this slice.
  Re-pointing it is the 2026-10-20 re-pin's work, not this plan's.
- `D:\camou-win\camoucrome` is a clone on the retired branch `review/2026-09-24`
  that may predate the 2026-09-26 history rewrite. Do not fetch from it, push
  from it, or cut a branch from it. Leave it alone.
- The repo's git identity is `Lãng <30039912+lang315@users.noreply.github.com>`.
  Never sign a commit with the session's own userEmail — pushes are rejected for
  email privacy and the history then needs rewriting.
- `main` is protected: work lands through a PR, and **every PR carries evidence**
  (command output with counts, not prose).
- RED before GREEN. A row's PASS counts only once its FAIL has been seen for the
  right reason. Assert the expected count, never just exit 0.
- Baselines are recaptured, never edited. Nothing in this slice recaptures one.

---

### Task 1: CI runs every test in `scripts/`, and the roadmap records Step 1's progress

**Why:** `.github/workflows/checks.yml` names its test files by hand. That list
is why the `CLIENT` latch regression went green through CI: it contains no module
that imports `lib_shell` at module scope, so the cross-module ordering that broke
`pytest scripts/` never happened there. Two test files in the tree —
`scripts/test_gen_keys.py` and `scripts/test_winhost.py` — have never run in CI
at all.

**Files:**
- Modify: `.github/workflows/checks.yml` (the `python client tests + packager tests` step)
- Modify: `docs/superpowers/plans/2026-10-02-long-term-roadmap.md` (Step 1 section)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing other tasks read.

- [ ] **Step 1: Prove the two never-run files need no build box**

```bash
python3 -m pytest -q scripts/test_gen_keys.py scripts/test_winhost.py
```
Expected: `11 passed`. If either needs the box, do **not** fold it in silently —
exclude it by name with a comment saying why.

- [ ] **Step 2: Prove the whole directory passes, and record the count**

```bash
python3 -m pytest -q scripts/
```
Expected: `60 passed`. This number goes in the PR body; a later task must not
change it without saying so.

- [ ] **Step 3: Replace the hand-maintained list**

In `.github/workflows/checks.yml`, the step currently reads:

```yaml
      - name: python client tests + packager tests
        run: |
          python3 -m pip install -q pytest browserforge==1.2.4
          python3 -m pytest -q client/python/tests scripts/test_package.py scripts/test_fonts.py scripts/test_capture_webgl_profile.py scripts/test_rebuild_branch.py scripts/test_repin.py scripts/test_verify_host_oracle.py
```

Replace the pytest line with the directory, and say in a comment why:

```yaml
      # scripts/ wholesale, not a hand-written list: the list is what let the
      # CLIENT latch regression through. It contained no module importing
      # lib_shell at module scope, so the cross-module import ordering that
      # breaks `pytest scripts/` never happened in CI. A directory also picks up
      # a new test file without anyone remembering to add it -- test_gen_keys.py
      # and test_winhost.py had never run here.
      - name: python client tests + packager tests
        run: |
          python3 -m pip install -q pytest browserforge==1.2.4
          python3 -m pytest -q client/python/tests scripts/
```

Leave the separate `argv freeze (lib_shell)` step alone: it prints its twelve
named rows, where pytest only runs them as an import side effect.

- [ ] **Step 4: Record Step 1's status in the roadmap**

Add this at the end of the "Step 1: Windows foundation" section, before
"Done when:":

```markdown
**Status 2026-10-03.** Shipped: `lib_shell` resolves its binaries and temp dir
from the environment (`CAMOU_OUT`, `CAMOU_EXE`, `tempfile.gettempdir()`, PR #4),
and the layout block eleven scripts repeated is one `lib_shell.layout()` call
(PRs #5, #6). Flags were deliberately not parametrised: `launch()` already takes
`extra_flags` and `CHROME_FLAGS` is platform-neutral.

Ruling 2026-10-03: the Windows tree stays on the **old** pin (`507c6ee3e2`,
153.0.8010.36) until the re-pin due 2026-10-20. Re-pointing it to 154 would cost
6-7 h of machine time that Chrome 156 obsoletes in 17 days, and it would put two
6-hour builds (WSL and Windows) on one machine on the same day, with the
build-overlap lock this step still owes. The plumbing is verified against the
153 build that already exists instead
(`plans/2026-10-03-step1-windows-substrate.md`).
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/checks.yml docs/superpowers/plans/2026-10-02-long-term-roadmap.md
git commit  # subject: "ci: run every test in scripts/, not a hand-written list"
```

---

### Task 2: the Windows host's verify environment

**Why:** nothing on the host can run a verification today — there is no venv and
no playwright. `lib_shell` imports playwright lazily (PR #5), so the paths and
`launch()` work without it, but `evaluate()` needs it.

**Files:**
- Create on the host: `D:\camou-win\verify-venv\` (a venv)
- Create on the host: `D:\camou-win\verify\{scripts,settings,baselines,client}\`
- No repo file changes.

**Interfaces:**
- Produces, for Task 3: `PY_WIN = D:\camou-win\verify-venv\Scripts\python.exe`,
  `VERIFY_WIN = D:\camou-win\verify`, `CAMOU_OUT = D:\camou-win\chromium\src\out\Release`.

- [ ] **Step 1: Read the box's playwright version, so the host matches it**

```bash
/home/lang/camoucrome-verify/venv/bin/python3 -m pip show playwright | head -2
```
Record the version. The host installs that exact version: a different one is a
second variable in every later comparison.

- [ ] **Step 2: Copy the trees the verifies import, through `/mnt/d`**

WSL can write `/mnt/d` (probed 2026-10-03), so no clone and no credential is
needed on the host. Source is the runner's own checkout, which `actions/checkout`
keeps on `main`:

```bash
R=/home/lang/actions-runner/_work/camoucrome/camoucrome
git -C $R fetch -q origin main
git -C $R rev-parse --short origin/main        # record what was copied
D=/mnt/d/camou-win/verify
mkdir -p $D
for d in scripts settings baselines client; do
  rsync -a --delete --exclude __pycache__ --exclude node_modules $R/$d/ $D/$d/
done
ls $D/scripts/lib_shell.py $D/settings/launcher.json
```

Gate: `git -C $R status --porcelain` must be empty before the copy, or the files
on the host do not correspond to any commit.

- [ ] **Step 3: Create the venv and install playwright at the pinned version**

```powershell
& 'C:\Program Files\Python39\python.exe' -m venv D:\camou-win\verify-venv
& 'D:\camou-win\verify-venv\Scripts\python.exe' -m pip install -q --upgrade pip
& 'D:\camou-win\verify-venv\Scripts\python.exe' -m pip install -q playwright==<version from Step 1>
& 'D:\camou-win\verify-venv\Scripts\python.exe' -c "import playwright; print(playwright.__file__)"
```

No `playwright install`: the verifies launch the fork's own binary and attach
over CDP, so no downloaded browser is wanted. If Python 3.9.13 cannot take that
playwright version, record the failure verbatim and install the newest version it
accepts, noting the mismatch — do not silently diverge from the box.

- [ ] **Step 4: Prove lib_shell resolves the Windows paths on the host**

```powershell
cd D:\camou-win\verify\scripts
$env:CAMOU_OUT='D:\camou-win\chromium\src\out\Release'
& 'D:\camou-win\verify-venv\Scripts\python.exe' -c "import lib_shell as L; print(L.SHELL); print(L.CHROME); print(L.STDERR_LOG); print(L.layout())"
```

Expected, and each one is a claim PR #4 made and never measured on Windows:
`CHROME` ends `out\Release\chrome.exe` (the `.exe` suffix), `STDERR_LOG` is under
the host's `%TEMP%` and not `/tmp`, and `layout()` returns Windows paths.

- [ ] **Step 5: RED — the same command with CAMOU_OUT pointing nowhere**

```powershell
$env:CAMOU_OUT='D:\no-such-out'
& 'D:\camou-win\verify-venv\Scripts\python.exe' -c "import lib_shell as L; print(L.CHROME)"
```
Expected: it prints `D:\no-such-out\chrome.exe`. The path is computed, not
checked, so the RED that matters is Task 3's launch failure naming that path.

---

### Task 3: the first committed verification green natively on `chrome.exe`

**Why:** `scripts/verify_sp7_fieldtrial.py` is the one verification that
exercises every claim PR #4 made, in three rows, with no captured baseline and no
local HTTP server: F1 counts VLOG lines in `lib_shell.STDERR_LOG` (so it proves
the `gettempdir()` change), F2 expects a **hard exit code 1** (so it proves
`launch()`'s failure path and its message), and F3 overrides
`navigator.hardwareConcurrency` (so it proves `CAMOU_CONFIG` reaches the renderer
on Windows, which is what the `windows-sandbox-env` patch exists for).

**Files:**
- No repo file changes expected. If the script needs a Windows-only change, it
  goes in a separate commit with its own RED.

**Interfaces:**
- Consumes Task 2's `PY_WIN`, `VERIFY_WIN`, `CAMOU_OUT`.

- [ ] **Step 1: Confirm the patch under test is in the Windows tree's applied set**

The Windows tree carries 31 patches as an **uncommitted** working tree. A RED row
means nothing until it is known whether the patch is there at all:

```bash
git -C /mnt/d/camou-win/chromium/src diff --stat | grep -iE 'field_trial|variations' || echo 'NO fieldtrial patch in the applied set'
```

If the patch is absent, stop and report: the row is RED for a reason that has
nothing to do with Windows, and the honest next step is a different script
(`verify_sp2b.py`, same shape, no baseline, no server), not a chase.

- [ ] **Step 2: RED first — run it with no binary where CAMOU_OUT points**

```powershell
cd D:\camou-win\verify\scripts
$env:CAMOU_OUT='D:\no-such-out'
& 'D:\camou-win\verify-venv\Scripts\python.exe' verify_sp7_fieldtrial.py
```
Expected: a `FileNotFoundError` naming `D:\no-such-out\chrome.exe` — the same
failure shape the Linux box gave for the same mistake. This is the proof that the
run reaches the binary through the parametrised path and not through some
hardcoded default.

- [ ] **Step 3: GREEN — the real out directory**

```powershell
$env:CAMOU_OUT='D:\camou-win\chromium\src\out\Release'
& 'D:\camou-win\verify-venv\Scripts\python.exe' verify_sp7_fieldtrial.py
```
Expected: the script's own three rows PASS and it prints its count line. Record
the output verbatim, including any row that fails.

- [ ] **Step 4: Triage every failing row to one of three causes, in writing**

For each FAIL, say which it is and the evidence: (a) the patch is not in the
Windows tree's 31, (b) the row depends on something Linux-only (a path, a flag, a
process model), or (c) the fork behaves differently on Windows. Only (c) is a
finding; (a) and (b) are notes for the re-point. Do not edit the script to make a
row pass.

- [ ] **Step 5: Second script, if and only if Step 3 produced a usable result**

```powershell
& 'D:\camou-win\verify-venv\Scripts\python.exe' verify_sp2b.py
```
`verify_sp2b.py` is the cheapest second opinion: chrome-driven, 158 lines, no
baseline, no server, and its criterion 1 measures an unconfigured run so a
configured-only failure is distinguishable. Record its count line.

---

### Task 4: what the 2026-10-20 re-point will have to deal with

**Why:** the Windows tree holds 90 modified files and **no commits** above the
pin — the roadmap's "no way back" in literal form. The re-point must know whether
those 90 files are exactly the retired change set or whether they contain
uncommitted work that would be lost, and whether `scripts/rebuild_branch.sh` can
run there at all. `bash` on the host's PATH is `C:\WINDOWS\system32\bash.exe`,
the WSL launcher — not Git Bash — so the script's shell has to be located.

**Files:**
- Modify: `docs/superpowers/specs/repin-runbook.md` (a Windows-tree section)

**Interfaces:**
- Produces: the recorded answer that the re-pin runbook needs.

- [ ] **Step 1: List what is modified in the Windows tree**

```bash
git -C /mnt/d/camou-win/chromium/src status --porcelain | sort > /tmp/win-dirty.txt
wc -l /tmp/win-dirty.txt
grep -c '^??' /tmp/win-dirty.txt    # untracked: additions/ copies
grep -c '^ M' /tmp/win-dirty.txt    # modified: patch targets
```

- [ ] **Step 2: Compare it against the retired change set, file by file**

The retired change set is the repo at the old pin. Its patch targets and
`additions/` paths are derivable without checking anything out:

```bash
R=/home/lang/actions-runner/_work/camoucrome/camoucrome
git -C $R show 3d78ae2:patches/series > /tmp/series-153.txt   # last commit still on the old pin
# every path the old patches touched:
for p in $(cat /tmp/series-153.txt); do git -C $R show 3d78ae2:patches/$p; done \
  | grep '^+++ b/' | sed 's|^+++ b/||' | sort -u > /tmp/win-expected.txt
wc -l /tmp/win-expected.txt
comm -13 /tmp/win-expected.txt <(grep '^ M' /tmp/win-dirty.txt | sed 's/^ M //' | sort)
```

The `comm` output is the answer: any file modified in the Windows tree that the
old change set did not touch is uncommitted work, and the re-point must decide
about it explicitly rather than discarding it.

- [ ] **Step 3: Find a shell that can run the project's scripts on the host**

```powershell
foreach ($p in 'C:\Program Files\Git\bin\bash.exe','C:\Program Files\Git\usr\bin\bash.exe') { "$p : " + (Test-Path $p) }
```
Record which exists. `rebuild_branch.sh` and `apply.sh` are bash; the Windows
change loop cannot be written down until this is known.

- [ ] **Step 4: Write the finding into the runbook**

Add a "The Windows tree" section to `docs/superpowers/specs/repin-runbook.md`
giving: the tree's path, that it holds applied patches with no commits, the
`comm` result (what would be lost), the bash path from Step 3, and the ruling
that the re-point happens at the 2026-10-20 re-pin rather than per-milestone.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/repin-runbook.md
git commit  # subject: "docs(repin): what the Windows tree needs at the next re-point"
```

---

### Task 5: the measurement doc, and the PR

**Files:**
- Create: `docs/superpowers/measurements/2026-10-03-windows-substrate.md`

- [ ] **Step 1: Write the measurement**

One section per task, each with the command and its verbatim output: the host's
Python and playwright versions, the paths `lib_shell` resolved there, the RED and
the GREEN of Task 3 with counts, the triage table for any failing row, and
Task 4's `comm` result. State plainly what is still unverified on Windows: the
component build, the change loop end to end, the clients, fonts, and every
baseline-comparing verification (the binary is 153, the baselines are 154).

- [ ] **Step 2: Open the PR with that evidence in the body**

The body carries the counts, not a description of them. Say explicitly that
`build-verify` does not run on pull requests, and that nothing in this slice
touches the change set, so the box's binaries are unaffected.

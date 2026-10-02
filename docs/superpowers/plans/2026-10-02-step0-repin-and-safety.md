# Step 0 (Re-pin and Safety) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the change set to the current Chrome stable milestone with a scripted, timed procedure, and make the project survive a failed rebuild, a lost branch and a hostile workflow.

**Architecture:** Two small tools are written and tested on the Mac first (`rebuild_branch.sh` made atomic; a new `repin.py` that names the target version and rewrites the pin). The build box is then hardened and its CI runner re-registered, so that the re-pin itself (a `git rebase --onto` of the box branch, a from-scratch build and the verify sweep) ends in a green CI run. A recovery drill and a runbook close the step.

**Tech Stack:** bash, Python 3 (stdlib plus pytest), git, GitHub Actions and `gh`, WSL2 Ubuntu 24.04 on the build PC, Chromium's `gclient` / `gn` / `autoninja`.

**Spec:** `docs/superpowers/plans/2026-10-02-long-term-roadmap.md`, section "Step 0: re-pin and safety". The earlier re-pin is recorded in `docs/superpowers/measurements/2026-09-09-sp6a-version-honesty.md`.

## Global Constraints

- Pin to a stable **tag**, never a branch head and never `main` (sp6a §2).
- The target is a version on the **Windows** Stable channel that real users already run. `repin.py target` prints the newest listed one; on 2026-10-02 that is `155.0.8059.26`, an early-stable build listed four days before the 155 release date (2026-10-06), while most users are still on `154.0.8037.98`. Task 4 step 1 settles the choice against the Chrome installed on the Windows host.
- Never retry ssh password authentication to the build box (fail2ban). If the ssh master is down, stop and ask the owner to reconnect.
- Cut every git branch from `origin/main`, never from a local `main` that predates 2026-09-26 (the repo's history was rewritten then).
- `main` is protected: every repo change lands through a PR whose body carries evidence (command output with exit status).
- RED first: every check in this plan is seen failing once before its pass counts.
- The WSL build and the Windows build must not run at the same time. Before any build: `pgrep -x ninja; pgrep -x siso` in WSL returns nothing, and `Get-Process siso` on Windows returns nothing.
- Out of scope: rebuilding the Windows tree at `D:\camou-win` on the new pin. That opens roadmap step 1.
- The non-negotiable rules in `docs/superpowers/specs/00-conventions.md` are unchanged by this plan.

## File structure

| File | Responsibility |
|---|---|
| `scripts/rebuild_branch.sh` (modify) | Recreate a branch from the repo, atomically: on any failure nothing is left behind |
| `scripts/test_rebuild_branch.py` (create) | Tests of the above on a throwaway git repo |
| `scripts/repin.py` (create) | Name the target stable version, assert a version is shipped stable, rewrite the pin and its literals |
| `scripts/test_repin.py` (create) | Tests of the above with a fake fetch and a throwaway tree |
| `.github/workflows/checks.yml` (modify) | Run the two new test files |
| `docs/superpowers/specs/repin-runbook.md` (create) | The re-pin checklist and the recovery procedure |
| `docs/superpowers/measurements/2026-10-repin.md` (create) | What the re-pin and the drills measured, recorded as they run |
| `upstream.env`, `patches/`, `baselines/`, `scripts/*.py` (modify, in Task 4) | The new pin, re-cut patches, recaptured baselines |

Tasks 1 and 2 touch only the repo and are independent of each other. Task 3 touches only the build box and GitHub settings. Task 4 needs 1, 2 and 3. Task 5 needs 1 and 4.

---

### Task 1: `rebuild_branch.sh` leaves nothing behind when it fails

Today a failing patch stops the script under `set -e` after the worktree and the branch already exist. The script's own guard (`camoucrome/main already exists`) then refuses every later run. The fix builds under a temporary branch name and renames it only on success. A third argument names the branch, so the recovery drill can build beside the real one.

**Files:**
- Modify: `scripts/rebuild_branch.sh`
- Create: `scripts/test_rebuild_branch.py`
- Modify: `.github/workflows/checks.yml` (the pytest line)

**Interfaces:**
- Produces: `scripts/rebuild_branch.sh <chromium-src-dir> [worktree-dir] [branch]`. `branch` defaults to `camoucrome/main`. Exit 0 leaves `branch` checked out in `worktree-dir`. Any non-zero exit leaves no new branch and no worktree.

- [ ] **Step 1: Write the failing tests**

Create `scripts/test_rebuild_branch.py`:

```python
"""rebuild_branch.sh on a throwaway repo: success, atomic failure, custom branch."""
import os
import pathlib
import shutil
import signal
import subprocess
import time

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parent / "rebuild_branch.sh"

GOOD = """diff --git a/a.txt b/a.txt
--- a/a.txt
+++ b/a.txt
@@ -1 +1 @@
-one
+two
"""
BAD = """diff --git a/a.txt b/a.txt
--- a/a.txt
+++ b/a.txt
@@ -1 +1 @@
-this line is not in the file
+x
"""


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def env(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    git(src, "init", "-q")
    (src / "a.txt").write_text("one\n")
    git(src, "add", "a.txt")
    git(src, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "pin")
    rev = git(src, "rev-parse", "HEAD")
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "additions" / "camoucfg").mkdir(parents=True)
    (root / "settings").mkdir()
    (root / "patches").mkdir()
    shutil.copy(SCRIPT, root / "scripts" / "rebuild_branch.sh")
    (root / "upstream.env").write_text(f"CHROMIUM_REV={rev}\nCHROMIUM_TAG=0.0.0.0\n")
    (root / "additions" / "camoucfg" / "x.cc").write_text("// x\n")
    (root / "settings" / "invariants.json").write_text("{}\n")
    (root / "patches" / "good.patch").write_text(GOOD)
    (root / "patches" / "bad.patch").write_text(BAD)
    return src, root, tmp_path / "wt", rev


def run(root, src, wt, *extra):
    return subprocess.run(["bash", str(root / "scripts" / "rebuild_branch.sh"),
                           str(src), str(wt), *extra], capture_output=True, text=True)


def branches(src):
    return git(src, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()


def test_success_builds_one_commit_per_patch(env):
    src, root, wt, rev = env
    (root / "patches" / "series").write_text("good.patch\n")
    r = run(root, src, wt)
    assert r.returncode == 0, r.stderr
    assert git(src, "log", "--format=%s", f"{rev}..camoucrome/main") == "good"
    assert (wt / "a.txt").read_text() == "two\n"
    assert (wt / "components" / "camoucfg" / "x.cc").exists()
    assert (wt / "components" / "camoucfg" / "invariants.json").exists()


def test_failure_leaves_no_branch_and_no_worktree_and_a_rerun_works(env):
    src, root, wt, rev = env
    before = branches(src)
    (root / "patches" / "series").write_text("good.patch\nbad.patch\n")
    r = run(root, src, wt)
    assert r.returncode != 0
    assert "bad.patch" in r.stderr
    assert branches(src) == before
    assert not wt.exists()
    (root / "patches" / "series").write_text("good.patch\n")
    assert run(root, src, wt).returncode == 0


def test_third_argument_names_the_branch(env):
    src, root, wt, rev = env
    (root / "patches" / "series").write_text("good.patch\n")
    assert run(root, src, wt, "camoucrome/drill").returncode == 0
    assert "camoucrome/drill" in branches(src)
    assert "camoucrome/main" not in branches(src)


def test_refuses_an_existing_branch_without_touching_it(env):
    src, root, wt, rev = env
    (root / "patches" / "series").write_text("good.patch\n")
    git(src, "branch", "camoucrome/main", rev)
    r = run(root, src, wt)
    assert r.returncode != 0
    assert "already exists" in r.stderr
    assert git(src, "rev-parse", "camoucrome/main") == rev
    assert not wt.exists()


def test_a_relative_worktree_dir_is_refused(env):
    src, root, wt, rev = env
    (root / "patches" / "series").write_text("good.patch\n")
    before = branches(src)
    r = subprocess.run(["bash", str(root / "scripts" / "rebuild_branch.sh"), str(src), "rel-wt"],
                       capture_output=True, text=True, cwd=root)
    assert r.returncode != 0
    assert "absolute" in r.stderr
    assert branches(src) == before


def test_an_existing_worktree_dir_is_refused_and_left_alone(env):
    src, root, wt, rev = env
    (root / "patches" / "series").write_text("good.patch\n")
    before = branches(src)
    wt.mkdir()
    (wt / "marker").write_text("mine\n")
    r = run(root, src, wt)
    assert r.returncode != 0
    assert "already exists" in r.stderr
    assert (wt / "marker").read_text() == "mine\n"
    assert branches(src) == before


def test_a_series_without_a_trailing_newline_keeps_its_last_patch(env):
    src, root, wt, rev = env
    (root / "patches" / "series").write_text("good.patch")
    r = run(root, src, wt)
    assert r.returncode == 0, r.stderr
    assert git(src, "log", "--format=%s", f"{rev}..camoucrome/main") == "good"


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGHUP])
def test_a_signal_mid_run_leaves_no_branch_and_no_worktree(env, sig):
    src, root, wt, rev = env
    # SIGINT is not tested: a background job of a non-interactive shell inherits
    # it as ignored, and bash cannot trap a signal ignored at entry.
    # git apply blocks opening a FIFO, so the run is parked mid-series.
    os.mkfifo(root / "patches" / "block.patch")
    (root / "patches" / "series").write_text("good.patch\nblock.patch\n")
    before = branches(src)
    p = subprocess.Popen(["bash", str(root / "scripts" / "rebuild_branch.sh"), str(src), str(wt)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    try:
        # the good commit has landed on the temporary branch: the run is at block.patch
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                if wt.exists() and git(wt, "log", "--format=%s", f"{rev}..HEAD") == "good":
                    break
            except subprocess.CalledProcessError:
                pass  # git worktree add still running: not ready yet
            time.sleep(0.05)
        else:
            pytest.fail("the run never reached the blocking patch")
        os.killpg(p.pid, sig)
        p.wait(timeout=30)
    finally:
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
    assert p.returncode != 0
    assert branches(src) == before
    assert not wt.exists()


def test_a_signal_right_after_the_rename_keeps_the_finished_branch_and_worktree(env, tmp_path):
    src, root, wt, rev = env
    (root / "patches" / "series").write_text("good.patch\n")
    # A git wrapper that, once `git branch -m` has succeeded, signals its parent (the script).
    # bash runs the trap as soon as that foreground child returns: exactly the window
    # between the rename and whatever follows it.
    real_git = shutil.which("git")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    wrapper = bindir / "git"
    wrapper.write_text(f"""#!/bin/bash
{real_git} "$@"
rc=$?
case " $* " in *" branch "*"-m "*) [ "$rc" -eq 0 ] && kill -TERM $PPID ;; esac
exit $rc
""")
    wrapper.chmod(0o755)
    r = subprocess.run(["bash", str(root / "scripts" / "rebuild_branch.sh"), str(src), str(wt)],
                       capture_output=True, text=True, timeout=60,
                       env={**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"})
    assert r.returncode != 0
    assert git(src, "log", "--format=%s", f"{rev}..camoucrome/main") == "good"
    assert (wt / "a.txt").read_text() == "two\n"
    assert not [b for b in branches(src) if b.startswith("camoucrome/rebuild-")]
```

- [ ] **Step 2: Run the tests and see the real failures**

Run: `python3 -m pytest -q scripts/test_rebuild_branch.py`

Expected: 8 failed, 2 passed (run against the original script, before step 3). `test_failure_leaves_no_branch_and_no_worktree_and_a_rerun_works` fails first on `assert "bad.patch" in r.stderr`: the original script never names the failing patch (it also has no cleanup at all, so the branch and worktree stay behind and the rerun would be refused). `test_third_argument_names_the_branch` fails because the script ignores the third argument. `test_a_relative_worktree_dir_is_refused` and `test_an_existing_worktree_dir_is_refused_and_left_alone` fail because the original script has neither guard. `test_a_series_without_a_trailing_newline_keeps_its_last_patch` fails because `read` drops an unterminated last line. The two `test_a_signal_mid_run_leaves_no_branch_and_no_worktree` cases (SIGTERM, SIGHUP) fail because the original script has no cleanup and no trap, so the interrupted run leaves its branch behind. `test_a_signal_right_after_the_rename_keeps_the_finished_branch_and_worktree` fails on `assert r.returncode != 0` against the original (no trap, so the wrapper's SIGTERM is ignored by the script and it exits 0); against a cleanup keyed on a completion flag set after the rename it fails on the missing worktree. SIGINT is not in the signal test: a background job of a non-interactive shell inherits it as ignored and bash cannot trap it. Only `test_success_builds_one_commit_per_patch` and `test_refuses_an_existing_branch_without_touching_it` pass. If all ten pass, the tests measure nothing: stop and find out why.

- [ ] **Step 3: Rewrite the script body**

Replace everything in `scripts/rebuild_branch.sh` from the `# Usage:` comment line to the end of the file with:

```bash
# Usage: scripts/rebuild_branch.sh <chromium-src-dir> [worktree-dir] [branch]
# Refuses to run while the branch (default camoucrome/main) exists: delete it
# first, on purpose (if ~/chromium/src is checked out on it, detach src first,
# then delete; afterwards `git -C src checkout camoucrome/main` and drop the
# worktree). Atomic: the series is applied on a temporary branch that is
# renamed only when every patch has landed, and a failure removes the
# temporary branch and the worktree, so a failed run can simply be repeated.
# A signal after the rename exits non-zero (129/130/143) but keeps the finished
# branch and worktree.
set -euo pipefail

SRC="${1:?usage: rebuild_branch.sh <chromium-src-dir> [worktree-dir] [branch]}"
WT="${2:-/home/lang/camoumain}"
BRANCH="${3:-camoucrome/main}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=../upstream.env
. "$ROOT/upstream.env"

if git -C "$SRC" show-ref --quiet "refs/heads/$BRANCH"; then
  echo "error: $BRANCH already exists in $SRC; remove its worktree and branch first" >&2
  exit 1
fi
# git resolves a relative path against $SRC, the -e test against the cwd: with
# a relative path the guard could miss a worktree that cleanup then removes.
case "$WT" in /*) ;; *) echo "error: worktree dir must be an absolute path: $WT" >&2; exit 1 ;; esac
if [ -e "$WT" ]; then
  echo "error: $WT already exists; remove it or name another worktree dir" >&2
  exit 1
fi

TMP="camoucrome/rebuild-$$"
CURRENT="setup"
# CURRENT only names the failing step for the message. Whether the run finished
# is read from the repository: the script refuses to start while $BRANCH exists,
# so if it exists now, this run's rename succeeded and nothing is removed (a
# signal can land between the rename and the next line, and bash runs $? == 0
# in the EXIT trap after a signal, so neither can be trusted).
cleanup() {
  rc=$?
  if git -C "$SRC" show-ref --quiet "refs/heads/$BRANCH"; then
    exit "$rc"
  fi
  git -C "$SRC" worktree remove --force "$WT" 2>/dev/null || rm -rf "$WT"
  git -C "$SRC" worktree prune
  git -C "$SRC" branch -q -D "$TMP" 2>/dev/null || true
  echo "error: rebuild failed at $CURRENT; the temporary branch and $WT were removed" >&2
  [ "$rc" -ne 0 ] || rc=1
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

git -C "$SRC" worktree add -q -b "$TMP" "$WT" "$CHROMIUM_REV"
mkdir -p "$WT/components/camoucfg"
cp "$ROOT"/additions/camoucfg/* "$WT/components/camoucfg/"
cp "$ROOT/settings/invariants.json" "$WT/components/camoucfg/invariants.json"
while read -r p || [ -n "$p" ]; do
  case "$p" in ""|\#*) continue ;; esac
  CURRENT="$p"
  git -C "$WT" apply --3way "$ROOT/patches/$p"
  git -C "$WT" add -A
  git -C "$WT" -c user.name=camoucrome -c user.email=camoucrome@localhost commit -q -m "${p%.patch}"
  echo "  ${p%.patch}"
done < "$ROOT/patches/series"
CURRENT="rename"
git -C "$WT" branch -m "$TMP" "$BRANCH"
echo "$BRANCH: $(git -C "$WT" rev-list --count "$CHROMIUM_REV..HEAD") commits above $CHROMIUM_REV at $WT"
```

Leave the first seven lines of the file (the shebang and the description comment) as they are.

- [ ] **Step 4: Run the tests and see them pass**

Run: `python3 -m pytest -q scripts/test_rebuild_branch.py && bash -n scripts/rebuild_branch.sh; echo "exit=$?"`

Expected: `10 passed` and `exit=0`.

- [ ] **Step 5: Add the test file to CI**

In `.github/workflows/checks.yml`, in the step named `python client tests + packager tests`, append ` scripts/test_rebuild_branch.py` to the end of the `python3 -m pytest -q ...` line.

- [ ] **Step 6: Commit**

```bash
git checkout -b fix/rebuild-branch-atomic origin/main
git add scripts/rebuild_branch.sh scripts/test_rebuild_branch.py .github/workflows/checks.yml
git commit -m "fix(scripts): rebuild_branch.sh is atomic and takes a branch name"
```

Open the PR with the RED output of step 2 and the GREEN output of step 4 in its body.

---

### Task 2: `repin.py` names the target and rewrites the pin

Three small commands. `target` prints the newest Windows stable version. `check` exits non-zero unless a version is listed as shipped on Stable (the "A5" assertion sp6a §2 asked for and nobody built). `retarget` rewrites `upstream.env`, renames the baselines that carry the old build number or revision in their names, and rewrites the same literals in `scripts/*.py`.

`retarget` deliberately does not touch `settings/`: the captured profiles there (`settings/audio.json`, `settings/webgl/*.json`) record the Chrome version they were captured from, and that stays true until they are captured again.

**Files:**
- Create: `scripts/repin.py`
- Create: `scripts/test_repin.py`
- Modify: `.github/workflows/checks.yml` (the pytest line)

**Interfaces:**
- Produces, as a module: `newest(versions: list[str]) -> str`; `stable_versions(platform: str = "Windows", fetch=None) -> list[str]`; `retarget(root: pathlib.Path, new_tag: str, new_rev: str) -> list[str]` (returns the paths it changed or renamed, relative to `root`).
- Produces, as a CLI: `repin.py target [--platform P]` prints one version; `repin.py check <version> [--platform P]` exits 0 or 1; `repin.py retarget <new_tag> <new_rev>` prints the changed paths.
- Consumes: `upstream.env` with `CHROMIUM_REV=` and `CHROMIUM_TAG=` lines.

- [ ] **Step 1: Write the failing tests**

Create `scripts/test_repin.py`:

```python
"""repin.py: version choice, the shipped-stable assertion, and the pin rewrite."""
import json
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import repin  # noqa: E402

OLD_REV = "507c6ee3e2f3b2ca0e660547e5b9ea4820c67f4c"
NEW_REV = "0123456789abcdef0123456789abcdef01234567"


def fake_fetch(versions):
    def fetch(url):
        assert "channel=Stable" in url and "platform=Windows" in url
        return json.dumps([{"version": v, "time": 1} for v in versions])
    return fetch


def test_newest_compares_numerically_not_as_text():
    assert repin.newest(["154.0.8037.9", "154.0.8037.98", "153.0.8010.36"]) == "154.0.8037.98"


def test_stable_versions_reads_the_channel_listing():
    got = repin.stable_versions(fetch=fake_fetch(["154.0.8037.98", "153.0.8010.36"]))
    assert got == ["154.0.8037.98", "153.0.8010.36"]


def test_stable_versions_refuses_an_empty_listing():
    with pytest.raises(SystemExit):
        repin.stable_versions(fetch=fake_fetch([]))


@pytest.fixture
def tree(tmp_path):
    root = tmp_path
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "upstream.env").write_text(
        "# refuses any other HEAD\n"
        f"CHROMIUM_REV={OLD_REV}\n"
        "# The tag that commit is: Chrome stable 153.0.8010.36 (refs/tags/153.0.8010.36,\n"
        "# branch-heads/8010).\n"
        "CHROMIUM_TAG=153.0.8010.36\n")
    (root / "scripts").mkdir()
    (root / "scripts" / "verify_x.py").write_text(
        'BASE = "baselines/chrome-8010-stock-oracle-windows.json"\n'
        'UA = "baselines/chrome-507c6ee3e2-stock-ua.json"\n'
        'STOCK_BASE_COMMIT = "507c6ee3e2"\n'
        'META = {"chrome": "153.0.8010.36"}\n'
        "PORT = 8010\n")
    (root / "settings").mkdir()
    (root / "settings" / "audio.json").write_text('{"chrome": "153.0.8010.36"}\n')
    (root / "baselines").mkdir()
    for name in ("chrome-8010-stock-oracle-windows.json", "content_shell-8010-stock-ua.json",
                 "chrome-507c6ee3e2-stock-ua.json", "chrome-0e8d4a9268-stock-ua.json"):
        (root / "baselines" / name).write_text("{}\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x"],
                   cwd=root, check=True)
    return root


def test_retarget_rewrites_the_pin_and_renames_the_baselines(tree):
    changed = repin.retarget(tree, "154.0.8037.98", NEW_REV)
    env = (tree / "upstream.env").read_text()
    assert f"CHROMIUM_REV={NEW_REV}\n" in env
    assert "CHROMIUM_TAG=154.0.8037.98\n" in env
    assert "refs/tags/154.0.8037.98" in env and "branch-heads/8037" in env
    assert "8010" not in env and OLD_REV not in env
    names = sorted(p.name for p in (tree / "baselines").iterdir())
    assert names == ["chrome-0123456789-stock-ua.json", "chrome-0e8d4a9268-stock-ua.json",
                     "chrome-8037-stock-oracle-windows.json", "content_shell-8037-stock-ua.json"]
    script = (tree / "scripts" / "verify_x.py").read_text()
    assert "chrome-8037-stock-oracle-windows.json" in script
    assert "chrome-0123456789-stock-ua.json" in script
    assert 'STOCK_BASE_COMMIT = "0123456789"' in script
    assert '"chrome": "154.0.8037.98"' in script
    assert "upstream.env" in changed and "scripts/verify_x.py" in changed


def test_retarget_leaves_unrelated_numbers_and_settings_alone(tree):
    repin.retarget(tree, "154.0.8037.98", NEW_REV)
    assert "PORT = 8010\n" in (tree / "scripts" / "verify_x.py").read_text()
    assert (tree / "settings" / "audio.json").read_text() == '{"chrome": "153.0.8010.36"}\n'


def test_retarget_refuses_a_malformed_tag_or_revision(tree):
    with pytest.raises(SystemExit):
        repin.retarget(tree, "154.0.8037", NEW_REV)
    with pytest.raises(SystemExit):
        repin.retarget(tree, "154.0.8037.98", "0123abc")


def test_a_failed_rename_leaves_the_pin_so_a_rerun_finishes_the_job(tree):
    extra = tree / "baselines" / "content_shell-8010-stock-extra.json"
    extra.write_text("{}\n")  # untracked: git mv refuses it
    with pytest.raises(subprocess.CalledProcessError):
        repin.retarget(tree, "154.0.8037.98", NEW_REV)
    env = (tree / "upstream.env").read_text()
    assert OLD_REV in env and "CHROMIUM_TAG=153.0.8010.36\n" in env
    subprocess.run(["git", "add", str(extra)], cwd=tree, check=True)
    repin.retarget(tree, "154.0.8037.98", NEW_REV)
    assert "CHROMIUM_TAG=154.0.8037.98\n" in (tree / "upstream.env").read_text()
    assert not [p for p in (tree / "baselines").iterdir() if "-8010-stock" in p.name]
    assert "chrome-8037-stock-oracle-windows.json" in (tree / "scripts" / "verify_x.py").read_text()
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `python3 -m pytest -q scripts/test_repin.py`

Expected: an import error, `ModuleNotFoundError: No module named 'repin'`.

- [ ] **Step 3: Write the tool**

Create `scripts/repin.py`:

```python
#!/usr/bin/env python3
"""The re-pin's three mechanical steps (the procedure itself is
docs/superpowers/specs/repin-runbook.md).

  repin.py target [--platform Windows]     newest version on the Stable channel
  repin.py check <version> [--platform P]  exit 1 unless <version> shipped on Stable
  repin.py retarget <new_tag> <new_rev>    rewrite upstream.env, rename the baselines
                                           named after the old build or revision, and
                                           rewrite those literals in scripts/*.py

retarget does not touch settings/: the captured profiles there record the
Chrome they were captured from, which stays true until they are recaptured.
Read `git diff` after it; a comment that tells the pin's history must keep the
old value, and only a reader can tell which one that is.
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DASH = "https://chromiumdash.appspot.com/fetch_releases?channel=Stable&platform={platform}&num=30"
TAG_RE = re.compile(r"\d+\.\d+\.\d+\.\d+")
REV_RE = re.compile(r"[0-9a-f]{40}")


def _get(url):
    # curl, not urllib: the python.org build on macOS ships without a CA
    # bundle and fails every https request with CERTIFICATE_VERIFY_FAILED.
    return subprocess.run(["curl", "-fsS", "-m", "30", url], check=True,
                          capture_output=True, text=True).stdout


def newest(versions):
    return max(versions, key=lambda v: tuple(int(x) for x in v.split(".")))


def stable_versions(platform="Windows", fetch=None):
    rows = json.loads((fetch or _get)(DASH.format(platform=platform)))
    versions = [r["version"] for r in rows]
    if not versions:
        sys.exit(f"chromiumdash lists no Stable release for {platform}")
    return versions


def _env(root):
    text = (root / "upstream.env").read_text()
    rev = re.search(r"^CHROMIUM_REV=(\S+)$", text, re.M)
    tag = re.search(r"^CHROMIUM_TAG=(\S+)$", text, re.M)
    if not rev or not tag:
        sys.exit("upstream.env has no CHROMIUM_REV / CHROMIUM_TAG line")
    return text, rev.group(1), tag.group(1)


def retarget(root, new_tag, new_rev):
    if not TAG_RE.fullmatch(new_tag):
        sys.exit(f"'{new_tag}' is not a MAJOR.MINOR.BUILD.PATCH version")
    if not REV_RE.fullmatch(new_rev):
        sys.exit(f"'{new_rev}' is not a 40-character revision")
    text, old_rev, old_tag = _env(root)
    old_build, new_build = old_tag.split(".")[2], new_tag.split(".")[2]
    old_short, new_short = old_rev[:10], new_rev[:10]
    changed = []

    # Only the three shapes a pin takes in a name or a literal; a bare build
    # number is not replaced, so an unrelated 8010 survives.
    pairs = [(f"-{old_build}-stock", f"-{new_build}-stock"),
             (f"-{old_short}-stock", f"-{new_short}-stock"),
             (old_tag, new_tag), (old_short, new_short)]

    for f in sorted((root / "baselines").glob("*")):
        name = f.name
        for a, b in pairs[:2]:
            name = name.replace(a, b)
        if name != f.name:
            subprocess.run(["git", "-C", str(root), "mv", f"baselines/{f.name}", f"baselines/{name}"],
                           check=True)
            changed.append(f"baselines/{name}")

    for f in sorted((root / "scripts").glob("*.py")):
        if f.name in ("repin.py", "test_repin.py"):
            continue
        before = f.read_text()
        after = before
        for a, b in pairs:
            after = after.replace(a, b)
        if after != before:
            f.write_text(after)
            changed.append(f"scripts/{f.name}")

    # Last: upstream.env is what a rerun reads as "old", so it must not move
    # until the renames and rewrites above have all succeeded.
    env = (text.replace(old_rev, new_rev).replace(old_tag, new_tag)
               .replace(f"branch-heads/{old_build}", f"branch-heads/{new_build}"))
    (root / "upstream.env").write_text(env)
    changed.append("upstream.env")
    return changed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("target")
    t.add_argument("--platform", default="Windows")
    c = sub.add_parser("check")
    c.add_argument("version")
    c.add_argument("--platform", default="Windows")
    r = sub.add_parser("retarget")
    r.add_argument("new_tag")
    r.add_argument("new_rev")
    a = ap.parse_args()
    if a.cmd == "target":
        print(newest(stable_versions(a.platform)))
    elif a.cmd == "check":
        if a.version not in stable_versions(a.platform):
            sys.exit(f"{a.version} is not listed as shipped on {a.platform} Stable")
        print(f"{a.version}: shipped on {a.platform} Stable")
    else:
        for path in retarget(ROOT, a.new_tag, a.new_rev):
            print(path)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `python3 -m pytest -q scripts/test_repin.py; echo "exit=$?"`

Expected: `7 passed` and `exit=0`.

- [ ] **Step 5: Run the two network commands for real, both ways**

Run:

```bash
python3 scripts/repin.py target; echo "exit=$?"
python3 scripts/repin.py check "$(python3 scripts/repin.py target)"; echo "exit=$?"
python3 scripts/repin.py check 154.0.8026.0; echo "exit=$?"
```

Expected: the first prints one version such as `155.0.8059.26` with `exit=0`. The second prints `<version>: shipped on Windows Stable` with `exit=0`. The third is the RED case (`154.0.8026.0` was the Dev-only build number of the first pin): it prints `154.0.8026.0 is not listed as shipped on Windows Stable` with `exit=1`.

- [ ] **Step 6: Add the test file to CI and commit**

In `.github/workflows/checks.yml`, append ` scripts/test_repin.py` to the same `python3 -m pytest -q ...` line that Task 1 extended.

```bash
git checkout -b feat/repin-tool origin/main
git add scripts/repin.py scripts/test_repin.py .github/workflows/checks.yml
git commit -m "feat(scripts): repin.py names the stable target and rewrites the pin"
```

Open the PR with the outputs of steps 2, 4 and 5 in its body. If Task 1's PR is not merged yet, the two PRs conflict on the one pytest line; merge Task 1 first and rebase.

---

### Task 3: Harden the build box, then re-register the runner

The repo is public, and the workflow `build-verify` runs repo code on the only build machine. On the recreated GitHub repo no runner is registered at all, so `build-verify` cannot run. This task removes the two ways workflow code could leave the Linux user it runs as, then brings the runner back.

**The decision this plan takes** (the roadmap left it open): the runner keeps running as `lang`, with passwordless sudo removed and WSL interop and automount turned off. A separate runner user is not created. The reason: the job has to write the same build tree `lang` owns (`/home/lang/chromium/src/out/Default`), so a second user needs write access to exactly what it would be isolated from. What a second user would still protect is the rest of `lang`'s home; step 1 checks that it holds no credentials. If step 1 finds credentials that cannot be removed, stop and revisit this decision.

What each change closes:

| Change | Closes |
|---|---|
| No `NOPASSWD` sudo for `lang` | Workflow code becoming root in WSL |
| `[interop] enabled=false` | Workflow code running Windows programs as the Windows user |
| `[automount] enabled=false` | Workflow code writing Windows files through `/mnt/c` (for example into a Startup folder) |

The owner keeps root: `wsl -d Ubuntu-24.04 -u root` from Windows needs no password.

**Files:**
- Modify on the box: the sudoers file that grants `NOPASSWD`, and `/etc/wsl.conf`
- Create: `docs/superpowers/measurements/2026-10-repin.md` (the "Runner hardening" section)

**Interfaces:**
- Produces: a self-hosted runner named `buildpc-wsl` with the label `buildpc-wsl`, online on `lang315/camoucrome`. Task 4 relies on `gh workflow run build-verify.yml` working.

All box commands below run through ssh to the Windows host and then `wsl -d Ubuntu-24.04 -u <user>`. Commands marked **root** use `-u root`.

- [ ] **Step 1: Inventory, read-only**

Run on the box as `lang`:

```bash
sudo -n true; echo "sudo_rc=$?"
grep -rn 'NOPASSWD' /etc/sudoers /etc/sudoers.d/ 2>/dev/null
cat /etc/wsl.conf
systemctl list-units --all --no-legend 'actions.runner*'
ls -la ~/.ssh ~/.netrc ~/.git-credentials ~/.config/gh ~/.docker/config.json ~/.aws 2>&1
ls /mnt/c 2>&1 | head -3
cmd.exe /c ver 2>&1 | head -2
```

Run in the repo on the Mac:

```bash
grep -rn 'sudo\|/mnt/\|\.exe\|powershell' .github/workflows/*.yml scripts/*.sh scripts/lib_shell.py scripts/run_coherence_tests.sh; echo "grep_rc=$?"
```

Expected and recorded as the RED state: `sudo_rc=0`; one `NOPASSWD` line naming `lang` or a group `lang` is in, with its file path; `/etc/wsl.conf` holding only `[boot]` / `systemd=true`; one `actions.runner.*` unit; `/mnt/c` listing Windows directories; `cmd.exe` printing a Windows version. Every credential path should read "No such file or directory". The Mac grep should print nothing with `grep_rc=1` (nothing in CI uses sudo, `/mnt` or a Windows program).

Write the outputs into `docs/superpowers/measurements/2026-10-repin.md` under a heading `## Runner hardening`, as "before".

If a credential file exists, stop: remove it or revisit the decision above before going on.

- [ ] **Step 2: Remove passwordless sudo**

Run on the box as **root**, with `FILE` set to the path step 1 printed:

```bash
FILE=/etc/sudoers.d/REPLACE_WITH_THE_PATH_FROM_STEP_1
cp -a "$FILE" "/root/$(basename "$FILE").bak-2026-10"
sed -i '/NOPASSWD/d' "$FILE"
visudo -c; echo "visudo_rc=$?"
```

Expected: `visudo_rc=0` and "parsed OK" for every file. If `visudo -c` reports an error, restore the backup at once: `cp -a "/root/$(basename "$FILE").bak-2026-10" "$FILE"`.

If the `NOPASSWD` line is in `/etc/sudoers` itself and not under `/etc/sudoers.d/`, set `FILE=/etc/sudoers` and use the same four commands.

- [ ] **Step 3: Turn off interop and automount**

First confirm no build is running, because the next step restarts WSL. On the box as `lang`: `pgrep -x ninja; pgrep -x siso; echo "rc=$?"` must print only `rc=1`. On Windows: `(Get-Process siso -ErrorAction SilentlyContinue | Measure-Object).Count` must print `0`.

Run on the box as **root**:

```bash
cp -a /etc/wsl.conf /root/wsl.conf.bak-2026-10
cat > /etc/wsl.conf <<'EOF'
[boot]
systemd=true

[interop]
enabled=false
appendWindowsPath=false

[automount]
enabled=false
EOF
```

Then on Windows (PowerShell over ssh): `wsl --shutdown`, wait 10 seconds, and start it again with `wsl -d Ubuntu-24.04 -u lang -- true`.

- [ ] **Step 4: See the three doors closed**

Run on the box as `lang`:

```bash
sudo -n true; echo "sudo_rc=$?"
ls /mnt/c 2>&1 | head -3; echo "mnt_entries=$(ls /mnt/c 2>/dev/null | wc -l)"
cmd.exe /c ver 2>&1 | head -2; echo "cmd_rc=$?"
systemctl is-system-running
```

Expected: `sudo_rc=1` with "a password is required"; `mnt_entries=0`; `cmd.exe: command not found` (or "Exec format error") with a non-zero `cmd_rc`; and `running` or `degraded` from systemd (`degraded` is acceptable only if the failed unit is the old runner service, which step 6 replaces).

Record these as "after" in the measurement doc.

- [ ] **Step 5: See that the box still builds and verifies**

Run on the box as `lang`:

```bash
export PATH=/home/lang/depot_tools:$PATH
cd ~/chromium/src && autoninja -C out/Default content_shell 2>&1 | tail -2
~/camoucrome-verify/venv/bin/python3 ~/camoucrome-client/scripts/verify_review_2026_09_24.py 2>&1 | tail -1
```

Expected: the build ends without an error (a no-op build is fine here; this checks the toolchain starts, not that anything compiles), and the verify prints `12/12 ALL_PASS`. If either fails only since step 3, an undetected dependency on interop or `/mnt` exists: restore `/root/wsl.conf.bak-2026-10`, restart WSL, and report what broke before continuing.

- [ ] **Step 6: Re-register the runner on the new repo**

Find the runner directory. On the box as `lang`:

```bash
systemctl cat 'actions.runner*' 2>/dev/null | grep -m1 WorkingDirectory
```

Call the printed directory `RUNNER_DIR`. Then, on the box as **root** (the service scripts need root, and `lang` no longer has sudo):

```bash
cd RUNNER_DIR && ./svc.sh stop; ./svc.sh uninstall
```

On the Mac, get a one-hour registration token (do not write it to a file):

```bash
gh api -X POST repos/lang315/camoucrome/actions/runners/registration-token -q .token
```

On the box as `lang`, with the token pasted in place of `TOKEN`:

```bash
cd RUNNER_DIR && rm -f .runner .credentials .credentials_rsaparams
./config.sh --unattended --url https://github.com/lang315/camoucrome --token TOKEN \
  --name buildpc-wsl --labels buildpc-wsl --replace
```

On the box as **root**:

```bash
cd RUNNER_DIR && ./svc.sh install lang && ./svc.sh start && ./svc.sh status | head -5
```

Expected: `config.sh` prints "Runner successfully added" and "Runner connection is good"; `svc.sh status` shows the unit `active (running)` with `User=lang`.

- [ ] **Step 7: See the runner online and a CI run green**

Run on the Mac:

```bash
gh api repos/lang315/camoucrome/actions/runners -q '.runners[] | "\(.name) \(.status) \([.labels[].name] | join(","))"'
gh workflow run build-verify.yml --ref main
sleep 20
gh run watch "$(gh run list --workflow build-verify.yml --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status; echo "exit=$?"
```

Expected: `buildpc-wsl online self-hosted,Linux,X64,buildpc-wsl`, then `exit=0`. Record the run URL in the measurement doc.

- [ ] **Step 8: Confirm the GitHub-side settings still hold**

Run on the Mac:

```bash
R=repos/lang315/camoucrome
gh api $R/actions/permissions -q .allowed_actions
gh api $R/actions/permissions/fork-pr-contributor-approval -q .approval_policy
gh api $R/branches/main/protection -q '"checks=\(.required_status_checks.contexts) force=\(.allow_force_pushes.enabled)"'
```

Expected: `selected`, `all_external_contributors`, `checks=["checks"] force=false`. `build-verify` runs only on a push to `main` and on a manual dispatch, so a fork's pull request never reaches the runner.

- [ ] **Step 9: Commit the record**

```bash
git checkout -b docs/runner-hardening origin/main
git add docs/superpowers/measurements/2026-10-repin.md
git commit -m "docs: runner hardening on the build box (no sudo, interop and automount off)"
```

Open the PR with the before and after outputs and the green run URL in its body.

---

### Task 4: The re-pin, timed

The box branch is rebased onto the new tag. A rebase keeps every commit, including the ones that touch only `components/camoucfg` and so produce no patch, and it stops on a conflict in the ordinary way. The old branch is kept until the sweep on the new base passes.

Throughout, write each measured duration into `docs/superpowers/measurements/2026-10-repin.md` under `## Re-pin`, in a table with the columns: step, duration, result. The roadmap needs these numbers to judge whether "never more than one milestone behind" can be kept.

**Files:**
- Modify: `upstream.env`, `patches/*.patch`, `patches/series`, `additions/`, `settings/invariants.json` (through `export.sh`)
- Modify: `baselines/` (renamed, then recaptured), `scripts/*.py` (through `repin.py retarget`)
- Modify: `docs/superpowers/measurements/2026-10-repin.md`

**Interfaces:**
- Consumes: `scripts/repin.py` (Task 2), the registered runner (Task 3).
- Produces: `upstream.env` on the new tag; box branch `camoucrome/main` on the new base; box branch `camoucrome/main-8010` holding the retired stack.

In the commands below, `NEW_TAG` is the output of `python3 scripts/repin.py target` at the time this task starts, `NEW_BUILD` is its third component, and `OLD_REV` is `507c6ee3e2f3b2ca0e660547e5b9ea4820c67f4c`.

- [ ] **Step 1: Name the target and check the control Chrome**

On the Mac: `python3 scripts/repin.py target`. Write the version down as the candidate `NEW_TAG`.

On the Windows host (PowerShell over ssh):

```powershell
(Get-Item "C:\Program Files\Google\Chrome\Application\chrome.exe").VersionInfo.ProductVersion
```

Expected: the same version as `NEW_TAG`. The stock baselines are recaptured from this Chrome in step 8, so they must describe the version being pinned.

If the two differ, the host's version decides, because a staged rollout means the newest listed version may reach only a few users for days:

- Open `chrome://settings/help` on the host so Chrome takes whatever update it is offered, and read the version again.
- Set `NEW_TAG` to the host's version, and confirm it with `python3 scripts/repin.py check <host version>` (exit 0).
- If that check fails, the host is on a version that never shipped on Stable: stop and find out why before pinning anything.

- [ ] **Step 2: Fetch the tag and predict the conflicts**

On the box as `lang`:

```bash
cd ~/chromium/src
bash ~/camoucrome-client/scripts/check_checkout_sync.sh local; echo "sync_rc=$?"
time git fetch --depth=1 origin "refs/tags/NEW_TAG:refs/tags/NEW_TAG"
NEW_REV=$(git rev-parse "NEW_TAG^{commit}"); echo "NEW_REV=$NEW_REV"
git show "NEW_TAG:chrome/VERSION"
git diff --stat OLD_REV NEW_TAG -- $(git diff --name-only OLD_REV camoucrome/main -- . ':(exclude)components/camoucfg') | tail -1
```

Expected: `sync_rc=0` (the box tree equals the repo before anything moves); `chrome/VERSION` reading the four numbers of `NEW_TAG`; and a last line such as `23 files changed, ...`. Record `NEW_REV` and that file count as the prediction. Only those files can conflict.

- [ ] **Step 3: Rebase a copy of the branch**

On the box as `lang`:

```bash
cd ~/chromium/src
git branch camoucrome/main-NEW_BUILD camoucrome/main
git worktree add -q ~/camourebase camoucrome/main-NEW_BUILD
cd ~/camourebase
time git -c user.name=camoucrome -c user.email=camoucrome@localhost rebase --onto NEW_TAG OLD_REV
```

For each conflict the rebase stops on: read both sides, resolve in the file, `git add` it, and run `git -c user.name=camoucrome -c user.email=camoucrome@localhost rebase --continue`. Keep the commit subject unchanged (it is the patch stem). Record in the measurement doc, per conflict: the patch stem, the file, how many hunks, what upstream changed, and how it was resolved. The earlier re-pin had one conflicting hunk in 26 patches.

Expected at the end:

```bash
git rev-list --count NEW_TAG..HEAD
git rev-list --count OLD_REV..camoucrome/main
```

Both print the same number (37 on 2026-10-02).

One commit needs a manual edit after the rebase: `windows-oracle` carries a code comment naming `baselines/chrome-507c6ee3e2-stock-ua.json` (see `patches/windows-oracle.patch` line 45). Amend that comment, in that commit on the box branch `camoucrome/main-NEW_BUILD`, to the new baseline name (`chrome-<first 10 characters of NEW_REV>-stock-ua.json`), so the export in step 6 carries it. Change it on the box branch, never by editing `patches/` by hand.

- [ ] **Step 4: Move the main checkout to the new base and build from scratch**

Confirm no build is running on either OS (Global Constraints). Then on the box as `lang`:

```bash
cd ~/chromium/src
git worktree remove ~/camourebase
git checkout -f --detach NEW_TAG
time gclient sync --revision "src@$NEW_REV" -D
time gclient runhooks
cat chrome/VERSION
git checkout camoucrome/main-NEW_BUILD
gn gen out/Default && gn check out/Default '//components/camoucfg:*' && gn check out/Default //content/shell:content_shell
time autoninja -C out/Default chrome content_shell components_unittests 2>&1 | tail -3
```

Expected: `chrome/VERSION` at the new tag; "Header dependency check OK" twice; a build that ends in success with a **non-zero** step count in the tens of thousands (a base move invalidates everything). The earlier re-pin took about 4 hours for `content_shell` alone on this machine. A build over ssh must be started in the foreground of a session that stays open, or detached; see the owner's notes on ssh drops.

Unlike the earlier re-pin, this builds the patched branch directly and not a pristine tree first. The pristine tree was needed only to capture the stock `content_shell` baseline, which step 8 does separately.

- [ ] **Step 5: Unit suites**

On the box as `lang`, the same suites `build-verify` runs:

```bash
cd ~/chromium/src
grep -n -A10 'camoucfg unit suites' ~/camoucrome-client/.github/workflows/build-verify.yml | head -14
```

Run exactly the command block that step shows, then `bash ~/camoucrome-client/scripts/run_coherence_tests.sh`.

Expected: every suite PASSED with the counts the workflow asserts, and `6/6` from the coherence script. A compile error here is a patch that applied cleanly but no longer matches upstream's API: fix it in the commit that owns the file (`git commit --fixup` then `git rebase -i --autosquash` is not available non-interactively, so amend with `git rebase --exec` or re-apply by hand), and record it as a semantic conflict.

- [ ] **Step 6: Export into the repo and retarget the pin**

On the Mac, on a new branch:

```bash
git checkout -b repin/NEW_BUILD origin/main
python3 scripts/repin.py retarget NEW_TAG NEW_REV
git status --short
```

`git mv` stages the renames, so `git diff --stat` would not show them. Read both `git status --short` (the baseline renames) and `git diff` of `scripts/` (the literal changes) in full. Any comment that tells the pin's history (for example "0e8d4a9268 -> 507c6ee3e2, captured that way" in `scripts/verify_sp1a_chrome.py`) must keep its old value: restore that line by hand and add the new move beside it.

Add one line to the `# History:` comment in `upstream.env` recording the old pin and the date.

Then run the export round trip described at the top of `scripts/export.sh` against `camoucrome/main-NEW_BUILD`:

```bash
bash ~/camoucrome-cs/scripts/export.sh ~/chromium/src camoucrome/main-NEW_BUILD
```

and bring `additions`, `patches` and `settings/invariants.json` back to the Mac. Then:

```bash
git status --porcelain additions patches settings | wc -l
git diff --stat -- patches | tail -1
```

Expected: a non-zero count (the re-cut patches). Record how many patches changed and classify each change as an `index` line, a hunk offset, or a real content change. Only resolved conflicts should be content changes.

- [ ] **Step 7: The verify sweep on the new base**

On the box, sync the client tree the verifies import (the `sync the client tree` step of `build-verify.yml` shows the commands), then run every verify the earlier re-pin ran: the `content_shell` scripts, then the ones that need `chrome`.

```bash
cd ~/camoucrome-client/scripts
for s in verify_*.py; do
  [ "$s" = verify_webrtc_ii_fakeip.py ] && continue
  ~/camoucrome-verify/venv/bin/python3 "$s" > "/tmp/sweep.$s.log" 2>&1; echo "rc=$? $s $(tail -1 "/tmp/sweep.$s.log" | cut -c1-80)"
done | tee /tmp/sweep.summary
grep -c '^rc=0' /tmp/sweep.summary; grep -v '^rc=0' /tmp/sweep.summary
```

`verify_webrtc_ii_fakeip.py` is excluded on purpose: it is the RED record of a rejected slice and fails by design.

Expected: scripts that compare against a stock baseline fail here, because the baselines still describe Chrome 153. That is the correct RED, and step 8 resolves it. Every other script passes at its asserted count. Record the full summary. A failure that is not a baseline comparison is a regression from the re-pin: debug it before going on.

- [ ] **Step 8: Recapture the baselines, the only legitimate way**

Stock baselines from the Windows host's Chrome (it is `NEW_TAG`, checked in step 1). On the box:

```bash
cd ~/camoucrome-client/scripts
for c in capture_host_oracle.py capture_font_metrics.py capture_chrome_object.py; do
  ~/camoucrome-verify/venv/bin/python3 "$c" 2>&1 | tail -1
done
```

Stock UA baselines from a pristine tree at the tag. `capture_ua_baseline.py` prints its JSON to stdout, so every run is redirected into a file, and `--shell` takes the path of the binary (the default is `content_shell`; a bare `chrome` is not a path). `NEW_SHORT` is the first 10 characters of `NEW_REV`. `verify_sp1a_chrome.py` reads the stock `chrome` baseline from `~/camoucrome-verify/baselines/chrome-NEW_SHORT-stock-ua.json` (`retarget` already rewrote that path in the script), and that directory is not covered by `check_checkout_sync.sh`, so the file lands there first and is then copied into the repo. On the box:

```bash
cd ~/chromium/src && git checkout -f --detach NEW_TAG
time autoninja -C out/Default chrome content_shell 2>&1 | tail -2
cd ~/camoucrome-client/scripts
PY=~/camoucrome-verify/venv/bin/python3
CHROME=~/chromium/src/out/Default/chrome
mkdir -p ~/camoucrome-verify/baselines
$PY capture_ua_baseline.py --shell "$CHROME" > /tmp/ua1.json
$PY capture_ua_baseline.py --shell "$CHROME" > /tmp/ua2.json
sha256sum /tmp/ua1.json /tmp/ua2.json
```

Expected: the two sha256 values are identical (the capture is deterministic; two runs hashed identically in the earlier re-pin). If they differ, stop. Then:

```bash
cp /tmp/ua1.json ~/camoucrome-verify/baselines/chrome-NEW_SHORT-stock-ua.json
sha256sum ~/camoucrome-verify/baselines/chrome-NEW_SHORT-stock-ua.json
```

That deployed file is also the one brought back to the Mac (scp) into the repo's `baselines/`, replacing the file `retarget` renamed. The JSON's `provenance` must read `"binary": "chrome"` and `"captured_at_commit": "NEW_SHORT"`; `verify_sp1a_chrome.py` refuses the file otherwise.

The `content_shell` stock UA baseline, `baselines/content_shell-NEW_BUILD-stock-ua.json`: the capture command for this baseline is not recorded in the repo (sp6a section 4 says only "stock baseline captured from it", the pristine `content_shell`); determine it on the box before this step. What the repo does show is that `baselines/content_shell-8010-stock-ua.json` has `provenance.binary` = `content_shell` and `captured_at_commit` = `507c6ee3e2`, which is what `capture_ua_baseline.py` writes when run against the default `content_shell` binary, so the likely form is `capture_ua_baseline.py > /tmp/ua_shell.json` with no `--shell`. Treat that as a hypothesis, and accept the file only if its `provenance` reads `"binary": "content_shell"` and `"captured_at_commit": "NEW_SHORT"`. Copy it into the repo's `baselines/content_shell-NEW_BUILD-stock-ua.json`.

Then rebuild the patched branch:

```bash
cd ~/chromium/src && git checkout camoucrome/main-NEW_BUILD && time autoninja -C out/Default chrome content_shell 2>&1 | tail -2
```

Update the sha256 that `scripts/verify_sp1a_chrome.py` pins beside `STOCK_BASE_COMMIT`. Read every difference between the old and new baselines before accepting it: a moved value is "the signal to stop and ask why", and the answer must be the re-pin and nothing else. Record the differences.

Bring the recaptured baselines back to the Mac into `baselines/`, re-run step 7's sweep, and expect every script green at its asserted count.

Gate: a baseline that `retarget` renamed but nobody recaptured still describes the old Chrome. On the Mac:

```bash
git diff -M --summary origin/main -- baselines | grep '(100%)'; echo "unchanged_renames_rc=$?"
```

Expected: no line printed and `unchanged_renames_rc=1`. A line here names a baseline whose content still describes the old Chrome.

- [ ] **Step 9: Switch the branch names and close the gates**

On the box as `lang`:

```bash
cd ~/chromium/src
git branch -m camoucrome/main camoucrome/main-8010
git branch -m camoucrome/main-NEW_BUILD camoucrome/main
git checkout camoucrome/main
```

Then run the export once more against `camoucrome/main` and, on the Mac:

```bash
git status --porcelain additions patches settings | wc -l
bash scripts/check_checkout_sync.sh; echo "sync_rc=$?"
python3 scripts/gen_keys.py --check; python3 scripts/check_additions_build.py; echo "preflight_rc=$?"
python3 scripts/repin.py check "$(grep '^CHROMIUM_TAG=' upstream.env | cut -d= -f2)"; echo "stable_rc=$?"
```

Expected: `0` changed files after the second export (the gate), `sync_rc=0`, `preflight_rc=0`, `stable_rc=0`.

- [ ] **Step 10: Commit, PR, CI**

Update the pin in the documents that state it: `CLAUDE.md` (the pin paragraph and the retired-branch sentence), `README.md` if it names the version, and the "Where the project stands" section of the roadmap.

```bash
git add -A upstream.env patches additions settings baselines scripts CLAUDE.md README.md docs
git commit -m "repin: Chrome stable NEW_TAG"
git push -u origin repin/NEW_BUILD
```

Open the PR. Its body carries: the prediction and the actual conflict count, the timing table, the sweep summary before and after the baseline recapture, and the four gate outputs of step 9. After the merge, `build-verify` runs on `main` by itself; watch it:

```bash
gh run watch "$(gh run list --workflow build-verify.yml --branch main --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status; echo "exit=$?"
```

Expected: `exit=0`. This is the roadmap's "CI is green on it".

---

### Task 5: Recovery drill and runbook

Prove that the box branch can be rebuilt from the repo alone, and write down how to bring the whole build machine back.

**Files:**
- Create: `docs/superpowers/specs/repin-runbook.md`
- Modify: `docs/superpowers/measurements/2026-10-repin.md` (the "Recovery drill" section)

**Interfaces:**
- Consumes: `scripts/rebuild_branch.sh <src> <worktree> <branch>` (Task 1), the re-pinned repo (Task 4).

- [ ] **Step 1: Rebuild the branch beside the real one**

Put the merged repo on the box (the export round trip's first half), then on the box as `lang`:

```bash
time bash ~/camoucrome-cs/scripts/rebuild_branch.sh ~/chromium/src ~/camoudrill camoucrome/drill; echo "rc=$?"
cd ~/chromium/src
git diff --stat camoucrome/main camoucrome/drill | tail -1; echo "difflines=$(git diff camoucrome/main camoucrome/drill | wc -l)"
```

The script requires an absolute worktree dir (it refuses a relative one), and the worktree checkout of a Chromium tree takes minutes, so run it in a session that survives an ssh drop and read the log:

```bash
setsid nohup bash -c 'time bash ~/camoucrome-cs/scripts/rebuild_branch.sh "$HOME/chromium/src" "$HOME/camoudrill" camoucrome/drill; echo "rc=$?"' > ~/drill.log 2>&1 &
tail -f ~/drill.log
```

The `cd ~/chromium/src` lines above then run once the log shows `rc=0`.

Expected: `rc=0`, one line per patch printed, and `difflines=0`. The two branches differ in how many commits they have (the drill has one per patch; the real branch also has commits that touch only `components/camoucfg`), but their trees must be identical. A non-zero `difflines` means the repo cannot reproduce the branch that was built: stop, and find the content that exists only on the box.

- [ ] **Step 2: See the atomic failure on the real tree**

On the box as `lang`, break one patch in the copy of the repo and run again under another name:

```bash
cd ~/camoucrome-cs && cp patches/series /tmp/series.bak && echo "does-not-exist.patch" >> patches/series
bash scripts/rebuild_branch.sh ~/chromium/src ~/camoudrill2 camoucrome/drill2; echo "rc=$?"
git -C ~/chromium/src branch --list 'camoucrome/drill2' 'camoucrome/rebuild-*' | wc -l; ls -d ~/camoudrill2 2>&1 | tail -1
cp /tmp/series.bak patches/series
```

Expected: a non-zero `rc`, the message "rebuild failed at does-not-exist.patch", `0` matching branches, and "No such file or directory" for the worktree. This is Task 1's fix observed on the real tree.

- [ ] **Step 3: Clean up the drill**

```bash
cd ~/chromium/src && git worktree remove ~/camoudrill && git branch -D camoucrome/drill
git worktree list
```

Expected: only the main checkout listed.

- [ ] **Step 4: List what lives only on the box**

On the box as `lang`:

```bash
ls ~ | head -40
ls ~/camoucrome-verify ~/camoucrome-client ~/camoucrome-driver 2>/dev/null | head -40
diff <(ls ~/camoucrome-client/baselines) <(git -C ~/camoucrome-cs ls-files baselines 2>/dev/null | xargs -n1 basename) | head -20
```

Record every directory and file that is not in the repo, and for each one how it is regenerated (a command) or that it must be backed up. The baselines that are "build-host-local and regenerable" must each have their capture command named.

- [ ] **Step 5: Write the runbook**

Create `docs/superpowers/specs/repin-runbook.md` with these sections, filled from what Tasks 3 to 5 actually ran. Use the real commands and the measured durations, not estimates:

1. **When to re-pin.** The rule from the roadmap: never more than one milestone behind stable; patch-level re-pins only for security fixes. `python3 scripts/repin.py target` names the version.
2. **The re-pin checklist.** The ten steps of Task 4 as a numbered list of commands, each with its expected output and its measured duration.
3. **What a re-pin costs.** The timing table from the measurement doc, and the total.
4. **Recovering the branch.** `rebuild_branch.sh` usage and the `difflines=0` proof.
5. **Recovering the machine.** In order: WSL and Ubuntu 24.04; `depot_tools`; `fetch chromium` at the pin and `gclient sync`; `rebuild_branch.sh`; `gn gen` with `settings/build-args.gn`; the build; the Python venv and the driver directory (from the owner's layout notes and step 4's list); the runner (Task 3 step 6) and the hardening (Task 3 steps 2 and 3). For each: the command and the measured or recorded duration.
6. **What is not in the repo.** Step 4's list.

- [ ] **Step 6: Commit**

```bash
git checkout -b docs/repin-runbook origin/main
git add docs/superpowers/specs/repin-runbook.md docs/superpowers/measurements/2026-10-repin.md
git commit -m "docs: re-pin runbook and recovery drill"
```

Open the PR with the outputs of steps 1 and 2 in its body.

---

### Task 6: Close step 0

**Files:**
- Modify: `docs/superpowers/plans/2026-10-02-long-term-roadmap.md`

- [ ] **Step 1: Check the done-criterion, item by item**

The roadmap says step 0 is done when: the pin is the current stable milestone, CI is green on it, the re-pin time is recorded, and `rebuild_branch.sh` recreates the branch from a clean state. Run:

```bash
python3 scripts/repin.py check "$(grep '^CHROMIUM_TAG=' upstream.env | cut -d= -f2)"; echo "stable_rc=$?"
[ "$(grep '^CHROMIUM_TAG=' upstream.env | cut -d= -f2 | cut -d. -f1)" = "$(python3 scripts/repin.py target | cut -d. -f1)" ] && echo SAME_MILESTONE || echo BEHIND
gh run list --workflow build-verify.yml --branch main --limit 1 --json conclusion -q '.[0].conclusion'
grep -c 'duration' docs/superpowers/measurements/2026-10-repin.md
```

Expected: `stable_rc=0`, `SAME_MILESTONE`, `success`, and a non-zero count. The fourth criterion is Task 5 step 1's recorded `difflines=0`.

If the stable milestone moved while the re-pin ran, `BEHIND` is the honest result. Record it; the roadmap's commitment allows one milestone of lag.

- [ ] **Step 2: Update the roadmap**

In `docs/superpowers/plans/2026-10-02-long-term-roadmap.md`:

- In "Where the project stands", replace the pin lines with the new pin and the date.
- In "Standing commitment: re-pin", add one sentence stating the measured total cost of a re-pin and whether "never more than one milestone behind" is achievable at that cost. If it is not, say so and move "Build time" to the top of the backlog, as the roadmap already requires.
- Mark step 0 as done with the date.

- [ ] **Step 3: Commit**

```bash
git checkout -b docs/step0-done origin/main
git add docs/superpowers/plans/2026-10-02-long-term-roadmap.md
git commit -m "docs: roadmap step 0 done, re-pin cost recorded"
```

Open the PR with step 1's four outputs in its body.

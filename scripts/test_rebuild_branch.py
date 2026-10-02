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

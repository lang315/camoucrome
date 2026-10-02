"""rebuild_branch.sh on a throwaway repo: success, atomic failure, custom branch."""
import pathlib
import shutil
import subprocess

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

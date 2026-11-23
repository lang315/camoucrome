"""The box's pre-rebase hook on a temp repo: a deep rebase is refused, a shallow one and the override pass."""
import os
import pathlib
import subprocess

import pytest

HOOKS = pathlib.Path(__file__).resolve().parent / "box-hooks"


def git(cwd, *a, env=None, check=True):
    e = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
         "GIT_COMMITTER_EMAIL": "t@t", **(env or {})}
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=check, env=e)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "camoucrome/main")
    git(tmp_path, "config", "core.hooksPath", str(HOOKS))
    for i in range(6):
        (tmp_path / "f").write_text(str(i))
        git(tmp_path, "add", "f")
        git(tmp_path, "commit", "-q", "-m", f"c{i}")
    return tmp_path


def rebase(repo, onto, env=None):
    # -i: a plain rebase onto an ancestor is "up to date" and never reaches the hook; the interactive and autosquash cases do
    return git(repo, "rebase", "-i", onto, env={"GIT_SEQUENCE_EDITOR": "true", **(env or {})}, check=False)


def test_deep_rebase_is_refused(repo):
    r = rebase(repo, "HEAD~5")
    assert r.returncode != 0 and "refused" in r.stderr and "tip" in r.stderr


def test_shallow_rebase_passes(repo):
    assert rebase(repo, "HEAD~2").returncode == 0


def test_override_passes(repo):
    assert rebase(repo, "HEAD~5", env={"CAMOU_ALLOW_DEEP_REBASE": "1"}).returncode == 0


def test_other_branches_are_not_judged(repo):
    git(repo, "checkout", "-q", "-b", "topic")
    assert rebase(repo, "HEAD~5").returncode == 0

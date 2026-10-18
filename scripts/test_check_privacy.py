"""check_privacy: every category caught, clean text passes, and no matched value is ever printed."""
import json
import os
import pathlib
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_privacy as cp  # noqa: E402

TERMS = {"<host-place>": ["Plantville"], "<host-offset>": ["GMT+0999"]}


@pytest.mark.parametrize("line,cat", [
    ("built on DESKTOP-AB12CD3 today", "machine-name"),
    (r"C:\Users\someone.BOX\AppData\Local", "windows-profile"),
    ("file:///C:/Users/someone/AppData/x.html", "windows-profile"),
    ("cd /home/someone/chromium/src", "home-path"),
    ("open /Users/someone/Go/x", "home-path"),
    ("HOME=/home/someone", "home-path"),
    ("cd /Users/someone", "home-path"),
    ("see `/home/someone` there", "home-path"),
    (r"\\wsl.localhost\Ubuntu-24.04\home\someone\x", "home-path"),
    (r"D:\Users\someone\x", "windows-profile"),
    ("memory at ~/.claude/projects/-Users-someone-Go-x/memory", "home-slug"),
    ("box at mybox.tail1234.ts.net", "tailnet"),
    ("Claude-Session: https://claude.ai/code/session-x", "session-link"),
    ("ran 16:03-16:37 XST on the host", "local-clock"),
    ("peer 100.101.102.103 up", "ip"),
    ("wsl at 172.20.1.9", "ip"),
    ("near Plantville", "<host-place>"),
    ("near plantville", "<host-place>"),
    ("date0 GMT+0999 (x)", "<host-offset>"),
])
def test_each_category_is_caught(line, cat):
    assert (1, cat) in cp.hits(line, TERMS)


@pytest.mark.parametrize("line", [
    "Chrome/154.0.0.0 and 154.0.8037.93 and 156.0.8078.36",
    "doc address 203.0.113.7, 127.0.0.1 and 0.0.0.0:54021",
    "fake webrtc ip 192.168.1.37",
    "~/chromium/src, $HOME/x, /home/runner/work and /home/<user>/x",
    r"C:\Users\user.HOST\AppData and C:\Users\<user>",
    "file:///C:/Users/user.HOST/AppData/x.html",
    "chrome/browser/ui/webui/home/foo.cc and /Users/user.HOST/x",
    "docs/superpowers/specs/2026-09-10-sp7-phone-home-quiet-design.md",
    "at 22:28 UTC; Thu Jan 01 1970 00:00:00 GMT+0000",
    "Wed Dec 31 1969 18:00:00 GMT-0600 (Central Standard Time)",
])
def test_clean_lines_pass(line):
    assert cp.hits(line, TERMS) == []


def git(repo, *a, tz="UTC", check=True):
    env = dict(os.environ, TZ=tz, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    return subprocess.run(["git", "-C", str(repo), *a], env=env, capture_output=True, text=True, check=check)


def commit(repo, path, data, msg="m", tz="UTC"):
    p = repo / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data if isinstance(data, bytes) else data.encode())
    git(repo, "add", path)
    return git(repo, "commit", "-q", "-m", msg, tz=tz)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps(TERMS))
    return tmp_path


def test_tracked_clean_passes(repo):
    commit(repo, "a.md", "nothing here\n")
    assert cp.main([]) == 0


def test_output_never_contains_the_matched_text(repo, capsys):
    commit(repo, "a.md", "line one\nnear Plantville on DESKTOP-AB12CD3\n")
    assert cp.main([]) == 1
    out = capsys.readouterr()
    assert "a.md:2: <host-place>" in out.out and "a.md:2: machine-name" in out.out
    assert "Plantville" not in out.out + out.err and "AB12CD3" not in out.out + out.err


def test_allowlisted_product_file_passes(repo):
    commit(repo, "settings/locale_zones.json", '{"x": "Plantville"}\n')
    assert cp.main([]) == 0


def test_binary_file_is_skipped(repo):
    commit(repo, "b.bin", b"\0\0DESKTOP-AB12CD3")
    assert cp.main([]) == 0


def test_staged_checks_the_index(repo):
    commit(repo, "a.md", "clean\n")
    (repo / "a.md").write_text("near Plantville\n")
    git(repo, "add", "a.md")
    assert cp.main(["--staged"]) == 1


def test_file_mode(repo, tmp_path):
    body = tmp_path / "body.md"
    body.write_text("see https://claude.ai/code/session-abc\n")
    assert cp.main(["--file", str(body)]) == 1


def test_range_refuses_a_non_utc_commit(repo, capsys):
    commit(repo, "a.md", "clean\n", tz="Etc/GMT-5")
    assert cp.main(["--range", "HEAD"]) == 1
    assert "date offset" in capsys.readouterr().out


def test_range_checks_messages(repo):
    commit(repo, "a.md", "clean\n", msg="x\n\nClaude-Session: https://claude.ai/code/session-x")
    assert cp.main(["--range", "HEAD"]) == 1


def test_range_passes_a_clean_utc_commit(repo):
    commit(repo, "a.md", "clean\n")
    assert cp.main(["--range", "HEAD"]) == 0


def test_range_refuses_a_github_made_commit_with_an_offset(repo):
    # GitHub's web merges carry the owner's offset (all 40 before 2026-10-18): merges are made locally in UTC
    commit(repo, "a.md", "clean\n")
    env = dict(os.environ, TZ="Etc/GMT-5", GIT_AUTHOR_NAME="GitHub", GIT_AUTHOR_EMAIL="noreply@github.com",
               GIT_COMMITTER_NAME="GitHub", GIT_COMMITTER_EMAIL="noreply@github.com")
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "Merge pull request #1"], env=env, check=True)
    assert cp.main(["--range", "HEAD"]) == 1


def test_gate_files_are_checked_for_private_terms_only(repo):
    commit(repo, "scripts/test_check_privacy.py", "example DESKTOP-AB12CD3 and /home/someone/x\n")
    assert cp.main([]) == 0
    assert cp.main(["--history"]) == 0
    commit(repo, "scripts/test_check_privacy.py", "near Plantville\n")
    assert cp.main([]) == 1


def test_a_leaking_path_is_caught_and_not_printed(repo, capsys):
    commit(repo, "notes/near-Plantville.md", "clean\n")
    assert cp.main([]) == 1
    assert cp.main(["--history"]) == 1
    out = capsys.readouterr()
    assert "<host-place>" in out.out and "Plantville" not in out.out + out.err


def test_require_terms_refuses_an_empty_term_set(repo, monkeypatch):
    commit(repo, "a.md", "clean\n")
    monkeypatch.setenv("PRIVATE_TERMS", "")
    assert cp.main(["--require-terms"]) == 2
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps(TERMS))
    assert cp.main(["--require-terms"]) == 0


def test_ci_falls_back_when_before_is_gone(repo, monkeypatch):
    commit(repo, "a.md", "clean\n")
    monkeypatch.setenv("PR_BASE", "")
    monkeypatch.setenv("PR_HEAD", "")
    monkeypatch.setenv("BEFORE", "1234567890abcdef1234567890abcdef12345678")  # a force-pushed-away tip
    assert cp.main(["--ci"]) == 0
    commit(repo, "b.md", "clean\n", tz="Etc/GMT-5")
    assert cp.main(["--ci"]) == 1


def test_history_finds_a_term_removed_at_the_tip(repo):
    commit(repo, "a.md", "near Plantville\n")
    commit(repo, "a.md", "clean\n")
    assert cp.main([]) == 0
    assert cp.main(["--history"]) == 1


def test_empty_private_terms_still_runs_generic(repo, monkeypatch):
    monkeypatch.setenv("PRIVATE_TERMS", "")
    commit(repo, "a.md", "near Plantville\n")
    assert cp.main([]) == 0
    commit(repo, "b.md", "on DESKTOP-AB12CD3\n")
    assert cp.main([]) == 1


def test_bad_terms_shape_exits(monkeypatch):
    monkeypatch.setenv("PRIVATE_TERMS", '["x"]')
    with pytest.raises(SystemExit):
        cp.load_terms()


HOOKS = HERE / "hooks"


def hooked(repo):
    git(repo, "config", "core.hooksPath", str(HOOKS))
    return repo


def try_commit(repo, path, text, msg="m", tz="UTC"):
    (repo / path).write_text(text)
    git(repo, "add", path)
    return git(repo, "commit", "-q", "-m", msg, tz=tz, check=False)


def test_pre_commit_hook_refuses_a_non_utc_date(repo):
    assert try_commit(hooked(repo), "a.md", "clean\n", tz="Etc/GMT-5").returncode != 0


def test_pre_commit_hook_refuses_a_planted_file(repo):
    assert try_commit(hooked(repo), "a.md", "near Plantville\n").returncode != 0


def test_commit_msg_hook_refuses_a_session_link(repo):
    r = try_commit(hooked(repo), "a.md", "clean\n", msg="x\n\nClaude-Session: https://claude.ai/code/session-x")
    assert r.returncode != 0


def test_hooks_pass_a_clean_utc_commit(repo):
    assert try_commit(hooked(repo), "a.md", "clean\n").returncode == 0

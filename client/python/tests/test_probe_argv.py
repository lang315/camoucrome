"""probe.browser_candidates: the probe reads the browser's argv from /proc; a second main browser process of the same
executable (a stray left by an earlier run) must be counted, not silently preferred (2026-10-29: all three patchright
rows of verify_sp6b_driver compared a stray's stock-style argv)."""
import pathlib

from camoucrome import probe

EXE = "/opt/x/chrome"


def fake_proc(root, procs):
    for pid, argv in procs.items():
        d = root / str(pid)
        d.mkdir()
        (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
    (root / "self").mkdir()  # a non-numeric entry, as in the real /proc
    return root


def test_one_browser_one_candidate_children_and_other_programs_ignored(tmp_path):
    root = fake_proc(tmp_path, {
        10: [EXE, "--headless=new", "--remote-debugging-pipe"],
        11: [EXE, "--type=renderer", "--lang=en-US"],
        12: ["/usr/bin/python3", "-m", "camoucrome.probe"],
    })
    assert probe.browser_candidates(EXE, str(root)) == [[EXE, "--headless=new", "--remote-debugging-pipe"]]


def test_a_stray_main_process_is_a_second_candidate(tmp_path):
    root = fake_proc(tmp_path, {
        10: [EXE, "--headless", "--remote-debugging-port=0", "about:blank"],   # the stray
        20: [EXE, "--headless=new", "--remote-debugging-pipe"],               # the browser under test
    })
    cands = probe.browser_candidates(EXE, str(root))
    assert len(cands) == 2


def test_chromiums_space_joined_title_is_split(tmp_path):
    d = tmp_path / "7"
    d.mkdir()
    (d / "cmdline").write_bytes(f"{EXE} --headless=new --no-sandbox".encode() + b"\0")
    assert probe.browser_candidates(EXE, str(tmp_path)) == [[EXE, "--headless=new", "--no-sandbox"]]


def test_no_proc_dir_is_no_candidate(tmp_path):
    assert probe.browser_candidates(EXE, str(tmp_path / "missing")) == []


def test_browser_argv_keeps_returning_the_first_candidate(tmp_path):
    root = fake_proc(tmp_path, {10: [EXE, "--a"], 20: [EXE, "--b"]})
    assert probe.browser_argv(EXE, str(root)) == [EXE, "--a"]

"""ci_checks: what build-verify asserts about the build and the unit-test filter, and the workflows' own hardening."""
import pathlib
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ci_checks as cc  # noqa: E402

WORKFLOWS = HERE.parent / ".github" / "workflows"


def test_steps_reads_the_siso_summary_line():
    assert cc.build_steps("[1/4] x\n15.96s Build Succeeded: 4 steps - 0.25/s\n") == 4
    assert cc.build_steps("Build Succeeded: 0 steps\n") == 0


@pytest.mark.parametrize("text", ["", "ninja: no work to do.\n", "Build Succeeded\n", "Build Failed: 3 steps\n"])
def test_steps_refuses_output_without_a_succeeded_count(text):
    assert cc.build_steps(text) is None


def test_listed_counts_the_tests_a_filter_matches():
    out = "CamoucfgKeysTest.\n  Declared\n  Unique\nOther.\n  A\n"
    assert cc.listed_tests(out) == 3
    assert cc.listed_tests("") == 0  # a filter that matches nothing prints nothing, and a run of it prints SUCCESS


def test_main_exits_nonzero_for_an_unparsable_build_or_an_empty_listing(tmp_path, capsys):
    good, bad, empty = tmp_path / "g", tmp_path / "b", tmp_path / "e"
    good.write_text("Build Succeeded: 4 steps\n")
    bad.write_text("whatever\n")
    empty.write_text("")
    assert cc.main(["steps", str(good)]) == 0 and "4 steps" in capsys.readouterr().out
    assert cc.main(["steps", str(bad)]) == 1
    assert cc.main(["listed", str(good)]) == 1 and cc.main(["listed", str(empty)]) == 1
    (tmp_path / "t").write_text("S.\n  a\n")
    assert cc.main(["listed", str(tmp_path / "t")]) == 0


def text(name):
    return (WORKFLOWS / name).read_text()


@pytest.mark.parametrize("name", ["checks.yml", "build-verify.yml"])
def test_every_workflow_asks_for_read_only_contents(name):
    assert "\npermissions:\n  contents: read\n" in text(name)


def test_checks_has_a_timeout_and_cancels_superseded_runs():
    t = text("checks.yml")
    assert "timeout-minutes:" in t
    assert "concurrency:" in t and "cancel-in-progress: true" in t


def test_build_verify_fails_instead_of_skipping_the_observer_verify():
    t = text("build-verify.yml")
    assert "SKIP verify_observe" not in t
    assert "camou_observe = true" in t


def test_build_verify_uses_the_build_and_filter_checks():
    t = text("build-verify.yml")
    import re
    assert re.search(r'ci_checks\.py"? steps', t) and re.search(r'ci_checks\.py"? listed', t)


def test_build_verify_syncs_scripts_and_settings_with_delete():
    # a file removed from the repo (settings/presets/chromium-154.json on 2026-10-29) must not linger in the client tree the verifies read
    t = text("build-verify.yml")
    assert "rsync -a --delete --exclude __pycache__ scripts/ " in t
    assert "rsync -a --delete settings/ " in t


def test_run_prints_the_tail_of_a_failing_log():
    # the row detail lines ("n=.. span=..") do not match FAIL|DIFF|Error, so without the tail a CI failure hides its numbers
    assert 'tail -15 "/tmp/$1.log"' in text("build-verify.yml")


def _run_fn():
    import re
    m = re.search(r"^ +(run\(\) \{.*\})$", text("build-verify.yml"), re.M)
    assert m, "run() not found in build-verify.yml"
    return m.group(1)


def _call_run(tmp_path, rc, ok):
    import os
    import subprocess
    py = tmp_path / "venv" / "bin" / "python3"
    py.parent.mkdir(parents=True)
    py.write_text(f"#!/bin/sh\necho 'UNMEASURED  no X'\nexit {rc}\n")
    py.chmod(0o755)
    env = dict(os.environ, VERIFY=str(tmp_path), OK3="1" if ok else "0")
    return subprocess.run(["bash", "-c", _run_fn() + '\nrun verify_r6test.py'], env=env, capture_output=True, text=True)


def test_run_fails_an_exit_3_the_line_did_not_declare(tmp_path):
    r = _call_run(tmp_path, 3, False)
    assert r.returncode != 0 and "FAILED verify_r6test.py" in r.stdout


def test_run_lets_a_declared_exit_3_through_loudly(tmp_path):
    r = _call_run(tmp_path, 3, True)
    assert r.returncode == 0 and "UNMEASURED verify_r6test.py" in r.stdout


def test_run_still_fails_exit_1_even_when_unmeasured_ok(tmp_path):
    assert _call_run(tmp_path, 1, True).returncode != 0


def test_the_loop_passes_unmeasured_ok_to_run():
    assert 'OK3=$ok run "$script"' in text("build-verify.yml")


def test_a_busy_box_is_waited_for_a_dirty_checkout_is_not():
    t = text("build-verify.yml")
    step = t[t.index("checkout is clean and no build is running"):t.index("pushed change set == built checkout")]
    assert "sleep 60" in step and "minute" in step
    assert step.index("checkout dirty") < step.index("sleep 60")

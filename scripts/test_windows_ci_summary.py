"""windows_ci_summary's verdict, run id and summary (spec 2026-10-28 §2.5, harness rows L1-L8)."""
import copy
import datetime
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import windows_ci_summary as w  # noqa: E402

UTC = datetime.timezone.utc


def rec(**over):
    r = {
        "commit": "aaaaaaa1111111",
        "tested_commit": "bbbbbbb2222222",
        "lock": "taken",
        "observe_in_use": "",
        "forced": "",
        "preconditions": {"session_active": True, "commit_headroom_gb": 20, "native_build_running": False},
        "headroom_lost": False,
        "session_lost": False,
        "build": {"steps": 1234, "seconds": 600, "exit": 0, "timed_out": False},
        "verify": {
            "red": [{"script": "verify_a.py", "rows": 3, "red_seen": True}],
            "green": [{"script": "verify_b.py", "rows": 21, "expected": 21, "fails": 0,
                       "not_measured": 0, "gpu_crashes": 0}],
        },
        "stock_version": "156.0.8078.48",
        "started_utc": "2026-10-28T01:00:00Z",
        "ended_utc": "2026-10-28T02:00:00Z",
    }
    r.update(over)
    return r


def mut(path, value):
    """A passing record with one nested field changed (path as dotted keys)."""
    r = rec()
    o = r
    keys = path.split(".")
    for k in keys[:-1]:
        o = o[int(k)] if isinstance(o, list) else o[k]
    if isinstance(o, list):
        o[int(keys[-1])] = value
    else:
        o[keys[-1]] = value
    return r


def test_pass_record_is_pass_exit_0():
    assert w.verdict(rec()) == ("PASS", 0)


def test_l1_lock_held_is_skipped_exit_0():
    assert w.verdict(rec(lock="held:other since 2026-10-28T00:00:00Z")) == ("SKIPPED", 0)


def test_l3_zero_steps_is_fail():
    assert w.verdict(mut("build.steps", 0)) == ("FAIL", 1)


def test_l4_unchanged_commit_is_skipped():
    assert w.verdict(rec(tested_commit="aaaaaaa1111111")) == ("SKIPPED", 0)


def test_l4_unchanged_but_forced_proceeds():
    assert w.verdict(rec(tested_commit="aaaaaaa1111111", forced="retest")) == ("PASS", 0)


@pytest.mark.parametrize("path,value", [
    ("preconditions.session_active", False),
    ("preconditions.commit_headroom_gb", 7.9),
    ("preconditions.native_build_running", True),
])
def test_l5_preconditions_are_skipped_with_reason(path, value):
    assert w.verdict(mut(path, value)) == ("SKIPPED", 0)


def test_skip_reasons_are_named():
    assert "session" in w.reason(mut("preconditions.session_active", False))
    assert "headroom" in w.reason(mut("preconditions.commit_headroom_gb", 7))
    assert "native build" in w.reason(mut("preconditions.native_build_running", True))
    assert w.reason(rec(lock="held:x since y")).startswith("lock held")
    assert w.reason(rec(tested_commit="aaaaaaa1111111")) == "nothing changed"


def test_observe_in_use_is_skipped_unless_forced():
    r = rec(observe_in_use="observe-auto process")
    assert w.verdict(r) == ("SKIPPED", 0)
    assert w.reason(r) == "observe in use: observe-auto process"
    assert w.render_summary(r).splitlines()[0].startswith("RESULT SKIPPED ")


def test_forced_proceeds_and_is_printed_with_or_without_observe():
    for obs in ("observe-auto process", ""):
        r = rec(observe_in_use=obs, forced="owner asked")
        assert w.verdict(r) == ("PASS", 0)
        assert "FORCED: owner asked" in w.render_summary(r).splitlines()


def test_forced_never_overrides_the_lock():
    assert w.verdict(rec(lock="held:x since y", forced="owner asked")) == ("SKIPPED", 0)


def test_headroom_lost_mid_run_is_unmeasured():
    assert w.verdict(rec(headroom_lost=True)) == ("UNMEASURED", 2)
    assert w.verdict(rec(session_lost=True)) == ("UNMEASURED", 2)


def test_l6_gpu_crash_is_unmeasured():
    assert w.verdict(mut("verify.green.0.gpu_crashes", 1)) == ("UNMEASURED", 2)


def test_not_measured_beyond_allowed_is_unmeasured():
    assert w.verdict(mut("verify.green.0.not_measured", 1)) == ("UNMEASURED", 2)
    r = rec()
    r["verify"]["green"][0].update(not_measured=2, allowed_not_measured=2)
    assert w.verdict(r) == ("PASS", 0)


def test_l7_red_not_seen_is_fail_with_reason():
    r = mut("verify.red.0.red_seen", False)
    assert w.verdict(r) == ("FAIL", 1)
    assert "red did not go red" in w.render_summary(r)


def test_green_row_failure_is_fail():
    assert w.verdict(mut("verify.green.0.fails", 1)) == ("FAIL", 1)


def test_green_fewer_rows_than_expected_is_fail():
    assert w.verdict(mut("verify.green.0.rows", 20)) == ("FAIL", 1)


def test_known_failure_that_passed_is_fail():
    r = rec()
    r["verify"]["green"][0]["known_fail_passed"] = 1
    assert w.verdict(r) == ("FAIL", 1)


@pytest.mark.parametrize("path,value", [("build.exit", 1), ("build.timed_out", True)])
def test_build_failure_or_timeout_is_fail(path, value):
    assert w.verdict(mut(path, value)) == ("FAIL", 1)


def test_precedence_skipped_over_fail_over_unmeasured():
    bad = rec()
    bad["build"]["steps"] = 0
    bad["verify"]["green"][0]["gpu_crashes"] = 1
    assert w.verdict(bad) == ("FAIL", 1)
    bad["lock"] = "held:x since y"
    assert w.verdict(bad) == ("SKIPPED", 0)


def test_run_id_utc_and_rejects_others():
    assert w.run_id(datetime.datetime(2026, 10, 28, 1, 2, 3, tzinfo=UTC)) == "20261028T010203Z"
    with pytest.raises(ValueError):
        w.run_id(datetime.datetime(2026, 10, 28, 1, 2, 3))
    with pytest.raises(ValueError):
        w.run_id(datetime.datetime(2026, 10, 28, 8, 2, 3, tzinfo=datetime.timezone(datetime.timedelta(hours=7))))


def test_l8_summary_first_line_and_contents():
    r = rec()
    s = w.render_summary(r)
    lines = s.splitlines()
    assert lines[0] == "RESULT PASS 20261028T010000Z"
    assert "aaaaaaa" in s and "2026-10-28T01:00:00Z" in s and "2026-10-28T02:00:00Z" in s
    assert "1234" in s and "verify_b.py" in s and "21/21" in s
    assert "156.0.8078.48" in s


def test_run_id_comes_from_started_utc():
    r = rec(started_utc="2026-10-28T23:59:59Z")
    assert w.render_summary(r).splitlines()[0] == "RESULT PASS 20261028T235959Z"


def test_stock_version_bump_is_printed_not_judged():
    r = rec(stock_version="157.0.8103.5", previous_stock_version="156.0.8078.48")
    assert w.verdict(r) == ("PASS", 0)
    assert "156.0.8078.48 -> 157.0.8103.5" in w.render_summary(r)


def test_cli_prints_result_and_exits_with_verdict(tmp_path):
    for r, code, name in [(rec(), 0, "PASS"), (mut("build.steps", 0), 1, "FAIL"),
                          (mut("verify.green.0.gpu_crashes", 1), 2, "UNMEASURED")]:
        rj, out = tmp_path / "r.json", tmp_path / "s.md"
        rj.write_text(json.dumps(copy.deepcopy(r)))
        p = subprocess.run([sys.executable, os.path.join(HERE, "windows_ci_summary.py"),
                            "--record", str(rj), "--out", str(out)], capture_output=True, text=True)
        assert p.returncode == code
        assert p.stdout.strip() == f"RESULT {name} 20261028T010000Z"
        assert out.read_text().splitlines()[0] == p.stdout.strip()


def test_missing_build_exit_is_unmeasured_not_fail():
    # PS 5.1 gives $null for a -PassThru process's ExitCode unless the handle was read; a good build
    # must not become a FAIL (and a stamped commit) because the driver could not read the code.
    assert w.verdict(mut("build.exit", None))[0] == "UNMEASURED"


def test_missing_build_exit_with_zero_steps_is_still_fail():
    r = mut("build.exit", None)
    r["build"]["steps"] = 0
    assert w.verdict(r)[0] == "FAIL"

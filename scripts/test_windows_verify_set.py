"""The runner's pure parts, checkable anywhere. The browser runs happen on the
Windows host; these pin how their output is judged.

Run: python3 -m pytest -q scripts/test_windows_verify_set.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import windows_verify_set as w  # noqa: E402


def test_count_rows_reads_every_row_shape_the_set_prints():
    out = "\n".join([
        "PASS  K1 chunked",            # verify_sp1b / sp4a / generator style
        "FAIL  K2 sandboxed",
        "W1: PASS",                    # verify_windows_sandbox_env style
        "J3: FAIL",                    # verify_metric_jitter style
        "PASS  O1 generated Windows identity: no difference",  # host oracle
        "note: W1: sandboxed + config, main -> 3 (expect 3)",  # not a row
        "      ok   C5 stack timing: +7%",                      # driver detail, not a row
        "2 PASS 1 FAIL",                                        # a summary, not a row
    ])
    assert w.count_rows(out) == (3, 2)


@pytest.mark.parametrize("rc,out,ok", [
    (0, "PASS  a\nPASS  b\n2 PASS 0 FAIL", True),
    (0, "PASS  a\n1 PASS 0 FAIL", False),        # a row dropped out: count is asserted
    (1, "PASS  a\nFAIL  b", False),
    (0, "PASS  a\nFAIL  b", False),              # exit 0 with a FAIL row is not green
])
def test_green_needs_exit_0_and_the_asserted_count(rc, out, ok):
    e = w.Entry("verify_x.py", 2, "stock")
    assert w.judge("green", e, rc, out)[0] is ok


def test_green_all_pass_entry_needs_the_line():
    e = w.Entry("verify_sp6b_driver.py", "ALL_PASS", "stock")
    assert w.judge("green", e, 0, "PASS  py\nALL_PASS")[0] is True
    assert w.judge("green", e, 0, "PASS  py\nFAIL")[0] is False


def test_red_stock_entry_must_fail_and_say_so():
    e = w.Entry("verify_x.py", 2, "stock")
    assert w.judge("red", e, 1, "FAIL  a\nPASS  b")[0] is True
    assert w.judge("red", e, 0, "PASS  a\nPASS  b")[0] is False   # stock passed: measures nothing
    assert w.judge("red", e, 1, "Traceback ...")[0] is False      # a crash is not a RED


def test_red_own_entry_is_skipped_with_its_reason():
    e = w.Entry("verify_x.py", 2, "own")
    ok, why = w.judge("red", e, 0, "")
    assert ok is True and "own" in why


def test_stock_version_is_the_one_version_directory(tmp_path):
    (tmp_path / "154.0.8037.93").mkdir()
    (tmp_path / "SetupMetrics").mkdir()
    assert w.stock_version(tmp_path) == "154.0.8037.93"
    (tmp_path / "155.0.8100.1").mkdir()      # an update half-applied: refuse
    with pytest.raises(SystemExit):
        w.stock_version(tmp_path)


def test_every_entry_names_a_script_that_exists():
    here = os.path.dirname(os.path.abspath(__file__))
    missing = [e.script for e in w.SET if not os.path.exists(os.path.join(here, e.script))]
    assert missing == []

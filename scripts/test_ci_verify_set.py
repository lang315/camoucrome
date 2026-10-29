"""scripts/ci_verify_set.txt is the list build-verify.yml runs: every verify is on it once, with a reason if it is skipped."""
import pathlib
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ci_verify_set as cv  # noqa: E402


def test_the_shipped_set_covers_every_verify_once():
    assert cv.check(cv.load(), HERE) == []


def test_a_verify_missing_from_the_set_is_reported(tmp_path):
    (tmp_path / "verify_a.py").write_text("")
    (tmp_path / "verify_b.py").write_text("")
    entries = cv.parse("run verify_a.py\n")
    assert cv.check(entries, tmp_path) == ["verify_b.py is not in ci_verify_set.txt (run, external or skip with a reason)"]


def test_a_listed_script_that_does_not_exist_and_a_duplicate_are_reported(tmp_path):
    (tmp_path / "verify_a.py").write_text("")
    entries = cv.parse("run verify_a.py\nrun verify_a.py\nrun verify_gone.py\n")
    problems = cv.check(entries, tmp_path)
    assert "verify_a.py is listed twice" in problems and "verify_gone.py is listed but does not exist" in problems


@pytest.mark.parametrize("text", ["skip verify_a.py\n", "skip verify_a.py  #\n", "run verify_a.py nope\n", "walk verify_a.py\n",
                                  "run notaverify.py\n"])
def test_a_malformed_line_is_refused(text):
    with pytest.raises(ValueError):
        cv.parse(text)


def test_list_prints_the_script_then_its_env_for_run_lines_only():
    entries = cv.parse("# c\nrun verify_a.py\nrun verify_b.py CAMOU_GEN_N=4 X=1\nexternal verify_c.py # own step\nskip verify_d.py # no\n")
    assert cv.listing(entries) == ["verify_a.py", "verify_b.py CAMOU_GEN_N=4 X=1"]

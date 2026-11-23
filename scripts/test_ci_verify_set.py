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
    entries = cv.parse("# c\nrun verify_a.py\nrun verify_b.py CAMOU_GEN_N=4 X=1\nexternal verify_c.py # own step\nskip verify_d.py # where=box: no\n")
    assert cv.listing(entries) == ["verify_a.py", "verify_b.py CAMOU_GEN_N=4 X=1"]


def local_imports(path):
    import ast
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.split(".")[0])
    return {n for n in names if (HERE / f"{n}.py").exists()}


def test_every_scripts_module_a_run_script_imports_is_copied_to_the_runner():
    # the workflow runs the verifies from $VERIFY, into which it copies only the files on its `cp scripts/...` line:
    # verify_sp2e and verify_sp2b failed there with ModuleNotFoundError on their *_analysis modules (2026-10-29)
    import fnmatch
    workflow = (HERE.parent / ".github" / "workflows" / "build-verify.yml").read_text()
    line = next(l for l in workflow.splitlines() if "cp scripts/verify_" in l)
    patterns = [t for t in line.split() if t.startswith("scripts/")]
    # a verify that puts the repo's scripts/ copy ($CLIENT/scripts, rsynced by the workflow) on sys.path finds the rest there
    tops = [e.script[:-3] for e in cv.load() if e.kind in ("run", "external")]
    todo = [n for n in tops if 'CLIENT / "scripts"' not in (HERE / f"{n}.py").read_text()]
    seen = set()
    while todo:
        name = todo.pop()
        if name not in seen:
            seen.add(name)
            todo += sorted(local_imports(HERE / f"{name}.py"))
    missing = sorted(n for n in seen if not any(fnmatch.fnmatch(f"scripts/{n}.py", p) for p in patterns))
    assert missing == [], f"imported by a verify that CI runs, but not copied to $VERIFY: {missing}"


def test_unmeasured_ok_is_kept_by_the_parser_and_the_listing():
    e = cv.parse("run verify_a.py unmeasured-ok X=1\nrun verify_b.py\n")
    assert [x.unmeasured_ok for x in e] == [True, False] and e[0].env == ["X=1"]
    assert cv.listing(e) == ["verify_a.py unmeasured-ok X=1", "verify_b.py"]


def test_only_the_launcher_is_declared_unmeasured_ok():
    # the one verify that ended UNMEASURED in the last green run (45096877347): no X server for a headed launch
    assert [e.script for e in cv.load() if e.unmeasured_ok] == ["verify_sp6b_launcher.py"]


def test_unmeasured_ok_is_for_run_lines_only():
    with pytest.raises(ValueError):
        cv.parse("external verify_a.py unmeasured-ok # r\n")


@pytest.mark.parametrize("text", ["skip verify_a.py  # not yet evaluated\n", "skip verify_a.py  # where=cloud: x\n", "skip verify_a.py  # where=box:\n"])
def test_a_skip_without_a_valid_where_is_refused(text):
    with pytest.raises(ValueError):
        cv.parse(text)


def test_every_shipped_skip_says_where_it_runs():
    skips = [e for e in cv.load() if e.kind == "skip"]
    assert skips and all(e.where in cv.WHERES for e in skips)


def test_every_measure_script_is_in_measure_set_with_a_where(tmp_path):
    assert cv.check_measure(cv.load_measure(), HERE) == []
    assert len(cv.load_measure()) == len(list(HERE.glob("measure_*.py")))
    (tmp_path / "measure_a.py").write_text("")
    assert cv.check_measure(cv.parse_measure("measure measure_x.py  # where=box: y\n"), tmp_path) == [
        "measure_x.py is listed but does not exist",
        "measure_a.py is not in measure_set.txt (measure <script>  # where=<box|host|manual|retired>: why)"]


def test_a_measure_line_with_a_where_outside_the_set_is_refused():
    with pytest.raises(ValueError):
        cv.parse_measure("measure measure_a.py  # where=cloud: x\n")

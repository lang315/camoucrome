"""lib_shell: UNMEASURED ends rc 3, but never over a FAIL (rc 1)."""
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent


def run(body):
    code = f"import sys; sys.path.insert(0, {str(HERE)!r}); import lib_shell\nlib_shell._mark_unmeasured('UNMEASURED  x')\n{body}"
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)


def test_unmeasured_alone_exits_3():
    assert run("print('PASS  a')\nsys.exit(0)").returncode == 3


def test_a_fail_row_then_unmeasured_exits_1():
    r = run("print('FAIL  a')\nsys.exit(1)")
    assert r.returncode == 1 and "exit 1" in r.stdout


def test_an_uncaught_exception_then_unmeasured_exits_1():
    assert run("raise RuntimeError('boom')").returncode == 1


def test_fall_off_the_end_after_unmeasured_exits_3():
    assert run("pass").returncode == 3


def test_a_deliberate_sys_exit_3_after_unmeasured_stays_3():
    assert run("sys.exit(3)").returncode == 3


def test_sys_exit_1_after_unmeasured_ends_1():
    assert run("sys.exit(1)").returncode == 1

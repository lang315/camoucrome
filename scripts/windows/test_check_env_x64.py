import pathlib
import subprocess
import sys

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parent / "check_env_x64.py"


def env(path, extra=""):
    return f"SystemRoot=C:\\Windows\0PATH={path}\0INCLUDE={extra}\0\0".encode()


@pytest.fixture
def out(tmp_path):
    o = tmp_path / "out" / "Official"
    o.mkdir(parents=True)
    (o / "environment.x64").write_bytes(env("C:\\py;C:\\depot_tools;C:\\Windows"))
    return o


def run(out, *a):
    return subprocess.run([sys.executable, str(SCRIPT), str(out), *a], capture_output=True, text=True)


def test_unchanged_passes(out):
    assert run(out, "--record").returncode == 0
    assert run(out).returncode == 0


def test_changed_path_is_refused_by_name_and_count_without_values(out):
    run(out, "--record")
    (out / "environment.x64").write_bytes(env("C:\\py;C:\\depot_tools;C:\\Windows;D:\\secret-host-dir\\"))
    r = run(out)
    assert r.returncode == 1
    assert "PATH differs (1 entries)" in r.stdout
    assert "secret-host-dir" not in r.stdout + r.stderr


def test_changed_other_variable_is_named(out):
    run(out, "--record")
    (out / "environment.x64").write_bytes(env("C:\\py;C:\\depot_tools;C:\\Windows", "x"))
    r = run(out)
    assert r.returncode == 1 and "INCLUDE differs" in r.stdout


def test_no_record_is_refused(out):
    assert run(out).returncode != 0

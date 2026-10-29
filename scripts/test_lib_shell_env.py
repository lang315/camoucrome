"""The caller's display environment must not change what a hand-run box verify measures.

CI's runner is a service with no DISPLAY, WAYLAND_DISPLAY, XDG_RUNTIME_DIR or PULSE_SERVER. A hand-run shell on the
build box inherits all four from WSLg, and with them headless Chrome's page.click() timed out ("waiting for element to
be visible, enabled and stable") on both the 156 and the 157 build (2026-10-28), failing verify_host_oracle O3 while
CI stayed green. lib_shell drops them at import, so every launch path that copies os.environ (lib_shell.launch, the
clients' build_env, the probes the verifies spawn) starts from CI's environment; a verify that needs the display on
purpose says so with restore_display_env().
"""
import importlib
import os
import pathlib
import sys
import types

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
if "playwright.sync_api" not in sys.modules:  # as test_lib_shell_launch: only session()/evaluate() need it
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        pkg, api = types.ModuleType("playwright"), types.ModuleType("playwright.sync_api")
        api.sync_playwright = None
        pkg.sync_api = api
        sys.modules["playwright"], sys.modules["playwright.sync_api"] = pkg, api

VARS = ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "PULSE_SERVER")


@pytest.fixture
def wslg_shell(monkeypatch):
    for k in VARS:
        monkeypatch.setenv(k, "/mnt/wslg/x" if k != "DISPLAY" else ":0")
    monkeypatch.delenv("CAMOU_VERIFY_KEEP_DISPLAY", raising=False)
    return monkeypatch


def fresh_lib_shell():
    import lib_shell
    return importlib.reload(lib_shell)


def test_import_drops_the_display_variables(wslg_shell):
    fresh_lib_shell()
    assert [k for k in VARS if k in os.environ] == []


def test_launch_child_env_has_no_display_variables(wslg_shell):
    lib_shell = fresh_lib_shell()
    seen = {}

    class Dead:
        returncode = 3
        def __init__(self, argv, env=None, **kw): seen["env"] = env
        def poll(self): return 3
        def terminate(self): pass
        def wait(self, timeout=None): return 3

    real = lib_shell.subprocess.Popen
    lib_shell.subprocess.Popen = Dead
    try:
        with pytest.raises(RuntimeError):
            lib_shell.launch(None)
    finally:
        lib_shell.subprocess.Popen = real
    assert [k for k in VARS if k in seen["env"]] == []


def test_keep_flag_leaves_the_display_alone(wslg_shell):
    wslg_shell.setenv("CAMOU_VERIFY_KEEP_DISPLAY", "1")
    fresh_lib_shell()
    assert all(k in os.environ for k in VARS)


def test_a_headed_verify_can_restore_what_the_caller_had(wslg_shell):
    lib_shell = fresh_lib_shell()
    assert "DISPLAY" not in os.environ
    lib_shell.restore_display_env()
    assert os.environ["DISPLAY"] == ":0" and os.environ["XDG_RUNTIME_DIR"] == "/mnt/wslg/x"


def test_every_script_that_launches_headed_restores_the_display():
    """A headed launch on WSLg needs DISPLAY; a script added later that forgets to ask would fail on the box only."""
    missing = []
    for p in sorted(SCRIPTS.glob("*.py")):
        if p.name.startswith("test_") or p.name == "lib_shell.py":
            continue
        src = p.read_text(encoding="utf-8")
        top_level = any(l.startswith(("import lib_shell", "from lib_shell")) for l in src.splitlines())
        if top_level and ('"--headed"' in src or "headless=False" in src) and "restore_display_env" not in src:
            missing.append(p.name)
    assert missing == []


def test_read_stderr_returns_this_sessions_log_or_the_fault(tmp_path, monkeypatch):
    # seven verifies carried the same copy of this guarded read; it lives in lib_shell now
    import lib_shell
    log = tmp_path / "stderr.log"
    monkeypatch.setattr(lib_shell, "STDERR_LOG", str(log))
    log.write_bytes(b"ok \xff line\n")
    text, err = lib_shell.read_stderr()
    assert err is None and text == "ok � line\n"
    log.unlink()
    text, err = lib_shell.read_stderr()
    assert text is None and isinstance(err, FileNotFoundError)  # a fault becomes a FAIL row, never an exception

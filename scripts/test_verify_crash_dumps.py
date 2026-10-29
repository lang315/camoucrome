"""verify_crash_dumps: a hung or failed launch must read NOT MEASURED, never PASS, and say what was swallowed."""
import pathlib
import sys
import types

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
if "playwright.sync_api" not in sys.modules:  # only session()/evaluate() and crash() need it
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        pkg, api = types.ModuleType("playwright"), types.ModuleType("playwright.sync_api")
        api.sync_playwright = None
        pkg.sync_api = api
        sys.modules.update({"playwright": pkg, "playwright.sync_api": api})
import verify_crash_dumps as v  # noqa: E402


@pytest.mark.parametrize("windows,code,crashed", [
    (False, None, False),   # a browser still alive after the wait is not a crash
    (False, 0, False), (False, 1, False), (False, -11, True), (False, -6, True),
    (True, None, False), (True, 0, False), (True, 1, False), (True, 0xC0000005, True),
])
def test_crashed_exit(monkeypatch, windows, code, crashed):
    monkeypatch.setattr(v, "WINDOWS", windows)
    assert v.crashed_exit(code) is crashed


def test_a_browser_crash_is_seen_by_its_exit_code_and_a_hung_browser_is_not(monkeypatch):
    monkeypatch.setattr(v, "WINDOWS", False)
    assert v.verdict(None, crashed=[], code=-11, alive=False, swallowed=[]) == (True, "exit code -11")
    seen, detail = v.verdict(None, crashed=[], code=None, alive=True, swallowed=["TimeoutError()"])
    assert seen is False and "exit code None" in detail and "TimeoutError()" in detail  # why nothing was measured


def test_a_renderer_crash_needs_the_event_and_a_live_browser():
    assert v.verdict("chrome://crash", crashed=[True], code=None, alive=True, swallowed=[]) == (
        True, "renderer crashed True, browser alive True")
    seen, detail = v.verdict("chrome://crash", crashed=[], code=None, alive=True, swallowed=["TargetClosedError()"])
    assert seen is False and "TargetClosedError()" in detail
    assert v.verdict("chrome://crash", crashed=[True], code=1, alive=False, swallowed=[])[0] is False

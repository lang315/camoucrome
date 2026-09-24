"""winhost.py's generated PowerShell: literal arguments and PS 5.1-safe process lookup.
No PowerShell runs here; the script text is captured and inspected."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import winhost  # noqa: E402

ARG = """--x=$env:USERNAME "q" it's"""


@pytest.fixture
def captured(monkeypatch):
    scripts = []

    def fake(script, timeout=300):
        scripts.append(script)
        return '<pre id="o">{}</pre>\nCDP_RESULT_BEGIN\n{"result":{"result":{"value":1}}}\nCDP_RESULT_END\nCDP_EVENTS_BEGIN\n\nCDP_EVENTS_END\n'

    monkeypatch.setattr(winhost, "powershell", fake)
    return scripts


def test_arguments_are_single_quoted_literals(captured):
    winhost.dump_dom("<p>", args=[ARG])
    winhost.cdp_eval("<p>", expression='"$x"', args=[ARG])
    winhost.cdp_headers("https://a/?b=$c", seconds=0, args=[ARG])
    for s in captured:
        assert """'--x=$env:USERNAME "q" it''s'""" in s
        assert '"--x=' not in s
    assert """expression = '"$x"'""" in captured[1]
    assert "url = 'https://a/?b=$c'" in captured[2]


def test_dump_dom_cleanup_does_not_read_commandline_from_get_process(captured):
    winhost.dump_dom("<p>")
    assert "Get-Process" not in captured[0]
    assert "Get-CimInstance Win32_Process" in captured[0]

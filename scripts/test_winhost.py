"""winhost.py's generated PowerShell: literal arguments and PS 5.1-safe process lookup.
No PowerShell runs here; the script text is captured and inspected."""
import base64
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gpu_gate  # noqa: E402
import winhost  # noqa: E402

ARG = """--x=$env:USERNAME "q" it's"""


@pytest.fixture
def captured(monkeypatch):
    scripts = []

    def fake(script, timeout=300):
        scripts.append(script)
        return ('SESSION=1\n<pre id="o">{}</pre>\nCDP_RESULT_BEGIN\n{"result":{"result":{"value":1}}}\nCDP_RESULT_END\n'
                'CDP_EVENTS_BEGIN\n\nCDP_EVENTS_END\n'
                'GPU_BEGIN\n{"id":9,"result":{"result":{"type":"string","value":"GPU process crash count :0"}}}\nGPU_END\n')

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


def test_in_session_registers_an_interactive_task_and_cleans_up():
    ps = winhost.in_session('"hello"', 90)
    for needle in ("New-ScheduledTaskPrincipal -UserId (whoami) -LogonType Interactive", "Register-ScheduledTask",
                   "Start-ScheduledTask", "Unregister-ScheduledTask", "AddSeconds(90)"):
        assert needle in ps
    b64 = ps.split('FromBase64String("')[1].split('"')[0]
    assert base64.b64decode(b64).decode() == '"hello"'


@pytest.mark.parametrize("out,raises", [
    ("SESSION=1\nx", None),
    ("SESSION=0\nx", "UNMEASURED session=0"),
    ("x", "UNMEASURED session=unknown"),
])
def test_session_gate(out, raises, monkeypatch):
    monkeypatch.delenv("CAMOU_ALLOW_SESSION0", raising=False)
    if raises is None:
        winhost.session_gate(out)
    else:
        with pytest.raises(gpu_gate.Unmeasured) as e:
            winhost.session_gate(out)
        assert str(e.value).startswith(raises)


def test_session_gate_off_for_a_red(monkeypatch):
    monkeypatch.setenv("CAMOU_ALLOW_SESSION0", "1")
    winhost.session_gate("SESSION=0\n")


def gpu_out(text):
    return 'GPU_BEGIN\n{"id":9,"result":{"result":{"type":"string","value":' + json.dumps(text) + "}}}\nGPU_END\n"


def test_crash_gate():
    winhost.crash_gate(gpu_out("GPU process crash count :0"))
    with pytest.raises(gpu_gate.GpuCrashed) as e:
        winhost.crash_gate(gpu_out("GPU process crash count :1"))
    assert e.value.n == 1
    with pytest.raises(gpu_gate.GpuCrashed):
        winhost.crash_gate("GPU_BEGIN\nGPU_END\n")  # no reading is not a pass


def test_cdp_paths_read_chrome_gpu(captured):
    winhost.cdp_eval("<p>")
    winhost.cdp_headers("https://a/", seconds=0)
    assert all("json/new?chrome://gpu" in s and "GPU_BEGIN" in s for s in captured)

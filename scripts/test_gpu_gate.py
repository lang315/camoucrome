"""gpu_gate's pure parts (S4: a GPU process that crashed at launch latches empty GPU answers)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gpu_gate as g  # noqa: E402

# The line's shape as chrome://gpu printed it on the host, 2026-10-13 (space before the colon).
S0 = "Video Decode: Hardware accelerated\nGPU process crash count :1\nWebGPU: Hardware accelerated but at reduced performance"
S1 = "Video Decode: Hardware accelerated\nGPU process crash count :0"


def test_crash_count_reads_the_host_shape():
    assert g.crash_count(S0) == 1
    assert g.crash_count(S1) == 0
    assert g.crash_count("GPU process crash count: 12") == 12


@pytest.mark.parametrize("text", [None, "", "Video Decode: Hardware accelerated", "GPU process crash count :"])
def test_no_count_line_is_none_not_zero(text):
    assert g.crash_count(text) is None


def test_check_passes_only_zero():
    g.check(0)
    for n in (1, None):
        with pytest.raises(g.GpuCrashed) as e:
            g.check(n)
        assert e.value.n == n
    assert str(g.GpuCrashed(1)) == "UNMEASURED gpu-crash=1"
    assert str(g.GpuCrashed(None)) == "UNMEASURED gpu-crash=unknown"
    assert isinstance(g.GpuCrashed(1), g.Unmeasured)


def test_session_problem_names_session_zero_only():
    assert g.session_problem(0).startswith("UNMEASURED session=0")
    assert g.session_problem(1) is None
    assert g.session_problem(None) is None  # off Windows


def test_require_interactive_exits_3_in_session_zero(monkeypatch, capsys):
    monkeypatch.setattr(g, "session_id", lambda: 0)
    monkeypatch.delenv("CAMOU_ALLOW_SESSION0", raising=False)
    with pytest.raises(SystemExit) as e:
        g.require_interactive()
    assert e.value.code == 3
    assert capsys.readouterr().out.startswith("UNMEASURED session=0")


def test_require_interactive_allows_a_red_run(monkeypatch, capsys):
    monkeypatch.setattr(g, "session_id", lambda: 0)
    monkeypatch.setenv("CAMOU_ALLOW_SESSION0", "1")
    g.require_interactive()
    assert "CAMOU_ALLOW_SESSION0=1" in capsys.readouterr().out


def test_session_id_is_none_off_windows():
    if os.name != "nt":
        assert g.session_id() is None

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


import types  # noqa: E402

import lib_shell  # noqa: E402


def proc(name="chrome.exe", port=9222):
    return types.SimpleNamespace(binary_name=name, cdp_port=port)


def test_lib_shell_gate_is_off_outside_windows_and_chrome():
    called = []
    reader = lambda port: called.append(port) or 1  # noqa: E731
    assert lib_shell.gpu_gate_line(proc(), osname="posix", reader=reader) is None
    assert lib_shell.gpu_gate_line(proc("content_shell.exe"), osname="nt", reader=reader) is None
    assert lib_shell.gpu_gate_line(proc(port=None), osname="nt", reader=reader) is None
    assert called == []


def test_lib_shell_gate_lines():
    assert lib_shell.gpu_gate_line(proc(), osname="nt", reader=lambda p: 0) is None
    assert lib_shell.gpu_gate_line(proc(), osname="nt", reader=lambda p: 1) == "UNMEASURED gpu-crash=1"
    assert lib_shell.gpu_gate_line(proc(), osname="nt", reader=lambda p: None) == "UNMEASURED gpu-crash=unknown"


def test_lib_shell_gate_skips_a_browser_that_already_exited():
    # verify_crash_dumps C2 crashes the browser on purpose (2026-10-13 session-1 run printed
    # "UNMEASURED gpu-crash=unknown" twice): a gone browser has no chrome://gpu to read, and
    # what it measured is that verify's own business.
    gone = types.SimpleNamespace(binary_name="chrome.exe", cdp_port=9222, poll=lambda: 3221225477)
    called = []
    assert lib_shell.gpu_gate_line(gone, osname="nt", reader=lambda p: called.append(p) or None) is None
    assert called == []


def test_lib_shell_gate_off_when_the_launch_opts_out():
    # verify_crash_dumps crashes a renderer on purpose; afterwards a CDP connect to read
    # chrome://gpu hangs (>60 s, host 2026-10-13), and none of its rows is GPU-backed.
    p = types.SimpleNamespace(binary_name="chrome.exe", cdp_port=9222, gpu_gate=False)
    assert lib_shell.gpu_gate_line(p, osname="nt", reader=lambda port: 1) is None


def test_lib_shell_launch_records_the_opt_out():
    import inspect
    assert inspect.signature(lib_shell.launch).parameters["gpu_gate"].default is True


def test_lib_shell_exit_code_turns_unmeasured_on_a_standalone_run():
    # Final review: a gated verify run on its own printed UNMEASURED and still exited 0.
    exits = []
    lib_shell._exit_if_unmeasured(["UNMEASURED gpu-crash=1"], exit=exits.append)
    lib_shell._exit_if_unmeasured([], exit=exits.append)
    assert exits == [3]


def test_lib_shell_gate_fails_closed_when_the_read_raises():
    def boom(port):
        raise OSError("gone")
    assert lib_shell.gpu_gate_line(proc(), osname="nt", reader=boom) == "UNMEASURED gpu-crash=unknown"


def test_renderer_family_names_vendor_and_backend_only():
    fam, software = g.renderer_family(
        "ANGLE (ExampleVendor, ExampleVendor Model 1 (0x0000ABCD) Direct3D11 vs_5_0 ps_5_0, D3D11-1.2.3.4)")
    assert fam == "ExampleVendor / Direct3D11" and software is False
    assert "Model 1" not in fam and "1.2.3.4" not in fam


def test_renderer_family_flags_software_renderers():
    for r in ("ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)",
              "ANGLE (Microsoft, Microsoft Basic Render Driver Direct3D11 vs_5_0 ps_5_0, D3D11)",
              "Mesa llvmpipe"):
        assert g.renderer_family(r)[1] is True


def test_renderer_family_unreadable_is_not_a_family():
    assert g.renderer_family(None) == ("unknown vendor / unknown backend", False)


def test_status_lines_keep_feature_states_only():
    text = ("Canvas: Hardware accelerated\nRasterization: Hardware accelerated on all threads\n"
            "GL_RENDERER: ANGLE (ExampleVendor, ExampleVendor Model 1 Direct3D11, D3D11)\nWebGL: Hardware accelerated\n"
            "Driver version: 1.2.3.4\nGPU process crash count :0")
    assert g.status_lines(text) == ["Canvas: Hardware accelerated", "Rasterization: Hardware accelerated on all threads",
                                    "WebGL: Hardware accelerated"]


def test_status_lines_accept_the_table_row_form_without_a_colon():
    assert g.status_lines("Canvas Hardware accelerated\nRasterization Software only. Hardware acceleration disabled")[0] == \
        "Canvas: Hardware accelerated"


def test_variation_count_counts_distinct_ids_only():
    page = "Variations: a1b2c3d4-0000ffff 11112222-33334444 a1b2c3d4-0000ffff"
    assert g.variation_count(page) == 2
    assert g.variation_count("Variations: ") == 0
    assert g.variation_count("Google Chrome 157") is None


def test_status_lines_accept_the_bulleted_form_of_chrome_gpu():
    assert g.status_lines("* Canvas: Hardware accelerated\n* Rasterization: Hardware accelerated\n"
                          "GL_VERSION :OpenGL ES 3.0 (ANGLE 2.1.3)") == ["Canvas: Hardware accelerated",
                                                                         "Rasterization: Hardware accelerated"]


def test_status_lines_drop_a_line_whose_value_is_not_a_state_word():
    assert g.status_lines("* Canvas: ANGLE (ExampleVendor, Model 1)\n* WebGL: Hardware accelerated") == ["WebGL: Hardware accelerated"]

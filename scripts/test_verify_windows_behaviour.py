import verify_windows_behaviour as v


def test_claim_rate_differs_from_the_boxs_real_rate():
    """A1/A4 prove the hook only if the claim is not what the device already reports (RED: 44100 claim on a 44100 box)."""
    assert v.audio_claim({"audio:sampleRate": 44100, "audio:bufferFrames": 441}, 44100) == (48000, 480)
    assert v.audio_claim({"audio:sampleRate": 48000, "audio:bufferFrames": 480}, 48000) == (44100, 441)


def test_claim_is_kept_when_it_already_differs():
    assert v.audio_claim({"audio:sampleRate": 44100, "audio:bufferFrames": 441}, 48000) == (44100, 441)


def test_claim_keeps_a_ten_millisecond_quantum():
    for real in (44100, 48000, 96000):
        rate, frames = v.audio_claim({"audio:sampleRate": 44100, "audio:bufferFrames": 441}, real)
        assert rate != real and frames == rate // 100


def test_interfaces_follow_the_claim():
    assert v.iface_ok("linux", {"share": "undefined", "bluetooth": "undefined"})
    assert v.iface_ok("windows", {"share": "function", "bluetooth": "object"})
    assert v.iface_ok("macos", {"share": "function", "bluetooth": "object"})


def test_interface_rows_fail_on_the_wrong_shape():
    """RED fixtures: the unamended Windows build under a Linux claim, and a build that dropped the enabling branch."""
    assert not v.iface_ok("linux", {"share": "function", "bluetooth": "object"})
    assert not v.iface_ok("linux", {"share": "undefined", "bluetooth": "object"})
    assert not v.iface_ok("windows", {"share": "undefined", "bluetooth": "undefined"})
    assert not v.iface_ok("macos", {"error": "launch failed"})


def test_row_count_includes_the_interface_rows():
    assert v.EXPECTED_ROWS == 17


def _run_as_script(monkeypatch, capsys):
    """Run the file the way the box does (`python3 verify_windows_behaviour.py --interfaces-only`), not as an import:
    helpers defined below the __main__ guard exist for the import tests and are missing here (NameError)."""
    import json
    import runpy
    import subprocess
    import sys
    import types
    import verify_windows_behaviour

    def fake_run(cmd, **kw):
        if "camoucrome.gen" in cmd:  # gen(): the config carries the claim, nothing else
            out = json.dumps({"config": {"claim": cmd[cmd.index("--os") + 1]}})
        else:  # iface_probe(): the page's answer, by the claim found in the embedded config
            claim = next(c for c in ("linux", "windows", "macos") if f'\\"claim\\": \\"{c}\\"' in cmd[2])
            out = json.dumps(v.iface_expect(claim))
        return subprocess.CompletedProcess(cmd, 0, out, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setitem(sys.modules, "gpu_gate", types.SimpleNamespace(require_interactive=lambda: None))
    monkeypatch.setattr(sys, "argv", [verify_windows_behaviour.__file__, "--interfaces-only"])
    with __import__("pytest").raises(SystemExit) as e:
        runpy.run_path(verify_windows_behaviour.__file__, run_name="__main__")
    return e.value.code, capsys.readouterr().out


def test_script_entry_path_runs_b1_to_b3(monkeypatch, capsys):
    code, out = _run_as_script(monkeypatch, capsys)
    assert code == 0
    assert [l.split()[1] for l in out.splitlines() if l.startswith("PASS")] == ["B1", "B2", "B3"]

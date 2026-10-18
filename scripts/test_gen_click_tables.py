# scripts/test_gen_click_tables.py
import json, pathlib, subprocess, sys
import gen_click_tables as g

FIX = pathlib.Path(__file__).parent / "testdata" / "human-click-fixture"


def test_outputs_have_21_knots_and_shared_constants(tmp_path):
    out = g.render(g.load(FIX, provisional=False))
    assert out["cpp"].count("kHoldMsKnots[21]") == 1 and out["cpp"].count("kDwellMsKnots[21]") == 1
    assert "kMaxHoldMs = 400" in out["cpp"] and "kMaxDwellMs = 600" in out["cpp"]
    py = {}
    exec(out["py"], py)
    assert len(py["HOLD_MS"]) == 21 and py["INNER_FRACTION"] == 0.8 and py["MAX_NOTCHES"] == 60
    assert py["GEOMETRY_JS"] == (pathlib.Path(g.ROOT) / "settings/human_click_geometry.js").read_text()
    assert '"maxNotches": 60' in json.dumps(out["launcher_block"])


def test_strict_refuses_one_session(tmp_path):
    one = tmp_path / "b"
    one.mkdir()
    (one / "mac-s1.json").write_text((FIX / "mac-s1.json").read_text())
    try:
        g.load(one, provisional=False)
        raise AssertionError("strict load accepted 1 session")
    except SystemExit as e:
        assert "2 sessions" in str(e)
    assert g.load(one, provisional=True)["n_sessions"] == 1


def test_floor_check_rejects_tiny_holds(tmp_path):
    s = g.load(FIX, provisional=False)
    s["hold_ms"] = [1.0] * 21
    try:
        g.render(s)
        raise AssertionError("accepted p5 < 25 ms")
    except SystemExit as e:
        assert "p5" in str(e)


def test_check_mode_detects_stale(tmp_path):
    r = subprocess.run([sys.executable, str(pathlib.Path(g.__file__)), "--baseline", str(FIX), "--check",
                        "--root", str(tmp_path)], capture_output=True, text=True)
    assert r.returncode == 1 and "stale" in r.stdout

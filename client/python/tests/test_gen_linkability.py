import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camoucrome import gen  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[3]


def test_audio_json_windows_row_equals_the_stock_baseline():
    base = json.loads((ROOT / "baselines" / "chrome-8103-stock-oracle-windows.json").read_text())["headed"]["audio"]
    row = json.loads((ROOT / "settings" / "audio.json").read_text())["Windows"]
    assert row["sampleRate"] == base["sampleRate"]
    assert row["bufferFrames"] == round(base["baseLatency"] * base["sampleRate"])


def test_host_platform_version_wins_over_the_pool():
    c = gen.generate("windows", timezone="Europe/Paris", seed=1, host_platform_version="15.0.0")["config"]
    assert c["ua:platformVersion"] == "15.0.0"


def test_no_host_version_keeps_the_pool_value():
    c = gen.generate("windows", timezone="Europe/Paris", seed=1)["config"]
    assert c["ua:platformVersion"] == "10.0.0"


EXPECTED_SHARE_CANCEL_MS_SEED_3 = 1167  # printed from the code before the window-position change


def _pos(seed):
    c = gen.generate("windows", timezone="Europe/Paris", seed=seed)["config"]
    return c["window.screenX"], c["window.screenY"]


def test_window_position_varies_across_seeds():
    assert len({_pos(s) for s in range(1, 21)}) >= 8


def test_window_position_is_seed_stable():
    assert _pos(7) == _pos(7)


def test_window_position_stays_inside_the_screen():
    for s in range(1, 41):
        r = gen.generate("windows", timezone="Europe/Paris", seed=s)
        c = r["config"]
        assert 0 <= c["window.screenX"] <= c["screen.width"] - c["window.outerWidth"]
        assert 0 <= c["window.screenY"] <= c["screen.height"] - c["window.outerHeight"]
        assert r["launch"]["position"] == [c["window.screenX"], c["window.screenY"]]


def test_other_seeded_keys_do_not_move():
    c = gen.generate("windows", timezone="Europe/Paris", seed=3)["config"]
    assert c["share:cancelMs"] == EXPECTED_SHARE_CANCEL_MS_SEED_3


def test_both_axes_vary_and_the_window_stays_inside_the_work_area():
    assert len({_pos(s)[0] for s in range(1, 21)}) >= 6
    assert len({_pos(s)[1] for s in range(1, 21)}) >= 6
    for s in range(1, 41):
        c = gen.generate("windows", timezone="Europe/Paris", seed=s)["config"]
        assert c["window.screenX"] + c["window.outerWidth"] <= c["screen.availWidth"]
        assert c["window.screenY"] + c["window.outerHeight"] <= c["screen.availHeight"]


def test_pinned_window_geometry_for_seeds_1_to_3():
    # (screenX, screenY, outerWidth, outerHeight) printed from the code that draws the offset
    keys = ("window.screenX", "window.screenY", "window.outerWidth", "window.outerHeight")
    got = {s: tuple(gen.generate("windows", timezone="Europe/Paris", seed=s)["config"][k] for k in keys) for s in (1, 2, 3)}
    assert got == {1: (66, 75, 1854, 1077), 2: (101, 115, 1434, 860), 3: (73, 11, 1847, 1021)}


def test_host_platform_version_is_windows_only_and_validated():
    ok = gen.generate("windows", timezone="Europe/Paris", seed=1, host_platform_version="15.0.0")
    assert ok["config"]["ua:platformVersion"] == "15.0.0"
    for os_ in ("macos", "linux"):
        r = gen.generate(os_, timezone="Europe/Paris", seed=1, host_platform_version="15.0.0")
        assert r["config"].get("ua:platformVersion") != "15.0.0"
    bad = gen.generate("windows", timezone="Europe/Paris", seed=1, host_platform_version="Windows 11")
    assert bad["config"]["ua:platformVersion"] == "10.0.0" and any("not N.N.N" in w for w in bad["warnings"])


def test_malformed_host_display_is_ignored_with_a_warning():
    r = gen.generate("windows", timezone="Europe/Paris", seed=1, host_display={"gamut": "p3"})
    assert r["launch"]["args"] == [] and any("malformed" in w for w in r["warnings"])


def test_modal_host_gets_no_flag_and_no_warning():
    assert gen.display_flags({"gamut": "srgb", "colorBits": 8, "hdr": False}) == ([], None)


def test_non_modal_host_gets_srgb_flag_and_warning():
    flags, warn = gen.display_flags({"gamut": "p3", "colorBits": 10, "hdr": True})
    assert flags == ["--force-color-profile=srgb"]
    assert "hdr" in warn and "10-bit" in warn   # the flag cannot hide these two; the warning says so


def test_unknown_display_is_left_alone():
    assert gen.display_flags(None) == ([], "display unknown: gamut, bit depth and HDR keep the host's values")


def test_generate_carries_the_display_flag_in_launch_args_and_the_warning():
    out = gen.generate("windows", timezone="Europe/Paris", seed=1,
                       host_display={"gamut": "p3", "colorBits": 8, "hdr": False})
    assert out["launch"]["args"] == ["--force-color-profile=srgb"] and not any("host display" in w for w in out["warnings"])
    out = gen.generate("windows", timezone="Europe/Paris", seed=1,
                       host_display={"gamut": "p3", "colorBits": 10, "hdr": False})
    assert any("10-bit" in w for w in out["warnings"])
    assert gen.generate("windows", timezone="Europe/Paris", seed=1)["launch"]["args"] == []


def test_locale_keys_move_together_for_every_known_locale():
    zones = json.loads((ROOT / "settings" / "locale_zones.json").read_text())["zones"]
    bad = []
    for loc in zones:
        r = gen.generate("windows", timezone=zones[loc][0], locale=loc, seed=1)
        c = r["config"]
        ok = (c["locale:tag"] == c["navigator.language"] == c["navigator.languages"][0] == loc
              and c["timezone:id"] == zones[loc][0])
        if not ok:
            bad.append(loc)
    assert bad == []


def test_malformed_host_display_exits_with_one_line(monkeypatch, capsys):
    import pytest
    for bad in ('{"gamut": "p3"}', '5', '{"gamut":"x","colorBits":8,"hdr":false}'):
        monkeypatch.setattr(sys, "argv", ["gen", "--host-display", bad])
        with pytest.raises(SystemExit) as e:
            gen.main()
        assert str(e.value).startswith("gen: --host-display must be") and "\n" not in str(e.value)

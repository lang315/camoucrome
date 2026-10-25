import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camoucrome import gen  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[3]


def test_audio_json_windows_row_equals_the_stock_baseline():
    base = json.loads((ROOT / "baselines" / "chrome-8078-stock-oracle-windows.json").read_text())["headed"]["audio"]
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


CODES = ("Backquote", "Digit1", "KeyA", "KeyQ")


def test_fr_locale_gets_an_azerty_map():
    keys, warn = gen.keyboard_keys("fr-FR")
    m = keys["keyboard:layoutMap"]
    assert (m["KeyA"], m["KeyQ"]) == ("q", "a") and warn is None


def test_us_locale_gets_the_us_map():
    m = gen.keyboard_keys("en-US")[0]["keyboard:layoutMap"]
    assert (m["KeyA"], m["KeyQ"], m["Backquote"], m["Digit1"]) == ("a", "q", "`", "1")


def test_unmapped_locale_has_no_layout_and_warns():
    keys, warn = gen.keyboard_keys("xx-XX")
    assert keys == {} and "keyboard layout" in warn


def test_every_known_locale_is_mapped_or_listed_unmapped():
    zones = json.loads((ROOT / "settings" / "locale_zones.json").read_text())["zones"]
    table = json.loads((ROOT / "settings" / "keyboard_layouts.json").read_text())
    missing = [l for l in zones if l not in table["locales"] and l not in table["unmapped"]]
    assert missing == []


def test_every_layout_has_the_four_codes_and_every_locale_points_at_one():
    table = json.loads((ROOT / "settings" / "keyboard_layouts.json").read_text())
    assert all(set(CODES) <= set(row) for row in table["layouts"].values())
    assert set(table["locales"].values()) <= set(table["layouts"])
    assert not set(table["locales"]) & set(table["unmapped"])


def test_only_y_varies_screen_x_is_zero_when_the_window_fills_the_width():
    # documents the real behaviour: pool windows fill the screen width, so x has no slack
    for s in range(1, 41):
        c = gen.generate("windows", timezone="Europe/Paris", seed=s)["config"]
        if c["window.outerWidth"] == c["screen.width"]:
            assert c["window.screenX"] == 0
    assert len({_pos(s)[1] for s in range(1, 21)}) >= 6


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


KEYBOARD_MAPPED = set(json.loads((ROOT / "settings" / "keyboard_layouts.json").read_text())["locales"])


def test_locale_keys_move_together_for_every_known_locale():
    zones = json.loads((ROOT / "settings" / "locale_zones.json").read_text())["zones"]
    bad = []
    for loc in zones:
        r = gen.generate("windows", timezone=zones[loc][0], locale=loc, seed=1)
        c = r["config"]
        ok = (c["locale:tag"] == c["navigator.language"] == c["navigator.languages"][0] == loc
              and c["timezone:id"] == zones[loc][0]
              and (loc not in KEYBOARD_MAPPED or "keyboard:layoutMap" in c))
        if not ok:
            bad.append(loc)
    assert bad == []

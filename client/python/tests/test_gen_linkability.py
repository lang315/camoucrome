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

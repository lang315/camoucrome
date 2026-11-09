"""settings/light_flags.json against itself and against settings/launcher.json (approach B)."""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
FLAGS = json.loads((ROOT / "settings" / "light_flags.json").read_text(encoding="utf-8"))["flags"]
LAUNCHER = json.loads((ROOT / "settings" / "launcher.json").read_text(encoding="utf-8"))


def test_entries_have_known_states_and_no_comma():
    assert FLAGS, "no candidate"
    for f in FLAGS:
        assert f["flag"].startswith("--") and "," not in f["flag"], f["flag"]  # observe-auto -Flags splits on ','
        assert f["gate"] in ("pending", "pass", "fail") and f["measured"] in ("pending", "kept", "dropped")
        assert not (f["measured"] == "kept" and f["gate"] != "pass"), f["flag"]
    assert len({f["flag"] for f in FLAGS}) == len(FLAGS)


def test_light_args_hold_only_kept_flags_and_nothing_forbidden():
    light = LAUNCHER["launch"].get("light_args", [])
    kept = [f["flag"] for f in FLAGS if f["measured"] == "kept"]
    assert light == kept  # same set, light_flags.json order
    assert not set(light) & set(LAUNCHER["browser_argv_must_not_contain"])

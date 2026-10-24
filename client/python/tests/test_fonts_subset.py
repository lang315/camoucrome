"""Fonts as subsets of the host's real families (step 6 task 7)."""
import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camoucrome import gen, hostfonts  # noqa: E402

OLD_FONTS_KEYS_WINDOWS = json.loads((pathlib.Path(__file__).parent / "fixtures" / "old_fonts_keys_windows.json").read_text(encoding="utf-8"))


def _fam():
    return json.loads((gen.ROOT / "settings/fonts.json").read_text(encoding="utf-8"))["families"]["Windows"]


def test_base_always_present_groups_drawn_per_seed():
    k = gen.fonts_keys("Windows", random.Random(1), host_families=None)
    assert set(_fam()["base"]) <= set(k["fonts:list"])


def test_font_draw_is_seed_stable():
    a = gen.fonts_keys("Windows", random.Random(9))["fonts:list"]
    assert a == gen.fonts_keys("Windows", random.Random(9))["fonts:list"]


def test_groups_vary_across_seeds():
    lists = {tuple(gen.fonts_keys("Windows", random.Random(s))["fonts:list"]) for s in range(30)}
    assert len(lists) >= 2


def test_base_font_missing_on_host_is_not_claimed():
    fam = _fam()
    host = set(fam["base"]) - {fam["base"][0]}
    assert fam["base"][0] not in gen.fonts_keys("Windows", random.Random(1), host_families=host)["fonts:list"]


def test_local_faces_follow_the_chosen_families():
    k = gen.fonts_keys("Windows", random.Random(2))
    chosen = set(k["fonts:list"])
    assert all(f.split("\t")[2] in chosen for f in k.get("fonts:local", []))


def test_rng_none_is_todays_output():
    assert json.loads(json.dumps(gen.fonts_keys("Windows"))) == OLD_FONTS_KEYS_WINDOWS


def test_nothing_is_claimed_that_the_capture_lacks():
    fam = _fam()
    captured = set(fam["list"])
    assert set(fam["base"]) <= captured
    for g in fam["groups"].values():
        assert set(g["families"]) <= captured
        assert g["p_how"] == "assumption" and g["how"]


def test_parse_registry_names():
    names = ["Arial (TrueType)", "Calibri Light (OpenType)", "Cambria & Cambria Math (TrueType)",
             "MS Gothic & MS UI Gothic & MS PGothic (TrueType)"]
    assert hostfonts.parse_registry_names(names) == {
        "Arial", "Calibri Light", "Cambria", "Cambria Math", "MS Gothic", "MS UI Gothic", "MS PGothic"}


def test_families_is_none_off_windows():
    if sys.platform != "win32":
        assert hostfonts.families() is None

"""Fonts as subsets of the host's real families (step 6 task 7)."""
import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camoucrome import gen, hostfonts  # noqa: E402

OLD_FONTS_KEYS_WINDOWS = json.loads((pathlib.Path(__file__).parent / "fixtures" / "old_fonts_keys_windows.json").read_text(encoding="utf-8"))


def _extra():
    return json.loads((gen.ROOT / "settings/fonts.json").read_text(encoding="utf-8"))["extra_allowed"]["Windows"]


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
    chosen = set(k["fonts:list"]) - set(_extra())
    assert k["fonts:local"] and all(f.split("\t")[2] in chosen for f in k["fonts:local"])


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


def _assert_no_hidden_name_passes(k):
    fonts = json.loads((gen.ROOT / "settings/fonts.json").read_text(encoding="utf-8"))
    fam = fonts["families"]["Windows"]
    shown = set(k["fonts:list"])
    hidden = set(fam["list"]) - shown
    assert hidden
    for name, v in fam["unique_names"].items():
        if v["family"] in hidden:
            assert name not in k["fonts:aliasLocal"], name
    assert not hidden & set(k["fonts:alias"])
    for name in k["fonts:aliasLocal"]:
        assert fam["unique_names"][name]["family"] in shown, name


def test_hidden_families_leave_no_local_or_alias_name():
    for seed in range(8):
        _assert_no_hidden_name_passes(gen.fonts_keys("Windows", random.Random(seed)))
    fam = _fam()
    host = set(fam["base"]) - {"Arial", "Verdana"}
    _assert_no_hidden_name_passes(gen.fonts_keys("Windows", random.Random(3), host_families=host))


def test_rng_none_with_host_limits_too():
    k = gen.fonts_keys("Windows", host_families={"Arial", "Verdana"})
    assert {"Arial", "Verdana"} <= set(k["fonts:list"]) and "Tahoma" not in k["fonts:list"]


def test_fonts_keys_does_not_advance_the_callers_rng():
    a, b = random.Random(5), random.Random(5)
    ka = gen.fonts_keys("Windows", a)
    assert a.getstate() == random.Random(5).getstate()
    assert gen.fonts_keys("Windows", b)["fonts:list"] == ka["fonts:list"]


def test_unknown_host_limits_nothing():
    base = gen.fonts_keys("Windows", random.Random(4))["fonts:list"]
    assert gen.fonts_keys("Windows", random.Random(4), host_families=set())["fonts:list"] == base
    assert gen.fonts_keys("Windows", random.Random(4), host_families={"NoSuchFont"})["fonts:list"] == base


def test_registry_labels_map_to_captured_families():
    fam = _fam()
    labels = hostfonts.parse_registry_names([
        "Bahnschrift (TrueType)", "Yu Gothic Regular & Yu Gothic UI Regular (TrueType)", "Arial (TrueType)",
        "Arial Bold (TrueType)", "Segoe UI Semibold (TrueType)"])
    got = hostfonts.host_families_from_labels(labels, fam)
    assert got >= {"Arial", "Yu Gothic", "Yu Gothic UI", "Segoe UI Semibold", "Bahnschrift", "Bahnschrift Condensed"}
    assert hostfonts.host_families_from_labels({"ARIAL", "No Such Face"}, fam) == {"Arial"}


def test_real_labels_keep_bahnschrift_instances_in_the_list():
    k = gen.fonts_keys("Windows", random.Random(1), host_families={"Bahnschrift", "Arial"})
    assert "Bahnschrift SemiBold Condensed" in k["fonts:list"] and "Tahoma" not in k["fonts:list"]


def test_host_families_are_ignored_for_a_non_windows_claim():
    host = {"Arial", "Times New Roman"}
    assert gen.fonts_keys("macOS", host_families=host) == gen.fonts_keys("macOS")
    assert gen.fonts_keys("macOS", random.Random(1), host_families=host) == gen.fonts_keys("macOS", random.Random(1))
    assert gen.fonts_keys("Linux", host_families=host) == gen.fonts_keys("Linux") == {}

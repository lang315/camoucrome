"""Supplemental font groups (specs/2026-11-20-supplemental-font-groups-design.md): each Windows Features-on-Demand
font pack is drawn per identity from its own generator, appended after extra_allowed, without faces or aliases."""
import json
import pathlib
import random
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camoucrome import gen  # noqa: E402

FONTS = json.loads((gen.ROOT / "settings/fonts.json").read_text(encoding="utf-8"))
W = FONTS["families"]["Windows"]
SUP = W["supplemental"]
EXTRA = FONTS["extra_allowed"]["Windows"]
SEEDS = range(1, 501)


def _fonts(seed, host_families=None):
    return gen.fonts_keys("Windows", random.Random(seed), host_families)


def _old_groups(seed):
    """origin/main's draw before this change: the optional groups in name order from rng's state."""
    draw = random.Random(repr(random.Random(seed).getstate()))
    return {g for g in sorted(W["groups"]) if draw.random() < W["groups"][g]["p"]}


def _tail(keys):
    """The fonts:list entries after extra_allowed."""
    lst = keys["fonts:list"]
    end = max(i for i, f in enumerate(lst) if f in EXTRA) + 1
    return lst[end:]


def test_data_shape():
    assert len(SUP) == 8
    for name, g in SUP.items():
        assert re.fullmatch(r"Language\.Fonts\.[A-Za-z]+~~~und-[A-Z]+~0\.0\.1\.0", g["capability"]), name
        assert g["families"] and g["p"] == 0.03 and "owner" in g["p_how"] and g["how"] and g["locales"], name


def test_office_terminal_unchanged():
    for s in SEEDS:
        listed = set(_fonts(s)["fonts:list"])
        got = {g for g, v in W["groups"].items() if set(v["families"]) <= listed}
        assert got == _old_groups(s), s


def test_supplemental_deterministic():
    for s in range(1, 50):
        assert _fonts(s) == _fonts(s)


def test_each_group_drawn_and_absent():
    tails = [set(_tail(_fonts(s))) for s in SEEDS]
    for name, g in SUP.items():
        fams = set(g["families"])
        hits = [t >= fams for t in tails]
        assert all(t >= fams or not t & fams for t in tails), f"{name} drawn in part"
        assert 0 < sum(hits) < len(SEEDS), name


def test_at_most_one_drawn_pack_and_rate():
    counts = [len(_packs(_tail(_fonts(s)))) for s in range(1, 2001)]
    assert max(counts) == 1
    share = sum(counts) / len(counts)
    assert 0.17 < share < 0.28, share  # 1-(0.97)^8 = 0.216


def test_appended_after_extra_allowed():
    for s in range(1, 300):
        tail = _tail(_fonts(s))
        drawn = [n for n in sorted(SUP) if set(SUP[n]["families"]) <= set(tail)]
        assert tail == [f for n in drawn for f in SUP[n]["families"]], s


def test_no_rng_no_supplemental():
    every = {f for g in SUP.values() for f in g["families"]}
    assert not every & set(gen.fonts_keys("Windows")["fonts:list"])


def test_host_families_do_not_limit():
    labels = ["Arial (TrueType)", "Calibri (TrueType)", "Segoe UI (TrueType)"]
    for s in range(1, 50):
        assert _tail(_fonts(s, labels)) == _tail(_fonts(s)), s


def test_supplemental_disjoint():
    other = set(W["list"]) | set(W["base"]) | set(EXTRA) | set(W["win11"]["families"])
    other |= {f for g in W["groups"].values() for f in g["families"]}
    seen = set()
    for name, g in SUP.items():
        fams = {f.casefold() for f in g["families"]}
        assert not fams & {f.casefold() for f in other}, name
        assert not fams & seen, name
        seen |= fams


def test_no_faces_or_aliases():
    every = {f for g in SUP.values() for f in g["families"]}
    for s in range(1, 50):
        k = _fonts(s)
        assert not [f for f in k.get("fonts:local", []) if f.split("\t")[2] in every]
        assert not every & set(k["fonts:alias"]) and not every & set(k["fonts:alias"].values())


def test_generate_carries_them_before_win11():
    c = gen.generate(os="windows", seed=7, host_platform_version="19.0.0", host_renderer=None, host_cores=12,
                     host_cpu_vendor=None)["config"]
    lst = c["fonts:list"]
    win11 = W["win11"]["families"]
    assert lst[-len(win11):] == win11
    every = {f for g in SUP.values() for f in g["families"]}
    assert all(i < len(lst) - len(win11) for i, f in enumerate(lst) if f in every)


def _gen(seed, locale=None, pv=None):
    tz = "UTC" if locale else None  # not every tag has a locale_zones row
    return gen.generate(os="windows", seed=seed, locale=locale, timezone=tz, host_platform_version=pv, host_renderer=None,
                        host_cores=12, host_cpu_vendor=None)["config"]


def _packs(lst):
    return {n for n, g in SUP.items() if set(g["families"]) <= set(lst)}


def test_locale_pack_always_present():
    for tag, pack in (("ja-JP", "japanese"), ("ko-KR", "korean"), ("zh-TW", "chinese_traditional"),
                      ("zh-CN", "chinese_simplified"), ("th-TH", "thai"), ("he-IL", "hebrew"), ("ar-SA", "arabic"),
                      ("bn-BD", "bangla")):
        for s in range(1, 41):
            assert pack in _packs(_gen(s, tag)["fonts:list"]), (tag, s)


def test_never_more_than_one_non_matching_pack():
    for tag, own in (("en-US", None), ("ja-JP", "japanese"), ("vi-VN", None), ("th-TH", "thai")):
        for s in range(1, 121):
            assert len(_packs(_gen(s, tag)["fonts:list"]) - {own}) <= 1, (tag, s)


def test_with_locale_pack_keeps_name_order_before_win11():
    win11 = W["win11"]["families"]
    for s in range(1, 41):
        lst = _gen(s, "ja-JP", "19.0.0")["fonts:list"]
        assert lst[-len(win11):] == win11
        body = lst[:-len(win11)]
        assert _tail({"fonts:list": body}) == [f for n in sorted(_packs(body)) for f in SUP[n]["families"]], s


def test_with_locale_pack_idempotent_and_absent_list():
    lst = _gen(3, "ja-JP")["fonts:list"]
    assert gen.with_locale_pack(lst, "ja-JP") == lst
    assert gen.with_locale_pack(None, "ja-JP") is None
    assert gen.with_locale_pack(lst, "vi-VN") == lst

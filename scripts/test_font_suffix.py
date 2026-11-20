"""Chromium's Windows weight/stretch suffix fallback, mirrored for the fonts:list gate
(specs/2026-11-20-font-weight-suffix-gate-design.md): the tables, the generator invariant, the F6 judges."""
import copy
import json
import os
import pathlib
import re
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import font_suffix as fs  # noqa: E402

FONTS = json.loads((HERE.parent / "settings" / "fonts.json").read_text(encoding="utf-8"))


def test_strip_follows_chromium_order():
    assert fs.strip_suffix("Arial Medium") == "Arial"
    assert fs.strip_suffix("Foo ExtraLight") == "Foo"  # " extralight" before " light"
    assert fs.strip_suffix("Bahnschrift Light Condensed") == "Bahnschrift Light"  # no weight suffix: stretch
    assert fs.strip_suffix("Arial Light Medium") == "Arial Light"  # one suffix only
    assert fs.strip_suffix("arial NARROW") == "arial"
    assert fs.strip_suffix("Arial Bold") is None and fs.strip_suffix("Segoe UI Semilight") is None
    assert fs.strip_suffix("Arial") is None


def test_generator_invariant_holds():
    assert fs.collisions(FONTS) == []


def test_invariant_catches_a_planted_collision():
    planted = copy.deepcopy(FONTS)
    planted["families"]["Windows"]["groups"]["planted"] = {"families": ["Calibri Medium"], "p": 0.5}
    assert fs.collisions(planted) == [("Windows", "Calibri Medium", "Calibri")]
    other = copy.deepcopy(FONTS)  # a base in a different optional group
    other["families"]["Windows"]["groups"]["planted"] = {"families": ["Cascadia Code Heavy"], "p": 0.5}
    assert fs.collisions(other) == [("Windows", "Cascadia Code Heavy", "Cascadia Code")]
    never = copy.deepcopy(FONTS)  # captured, in neither base nor a group: every draw hides it
    never["families"]["Windows"]["list"].append("Calibri Medium")
    assert fs.collisions(never) == [("Windows", "Calibri Medium", "Calibri")]
    win11 = copy.deepcopy(FONTS)
    win11["families"]["Windows"]["win11"]["families"].append("Segoe UI Black")
    assert fs.collisions(win11) == [("Windows", "Segoe UI Black", "Segoe UI")]
    sup = copy.deepcopy(FONTS)
    sup["families"]["Windows"]["supplemental"]["japanese"]["families"].append("Calibri Light")
    assert fs.collisions(sup) == [("Windows", "Calibri Light", "Calibri")]


def _cpp_tables(src):
    out = []
    for name in ("kWeightSuffixes", "kStretchSuffixes"):
        body = re.search(name + r"\[\][^{]*\{(.*?)\};", src, re.S)[1]
        out.append(re.findall(r'"( [a-z]+)"', body))
    return out


def test_tables_match_the_camoucfg_copy():
    src = (HERE.parent / "additions" / "camoucfg" / "mask_config.cc").read_text(encoding="utf-8")
    assert _cpp_tables(src) == [list(fs.WEIGHT_SUFFIXES), list(fs.STRETCH_SUFFIXES)]


@pytest.mark.skipif(not os.environ.get("CAMOU_CHROMIUM_SRC"), reason="needs a Chromium tree (re-pin check)")
def test_tables_match_chromium():
    f = pathlib.Path(os.environ["CAMOU_CHROMIUM_SRC"]) / "third_party/blink/renderer/platform/fonts/win/font_cache_skia_win.cc"
    tables = re.findall(r"kVariantForSuffix\[\] = \{(.*?)\};", f.read_text(encoding="utf-8"), re.S)
    assert [re.findall(r'\{"( [a-z]+)"', t) for t in tables] == [list(fs.WEIGHT_SUFFIXES), list(fs.STRETCH_SUFFIXES)]


def _r(**widths):
    """A measure() result: resolved names have widths unlike the bare fallbacks."""
    base = {"__mono": 1000.0, "__serif": 1100.0, "__narrow": 900.0, "__arial": 900.0}
    base.update({k.replace("_", " "): v for k, v in widths.items()})
    return base


def _resolved(r, fam):
    mono, serif = r[fam]
    return abs(mono - r["__mono"]) > 1 or abs(serif - r["__serif"]) > 1


HIT, MISS = [1300.0, 1300.0], [1000.0, 1100.0]


def test_f6a():
    names = ["Arial Medium", "Segoe UI Thin"]
    both = _r(Arial_Medium=HIT, Segoe_UI_Thin=HIT)
    assert fs.f6a(both, both, both, names, _resolved)
    assert not fs.f6a(_r(Arial_Medium=MISS, Segoe_UI_Thin=HIT), both, both, names, _resolved)  # today's fork
    assert not fs.f6a(both, both, _r(Arial_Medium=MISS, Segoe_UI_Thin=HIT), names, _resolved)  # stock premise
    assert not fs.f6a(None, both, both, names, _resolved)


def test_f6b():
    hidden, shown = _r(ROG_Fonts_Medium=MISS), _r(ROG_Fonts_Medium=HIT)
    assert fs.f6b(hidden, hidden, shown, "ROG Fonts Medium", _resolved)
    assert not fs.f6b(shown, hidden, shown, "ROG Fonts Medium", _resolved)  # the mutant: strip without the list
    assert not fs.f6b(hidden, hidden, hidden, "ROG Fonts Medium", _resolved)  # host lacks it: proves nothing


def test_f6c():
    real_narrow = _r(Arial_Narrow=HIT) | {"__narrow": 800.0, "__arial": 900.0}
    assert fs.f6c(real_narrow | {"__narrow": 900.0}, real_narrow, ["Arial"], _resolved) is True
    assert fs.f6c(real_narrow, real_narrow, ["Arial"], _resolved) is False  # the fork reaches the real face
    assert fs.f6c(real_narrow, _r(Arial_Narrow=MISS), ["Arial"], _resolved) is None  # host lacks it
    assert fs.f6c(real_narrow, real_narrow, ["Arial", "Arial Narrow"], _resolved) is None  # the list shows it
    assert fs.f6c(real_narrow, real_narrow | {"__narrow": 900.0}, ["Arial"], _resolved) is None  # no distinct face


def test_f6d():
    blocked, shown = _r(Arial_Medium=MISS), _r(Arial_Medium=HIT)
    assert fs.f6d(blocked, blocked, shown, "Arial Medium", _resolved)  # a macOS claim keeps the exact match
    assert not fs.f6d(shown, blocked, shown, "Arial Medium", _resolved)  # the mutant without the claim check
    assert not fs.f6d(blocked, blocked, blocked, "Arial Medium", _resolved)  # stock premise


def test_f6c_reference_is_plain_arial():
    # ctx.font re-derives font-stretch from its shorthand (canvas_rendering_context_2d_state.cc SetFont), so a
    # fontStretch set before it measures nothing; the reference is what stock's suffix path renders: Arial
    src = (HERE / "verify_windows_fonts.py").read_text(encoding="utf-8")
    assert "fontStretch" not in src and "out.__arial = w('100px Arial, monospace', TEXT);" in src

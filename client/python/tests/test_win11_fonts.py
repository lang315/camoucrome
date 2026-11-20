"""A Windows 11 host's identity lists the Windows 11 families (specs/2026-11-20-win11-host-fonts-design.md):
UA-CH carries the host's platformVersion, and CreepJS dates Windows by fonts ('11': ['Segoe Fluent Icons'])."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camoucrome import gen  # noqa: E402

WIN11 = ["Segoe Fluent Icons", "Segoe UI Variable Display", "Segoe UI Variable Text", "Segoe UI Variable Small",
         "Nirmala Text", "Sans Serif Collection"]
HOST = dict(host_renderer=None, host_cores=12, host_cpu_vendor=None)


def _config(pv, os="windows", seed=7):
    return gen.generate(os=os, seed=seed, host_platform_version=pv, **HOST)["config"]


def test_fonts_json_holds_the_win11_set():
    w = json.loads((gen.ROOT / "settings/fonts.json").read_text(encoding="utf-8"))["families"]["Windows"]["win11"]
    assert w["min_platform_major"] == 13 and w["families"] == WIN11 and w["how"]


def test_win11_host_lists_the_win11_families():
    for pv in ("19.0.0", "13.0.0"):
        c = _config(pv)
        assert c["ua:platformVersion"] == pv
        assert set(WIN11) <= set(c["fonts:list"]), pv


def test_win10_or_unknown_host_lists_none_of_them():
    for pv in ("12.0.0", "10.0.0", None, "bad"):
        assert not set(WIN11) & set(_config(pv)["fonts:list"]), pv


def test_win11_families_never_reach_fonts_local():
    # queryLocalFonts faces need a stock capture (approach B): the claim lists no face it cannot back
    c = _config("19.0.0")
    assert not [f for f in c.get("fonts:local", []) if f.split("\t")[2] in WIN11]


def test_listed_once_even_when_the_capture_gains_them(monkeypatch):
    # a later capture (approach B) may already list a Windows 11 family: it stays listed once
    real = gen.fonts_keys
    monkeypatch.setattr(gen, "fonts_keys", lambda *a, **k: {**real(*a, **k), "fonts:list": real(*a, **k)["fonts:list"] + [WIN11[0]]})
    c = _config("19.0.0")
    assert c["fonts:list"].count(WIN11[0]) == 1 and set(WIN11) <= set(c["fonts:list"])


def test_win11_set_is_appended_and_the_rest_is_unchanged():
    a, b = _config("10.0.0"), _config("19.0.0")
    assert b["fonts:list"] == a["fonts:list"] + WIN11
    assert {k: v for k, v in a.items() if k not in ("fonts:list", "ua:platformVersion")} == \
           {k: v for k, v in b.items() if k not in ("fonts:list", "ua:platformVersion")}


def test_non_windows_claim_keeps_its_own_version_and_fonts():
    c = _config("19.0.0", os="macos")
    assert c["ua:platformVersion"] != "19.0.0" and not set(WIN11) & set(c["fonts:list"])


def test_a_windows_recapture_carries_the_win11_block():
    sys.path.insert(0, str(gen.ROOT / "scripts"))
    import capture_fonts_list  # noqa: PLC0415
    assert "win11" in capture_fonts_list.CARRIED

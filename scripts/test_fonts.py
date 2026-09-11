import json
import pathlib
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gen_fontconfig as g  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONTS = json.loads((ROOT / "settings" / "fonts.json").read_text())


def test_every_bundle_entry_is_ofl_with_a_licence_and_sha():
    for b in FONTS["bundle"]:
        assert b["licence"] == "SIL OFL 1.1" and b["licence_url"].startswith("https://"), b["name"]
        if "urls" in b:
            assert len(b["sha256"]) == len(b["urls"]) == len(b["files"]) and all(len(x) == 64 for x in b["sha256"]), b["name"]
        else:
            assert len(b["sha256"]) == 64 and b["url"].startswith("https://"), b["name"]


def test_alias_target_by_explicit_then_class_then_sans():
    assert g.alias_target(FONTS, "Windows", "Segoe UI") == "Selawik"
    assert g.alias_target(FONTS, "Windows", "Yu Gothic") == "Noto Sans CJK SC"
    assert g.alias_target(FONTS, "Windows", "Georgia") == "Liberation Serif"
    assert g.alias_target(FONTS, "Windows", "Some Unknown Family") == "Selawik"
    assert g.alias_target(FONTS, "macOS", "Some Unknown Family") == "Inter Variable"


def test_xml_is_strong_relative_and_covers_every_captured_family():
    bundled = {f for b in FONTS["bundle"] for f in b["provides"]}
    for os_name in ("Windows", "macOS"):
        root = ET.fromstring(g.fontconfig_xml(FONTS, os_name))
        d = root.find("dir")
        assert d.get("prefix") == "relative" and d.text == "../../fonts"
        assert root.find("cachedir").get("prefix") == "xdg"
        aliases = {a.find("family").text: a for a in root.findall("alias")}
        assert all(a.get("binding") == "strong" for a in aliases.values())
        for fam in FONTS["families"][os_name]["list"]:
            assert fam in aliases or fam in bundled, fam
        assert "sans-serif" in aliases and "system-ui" in aliases
        assert all(a.find("prefer/family").text in bundled for a in aliases.values())


def test_captured_lists_have_provenance_and_no_excluded_vendor_font():
    for os_name in ("Windows", "macOS"):
        f = FONTS["families"][os_name]
        assert f["captured"] and f["how"] and len(f["list"]) > 100
        assert not set(f["list"]) & set(FONTS["families"]["exclude"])


def test_checked_in_confs_match_the_generator():
    for os_name, f in (("Windows", "windows.conf"), ("macOS", "macos.conf")):
        assert (ROOT / "settings" / "fontconfig" / f).read_text() == g.fontconfig_xml(FONTS, os_name)

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
        assert b["licence"] in ("SIL OFL 1.1", "LGPL 2.1+") and b["licence_url"].startswith("https://"), b["name"]
        if "urls" in b:
            assert len(b["sha256"]) == len(b["urls"]) == len(b["files"]) and all(len(x) == 64 for x in b["sha256"]), b["name"]
        else:
            assert len(b["sha256"]) == 64 and b["url"].startswith("https://"), b["name"]


def test_alias_target_by_explicit_then_class_then_sans():
    assert g.alias_target(FONTS, "Windows", "Segoe UI") == "Selawik"
    assert g.alias_target(FONTS, "Windows", "Yu Gothic") == "Noto Sans CJK JP"
    assert g.alias_target(FONTS, "Windows", "Microsoft YaHei") == "Noto Sans CJK SC"
    assert g.alias_target(FONTS, "macOS", "PingFang HK") == "Noto Sans CJK HK"
    assert g.alias_target(FONTS, "Windows", "Malgun Gothic") == "Noto Sans CJK KR"
    assert g.alias_target(FONTS, "Windows", "Georgia") == "Gelasio"
    assert g.alias_target(FONTS, "Windows", "Tahoma") == "Tahoma"  # Wine's file is named Tahoma: no alias
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


def test_alias_map_covers_every_captured_family_with_a_bundled_target_and_no_identity():
    bundled = {f for b in FONTS["bundle"] for f in b["provides"]}
    for os_name in ("Windows", "macOS"):
        m = g.alias_map(FONTS, os_name)
        assert m == FONTS["alias_map"][os_name]  # generated section is current
        for fam in FONTS["families"][os_name]["list"]:
            assert fam in m or fam in bundled, fam
        assert all(v in bundled and k != v for k, v in m.items())
        assert m["system-ui"] in bundled and "sans-serif" in m


def test_every_cjk_family_sits_in_exactly_one_region_with_a_target():
    regions = [k for k in FONTS["script_class"] if k.startswith("cjk_")]
    assert sorted(regions) == ["cjk_hk", "cjk_jp", "cjk_kr", "cjk_sc", "cjk_tc"]
    seen = [f for k in regions for f in FONTS["script_class"][k]]
    assert len(seen) == len(set(seen)) == 69
    bundled = {f for b in FONTS["bundle"] for f in b["provides"]}
    for os_name in ("Windows", "macOS"):
        assert all(FONTS["class_font"][os_name][k] in bundled for k in regions)


def test_a_bundled_family_named_like_the_claim_is_never_an_alias_key():
    for os_name in ("Windows", "macOS"):
        assert "Tahoma" not in FONTS["alias_map"][os_name] and "Tahoma" in FONTS["families"][os_name]["list"]


def test_unique_names_map_onto_a_bundled_face_of_the_same_style():
    m = FONTS["unique_map"]["Windows"]
    assert m == g.unique_map(FONTS, "Windows")
    assert m["SegoeUI"] == "Selawik" and m["SegoeUI-Bold"] == "Selawik Bold"
    assert m["ArialMT"] == "Liberation Sans" and m["Arial-BoldMT"] == "Liberation Sans Bold"
    assert m["Tahoma-Bold"] == "Tahoma Bold" and "Tahoma" not in m  # Wine's file carries the host's own names
    bundled_full = {f["full"] for b in FONTS["bundle"] for f in b["faces"]}
    assert set(m.values()) <= bundled_full
    for os_name in ("Windows", "macOS"):
        names = FONTS["families"][os_name]["unique_names"]
        assert len(names) > 100 and all(v["family"] in FONTS["families"][os_name]["list"] for v in names.values())
        # a bundle face's full name is a host name only for a bundled file carrying the claimed name (Wine's Tahoma)
        own = {f["full"] for b in FONTS["bundle"] if set(b["provides"]) & set(FONTS["families"][os_name]["list"]) for f in b["faces"]}
        assert set(names) & bundled_full <= own


def test_every_bundle_entry_records_its_faces():
    for b in FONTS["bundle"]:
        assert b["faces"] and set(b["provides"]) <= {f["family"] for f in b["faces"]}, b["name"]  # legacy families (Selawik Light) may add more

"""install-font-packs.ps1 installs exactly the Windows FoD packs settings/fonts.json draws from,
and holds the Japanese and Korean packs behind -IncludeJapaneseKorean (a build before #233
renders a hidden Jpan/Kore family through the lang=ja/ko generics)."""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = (ROOT / "scripts" / "windows" / "install-font-packs.ps1").read_text()
CAPABILITY = re.compile(r"Language\.Fonts\.\w+~~~und-\w+~0\.0\.1\.0")


def manifest():
    packs = json.loads((ROOT / "settings" / "fonts.json").read_text())["families"]["Windows"]["supplemental"]
    return {p["capability"] for p in packs.values()}


def test_script_names_every_manifest_pack_and_nothing_else():
    assert set(CAPABILITY.findall(SCRIPT)) == manifest()


def test_japanese_and_korean_are_the_gated_packs():
    gated = [line for line in SCRIPT.splitlines() if line.lstrip().startswith("$gated")]
    assert len(gated) == 1
    assert set(CAPABILITY.findall(gated[0])) == {
        "Language.Fonts.Jpan~~~und-JPAN~0.0.1.0",
        "Language.Fonts.Kore~~~und-KORE~0.0.1.0",
    }

"""gen_go_core_data.py: the compact pool, the country table and the --check gate. Draw tests need the pinned
BrowserForge and datapoints (a venv; without them those tests skip and say why); the rest need nothing."""
import gzip
import json
import pathlib
import shutil
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gen_go_core_data as g  # noqa: E402

ROOT = g.ROOT
SOURCE = json.loads((ROOT / "settings" / "country_locale.json").read_text(encoding="utf-8"))


def need_pins():
    try:
        g.check_pins()
    except SystemExit as e:
        pytest.skip(str(e))


def test_compact_entry_rebuilds():
    need_pins()
    from camoucrome import gen
    fonts = g.fonts_subset()
    for seed in range(1, 21):
        out = gen.generate(g.OS, seed=seed, host_cores=1024)
        cfg = out["config"]
        entry = g.compact(out, fonts)
        groups = entry.pop("fontGroups")
        assert entry.pop("dpr") == out["launch"]["dpr"]
        # the entry is the config minus the excluded keys ...
        assert entry == {k: v for k, v in cfg.items() if not g.excluded(k)}
        # ... and the font keys come back from the groups
        for k, v in g.rebuild_fonts(fonts, groups).items():
            assert cfg[k] == v, (seed, k)
        assert not any(k.startswith("webgl:") for k in cfg)  # no host renderer: gen claims no GPU


def test_country_table_covers_iso():
    t = json.loads((g.DATA / "country_locale.json").read_text(encoding="utf-8"))
    assert len(t) >= 240
    for code, tag in {"TH": "th-TH", "ID": "id-ID", "PH": "fil-PH", "CA": "en-CA", "US": "en-US"}.items():
        assert t[code] == tag
    zones = json.loads((ROOT / "settings" / "locale_zones.json").read_text(encoding="utf-8"))["zones"]
    assert t["CH"] == next(z for z in zones if z.endswith("-CH"))
    assert not any(v.startswith("und") for v in t.values())


def test_country_rule_from_cldr_shapes():
    likely = {"und-KE": "sw-Latn-KE", "und-AQ": "und-Latn-AQ"}
    terr = {"KE": {}, "AQ": {}, "CA": {"languagePopulation": {"fr": {"_populationPercent": "29", "_officialStatus": "official"},
                                                           "en": {"_populationPercent": "87", "_officialStatus": "official"},
                                                           "es": {"_populationPercent": "99"}}},
            "EU": {}, "NN": {"languagePopulation": {"iu_Latn": {"_populationPercent": "1"}}}}
    assert g.country_locale_from_cldr(likely, terr) == {"CA": "en-CA", "NN": "iu-NN", "KE": "sw-KE"}


def test_committed_files_are_fresh_without_the_pool():
    assert g.check(SOURCE, g.DATA, no_pool=True) == 0


def test_committed_pool_is_fresh():
    need_pins()
    assert g.check(SOURCE, g.DATA) == 0


def test_check_detects_drift(tmp_path):
    need_pins()
    g.write_all(20, SOURCE, tmp_path)
    assert g.check(SOURCE, tmp_path) == 0
    # one byte of a copied data file
    p = tmp_path / "voices.json"
    p.write_text(p.read_text(encoding="utf-8").replace("Microsoft", "Microsofu", 1), encoding="utf-8")
    assert g.check(SOURCE, tmp_path, no_pool=True) == 1
    g.write_all(20, SOURCE, tmp_path)
    # one value of one pool entry
    pool = g.read_pool(tmp_path / "pool-windows.json.gz")
    pool["entries"][3]["navigator.maxTouchPoints"] += 1
    with gzip.open(tmp_path / "pool-windows.json.gz", "wb") as f:
        f.write(g.dumps(pool).encode())
    assert g.check(SOURCE, tmp_path) == 1


def test_stale_missing_file_is_reported(tmp_path):
    shutil.copytree(g.DATA, tmp_path / "d")
    (tmp_path / "d" / "fonts.json").unlink()
    assert g.check(SOURCE, tmp_path / "d", no_pool=True) == 1


def test_pins_are_enforced(monkeypatch):
    monkeypatch.setitem(g.PINS, "browserforge", "0.0.0")
    with pytest.raises(SystemExit):
        g.check_pins()


def test_no_host_data():
    terms = pathlib.Path.home() / ".config" / "camoucrome" / "private-terms.json"
    if not terms.exists():
        pytest.skip("no private-terms.json on this machine")
    strings = [s for v in json.loads(terms.read_text()).values() for s in v if s]
    for p in g.DATA.iterdir():
        if p.name in ("voices.json", "locale_zones.json"):  # product data, ALLOW_PATHS in check_privacy.py
            continue
        text = (gzip.open(p, "rt", encoding="utf-8").read() if p.suffix == ".gz" else p.read_text(encoding="utf-8")).lower()
        for s in strings:
            assert s.lower() not in text, f"{p.name} holds a private term"

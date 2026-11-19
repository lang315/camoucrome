"""gen_gpu_architectures.py: Dawn's gpu_info.json -> settings/webgl/gpu-architectures.json, and what the committed table says
for the ids the project measured. No test reads the machine's GPU."""
import json
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gen_gpu_architectures as g  # noqa: E402

ROOT = g.ROOT
SCRIPT = pathlib.Path(g.__file__)

# Dawn's own shape: "_" keys are comments, a set has an optional mask (none = exact), internal sets are never reported.
FIXTURE = {
    "_comment": ["licence text"],
    "vendors": {
        "_Example Vendor": {"id": "0xDEAD", "devices": [{"architecture": {"Alpha": ["0x0A01"]}}]},
        "Intel": {"id": "0x8086", "devices": [{"mask": "0xFF00", "architecture": {"Gen 9": ["0x9B00", "0x3E00"], "Gen 12 LP": ["0x9A00"]}}]},
        "Nvidia": {"id": "0x10DE", "devices": [{"mask": "0xFFFFFF00", "architecture": {"Ampere": ["0x2500"], "Lovelace": ["0x2600"]}}]},
        "AMD": {"id": "0x1002", "devices": [
            {"mask": "0xFFF0", "architecture": {"RDNA 2": ["0x73B0", "0x13c0"]}},
            {"_comment": "exact ids", "mask": "0xFFFF", "architecture": {"RDNA 2": ["0x163F"], "GCN 5": ["0x1636"]}},
            {"internal": True, "mask": "0xFFF0", "architecture": {"Internal Only": ["0x73B0"]}}]},
        "Apple": {"id": "0x106b"},
    },
}


def test_extraction_builds_vendor_mask_id_architecture(tmp_path):
    t = g.build(FIXTURE, "rev")
    assert set(t["vendors"]) == {"intel", "nvidia", "amd"}  # a comment vendor and one with no devices are left out
    assert t["vendors"]["intel"]["id"] == "0x8086"
    assert t["vendors"]["intel"]["sets"] == [{"mask": "0xFF00", "ids": {"0x9B00": "gen-9", "0x3E00": "gen-9", "0x9A00": "gen-12-lp"}}]
    # internal sets are never reported by adapter.info, so they are not in the table
    assert "internal-only" not in json.dumps(t)
    assert t["dawn"]["revision"] == "rev" and "BSD-3-Clause" in t["dawn"]["licence"]


def test_lookup_applies_the_mask_and_the_exact_set():
    t = g.build(FIXTURE, "rev")
    assert g.architecture(t, "Intel", 0x9B41) == "gen-9" and g.architecture(t, "Intel", 0x9BC5) == "gen-9"  # masked
    assert g.architecture(t, "NVIDIA", 0x2504) == "ampere" and g.architecture(t, "NVIDIA", 0x2684) == "lovelace"
    assert g.architecture(t, "AMD", 0x73BF) == "rdna-2" and g.architecture(t, "AMD", 0x13C5) == "rdna-2"  # lower-case id in the source
    assert g.architecture(t, "AMD", 0x163F) == "rdna-2" and g.architecture(t, "AMD", 0x1636) == "gcn-5"  # exact set
    assert g.architecture(t, "AMD", 0x1637) is None  # same family prefix, not in any set
    assert g.architecture(t, "Intel", 0xFFFF) is None and g.architecture(t, "Matrox", 0x1) is None


def test_overlapping_sets_with_two_architectures_are_refused():
    bad = {"vendors": {"Intel": {"id": "0x8086", "devices": [{"mask": "0xFF00", "architecture": {"A": ["0x9B00"]}},
                                                              {"mask": "0xFFFF", "architecture": {"B": ["0x9B41"]}}]}}}
    with pytest.raises(ValueError, match="overlap"):
        g.build(bad, "rev")


def test_check_mode_passes_on_fresh_and_fails_on_stale(tmp_path):
    src, out = tmp_path / "gpu_info.json", tmp_path / "out.json"
    src.write_text(json.dumps(FIXTURE))
    run = lambda *a: subprocess.run([sys.executable, str(SCRIPT), str(src), "--out", str(out), "--revision", "rev", *a],
                                    capture_output=True, text=True)
    assert run("--check").returncode == 1  # no file yet
    assert run().returncode == 0 and run("--check").returncode == 0
    out.write_text(out.read_text().replace("gen-9", "gen-8", 1))
    r = run("--check")
    assert r.returncode == 1 and "stale" in r.stdout


# The committed table: the two measured points (0x9B41 on 2026-11-19, 0x9BC5 on 2026-11-04) read gen-9 in adapter.info.
COMMITTED = json.loads((ROOT / "settings" / "webgl" / "gpu-architectures.json").read_text(encoding="utf-8"))


def test_committed_table_matches_the_measured_points_and_the_families():
    a = lambda v, d: g.architecture(COMMITTED, v, d)
    assert a("Intel", 0x9B41) == "gen-9" and a("Intel", 0x9BC5) == "gen-9"
    assert a("Intel", 0x3E92) == "gen-9" and a("Intel", 0x5917) == "gen-9"
    assert a("Intel", 0x9A49) == "gen-12-lp"
    assert a("NVIDIA", 0x2504) == "ampere"  # RTX 3060
    assert a("NVIDIA", 0x2684) == "lovelace"  # RTX 4090 (Ada)
    assert a("AMD", 0x73BF) == "rdna-2"  # RX 6800 XT, masked 0x73B0
    assert a("AMD", 0x163F) == "rdna-2" and a("AMD", 0x1636) == "gcn-5"  # exact set
    assert COMMITTED["dawn"]["revision"] == g.DAWN_REVISION


def test_every_gen9_pool_id_is_gen9_in_dawn():
    ids = json.loads((ROOT / "settings" / "webgl" / "intel-gen9-pool.json").read_text(encoding="utf-8"))["device_ids"]
    assert ids and all(g.architecture(COMMITTED, "Intel", d) == "gen-9" for d in ids)

"""A Gen9 identity drawn per seed must not claim more threads than that GPU ships with (rule 4)."""
import json
import pathlib
import random
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camoucrome import gen  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[3]
CAPS = json.loads((ROOT / "settings" / "webgl" / "intel-gen9-thread-caps.json").read_text(encoding="utf-8"))
HOST = "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00009BC5) Direct3D11 vs_5_0 ps_5_0, D3D11)"
SEEDS = range(1, 201)
CAP_OF = {int(r["device_id"], 16): r["max_threads"] for r in CAPS["rows"]}


def swap(seed, host=HOST):
    return gen.generate("windows", "Europe/Paris", None, seed, host_renderer=host)["config"]


def test_caps_file_covers_the_pool_and_every_sourced_row_cites_ark():
    assert set(CAP_OF) == {r["device_id"] for r in gen.gen9_pool()["renderers"]}
    sourced = [r for r in CAPS["rows"] if r["max_threads"] is not None]
    assert sourced
    for r in sourced:
        assert type(r["max_threads"]) is int and 2 <= r["max_threads"] <= 20
        assert r["source_url"].startswith("https://www.intel.com/")
    assert [r["device_id"] for r in CAPS["rows"] if r["max_threads"] is None] == ["0x5921"]


def test_caps_file_is_not_a_webgl_profile():
    assert not any(stem.endswith("-thread-caps") for stem in gen.load_profiles())


def test_unsourced_renderer_is_never_drawn_and_still_recognised():
    drawn = {gen.gen9_device_id(gen.gpu_for("Windows", HOST, random.Random(s))[0]["renderer"]) for s in range(500)}
    assert 0x5921 not in drawn and len(drawn) > 3
    assert 0x5921 in gen.gen9_pool()["device_ids"]
    assert gen.gen9_thread_cap("ANGLE (Intel, Intel(R) HD Graphics 620 (0x00005921) Direct3D11 vs_5_0 ps_5_0, D3D11)") is None
    assert gen.gen9_thread_cap("ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002504) Direct3D11 vs_5_0 ps_5_0, D3D11)") is None


def test_threads_never_exceed_the_drawn_gpus_cap():
    for s in SEEDS:
        cfg = swap(s)
        assert cfg["navigator.hardwareConcurrency"] <= CAP_OF[gen.gen9_device_id(cfg["webGl:renderer"])], s


def test_compatible_old_values_are_untouched():
    kept = 0
    for s in SEEDS:
        old = gen.generate("windows", "Europe/Paris", None, s)["config"]["navigator.hardwareConcurrency"]
        new = swap(s)
        if old <= CAP_OF[gen.gen9_device_id(new["webGl:renderer"])]:
            assert new["navigator.hardwareConcurrency"] == old, s
            kept += 1
    assert kept > 20


def test_check_can_fail_when_the_cap_lookup_is_dead(monkeypatch):
    monkeypatch.setattr(gen, "gen9_thread_cap", lambda renderer: None)
    assert any(swap(s)["navigator.hardwareConcurrency"] > CAP_OF[gen.gen9_device_id(swap(s)["webGl:renderer"])] for s in SEEDS)


PINNED = {
    1: (2543, 577090038, 2444712011, 3639700192),
    2: (1015, 4106135924, 3707026330, 4070888060),
    3: (1167, 1022050302, 2545373331, 2337446731),
}


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_seeded_keys_do_not_move(seed):
    cfg = swap(seed)
    assert tuple(cfg[k] for k in ("share:cancelMs", "canvas:seed", "audio:seed", "mediaDevices:seed")) == PINNED[seed]


def test_swap_path_is_deterministic():
    assert swap(7) == swap(7)


def test_redraw_does_not_advance_the_callers_rng():
    from dataclasses import asdict
    from browserforge.fingerprints import FingerprintGenerator
    random.seed(3)
    sample = asdict(FingerprintGenerator(browser="chrome", os="windows").generate())

    def run(threads):
        fp = json.loads(json.dumps(sample))
        fp["navigator"]["hardwareConcurrency"] = threads
        rng = random.Random(5)
        cfg = gen.from_pool(fp, "Europe/Paris", rng=rng, host_renderer=HOST)["config"]
        return cfg["navigator.hardwareConcurrency"], rng.getstate()

    redrawn, after_redraw = run(64)  # above every cap: the redraw runs
    kept, after_kept = run(2)        # at or below every cap: no redraw
    assert kept == 2 and redrawn in (2, 4, 6, 8, 12, 16, 20) and redrawn != 64
    assert after_redraw == after_kept


@pytest.mark.parametrize("host", [None, "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002504) Direct3D11 vs_5_0 ps_5_0, D3D11)"])
def test_no_gen9_host_leaves_the_drawn_threads(host):
    for s in range(1, 30):
        base = gen.generate("windows", "Europe/Paris", None, s)["config"]["navigator.hardwareConcurrency"]
        assert swap(s, host)["navigator.hardwareConcurrency"] == base

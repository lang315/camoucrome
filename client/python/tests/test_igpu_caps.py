"""A claimed non-Gen9 iGPU must not claim more threads than that part ships with (rule 4); an unsourced id is never drawn."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camoucrome import gen  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[3]
CAPS = json.loads((ROOT / "settings" / "webgl" / "igpu-thread-caps.json").read_text(encoding="utf-8"))
CAP_OF = {(r["vendor"], int(r["device_id"], 16)): r["max_threads"] for r in CAPS["rows"] if r["max_threads"] is not None}
SEEDS = range(1, 2001)
THREAD_CAP = gen.thread_cap  # the real lookup, kept apart from the RED test's monkeypatch
INTEL = "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics (0x%08X) Direct3D11 vs_5_0 ps_5_0, D3D11)"
AMD = "ANGLE (AMD, AMD Radeon(TM) Graphics (0x%08X) Direct3D11 vs_5_0 ps_5_0, D3D11)"


def draw(seed):
    return gen.generate("windows", "Europe/Paris", None, seed, host_cores=64)["config"]


def claimed():
    out = []
    for s in SEEDS:
        cfg = draw(s)
        if gen.gpu_class(cfg["webGl:renderer"]) in ("igpu", "igpu-gen9"):  # every claimed iGPU, Gen9 included
            out.append(cfg)
    return out


def cap_for(cfg):
    cap = THREAD_CAP(cfg["webGl:renderer"])
    assert cap is not None, cfg["webGl:renderer"]
    return cap


def test_every_row_is_sourced_and_ids_do_not_overlap_gen9():
    assert CAPS["rows"]
    gen9 = set(gen.gen9_pool()["device_ids"])
    for r in CAPS["rows"]:
        assert r["vendor"] in ("Intel", "AMD"), r
        if r["max_threads"] is None:
            continue
        assert type(r["max_threads"]) is int and 2 <= r["max_threads"] <= 64, r
        assert r["source_url"].startswith("https://"), r
        assert not (r["vendor"] == "Intel" and int(r["device_id"], 16) in gen9), r


def test_a_sourced_id_is_igpu_and_an_unsourced_one_is_not_drawable():
    (vendor, dev), cap = next(iter(CAP_OF.items()))
    r = (INTEL if vendor == "Intel" else AMD) % dev
    assert gen.gpu_class(r) == "igpu" and gen.thread_cap(r) == cap
    for bad in (INTEL % 0x7D99, AMD % 0x9999, INTEL % 0x8A5D, AMD % 0x1681):  # the last two are listed with max_threads null
        assert gen.gpu_class(bad) is None and gen.thread_cap(bad) is None
    # the vendor is part of the key: an AMD string never takes an Intel row's cap
    intel_id = next(d for (v, d) in CAP_OF if v == "Intel" and (("AMD", d) not in CAP_OF))
    assert gen.gpu_class(AMD % intel_id) is None


def test_threads_never_exceed_the_claimed_igpus_cap_over_2000_seeds():
    cfgs = claimed()
    assert len(cfgs) > 200
    for cfg in cfgs:
        assert cfg["navigator.hardwareConcurrency"] <= cap_for(cfg), cfg["webGl:renderer"]


def test_check_can_fail_when_the_cap_is_not_applied(monkeypatch):
    monkeypatch.setattr(gen, "thread_cap", lambda renderer: None)
    assert any(cfg["navigator.hardwareConcurrency"] > cap_for(cfg) for cfg in claimed())


def test_non_gen9_igpu_claim_is_webgpu_blocked_even_on_a_gen9_host():
    (vendor, dev) = next(iter(CAP_OF))
    r = (INTEL if vendor == "Intel" else AMD) % dev
    host = "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00009BC5) Direct3D11 vs_5_0 ps_5_0, D3D11)"
    assert gen.gpu_keys("x", r, host)["webGpu:blocked"] is True


FLOOR = gen.igpu_thread_floor  # the real lookup, kept apart from the RED test's monkeypatch
KEYS = gen.GPU_CLAIM_KEYS


def test_floors_are_within_caps():
    for r in CAPS["rows"]:
        if r["max_threads"] is not None and r.get("min_threads") is not None:
            assert 2 <= r["min_threads"] <= r["max_threads"], r


def test_threads_never_fall_below_the_claimed_igpus_floor_over_2000_seeds():
    n = 0
    for cfg in claimed():
        floor = FLOOR(cfg["webGl:renderer"])
        if floor:
            n += 1
            assert floor <= cfg["navigator.hardwareConcurrency"] <= cap_for(cfg), (cfg["webGl:renderer"], cfg["navigator.hardwareConcurrency"])
    assert n > 200


def test_floor_check_can_fail_when_the_floor_is_not_applied(monkeypatch):
    monkeypatch.setattr(gen, "igpu_thread_floor", lambda renderer: None)
    assert any(cfg["navigator.hardwareConcurrency"] < FLOOR(cfg["webGl:renderer"]) for cfg in claimed() if FLOOR(cfg["webGl:renderer"]))


def test_a_host_snap_below_the_floor_drops_the_five_gpu_keys():
    dropped = kept = 0
    for s in range(1, 301):
        big = gen.generate("windows", "Europe/Paris", None, s, host_cores=64)
        small = gen.generate("windows", "Europe/Paris", None, s, host_cores=4)  # same draw: the snap consumes no rng
        floor = FLOOR(big["config"]["webGl:renderer"]) if "webGl:renderer" in big["config"] else None
        assert all(k in big["config"] for k in KEYS)
        if floor and floor > 4:
            assert not any(k in small["config"] for k in KEYS), s
            assert small["config"]["navigator.hardwareConcurrency"] == 4
            assert any("GPU claim is dropped" in w for w in small["warnings"])
            dropped += 1
        else:
            assert all(k in small["config"] for k in KEYS), s
            kept += 1
    assert dropped > 20 and kept > 20


def test_an_arc_name_with_a_memory_label_is_not_drawable():
    for name, dev in (("Intel(R) Arc(TM) 140V GPU (16GB)", 0x64A0), ("Intel(R) Arc(TM) 140T GPU (32GB)", 0x7D51)):
        r = f"ANGLE (Intel, {name} (0x{dev:08X}) Direct3D11 vs_5_0 ps_5_0, D3D11)"
        assert gen.gpu_class(r) is None and gen.thread_cap(r) is None
    assert gen.gpu_class("ANGLE (Intel, Intel(R) Arc(TM) Graphics (0x00007D55) Direct3D11 vs_5_0 ps_5_0, D3D11)") == "igpu"


GEN9 = json.loads((ROOT / "settings" / "webgl" / "intel-gen9-thread-caps.json").read_text(encoding="utf-8"))
UHD620 = "ANGLE (Intel, Intel(R) UHD Graphics 620 (0x00003EA0) Direct3D11 vs_5_0 ps_5_0, D3D11)"


def test_gen9_floors_are_within_caps_and_looked_up_by_device_id():
    for r in GEN9["rows"]:
        if r["max_threads"] is not None and r.get("min_threads") is not None:
            assert 2 <= r["min_threads"] <= r["max_threads"], r
            assert r.get("min_note"), r
    assert FLOOR(UHD620) >= 4  # no CPU that ships UHD 620 has fewer than 4 threads
    # the name carries no model number: the floor is the device id's
    assert FLOOR("ANGLE (Intel, Intel(R) UHD Graphics (0x00009B41) Direct3D11 vs_5_0 ps_5_0, D3D11)") == FLOOR(
        "ANGLE (Intel, Intel(R) UHD Graphics 620 (0x00009B41) Direct3D11 vs_5_0 ps_5_0, D3D11)")


def test_uhd620_never_draws_fewer_threads_than_its_floor_over_many_seeds():
    n = 0
    for cfg in claimed():
        if cfg["webGl:renderer"] == UHD620:
            n += 1
            assert FLOOR(UHD620) <= cfg["navigator.hardwareConcurrency"] <= cap_for(cfg), cfg["navigator.hardwareConcurrency"]
    assert n > 5


def test_a_host_snap_below_a_gen9_floor_drops_the_claim():
    dropped = 0
    for s in range(1, 1001):
        big = gen.generate("windows", "Europe/Paris", None, s, host_cores=64)["config"]
        floor = FLOOR(big.get("webGl:renderer"))
        if not floor or floor <= 2 or gen.gpu_class(big["webGl:renderer"]) != "igpu-gen9":
            continue
        small = gen.generate("windows", "Europe/Paris", None, s, host_cores=2)
        assert not any(k in small["config"] for k in KEYS), s
        assert any("GPU claim is dropped" in w for w in small["warnings"])
        dropped += 1
    assert dropped > 5


def test_go_floors_table_is_every_sourced_floor_of_both_files():
    import importlib.util
    spec = importlib.util.spec_from_file_location("gen_go_core_data", ROOT / "scripts" / "gen_go_core_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    want = {f"{v}:0x{d:08X}": t for (v, d), t in gen._igpu_floors().items()}
    want.update({f"Intel:0x{d:08X}": t for d, t in gen._gen9_floors().items()})
    assert mod.igpu_floors() == want
    assert json.loads((ROOT / "client" / "go" / "core" / "data" / "igpu-floors.json").read_text(encoding="utf-8")) == want

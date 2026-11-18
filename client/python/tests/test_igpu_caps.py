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

"""A claimed iGPU must match the host CPU's vendor: AMD APUs ship only with AMD CPUs, Intel iGPUs only with Intel CPUs
(camoufox #1024: Skia's RCPPS/RSQRTPS estimates show the CPU vendor in a CPU-rastered readback). dGPUs imply no vendor.
Vendor strings here are synthetic: GenuineIntel, AuthenticAMD."""
import pathlib
import random
import sys
from dataclasses import asdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camoucrome import gen  # noqa: E402

INTEL, AMD = "GenuineIntel", "AuthenticAMD"
KEYS = gen.GPU_CLAIM_KEYS
XE = "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics (0x000046A6) Direct3D11 vs_5_0 ps_5_0, D3D11)"
UHD620 = "ANGLE (Intel, Intel(R) UHD Graphics 620 (0x00003EA0) Direct3D11 vs_5_0 ps_5_0, D3D11)"
ARC = "ANGLE (Intel, Intel(R) Arc(TM) A770 Graphics (0x000056A0) Direct3D11 vs_5_0 ps_5_0, D3D11)"
RX = "ANGLE (AMD, AMD Radeon RX 6800 (0x000073BF) Direct3D11 vs_5_0 ps_5_0, D3D11)"
NV = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002503) Direct3D11 vs_5_0 ps_5_0, D3D11)"


def amd_igpu():
    for r in (gen._igpu_caps() or {}):
        if r[0] == "AMD":
            return f"ANGLE (AMD, AMD Radeon(TM) Graphics (0x{r[1]:08X}) Direct3D11 vs_5_0 ps_5_0, D3D11)"


def test_igpu_vendor_names_the_cpu_vendor_only_for_igpus():
    assert gen.igpu_vendor(XE) == INTEL and gen.igpu_vendor(UHD620) == INTEL
    assert gen.igpu_vendor(amd_igpu()) == AMD
    assert gen.igpu_vendor(ARC) is None and gen.igpu_vendor(RX) is None and gen.igpu_vendor(NV) is None
    assert gen.igpu_vendor(None) is None


def test_cpu_vendor_parses_cpuinfo_and_processor_identifier():
    assert gen.cpu_vendor_of("vendor_id\t: GenuineIntel\nmodel name : x") == INTEL
    assert gen.cpu_vendor_of("vendor_id\t: AuthenticAMD") == AMD
    assert gen.cpu_vendor_of("Intel64 Family 6 Model 140 Stepping 1, GenuineIntel") == INTEL
    assert gen.cpu_vendor_of("AMD64 Family 25 Model 33 Stepping 0, AuthenticAMD") == AMD
    assert gen.cpu_vendor_of("Apple M1") is None and gen.cpu_vendor_of("") is None


def claims(vendor, seeds=range(1, 301)):
    out = []
    for s in seeds:
        cfg = gen.generate("windows", "Europe/Paris", None, s, host_cores=64, host_cpu_vendor=vendor)["config"]
        out.append(cfg.get("webGl:renderer"))
    return out


def test_a_new_draw_on_an_intel_host_never_claims_an_amd_igpu_and_keeps_a_claim():
    got = claims(INTEL)
    assert all(gen.igpu_vendor(r) != AMD for r in got)
    assert sum(gen.igpu_vendor(r) == INTEL for r in got) > 20 and all(got)


def test_a_new_draw_on_an_amd_host_never_claims_an_intel_igpu_and_keeps_a_claim():
    got = claims(AMD)
    assert all(gen.igpu_vendor(r) != INTEL for r in got)
    assert sum(gen.igpu_vendor(r) == AMD for r in got) > 20 and all(got)


def test_unset_vendor_draws_as_before():
    got = claims(None)
    assert {gen.igpu_vendor(r) for r in got} >= {INTEL, AMD}


def stored(vendor_claim):
    g = __import__("browserforge.fingerprints", fromlist=["FingerprintGenerator"]).FingerprintGenerator(browser="chrome", os="windows")
    random.seed(7)
    while True:
        fp = asdict(g.generate())
        vc = fp.get("videoCard") or {}
        if gen.gpu_class(vc.get("renderer")) in ("igpu", "igpu-gen9") and gen.igpu_vendor(vc["renderer"]) == vendor_claim \
                and fp["navigator"]["hardwareConcurrency"] >= (gen.igpu_thread_floor(vc["renderer"]) or 0):
            return fp


def test_a_stored_identity_drops_the_claim_on_a_mismatched_host_and_keeps_it_elsewhere():
    for claim, other in ((AMD, INTEL), (INTEL, AMD)):
        fp = stored(claim)
        kw = dict(rng=random.Random(1), host_cores=64)
        for host, kept in ((claim, True), (None, True), (other, False)):
            out = gen.from_pool(fp, "Europe/Paris", None, host_cpu_vendor=host, **{**kw, "rng": random.Random(1)})
            assert all(k in out["config"] for k in KEYS) == kept, (claim, host)
            assert any("CPU vendor" in w for w in out["warnings"]) == (not kept)


def test_an_explicit_gpu_is_never_dropped_for_vendor():
    # --gpu is the owner's opt-in: the claim stays whatever the CPU says.
    out = gen.generate("windows", "Europe/Paris", None, 1, gpu="windows-intel-uhd-630-d3d11", host_cores=64, host_cpu_vendor=AMD)
    assert "webGl:renderer" in out["config"]


def test_pool_shares_match_the_go_pool_counts():
    # client/go/core TestPoolMismatchShares: the same 5000 entries, classified by gen.gpu_class.
    import gzip
    import json
    entries = json.load(gzip.open(pathlib.Path(__file__).resolve().parents[2] / "go" / "core" / "data" / "pool-windows.json.gz"))["entries"]
    vendors = [gen.igpu_vendor(e["webGl:renderer"]) for e in entries]
    assert (vendors.count(AMD), vendors.count(INTEL), len(entries)) == (634, 2276, 5000)

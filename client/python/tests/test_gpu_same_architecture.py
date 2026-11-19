"""Same-architecture mode (owner 2026-11-19): a new draw claims a GPU only from the host's own Dawn architecture, and
webGpu:blocked is false exactly when the claim and the host share vendor and architecture. Hosts here are fake renderer
strings: no test reads the machine's GPU or CPU."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camoucrome import gen  # noqa: E402

D3D = "Direct3D11 vs_5_0 ps_5_0, D3D11)"
UHD630 = f"ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00003E92) {D3D}"
UHD620 = f"ANGLE (Intel, Intel(R) UHD Graphics 620 (0x00005917) {D3D}"
GEN9_9B41 = f"ANGLE (Intel, Intel(R) UHD Graphics (0x00009B41) {D3D}"  # the host measured 2026-11-19
XE = f"ANGLE (Intel, Intel(R) Iris(R) Xe Graphics (0x00009A49) {D3D}"
RTX3060 = f"ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002504) {D3D}"
RTX3070 = f"ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 (0x00002484) {D3D}"
RTX4090 = f"ANGLE (NVIDIA, NVIDIA GeForce RTX 4090 (0x00002684) {D3D}"
GTX1060 = f"ANGLE (NVIDIA, NVIDIA GeForce GTX 1060 6GB (0x00001C03) {D3D}"
RX6800 = f"ANGLE (AMD, AMD Radeon RX 6800 (0x000073BF) {D3D}"
RX6600 = f"ANGLE (AMD, AMD Radeon RX 6600 (0x000073FF) {D3D}"
RX5700 = f"ANGLE (AMD, AMD Radeon RX 5700 XT (0x0000731F) {D3D}"
NOT_IN_TABLE = f"ANGLE (Intel, Intel(R) UHD Graphics (0x0000FFFF) {D3D}"
SWIFTSHADER = "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)"


def test_gpu_architecture_names_vendor_and_dawn_architecture():
    assert gen.gpu_architecture(UHD630) == ("intel", "gen-9") == gen.gpu_architecture(GEN9_9B41)
    assert gen.gpu_architecture(RTX3060) == ("nvidia", "ampere") == gen.gpu_architecture(RTX3070)
    assert gen.gpu_architecture(RTX4090) == ("nvidia", "lovelace")
    assert gen.gpu_architecture(RX6800) == ("amd", "rdna-2") == gen.gpu_architecture(RX6600)
    assert gen.gpu_architecture(XE) == ("intel", "gen-12-lp")
    for none in (None, "", NOT_IN_TABLE, SWIFTSHADER, "llvmpipe (LLVM 15)", "Microsoft Basic Render Driver"):
        assert gen.gpu_architecture(none) is None


# (claim, host, blocked): the rule is "false exactly when vendor and architecture agree"; an unknown host stays blocked.
PAIRS = [
    (UHD630, UHD620, False),  # Gen9 on Gen9, two SKUs
    (UHD630, GEN9_9B41, False),
    (RTX3060, RTX3070, False),  # Ampere on Ampere, a different SKU
    (RX6800, RX6600, False),  # RDNA 2 on RDNA 2
    (RTX3060, RTX3060, False),  # the host's own renderer
    (RTX3060, RTX4090, True),  # one vendor, two architectures
    (RTX3060, GTX1060, True),
    (RX6800, RX5700, True),
    (XE, UHD630, True),  # Intel Gen 12 LP claim on a Gen 9 host
    (UHD630, RTX3060, True),  # two vendors
    (RTX3060, RX6800, True),
    (RTX3060, None, True),  # unknown host
    (RTX3060, SWIFTSHADER, True),
    (UHD630, NOT_IN_TABLE, True),
]


@pytest.mark.parametrize("claim,host,blocked", PAIRS)
def test_webgpu_blocked_is_false_exactly_when_vendor_and_architecture_agree(claim, host, blocked):
    assert gen.gpu_keys("v", claim, host)["webGpu:blocked"] is blocked


def test_the_host_string_alone_opens_webgpu_when_its_architecture_is_unknown():
    # #216 behaviour kept for an unknown architecture: the claim is the host's own renderer string
    assert gen.gpu_keys("v", NOT_IN_TABLE, NOT_IN_TABLE)["webGpu:blocked"] is False


def draw(seed, host, **kw):
    return gen.generate("windows", seed=seed, host_renderer=host, host_cores=1024, host_cpu_vendor=None, **kw)


@pytest.mark.parametrize("host", [UHD630, RTX3060, RX6800])
def test_every_claim_on_a_known_host_has_its_vendor_and_architecture_or_none(host):
    want = gen.gpu_architecture(host)
    claims = 0
    for seed in range(1, 41):
        cfg = draw(seed, host)["config"]
        r = cfg.get("webGl:renderer")
        if r is None:
            assert "webGpu:blocked" not in cfg and "webGl2:renderer" not in cfg
            continue
        claims += 1
        assert gen.gpu_architecture(r) == want, (seed, r)
        assert cfg["webGpu:blocked"] is False
    assert claims, "the pool holds no entry of this architecture in 40 seeds"


def test_no_same_architecture_entry_in_the_budget_means_no_claim_and_a_warning():
    gen8 = f"ANGLE (Intel, Intel(R) HD Graphics 5500 (0x00001616) {D3D}"  # Gen 8: no pool entry
    assert gen.gpu_architecture(gen8) == ("intel", "gen-8")
    out = draw(7, gen8)
    assert not any(k in out["config"] for k in gen.GPU_CLAIM_KEYS)
    assert any("architecture" in w and "no GPU claim" in w for w in out["warnings"])


def test_an_unknown_host_is_choice_b_unchanged_and_warns_once():
    base = draw(3, None)
    for unknown in (SWIFTSHADER, NOT_IN_TABLE, "llvmpipe (LLVM 15)"):
        out = draw(3, unknown)
        assert out["config"] == base["config"] and out["launch"] == base["launch"]
        assert sum("architecture" in w for w in out["warnings"]) == 1
    assert not any("architecture" in w for w in base["warnings"])  # no host renderer passed: nothing changes, nothing said


def test_gpu_flag_is_not_gated():
    # --gpu names a captured profile on purpose (a test box); the arch rule is for drawn claims only
    out = draw(1, RTX3060, gpu="windows-intel-uhd-630-d3d11")
    assert out["config"]["webGl:renderer"].endswith("D3D11)") and "Intel" in out["config"]["webGl:renderer"]

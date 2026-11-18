import json
import pathlib

from camoucrome import gen

NV = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002504) Direct3D11 vs_5_0 ps_5_0, D3D11)"
G620 = "ANGLE (Intel, Intel(R) UHD Graphics 620 (0x00005917) Direct3D11 vs_5_0 ps_5_0, D3D11)"
G630 = "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00003E92) Direct3D11 vs_5_0 ps_5_0, D3D11)"


def test_gpu_class_rejects():
    assert gen.gpu_class("ANGLE (AMD, AMD Radeon(TM) Graphics (0x00001638) Direct3D11 vs_5_0 ps_5_0, D3D11)") is None
    assert gen.gpu_class("ANGLE (Intel, Intel(R) Iris(R) Xe Graphics (0x00009A49) Direct3D11 vs_5_0 ps_5_0, D3D11)") is None
    assert gen.gpu_class("ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)") is None
    assert gen.gpu_class("ANGLE (Microsoft, Microsoft Basic Render Driver (0x0000008C) Direct3D11 vs_5_0 ps_5_0, D3D11)") is None
    assert gen.gpu_class("garbage") is None and gen.gpu_class("") is None and gen.gpu_class(None) is None


def test_gpu_class_accepts():
    assert gen.gpu_class(NV) == "dgpu"
    assert gen.gpu_class("ANGLE (AMD, AMD Radeon RX 6600 (0x000073FF) Direct3D11 vs_5_0 ps_5_0, D3D11)") == "dgpu"
    assert gen.gpu_class("ANGLE (Intel, Intel(R) Arc(TM) A750 Graphics (0x000056A1) Direct3D11 vs_5_0 ps_5_0, D3D11)") == "dgpu"
    assert gen.gpu_class(G620) == "igpu-gen9"


def test_blocked_rule():
    assert gen.gpu_keys("Google Inc. (NVIDIA)", NV, NV)["webGpu:blocked"] is False
    assert gen.gpu_keys("Google Inc. (NVIDIA)", NV, None)["webGpu:blocked"] is True
    assert gen.gpu_keys("Google Inc. (NVIDIA)", NV, G630)["webGpu:blocked"] is True
    assert gen.gpu_keys("Google Inc. (Intel)", G620, G630)["webGpu:blocked"] is False  # Gen9 on Gen9
    assert set(gen.gpu_keys("Google Inc. (NVIDIA)", NV, None)) == {
        "webGl:vendor", "webGl:renderer", "webGl2:vendor", "webGl2:renderer", "webGpu:blocked"}


def test_claims_vary_and_are_deterministic():
    seen = {gen.generate("windows", seed=s, host_cores=1024)["config"]["webGl:renderer"] for s in range(1, 201)}
    assert len(seen) >= 20 and len({r.split(",")[0] for r in seen}) >= 2
    a = gen.generate("windows", seed=7, host_cores=1024)["config"]
    assert a == gen.generate("windows", seed=7, host_cores=1024)["config"]
    assert not any(k.endswith((":parameters", ":supportedExtensions", ":shaderPrecisionFormats")) for k in a)


def test_gen9_claim_holds_thread_cap():
    for s in range(1, 400):
        c = gen.generate("windows", seed=s, host_cores=1024)["config"]
        cap = gen.gen9_thread_cap(c["webGl:renderer"])
        if cap is not None:
            assert c["navigator.hardwareConcurrency"] <= cap


def test_gpu_claim_keeps_other_keys():
    fixture = json.loads((pathlib.Path(__file__).parent / "fixtures" / "gpu_claim_seed.json").read_text())
    for seed, want in fixture.items():
        got = gen.generate("windows", seed=int(seed), host_cores=1024)["config"]
        assert {k: v for k, v in got.items() if not k.startswith(("webGl:", "webGl2:", "webGpu:"))} == want

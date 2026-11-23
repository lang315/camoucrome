"""A host iGPU whose thread floor is no THREAD_STEPS value (14, 18, 24: real SKU counts) must not make generate fail, and a
config with no GPU claim (the host's real iGPU shows) never has fewer threads than that floor when the host has them.
Go core's Draw and Resolve keep the same rule (client/go/core samearch_test.go). Hosts are fake renderer strings."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camoucrome import gen  # noqa: E402

D3D = "Direct3D11 vs_5_0 ps_5_0, D3D11)"
HOSTS = [
    (f"ANGLE (Intel, Intel(R) Graphics (0x00007D45) {D3D}", 14),
    (f"ANGLE (Intel, Intel(R) Graphics (0x00007D55) {D3D}", 18),
]


@pytest.mark.parametrize("renderer,cores", HOSTS)
def test_non_step_floor_host_always_draws_and_never_sits_below_its_floor(renderer, cores):
    floor = gen.igpu_thread_floor(renderer)
    assert floor == cores and floor not in gen.THREAD_STEPS
    spares = 0
    for seed in range(1, 41):
        out = gen.generate("windows", seed=seed, host_renderer=renderer, host_cores=cores, host_cpu_vendor=None)
        cfg = out["config"]
        if "webGl:renderer" not in cfg:
            spares += 1
            assert cfg["navigator.hardwareConcurrency"] >= floor, (seed, cfg["navigator.hardwareConcurrency"])
    assert spares, "no draw without a GPU claim: the test did not reach the spare path"

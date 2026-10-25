import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import step2_rows as rows  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CONSTANTS = json.load(open(os.path.join(ROOT, "settings", "machine_constants.json")))["leaves"]
GPU_LIMIT_LEAVES = ["gpu.limits.maxBindGroups", "gpu.limits.maxBufferSize",
                    "gpu.limits.maxComputeWorkgroupSizeX", "gpu.limits.maxStorageBufferBindingSize",
                    "gpu.limits.maxTextureDimension2D"]


def test_webgpu_limits_are_explained():
    assert rows.unexplained(GPU_LIMIT_LEAVES, CONSTANTS) == []


def test_a_new_gpu_limit_is_not_swallowed():
    assert rows.unexplained(["gpu.limits.maxSomethingNew"], CONSTANTS) == ["gpu.limits.maxSomethingNew"]


def test_webgpu_features_stay_unexplained():
    # Filed in docs/superpowers/measurements/2026-10-25-webgpu-limits-source.md (local), ruling R8: the feature list depends on the machine's driver, shader model and
    # 16-bit shader ops (a different real machine can lack shader-f16), so it is not a
    # machine constant. Filed limit; allowlisting it needs the owner.
    assert rows.unexplained(["gpu.features"], CONSTANTS) == ["gpu.features"]


def test_every_gpu_row_has_a_sourced_reason():
    for k, why in CONSTANTS.items():
        if k.startswith("gpu."):
            assert len(why) > 40 and "TBD" not in why, k
        if k.startswith("gpu.limits."):
            assert "webgpu-limits-source" in why, k

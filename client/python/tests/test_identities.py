"""Spec section 2: two generated Windows identities share only the declared GPU-derived keys."""
from camoucrome import gen

DEVICE_KEYS = ["screen.width", "screen.height", "navigator.hardwareConcurrency", "navigator.deviceMemory",
               "fonts:list", "voices:list"]


def keys_of(seed):
    return gen.generate(os="windows", seed=seed)["config"]


def test_two_seeds_give_two_devices():
    a, b = keys_of(1), keys_of(2)
    differing = [k for k in DEVICE_KEYS if a.get(k) != b.get(k)]
    assert len(differing) >= 3, f"only {differing} differ"


def test_only_gpu_keys_are_forced_equal():
    a, b = keys_of(1), keys_of(2)
    gpu = {k for k in a if k.startswith(("webGl:", "webGl2:"))}
    assert gpu, "no WebGL keys: the identity claims no GPU"
    assert all(a[k] == b[k] for k in gpu), "two identities claim different GPUs on a one-GPU host"

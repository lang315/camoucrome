"""Spec section 2: two generated Windows identities share only a declared list of components."""
from camoucrome import gen

# Keys that must differ between two seeds.
DEVICE_KEYS = ["screen.width", "screen.height", "navigator.hardwareConcurrency"]
PER_INSTANCE_SEEDS = ["canvas:seed", "audio:seed", "mediaDevices:seed"]

# Config keys, or key prefixes ending in ":" or ".", that two identities may share.
SHARED_ALLOWED = frozenset({
    # the host generation's WebGL tables; only webGl:renderer (name + DeviceId) is per profile
    *(f"{c}:{k}" for c in ("webGl", "webGl2") for k in ("vendor", "parameters", "supportedExtensions", "shaderPrecisionFormats")),
    # stock Windows 10 / Chrome data every user shares
    "ua:",                          # osInfo, platform, platformVersion, architecture, bitness, brand, ...
    "locale:tag", "navigator.language", "navigator.languages",  # en-US default
    "fonts:",                       # stock Windows font list and its alias maps
    "voices:list",                  # stock Windows voices
    "navigator.deviceMemory",       # Chrome caps it at 8
    "navigator.maxTouchPoints",     # 0 on a non-touch desktop
    "window.screenX", "window.screenY",  # maximised window at 0,0
    "audio:sampleRate", "audio:bufferFrames",  # stock Windows audio output
    "battery:charging",             # desktop default
    "mediaDevices:enabled", "mediaDevices:speakers",  # one speaker, stock
})


HOST = "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00009BC5) Direct3D11 vs_5_0 ps_5_0, D3D11)"


def keys_of(seed):
    return gen.generate(os="windows", seed=seed, host_renderer=HOST)["config"]


def allowed(key):
    return key in SHARED_ALLOWED or any(p[-1] in ":." and key.startswith(p) for p in SHARED_ALLOWED)


def test_two_seeds_give_two_devices():
    a, b = keys_of(1), keys_of(2)
    assert [k for k in DEVICE_KEYS if a.get(k) == b.get(k)] == []


def test_per_instance_seeds_differ():
    a, b = keys_of(1), keys_of(2)
    assert [k for k in PER_INSTANCE_SEEDS if a.get(k) == b.get(k)] == []


def test_only_declared_keys_are_shared():
    a, b = keys_of(1), keys_of(2)
    assert any(k.startswith(("webGl:", "webGl2:")) for k in a), "no WebGL keys: the identity claims no GPU"
    shared = {k for k in a if a[k] == b.get(k)}
    assert {k for k in shared if not allowed(k)} == set()


def test_gpu_name_differs_for_some_pair_of_seeds():
    names = {keys_of(s)["webGl:renderer"] for s in range(1, 6)}
    assert len(names) > 1

#!/usr/bin/env python3
"""Golden fixtures for client/go/core: what gen.py's deterministic steps answer, written to
client/go/core/testdata/golden/*.json. Run under the pinned venv (gen_go_core_data.py's PINS).
Go's TestGoldenDeterministic compares itself to these key by key. The random host steps (window fit) have
no golden: they are tested by invariants."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gen_go_core_data as d  # noqa: E402

OUT = d.ROOT / "client" / "go" / "core" / "testdata" / "golden"
HOSTS = [  # a fixed host per full run: cores, platform version, display
    (3, "10.0.0", {"gamut": "srgb", "colorBits": 8, "hdr": False}),
    (8, "13.0.0", {"gamut": "p3", "colorBits": 10, "hdr": True}),
    (64, "15.0.0", None),
]
TAGS = ["en-US", "tr-TR", "fil-PH", "th-TH", "id-ID", "de-DE", "pt-BR", "ja-JP", "en-CA", "fr-CA", "xx-YY", "zz"]
DISPLAYS = [None, {"gamut": "srgb", "colorBits": 8, "hdr": False}, {"gamut": "p3", "colorBits": 8, "hdr": False},
            {"gamut": "rec2020", "colorBits": 10, "hdr": False}, {"gamut": "srgb", "colorBits": 10, "hdr": True},
            {"gamut": "srgb", "colorBits": 8, "hdr": True}]


# Synthetic (claim, host) renderer pairs from the settings files: Gen9 ids from settings/webgl/intel-gen9-pool.json,
# the Iris Xe and RTX 3060 strings from the golden tests of gen.py. None is a real host.
G620_A = "ANGLE (Intel, Intel(R) UHD Graphics 620 (0x00005917) Direct3D11 vs_5_0 ps_5_0, D3D11)"
G620_B = "ANGLE (Intel, Intel(R) UHD Graphics 620 (0x00003EA0) Direct3D11 vs_5_0 ps_5_0, D3D11)"
G630 = "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00003E92) Direct3D11 vs_5_0 ps_5_0, D3D11)"
XE = "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics (0x00009A49) Direct3D11 vs_5_0 ps_5_0, D3D11)"
RTX = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002504) Direct3D11 vs_5_0 ps_5_0, D3D11)"
RTX2 = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 (0x00002484) Direct3D11 vs_5_0 ps_5_0, D3D11)"
FAKE_GEN9 = "ANGLE (Intel, Intel(R) UHD Graphics 620 (0x0000FFFF) Direct3D11 vs_5_0 ps_5_0, D3D11)"  # the shape, an id not in the pool
RTX4090 = "ANGLE (NVIDIA, NVIDIA GeForce RTX 4090 (0x00002684) Direct3D11 vs_5_0 ps_5_0, D3D11)"  # Dawn: lovelace (Ada)
GTX1060 = "ANGLE (NVIDIA, NVIDIA GeForce GTX 1060 6GB (0x00001C03) Direct3D11 vs_5_0 ps_5_0, D3D11)"  # Dawn: pascal
RX6800 = "ANGLE (AMD, AMD Radeon RX 6800 (0x000073BF) Direct3D11 vs_5_0 ps_5_0, D3D11)"  # Dawn: rdna-2 (mask 0xFFF0)
RX6600 = "ANGLE (AMD, AMD Radeon RX 6600 (0x000073FF) Direct3D11 vs_5_0 ps_5_0, D3D11)"
RX5700 = "ANGLE (AMD, AMD Radeon RX 5700 XT (0x0000731F) Direct3D11 vs_5_0 ps_5_0, D3D11)"  # Dawn: rdna-1
UHD_9B41 = "ANGLE (Intel, Intel(R) UHD Graphics (0x00009B41) Direct3D11 vs_5_0 ps_5_0, D3D11)"  # Gen9 by Dawn's mask, not in the pool
NOT_IN_TABLE = "ANGLE (Intel, Intel(R) UHD Graphics (0x0000FFFF) Direct3D11 vs_5_0 ps_5_0, D3D11)"
SWIFTSHADER = "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)"
WEBGPU_PAIRS = [  # (claim, host)
    (RTX, RTX), (G620_A, G620_A), (G620_A, G630), (G620_B, G630), (G630, XE), (XE, G630), (XE, XE), (RTX, G630), (G630, RTX),
    (RTX, RTX2), (G620_A, None), (RTX, None), (XE, None), (G620_A, ""), (FAKE_GEN9, G630), (G630, FAKE_GEN9), (FAKE_GEN9, FAKE_GEN9),
    # same-architecture mode: a different SKU of one architecture opens, one vendor with two architectures does not
    (RTX, RTX4090), (RTX, GTX1060), (RTX4090, RTX), (RX6800, RX6600), (RX6800, RX5700), (RX6800, RTX), (G630, UHD_9B41),
    (UHD_9B41, G620_A), (XE, UHD_9B41), (RTX, SWIFTSHADER), (G630, NOT_IN_TABLE), (NOT_IN_TABLE, NOT_IN_TABLE), (RX6800, None)]


def webgpu_rows(gen):
    """gen.gpu_keys's webGpu:blocked for every pair: what core.Resolve must answer for a claim on a host renderer."""
    return [{"claim": c, "host": h, "blocked": gen.gpu_keys("v", c, h)["webGpu:blocked"]} for c, h in WEBGPU_PAIRS]


def write(name, v, indent=1):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(v, indent=indent, ensure_ascii=False, separators=None if indent else (",", ":")) + "\n", encoding="utf-8")


def main():
    d.check_pins()
    from camoucrome import gen, geoip
    # cores: the claim and the snapped result both come out of gen.generate (from_pool's host_cores line)
    cores, seen = [], set()
    # 200 seeds, not 60: once gen.py redraws samples with no drawable GPU, seeds 1..60 draw only 11 distinct claims
    # (352 rows), below the Go guard of 400 (12.5 claims x 32 hosts); seeds 1..200 draw 17 (544 rows).
    for seed in range(1, 201):
        claim = gen.generate(d.OS, seed=seed, host_cores=1024, host_cpu_vendor=None)["config"]["navigator.hardwareConcurrency"]
        for host in range(1, 33):
            if (claim, host) in seen:
                continue
            seen.add((claim, host))
            got = gen.generate(d.OS, seed=seed, host_cores=host, host_cpu_vendor=None)["config"]["navigator.hardwareConcurrency"]
            cores.append({"cores": host, "claim": claim, "want": got})
    write("cores.json", cores)
    write("display.json", [{"display": x, "flags": gen.display_flags(x)[0], "warning": gen.display_flags(x)[1]} for x in DISPLAYS])
    write("voices.json", [{"tag": t, "list": gen.voices_keys("Windows", t)["voices:list"]} for t in TAGS])
    zones = json.loads((d.ROOT / "settings" / "locale_zones.json").read_text())["zones"]
    exits = []
    for code in ["US", "DE", "PH", "CA", "CH", "JP", "TH", "ID", "BR", "GB", "FR", "TR"]:
        tag = geoip.locale_for(code)  # no fallback: every code here has a locale_zones row
        # the locale triple and voices as gen.from_pool builds them for a given locale
        cfg = gen.generate(d.OS, seed=1, timezone=zones[tag][0], locale=tag, host_cores=1024, host_cpu_vendor=None)["config"]
        exits.append({"country": code, "tag": tag, "languages": cfg["navigator.languages"],
                      "voices": cfg["voices:list"]})
    write("exit.json", exits)
    # snap_window over every DPR the generator accepts and a range of outer sizes: [launch, reported outer]
    write("snap.json", {str(dpr): [list(gen.snap_window(dpr, o)) for o in range(600, 2201)] for dpr in gen.WINDOW_OFFSET}, indent=None)
    runs = []
    fonts = d.fonts_subset()
    for seed, (hc, pv, disp) in zip([11, 222, 3333], HOSTS):
        base = gen.generate(d.OS, seed=seed, host_cores=1024, host_cpu_vendor=None)
        entry = {k: v for k, v in base["config"].items()
                 if k not in ("voices:list", "canvas:seed", "mediaDevices:seed", "timezone:id")}
        entry["dpr"] = base["launch"]["dpr"]
        want = gen.generate(d.OS, seed=seed, host_cores=hc, host_platform_version=pv, host_display=disp, host_cpu_vendor=None)
        skip = ("canvas:seed", "mediaDevices:seed", "timezone:id")
        runs.append({"seed": seed, "entry": entry, "host": {"cores": hc, "platformVersion": pv, "display": disp},
                     "config": {k: v for k, v in want["config"].items() if k not in skip},
                     "args": want["launch"]["args"], "dpr": want["launch"]["dpr"],
                     "warnings": want["warnings"]})
    write("from_pool.json", runs)
    write("webgpu.json", webgpu_rows(gen))
    print("golden written:", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()

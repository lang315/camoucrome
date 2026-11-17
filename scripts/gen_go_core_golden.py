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


def write(name, v, indent=1):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(v, indent=indent, ensure_ascii=False, separators=None if indent else (",", ":")) + "\n", encoding="utf-8")


def main():
    d.check_pins()
    from camoucrome import gen, geoip
    # cores: the claim and the snapped result both come out of gen.generate (from_pool's host_cores line)
    cores, seen = [], set()
    for seed in range(1, 61):
        claim = gen.generate(d.OS, seed=seed, host_cores=1024)["config"]["navigator.hardwareConcurrency"]
        for host in range(1, 33):
            if (claim, host) in seen:
                continue
            seen.add((claim, host))
            got = gen.generate(d.OS, seed=seed, host_cores=host)["config"]["navigator.hardwareConcurrency"]
            cores.append({"cores": host, "claim": claim, "want": got})
    write("cores.json", cores)
    write("display.json", [{"display": x, "flags": gen.display_flags(x)[0], "warning": gen.display_flags(x)[1]} for x in DISPLAYS])
    write("voices.json", [{"tag": t, "list": gen.voices_keys("Windows", t)["voices:list"]} for t in TAGS])
    zones = json.loads((d.ROOT / "settings" / "locale_zones.json").read_text())["zones"]
    exits = []
    for code in ["US", "DE", "PH", "CA", "CH", "JP", "TH", "ID", "BR", "GB", "FR", "TR"]:
        tag = geoip.locale_for(code)  # no fallback: every code here has a locale_zones row
        # the locale triple and voices as gen.from_pool builds them for a given locale
        cfg = gen.generate(d.OS, seed=1, timezone=zones[tag][0], locale=tag, host_cores=1024)["config"]
        exits.append({"country": code, "tag": tag, "languages": cfg["navigator.languages"],
                      "voices": cfg["voices:list"]})
    write("exit.json", exits)
    # snap_window over every DPR the generator accepts and a range of outer sizes: [launch, reported outer]
    write("snap.json", {str(dpr): [list(gen.snap_window(dpr, o)) for o in range(600, 2201)] for dpr in gen.WINDOW_OFFSET}, indent=None)
    runs = []
    fonts = d.fonts_subset()
    for seed, (hc, pv, disp) in zip([11, 222, 3333], HOSTS):
        base = gen.generate(d.OS, seed=seed, host_cores=1024)
        entry = {k: v for k, v in base["config"].items()
                 if k not in ("voices:list", "canvas:seed", "mediaDevices:seed", "timezone:id")}
        entry["dpr"] = base["launch"]["dpr"]
        want = gen.generate(d.OS, seed=seed, host_cores=hc, host_platform_version=pv, host_display=disp)
        skip = ("canvas:seed", "mediaDevices:seed", "timezone:id")
        runs.append({"seed": seed, "entry": entry, "host": {"cores": hc, "platformVersion": pv, "display": disp},
                     "config": {k: v for k, v in want["config"].items() if k not in skip},
                     "args": want["launch"]["args"], "dpr": want["launch"]["dpr"],
                     "warnings": want["warnings"]})
    write("from_pool.json", runs)
    print("golden written:", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()

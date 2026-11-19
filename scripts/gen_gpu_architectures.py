#!/usr/bin/env python3
"""Derive settings/webgl/gpu-architectures.json from Dawn's gpu_info.json, and check that it is fresh.

  python3 scripts/gen_gpu_architectures.py <gpu_info.json>           write the table
  python3 scripts/gen_gpu_architectures.py <gpu_info.json> --check   fail (rc 1) when the committed table differs

gpu_info.json is third_party/dawn/src/dawn/gpu_info.json at the Dawn revision the pin's DEPS names (read it from the box tree,
or from dawn.googlesource.com at DAWN_REVISION). Chrome 157's WebGPU reports adapter.info.architecture from it, so the
table says which GPUs a page cannot tell apart through WebGPU. Only the derived table is committed, never Dawn's file.

Table: vendors[<lower-case vendor>] = {"id", "sets": [{"mask", "ids": {<masked device id>: <architecture>}}]}. A device id
matches a set when id & mask is a key of ids (Dawn's own rule). The architecture is Dawn's name lower-cased by js_enum_case, as adapter.info reports it (Dawn's js_enum_case, see arch_name). Sets Dawn marks internal are never reported and are left out.
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "settings" / "webgl" / "gpu-architectures.json"
# Dawn at the Chromium pin 653674df29 (157.0.8103.51): the revision of third_party/dawn in the box tree.
DAWN_REVISION = "3c24c91e70eaf701ae92ab8cc414669cc4c38892"
LICENCE = ("Derived from Dawn's src/dawn/gpu_info.json; Dawn is BSD-3-Clause, Copyright The Dawn & Tint Authors "
           "(https://dawn.googlesource.com/dawn/+/refs/heads/main/LICENSE).")
EXACT = 0xFFFFFFFF  # a set with no mask compares the whole id


def arch_name(name):
    """Dawn's js_enum_case: lower case, words joined by hyphens, except that a letter word right after a number word attaches
    to it ("Gen 12 LP" -> gen-12lp, "Xe 3 LPG XS" -> xe-3lpg-xs, "Gen 9" -> gen-9)."""
    out = ""
    for w in name.lower().split():
        out += w if out and out.split("-")[-1].isdigit() and w[0].isalpha() else ("-" if out else "") + w
    return out


def build(info, revision):
    vendors = {}
    for name, v in info["vendors"].items():
        if name.startswith("_") or not v.get("devices"):
            continue
        sets = []
        for s in v["devices"]:
            if s.get("internal"):
                continue
            mask = int(s["mask"], 16) if "mask" in s else EXACT
            width = max(4, len(f"{mask:X}"))
            ids = {}
            for arch, devs in s["architecture"].items():
                if arch.startswith("_"):
                    continue
                for d in devs:
                    ids[f"0x{int(d, 16) & mask:0{width}X}"] = arch_name(arch)
            sets.append({"mask": f"0x{mask:0{width}X}", "ids": ids})
        vendors[name.lower()] = {"id": v["id"], "sets": sets}
    for name, v in vendors.items():
        _no_overlap(name, v["sets"])
    return {"dawn": {"revision": revision, "source": "src/dawn/gpu_info.json", "licence": LICENCE}, "vendors": vendors}


def _no_overlap(vendor, sets):
    """Two sets that can match one device id must agree on its architecture: a lookup then never depends on set order."""
    rows = [(int(s["mask"], 16), int(i, 16), a) for s in sets for i, a in s["ids"].items()]
    for n, (m1, i1, a1) in enumerate(rows):
        for m2, i2, a2 in rows[n + 1:]:
            if a1 != a2 and (i1 ^ i2) & m1 & m2 == 0:
                raise ValueError(f"{vendor}: overlap between 0x{i1:X}/{m1:X} ({a1}) and 0x{i2:X}/{m2:X} ({a2})")


def architecture(table, vendor, device_id):
    """The Dawn architecture name of a (vendor name, device id), or None when the table has no such part."""
    v = table["vendors"].get(vendor.lower())
    for s in v["sets"] if v else ():
        a = s["ids"].get(f"0x{device_id & int(s['mask'], 16):0{len(s['mask']) - 2}X}")
        if a:
            return a
    return None


def dumps(table):
    return json.dumps(table, indent=1, ensure_ascii=False) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gpu_info", type=pathlib.Path)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--revision", default=DAWN_REVISION)
    ap.add_argument("--out", type=pathlib.Path, default=OUT)
    a = ap.parse_args(argv)
    text = dumps(build(json.loads(a.gpu_info.read_text(encoding="utf-8")), a.revision))
    if a.check:
        if not a.out.exists() or a.out.read_text(encoding="utf-8") != text:
            print("stale:", a.out)
            return 1
        return 0
    a.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

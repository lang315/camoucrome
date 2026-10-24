#!/usr/bin/env python3
"""Writes settings/webgl/intel-gen9-pool.json: the Intel Gen9/9.5 renderer
strings real Windows Chrome reports, weighted by how often BrowserForge's
network (apify data) draws them, keeping only DeviceIds in ANGLE's Gen9
tables. Usage: gen_gpu_pool.py <angle driver_utils.cpp> [--draws N]"""
import argparse, collections, datetime, json, pathlib, random, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "settings" / "webgl" / "intel-gen9-pool.json"
# ANGLE driver_utils.cpp: Skylake (l.65, gen9), KabyLake (l.78, gen9p5), CoffeeLake (l.89, also
# holds Whisky/Amber/Comet Lake). The plan's Kabylake/Coffeelake/Cometlake spellings do not exist there.
# Broxton/GeminiLake (gen9lp) are left out: no desktop UHD 6xx names.
GEN9_TABLES = ("Skylake", "KabyLake", "CoffeeLake")
RENDERER_RE = re.compile(r"^ANGLE \(Intel, Intel\(R\) (U?HD Graphics( 6\d\d)?) \((0x[0-9A-F]{8})\) "
                         r"Direct3D11 vs_5_0 ps_5_0, D3D11\)$")
# `const uint16_t Name[] = {` (ANGLE) or `std::array<uint32_t, N> Name = {`
ARRAY_RE = re.compile(r"(?:\b(\w+)\s*\[\]|std::array<uint32_t,\s*\d+>\s+(\w+))\s*=\s*\{([^}]*)\}")


def gen9_ids(driver_utils_src):
    ids = set()
    for a, b, body in ARRAY_RE.findall(driver_utils_src):
        if (a or b) in GEN9_TABLES:
            ids |= {int(x, 16) for x in re.findall(r"0x[0-9A-Fa-f]+", body)}
    return ids


def pool_from_counts(counts, ids):
    kept = {}
    for renderer, n in counts.items():
        m = RENDERER_RE.match(renderer)
        if m and int(m.group(3), 16) in ids:
            kept[renderer] = (int(m.group(3), 16), n)
    total = sum(n for _, n in kept.values())
    return sorted(({"renderer": r, "device_id": d, "weight": n / total} for r, (d, n) in kept.items()),
                  key=lambda x: -x["weight"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("driver_utils")
    ap.add_argument("--draws", type=int, default=20000)
    a = ap.parse_args()
    from browserforge.fingerprints import FingerprintGenerator
    random.seed(1)
    gen = FingerprintGenerator(browser="chrome", os="windows")
    counts = collections.Counter(gen.generate().videoCard.renderer for _ in range(a.draws))
    ids = gen9_ids(pathlib.Path(a.driver_utils).read_text())
    pool = pool_from_counts(counts, ids)
    if not pool:
        sys.exit("no Gen9 renderer in the draws: refusing to write an empty pool")
    OUT.write_text(json.dumps({"source": "browserforge 1.2.4 network, ANGLE driver_utils.cpp Gen9 tables",
                               "generated": datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
                               "draws": a.draws, "device_ids": sorted(ids), "renderers": pool}, indent=1) + "\n")
    print(f"{len(pool)} renderers, {len(ids)} Gen9 ids")


if __name__ == "__main__":
    main()

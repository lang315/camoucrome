#!/usr/bin/env python3
"""Generate the data client/go/core embeds, and check that it is fresh.

  python3 scripts/gen_go_core_data.py [--seeds N]    write client/go/core/data/*
  python3 scripts/gen_go_core_data.py --check        fail (rc 1) when a committed file differs from a fresh run
  python3 scripts/gen_go_core_data.py --cldr FILE --territory FILE
                                                     also rebuild settings/country_locale.json from CLDR json

Run it under a venv with the pinned draw dependencies (PINS); it refuses any other version, because a different
BrowserForge or datapoints release draws different devices. The pool is drawn with no host inputs: no GPU, no
host fonts, no host screen. Gzip files are compared by content, not bytes (zlib versions differ).
"""
import argparse
import gzip
import hashlib
import json
import pathlib
import sys
from importlib import metadata

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "client" / "python"))

PINS = {"browserforge": "1.2.4", "apify_fingerprint_datapoints": "0.15.0"}
CLDR_VERSION = "47.0.0"
CLDR_SHA256 = {"likelySubtags": "b0f791c37b7f1dedb57f6d0542b904ab0ceee7a476f5194c797f53e87511b9db",
               "territoryInfo": "1fc8e5625dd4abe7b37f8261ee88c5295f3ca323526bd1ea590f046ddfb946fb"}
# cldr-json 47.0.0 cldr-core/supplemental/{likelySubtags,territoryInfo}.json
POOL_FORMAT = 1
DEFAULT_SEEDS = 5000
OS = "windows"
PLATFORM = "Windows"
DATA = ROOT / "client" / "go" / "core" / "data"
# Left out of a compact entry: the font tables and voices:list (about 31 of 35 KB, rebuilt or recomputed in Go),
# the seeds (drawn per identity) and the zone (set by Exit or the locale default).
# GPU claim keys stay: webGpu:blocked is always true in the pool (it has no host renderer); Resolve unblocks it for a same-family host.
# The locale triple stays: without an Exit it is the entry's own.
EXCLUDED_PREFIXES = ("fonts:",)
EXCLUDED_KEYS = {"voices:list", "canvas:seed", "mediaDevices:seed", "timezone:id"}
# ISO 3166-1 alpha-2 assigned codes = CLDR territoryInfo minus these (CLDR exceptional reservations and codes
# outside 3166-1); 249 remain, which equals tzdata's iso3166.tab.
NOT_ISO = {"AC", "CP", "DG", "EA", "IC", "TA", "XK", "ZZ", "EU", "UN", "QO", "CQ"}


def check_pins():
    bad = []
    for name, want in PINS.items():
        try:
            have = metadata.version(name)
        except metadata.PackageNotFoundError:
            have = None
        if have != want:
            bad.append(f"{name}=={want} required, found {have}")
    if bad:
        sys.exit("refusing to draw: " + "; ".join(bad))


def excluded(key):
    return key in EXCLUDED_KEYS or key.startswith(EXCLUDED_PREFIXES)


def fonts_subset():
    """Only what fonts_keys reads for the Windows claim."""
    f = json.loads((ROOT / "settings" / "fonts.json").read_text(encoding="utf-8"))
    return {"families": {PLATFORM: f["families"][PLATFORM]}, "alias_map": {PLATFORM: f["alias_map"][PLATFORM]},
            "extra_allowed": {PLATFORM: f["extra_allowed"][PLATFORM]}, "unique_map": {PLATFORM: f["unique_map"][PLATFORM]}}


def rebuild_fonts(fonts, groups):
    """The font keys of gen.fonts_keys for the Windows claim with chosen = base + the named groups, no host
    families. The reference the Go side ports (client/go/core/fonts.go)."""
    fam = fonts["families"][PLATFORM]
    chosen = set(fam["base"])
    for g in groups:
        chosen |= set(fam["groups"][g]["families"])
    families = [f for f in fam["list"] if f in chosen]
    hidden = set(fam["list"]) - chosen
    alias = {k: v for k, v in fonts["alias_map"][PLATFORM].items() if k not in hidden}
    allowed = families + fonts["extra_allowed"][PLATFORM]
    if fam["ps_names_are_css_families"]:
        for name, v in fam["unique_names"].items():
            target = alias.get(v["family"], v["family"])
            if target != name:
                alias[name] = target
        allowed = allowed + sorted(fam["unique_names"])
    return {"fonts:list": allowed,
            **({"fonts:local": ["\t".join(f) for f in fam["faces"] if f[2] in families]} if fam.get("faces") else {}),
            "fonts:alias": alias,
            "fonts:aliasLocal": {k: v for k, v in fonts["unique_map"][PLATFORM].items()
                                 if fam["unique_names"].get(k, {}).get("family") not in hidden}}


def font_groups(fonts, config):
    """The group names whose families all appear in the drawn fonts:list, verified by rebuilding the font keys."""
    fam = fonts["families"][PLATFORM]
    listed = set(config["fonts:list"])
    groups = sorted(g for g, v in fam["groups"].items() if set(v["families"]) <= listed)
    rebuilt = rebuild_fonts(fonts, groups)
    for k, v in rebuilt.items():
        if config.get(k) != v:
            raise ValueError(f"font groups {groups} do not rebuild {k}")
    return groups


def compact(out, fonts):
    """A gen.generate result -> the pool entry: the config minus EXCLUDED, plus dpr and fontGroups."""
    cfg = out["config"]
    entry = {k: v for k, v in cfg.items() if not excluded(k)}
    entry["dpr"] = out["launch"]["dpr"]
    entry["fontGroups"] = font_groups(fonts, cfg)
    return entry


def draw_pool(n):
    check_pins()
    from camoucrome import gen
    fonts = fonts_subset()
    entries, skipped = [], 0
    for seed in range(1, n + 1):
        try:
            out = gen.generate(OS, seed=seed, host_cores=1024, host_cpu_vendor=None)
        except (ValueError, RuntimeError):  # a locale with no zone row, or no acceptable sample
            skipped += 1
            continue
        entries.append(compact(out, fonts))
    return {"version": POOL_FORMAT, "os": OS, "seeds": n, "skipped": skipped, "entries": entries}


def country_locale_from_cldr(likely, territory):
    """{ISO alpha-2: BCP-47 tag}. und-XX in likelySubtags when present (script dropped), else the territory's
    most-spoken official language (else most-spoken). A territory with no language data gets no row."""
    out = {}
    for code in sorted(set(territory) - NOT_ISO):
        t = likely.get("und-" + code)
        if t and not t.startswith("und-"):  # und-AQ -> und-Latn-AQ: no language
            out[code] = f"{t.split('-')[0]}-{code}"
            continue
        langs = territory[code].get("languagePopulation") or {}
        if not langs:
            continue
        def key(item):
            lang, v = item
            return (v.get("_officialStatus") == "official", float(v.get("_populationPercent", 0)))
        best = max(langs.items(), key=key)[0]
        if best.split("_")[0] == "und":
            continue
        out[code] = f"{best.split('_')[0]}-{code}"
    return out


def read_cldr(path, name):
    raw = pathlib.Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != CLDR_SHA256[name]:
        sys.exit(f"{path} is not cldr-json {CLDR_VERSION} {name}.json (sha256 differs)")
    return json.loads(raw)["supplemental"]


def build_cldr_source(likely_path, territory_path):
    likely = read_cldr(likely_path, "likelySubtags")["likelySubtags"]
    territory = read_cldr(territory_path, "territoryInfo")["territoryInfo"]
    return {"$comment": f"ISO 3166-1 alpha-2 -> BCP-47, from cldr-json {CLDR_VERSION} likelySubtags (und-XX, script "
                        "dropped) and territoryInfo (most-spoken official language) by scripts/gen_go_core_data.py --cldr. "
                        "settings/locale_zones.json overrides it in client/go/core/data/country_locale.json.",
            "cldr": CLDR_VERSION, "rows": country_locale_from_cldr(likely, territory)}


def country_locale(source, zones):
    """The CLDR rows with settings/locale_zones.json's choice winning where it has a locale for the region: its
    first such locale in file order (geoip.locale_for: en-CA before fr-CA)."""
    rows = dict(source["rows"])
    seen = set()
    for tag in zones:
        region = tag.rsplit("-", 1)[-1]
        if region not in seen:
            seen.add(region)
            rows[region] = tag
    return dict(sorted(rows.items()))


def igpu_floors():
    """{"Intel:0x00009A49": min threads}: igpu-thread-caps.json rows and intel-gen9-thread-caps.json rows (vendor Intel) with a
    sourced min_threads. Resolve drops the GPU claim when the host's cores fall below it (gen.py from_pool)."""
    rows = json.loads((ROOT / "settings" / "webgl" / "igpu-thread-caps.json").read_text(encoding="utf-8"))["rows"]
    rows += [dict(r, vendor="Intel") for r in
             json.loads((ROOT / "settings" / "webgl" / "intel-gen9-thread-caps.json").read_text(encoding="utf-8"))["rows"]]
    return {f"{r['vendor']}:0x{int(r['device_id'], 16):08X}": r["min_threads"] for r in rows
            if r["max_threads"] is not None and r.get("min_threads") is not None}


def igpu_ids():
    """["AMD:0x000015DD", "Intel:0x00009A49", ...]: every (vendor, device id) gen.gpu_class calls an iGPU, i.e. the ids with a
    sourced thread cap (igpu-thread-caps.json, and intel-gen9-thread-caps.json for Intel). core.igpuVendor classifies by this
    set alone, so it cannot call an RX Vega 64, an Arc B580 or an unsourced Gen9 id an iGPU when gen.py does not."""
    from camoucrome import gen
    ids = {f"{v}:0x{d:08X}" for v, d in gen._igpu_caps()}
    ids |= {f"Intel:0x{d:08X}" for d in gen._thread_caps()}
    return sorted(ids)


def gen9_ids():
    """["0x00003EA0", ...]: the device ids gen.gen9_device_id accepts (settings/webgl/intel-gen9-pool.json). core.gen9DeviceID
    takes the same name shape and this set, so the webGpu:blocked rule cannot differ from gen.gpu_keys on a Gen9 id."""
    from camoucrome import gen
    return [f"0x{d:08X}" for d in sorted(gen.gen9_pool()["device_ids"])]


def build_files(n, source):
    """{relative name: JSON value} for every embedded file. The pool is built apart (draw_pool)."""
    voices = json.loads((ROOT / "settings" / "voices.json").read_text(encoding="utf-8"))
    zones = json.loads((ROOT / "settings" / "locale_zones.json").read_text(encoding="utf-8"))["zones"]
    return {
        "voices.json": {PLATFORM: voices[PLATFORM], "remote": voices["remote"]},
        "fonts.json": fonts_subset(),
        "country_locale.json": country_locale(source, zones),
        "locale_zones.json": {t: z for t, z in zones.items()},
        "igpu-floors.json": igpu_floors(),
        "igpu-ids.json": igpu_ids(),
        "gen9-ids.json": gen9_ids(),
        "launcher.json": (ROOT / "settings" / "launcher.json").read_text(encoding="utf-8"),  # a byte copy (a str is written as is)
    }


def version_json(pool):
    tag = next(l.split("=", 1)[1].strip() for l in (ROOT / "upstream.env").read_text().splitlines()
               if l.startswith("CHROMIUM_TAG="))
    return {"forkVersion": tag, "poolFormat": POOL_FORMAT, "poolOS": OS, "poolSeeds": pool["seeds"],
            "poolEntries": len(pool["entries"]), "pins": PINS, "cldr": CLDR_VERSION}


def key_problems(pool):
    """Entry keys, and the keys Resolve adds, that the fork's settings/keys.json does not declare."""
    declared = {e["key"] for e in json.loads((ROOT / "settings" / "keys.json").read_text(encoding="utf-8"))["keys"]}
    used = {"timezone:id", "voices:list", "webrtc:ipHandlingPolicy", "canvas:seed", "mediaDevices:seed"}
    for e in pool["entries"]:
        used |= {k for k in e if k not in ("dpr", "fontGroups")}
    used |= {"fonts:list", "fonts:local", "fonts:alias", "fonts:aliasLocal"}
    return sorted(used - declared)


def dumps(v):
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"), sort_keys=False) + "\n"


def write_all(n, source, out_dir):
    pool = draw_pool(n)
    bad = key_problems(pool)
    if bad:
        sys.exit(f"keys not in settings/keys.json: {bad}")
    out_dir.mkdir(parents=True, exist_ok=True)
    files = build_files(n, source)
    files["version.json"] = version_json(pool)
    for name, v in files.items():
        (out_dir / name).write_text(dumps(v), encoding="utf-8")
    with open(out_dir / "pool-windows.json.gz", "wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9, mtime=0) as g:
            g.write(dumps(pool).encode())
    return pool


def read_pool(path):
    with gzip.open(path, "rb") as g:
        return json.loads(g.read())


def check(source, data_dir=DATA, no_pool=False):
    """0 when every committed file equals a fresh generation; 1 and a line per stale file otherwise."""
    stale = []
    committed_ver = data_dir / "version.json"
    if not committed_ver.exists():
        print("missing", committed_ver)
        return 1
    ver = json.loads(committed_ver.read_text(encoding="utf-8"))
    files = build_files(ver["poolSeeds"], source)
    for name, v in files.items():
        p = data_dir / name
        if not p.exists() or p.read_text(encoding="utf-8") != dumps(v):
            stale.append(name)
    pool_path = data_dir / "pool-windows.json.gz"
    if no_pool:
        print("pool: NOT CHECKED (--no-pool)")
    else:
        fresh = draw_pool(ver["poolSeeds"])
        if not pool_path.exists() or read_pool(pool_path) != fresh:
            stale.append("pool-windows.json.gz")
        if ver != version_json(fresh):
            stale.append("version.json")
        bad = key_problems(fresh)
        if bad:
            print("keys not in settings/keys.json:", bad)
            return 1
    for name in stale:
        print("stale:", name)
    return 1 if stale else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--no-pool", action="store_true", help="with --check: skip the pool (needs no pinned deps); says so")
    ap.add_argument("--seeds", type=int, default=DEFAULT_SEEDS)
    ap.add_argument("--cldr", help="likelySubtags.json of cldr-json " + CLDR_VERSION)
    ap.add_argument("--territory", help="territoryInfo.json of cldr-json " + CLDR_VERSION)
    ap.add_argument("--data-dir", type=pathlib.Path, default=DATA)
    a = ap.parse_args(argv)
    src_path = ROOT / "settings" / "country_locale.json"
    if a.cldr or a.territory:
        if not (a.cldr and a.territory):
            sys.exit("--cldr and --territory go together")
        src_path.write_text(json.dumps(build_cldr_source(a.cldr, a.territory), indent=1, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    source = json.loads(src_path.read_text(encoding="utf-8"))
    if a.check:
        return check(source, a.data_dir, a.no_pool)
    pool = write_all(a.seeds, source, a.data_dir)
    print(f"pool: {len(pool['entries'])} entries of {pool['seeds']} seeds ({pool['skipped']} skipped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Light mode (social mode part 3): arm A against arm B of one site, on the host.

Spec docs/superpowers/specs/2026-10-30-fb-light-design.md section 4 C4. Reads net.json, ram.json,
loads.json and (when present) trace.json of each arm; writes kinds, counts, MB, CPU seconds and
load ms only: no URL, no query, no header value. Exit 0, or 3 with "UNMEASURED light: <why>".
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import observe_report as rep  # noqa: E402
import sites  # noqa: E402


class Unmeasured(Exception):
    pass


def _mb(n):
    return round(n / 1e6, 2)


def arm_numbers(arm_dir, label=None):
    d = pathlib.Path(arm_dir)
    label = label or d.name
    missing = [f for f in ("net.json", "ram.json", "loads.json") if not (d / f).exists()]
    if missing:
        raise Unmeasured(f"{label} {' '.join(missing)} missing")
    costs = rep.load_costs(d / "net.json")
    if costs is None:
        raise Unmeasured(f"{label} net.json unreadable")
    ram = rep.ram_summary(d / "ram.json")
    if not ram:
        raise Unmeasured(f"{label} ram.json has no samples")
    kinds = costs["by_kind"]
    zero = {"n": 0, "network": 0, "cache": 0}
    v, js = kinds.get("video", zero), kinds.get("js", zero)
    video_mb = _mb(v["network"] + v["cache"])
    cpu = {"top_s": None, "all_s": None}  # a stock or trace-less arm: unknown, never 0
    if (d / "trace.json").exists():
        by = rep.cpu_by_script(rep.all_events(rep.load_trace(d / "trace.json")))
        tot = [x["run"] + x["compile"] for x in by.values()]
        cpu = {"top_s": round(max(tot, default=0) / 1000, 1), "all_s": round(sum(tot) / 1000, 1)}
    return {
        "kinds": {k: {"n": x["n"], "network_mb": _mb(x["network"]), "cache_mb": _mb(x["cache"])} for k, x in sorted(kinds.items())},
        "total_network_mb": _mb(sum(x["network"] for x in kinds.values())),
        "video": {"n": v["n"], "mb": video_mb, "mb_per_request": round(video_mb / v["n"], 3) if v["n"] else None},
        "js": {"network_mb": _mb(js["network"]), "cache_mb": _mb(js["cache"])},
        "renderer_max": rep.renderer_max(d / "ram.json"),
        "ram": {t: {"peak_mb": x["peak_mb"], "mean_mb": x["mean_mb"]} for t, x in sorted(ram.items())},
        "cpu": cpu,
        "loads": [{"path": x["path"], "ms": x["ms"]} for x in json.loads((d / "loads.json").read_text(encoding="utf-8"))],
    }


def _pct(a, b):
    return None if not a or b is None else round((b - a) / a * 100)


def compare(a, b):
    # bundle hashes do not rotate within the pair's 15-30 minutes: B with no JS from cache did not get the warm copy
    if b["js"]["cache_mb"] == 0:
        raise Unmeasured("b cache cold: JS cache 0 MB in the warm arm")
    keys = {"total_network_mb": lambda n: n["total_network_mb"], "video_requests": lambda n: n["video"]["n"],
            "video_mb": lambda n: n["video"]["mb"], "js_network_mb": lambda n: n["js"]["network_mb"],
            "renderer_peak_mb": lambda n: n["ram"].get("renderer", {}).get("peak_mb"),
            "utility_peak_mb": lambda n: n["ram"].get("utility", {}).get("peak_mb"),
            "cpu_all_s": lambda n: n["cpu"]["all_s"]}
    return {"a": a, "b": b, "delta_pct": {k: _pct(f(a), f(b)) for k, f in keys.items()}}


def render(cmp):
    a, b, dp = cmp["a"], cmp["b"], cmp["delta_pct"]
    rows = [("total network MB", a["total_network_mb"], b["total_network_mb"], dp["total_network_mb"]),
            ("video requests", a["video"]["n"], b["video"]["n"], dp["video_requests"]),
            ("video MB", a["video"]["mb"], b["video"]["mb"], dp["video_mb"]),
            ("video MB per request", a["video"]["mb_per_request"], b["video"]["mb_per_request"], None),
            ("JS network MB", a["js"]["network_mb"], b["js"]["network_mb"], dp["js_network_mb"]),
            ("JS cache MB", a["js"]["cache_mb"], b["js"]["cache_mb"], None),
            ("renderer peak MB", a["ram"].get("renderer", {}).get("peak_mb"), b["ram"].get("renderer", {}).get("peak_mb"), dp["renderer_peak_mb"]),
            ("utility peak MB", a["ram"].get("utility", {}).get("peak_mb"), b["ram"].get("utility", {}).get("peak_mb"), dp["utility_peak_mb"]),
            ("CPU all scripts s", a["cpu"]["all_s"], b["cpu"]["all_s"], dp["cpu_all_s"]),
            ("CPU top script s", a["cpu"]["top_s"], b["cpu"]["top_s"], None)]
    out = ["# Light mode: A against B", "", "One pair is one sample, not a benchmark.", "",
           "| metric | A | B | delta % |", "|---|---|---|---|"]
    out += [f"| {m} | {x} | {y} | {'' if p is None else p} |" for m, x, y, p in rows]
    out += ["", "| process | A peak MB | A mean MB | B peak MB | B mean MB |", "|---|---|---|---|---|"]
    for t in sorted(set(a["ram"]) | set(b["ram"])):
        x, y = a["ram"].get(t, {}), b["ram"].get(t, {})
        out.append(f"| {t} | {x.get('peak_mb', '')} | {x.get('mean_mb', '')} | {y.get('peak_mb', '')} | {y.get('mean_mb', '')} |")
    unk = lambda v: "unknown" if v is None else v  # noqa: E731
    out.append(f"| renderer processes, most | {unk(a.get('renderer_max'))} |  | {unk(b.get('renderer_max'))} |  |")
    out += ["", "| kind | A requests | A network MB | A cache MB | B requests | B network MB | B cache MB |", "|---|---|---|---|---|---|---|"]
    for k in sorted(set(a["kinds"]) | set(b["kinds"])):
        x, y = a["kinds"].get(k, {}), b["kinds"].get(k, {})
        out.append(f"| {k} | {x.get('n', 0)} | {x.get('network_mb', 0)} | {x.get('cache_mb', 0)} | {y.get('n', 0)} | {y.get('network_mb', 0)} | {y.get('cache_mb', 0)} |")
    out += ["", "| page | A ms | B ms |", "|---|---|---|"]
    for i, la in enumerate(a["loads"]):
        lb = b["loads"][i] if i < len(b["loads"]) and b["loads"][i]["path"] == la["path"] else {}
        out.append(f"| `{la['path']}` | {la['ms']} | {lb.get('ms', '')} |")
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--out", required=True)
    ap.add_argument("--md", required=True)
    ap.add_argument("--site", default="facebook")
    x = ap.parse_args(argv)
    try:
        site = sites.load(x.site)
    except sites.SiteError as e:
        print(f"UNMEASURED site: {e}")
        return 3
    rep.use_site(site)
    try:
        na, nb = arm_numbers(x.a, "a"), arm_numbers(x.b, "b")
        cmp = compare(na, nb)
    except Unmeasured as e:
        print(f"UNMEASURED light: {e}")
        return 3
    pathlib.Path(x.out).write_text(json.dumps(cmp, indent=1, sort_keys=True), encoding="utf-8")
    pathlib.Path(x.md).write_text(render(cmp), encoding="utf-8")
    print(f"LIGHT total_network_mb A={na['total_network_mb']} B={nb['total_network_mb']} delta={cmp['delta_pct']['total_network_mb']}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""What one tracking-map arm sent that another did not (fork against stock): endpoints, field paths,
surface matches, and bytes per kind of the page site (the browser's own traffic is a separate total). Reads channels.json, matches.json and net.json of two arm dirs.

Usage: observe_diff.py DIR_A DIR_B [--names fork,stock] [--site https://facebook.com]
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import observe_report  # noqa: E402
import sites  # noqa: E402


def _load(d, name, default):
    p = pathlib.Path(d) / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def _sets(d):
    ch = _load(d, "channels.json", {"endpoints": {}})
    pe = observe_report.public_endpoint
    eps = {pe(e) for e in ch["endpoints"]}
    fields = {f"{pe(e)} {f}" for e, v in ch["endpoints"].items() for f in v["fields"]}
    matches = {f"{pe(m['endpoint'])} {m['field']} {m['surface']}" for m in _load(d, "matches.json", []) if not m["weak"]}
    return eps, fields, matches


def _bytes(row):
    return (row["network"] + row["cache"]) if row else 0


def _bytes_sum(kinds):
    return sum(_bytes(v) for v in kinds.values())


def _site_kinds(d, site):
    costs = observe_report.load_costs(pathlib.Path(d) / "net.json")
    return (costs or {"by_site_kind": {}})["by_site_kind"].get(site, {})


def _split(a, b):
    return {"only_a": sorted(a - b), "only_b": sorted(b - a)}


def diff(dir_a, dir_b, site="https://facebook.com"):
    ea, fa, ma = _sets(dir_a)
    eb, fb, mb = _sets(dir_b)
    ka, kb = (_site_kinds(d, site) for d in (dir_a, dir_b))
    kinds = {k: (_bytes(ka.get(k)), _bytes(kb.get(k))) for k in sorted(set(ka) | set(kb))}
    browser = tuple(_bytes_sum(_site_kinds(d, observe_report.BROWSER)) for d in (dir_a, dir_b))
    return {"endpoints": _split(ea, eb), "fields": _split(fa, fb), "matches": _split(ma, mb), "kinds": kinds,
            "browser": browser}


def render(d, name_a, name_b):
    lines = [f"# Tracking map diff: {name_a} against {name_b}", ""]
    for key in ("endpoints", "fields", "matches"):
        for side, name in (("only_a", name_a), ("only_b", name_b)):
            items = d[key][side]
            lines.append(f"## {key}: only {name} ({len(items)})")
            lines += [f"- `{x}`" for x in items] or ["- none"]
            lines.append("")
    lines += [f"## bytes per kind of the page site (network + cache, MB): {name_a} / {name_b}", ""]
    lines += [f"- {k}: {a / 1e6:.2f} / {b / 1e6:.2f}" for k, (a, b) in d["kinds"].items()]
    lines += ["", f"browser-internal, not compared (MB): {name_a} {d['browser'][0] / 1e6:.2f}",
              f"browser-internal, not compared (MB): {name_b} {d['browser'][1] / 1e6:.2f}"]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dir_a")
    ap.add_argument("dir_b")
    ap.add_argument("--names", default="A,B")
    ap.add_argument("--site", default="facebook", help="site profile in settings/sites")
    a = ap.parse_args(argv)
    try:
        site = sites.load(a.site)
    except sites.SiteError as e:
        print(f"UNMEASURED site: {e}")
        return 3
    observe_report.use_site(site)
    na, nb = a.names.split(",", 1)
    print(render(diff(a.dir_a, a.dir_b, site.surface_site), na, nb))
    return 0


if __name__ == "__main__":
    sys.exit(main())

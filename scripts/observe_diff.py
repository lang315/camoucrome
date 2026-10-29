"""What one tracking-map arm sent that another did not (fork against stock): endpoints, field paths,
surface matches, and bytes per kind. Reads channels.json, matches.json and net.json of two arm dirs.

Usage: observe_diff.py DIR_A DIR_B [--names fork,stock]
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import observe_report  # noqa: E402


def _load(d, name, default):
    p = pathlib.Path(d) / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def _sets(d):
    ch = _load(d, "channels.json", {"endpoints": {}})
    eps = set(ch["endpoints"])
    fields = {f"{e} {f}" for e, v in ch["endpoints"].items() for f in v["fields"]}
    matches = {f"{m['endpoint']} {m['field']} {m['surface']}" for m in _load(d, "matches.json", []) if not m["weak"]}
    return eps, fields, matches


def _split(a, b):
    return {"only_a": sorted(a - b), "only_b": sorted(b - a)}


def diff(dir_a, dir_b):
    ea, fa, ma = _sets(dir_a)
    eb, fb, mb = _sets(dir_b)
    ca = observe_report.load_costs(pathlib.Path(dir_a) / "net.json") or {"by_kind": {}}
    cb = observe_report.load_costs(pathlib.Path(dir_b) / "net.json") or {"by_kind": {}}
    kinds = {}
    for k in sorted(set(ca["by_kind"]) | set(cb["by_kind"])):
        def tot(c):
            v = c["by_kind"].get(k, {"network": 0, "cache": 0})
            return v["network"] + v["cache"]
        kinds[k] = (tot(ca), tot(cb))
    return {"endpoints": _split(ea, eb), "fields": _split(fa, fb), "matches": _split(ma, mb), "kinds": kinds}


def render(d, name_a, name_b):
    lines = [f"# Tracking map diff: {name_a} against {name_b}", ""]
    for key in ("endpoints", "fields", "matches"):
        for side, name in (("only_a", name_a), ("only_b", name_b)):
            items = d[key][side]
            lines.append(f"## {key}: only {name} ({len(items)})")
            lines += [f"- `{x}`" for x in items] or ["- none"]
            lines.append("")
    lines += [f"## bytes per kind (network + cache, MB): {name_a} / {name_b}", ""]
    lines += [f"- {k}: {a / 1e6:.2f} / {b / 1e6:.2f}" for k, (a, b) in d["kinds"].items()]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dir_a")
    ap.add_argument("dir_b")
    ap.add_argument("--names", default="A,B")
    a = ap.parse_args(argv)
    na, nb = a.names.split(",", 1)
    print(render(diff(a.dir_a, a.dir_b), na, nb))
    return 0


if __name__ == "__main__":
    sys.exit(main())

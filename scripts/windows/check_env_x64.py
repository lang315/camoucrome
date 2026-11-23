#!/usr/bin/env python3
"""Refuses a Windows build when out\\<dir>\\environment.x64 (and .x86) changed since the last clean build.

    check_env_x64.py <out-dir> --record   after a clean build: store the hashes beside the out dir
    check_env_x64.py <out-dir>            before a build: exit 1 on a mismatch

Why: `gn.bat` appends its own directory to PATH, ninja runs every compile and link through
`ninja -t msvc -e environment.x64`, so one changed entry changes every command line and rebuilds
the whole graph (about 25k steps, 3 h, 2026-11-20; recipe in memory windows-gn-regen-path-trap).
Run `gn.exe gen` directly with the recorded PATH, not `gn.bat`.

The record is `<out-dir>.envhash.json` (a sibling of the out dir, so a regen of the out dir keeps it).
It holds hashes only: variable names, a sha256 per value, a sha256 per PATH entry. Output names variables and
counts PATH entries; it never prints a value, because PATH holds host paths.
"""
import hashlib
import json
import pathlib
import sys

FILES = ("environment.x64", "environment.x86")


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode("utf-8", "surrogateescape")).hexdigest()


def parse(raw):
    """environment.x64 is NUL-separated NAME=value entries; Windows names are case-insensitive."""
    env = {}
    for item in raw.decode("utf-8", "surrogateescape").split("\0"):
        if "=" in item:
            k, v = item.split("=", 1)
            env[k.upper()] = v
    return env


def snapshot(out):
    snap = {}
    for name in FILES:
        f = out / name
        if f.is_file():
            raw = f.read_bytes()
            env = parse(raw)
            snap[name] = {"file": sha(raw), "vars": {k: sha(v) for k, v in env.items()},
                          "path": [sha(e) for e in env.get("PATH", "").split(";") if e]}
    return snap


def record_path(out):
    return out.parent / (out.name + ".envhash.json")


def diff(old, new):
    """Lines naming what differs, never a value."""
    lines = []
    for name in sorted(set(old) | set(new)):
        if name not in new:
            lines.append(f"{name}: missing now")
        elif name not in old:
            lines.append(f"{name}: not in the record")
        elif old[name]["file"] != new[name]["file"]:
            o, n = old[name], new[name]
            for k in sorted(set(o["vars"]) | set(n["vars"])):
                if o["vars"].get(k) == n["vars"].get(k):
                    continue
                if k == "PATH":
                    a, b = o["path"], n["path"]
                    lines.append(f"{name}: PATH differs ({len(set(a) ^ set(b)) or 'order, 0'} entries)")
                else:
                    lines.append(f"{name}: {k} differs")
            if not any(l.startswith(name) for l in lines):
                lines.append(f"{name}: bytes differ (no variable differs: ordering or padding)")
    return lines


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    out = pathlib.Path(args[0]).resolve()
    snap = snapshot(out)
    if "environment.x64" not in snap:
        sys.exit(f"{out / 'environment.x64'} missing: not a generated out dir")
    rec = record_path(out)
    if "--record" in argv:
        rec.write_text(json.dumps(snap, indent=1, sort_keys=True) + "\n")
        print(f"recorded {', '.join(snap)} -> {rec}")
        return 0
    if not rec.is_file():
        sys.exit(f"no record {rec}: run with --record after a clean build, then check")
    lines = diff(json.loads(rec.read_text()), snap)
    if lines:
        print("REFUSED: the build environment changed since the last clean build (a full rebuild follows):")
        print("\n".join("  " + l for l in lines))
        print("Regenerate with gn.exe directly under the recorded PATH, not gn.bat (docs/windows-build.md).")
        return 1
    print("environment unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

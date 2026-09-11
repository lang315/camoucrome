#!/usr/bin/env python3
"""Packages a release build into a portable archive from GN's own runtime-deps
list (SP6 4.4: no hand-maintained manifest, no installer, no launcher binary).

    scripts/package.py <chromium-src> [--out out/Release] [--platform linux-x64]
                       [--dist dist] [--runtime-deps-file F] [--allow-component]
                       [--changeset-commit SHA] [--no-fonts]
    scripts/package.py --check dist/*.release.json

The archive holds every file `gn desc <out> //chrome:chrome runtime_deps`
names (transitively computed by GN, so a new dependency cannot be missed
silently), the launcher contract, the shipped presets, and a stamp
`camoucrome-release.json` naming the Chromium tag/revision, the change-set
commit and the branch tip the binary was built from. `--check` refuses a set
of stamps whose sources differ (SP6 4.2: binaries across platforms must come
from the same commit).

Two things GN's list needs before it is a manifest, both measured on the
first release build (2026-09-11, 5108 lines): `gn desc` prints its
build-arg WARNINGs to stdout ahead of the paths (path lines are the
whitespace-free ones; out-dir paths are bare, source-tree ones `../../`); and 4803 of the entries are `gen/third_party/devtools-frontend/`
sources that the frontend targets mark as `data` for their own tests while
the shipped copy lives in resources.pak (upstream's installer.py ships none
of them) -- PRUNE drops that tree (and pyproto/, 36 protobuf Python files a
build tool lists as data), and the extracted archive is verified to
open the bundled DevTools front end.

Refusals, each a measured trap: a component build (out/Default -- the .so
graph is not what ships); a chrome/VERSION that disagrees with upstream.env's
tag (version honesty); a runtime dep GN lists that is not on disk (a build
that did not finish).

`--changeset-commit` is required when this script runs from an exported copy
of the change set (the box's ~/camoucrome-cs is a tar extract, not a git
checkout); otherwise the commit is `git rev-parse HEAD` of the repo root.
"""
import argparse
import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGET = "//chrome:chrome"
PRUNE = ("gen/third_party/devtools-frontend/", "pyproto/")  # pyproto: protobuf Python bindings, a tool data dep


def read_args_gn(out):
    text = (out / "args.gn").read_text()
    return {k.strip(): v.strip() for k, _, v in
            (l.partition("=") for l in text.splitlines() if "=" in l and not l.lstrip().startswith("#"))}


def chrome_version(src):
    parts = dict(l.split("=", 1) for l in (src / "chrome" / "VERSION").read_text().split())
    return ".".join(parts[k] for k in ("MAJOR", "MINOR", "BUILD", "PATCH"))


def upstream_env():
    return dict(l.split("=", 1) for l in (ROOT / "upstream.env").read_text().splitlines()
                if "=" in l and not l.startswith("#"))


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def runtime_deps(src, out, file=None):
    """Paths relative to `out`, as GN emits them (../../ for source files)."""
    if file:
        raw = pathlib.Path(file).read_text()
    else:
        raw = subprocess.run(["gn", "desc", str(out), TARGET, "runtime_deps"], cwd=src,
                             capture_output=True, text=True, check=True).stdout
    # ponytail: a path line is one token without whitespace; the WARNING block's lines all
    # have spaces or start with "^" (Chromium paths never contain spaces). Out-dir paths
    # come bare ("chrome", "locales/en-US.pak"), source-tree ones as "../../x".
    lines = [l.strip() for l in raw.splitlines()]
    paths = [l for l in lines if l and " " not in l and not l.startswith("^")]
    # gn lists a few files twice (resources.pak, snapshot_blob.bin, the angledata jsons): once each.
    return list(dict.fromkeys(p for p in paths if not p.startswith(PRUNE)))


def changeset_commit(explicit=None):
    if explicit:
        return explicit
    try:
        return git(ROOT, "rev-parse", "HEAD")
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit(f"{ROOT} is not a git checkout: pass --changeset-commit <sha of the change-set commit>")


def stage(src, out, deps, platform, dist, allow_component, now=None, changeset=None, no_fonts=False):
    args = read_args_gn(out)
    if args.get("is_component_build") == "true" and not allow_component:
        sys.exit("refusing a component build (is_component_build = true): use a release out dir "
                 "(settings/release-args.gn) or --allow-component for a smoke test")
    version = chrome_version(src)
    env = upstream_env()
    if version != env["CHROMIUM_TAG"]:
        sys.exit(f"chrome/VERSION {version} != upstream.env CHROMIUM_TAG {env['CHROMIUM_TAG']}: "
                 "the checkout is not on the pin")
    missing = [d for d in deps if not (out / d).exists()]
    if missing:
        sys.exit(f"{len(missing)} runtime dep(s) GN lists are not on disk (build unfinished?): "
                 f"{missing[:5]}")
    name = f"camoucrome-{version}-{platform}"
    staging = pathlib.Path(dist) / name
    if staging.exists():
        shutil.rmtree(staging)
    for d in deps:
        srcp = (out / d).resolve()
        rel = pathlib.Path(os.path.normpath(d))
        if rel.parts[:2] == ("..", ".."):  # a source-tree file: keep it under its tree path
            rel = pathlib.Path("src", *rel.parts[2:])
        dst = staging / rel
        if srcp.is_dir():
            shutil.copytree(srcp, dst, symlinks=True, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(srcp, dst, follow_symlinks=False)
    shutil.copy2(ROOT / "settings" / "launcher.json", staging / "launcher.json")
    if (ROOT / "settings" / "presets").is_dir():
        shutil.copytree(ROOT / "settings" / "presets", staging / "presets", dirs_exist_ok=True)
    # The open font bundle (scripts/fetch_fonts.py) and its per-OS fontconfig files, in the
    # layout the launcher contract names: <root>/fonts and <root>/settings/fontconfig.
    fonts = (ROOT / "fonts").is_dir() and not no_fonts
    if fonts:
        shutil.copytree(ROOT / "fonts", staging / "fonts", dirs_exist_ok=True)
        shutil.copytree(ROOT / "settings" / "fontconfig", staging / "settings" / "fontconfig", dirs_exist_ok=True)
    stamp = {
        "name": name, "version": version, "platform": platform,
        "chromium_tag": env["CHROMIUM_TAG"], "chromium_rev": env["CHROMIUM_REV"],
        "changeset_commit": changeset_commit(changeset),
        "branch_tip": git(src, "rev-parse", "HEAD"),
        "args_gn": args, "runtime_deps": len(deps), "fonts": bool(fonts),
        "built": (now or datetime.datetime.now(datetime.timezone.utc)).isoformat(timespec="seconds"),
    }
    (staging / "camoucrome-release.json").write_text(json.dumps(stamp, indent=2) + "\n")
    (pathlib.Path(dist) / f"{name}.release.json").write_text(json.dumps(stamp, indent=2) + "\n")
    return staging, stamp


def archive(staging, platform):
    if platform.startswith("win"):
        path = staging.with_suffix(".zip")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(staging.rglob("*")):
                z.write(f, f.relative_to(staging.parent))
    else:
        path = pathlib.Path(str(staging) + ".tar.xz")
        with tarfile.open(path, "w:xz") as t:
            t.add(staging, arcname=staging.name)
    return path


def check(stamp_paths):
    stamps = [json.loads(pathlib.Path(p).read_text()) for p in stamp_paths]
    keys = ("version", "chromium_tag", "chromium_rev", "changeset_commit", "branch_tip")
    bad = [k for k in keys if len({s[k] for s in stamps}) > 1]
    for s in stamps:
        print(f"{s['name']}: {s['changeset_commit'][:10]} tip {s['branch_tip'][:10]} {s['built']}")
    if bad:
        sys.exit(f"stamps disagree on {bad}: not one release")
    print(f"{len(stamps)} stamp(s) agree")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", nargs="?")
    ap.add_argument("--out", default="out/Release")
    ap.add_argument("--platform", default="linux-x64")
    ap.add_argument("--dist", default=str(ROOT / "dist"))
    ap.add_argument("--runtime-deps-file")
    ap.add_argument("--allow-component", action="store_true")
    ap.add_argument("--no-archive", action="store_true")
    ap.add_argument("--no-fonts", action="store_true", help="leave the font bundle out even when fonts/ exists")
    ap.add_argument("--changeset-commit", metavar="SHA",
                    help="change-set commit to stamp (required when the script is not inside a git checkout)")
    ap.add_argument("--check", nargs="+", metavar="STAMP")
    a = ap.parse_args()
    if a.check:
        return check(a.check)
    if not a.src:
        ap.error("chromium-src is required unless --check")
    src = pathlib.Path(a.src).resolve()
    out = (src / a.out).resolve()
    deps = runtime_deps(src, out, a.runtime_deps_file)
    staging, stamp = stage(src, out, deps, a.platform, a.dist, a.allow_component,
                           changeset=a.changeset_commit, no_fonts=a.no_fonts)
    print(f"staged {stamp['runtime_deps']} runtime deps -> {staging}")
    if not a.no_archive:
        path = archive(staging, a.platform)
        print(f"archive {path} ({path.stat().st_size // (1 << 20)} MB)")


if __name__ == "__main__":
    main()

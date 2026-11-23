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

The stale-source check judges only C++ files of the Chromium tree that differ from the pin and are newer
than the main binary; --allow-stale REASON overrides it. It does not catch the `touch -r` replay; see
stale_sources() for what it catches and misses.

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
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile

import check_privacy

ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGET = "//chrome:chrome"
# LGPL-3.0 obligations for the embedded Cursory port: license, GPL text it incorporates,
# notice of changes, and the relinking recipe all ship in the archive.
CURSORY_FILES = (("LICENSE", "LICENSE.cursory"), ("COPYING", "COPYING.cursory"),
                 ("NOTICE", "NOTICE.cursory"), ("RELINK.md", "RELINK.cursory.md"))
CREDITS = pathlib.Path("gen") / "components" / "resources" / "about_credits.html"
# Chromium writes this page when generate_about_credits is unset: every 156 release shipped it.
CREDITS_PLACEHOLDER = b"This is sample credits page."
PRUNE = ("gen/third_party/devtools-frontend/", "pyproto/")  # pyproto: protobuf Python bindings, a tool data dep
# By basename: debug symbols, and Vulkan's mock ICD and validation layer (test-only; vk_swiftshader* stays).
PRUNE_BASENAME = ("VkICD_mock_icd", "VkLayer_khronos_validation")


def pruned(p):
    base = p.rsplit("/", 1)[-1]
    return p.startswith(PRUNE) or base.endswith(".pdb") or base.startswith(PRUNE_BASENAME)


def parse_args_gn(text):
    # ponytail: drops "#..." even inside a quoted string; only the bool args are read here
    lines = (l.partition("#")[0] for l in text.splitlines())
    return {k.strip(): v.strip() for k, _, v in (l.partition("=") for l in lines if "=" in l)}


def read_args_gn(out):
    return parse_args_gn((out / "args.gn").read_text())


def required_args():
    """settings/build-args.gn: what a build MUST set (the codec pair and the fieldtrial flag are page-visible tells)."""
    return parse_args_gn((ROOT / "settings" / "build-args.gn").read_text())


def chrome_version(src):
    parts = dict(l.split("=", 1) for l in (src / "chrome" / "VERSION").read_text().split())
    return ".".join(parts[k] for k in ("MAJOR", "MINOR", "BUILD", "PATCH"))


def upstream_env():
    return dict(l.split("=", 1) for l in (ROOT / "upstream.env").read_text().splitlines()
                if "=" in l and not l.startswith("#"))


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def tree_fingerprint(src, rev):
    """One hash for the change set laid on the pin, whether committed (the box's
    branch) or applied uncommitted (the Windows tree): tracked edits as a full-index
    binary diff against the pin, plus the untracked camoucfg and camoucfg_lgpl files by content."""
    excl = [":(exclude)out", ":(exclude)components/camoucfg", ":(exclude)components/camoucfg_lgpl"]
    stray = [l[3:] for l in git(src, "status", "--porcelain", "--untracked-files=all", "--", ".", *excl).splitlines()
             if l.startswith("??")]
    if stray:
        sys.exit(f"refusing a tree with {len(stray)} untracked file(s) outside out/ and components/camoucfg*: {stray[:5]}")
    # flags pinned so the user's git config (diff.renames, external diff, textconv) cannot change the bytes
    diff = subprocess.run(["git", "diff", "--binary", "--full-index", "--no-renames", "--no-ext-diff", "--no-textconv", rev, "--", ".", *excl],
                          cwd=src, capture_output=True, check=True).stdout
    h = hashlib.sha256(diff + b"\n")
    # camoucfg files keep their bare relative path, so a tree without camoucfg_lgpl hashes as before
    for d, prefix in (("camoucfg", ""), ("camoucfg_lgpl", "camoucfg_lgpl/")):
        cfg = src / "components" / d
        for f in sorted((p for p in cfg.rglob("*") if p.is_file()), key=lambda p: p.relative_to(cfg).as_posix()) if cfg.is_dir() else []:
            h.update(f"{prefix}{f.relative_to(cfg).as_posix()} {hashlib.sha256(f.read_bytes()).hexdigest()}\n".encode())
    return h.hexdigest()


def stale_sources(src, out, rev):
    """C++ files (.cc/.h) of the Chromium tree that differ from the pin (the change set as applied, plus
    untracked ones) and are newer than the main binary: an edit made after the build.
    Catches: packaging a tree whose sources were edited or replaced after the binary was built.
    Misses: the `touch -r` replay of 2026-11-15 (the source keeps an OLD mtime, older than the binary, while its
    content is new), a stale object whose source mtime is old, and non-C++ inputs (BUILD.gn, .gni, generated
    headers). Repo files (additions/, patches/, settings/) are not judged: their mtime is checkout time, and
    content equality with the tree is the sync gate's job (scripts/check_checkout_sync.sh).
    shortcut: mtime vs the main binary only; upgrade when siso's source-to-object map can be queried (ledger L72)."""
    binary = next((out / b for b in ("chrome", "chrome.exe") if (out / b).is_file()), None)
    if binary is None:
        return []
    built = binary.stat().st_mtime
    names = set(git(src, "diff", "--name-only", "--no-renames", rev, "--", ".").splitlines())
    names |= set(git(src, "ls-files", "--others", "--exclude-standard").splitlines())
    return sorted(n for n in names if n.endswith((".cc", ".h")) and (src / n).is_file()
                  and (src / n).stat().st_mtime > built)


def runtime_deps(src, out, file=None):
    """Paths relative to `out`, as GN emits them (../../ for source files)."""
    if file:
        raw = pathlib.Path(file).read_text()
    else:
        raw = subprocess.run([shutil.which("gn") or "gn", "desc", str(out), TARGET, "runtime_deps"], cwd=src,
                             capture_output=True, text=True, check=True).stdout
    # ponytail: a path line is one token without whitespace; the WARNING block's lines all
    # have spaces or start with "^" (Chromium paths never contain spaces). Out-dir paths
    # come bare ("locales/en-US.pak"; executables "./chrome" since 156, made bare here),
    # source-tree ones as "../../x".
    lines = [l.strip() for l in raw.splitlines()]
    paths = [l.removeprefix("./") for l in lines if l and " " not in l and not l.startswith("^")]
    # gn lists a few files twice (resources.pak, snapshot_blob.bin, the angledata jsons): once each.
    return list(dict.fromkeys(p for p in paths if not pruned(p)))


def changeset_commit(explicit=None):
    if explicit:
        return explicit
    try:
        return git(ROOT, "rev-parse", "HEAD")
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit(f"{ROOT} is not a git checkout: pass --changeset-commit <sha of the change-set commit>")


def leak_scan(staging, scan=True):
    """Refuse a staged file whose bytes hold a private term; refuse too when no terms load
    (a scan with nothing to look for measures nothing), unless scan=False (--no-leak-scan:
    the caller scans the archive elsewhere). Returns the value for the stamp."""
    if not scan:
        print("leak scan: UNSCANNED (--no-leak-scan)", file=sys.stderr)
        return "unscanned"
    terms = check_privacy.load_terms()
    if not check_privacy.term_count(terms):
        shutil.rmtree(staging)
        sys.exit("refusing to package: 0 non-empty private terms loaded, so the leak scan would measure nothing "
                 "(set PRIVATE_TERMS or ~/.config/camoucrome/private-terms.json, or pass --no-leak-scan)")
    if not check_privacy.identity_term_count(terms):
        shutil.rmtree(staging)
        sys.exit("refusing to package: 0 non-empty identity (non-GEO) private terms loaded, so binaries would be scanned for nothing")
    print(f"leak scan: {len(terms)} private term group(s) loaded", file=sys.stderr)
    for f in sorted(p for p in staging.rglob("*") if p.is_file() and not p.is_symlink()):
        found = check_privacy.byte_hits(f.read_bytes(), terms, f.name)
        if found:
            shutil.rmtree(staging)
            sys.exit(f"refusing to package: {f.relative_to(staging).as_posix()} holds a private term ({found[0]})")
    return f"scanned:{len(terms)} groups"


def config_keys(src):
    """The key strings the binary knows, for the stamp. The binary knows kAllKeys in the built tree's
    keys.h, not settings/keys.json: refuse when the two name different keys."""
    registry = json.loads((ROOT / "settings" / "keys.json").read_text())["keys"]
    header = (src / "components" / "camoucfg" / "keys.h").read_text()
    m = re.search(r"kAllKeys\s*=\s*\{(.*?)\};", header, re.S)
    if not m:
        sys.exit("refusing: no kAllKeys in the built tree's components/camoucfg/keys.h")
    built, declared = set(re.findall(r"\bk\w+", m.group(1))), {k["name"] for k in registry}
    if built != declared:
        sys.exit(f"refusing: the built tree's keys.h and settings/keys.json differ "
                 f"(only in keys.h: {sorted(built - declared)}, only in keys.json: {sorted(declared - built)})")
    return sorted(k["key"] for k in registry)


def stage(src, out, deps, platform, dist, allow_component, now=None, changeset=None, no_fonts=False, scan=True, allow_stale=None):
    args = read_args_gn(out)
    # GN's default is is_component_build = is_debug, and is_debug defaults to
    # true: only an explicit false (or an explicit is_debug = false) is a release.
    component = args.get("is_component_build", "false" if args.get("is_debug") == "false" else "true")
    if component != "false" and not allow_component:
        sys.exit("refusing a component build (is_component_build not explicitly false in args.gn): use a "
                 "release out dir (settings/release-args.gn) or --allow-component for a smoke test")
    if args.get("camou_observe") != "true":
        sys.exit("refusing a release without camou_observe = true: chrome://observer ships in every release "
                 "(settings/release-args.gn, docs/observer/README.md)")
    # A release is built like stock Chrome: PGO, ThinLTO (and CFI on Linux) come with is_official_build, and the C++ side's
    # timing against a page's regexp replace shows it (measurements/2026-11-13-timing-parity.md). A smoke test of a
    # component build (--allow-component) is not a release.
    if not allow_component and (args.get("is_official_build") != "true" or args.get("chrome_pgo_phase") != "2"):
        sys.exit("refusing a release whose args.gn lacks is_official_build = true and chrome_pgo_phase = 2: a "
                 "non-official build's C++-side timing differs from stock's, from page script "
                 f"(settings/release-args.gn); got is_official_build={args.get('is_official_build')} "
                 f"chrome_pgo_phase={args.get('chrome_pgo_phase')}")
    if args.get("v8_enable_runtime_call_stats") == "true":
        sys.exit("refusing a release with v8_enable_runtime_call_stats = true: the observer's Intl counts are an "
                 "audit-build feature, never a release (docs/observer/README.md)")
    wrong = {k: args.get(k) for k, v in required_args().items() if args.get(k) != v}
    if wrong:
        sys.exit(f"refusing a build whose args.gn differs from settings/build-args.gn (required, page-visible): {wrong}")
    shape = {k: args.get(k) for k, v in parse_args_gn((ROOT / "settings" / "release-args.gn").read_text()).items()
             if args.get(k) != v}
    if shape:
        print(f"warning: args.gn differs from settings/release-args.gn (not page-visible, not refused): {shape}", file=sys.stderr)
    if not {"chrome", "chrome.exe"} & set(deps):
        sys.exit(f"GN's runtime deps ({len(deps)} paths) do not list the main binary: wrong target or out dir?")
    version = chrome_version(src)
    env = upstream_env()
    if version != env["CHROMIUM_TAG"]:
        sys.exit(f"chrome/VERSION {version} != upstream.env CHROMIUM_TAG {env['CHROMIUM_TAG']}: "
                 "the checkout is not on the pin")
    fingerprint = tree_fingerprint(src, env["CHROMIUM_REV"])
    if not (out / CREDITS).is_file():
        sys.exit(f"{out / CREDITS} missing: build //components/resources:about_credits (it ships with chrome)")
    placeholder = CREDITS_PLACEHOLDER in (out / CREDITS).read_bytes()
    if placeholder:
        sys.exit(f"{out / CREDITS} is Chromium's placeholder: set generate_about_credits=true "
                 "(settings/release-args.gn) and rebuild //components/resources:about_credits")
    missing = [d for d in deps if not (out / d).exists()]
    if missing:
        sys.exit(f"{len(missing)} runtime dep(s) GN lists are not on disk (build unfinished?): "
                 f"{missing[:5]}")
    stale = stale_sources(src, out, env["CHROMIUM_REV"])
    if stale and allow_stale:
        print(f"warning: {len(stale)} changed source(s) newer than the main binary, allowed: {allow_stale}", file=sys.stderr)
    elif stale:
        sys.exit(f"refusing: {len(stale)} changed source(s) are newer than the main binary, so the build is stale "
                 f"(rebuild out dir first, or --allow-stale REASON for a deliberate case): {stale[:5]}")
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
    shutil.copy2(ROOT / "LICENSE", staging / "LICENSE")
    shutil.copy2(src / "LICENSE", staging / "LICENSE.chromium")
    shutil.copy2(out / CREDITS, staging / "about_credits.html")
    for src_name, dst in CURSORY_FILES:
        shutil.copy2(ROOT / "additions/camoucfg_lgpl" / src_name, staging / dst)
    shutil.copy2(ROOT / "settings" / "launcher.json", staging / "launcher.json")
    if (ROOT / "settings" / "presets").is_dir():
        shutil.copytree(ROOT / "settings" / "presets", staging / "presets", dirs_exist_ok=True)
    # The open font bundle (scripts/fetch_fonts.py) and its per-OS fontconfig files, in the
    # layout the launcher contract names: <root>/fonts and <root>/settings/fontconfig.
    fonts = (ROOT / "fonts").is_dir() and not no_fonts
    if fonts:
        shutil.copytree(ROOT / "fonts", staging / "fonts", dirs_exist_ok=True)
        shutil.copytree(ROOT / "settings" / "fontconfig", staging / "settings" / "fontconfig", dirs_exist_ok=True)
    scanned = leak_scan(staging, scan)
    stamp = {
        "name": name, "version": version, "platform": platform,
        "chromium_tag": env["CHROMIUM_TAG"], "chromium_rev": env["CHROMIUM_REV"],
        "changeset_commit": changeset_commit(changeset),
        "branch_tip": git(src, "rev-parse", "HEAD"), "tree_fingerprint": fingerprint,
        "config_keys": config_keys(src),
        "args_gn": args, "runtime_deps": len(deps), "fonts": bool(fonts),
        "leak_scan": scanned, "credits_placeholder": placeholder,
        "built": (now or datetime.datetime.now(datetime.timezone.utc)).isoformat(timespec="seconds"),
    }
    (staging / "camoucrome-release.json").write_text(json.dumps(stamp, indent=2) + "\n")
    (pathlib.Path(dist) / f"{name}.release.json").write_text(json.dumps(stamp, indent=2) + "\n")
    return staging, stamp


def _anonymous(ti):
    """tar headers otherwise carry the build account's user name, group name and ids into the public archive."""
    ti.uid = ti.gid = 0
    ti.uname = ti.gname = ""
    return ti


def zip_time(built):
    """The stamp's `built` as a zip date_time: UTC, 2 s grain."""
    t = datetime.datetime.fromisoformat(built).astimezone(datetime.timezone.utc)
    return (t.year, t.month, t.day, t.hour, t.minute, t.second - t.second % 2)


def archive(staging, platform):
    if platform.startswith("win"):
        path = pathlib.Path(str(staging) + ".zip")
        # One entry time for every member, from the stamp: a file's own mtime would be stored in the packager's local time.
        when = zip_time(json.loads((staging / "camoucrome-release.json").read_text())["built"])
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(staging.rglob("*")):
                zi = zipfile.ZipInfo.from_file(f, f.relative_to(staging.parent))
                zi.date_time = when
                if zi.is_dir():
                    z.writestr(zi, b"")
                    continue
                zi.compress_type = zipfile.ZIP_DEFLATED
                with open(f, "rb") as src, z.open(zi, "w", force_zip64=zi.file_size > zipfile.ZIP64_LIMIT) as dst:
                    shutil.copyfileobj(src, dst)
        # The same tree as .tar.xz, the smaller download for tools (201 -> 140 MB on -10); the zip stays for
        # manual install, since Windows 10's tar may not read xz.
        with tarfile.open(str(staging) + ".tar.xz", "w:xz", preset=9) as t:
            t.add(staging, arcname=staging.name, filter=_anonymous)
    else:
        path = pathlib.Path(str(staging) + ".tar.xz")
        with tarfile.open(path, "w:xz") as t:
            t.add(staging, arcname=staging.name, filter=_anonymous)
    return path


def check(stamp_paths):
    stamps = [json.loads(pathlib.Path(p).read_text()) for p in stamp_paths]
    keys = ("version", "chromium_tag", "chromium_rev", "changeset_commit", "tree_fingerprint")
    bad = [k for k in keys if len({s[k] for s in stamps}) > 1]
    for s in stamps:
        print(f"{s['name']}: {s['changeset_commit'][:10]} tip {s['branch_tip'][:10]} {s['built']}")
    unvouched = [s["name"] for s in stamps if s.get("credits_placeholder") is not False]
    if unvouched:
        sys.exit(f"{unvouched}: stamp ships the placeholder credits page, or predates the credits gate")
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
    ap.add_argument("--no-leak-scan", action="store_true",
                    help="skip the staged-bytes private-term scan (release.py scans the archive instead)")
    ap.add_argument("--changeset-commit", metavar="SHA",
                    help="change-set commit to stamp (required when the script is not inside a git checkout)")
    ap.add_argument("--allow-stale", metavar="REASON",
                    help="package although a changed C++ source is newer than the main binary; the reason is printed")
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
                           changeset=a.changeset_commit, no_fonts=a.no_fonts, scan=not a.no_leak_scan, allow_stale=a.allow_stale)
    print(f"staged {stamp['runtime_deps']} runtime deps -> {staging}")
    if not a.no_archive:
        path = archive(staging, a.platform)
        print(f"archive {path} ({path.stat().st_size // (1 << 20)} MB)")
        xz = pathlib.Path(str(staging) + ".tar.xz")
        if path.suffix == ".zip" and xz.is_file():
            print(f"archive {xz} ({xz.stat().st_size // (1 << 20)} MB)")


if __name__ == "__main__":
    main()

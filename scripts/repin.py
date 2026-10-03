#!/usr/bin/env python3
"""The re-pin's three mechanical steps (the procedure itself is
docs/superpowers/specs/repin-runbook.md).

  repin.py target [--platform Windows]     newest version on the Stable channel
  repin.py check <version> [--platform P]  exit 1 unless <version> shipped on Stable
  repin.py retarget <new_tag> <new_rev>    rewrite upstream.env, rename the baselines
                                           named after the old build or revision, and
                                           rewrite those literals in scripts/*.py

retarget does not touch settings/: the captured profiles there record the
Chrome they were captured from, which stays true until they are recaptured. A
value DERIVED from a baseline (settings/audio.json's Windows block cites the
host oracle capture) is not covered by that and must be checked by hand when
the baseline it came from is recaptured.

It also leaves DATED history lines alone -- a comment like
`# 2026-10-02: 507c6ee3e2 -> f89f3a4363 (Chrome stable 154.0.8037.93)` records
what one re-pin did, and both of its right-hand values are the NEXT re-pin's
"old" pair, so a blind rewrite would turn it into a false record of a re-pin
that never happened. HISTORY_RE is that exemption; test_repin.py pins it.
Read `git diff` after a retarget anyway: an undated history sentence in prose
is still rewritten, and only a reader can tell.
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DASH = "https://chromiumdash.appspot.com/fetch_releases?channel=Stable&platform={platform}&num=30"
TAG_RE = re.compile(r"\d+\.\d+\.\d+\.\d+")
REV_RE = re.compile(r"[0-9a-f]{40}")
# A comment line that opens with an ISO date is a record of a past re-pin, not a
# reference to the current pin: left byte-for-byte alone (see the module
# docstring). Anchored on the date so an ordinary comment that merely mentions a
# version is still rewritten.
HISTORY_RE = re.compile(r"\s*#.*\d{4}-\d{2}-\d{2}:")


def _sub(line, pairs):
    for a, b in pairs:
        line = line.replace(a, b)
    return line


def _get(url):
    # curl, not urllib: the python.org build on macOS ships without a CA
    # bundle and fails every https request with CERTIFICATE_VERIFY_FAILED.
    return subprocess.run(["curl", "-fsS", "-m", "30", url], check=True,
                          capture_output=True, text=True).stdout


def newest(versions):
    return max(versions, key=lambda v: tuple(int(x) for x in v.split(".")))


def stable_versions(platform="Windows", fetch=None):
    rows = json.loads((fetch or _get)(DASH.format(platform=platform)))
    versions = [r["version"] for r in rows]
    if not versions:
        sys.exit(f"chromiumdash lists no Stable release for {platform}")
    return versions


def _env(root):
    text = (root / "upstream.env").read_text()
    rev = re.search(r"^CHROMIUM_REV=(\S+)$", text, re.M)
    tag = re.search(r"^CHROMIUM_TAG=(\S+)$", text, re.M)
    if not rev or not tag:
        sys.exit("upstream.env has no CHROMIUM_REV / CHROMIUM_TAG line")
    return text, rev.group(1), tag.group(1)


def retarget(root, new_tag, new_rev):
    if not TAG_RE.fullmatch(new_tag):
        sys.exit(f"'{new_tag}' is not a MAJOR.MINOR.BUILD.PATCH version")
    if not REV_RE.fullmatch(new_rev):
        sys.exit(f"'{new_rev}' is not a 40-character revision")
    text, old_rev, old_tag = _env(root)
    old_build, new_build = old_tag.split(".")[2], new_tag.split(".")[2]
    old_short, new_short = old_rev[:10], new_rev[:10]
    changed = []

    # Only the three shapes a pin takes in a name or a literal; a bare build
    # number is not replaced, so an unrelated 8010 survives.
    pairs = [(f"-{old_build}-stock", f"-{new_build}-stock"),
             (f"-{old_short}-stock", f"-{new_short}-stock"),
             (old_tag, new_tag), (old_short, new_short)]

    for f in sorted((root / "baselines").glob("*")):
        name = f.name
        for a, b in pairs[:2]:
            name = name.replace(a, b)
        if name != f.name:
            subprocess.run(["git", "-C", str(root), "mv", f"baselines/{f.name}", f"baselines/{name}"],
                           check=True)
            changed.append(f"baselines/{name}")

    for f in sorted((root / "scripts").glob("*.py")):
        if f.name in ("repin.py", "test_repin.py"):
            continue
        before = f.read_text()
        after = "".join(line if HISTORY_RE.match(line) else _sub(line, pairs)
                        for line in before.splitlines(keepends=True))
        if after != before:
            f.write_text(after)
            changed.append(f"scripts/{f.name}")

    # Last: upstream.env is what a rerun reads as "old", so it must not move
    # until the renames and rewrites above have all succeeded.
    env = (text.replace(old_rev, new_rev).replace(old_tag, new_tag)
               .replace(f"branch-heads/{old_build}", f"branch-heads/{new_build}"))
    (root / "upstream.env").write_text(env)
    changed.append("upstream.env")
    return changed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("target")
    t.add_argument("--platform", default="Windows")
    c = sub.add_parser("check")
    c.add_argument("version")
    c.add_argument("--platform", default="Windows")
    r = sub.add_parser("retarget")
    r.add_argument("new_tag")
    r.add_argument("new_rev")
    a = ap.parse_args()
    if a.cmd == "target":
        print(newest(stable_versions(a.platform)))
    elif a.cmd == "check":
        if a.version not in stable_versions(a.platform):
            sys.exit(f"{a.version} is not listed as shipped on {a.platform} Stable")
        print(f"{a.version}: shipped on {a.platform} Stable")
    else:
        for path in retarget(ROOT, a.new_tag, a.new_rev):
            print(path)


if __name__ == "__main__":
    main()

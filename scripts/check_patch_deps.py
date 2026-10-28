"""Run Chromium's checkdeps on every directory the change set touches.

`checkdeps` and `gn check` do not run on a .cc-only build, so an illegal
include in a patch (issue #45) passed CI. A violation fails unless a
time-bound entry in settings/checkdeps_exceptions.json names it; an entry that
matches nothing is STALE and fails, so the list shrinks as issues are fixed.

Run: python3 scripts/check_patch_deps.py --src <chromium-src>
"""

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXC_FILE = ROOT / "settings" / "checkdeps_exceptions.json"

# apply.sh copies additions/camoucfg/* flat into components/camoucfg/; there is
# no other additions/ subtree. Anything else maps verbatim (additions/<p> -> <p>).
ADDITIONS_MAP = {"camoucfg": "components/camoucfg"}


def dirs_from_patch(text):
    out = set()
    for m in re.finditer(r"^\+\+\+ b/(\S+)", text, re.M):
        d = os.path.dirname(m.group(1))
        if d:  # a root-level file would mean checking the whole tree
            out.add(d)
    return out


def minimal(dirs):
    return sorted(d for d in dirs
                  if not any(o != d and d.startswith(o + "/") for o in dirs))


def change_set_dirs():
    dirs = set()
    for line in (ROOT / "patches" / "series").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            dirs |= dirs_from_patch((ROOT / "patches" / line.strip()).read_text())
    add = ROOT / "additions"
    for f in add.rglob("*"):
        if f.is_file():
            rel = f.relative_to(add).parent.as_posix()
            top, _, rest = rel.partition("/")
            rel = ADDITIONS_MAP.get(top, top) + ("/" + rest if rest else "")
            if rel != ".":
                dirs.add(rel)
    return dirs


def parse(output, src):
    """(tree-relative file, include) pairs from checkdeps output."""
    res, cur = [], None
    for line in output.splitlines():
        m = re.match(r"ERROR in (\S+)", line)
        if m:
            cur = m.group(1)
            if cur.startswith(src.rstrip("/") + "/"):
                cur = cur[len(src.rstrip("/")) + 1:]
            continue
        m = re.match(r'\s+Illegal include: "([^"]+)"', line)
        if m and cur:
            res.append((cur, m.group(1)))
    return res


def run_checkdeps(d, src):
    p = subprocess.run([sys.executable, "buildtools/checkdeps/checkdeps.py", d],
                       cwd=src, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def run_all(dirs, src, exceptions, runner=run_checkdeps):
    bad = excepted = 0
    seen = set()
    for d in dirs:
        rc, out = runner(d, src)
        found = parse(out, src)
        if rc != 0 and not found:
            print(f"FAIL checkdeps {d}: exit {rc} with no parseable violation")
            bad += 1
        seen.update(found)
    ex = {(e["file"], e["include"]): e for e in exceptions}
    for f, inc in sorted(seen):
        if (f, inc) in ex:
            print(f"EXCEPTION issue {ex[(f, inc)]['issue']} {f}: {inc}")
            excepted += 1
        else:
            print(f"FAIL {f}: illegal include {inc}")
            bad += 1
    for (f, inc), e in ex.items():
        if (f, inc) not in seen:
            print(f"STALE exception (remove it): issue {e['issue']} {f}: {inc}")
            bad += 1
    print(f"check_patch_deps: {len(dirs)} directories, "
          f"{len(seen)} violations ({excepted} excepted)")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    a = ap.parse_args()
    exc = json.loads(EXC_FILE.read_text())
    return run_all(minimal(change_set_dirs()), a.src, exc)


if __name__ == "__main__":
    sys.exit(main())

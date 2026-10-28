"""Every source file in additions/camoucfg/ and additions/camoucfg_lgpl/ must be
listed in its BUILD.gn.

This exists because the omission already happened. coherence_validator.cc and
.h sat in the tree for a full build cycle without being in `sources`, and
nothing complained: a file absent from sources is simply not compiled, so the
archive built, the tests linked, and the component the whole sub-project was
about was never built at all. It was found by hand-comparing hashes between
the repo and the checkout while confirming something unrelated.

A file that is present but unbuilt is the silent direction of this failure --
it looks like coverage and provides none -- which is why the check runs the
same way in both directions:

  every source file        must appear in BUILD.gn   (or it is never compiled)
  every BUILD.gn entry     must exist on disk        (or the build breaks loudly)

The second is not redundant. gn fails on a missing file, so it is caught at
build time -- but this script runs in a second and a build does not, and a
name left behind by a rename is worth reporting where it is cheap.

Run: python3 scripts/check_additions_build.py
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIRS = [ROOT / "additions" / "camoucfg", ROOT / "additions" / "camoucfg_lgpl"]

# .json is data copied by apply.sh, not a compilation unit. invariants.json is
# the one file whose repo location differs from its tree location on purpose:
# it lives in settings/ and apply.sh copies it beside the header.
SOURCE_SUFFIXES = {".cc", ".h"}


def listed_in_build_gn(text):
    """Every quoted "name.ext" inside any sources = [ ... ] block."""
    listed = set()
    for block in re.findall(r"sources\s*=\s*\[(.*?)\]", text, re.S):
        listed.update(re.findall(r'"([^"]+)"', block))
    return listed


def check(directory):
    name = directory.name
    build_gn = directory / "BUILD.gn"
    if not build_gn.exists():
        print(f"FAIL  no BUILD.gn at {build_gn}")
        return 1

    listed = listed_in_build_gn(build_gn.read_text())
    on_disk = {p.name for p in directory.iterdir()
               if p.suffix in SOURCE_SUFFIXES}

    unbuilt = sorted(on_disk - listed)
    missing = sorted(listed - on_disk)

    for f in unbuilt:
        print(f"FAIL  {f} is in additions/{name}/ but not in BUILD.gn, "
              f"so it is never compiled and nothing will say so")
    for f in missing:
        print(f"FAIL  BUILD.gn lists {f}, which does not exist")

    if unbuilt or missing:
        return 1
    print(f"PASS  all {len(on_disk)} source files in additions/{name}/ "
          f"are listed in BUILD.gn")
    return 0


def main():
    return max(check(d) for d in DIRS)


if __name__ == "__main__":
    sys.exit(main())

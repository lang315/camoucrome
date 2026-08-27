"""Every source file in additions/camoucfg/ must be listed in its BUILD.gn.

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
CAMOUCFG = ROOT / "additions" / "camoucfg"
BUILD_GN = CAMOUCFG / "BUILD.gn"

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


def main():
    if not BUILD_GN.exists():
        print(f"FAIL  no BUILD.gn at {BUILD_GN}")
        return 1

    text = BUILD_GN.read_text()
    listed = listed_in_build_gn(text)
    on_disk = {p.name for p in CAMOUCFG.iterdir()
               if p.suffix in SOURCE_SUFFIXES}

    unbuilt = sorted(on_disk - listed)
    missing = sorted(listed - on_disk)

    for name in unbuilt:
        print(f"FAIL  {name} is in additions/camoucfg/ but not in BUILD.gn, "
              f"so it is never compiled and nothing will say so")
    for name in missing:
        print(f"FAIL  BUILD.gn lists {name}, which does not exist")

    if unbuilt or missing:
        return 1
    print(f"PASS  all {len(on_disk)} source files in additions/camoucfg/ "
          f"are listed in BUILD.gn")
    return 0


if __name__ == "__main__":
    sys.exit(main())

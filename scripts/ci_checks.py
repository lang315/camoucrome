#!/usr/bin/env python3
"""Two asserts build-verify.yml makes that a bare `grep` could not.

  ci_checks.py steps FILE    FILE holds the tail of the autoninja output: it must carry "Build Succeeded: N steps"; prints N.
                             N = 0 is allowed: the box tree is built by hand before a slice merges, so a CI rebuild is a near no-op.
  ci_checks.py listed FILE   FILE is `components_unittests --gtest_list_tests --gtest_filter=...`: it must list at least one test.
                             A filter that matches nothing makes the real run print "SUCCESS: all tests passed" with nothing run.
"""
import pathlib
import re
import sys


def build_steps(text):
    m = re.search(r"Build Succeeded: (\d+) steps", text)
    return int(m.group(1)) if m else None


def listed_tests(text):
    return sum(1 for line in text.splitlines() if re.match(r"  \S", line))


def main(argv):
    if len(argv) != 2 or argv[0] not in ("steps", "listed"):
        print(__doc__, file=sys.stderr)
        return 2
    text = pathlib.Path(argv[1]).read_text()
    if argv[0] == "steps":
        n = build_steps(text)
        if n is None:
            print("build: no 'Build Succeeded: N steps' line in the autoninja output")
            return 1
        print(f"build: {n} steps")
        return 0
    n = listed_tests(text)
    print(f"camoucfg unit tests listed by the filter: {n}")
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

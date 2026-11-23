"""The additions/ -> tree map and the patches/series rule, once for Python.

The bash twin is lib_additions.sh; scripts/test_lib_additions.py keeps them equal.
"""

import pathlib

HERE = pathlib.Path(__file__).resolve().parent


def lines(path):
    """The one rule for patches/series and additions_map.txt: trim each line,
    drop blank lines and lines starting with '#'."""
    out = (l.strip() for l in pathlib.Path(path).read_text().splitlines())
    return [l for l in out if l and not l.startswith("#")]


def series(path):
    return lines(path)


def additions_map():
    """[(additions/<dir>, tree dir)] in file order."""
    return [tuple(l.split()) for l in lines(HERE / "additions_map.txt")]


def tree_dir(rel):
    """Tree path of a repo-relative path under additions/ (a dir or a file's
    parent); an unmapped subtree maps verbatim (additions/<p> -> <p>)."""
    for a, t in additions_map():
        if rel == a or rel.startswith(a + "/"):
            return t + rel[len(a):]
    return rel[len("additions/"):]

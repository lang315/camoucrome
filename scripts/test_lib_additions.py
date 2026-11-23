"""One additions/ map and one patches/series rule, in bash and in Python.

  - the two series parsers give the same list on the real series and on a fixture
    with comments, blanks and stray whitespace
  - the two readers give the same additions map
  - apply.sh / rebuild_branch.sh's copy step (copy_additions) copies the same
    files as the inline cp lines it replaced, on the real additions/ and on a
    fixture with a data/ subdirectory
  - a camoucfg_lgpl source maps to components/camoucfg_lgpl (check_patch_deps)
"""

import pathlib
import subprocess
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
import check_patch_deps  # noqa: E402
import lib_additions  # noqa: E402

FIXTURE = "# head\n\na.patch\n  b.patch  \n\t# indented comment\n\n\nc.patch"


def bash(code):
    r = subprocess.run(["bash", "-c", f'. "{SCRIPTS}/lib_additions.sh"; {code}'],
                       capture_output=True, text=True, check=True)
    return r.stdout.splitlines()


def test_series_parsers_agree_on_fixture(tmp_path):
    f = tmp_path / "series"
    f.write_text(FIXTURE)
    assert lib_additions.series(f) == ["a.patch", "b.patch", "c.patch"]
    assert bash(f'series_list "{f}"') == lib_additions.series(f)


def test_series_parsers_agree_on_real_series():
    f = ROOT / "patches" / "series"
    got = lib_additions.series(f)
    assert got and bash(f'series_list "{f}"') == got


def test_map_readers_agree():
    py = [" ".join(p) for p in lib_additions.additions_map()]
    assert "additions/camoucfg_lgpl components/camoucfg_lgpl" in py
    assert bash("additions_map") == py


def old_copy(root, tree):
    """The inline lines apply.sh and rebuild_branch.sh had before the map."""
    code = f'''set -e; ROOT="{root}"; T="{tree}"
mkdir -p "$T/components/camoucfg"
cp "$ROOT"/additions/camoucfg/* "$T/components/camoucfg/"
if [ -d "$ROOT/additions/camoucfg_lgpl" ]; then
  mkdir -p "$T/components/camoucfg_lgpl"
  cp -R "$ROOT"/additions/camoucfg_lgpl/. "$T/components/camoucfg_lgpl/"
fi'''
    subprocess.run(["bash", "-c", code], check=True)


def listing(tree):
    return sorted((p.relative_to(tree).as_posix(), p.read_bytes()) for p in tree.rglob("*") if p.is_file())


@pytest.mark.parametrize("real", [True, False])
def test_copy_step_matches_old_inline_copy(tmp_path, real):
    root = ROOT
    if not real:
        root = tmp_path / "repo"
        (root / "additions/camoucfg").mkdir(parents=True)
        (root / "additions/camoucfg/x.cc").write_text("x\n")
        (root / "additions/camoucfg_lgpl/data").mkdir(parents=True)
        (root / "additions/camoucfg_lgpl/y.cc").write_text("y\n")
        (root / "additions/camoucfg_lgpl/data/d.txt").write_text("d\n")
    old, new = tmp_path / "old", tmp_path / "new"
    old_copy(root, old)
    bash(f'copy_additions "{root}" "{new}"')
    assert listing(new) == listing(old) and listing(new)


def test_lgpl_source_maps_to_its_own_tree_dir():
    assert lib_additions.tree_dir("additions/camoucfg_lgpl") == "components/camoucfg_lgpl"
    assert lib_additions.tree_dir("additions/camoucfg_lgpl/data") == "components/camoucfg_lgpl/data"
    assert lib_additions.tree_dir("additions/camoucfg") == "components/camoucfg"
    dirs = check_patch_deps.change_set_dirs()
    assert "components/camoucfg_lgpl" in dirs and "camoucfg_lgpl" not in dirs

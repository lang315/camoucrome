"""package.py on a fake tree: staging, stamps, archive, and the three refusals."""
import json
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import package  # noqa: E402

TAG = package.upstream_env()["CHROMIUM_TAG"]


@pytest.fixture
def tree(tmp_path):
    src = tmp_path / "src"
    (src / "chrome").mkdir(parents=True)
    major, minor, build, patch = TAG.split(".")
    (src / "chrome" / "VERSION").write_text(f"MAJOR={major}\nMINOR={minor}\nBUILD={build}\nPATCH={patch}\n")
    subprocess.run(["git", "init", "-q"], cwd=src, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "tip"], cwd=src, check=True)
    out = src / "out" / "Release"
    (out / "locales").mkdir(parents=True)
    (out / "args.gn").write_text('is_debug = false\nis_component_build = false\nproprietary_codecs = true\n')
    (out / "chrome").write_bytes(b"\x7fELF")
    (out / "locales" / "en-US.pak").write_bytes(b"pak")
    (src / "chrome" / "data.txt").write_text("x")
    deps = out / "deps.txt"
    deps.write_text("./chrome\n./locales/en-US.pak\n../../chrome/data.txt\n")
    return src, out, deps


def test_stage_copies_every_dep_and_writes_the_stamp(tree, tmp_path):
    src, out, deps = tree
    d = package.runtime_deps(src, out, deps)
    staging, stamp = package.stage(src, out, d, "linux-x64", tmp_path / "dist", False)
    assert (staging / "chrome").read_bytes() == b"\x7fELF"
    assert (staging / "locales" / "en-US.pak").exists()
    assert (staging / "src" / "chrome" / "data.txt").exists()
    assert (staging / "launcher.json").exists() and (staging / "presets" / "chromium-153.json").exists()
    assert stamp["version"] == TAG and stamp["chromium_tag"] == TAG and stamp["runtime_deps"] == 3
    assert len(stamp["branch_tip"]) == 40 and len(stamp["changeset_commit"]) == 40
    assert json.loads((staging / "camoucrome-release.json").read_text()) == stamp
    path = package.archive(staging, "linux-x64")
    assert path.name == f"camoucrome-{TAG}-linux-x64.tar.xz" and path.stat().st_size > 0
    win = package.archive(staging, "win-x64")
    assert win.suffix == ".zip"


def test_explicit_changeset_commit_wins_over_git(tree, tmp_path, monkeypatch):
    src, out, deps = tree
    d = package.runtime_deps(src, out, deps)
    _, stamp = package.stage(src, out, d, "linux-x64", tmp_path / "dist", False, changeset="c" * 40)
    assert stamp["changeset_commit"] == "c" * 40
    monkeypatch.setattr(package, "ROOT", tmp_path / "not-a-repo")
    with pytest.raises(SystemExit, match="not a git checkout"):
        package.changeset_commit(None)


def test_refuses_component_build(tree, tmp_path):
    src, out, deps = tree
    (out / "args.gn").write_text("is_component_build = true\n")
    with pytest.raises(SystemExit, match="component build"):
        package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False)
    package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", True)


def test_refuses_version_off_the_pin(tree, tmp_path):
    src, out, deps = tree
    (src / "chrome" / "VERSION").write_text("MAJOR=154\nMINOR=0\nBUILD=1\nPATCH=0\n")
    with pytest.raises(SystemExit, match="CHROMIUM_TAG"):
        package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False)


def test_refuses_a_missing_runtime_dep(tree, tmp_path):
    src, out, deps = tree
    (out / "chrome").unlink()
    with pytest.raises(SystemExit, match="not on disk"):
        package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False)


def test_check_refuses_mismatched_stamps(tree, tmp_path, capsys):
    src, out, deps = tree
    _, a = package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False)
    b = dict(a, name="camoucrome-x-win-x64", platform="win-x64")
    (tmp_path / "b.json").write_text(json.dumps(b))
    package.check([tmp_path / "dist" / f"{a['name']}.release.json", tmp_path / "b.json"])
    assert "2 stamp(s) agree" in capsys.readouterr().out
    b["branch_tip"] = "0" * 40
    (tmp_path / "b.json").write_text(json.dumps(b))
    with pytest.raises(SystemExit, match="branch_tip"):
        package.check([tmp_path / "dist" / f"{a['name']}.release.json", tmp_path / "b.json"])

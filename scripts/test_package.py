"""package.py on a fake tree: staging, stamps, archive, and the three refusals."""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import package  # noqa: E402

TAG = package.upstream_env()["CHROMIUM_TAG"]
OFFICIAL = "is_official_build = true\nchrome_pgo_phase = 2\n"  # what a release out dir carries (settings/release-args.gn)
REQUIRED = (package.ROOT / "settings" / "build-args.gn").read_text()  # a build must carry these


@pytest.fixture
def tree(tmp_path, monkeypatch):
    src = tmp_path / "src"
    (src / "chrome").mkdir(parents=True)
    major, minor, build, patch = TAG.split(".")
    (src / "chrome" / "VERSION").write_text(f"MAJOR={major}\nMINOR={minor}\nBUILD={build}\nPATCH={patch}\n")
    (src / "LICENSE").write_text("chromium bsd")
    (src / "chrome" / "data.txt").write_text("x")
    (src / "components" / "camoucfg").mkdir(parents=True)
    shutil.copy(package.ROOT / "additions" / "camoucfg" / "keys.h", src / "components" / "camoucfg" / "keys.h")
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps({"<dummy>": ["zz-no-such-term"]}))  # the gate needs terms
    subprocess.run(["git", "init", "-q"], cwd=src, check=True)
    subprocess.run(["git", "add", "-A"], cwd=src, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "tip"], cwd=src, check=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=src, capture_output=True, text=True, check=True).stdout.strip()
    monkeypatch.setattr(package, "upstream_env", lambda: {"CHROMIUM_TAG": TAG, "CHROMIUM_REV": head})
    out = src / "out" / "Release"
    (out / "locales").mkdir(parents=True)
    (out / "args.gn").write_text('is_debug = false\nis_component_build = false\ncamou_observe = true\n' + OFFICIAL + REQUIRED)
    (out / "chrome").write_bytes(b"\x7fELF")
    (out / "locales" / "en-US.pak").write_bytes(b"pak")
    (out / "gen" / "components" / "resources").mkdir(parents=True)
    (out / "gen" / "components" / "resources" / "about_credits.html").write_text("<html>credits</html>")
    deps = out / "deps.txt"
    deps.write_text("WARNING at build arg file: Build argument has no effect.\nenable_nacl = false\n\n"
                    "chrome\nlocales/en-US.pak\n../../chrome/data.txt\nchrome\n"
                    "gen/third_party/devtools-frontend/src/front_end/Tests.js\npyproto/google/protobuf/x.py\n")
    return src, out, deps


def test_runtime_deps_keeps_only_paths_once_and_prunes_the_tool_data(tree):
    src, out, deps = tree
    assert package.runtime_deps(src, out, deps) == ["chrome", "locales/en-US.pak", "../../chrome/data.txt"]


@pytest.mark.parametrize("key", sorted(package.required_args()))
def test_stage_refuses_a_build_without_a_required_arg(tree, tmp_path, key):
    # a hand-made args.gn that forgets ffmpeg_branding or the fieldtrial flag packages cleanly and ships both tells
    src, out, deps = tree
    keep = [l for l in (out / "args.gn").read_text().splitlines() if not l.startswith(key + " ")]
    (out / "args.gn").write_text("\n".join(keep) + "\n")
    with pytest.raises(SystemExit) as e:
        package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False)
    assert key in str(e.value) and "build-args.gn" in str(e.value)


def test_stage_refuses_a_required_arg_with_the_wrong_value(tree, tmp_path):
    src, out, deps = tree
    (out / "args.gn").write_text((out / "args.gn").read_text().replace('ffmpeg_branding = "Chrome"', 'ffmpeg_branding = "Chromium"'))
    with pytest.raises(SystemExit):
        package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False)


def test_stage_warns_when_the_release_shape_differs(tree, tmp_path, capsys):
    src, out, deps = tree
    (out / "args.gn").write_text((out / "args.gn").read_text() + "symbol_level = 2\n")
    package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False)
    assert "symbol_level" in capsys.readouterr().err


def test_build_args_are_a_subset_of_release_args():
    assert package.required_args().items() <= package.parse_args_gn((package.ROOT / "settings" / "release-args.gn").read_text()).items()


def test_tar_headers_carry_no_account_name_or_id(tree, tmp_path):
    src, out, deps = tree
    staging, _ = package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False)
    with tarfile.open(package.archive(staging, "linux-x64")) as t:
        members = t.getmembers()
    assert members and all((m.uid, m.gid, m.uname, m.gname) == (0, 0, "", "") for m in members)


def test_stamp_name_is_the_archive_name_not_the_last_cursory_file(tree, tmp_path):
    src, out, deps = tree
    staging, stamp = package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False)
    assert stamp["name"] == staging.name == f"camoucrome-{TAG}-linux-x64"
    assert (tmp_path / "dist" / f"{staging.name}.release.json").exists()


def test_runtime_deps_strips_the_dot_slash_gn_156_puts_on_executables(tree):
    src, out, deps = tree
    deps.write_text("./chrome\nlocales/en-US.pak\n./chrome_crashpad_handler\nchrome\n")
    assert package.runtime_deps(src, out, deps) == ["chrome", "locales/en-US.pak", "chrome_crashpad_handler"]


def test_stage_copies_every_dep_and_writes_the_stamp(tree, tmp_path):
    src, out, deps = tree
    d = package.runtime_deps(src, out, deps)
    staging, stamp = package.stage(src, out, d, "linux-x64", tmp_path / "dist", False)
    assert (staging / "chrome").read_bytes() == b"\x7fELF"
    assert (staging / "locales" / "en-US.pak").exists()
    assert (staging / "src" / "chrome" / "data.txt").exists()
    assert (staging / "launcher.json").exists() and (staging / "presets" / "chromium-157.json").exists()
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
    (out / "args.gn").write_text("is_component_build = true\ncamou_observe = true\n" + REQUIRED)
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
    b["branch_tip"] = "0" * 40  # the Windows tree's tip is the pin, the box's the branch: not a disagreement
    (tmp_path / "b.json").write_text(json.dumps(b))
    package.check([tmp_path / "dist" / f"{a['name']}.release.json", tmp_path / "b.json"])
    b["tree_fingerprint"] = "0" * 64
    (tmp_path / "b.json").write_text(json.dumps(b))
    with pytest.raises(SystemExit, match="tree_fingerprint"):
        package.check([tmp_path / "dist" / f"{a['name']}.release.json", tmp_path / "b.json"])


def test_font_bundle_is_staged_when_present(tree, tmp_path, monkeypatch):
    src, out, deps = tree
    root = tmp_path / "root"
    (root / "fonts" / "Selawik").mkdir(parents=True)
    (root / "fonts" / "Selawik" / "selawk.ttf").write_bytes(b"ttf")
    (root / "settings" / "fontconfig").mkdir(parents=True)
    (root / "settings" / "fontconfig" / "windows.conf").write_text("<fontconfig/>")
    (root / "settings" / "presets").mkdir()
    (root / "settings" / "launcher.json").write_text("{}")
    shutil.copy(package.ROOT / "settings" / "keys.json", root / "settings" / "keys.json")
    (root / "LICENSE").write_text("mpl")
    (root / "additions" / "camoucfg_lgpl").mkdir(parents=True)
    (root / "additions" / "camoucfg_lgpl" / "LICENSE").write_text("lgpl")
    for n in ("NOTICE", "COPYING", "RELINK.md"):
        (root / "additions" / "camoucfg_lgpl" / n).write_text(n)
    (root / "upstream.env").write_text(package.ROOT.joinpath("upstream.env").read_text())
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x"], cwd=root, check=True)
    for f in ("build-args.gn", "release-args.gn"):
        (root / "settings" / f).write_text((package.ROOT / "settings" / f).read_text())
    monkeypatch.setattr(package, "ROOT", root)
    os.utime(out / "chrome", (4_000_000_000,) * 2)  # the stand-in root was written after the binary; not a stale build
    d = package.runtime_deps(src, out, deps)
    staging, stamp = package.stage(src, out, d, "linux-x64", tmp_path / "dist", False)
    assert stamp["fonts"] is True
    assert (staging / "fonts" / "Selawik" / "selawk.ttf").exists()
    assert (staging / "settings" / "fontconfig" / "windows.conf").exists()
    staging, stamp = package.stage(src, out, d, "linux-x64", tmp_path / "dist2", False, no_fonts=True)
    assert stamp["fonts"] is False and not (staging / "fonts").exists()


def test_refuses_implicit_component_build(tree, tmp_path):
    # GN's default is is_component_build = is_debug, and is_debug defaults to true.
    src, out, deps = tree
    for args in ("", "is_debug = true\n", "import(\"//build/args/x.gn\")\n"):
        (out / "args.gn").write_text(args)
        with pytest.raises(SystemExit, match="component build"):
            package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False)
    (out / "args.gn").write_text("is_debug = true\nis_component_build = false\ncamou_observe = true\n" + OFFICIAL + REQUIRED)
    package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False)


def test_refuses_deps_without_the_binary(tree, tmp_path):
    src, out, deps = tree
    for text in ("", "locales/en-US.pak\n"):
        deps.write_text(text)
        with pytest.raises(SystemExit, match="main binary"):
            package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False)


FUTURE = 4_000_000_000  # fixture binary mtime: newer than every real file under package.ROOT, so only the test's own edits can be stale


def _stage(tree, tmp_path, **kw):
    src, out, deps = tree
    return package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False, **kw)


def _stale_tree(tree, source, newer):
    """Commit a change-set C++ file, then give it an mtime newer or older than the main binary."""
    src, out, _ = tree
    f = src / source
    f.write_text("// new")
    subprocess.run(["git", "add", "-A"], cwd=src, check=True)  # the tree's diff against the pin, not an untracked stray
    os.utime(out / "chrome", (FUTURE, FUTURE))
    os.utime(f, (FUTURE + (1000 if newer else -1000),) * 2)


def test_stage_refuses_a_changed_source_newer_than_the_binary(tree, tmp_path):
    _stale_tree(tree, "chrome/hook.cc", newer=True)
    with pytest.raises(SystemExit) as e:
        _stage(tree, tmp_path)
    assert "chrome/hook.cc" in str(e.value) and "--allow-stale" in str(e.value)


def test_stage_passes_a_changed_source_older_than_the_binary(tree, tmp_path):
    _stale_tree(tree, "chrome/hook.cc", newer=False)
    _stage(tree, tmp_path)


def test_stage_ignores_a_newer_file_the_build_does_not_compile(tree, tmp_path):
    # a merge that touched only scripts/, docs/, client/ leaves no build input newer than the binary
    _stale_tree(tree, "chrome/notes.md", newer=True)
    _stage(tree, tmp_path)


def test_stage_allow_stale_packages_with_a_warning(tree, tmp_path, capsys):
    _stale_tree(tree, "chrome/hook.cc", newer=True)
    _stage(tree, tmp_path, allow_stale="comment-only edit")
    assert "comment-only edit" in capsys.readouterr().err


def _root(tmp_path):
    root = tmp_path / "repo"
    for rel in ("settings/keys.json", "settings/invariants.json", "settings/presets/a.json", "settings/launcher.json",
                "settings/webgl/x.json", "settings/new-unlisted.json", "additions/camoucfg/k.cc", "patches/p.patch",
                "scripts/s.py", "client/c.go", "docs/d.md"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("x")
        os.utime(root / rel, (1000, 1000))
    return root


def _stale(tree, root):
    src, out, _ = tree
    os.utime(out / "chrome", (2000, 2000))
    return package.stale_sources(src, out, package.upstream_env()["CHROMIUM_REV"], root)


@pytest.mark.parametrize("rel", ["settings/keys.json", "settings/invariants.json", "settings/new-unlisted.json",
                                 "additions/camoucfg/k.cc", "patches/p.patch"])
def test_a_newer_build_input_in_the_repo_trips_the_check(tree, tmp_path, rel):
    root = _root(tmp_path)
    os.utime(root / rel, (3000, 3000))
    assert _stale(tree, root) == [rel]


@pytest.mark.parametrize("rel", ["settings/presets/a.json", "settings/launcher.json", "settings/webgl/x.json",
                                 "scripts/s.py", "client/c.go", "docs/d.md"])
def test_a_newer_runtime_or_non_build_file_in_the_repo_passes(tree, tmp_path, rel):
    root = _root(tmp_path)
    os.utime(root / rel, (3000, 3000))
    assert _stale(tree, root) == []

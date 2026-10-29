"""package.py on a fake tree: staging, stamps, archive, and the three refusals."""
import json
import pathlib
import subprocess
import sys
import tarfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import package  # noqa: E402

TAG = package.upstream_env()["CHROMIUM_TAG"]
REQUIRED = (package.ROOT / "settings" / "build-args.gn").read_text()  # a build must carry these


@pytest.fixture
def tree(tmp_path, monkeypatch):
    src = tmp_path / "src"
    (src / "chrome").mkdir(parents=True)
    major, minor, build, patch = TAG.split(".")
    (src / "chrome" / "VERSION").write_text(f"MAJOR={major}\nMINOR={minor}\nBUILD={build}\nPATCH={patch}\n")
    (src / "LICENSE").write_text("chromium bsd")
    (src / "chrome" / "data.txt").write_text("x")
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps({"<dummy>": ["zz-no-such-term"]}))  # the gate needs terms
    subprocess.run(["git", "init", "-q"], cwd=src, check=True)
    subprocess.run(["git", "add", "-A"], cwd=src, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "tip"], cwd=src, check=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=src, capture_output=True, text=True, check=True).stdout.strip()
    monkeypatch.setattr(package, "upstream_env", lambda: {"CHROMIUM_TAG": TAG, "CHROMIUM_REV": head})
    out = src / "out" / "Release"
    (out / "locales").mkdir(parents=True)
    (out / "args.gn").write_text('is_debug = false\nis_component_build = false\n' + REQUIRED)
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
    (out / "args.gn").write_text("is_component_build = true\n" + REQUIRED)
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
    (out / "args.gn").write_text("is_debug = true\nis_component_build = false\n" + REQUIRED)
    package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False)


def test_refuses_deps_without_the_binary(tree, tmp_path):
    src, out, deps = tree
    for text in ("", "locales/en-US.pak\n"):
        deps.write_text(text)
        with pytest.raises(SystemExit, match="main binary"):
            package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False)


def test_refuses_observer_build(tree, tmp_path):
    src, out, deps = tree
    (out / "args.gn").write_text("is_debug = false\nis_component_build = false\ncamou_observe = true\n")
    with pytest.raises(SystemExit, match="camou_observe"):
        package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False)


def test_refuses_observer_build_with_a_comment_or_no_spaces(tree, tmp_path):
    src, out, deps = tree
    for line in ("camou_observe = true # audit build", "camou_observe=true", "camou_observe=true#x"):
        (out / "args.gn").write_text(f"is_debug = false\nis_component_build = false\n{line}\n")
        with pytest.raises(SystemExit, match="camou_observe"):
            package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False)


def test_a_trailing_comment_does_not_hide_a_release_arg(tree, tmp_path):
    src, out, deps = tree
    (out / "args.gn").write_text("is_debug = false  # release\nis_component_build = false # yes\n" + REQUIRED)
    package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False)


def rev(src):
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=src, capture_output=True, text=True, check=True).stdout.strip()


def commit_all(src, msg):
    subprocess.run(["git", "add", "-A", "--", ".", ":(exclude)out", ":(exclude)components/camoucfg"], cwd=src, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", msg], cwd=src, check=True)


def test_fingerprint_is_the_same_for_committed_and_uncommitted_change_sets(tree, tmp_path):
    src, out, deps = tree
    pin = rev(src)
    (src / "components" / "camoucfg").mkdir(parents=True)
    (src / "components" / "camoucfg" / "a.cc").write_text("int a;")
    (src / "chrome" / "data.txt").write_text("patched")
    uncommitted = package.tree_fingerprint(src, pin)
    commit_all(src, "patch")
    assert package.tree_fingerprint(src, pin) == uncommitted


def test_fingerprint_changes_with_the_change_set(tree):
    src, out, deps = tree
    pin = rev(src)
    before = package.tree_fingerprint(src, pin)
    (src / "chrome" / "data.txt").write_text("other")
    assert package.tree_fingerprint(src, pin) != before
    (src / "chrome" / "data.txt").write_text("x")
    (src / "components" / "camoucfg").mkdir(parents=True)
    (src / "components" / "camoucfg" / "k.h").write_text("#define K")
    assert package.tree_fingerprint(src, pin) != before


def test_fingerprint_refuses_a_stray_untracked_file(tree):
    src, out, deps = tree
    (src / "content").mkdir()
    (src / "content" / "stray.cc").write_text("x")
    with pytest.raises(SystemExit, match="stray.cc"):
        package.tree_fingerprint(src, rev(src))


def test_check_refuses_stamps_with_different_fingerprints(tree, tmp_path):
    a = {"name": "a", "version": "1", "chromium_tag": "t", "chromium_rev": "r", "changeset_commit": "c",
         "branch_tip": "x", "tree_fingerprint": "f1", "built": "b", "credits_placeholder": False}
    b = dict(a, name="b", branch_tip="y", tree_fingerprint="f2")
    pa, pb = tmp_path / "a.json", tmp_path / "b.json"
    pa.write_text(json.dumps(a)); pb.write_text(json.dumps(b))
    with pytest.raises(SystemExit, match="tree_fingerprint"):
        package.check([pa, pb])


def test_stage_ships_licences_and_credits_and_names_linux_without_beta(tree, tmp_path):
    src, out, deps = tree
    d = package.runtime_deps(src, out, deps)
    staging, stamp = package.stage(src, out, d, "linux-x64", tmp_path / "dist", False)
    assert staging.name == f"camoucrome-{TAG}-linux-x64"
    assert (staging / "LICENSE.chromium").read_text() == "chromium bsd"
    assert (staging / "about_credits.html").exists() and (staging / "LICENSE").exists()
    for n in ("LICENSE.cursory", "NOTICE.cursory", "COPYING.cursory", "RELINK.cursory.md"):
        assert (staging / n).exists(), n
    assert len(stamp["tree_fingerprint"]) == 64


def test_stage_refuses_a_build_without_credits(tree, tmp_path):
    src, out, deps = tree
    (out / "gen" / "components" / "resources" / "about_credits.html").unlink()
    with pytest.raises(SystemExit, match="about_credits"):
        package.stage(src, out, package.runtime_deps(src, out, deps), "win-x64", tmp_path / "dist", False)


PLACEHOLDER = "<html><body>This is sample credits page.\n\nTo get correct credits page, set `generate_about_credits=true` in args.gn.</body></html>"


def test_stage_refuses_the_placeholder_credits_page(tree, tmp_path):
    src, out, deps = tree
    (out / "gen" / "components" / "resources" / "about_credits.html").write_text(PLACEHOLDER)
    with pytest.raises(SystemExit, match="generate_about_credits"):
        package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False)


def test_check_refuses_a_stamp_that_ships_or_does_not_vouch_for_real_credits(tree, tmp_path):
    src, out, deps = tree
    _, a = package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False)
    assert a["credits_placeholder"] is False
    stamp = tmp_path / "dist" / f"{a['name']}.release.json"
    package.check([stamp])
    old = {k: v for k, v in a.items() if k != "credits_placeholder"}  # a stamp from before the gate (-3 and earlier)
    stamp.write_text(json.dumps(old))
    with pytest.raises(SystemExit, match="credits"):
        package.check([stamp])
    stamp.write_text(json.dumps(dict(a, credits_placeholder=True)))
    with pytest.raises(SystemExit, match="credits"):
        package.check([stamp])


def test_fingerprint_orders_camoucfg_files_by_posix_relpath_bytes(tree):
    # Path ordering is case-insensitive on Windows: the order must not depend on the platform.
    import hashlib
    src, out, deps = tree
    cfg = src / "components" / "camoucfg"
    cfg.mkdir(parents=True)
    for n in ("DEPS", "a.cc", "BUILD.gn"):
        (cfg / n).write_text(n)
    expected = hashlib.sha256(b"\n" + b"".join(
        f"{n} {hashlib.sha256(n.encode()).hexdigest()}\n".encode() for n in ("BUILD.gn", "DEPS", "a.cc"))).hexdigest()
    assert package.tree_fingerprint(src, rev(src)) == expected


def test_gn_is_launched_by_its_resolved_path(tree, monkeypatch):
    """On Windows gn is gn.bat, which CreateProcess does not find under the bare name."""
    src, out, _ = tree
    seen = []
    monkeypatch.setattr(package.shutil, "which", lambda n: f"/depot/{n}.bat")
    monkeypatch.setattr(package.subprocess, "run",
                        lambda cmd, **kw: seen.append(cmd) or subprocess.CompletedProcess(cmd, 0, stdout="chrome\n"))
    assert package.runtime_deps(src, out) == ["chrome"]
    assert seen[0][0] == "/depot/gn.bat"


def test_windows_zip_keeps_the_whole_staging_name(tmp_path):
    """with_suffix would eat the version's last component (.48-windows-x64)."""
    staging = tmp_path / "camoucrome-157.0.8103.15-windows-x64"
    staging.mkdir()
    (staging / "chrome.exe").write_bytes(b"MZ")
    assert package.archive(staging, "windows-x64").name == "camoucrome-157.0.8103.15-windows-x64.zip"


def test_runtime_deps_prunes_symbols_and_test_gpu_layers_by_basename(tmp_path):
    names = ["chrome.dll", "chrome.dll.pdb", "sub/x.exe.pdb", "VkICD_mock_icd.dll", "VkICD_mock_icd.dll.pdb",
             "VkICD_mock_icd.json", "VkLayer_khronos_validation.dll", "VkLayer_khronos_validation.json",
             "vk_swiftshader.dll", "vk_swiftshader_icd.json", "locales/en-US.pak"]
    f = tmp_path / "deps.txt"
    f.write_text("\n".join(names) + "\n")
    assert package.runtime_deps(tmp_path, tmp_path, f) == ["chrome.dll", "vk_swiftshader.dll",
                                                          "vk_swiftshader_icd.json", "locales/en-US.pak"]


def test_gn_missing_from_path_falls_back_to_the_bare_name(tree, monkeypatch):
    src, out, _ = tree
    seen = []
    monkeypatch.setattr(package.shutil, "which", lambda n: None)
    monkeypatch.setattr(package.subprocess, "run",
                        lambda cmd, **kw: seen.append(cmd) or subprocess.CompletedProcess(cmd, 0, stdout="chrome\n"))
    package.runtime_deps(src, out)
    assert seen[0][0] == "gn"


def test_stage_refuses_a_staged_file_holding_a_private_term(tree, tmp_path, monkeypatch):
    src, out, deps = tree
    d = package.runtime_deps(src, out, deps)
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps({"<host-name>": ["Secret-Box-7"]}))
    (out / "chrome").write_bytes(b"\x7fELF..host SECRET-box-7 name..")
    with pytest.raises(SystemExit) as e:
        package.stage(src, out, d, "linux-x64", tmp_path / "dist", False)
    msg = str(e.value)
    assert "chrome" in msg and "<host-name>" in msg and "secret-box-7" not in msg.lower()


def test_stage_refuses_a_term_in_utf16_too(tree, tmp_path, monkeypatch):
    src, out, deps = tree
    d = package.runtime_deps(src, out, deps)
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps({"<host-name>": ["Secret-Box-7"]}))
    (out / "chrome").write_bytes(b"MZ" + "Secret-Box-7".encode("utf-16le"))
    with pytest.raises(SystemExit, match="host-name"):
        package.stage(src, out, d, "linux-x64", tmp_path / "dist", False)


def test_staged_binary_may_hold_a_geo_term_but_staged_text_may_not(tree, tmp_path, monkeypatch):
    src, out, deps = tree
    d = package.runtime_deps(src, out, deps)
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps({"<host-tz-name>": ["Geo-Zone-X"], "<host-name>": ["Secret-Box-7"]}))
    (out / "locales" / "en-US.pak").write_bytes(b"\0..geo-zone-x..")
    package.stage(src, out, d, "linux-x64", tmp_path / "dist", False)
    (src / "chrome" / "data.txt").write_text("geo-zone-x")
    with pytest.raises(SystemExit, match="host-tz-name"):
        package.stage(src, out, d, "linux-x64", tmp_path / "dist", False)


def test_staged_text_with_an_unlisted_suffix_and_no_nul_is_text(tree, tmp_path, monkeypatch):
    src, out, deps = tree
    d = package.runtime_deps(src, out, deps)
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps({"<host-tz-name>": ["Geo-Zone-X"], "<host-name>": ["Secret-Box-7"]}))
    (out / "locales" / "en-US.pak").write_bytes(b"<html>geo-zone-x</html>")  # no NUL: text whatever the suffix
    with pytest.raises(SystemExit, match="host-tz-name"):
        package.stage(src, out, d, "linux-x64", tmp_path / "dist", False)


@pytest.mark.parametrize("terms", [{"<x>": []}, {"<x>": [""]}])
def test_stage_refuses_when_no_non_empty_term_loads(tree, tmp_path, monkeypatch, terms):
    src, out, deps = tree
    d = package.runtime_deps(src, out, deps)
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps(terms))
    with pytest.raises(SystemExit, match="0 non-empty private term"):
        package.stage(src, out, d, "linux-x64", tmp_path / "dist", False)
    assert not list((tmp_path / "dist").glob("*"))


def test_stage_refuses_when_no_terms_are_loaded(tree, tmp_path, monkeypatch):
    src, out, deps = tree
    d = package.runtime_deps(src, out, deps)
    monkeypatch.setenv("PRIVATE_TERMS", "{}")
    with pytest.raises(SystemExit, match="0 non-empty private term"):
        package.stage(src, out, d, "linux-x64", tmp_path / "dist", False)


def test_no_leak_scan_continues_and_the_stamp_says_unscanned(tree, tmp_path, monkeypatch, capsys):
    src, out, deps = tree
    d = package.runtime_deps(src, out, deps)
    monkeypatch.setenv("PRIVATE_TERMS", "{}")
    _, stamp = package.stage(src, out, d, "linux-x64", tmp_path / "dist", False, scan=False)
    assert stamp["leak_scan"] == "unscanned"
    assert "leak scan: UNSCANNED (--no-leak-scan)" in capsys.readouterr().err


def test_stamp_records_the_scanned_group_count(tree, tmp_path):
    src, out, deps = tree
    _, stamp = package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False)
    assert stamp["leak_scan"] == "scanned:1 groups"


def test_stage_passes_when_no_staged_file_holds_a_term(tree, tmp_path, monkeypatch):
    src, out, deps = tree
    d = package.runtime_deps(src, out, deps)
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps({"<host-name>": ["Secret-Box-7"]}))
    package.stage(src, out, d, "linux-x64", tmp_path / "dist", False)


@pytest.mark.parametrize("terms", [{"<host-tz-name>": ["Geo-Zone-X"]}, {"<host-city>": ["Cityville"], "<host-name>": [""]}])
def test_stage_refuses_when_only_geo_terms_load(tree, tmp_path, monkeypatch, terms):
    src, out, deps = tree
    d = package.runtime_deps(src, out, deps)
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps(terms))
    with pytest.raises(SystemExit, match="0 non-empty identity"):
        package.stage(src, out, d, "linux-x64", tmp_path / "dist", False)
    assert not list((tmp_path / "dist").glob("*"))

import json
import pathlib
import sys
import tarfile
import zipfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import release  # noqa: E402

V = "156.0.8078.48"
SHA = "a" * 40


class Gh:
    def __init__(self, listed=(), ci=None, main=SHA):
        self.listed, self.main, self.calls = list(listed), main, []
        self.ci = {"checks": "success", "build-verify": "success"} if ci is None else ci

    def __call__(self, args):
        self.calls.append(args)
        if args[:2] == ["release", "list"]:
            return 0, json.dumps([{"tagName": t, "isDraft": d} for t, d in self.listed])
        if args[:2] == ["run", "list"]:
            return 0, json.dumps([{"workflowName": w, "conclusion": c} for w, c in self.ci.items()])
        if args[:2] == ["release", "create"]:
            return 0, "https://example.invalid/draft"
        raise AssertionError(args)


@pytest.fixture
def stamps(tmp_path):
    out = []
    for plat in ("windows-x64", "linux-x64-beta"):
        p = tmp_path / f"{plat}.json"
        p.write_text(json.dumps({"name": plat, "version": V, "chromium_tag": V, "chromium_rev": "r",
                                 "changeset_commit": SHA, "branch_tip": plat, "tree_fingerprint": "f", "built": "b"}))
        out.append(p)
    notes = tmp_path / "notes.md"
    notes.write_text("Chrome 156.0.8078.48. Unsigned.")
    return out, notes


def run(monkeypatch, gh, stamps, tag=f"v{V}-1", main=SHA, extra=(), remote=False, hits=0):
    monkeypatch.setattr(release, "gh", gh)
    monkeypatch.setattr(release, "origin_main", lambda: main)
    monkeypatch.setattr(release, "remote_tag", lambda t: remote)
    monkeypatch.setattr(release, "privacy_hits", lambda path: hits)
    paths, notes = stamps
    return release.main([tag, *sum((["--stamp", str(p)] for p in paths), []), "--notes", str(notes), *extra])


def refused(monkeypatch, gh, stamps, tmp_path, **kw):
    """Exit 2, no draft created, no SHA256SUMS written."""
    asset = tmp_path / "as" / "x.json"
    asset.parent.mkdir(exist_ok=True)
    asset.write_text("{}")
    extra = kw.pop("extra", ()) or ("--asset", str(asset))
    assert run(monkeypatch, gh, stamps, extra=extra, **kw) == 2
    assert not any(c[:2] == ["release", "create"] for c in gh.calls)
    assert not list(tmp_path.rglob("SHA256SUMS"))


def test_creates_a_draft_and_never_publishes(monkeypatch, stamps):
    gh = Gh()
    assert run(monkeypatch, gh, stamps) == 0
    create = next(c for c in gh.calls if c[:2] == ["release", "create"])
    assert "--draft" in create and not any("--draft=false" in a for a in create)


def test_refuses_a_listed_release_or_draft(monkeypatch, stamps, tmp_path):
    refused(monkeypatch, Gh(listed=[(f"v{V}-1", False)]), stamps, tmp_path)
    refused(monkeypatch, Gh(listed=[(f"v{V}-1", True)]), stamps, tmp_path)


def test_refuses_a_remote_tag(monkeypatch, stamps, tmp_path):
    refused(monkeypatch, Gh(), stamps, tmp_path, remote=True)


@pytest.mark.parametrize("ci", [
    {"checks": "failure", "build-verify": "failure"},
    {"checks": "success", "build-verify": "failure"},
    {"checks": "failure", "build-verify": "success"},
    {"checks": "success"},
    {"build-verify": "success"},
])
def test_refuses_red_or_missing_ci(monkeypatch, stamps, tmp_path, ci):
    refused(monkeypatch, Gh(ci=ci), stamps, tmp_path)


def test_refuses_stamps_off_main(monkeypatch, stamps, tmp_path):
    refused(monkeypatch, Gh(), stamps, tmp_path, main="b" * 40)


def test_refuses_a_tag_that_is_not_the_stamped_version(monkeypatch, stamps, tmp_path):
    refused(monkeypatch, Gh(), stamps, tmp_path, tag="v156.0.8078.49-1")
    refused(monkeypatch, Gh(), stamps, tmp_path, tag="156.0.8078.48")


TERM = "Secret-Box-7"


@pytest.fixture(autouse=True)
def terms(monkeypatch):
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps({"<host-name>": [TERM]}))


def make_zip(path, member_bytes):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("camoucrome/chrome.exe", member_bytes)
    return path


def test_refuses_an_archive_member_holding_a_term(monkeypatch, stamps, tmp_path, capsys):
    z = make_zip(tmp_path / "bad.zip", b"MZ" + TERM.lower().encode())
    refused(monkeypatch, Gh(), stamps, tmp_path, extra=("--asset", str(z)))
    err = capsys.readouterr().err
    assert "bad.zip" in err and "chrome.exe" in err and "<host-name>" in err and TERM.lower() not in err.lower()


def test_refuses_a_tar_xz_member_holding_a_term(monkeypatch, stamps, tmp_path):
    src = tmp_path / "m.bin"
    src.write_bytes(TERM.encode("utf-16le"))
    t = tmp_path / "bad.tar.xz"
    with tarfile.open(t, "w:xz") as tf:
        tf.add(src, arcname="camoucrome/m.bin")
    refused(monkeypatch, Gh(), stamps, tmp_path, extra=("--asset", str(t)))


def test_refuses_a_stamp_holding_a_term(monkeypatch, stamps, tmp_path):
    paths, notes = stamps
    paths[0].write_text(paths[0].read_text().replace('"branch_tip": "windows-x64"', f'"branch_tip": "{TERM}"'))  # not a field --check compares
    refused(monkeypatch, Gh(), stamps, tmp_path)


def test_a_clean_archive_proceeds(monkeypatch, stamps, tmp_path):
    z = make_zip(tmp_path / "ok.zip", b"MZ clean")
    gh = Gh()
    assert run(monkeypatch, gh, stamps, extra=("--asset", str(z))) == 0
    assert any(c[:2] == ["release", "create"] for c in gh.calls)


def test_refuses_when_no_term_groups_load(monkeypatch, stamps, tmp_path):
    monkeypatch.setenv("PRIVATE_TERMS", "{}")
    z = make_zip(tmp_path / "ok.zip", b"MZ clean")
    refused(monkeypatch, Gh(), stamps, tmp_path, extra=("--asset", str(z)))


def test_refuses_a_privacy_hit(monkeypatch, stamps, tmp_path):
    refused(monkeypatch, Gh(), stamps, tmp_path, hits=1)


def test_disagreeing_stamps_return_2(monkeypatch, stamps, tmp_path):
    paths, _ = stamps
    d = json.loads(paths[1].read_text())
    d["tree_fingerprint"] = "other"
    paths[1].write_text(json.dumps(d))
    refused(monkeypatch, Gh(), stamps, tmp_path)


def test_refuses_a_missing_tables_dir(monkeypatch, stamps, tmp_path):
    refused(monkeypatch, Gh(), stamps, tmp_path, extra=("--tables", str(tmp_path / "nope")))


def test_refuses_a_missing_asset(monkeypatch, stamps, tmp_path):
    refused(monkeypatch, Gh(), stamps, tmp_path, extra=("--asset", str(tmp_path / "nope.zip")))


def test_uppercase_suffix_is_privacy_checked(monkeypatch, stamps, tmp_path):
    a = tmp_path / "X.JSON"
    a.write_text("{}")
    seen = []
    monkeypatch.setattr(release, "gh", Gh())
    monkeypatch.setattr(release, "origin_main", lambda: SHA)
    monkeypatch.setattr(release, "remote_tag", lambda t: False)
    monkeypatch.setattr(release, "privacy_hits", lambda p: seen.append(pathlib.Path(p).name) or 0)
    paths, notes = stamps
    argv = [f"v{V}-1", "--stamp", str(paths[0]), "--stamp", str(paths[1]), "--notes", str(notes), "--asset", str(a)]
    assert release.main(argv) == 0
    assert "X.JSON" in seen


def test_checks_text_assets_and_tables_not_archives_and_uploads_sums(monkeypatch, stamps, tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    make_zip(a / "x.zip", b"MZ clean")
    (a / "m.json").write_text("{}")
    t = tmp_path / "tables"
    t.mkdir()
    (t / "t.tsv").write_text("a\tb")
    seen = []
    gh = Gh()
    monkeypatch.setattr(release, "gh", gh)
    monkeypatch.setattr(release, "origin_main", lambda: SHA)
    monkeypatch.setattr(release, "remote_tag", lambda t: False)
    monkeypatch.setattr(release, "privacy_hits", lambda p: seen.append(pathlib.Path(p).name) or 0)
    paths, notes = stamps
    argv = [f"v{V}-1", "--stamp", str(paths[0]), "--stamp", str(paths[1]), "--notes", str(notes),
            "--asset", str(a / "x.zip"), "--asset", str(a / "m.json"), "--tables", str(t)]
    assert release.main(argv) == 0
    assert sorted(seen) == ["m.json", "notes.md", "t.tsv"]
    create = next(c for c in gh.calls if c[:2] == ["release", "create"])
    sums = a / "SHA256SUMS"
    assert str(sums) in create and str(t / "t.tsv") in create
    assert "  x.zip" in sums.read_text()

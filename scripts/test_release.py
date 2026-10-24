import json
import pathlib
import sys
import tarfile
import zipfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import release  # noqa: E402

V = "157.0.8103.15"
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
    notes.write_text(f"Chrome 157.0.8103.15. Unsigned. pip install git+https://example.invalid/r@{SHA}")
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
    refused(monkeypatch, Gh(), stamps, tmp_path, tag="157.0.8103.15")


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


GEO_TERM = "Geo-Zone-X"


def two_classes(monkeypatch):
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps({"<host-tz-name>": [GEO_TERM], "<host-name>": [TERM]}))


def zip_of(path, **members):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in members.items():
            z.writestr(name.replace("__", "."), data)
    return path


def test_binary_member_with_a_geo_term_passes(monkeypatch, stamps, tmp_path):
    two_classes(monkeypatch)
    z = zip_of(tmp_path / "a.zip", icudtl__dat=b"\0..geo-zone-x..")
    assert run(monkeypatch, Gh(), stamps, extra=("--asset", str(z))) == 0


def test_binary_member_with_an_identity_term_is_refused(monkeypatch, stamps, tmp_path):
    two_classes(monkeypatch)
    z = zip_of(tmp_path / "a.zip", chrome__dll=b"\0..secret-box-7..")
    refused(monkeypatch, Gh(), stamps, tmp_path, extra=("--asset", str(z)))


def test_text_member_with_a_geo_term_is_refused(monkeypatch, stamps, tmp_path):
    two_classes(monkeypatch)
    z = zip_of(tmp_path / "a.zip", manifest__JSON=b'{"x": "Geo-Zone-X"}')
    refused(monkeypatch, Gh(), stamps, tmp_path, extra=("--asset", str(z)))


def test_unknown_placeholder_in_a_binary_counts_as_identity(monkeypatch, stamps, tmp_path):
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps({"<something-new>": [GEO_TERM]}))
    z = zip_of(tmp_path / "a.zip", chrome__dll=b"\0..geo-zone-x..")
    refused(monkeypatch, Gh(), stamps, tmp_path, extra=("--asset", str(z)))


def test_a_geo_term_in_a_stamp_is_refused(monkeypatch, stamps, tmp_path):
    two_classes(monkeypatch)
    paths, notes = stamps
    paths[0].write_text(paths[0].read_text().replace('"branch_tip": "windows-x64"', f'"branch_tip": "{GEO_TERM}"'))
    refused(monkeypatch, Gh(), stamps, tmp_path)


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


# Fix round 4: a member is binary only with no text suffix AND a NUL in its bytes; everything else is text.
@pytest.mark.parametrize("name,data", [
    ("about_credits.html", b"<p>Geo-Zone-X</p>"),
    ("camoucrome/chrome.VisualElementsManifest.xml", b"<x>geo-zone-x</x>"),
    ("camoucrome/LICENSE", b"geo-zone-x"),
    ("camoucrome/data.json", b'{"\0": "geo-zone-x"}'),  # a text suffix stays text even with a NUL
])
def test_a_text_member_with_a_geo_term_is_refused(monkeypatch, stamps, tmp_path, name, data):
    two_classes(monkeypatch)
    z = tmp_path / "a.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr(name, data)
    refused(monkeypatch, Gh(), stamps, tmp_path, extra=("--asset", str(z)))


def test_a_suffixless_member_with_a_nul_is_binary(monkeypatch, stamps, tmp_path):
    two_classes(monkeypatch)
    z = tmp_path / "a.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("camoucrome/chrome_sandbox", b"\x7fELF\0geo-zone-x")
    assert run(monkeypatch, Gh(), stamps, extra=("--asset", str(z))) == 0


def test_isp_is_identity_even_in_a_binary(monkeypatch, stamps, tmp_path):
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps({"<host-isp>": [GEO_TERM]}))
    z = zip_of(tmp_path / "a.zip", chrome__dll=b"\0..geo-zone-x..")
    refused(monkeypatch, Gh(), stamps, tmp_path, extra=("--asset", str(z)))


@pytest.mark.parametrize("name", ["setup.exe", "camoucrome.msi", "camoucrome.7z", "notes.txt"])
def test_a_non_archive_asset_is_scanned_as_one_member(monkeypatch, stamps, tmp_path, name):
    a = tmp_path / "as" / name
    a.parent.mkdir()
    a.write_bytes(b"MZ\0" + TERM.encode("utf-16le"))
    refused(monkeypatch, Gh(), stamps, tmp_path, extra=("--asset", str(a)))


@pytest.mark.parametrize("name,mode", [("bad.tgz", "w:gz"), ("bad.tar.bz2", "w:bz2"), ("bad.TAR.GZ", "w:gz")])
def test_tgz_and_tar_star_open_as_tar(monkeypatch, stamps, tmp_path, name, mode):
    src = tmp_path / "m.bin"
    src.write_bytes(b"\0" + TERM.encode())
    t = tmp_path / name
    with tarfile.open(t, mode) as tf:
        tf.add(src, arcname="camoucrome/m.bin")
    refused(monkeypatch, Gh(), stamps, tmp_path, extra=("--asset", str(t)))


@pytest.mark.parametrize("terms", [{"<x>": []}, {"<x>": [""]}, {"<x>": [], "<y>": [""]}])
def test_refuses_when_no_non_empty_term_loads(monkeypatch, stamps, tmp_path, terms):
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps(terms))
    z = make_zip(tmp_path / "ok.zip", b"MZ clean")
    refused(monkeypatch, Gh(), stamps, tmp_path, extra=("--asset", str(z)))


def patched_zip(path, field, value):
    """A one-member zip with a header field set in both the local and central header
    (zipfile cannot write an encrypted member or an unknown method). field: offsets (local, central)."""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("camoucrome/chrome.dll", b"MZ\0 clean")
    b = bytearray(path.read_bytes())
    for sig, off in zip((b"PK\x03\x04", b"PK\x01\x02"), field):
        i = b.index(sig)
        b[i + off:i + off + 2] = value.to_bytes(2, "little")
    path.write_bytes(bytes(b))
    return path


@pytest.mark.parametrize("make", [
    lambda p: patched_zip(p, (6, 8), 0x1),            # flag bit 0, encrypted: RuntimeError, password required
    lambda p: patched_zip(p, (8, 10), 99),            # compression method 99: NotImplementedError
    lambda p: p.write_bytes(b"not a zip") or p,       # BadZipFile
])
def test_an_unreadable_zip_returns_2(monkeypatch, stamps, tmp_path, make):
    z = make(tmp_path / "u.zip")
    refused(monkeypatch, Gh(), stamps, tmp_path, extra=("--asset", str(z)))


def test_an_unreadable_tar_returns_2(monkeypatch, stamps, tmp_path):
    t = tmp_path / "u.tar.gz"
    t.write_bytes(b"not a tar")
    refused(monkeypatch, Gh(), stamps, tmp_path, extra=("--asset", str(t)))


def test_create_targets_the_checked_sha(monkeypatch, stamps):
    gh = Gh()
    assert run(monkeypatch, gh, stamps) == 0
    create = next(c for c in gh.calls if c[:2] == ["release", "create"])
    assert create[create.index("--target") + 1] == SHA


def test_refuses_notes_without_the_full_sha(monkeypatch, stamps, tmp_path):
    notes = stamps[1]
    notes.write_text("Chrome 157.0.8103.15. Unsigned.")
    refused(monkeypatch, Gh(), stamps, tmp_path)
    notes.write_text(f"short {SHA[:12]}")
    refused(monkeypatch, Gh(), stamps, tmp_path)


def archive_with_stamp(path, stamp_bytes):
    path.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("camoucrome-x/chrome.exe", b"MZ clean")
        if stamp_bytes is not None:
            z.writestr("camoucrome-x/camoucrome-release.json", stamp_bytes)
    return path


@pytest.mark.parametrize("embedded,ok", [("given", True), (b'{"changeset_commit": "old"}', False), (None, False)])
def test_platform_archive_must_embed_a_given_stamp(monkeypatch, stamps, tmp_path, embedded, ok):
    paths, _ = stamps
    sb = paths[1].read_bytes() if embedded == "given" else embedded
    z = archive_with_stamp(tmp_path / "as" / f"camoucrome-{V}-windows-x64.zip", sb)
    if ok:
        assert run(monkeypatch, Gh(), stamps, extra=("--asset", str(z))) == 0
    else:
        refused(monkeypatch, Gh(), stamps, tmp_path, extra=("--asset", str(z)))


def test_npm_tarball_is_not_a_platform_archive(monkeypatch, stamps, tmp_path):
    src = tmp_path / "p.json"
    src.write_text("{}")
    t = tmp_path / "camoucrome-0.1.0.tgz"
    with tarfile.open(t, "w:gz") as tf:
        tf.add(src, arcname="package/package.json")
    assert run(monkeypatch, Gh(), stamps, extra=("--asset", str(t))) == 0


@pytest.mark.parametrize("terms", [{"<host-tz-name>": ["Geo-Zone-X"]},
                                   {"<host-tz-name>": ["Geo-Zone-X"], "<host-city>": ["Cityville"], "<host-name>": [""]}])
def test_refuses_when_only_geo_terms_load(monkeypatch, stamps, tmp_path, terms):
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps(terms))
    z = make_zip(tmp_path / "ok.zip", b"MZ clean")
    refused(monkeypatch, Gh(), stamps, tmp_path, extra=("--asset", str(z)))

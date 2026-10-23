import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import release  # noqa: E402

V = "156.0.8078.48"
SHA = "a" * 40


class Gh:
    def __init__(self, existing=(), ci="success", main=SHA):
        self.existing, self.ci, self.main, self.calls = set(existing), ci, main, []

    def __call__(self, args):
        self.calls.append(args)
        if args[:2] == ["release", "view"]:
            return (0 if args[2] in self.existing else 1), ""
        if args[:2] == ["run", "list"]:
            return 0, json.dumps([{"workflowName": w, "conclusion": self.ci} for w in ("checks", "build-verify")])
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


def run(monkeypatch, gh, stamps, tag=f"v{V}-1", main=SHA, extra=()):
    monkeypatch.setattr(release, "gh", gh)
    monkeypatch.setattr(release, "origin_main", lambda: main)
    monkeypatch.setattr(release, "privacy_hits", lambda path: 0)
    paths, notes = stamps
    return release.main([tag, *sum((["--stamp", str(p)] for p in paths), []), "--notes", str(notes), *extra])


def test_creates_a_draft_and_never_publishes(monkeypatch, stamps):
    gh = Gh()
    assert run(monkeypatch, gh, stamps) == 0
    create = next(c for c in gh.calls if c[:2] == ["release", "create"])
    assert "--draft" in create and not any("--draft=false" in a for a in create)


def test_refuses_an_existing_tag_or_draft(monkeypatch, stamps):
    assert run(monkeypatch, Gh(existing={f"v{V}-1"}), stamps) == 2


def test_refuses_red_ci(monkeypatch, stamps):
    assert run(monkeypatch, Gh(ci="failure"), stamps) == 2


def test_refuses_stamps_off_main(monkeypatch, stamps):
    assert run(monkeypatch, Gh(), stamps, main="b" * 40) == 2


def test_refuses_a_tag_that_is_not_the_stamped_version(monkeypatch, stamps):
    assert run(monkeypatch, Gh(), stamps, tag="v156.0.8078.49-1") == 2
    assert run(monkeypatch, Gh(), stamps, tag="156.0.8078.48") == 2


def test_refuses_a_privacy_hit(monkeypatch, stamps):
    monkeypatch.setattr(release, "privacy_hits", lambda path: 1)
    monkeypatch.setattr(release, "gh", Gh())
    monkeypatch.setattr(release, "origin_main", lambda: SHA)
    paths, notes = stamps
    assert release.main([f"v{V}-1", "--stamp", str(paths[0]), "--stamp", str(paths[1]), "--notes", str(notes)]) == 2


def test_disagreeing_stamps_return_2(monkeypatch, stamps):
    paths, _ = stamps
    d = json.loads(paths[1].read_text())
    d["tree_fingerprint"] = "other"
    paths[1].write_text(json.dumps(d))
    assert run(monkeypatch, Gh(), stamps) == 2


def test_checks_text_assets_and_tables_not_archives_and_uploads_sums(monkeypatch, stamps, tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    (a / "x.zip").write_bytes(b"\x00zip")
    (a / "m.json").write_text("{}")
    t = tmp_path / "tables"
    t.mkdir()
    (t / "t.tsv").write_text("a\tb")
    seen = []
    gh = Gh()
    monkeypatch.setattr(release, "gh", gh)
    monkeypatch.setattr(release, "origin_main", lambda: SHA)
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

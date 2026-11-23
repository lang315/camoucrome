"""gen_invariants.py --check must fail on a JSON edit made without a regen."""

import json
import pathlib
import subprocess
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import gen_invariants  # noqa: E402


def test_header_matches_registry():
    assert gen_invariants.main(["--check"]) == 0


def test_json_edit_without_regen_fails_check(tmp_path, monkeypatch, capsys):
    reg = json.loads(pathlib.Path(gen_invariants.REGISTRY).read_text())
    reg["invariants"][1]["id"] = "screen-avail-width-fits-edited"
    edited = tmp_path / "invariants.json"
    edited.write_text(json.dumps(reg))
    monkeypatch.setattr(gen_invariants, "REGISTRY", str(edited))
    assert gen_invariants.main(["--check"]) == 1
    assert "stale" in capsys.readouterr().out


def test_unknown_relation_is_refused(tmp_path, monkeypatch):
    reg = json.loads(pathlib.Path(gen_invariants.REGISTRY).read_text())
    reg["invariants"][0]["relation"] = "no-such-relation"
    bad = tmp_path / "invariants.json"
    bad.write_text(json.dumps(reg))
    monkeypatch.setattr(gen_invariants, "REGISTRY", str(bad))
    with pytest.raises(AssertionError):
        gen_invariants.main(["--check"])


def test_cli_check_rc0():
    r = subprocess.run([sys.executable, str(SCRIPTS / "gen_invariants.py"), "--check"])
    assert r.returncode == 0

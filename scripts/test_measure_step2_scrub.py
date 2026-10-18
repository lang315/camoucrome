"""measure_step2 scrub takes the private terms when CAMOU_SCRUB is unset."""
import argparse
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import measure_step2 as ms  # noqa: E402


def test_scrub_falls_back_to_private_terms(tmp_path, monkeypatch):
    monkeypatch.delenv("CAMOU_SCRUB", raising=False)
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps({"<host-tz>": ["Mars/Olympus"]}))
    src, dst = tmp_path / "run", tmp_path / "out"
    src.mkdir()
    (src / "rows.json").write_text(json.dumps({"tz": "Mars/Olympus"}))
    (src / "tables.md").write_text("| tz | Mars/Olympus |\n")
    assert ms.scrub_cmd(argparse.Namespace(run_dir=str(src), out_dir=str(dst))) == 0
    assert json.loads((dst / "rows.json").read_text()) == {"tz": "<host-tz>"}
    assert "Mars/Olympus" not in (dst / "tables.md").read_text()


def test_scrub_refuses_a_leftover_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("CAMOU_SCRUB", raising=False)
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps({"<host-tz>": ["Mars/Olympus"]}))
    src, dst = tmp_path / "run", tmp_path / "out"
    src.mkdir()
    (src / "rows.json").write_text(json.dumps({"where": "built on DESKTOP-AB12CD3"}))
    (src / "tables.md").write_text("| tz | Mars/Olympus |\n")
    with pytest.raises(SystemExit):
        ms.scrub_cmd(argparse.Namespace(run_dir=str(src), out_dir=str(dst)))
    assert not (dst / "rows.json").exists() and not (dst / "tables.md").exists()


def test_camou_scrub_adds_to_the_private_terms(tmp_path, monkeypatch):
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps({"<host-tz>": ["Mars/Olympus"]}))
    monkeypatch.setenv("CAMOU_SCRUB", json.dumps({"<city>": ["Plantville"]}))
    src, dst = tmp_path / "run", tmp_path / "out"
    src.mkdir()
    (src / "rows.json").write_text(json.dumps({"tz": "Mars/Olympus", "city": "Plantville"}))
    (src / "tables.md").write_text("x\n")
    assert ms.scrub_cmd(argparse.Namespace(run_dir=str(src), out_dir=str(dst))) == 0
    assert json.loads((dst / "rows.json").read_text()) == {"tz": "<host-tz>", "city": "<city>"}

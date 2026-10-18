"""measure_step2 scrub takes the private terms when CAMOU_SCRUB is unset."""
import argparse
import json
import pathlib
import sys

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

"""verify_observe_drive.redroute_scripts (RED D7): the copy it runs the driver from, on the repo and on the host layout."""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import verify_observe_drive as v  # noqa: E402


def _check(root):
    assert (root / "observe_drive.py").exists() and (root / "sites" / "__init__.py").exists()
    doc = json.loads((root / "settings" / "sites" / "testpage" / "site.json").read_text(encoding="utf-8"))
    assert doc["route_paths"] == ["/ajax/nothere"]


def test_repo_layout(tmp_path):
    _check(v.redroute_scripts(tmp_path))


def test_host_layout_copies_scripts_and_sites_only(tmp_path, monkeypatch):
    # the host's observe dir: scripts flat, sites/, settings/sites/, and the login backup, venv and runs beside them
    host = tmp_path / "host"
    (host / "settings").mkdir(parents=True)
    for f in HERE.glob("*.py"):
        (host / f.name).write_bytes(f.read_bytes())
    import shutil
    shutil.copytree(HERE / "sites", host / "sites", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(HERE.parent / "settings" / "sites", host / "settings" / "sites")
    for d in ("backup/fb-login", "venv/Lib", "auto/20261031-000000"):
        (host / d).mkdir(parents=True)
        (host / d / "x").write_text("x")
    monkeypatch.setattr(v, "HERE", host)
    root = v.redroute_scripts(tmp_path / "work")
    _check(root)
    assert not any((root / d).exists() for d in ("backup", "venv", "auto"))

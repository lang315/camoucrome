"""A non-editable install must generate without the repository (spec section 3)."""
import json
import re
import os
import pathlib
import shutil
import subprocess
import sys
import venv

import pytest

CLIENT = pathlib.Path(__file__).resolve().parents[1]
REPO = CLIENT.parents[1]


def copy_tree(dst, ignore_settings_copy=True):
    """client/python + settings/ in a tmp dir, so pip never writes into the real tree."""
    ign = ["build", "*.egg-info"] + (["_settings"] if ignore_settings_copy else [])
    shutil.copytree(REPO / "client" / "python", dst / "client" / "python", ignore=shutil.ignore_patterns(*ign))
    shutil.copytree(REPO / "settings", dst / "settings")


GEN9_HOST = "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00009BC5) Direct3D11 vs_5_0 ps_5_0, D3D11)"


def build_and_run(tmp_path):
    copy_tree(tmp_path / "src")
    wheels = tmp_path / "wheels"
    subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", str(wheels), str(tmp_path / "src" / "client" / "python")],
                   check=True, capture_output=True)
    env_dir = tmp_path / "venv"
    venv.create(env_dir, with_pip=True)
    py = env_dir / ("Scripts" if os.name == "nt" else "bin") / "python"
    wheel = next(wheels.glob("camoucrome-*.whl"))
    subprocess.run([str(py), "-m", "pip", "install", "-q", str(wheel), "browserforge==1.2.4"], check=True)
    env = {k: v for k, v in os.environ.items() if k != "CAMOUCROME_ROOT"}
    out = subprocess.run([str(py), "-m", "camoucrome.gen", "--os", "windows", "--seed", "1", "--host-renderer", GEN9_HOST],
                         cwd=tmp_path, env=env, capture_output=True, text=True)
    return out


@pytest.mark.slow
def test_wheel_generates_outside_the_repository(tmp_path):
    out = build_and_run(tmp_path)
    assert out.returncode == 0, out.stderr
    cfg = json.loads(out.stdout)["config"]
    assert cfg["ua:platform"] == "Windows"
    assert re.search(r"\(0x[0-9A-F]{8}\)", cfg["webGl:renderer"]), "the packaged Gen9 pool was not read"


@pytest.mark.slow
def test_wheel_carries_the_settings_of_the_tree_it_was_built_from(tmp_path):
    copy = tmp_path / "repo"
    copy_tree(copy, ignore_settings_copy=False)
    stale = copy / "client" / "python" / "camoucrome" / "_settings" / "settings" / "locale_zones.json"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text(json.dumps({"zones": {"en-US": ["Europe/Oslo"]}}))  # another tag's copy
    zones = copy / "settings" / "locale_zones.json"
    data = json.loads(zones.read_text())
    data["zones"] = {"en-US": ["Pacific/Honolulu"]}
    zones.write_text(json.dumps(data))
    subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", str(tmp_path / "w"),
                    str(copy / "client" / "python")], check=True, capture_output=True)
    import zipfile
    whl = next((tmp_path / "w").glob("*.whl"))
    with zipfile.ZipFile(whl) as z:
        name = next(n for n in z.namelist() if n.endswith("settings/locale_zones.json"))
        assert json.loads(z.read(name))["zones"] == {"en-US": ["Pacific/Honolulu"]}

import pathlib
import sys
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import client_guard  # noqa: E402


def fake(path):
    return types.SimpleNamespace(__file__=path)


def test_inside_client_passes(tmp_path):
    assert client_guard.check(fake(str(tmp_path / "client" / "python" / "camoucrome" / "__init__.py")), tmp_path) is None


def test_shadow_names_both_paths(tmp_path):
    stale = str(tmp_path / "old" / "client" / "python" / "camoucrome" / "__init__.py")
    msg = client_guard.check(fake(stale), tmp_path / "new")
    assert "old" in msg and str(tmp_path / "new" / "client" / "python") in msg


def test_sibling_prefix_is_not_inside(tmp_path):
    p = tmp_path / "client" / "python2" / "camoucrome" / "__init__.py"
    assert client_guard.check(fake(str(p)), tmp_path) is not None


def test_no_file_attribute(tmp_path):
    assert client_guard.check(types.SimpleNamespace(), tmp_path) is not None


def test_require_exits_3(tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        client_guard.require(fake("/x/camoucrome/__init__.py"), tmp_path)
    assert e.value.code == 3 and "UNMEASURED" in capsys.readouterr().err

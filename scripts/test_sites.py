"""scripts/sites: the site profile loader, the schema of every profile, and facebook's pinned values."""
import json
import pathlib
import shutil
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sites  # noqa: E402

REPO_SITES = HERE.parent / "settings" / "sites"


def test_every_profile_loads():
    names = sorted(p.name for p in REPO_SITES.iterdir() if (p / "site.json").exists())
    assert names == ["facebook", "testpage"]
    for n in names:
        s = sites.load(n)
        assert s.name == n and s.dir == REPO_SITES / n


def test_facebook_pins_the_old_constants():
    s = sites.load("facebook")
    assert s.origin == "https://www.facebook.com"
    assert s.surface_site == "https://facebook.com"
    assert s.cookie_domain == ".facebook.com"
    assert s.logged_in_cookies == ("c_user", "xs")
    assert s.route_paths == ("/ajax/bz", "/ajax/bnzai", "/ajax/qm/")
    assert s.unlink_endpoints == ("/ajax/bz", "/ajax/qm/", "/ajax/webstorage/process_keys/")
    assert s.beacon_path == "/ajax/bz"
    assert s.post_hosts == ("www.facebook.com", "web.facebook.com", "graph.facebook.com", "www.fbsbx.com", "gateway.facebook.com")
    assert s.resource_hosts == ("static.xx.fbcdn.net", "connect.facebook.net")
    assert s.doc_hosts == ("www.facebook.com",)
    assert s.ws_hosts == (".facebook.com",)
    feed = ("/", "/watch/", "/marketplace/", "/messages/", "/me/")
    assert s.pages["3w"] == feed and s.pages["lw"] == feed
    for arm in ("1f", "1c", "lf1", "lf2", "lf3", "lc1", "lc2", "lc3"):
        assert s.pages[arm] == ("/",)
    assert s.backup == "D:\\camou-win\\observe\\backup\\fb-login-20261017"
    assert s.baseline == "D:\\camou-win\\observe\\baseline-facebook.json"
    assert s.ledger == "auto\\ledger.json"
    assert s.cap == {"per_day": 3, "min_gap_min": 15}
    assert s.expired_hint == "session expired: log in with recon.ps1 -Site facebook -Arm 2 -Intl and refresh the backup"


def test_facebook_pop_host_is_the_old_collapse():
    s = sites.load("facebook")
    assert s.pop_host("scontent.fxyz1-1.fna.fbcdn.net") == "scontent.*.fbcdn.net"
    assert s.pop_host("video.fxyz1-1.fna.fbcdn.net") == "*.fna.fbcdn.net"
    assert s.pop_host("media.fxyz1-1.fna.whatsapp.net") == "*.fna.whatsapp.net"
    assert s.pop_host("static.xx.fbcdn.net") == "static.xx.fbcdn.net"


def test_testpage_uses_the_base_hooks():
    s = sites.load("testpage")
    assert s.pop_host("scontent.fxyz1-1.fna.fbcdn.net") == "scontent.fxyz1-1.fna.fbcdn.net"
    assert s.binary_units(b"\x0d\x00\x01\x02\x00\x00{}") is None


@pytest.mark.parametrize("name", ["", "../facebook", "Facebook", "face book", "nosuch"])
def test_bad_or_unknown_names_raise(name):
    with pytest.raises(sites.SiteError):
        sites.load(name)


def _copy_profile(dst_root, name="facebook"):
    d = dst_root / "settings" / "sites" / name
    d.mkdir(parents=True)
    shutil.copy(REPO_SITES / name / "site.json", d / "site.json")
    return d


def test_a_missing_key_raises_and_names_it(tmp_path):
    d = _copy_profile(tmp_path)
    doc = json.loads((d / "site.json").read_text(encoding="utf-8"))
    del doc["route_paths"]
    (d / "site.json").write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(sites.SiteError, match="route_paths"):
        sites.load("facebook", root=tmp_path / "settings" / "sites")


def test_a_bom_is_read(tmp_path):
    d = _copy_profile(tmp_path)
    raw = (d / "site.json").read_bytes()
    (d / "site.json").write_bytes(b"\xef\xbb\xbf" + raw)
    assert sites.load("facebook", root=tmp_path / "settings" / "sites").origin == "https://www.facebook.com"


def test_load_finds_host_layout(tmp_path):
    # the host: D:\camou-win\observe\sites\ (package) and D:\camou-win\observe\settings\sites\ (data)
    shutil.copytree(HERE / "sites", tmp_path / "sites", ignore=shutil.ignore_patterns("__pycache__"))
    _copy_profile(tmp_path)
    import subprocess
    out = subprocess.run([sys.executable, "-c", "import sites; s = sites.load(); print(s.dir)"], cwd=tmp_path,
                         capture_output=True, text=True, check=True).stdout.strip()
    assert pathlib.Path(out) == (tmp_path / "settings" / "sites" / "facebook").resolve()

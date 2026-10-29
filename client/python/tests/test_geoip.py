"""camoucrome.geoip: the zone and locale an exit IP implies, the warn paths, and the echo lookup. No browser."""
import http.server
import json
import os
import pathlib
import sys
import threading
from datetime import datetime, timezone

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camoucrome import geoip  # noqa: E402

pytest.importorskip("maxminddb")
pytest.importorskip("timezonefinder")
FIXTURE = str(pathlib.Path(__file__).resolve().parent / "data" / "geoip-test.mmdb")
REAL_DB = os.path.expanduser(os.environ.get("CAMOU_TEST_GEOIP_DB", "~/.config/camoucrome/dbip-city-lite.mmdb"))


def test_zone_comes_from_the_coordinates():
    assert geoip.lookup("192.0.2.5", FIXTURE) == {"country": "US", "timezone": "America/New_York", "locale": "en-US"}
    assert geoip.lookup("198.51.100.5", FIXTURE)["timezone"] == "America/Los_Angeles"  # same country, another zone


def test_a_records_own_time_zone_wins_over_its_coordinates():
    assert geoip.lookup("203.0.113.7", FIXTURE) == {"country": "FR", "timezone": "Europe/Paris", "locale": "fr-FR"}


def test_a_country_without_a_locale_row_still_gives_its_zone():
    assert geoip.lookup("2001:db8::1", FIXTURE) == {"country": "SG", "timezone": "Asia/Singapore", "locale": None}


@pytest.mark.parametrize("ip,why", [("2001:db8:1::1", "no time zone"), ("2001:db8:ffff::1", "not in the database"), ("nonsense", "nonsense")])
def test_unresolvable_ips_raise_with_a_reason(ip, why):
    with pytest.raises(geoip.GeoIPError, match=why):
        geoip.lookup(ip, FIXTURE)


def test_no_database_and_a_missing_file_raise():
    with pytest.raises(geoip.GeoIPError, match="no geoip database"):
        geoip.lookup("192.0.2.5", None)
    with pytest.raises(geoip.GeoIPError, match="not found"):
        geoip.lookup("192.0.2.5", "/nonexistent.mmdb")


def test_the_environment_names_the_database(monkeypatch):
    monkeypatch.setenv("CAMOU_GEOIP_DB", FIXTURE)
    assert geoip.lookup("192.0.2.5")["country"] == "US"


@pytest.mark.parametrize("country,locale", [("US", "en-US"), ("CA", "en-CA"), ("BE", "fr-BE"), ("fr", "fr-FR"), ("SG", None), (None, None)])
def test_locale_for_takes_the_first_row_of_the_file(country, locale):
    assert geoip.locale_for(country) == locale


WINTER = datetime(2026, 1, 15, 12, tzinfo=timezone.utc)
SUMMER = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)


def test_check_zone_compares_offsets_now_not_names():
    assert geoip.check_zone("Europe/Paris", "Europe/Berlin", WINTER) is None  # two ids, one offset
    assert "contradicts" in geoip.check_zone("Asia/Tokyo", "Europe/Paris", WINTER)
    msg = geoip.check_zone("Europe/London", "Europe/Paris", SUMMER)  # BST against CEST: one hour apart in July
    assert "UTC+01:00" in msg and "UTC+02:00" in msg


def test_check_zone_names_both_offsets():
    msg = geoip.check_zone("Asia/Tokyo", "Europe/Paris", WINTER)
    assert "UTC+09:00" in msg and "UTC+01:00" in msg


def test_check_config_warns_on_a_contradiction_and_stays_quiet_on_a_match():
    assert geoip.check_config({"timezone:id": "America/New_York"}, exit_ip_="192.0.2.5", db=FIXTURE) == []
    [msg] = geoip.check_config({"timezone:id": "Asia/Tokyo"}, exit_ip_="192.0.2.5", db=FIXTURE)
    assert "Asia/Tokyo" in msg and "America/New_York" in msg


def test_check_config_warns_instead_of_raising_when_the_ip_cannot_be_resolved():
    [msg] = geoip.check_config({"timezone:id": "Asia/Tokyo"}, exit_ip_="2001:db8:ffff::1", db=FIXTURE)
    assert "could not be checked" in msg and "not in the database" in msg
    [msg] = geoip.check_config({"timezone:id": "Asia/Tokyo"}, exit_ip_="192.0.2.5", db=None)
    assert "no geoip database" in msg


def test_check_config_has_nothing_to_check_without_a_zone():
    assert geoip.check_config({}, exit_ip_="192.0.2.5", db=FIXTURE) == []
    assert geoip.check_config(None, exit_ip_="192.0.2.5", db=FIXTURE) == []


def test_main_prints_json_and_the_warning(capsys):
    assert geoip.main(["--ip", "192.0.2.5", "--db", FIXTURE, "--check-zone", "Asia/Tokyo"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["timezone"] == "America/New_York" and "contradicts" in out["warning"]
    assert geoip.main(["--ip", "2001:db8:ffff::1", "--db", FIXTURE]) == 2
    assert "not in the database" in json.loads(capsys.readouterr().out)["error"]


def test_check_config_warns_on_an_unknown_configured_zone():
    [msg] = geoip.check_config({"timezone:id": "Not/AZone"}, exit_ip_="192.0.2.5", db=FIXTURE)
    assert "Not/AZone" in msg and "could not be checked" in msg


def test_lookup_turns_unusable_coordinates_and_zones_into_geoip_error(monkeypatch):
    def boom(record):
        raise ValueError("Longitude out of range")
    monkeypatch.setattr(geoip, "zone_of", boom)
    with pytest.raises(geoip.GeoIPError, match="unusable time zone"):
        geoip.lookup("192.0.2.5", FIXTURE)
    monkeypatch.setattr(geoip, "zone_of", lambda record: "Not/AZone")
    with pytest.raises(geoip.GeoIPError, match="unusable time zone"):
        geoip.lookup("192.0.2.5", FIXTURE)
    [msg] = geoip.check_config({"timezone:id": "Asia/Tokyo"}, exit_ip_="192.0.2.5", db=FIXTURE)
    assert "could not be checked" in msg


def test_main_reports_an_invalid_check_zone_as_a_warning(capsys):
    assert geoip.main(["--ip", "192.0.2.5", "--db", FIXTURE, "--check-zone", "Not/AZone"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["timezone"] == "America/New_York" and "Not/AZone" in out["warning"]


class EchoProxy(http.server.ThreadingHTTPServer):
    """An HTTP proxy that answers every GET with `body`, after one 407 round when `auth` is set."""

    def __init__(self, body, auth=False):
        self.seen = []
        self.connections = 0
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                authed = bool(self.headers.get("Proxy-Authorization"))
                outer.seen.append((self.path, authed))
                if auth and not authed:
                    self.send_response(407)
                    self.send_header("Proxy-Authenticate", 'Basic realm="t"')
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        super().__init__(("127.0.0.1", 0), H)
        threading.Thread(target=self.serve_forever, daemon=True).start()

    def get_request(self):
        self.connections += 1
        return super().get_request()

    @property
    def server(self_):  # noqa: N805 - the proxy URL, named like Playwright's option
        return f"http://127.0.0.1:{self_.server_port}"


def test_exit_ip_asks_the_echo_service_through_the_proxy_with_credentials():
    p = EchoProxy(b"203.0.113.9\n", auth=True)
    try:
        got = geoip.exit_ip({"server": p.server, "username": "u", "password": "p@ss"}, urls=("http://echo.test/",))
    finally:
        p.shutdown()
    assert got == "203.0.113.9"
    assert p.seen and all(path == "http://echo.test/" for path, _ in p.seen)


def test_exit_ip_moves_on_past_a_service_that_answers_garbage_and_then_gives_up():
    p = EchoProxy(b"<html>blocked</html>")
    try:
        with pytest.raises(geoip.GeoIPError, match="no echo service answered"):
            geoip.exit_ip({"server": p.server}, urls=("http://a.test/", "http://b.test/"))
    finally:
        p.shutdown()
    assert [path for path, _ in p.seen] == ["http://a.test/", "http://b.test/"]


# Pins read from the database file itself (DB-IP Lite), not from memory, kept OUTSIDE the repository because the
# addresses are public ones the gate (loopback and RFC 5737 only) does not allow: {"build_epoch": N, "pins": {ip: zone}}.
# Keep two addresses of one country in two zones (a US pair): only the coordinates tell those apart.
PINS_FILE = os.path.expanduser(os.environ.get("CAMOU_TEST_GEOIP_PINS", "~/.config/camoucrome/geoip-pins.json"))


@pytest.fixture
def real_pins():
    if not os.path.isfile(REAL_DB):
        pytest.skip("no DB-IP Lite file (set CAMOU_TEST_GEOIP_DB)")
    if not os.path.isfile(PINS_FILE):
        pytest.skip(f"no pins file at {PINS_FILE} (set CAMOU_TEST_GEOIP_PINS)")
    pins = json.loads(pathlib.Path(PINS_FILE).read_text())
    import maxminddb
    with maxminddb.open_database(REAL_DB) as r:
        if r.metadata().build_epoch != pins["build_epoch"]:
            pytest.skip(f"database build {r.metadata().build_epoch} differs from the pinned {pins['build_epoch']}: re-pin {PINS_FILE} from this file")
    return pins["pins"]


def test_real_database_zones_match_the_pins(real_pins):
    assert len(real_pins) >= 2
    for ip, zone in real_pins.items():
        assert geoip.lookup(ip, REAL_DB)["timezone"] == zone, ip


# generate(): item 13 at generation time, where the locale's voices, languages and Accept-Language are built.
def _gen(**kw):
    pytest.importorskip("browserforge")
    from camoucrome import gen
    return gen.generate("windows", seed=1, geoip_db=FIXTURE, **kw)["config"]


def test_generate_derives_the_zone_and_locale_from_the_exit_ip():
    cfg = _gen(exit_ip="203.0.113.7")
    assert cfg["timezone:id"] == "Europe/Paris" and cfg["locale:tag"] == "fr-FR"
    assert cfg["navigator.languages"][0] == "fr-FR"
    assert _gen(exit_ip="198.51.100.5")["timezone:id"] == "America/Los_Angeles"


def test_generate_keeps_an_explicit_zone_or_locale_over_the_ip():
    cfg = _gen(exit_ip="203.0.113.7", timezone="Asia/Tokyo")
    assert cfg["timezone:id"] == "Asia/Tokyo" and cfg["locale:tag"] == "fr-FR"
    assert _gen(exit_ip="203.0.113.7", locale="de-DE")["locale:tag"] == "de-DE"


def test_generate_warns_and_falls_back_when_the_ip_is_not_resolved():
    with pytest.warns(geoip.GeoIPWarning, match="not resolved"):
        cfg = _gen(exit_ip="2001:db8:ffff::1")
    assert cfg["timezone:id"]  # drawn as without an exit IP


def test_generate_warns_for_a_country_without_a_locale_row():
    with pytest.warns(geoip.GeoIPWarning, match="no locale for country SG"):
        cfg = _gen(exit_ip="2001:db8::1")
    assert cfg["timezone:id"] == "Asia/Singapore"


# launch(geoip=...): checks and warns, never rewrites.
import warnings as _warnings  # noqa: E402

import camoucrome  # noqa: E402
from test_launcher import FakePlaywright  # noqa: E402


def test_launch_warns_on_a_contradicting_zone_and_still_launches():
    pw = FakePlaywright()
    cfg = {"timezone:id": "Asia/Tokyo"}
    with pytest.warns(geoip.GeoIPWarning, match="contradicts"):
        camoucrome.launch(pw, "/x/chrome", config=cfg, user_data_dir="/tmp/p", geoip=FIXTURE, exit_ip="192.0.2.5")
    assert json.loads(pw.chromium.kw["env"]["CAMOU_CONFIG"]) == cfg  # not rewritten


def test_launch_checks_the_zone_a_preset_gives_and_the_explicit_config_wins():
    # preset_loader.cc maps a preset's "timezone" to timezone:id: the documented preset + seeds launch has no zone in config
    with pytest.warns(geoip.GeoIPWarning, match="contradicts"):
        camoucrome.launch(FakePlaywright(), "/x/chrome", preset={"timezone": "Asia/Tokyo"}, config={"canvas:seed": 7},
                          user_data_dir="/tmp/p", geoip=FIXTURE, exit_ip="192.0.2.5")
    with _warnings.catch_warnings():
        _warnings.simplefilter("error")
        camoucrome.launch(FakePlaywright(), "/x/chrome", preset={"timezone": "Asia/Tokyo"},
                          config={"timezone:id": "America/New_York"}, user_data_dir="/tmp/p", geoip=FIXTURE, exit_ip="192.0.2.5")


def test_launch_is_quiet_when_the_zone_matches_and_does_nothing_without_the_option():
    with _warnings.catch_warnings():
        _warnings.simplefilter("error")
        camoucrome.launch(FakePlaywright(), "/x/chrome", config={"timezone:id": "America/New_York"},
                          user_data_dir="/tmp/p", geoip=FIXTURE, exit_ip="192.0.2.5")
        camoucrome.launch(FakePlaywright(), "/x/chrome", config={"timezone:id": "Asia/Tokyo"}, user_data_dir="/tmp/p")


def test_launch_warns_when_it_cannot_tell_and_the_browser_still_starts():
    pw = FakePlaywright()
    with pytest.warns(geoip.GeoIPWarning, match="could not be checked"):
        camoucrome.launch(pw, "/x/chrome", config={"timezone:id": "Asia/Tokyo"}, user_data_dir="/tmp/p",
                          geoip="/nonexistent.mmdb", exit_ip="192.0.2.5")
    assert pw.chromium.kw["headless"] is True


def test_geoip_true_reads_the_environment(monkeypatch):
    monkeypatch.setenv("CAMOU_GEOIP_DB", FIXTURE)
    with pytest.warns(geoip.GeoIPWarning, match="contradicts"):
        camoucrome.launch(FakePlaywright(), "/x/chrome", config={"timezone:id": "Asia/Tokyo"},
                          user_data_dir="/tmp/p", geoip=True, exit_ip="192.0.2.5")


@pytest.mark.parametrize("proxy", ["http://h:1", {"username": "u"}])
def test_exit_ip_raises_geoiperror_for_a_proxy_without_a_server(proxy):
    with pytest.raises(geoip.GeoIPError):
        geoip.exit_ip(proxy)


def test_launch_rejects_a_bad_proxy_before_any_echo_request(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("echo request made")
    monkeypatch.setattr(geoip, "exit_ip", boom)
    with pytest.raises(ValueError):
        camoucrome.launch(FakePlaywright(), "/x/chrome", config={"timezone:id": "Asia/Tokyo"}, geoip=FIXTURE, proxy={"server": "http://u:p@h:1"})
    with pytest.raises(ValueError):
        camoucrome.launch(FakePlaywright(), "/x/chrome", config={"timezone:id": "Asia/Tokyo"}, geoip=FIXTURE, proxy="http://h:1")


def test_exit_ip_short_form_server_means_http():
    p = EchoProxy(b"203.0.113.9\n")
    try:
        got = geoip.exit_ip({"server": p.server.removeprefix("http://")}, urls=("http://echo.test/",))
    finally:
        p.shutdown()
    assert got == "203.0.113.9" and p.seen


@pytest.mark.parametrize("scheme", ["https", "socks5"])
def test_exit_ip_makes_no_connection_through_a_non_http_proxy_and_leaks_no_credentials(scheme):
    p = EchoProxy(b"203.0.113.9\n")
    try:
        with pytest.raises(geoip.GeoIPError, match=f"through a {scheme} proxy \\(only http\\)") as ei:
            geoip.exit_ip({"server": p.server.replace("http", scheme), "username": "uuu", "password": "ppp"}, urls=("http://echo.test/",))
        assert "uuu" not in str(ei.value) and "ppp" not in str(ei.value) and "127.0.0.1" not in str(ei.value)
        [msg] = geoip.check_config({"timezone:id": "Asia/Tokyo"}, {"server": p.server.replace("http", scheme), "username": "uuu", "password": "ppp"}, db=FIXTURE)
        assert "could not be checked" in msg and scheme in msg and "uuu" not in msg and "ppp" not in msg
    finally:
        p.shutdown()
    assert p.connections == 0 and not p.seen


def test_an_unreadable_database_is_a_geoip_error_and_a_warning(tmp_path):
    # A directory at the path fails to open on every OS; chmod(0) denies nothing on Windows and nothing to root.
    db = tmp_path / "locked.mmdb"
    db.mkdir()
    with pytest.raises(geoip.GeoIPError):
        geoip.lookup("192.0.2.5", str(db))
    [msg] = geoip.check_config({"timezone:id": "Asia/Tokyo"}, exit_ip_="192.0.2.5", db=str(db))
    assert "could not be checked" in msg
    with pytest.warns(geoip.GeoIPWarning, match="not resolved"):
        cfg = _gen_db(str(db))
    assert cfg["timezone:id"]


def _gen_db(db):
    pytest.importorskip("browserforge")
    from camoucrome import gen
    return gen.generate("windows", seed=1, exit_ip="192.0.2.5", geoip_db=db)["config"]


def test_a_non_string_configured_zone_is_nothing_to_check():
    assert geoip.check_config({"timezone:id": 5}, exit_ip_="192.0.2.5", db=FIXTURE) == []


def test_a_zone_key_that_is_a_directory_is_not_an_oserror_escape(monkeypatch):
    def isdir(key):
        raise IsADirectoryError(key)
    monkeypatch.setattr(geoip, "ZoneInfo", isdir)
    with pytest.raises(geoip.GeoIPError, match="unusable time zone"):
        geoip.lookup("203.0.113.7", FIXTURE)
    [msg] = geoip.check_config({"timezone:id": "America"}, exit_ip_="192.0.2.5", db=FIXTURE)
    assert "could not be checked" in msg


def test_cli_check_zone_failure_reads_like_check_configs(capsys):
    assert geoip.main(["--ip", "192.0.2.5", "--db", FIXTURE, "--check-zone", "Not/AZone"]) == 0
    assert "timezone:id Not/AZone could not be checked against the exit IP:" in json.loads(capsys.readouterr().out)["warning"]


def test_gen_cli_takes_exit_ip_and_db():
    pytest.importorskip("browserforge")
    import subprocess
    root = pathlib.Path(__file__).resolve().parents[1]
    out = subprocess.run([sys.executable, "-m", "camoucrome.gen", "--os", "windows", "--seed", "1", "--exit-ip", "203.0.113.7",
                          "--geoip-db", FIXTURE], cwd=root, capture_output=True, text=True, check=True).stdout
    assert json.loads(out)["config"]["timezone:id"] == "Europe/Paris"


def test_the_geoip_extra_brings_tzdata_on_windows():
    # Windows has no system zone database: without tzdata every ZoneInfo(...) raises there.
    text = (pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert "tzdata; sys_platform == 'win32'" in text

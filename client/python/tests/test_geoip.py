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

"""C2: coordinates from the exit IP, the geolocation permission, the proxy-without-geoip warning. Offline."""
import math
import pathlib
import sys
import warnings

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import camoucrome  # noqa: E402
from camoucrome import gen, geoip  # noqa: E402
from test_launcher import FakePlaywright  # noqa: E402

pytest.importorskip("maxminddb")
pytest.importorskip("timezonefinder")
pytest.importorskip("browserforge")
FIXTURE = str(pathlib.Path(__file__).resolve().parent / "data" / "geoip-test.mmdb")
POINT = (42.3592, -71.0931)  # the fixture's record for 192.0.2.5
LAT, LNG = "geolocation:latitude", "geolocation:longitude"


def km(a, b):
    p, q = math.radians(a[0]), math.radians(b[0])
    h = math.sin((q - p) / 2) ** 2 + math.cos(p) * math.cos(q) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def drawn(seed, ip="192.0.2.5"):
    return gen.generate(os="windows", seed=seed, exit_ip=ip, geoip_db=FIXTURE)["config"]


def test_lookup_returns_the_records_point():
    r = geoip.lookup("192.0.2.5", FIXTURE)
    assert (r["latitude"], r["longitude"]) == POINT


def test_the_config_carries_a_point_within_2_km_of_the_record():
    c = drawn(1)
    assert 0 < km(POINT, (c[LAT], c[LNG])) <= 2
    assert round(c[LAT], 6) == c[LAT] and round(c[LNG], 6) == c[LNG]
    assert "geolocation:accuracy" not in c


def test_same_seed_same_point_two_seeds_differ():
    a, b, c = drawn(7), drawn(7), drawn(8)
    assert (a[LAT], a[LNG]) == (b[LAT], b[LNG])
    assert (a[LAT], a[LNG]) != (c[LAT], c[LNG])


def test_a_failed_lookup_gives_no_geolocation_keys():
    with pytest.warns(geoip.GeoIPWarning):
        c = drawn(1, "2001:db8:ffff::1")
    assert LAT not in c and LNG not in c
    assert LAT not in gen.generate(os="windows", seed=1)["config"]


def test_a_record_without_coordinates_gives_no_keys(monkeypatch):
    real = geoip.lookup
    monkeypatch.setattr(geoip, "lookup", lambda *a: {**real(*a), "latitude": None, "longitude": None})
    c = drawn(1)
    assert LAT not in c and LNG not in c


def launched(**kw):
    pw = FakePlaywright()
    camoucrome.launch(pw, "/x/chrome", user_data_dir="/tmp/p", **kw)
    return pw.chromium.kw


def test_the_permission_is_granted_only_with_both_coordinates():
    assert launched(config={LAT: 1.5, LNG: 2.5})["permissions"] == ["geolocation"]
    assert "permissions" not in launched(config={LAT: 1.5})
    assert "permissions" not in launched(config={LNG: 2.5})
    assert "permissions" not in launched(config={"a": 1})


def test_the_permission_merges_with_the_callers_list_without_a_duplicate():
    cfg = {LAT: 1.5, LNG: 2.5}
    assert launched(config=cfg, permissions=["notifications"])["permissions"] == ["notifications", "geolocation"]
    assert launched(config=cfg, permissions=["geolocation", "notifications"])["permissions"] == ["geolocation", "notifications"]
    assert launched(config={"a": 1}, permissions=["notifications"])["permissions"] == ["notifications"]


PROXY = {"server": "http://p.example:8080"}
WORDS = "a proxy without geoip: timezone, locale and geolocation are not checked against the exit IP"


def test_a_proxy_without_geoip_warns():
    with pytest.warns(geoip.GeoIPWarning) as w:
        launched(config={"a": 1}, proxy=PROXY)
    assert [str(x.message) for x in w] == [WORDS]


def test_no_warning_without_a_proxy_or_with_geoip():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        launched(config={"a": 1})
        launched(config={"a": 1}, proxy=PROXY, geoip=FIXTURE, exit_ip="192.0.2.5")

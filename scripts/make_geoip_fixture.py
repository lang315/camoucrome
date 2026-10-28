#!/usr/bin/env python3
"""Rebuild client/python/tests/data/geoip-test.mmdb: a tiny synthetic database in the GeoLite2-City layout, built
from documentation addresses only (no DB-IP or MaxMind data). Needs `pip install mmdb-writer netaddr`; the output
is committed, so only a change to the cases below needs this script."""
import pathlib

import netaddr
from mmdb_writer import MMDBWriter

OUT = pathlib.Path(__file__).resolve().parents[1] / "client" / "python" / "tests" / "data" / "geoip-test.mmdb"
CASES = [
    ("192.0.2.0/24", {"country": {"iso_code": "US"}, "location": {"latitude": 42.3592, "longitude": -71.0931}}),
    ("198.51.100.0/24", {"country": {"iso_code": "US"}, "location": {"latitude": 37.8641, "longitude": -122.268}}),
    # MaxMind's field present: it wins over the coordinates (which are in Tokyo).
    ("203.0.113.0/24", {"country": {"iso_code": "FR"},
                        "location": {"latitude": 35.6916, "longitude": 139.768, "time_zone": "Europe/Paris"}}),
    # A country with no row in settings/locale_zones.json.
    ("2001:db8::/48", {"country": {"iso_code": "SG"}, "location": {"latitude": 1.29, "longitude": 103.85}}),
    # No location at all.
    ("2001:db8:1::/48", {"country": {"iso_code": "DE"}}),
]

w = MMDBWriter(ip_version=6, ipv4_compatible=True, database_type="GeoLite2-City", languages=["en"],
               description={"en": "synthetic test data, documentation addresses only"})
for net, record in CASES:
    w.insert_network(netaddr.IPSet([net]), record)
OUT.parent.mkdir(parents=True, exist_ok=True)
w.to_db_file(str(OUT))
print(OUT, OUT.stat().st_size, "bytes")

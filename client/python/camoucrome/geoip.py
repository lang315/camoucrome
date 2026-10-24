"""Exit-IP geolocation for item 13: the time zone and locale an identity should claim for an IP.

IP Geolocation by DB-IP (https://db-ip.com), "IP to City Lite", CC BY 4.0. The database is the user's own
download (a monthly .mmdb, no account); nothing is fetched or shipped here. Any GeoLite2-layout .mmdb works too:
a record's location.time_zone is used when it has one (MaxMind), else the zone comes from its coordinates.

    pip install camoucrome[geoip]        # maxminddb + timezonefinder, needed only here
    python -m camoucrome.geoip --ip 203.0.113.9 --db dbip-city-lite.mmdb [--check-zone Europe/Paris]
"""
import argparse
import functools
import ipaddress
import json
import os
import sys
import urllib.parse
import urllib.request
import warnings
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .gen import ROOT

ECHO_URLS = ("https://api.ipify.org", "https://checkip.amazonaws.com", "https://icanhazip.com", "https://ifconfig.co/ip")
ECHO_TIMEOUT = 5


class GeoIPError(Exception):
    """The exit IP cannot be resolved; the message says why and goes into the warning."""


class GeoIPWarning(UserWarning):
    pass


def db_path(db=None):
    return db or os.environ.get("CAMOU_GEOIP_DB")


@functools.lru_cache(maxsize=1)
def _finder():
    try:
        from timezonefinder import TimezoneFinder
    except ImportError as e:
        raise GeoIPError("this database has no time zones and timezonefinder is missing: pip install camoucrome[geoip]") from e
    return TimezoneFinder()


def zone_of(record):
    """The IANA zone of a database record: its own time_zone, else the one its coordinates fall in."""
    loc = record.get("location") or {}
    if loc.get("time_zone"):
        return loc["time_zone"]
    lat, lng = loc.get("latitude"), loc.get("longitude")
    if lat is None or lng is None:
        return None
    return _finder().timezone_at(lat=lat, lng=lng)


@functools.lru_cache(maxsize=1)
def _locale_by_region():
    """region -> the first locale of settings/locale_zones.json with that region (file order decides: en-CA before fr-CA)."""
    zones = json.loads((ROOT / "settings" / "locale_zones.json").read_text(encoding="utf-8"))["zones"]
    out = {}
    for tag in zones:
        out.setdefault(tag.rsplit("-", 1)[-1], tag)
    return out


def locale_for(country):
    return _locale_by_region().get((country or "").upper())


def lookup(ip, db=None):
    """{"country", "timezone", "locale"} for an IP. locale is None for a country with no row in locale_zones.json.
    Raises GeoIPError (no database, unreadable, IP not in it, no zone for its coordinates)."""
    path = db_path(db)
    if not path:
        raise GeoIPError("no geoip database: pass one or set CAMOU_GEOIP_DB")
    if not os.path.isfile(path):
        raise GeoIPError(f"geoip database not found: {path}")
    try:
        import maxminddb
    except ImportError as e:
        raise GeoIPError("maxminddb is missing: pip install camoucrome[geoip]") from e
    try:
        ipaddress.ip_address(ip)
        with maxminddb.open_database(path) as reader:
            record = reader.get(ip)
    except (ValueError, maxminddb.InvalidDatabaseError) as e:
        raise GeoIPError(f"{ip}: {e}") from e
    if not record:
        raise GeoIPError(f"{ip} is not in the database")
    try:
        zone = zone_of(record)
        if zone:
            ZoneInfo(zone)
    except (KeyError, ValueError) as e:  # bad coordinates, or a zone this machine's tzdata lacks
        raise GeoIPError(f"{ip}: unusable time zone ({e})") from e
    if not zone:
        raise GeoIPError(f"{ip} has no time zone in the database")
    country = (record.get("country") or {}).get("iso_code")
    return {"country": country, "timezone": zone, "locale": locale_for(country)}


def check_zone(config_zone, ip_zone, now=None):
    """A warning when the two zones' UTC offsets differ now (what detectors compare), else None."""
    now = now or datetime.now(timezone.utc)
    try:
        a, b = now.astimezone(ZoneInfo(config_zone)).utcoffset(), now.astimezone(ZoneInfo(ip_zone)).utcoffset()
    except (KeyError, ValueError) as e:
        raise GeoIPError(f"unknown time zone ({e})") from e
    if a != b:
        return f"timezone:id {config_zone} (UTC{_fmt(a)}) contradicts the exit IP's {ip_zone} (UTC{_fmt(b)})"
    return None


def _fmt(delta):
    minutes = int(delta.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    return f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


def exit_ip(proxy=None, urls=ECHO_URLS, timeout=ECHO_TIMEOUT):
    """The address the world sees: ask an echo service, through the proxy when given
    ({"server", "username", "password"}). One service after another; GeoIPError when none answers."""
    handlers = []
    if proxy:
        u = urllib.parse.urlsplit(proxy["server"])
        auth = ""
        if proxy.get("username"):
            auth = urllib.parse.quote(proxy["username"], safe="") + ":" + urllib.parse.quote(proxy.get("password") or "", safe="") + "@"
        url = f"{u.scheme}://{auth}{u.netloc}"
        handlers.append(urllib.request.ProxyHandler({"http": url, "https": url}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))
    opener = urllib.request.build_opener(*handlers)
    errors = []
    for url in urls:
        try:
            text = opener.open(url, timeout=timeout).read(200).decode("ascii", "replace").strip()
            ipaddress.ip_address(text)
            return text
        except Exception as e:  # noqa: BLE001 - every failure is one more service to try
            errors.append(f"{url}: {type(e).__name__}")
    raise GeoIPError("no echo service answered (" + "; ".join(errors) + ")")


def check_config(config, proxy=None, exit_ip_=None, db=None):
    """Warnings about a config's timezone:id against the exit IP. Never raises; [] when there is nothing to check."""
    zone = (config or {}).get("timezone:id")
    if not zone:
        return []
    try:
        ip = exit_ip_ or exit_ip(proxy)
        found = lookup(ip, db)
        msg = check_zone(zone, found["timezone"])
    except GeoIPError as e:
        return [f"timezone:id {zone} could not be checked against the exit IP: {e}"]
    return [msg] if msg else []


def warn_all(messages):
    for m in messages:
        warnings.warn(m, GeoIPWarning, stacklevel=3)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--ip", required=True)
    ap.add_argument("--db")
    ap.add_argument("--check-zone", help="also report a warning when this IANA zone contradicts the IP's")
    a = ap.parse_args(argv)
    try:
        out = lookup(a.ip, a.db)
    except GeoIPError as e:
        print(json.dumps({"error": str(e)}))
        return 2
    try:
        out["warning"] = check_zone(a.check_zone, out["timezone"]) if a.check_zone else None
    except GeoIPError as e:
        out["warning"] = f"--check-zone {a.check_zone} could not be checked: {e}"
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

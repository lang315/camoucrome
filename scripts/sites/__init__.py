"""Site profiles for the observe toolchain: settings/sites/<name>/site.json plus an optional hook module here.

Spec docs/superpowers/specs/2026-10-31-site-profile-design.md (local). Data is found next to the scripts on the host
(<observe>\\settings\\sites) or in the repo (settings/sites).
"""
import dataclasses
import importlib
import json
import pathlib
import re
import types

HERE = pathlib.Path(__file__).resolve().parent
NAME_RE = re.compile(r"^[a-z0-9_-]+$")
REQUIRED = ("name", "origin", "surface_site", "cookie_domain", "logged_in_cookies", "pages", "route_paths",
            "unlink_endpoints", "beacon_path", "post_hosts", "resource_hosts", "doc_hosts", "ws_hosts", "backup",
            "baseline", "ledger", "cap", "expired_hint")
_TUPLES = ("logged_in_cookies", "route_paths", "unlink_endpoints", "post_hosts", "resource_hosts", "doc_hosts", "ws_hosts")


class SiteError(Exception):
    pass


@dataclasses.dataclass(frozen=True)
class Site:
    name: str
    dir: pathlib.Path
    origin: str
    surface_site: str
    cookie_domain: str
    logged_in_cookies: tuple
    pages: dict
    route_paths: tuple
    unlink_endpoints: tuple
    beacon_path: str
    post_hosts: tuple
    resource_hosts: tuple
    doc_hosts: tuple
    ws_hosts: tuple
    backup: str
    baseline: str
    ledger: str
    cap: dict
    expired_hint: str
    hooks: types.ModuleType

    def pop_host(self, host):
        return self.hooks.pop_host(host)

    def binary_units(self, raw):
        return self.hooks.binary_units(raw)


def _roots():
    # host: <observe>\sites\__init__.py with data in <observe>\settings\sites; repo: scripts/sites with settings/sites
    return [HERE.parent / "settings" / "sites", HERE.parent.parent / "settings" / "sites"]


def load(name="facebook", root=None):
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise SiteError(f"bad site name {name!r}")
    roots = [pathlib.Path(root)] if root else _roots()
    d = next((r / name for r in roots if (r / name / "site.json").is_file()), None)
    if d is None:
        raise SiteError(f"{name} not found")
    try:
        doc = json.loads((d / "site.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise SiteError(f"{name} site.json unreadable ({type(e).__name__})")
    missing = [k for k in REQUIRED if k not in doc]
    if missing:
        raise SiteError(f"{name} site.json lacks {' '.join(missing)}")
    if doc["name"] != name:
        raise SiteError(f"{name} site.json names {doc['name']!r}")
    hooks = importlib.import_module("sites." + doc.get("module", "base"))
    kw = {k: (tuple(doc[k]) if k in _TUPLES else doc[k]) for k in REQUIRED}
    kw["pages"] = {arm: tuple(paths) for arm, paths in doc["pages"].items()}
    return Site(dir=d.resolve(), hooks=hooks, **kw)

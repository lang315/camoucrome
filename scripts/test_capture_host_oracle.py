"""capture_host_oracle writes only a scrubbed doc, and refuses rather than write a host value."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import capture_host_oracle as cho  # noqa: E402

TERMS = {"<host-tz>": ["Mars/Olympus"], "user.HOST": ["someone.BOX"]}
DOC = {"headed": {"intl": {"dtf": {"timeZone": "Mars/Olympus"}},
                  "err": {"stack": r"at file:///C:/Users/someone.BOX/AppData/Local/Temp/p.html"}}}


def test_committable_replaces_host_values():
    out = cho.committable(DOC, TERMS)
    assert out["headed"]["intl"]["dtf"]["timeZone"] == "<host-tz>"
    assert out["headed"]["err"]["stack"] == "at file:///C:/Users/user.HOST/AppData/Local/Temp/p.html"


def test_committable_refuses_without_terms():
    with pytest.raises(SystemExit):
        cho.committable(DOC, {})


def test_committable_refuses_a_leftover_hit():
    doc = {"headed": {"where": "built on DESKTOP-AB12CD3"}}
    with pytest.raises(SystemExit):
        cho.committable(doc, TERMS)

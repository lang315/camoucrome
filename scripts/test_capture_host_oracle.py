"""capture_host_oracle writes only a scrubbed doc, and refuses rather than write a host value."""
import json
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


def test_from_raw_scrubs_on_the_mac(tmp_path, monkeypatch):
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps(DOC))
    out = tmp_path / "baseline.json"
    monkeypatch.setattr(cho, "OUT", out)
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps(TERMS))
    assert cho.main(["--from-raw", str(raw)]) == 0
    assert json.loads(out.read_text())["headed"]["intl"]["dtf"]["timeZone"] == "<host-tz>"


def test_raw_out_inside_the_repository_is_refused():
    with pytest.raises(SystemExit):
        cho.main(["--raw-out", str(cho.ROOT / "raw.json")])


def test_page_reads_the_unmasked_webgl_leaves():
    # step 6: without these the linkability table cannot see the GPU the fork shares across profiles
    html = cho.page()
    assert "step('webgl'" in html
    assert "UNMASKED_VENDOR_WEBGL" in html and "UNMASKED_RENDERER_WEBGL" in html
    assert "getParameter(36183)" in html

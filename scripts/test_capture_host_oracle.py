"""capture_host_oracle writes only a scrubbed doc, and refuses rather than write a host value."""
import json
import os
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


class FakeWinhost:
    """winhost with scripted answers: cdp_eval returns the doc for the mode, powershell the display."""
    def __init__(self, headed, headless, display="1440x900"):
        self.calls, self.docs, self.display, self.profiles, self.removed = [], {True: headed, False: headless}, display, [], []

    def cdp_eval(self, page_html, expression, args=(), headed=True, wait_ms=0, profile=None, exe=None, **kw):
        self.calls.append(("cdp", headed, wait_ms))
        self.profiles.append((profile, exe))
        return json.dumps(self.docs[headed])

    def dump_dom(self, *a, **kw):
        raise AssertionError("headless must not use --dump-dom (virtual time races the async cells)")

    def powershell(self, ps, timeout=0):
        if ps.startswith("Remove-Item"):
            self.removed.append(ps.split()[3])
            return ""
        return f"DISPLAY {self.display}\r\n"


def _good(w=1440, h=900):
    return {"done": True, "screen": {"width": w, "height": h}, "gpu": {"info": 1}}


def _run(monkeypatch, tmp_path, fake):
    monkeypatch.setitem(sys.modules, "winhost", fake)
    return cho.main(["--raw-out", str(tmp_path / "raw.json")])


def test_capture_reads_both_modes_by_cdp_in_real_time(monkeypatch, tmp_path):
    fake = FakeWinhost(_good(), {"done": True, "gpu": {"info": 1}})
    assert _run(monkeypatch, tmp_path, fake) == 0
    reads = [c[:2] for c in fake.calls if c[2] == 25000]
    assert reads == [("cdp", True), ("cdp", False)]
    doc = json.loads((tmp_path / "raw.json").read_text())
    assert doc["display"] == {"width": 1440, "height": 900} and "dump-dom" not in doc["where"]


def test_each_mode_reads_on_a_profile_primed_by_an_earlier_launch(monkeypatch, tmp_path):
    # a fresh profile has no variations seed, so the capture measured compiled defaults (2026-10-24 baseline)
    monkeypatch.setenv("CAMOU_STOCK_APP", r"D:\stock\156")
    fake = FakeWinhost(_good(), {"done": True, "gpu": {"info": 1}})
    assert _run(monkeypatch, tmp_path, fake) == 0
    prime_read = [(c[1], c[2], p) for c, p in zip(fake.calls, fake.profiles)]
    assert [(h, w) for h, w, _ in prime_read] == [(True, 60000), (True, 25000), (False, 60000), (False, 25000)]
    assert prime_read[0][2] == prime_read[1][2] and prime_read[2][2] == prime_read[3][2]
    assert prime_read[0][2][0] != prime_read[2][2][0] and prime_read[0][2][0] is not None
    assert all(exe == os.path.join(r"D:\stock\156", "chrome.exe") for _, _, (_, exe) in prime_read)
    # the doc names the build measured: the version a frozen stock's directory carries, else the pin
    assert json.loads((tmp_path / "raw.json").read_text())["chrome"] == "156.0.8078.48"
    monkeypatch.setenv("CAMOU_STOCK_APP", os.path.join(os.sep, "stock", "156.0.8078.80"))
    assert _run(monkeypatch, tmp_path, FakeWinhost(_good(), {"done": True, "gpu": {"info": 1}})) == 0
    assert json.loads((tmp_path / "raw.json").read_text())["chrome"] == "156.0.8078.80"
    assert sorted(fake.removed) == sorted({pr[0] for _, _, pr in prime_read})


def test_a_capture_with_protected_audience_still_present_is_unseeded_not_a_baseline(monkeypatch, tmp_path):
    fake = FakeWinhost(dict(_good(), navProto=["joinAdInterestGroup"]), {"done": True, "navProto": []})
    with pytest.raises(SystemExit, match="UNSEEDED.*headed"):
        _run(monkeypatch, tmp_path, fake)
    assert not (tmp_path / "raw.json").exists()


def test_a_timeout_cell_is_unmeasured_not_a_baseline(monkeypatch, tmp_path):
    fake = FakeWinhost(_good(), {"done": True, "perms": "timeout"})
    with pytest.raises(SystemExit, match="UNMEASURED cells.*headless.perms"):
        _run(monkeypatch, tmp_path, fake)
    assert not (tmp_path / "raw.json").exists() and (tmp_path / "raw.json.refused").exists()


def test_headed_screen_must_equal_the_console_display(monkeypatch, tmp_path):
    fake = FakeWinhost(_good(1280, 1024), {"done": True}, display="1440x900")
    with pytest.raises(SystemExit, match="not the console display"):
        _run(monkeypatch, tmp_path, fake)
    assert not (tmp_path / "raw.json").exists()


def test_oracle_reads_av1_media_capabilities():
    src = (pathlib.Path(__file__).resolve().parent / "capture_host_oracle.py").read_text(encoding="utf-8")
    assert "av01.0.05M.08" in src.split("await step('mediaCapAv1'")[1].split("await step(")[0]

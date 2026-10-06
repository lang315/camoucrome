"""observe_report.py on hand-made fixtures shaped like the real files."""
import json
import pathlib
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import observe_report as r  # noqa: E402

CAT = "disabled-by-default-camou.observe"


def ev(name, origin, site, cat=CAT, ph="I"):
    return {"name": name, "cat": cat, "ph": ph, "pid": 1, "tid": 1, "ts": 1,
            "args": {"origin": origin, "site": site}}


def write_trace(tmp_path, events, wrap=True):
    p = tmp_path / "trace.json"
    p.write_text(json.dumps({"traceEvents": events} if wrap else events))
    return p


def test_load_events_keeps_only_the_category(tmp_path):
    p = write_trace(tmp_path, [ev("Navigator.userAgent.get", "https://a.com", "https://a.com"),
                               ev("Other", "x", "y", cat="blink")])
    assert [e["name"] for e in r.load_events(p)] == ["Navigator.userAgent.get"]


def test_load_events_accepts_a_bare_array(tmp_path):
    p = write_trace(tmp_path, [ev("Screen.width.get", "https://a.com", "https://a.com")], wrap=False)
    assert len(r.load_events(p)) == 1


def test_counts_are_real_call_counts_split_by_reading_origin():
    events = [ev("Navigator.userAgent.get", "https://www.facebook.com", "https://news.com")] * 3 + [
        ev("Navigator.userAgent.get", "https://news.com", "https://news.com")]
    c = r.surface_counts(events)
    assert c["https://news.com"]["https://www.facebook.com"]["Navigator.userAgent.get"] == 3
    assert c["https://news.com"]["https://news.com"]["Navigator.userAgent.get"] == 1


def test_worker_events_group_by_origin_when_site_is_empty():
    c = r.surface_counts([ev("WorkerNavigator.hardwareConcurrency.get", "https://a.com", "")])
    assert c["https://a.com"]["https://a.com"]["WorkerNavigator.hardwareConcurrency.get"] == 1


def test_group_of_member_entries_win_over_interface_entries():
    assert r.group_of("Navigator.deviceMemory.get") == "navigator"
    assert r.group_of("Window.matchMedia") == "layout-probe"
    assert r.group_of("Document.cookie.get") == "storage"
    assert r.group_of("Frobnicator.x.get") == "other"


def write_netlog(tmp_path, events):
    data = {"constants": {"logEventTypes": {"URL_REQUEST_START_JOB": 7, "OTHER": 8},
                          "logEventPhase": {"PHASE_BEGIN": 1, "PHASE_END": 2, "PHASE_NONE": 0}},
            "events": events}
    p = tmp_path / "net.json"
    p.write_text(json.dumps(data))
    return p


def start_job(url, nik, sfc="SiteForCookies: {site=null; schemefully_same=false}", phase=1, method="GET"):
    return {"type": 7, "phase": phase, "params": {
        "url": url, "method": method, "network_isolation_key": nik,
        "site_for_cookies": sfc, "initiator": "not an origin"}}


def test_requests_strip_queries_and_use_the_top_frame_site(tmp_path):
    p = write_netlog(tmp_path, [
        start_job("https://www.facebook.com/tr?id=123&ev=PageView", "https://news.com https://news.com"),
        start_job("https://x.com/a", "https://news.com https://news.com", phase=2),
        {"type": 8, "phase": 1, "params": {}},
    ])
    assert r.load_requests(p) == [("https://news.com", "www.facebook.com", "/tr", "GET")]


def test_requests_fall_back_to_site_for_cookies(tmp_path):
    p = write_netlog(tmp_path, [start_job(
        "https://a.com/x?q=1", "null", sfc="SiteForCookies: {site=https://a.com; schemefully_same=true}")])
    assert r.load_requests(p)[0][0] == "https://a.com"


def make_cookies(tmp_path):
    db = tmp_path / "Cookies"
    con = sqlite3.connect(db)
    con.execute("create table cookies (host_key text, name text, value text, encrypted_value blob, "
                "expires_utc integer, is_httponly integer)")
    con.execute("insert into cookies values ('.facebook.com', 'datr', 'SECRET', x'00', 13400000000000000, 1)")
    con.commit()
    con.close()
    return db


def test_cookie_names_never_carry_values(tmp_path):
    rows = r.load_cookie_names(make_cookies(tmp_path))
    assert rows == [(".facebook.com", "datr", 13400000000000000, 1)]
    assert "SECRET" not in repr(rows)


def test_render_lists_counts_hosts_cookies_and_blind_spots(tmp_path):
    events = [ev("Navigator.deviceMemory.get", "https://www.facebook.com", "https://www.facebook.com")] * 2
    requests = [("https://www.facebook.com", "www.facebook.com", "/ajax/bz", "POST")]
    cookies = [(".facebook.com", "datr", 1, 1)]
    out = r.render(events, requests, cookies)
    assert "## https://www.facebook.com" in out
    assert "| navigator | Navigator.deviceMemory.get | https://www.facebook.com | 2 |" in out
    assert "| www.facebook.com | POST /ajax/bz | 1 |" in out
    assert "datr" in out and "SECRET" not in out
    assert "## Not observable" in out and "Intl" in out

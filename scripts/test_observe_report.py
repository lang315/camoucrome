"""observe_report.py on hand-made fixtures shaped like the real files."""
import json
import pathlib
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import observe_report as r  # noqa: E402

CAT = "disabled-by-default-camou.observe"


def ev(name, origin, site, cat=CAT, ph="I", script=""):
    return {"name": name, "cat": cat, "ph": ph, "pid": 1, "tid": 1, "ts": 1,
            "args": {"origin": origin, "site": site, "script": script}}


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


FBQ = "https://connect.facebook.net/en_US/fbevents.js"


def test_counts_are_real_call_counts_split_by_reading_origin_and_script():
    events = [ev("Navigator.userAgent.get", "https://www.facebook.com", "https://news.com")] * 3 + [
        ev("Navigator.userAgent.get", "https://news.com", "https://news.com", script=FBQ + "?v=2"),
        ev("Navigator.userAgent.get", "https://news.com", "https://news.com", script=FBQ + "#x"),
        ev("Navigator.userAgent.get", "https://news.com", "https://news.com",
           script="https://news.com/app.js")]
    c = r.surface_counts(events)
    ua = "Navigator.userAgent.get"
    assert c["https://news.com"][("https://www.facebook.com", "(no script)")][ua] == 3
    assert c["https://news.com"][("https://news.com", "connect.facebook.net/en_US/fbevents.js")][ua] == 2
    assert c["https://news.com"][("https://news.com", "news.com/app.js")][ua] == 1


def test_script_label_is_host_and_path():
    assert r.script_label(FBQ + "?id=123&ev=PageView#frag") == "connect.facebook.net/en_US/fbevents.js"
    assert r.script_label("http://127.0.0.1:8080/probe.html") == "127.0.0.1:8080/probe.html"
    assert r.script_label("https://user:pass@cdn.example.com:8443/x.js?t=1") == "cdn.example.com:8443/x.js"
    assert r.script_label("https://user:pass@cdn.example.com/x.js") == "cdn.example.com/x.js"
    assert r.script_label("") == "(no script)"
    assert r.script_label(None) == "(no script)"


def test_worker_events_group_by_origin_when_site_is_empty():
    c = r.surface_counts([ev("WorkerNavigator.hardwareConcurrency.get", "https://a.com", "",
                             script="https://a.com/w.js")])
    assert c["https://a.com"][("https://a.com", "a.com/w.js")]["WorkerNavigator.hardwareConcurrency.get"] == 1


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
    assert ("| navigator | Navigator.deviceMemory.get | https://www.facebook.com | (no script) | 2 |"
            in out)
    assert "| www.facebook.com | POST /ajax/bz | 1 |" in out
    assert "datr" in out and "SECRET" not in out
    assert "## Not observable" in out and "Intl" in out and "NoAllocDirectCall" not in out


def test_render_top_scripts_per_site():
    site = "https://news.com"
    events = ([ev("Navigator.userAgent.get", site, site, script=FBQ + "?v=1")] * 4
              + [ev("Screen.width.get", site, site, script=FBQ)] * 3
              + [ev("Navigator.deviceMemory.get", site, site, script=FBQ)] * 2
              + [ev("Window.matchMedia", site, site, script=FBQ)]
              + [ev("Document.cookie.get", site, site, script="https://news.com/app.js")] * 5)
    out = r.render(events, [], [])
    assert "| group | API | reading origin | script | calls |" in out
    assert "| screen | Screen.width.get | https://news.com | connect.facebook.net/en_US/fbevents.js | 3 |" in out
    top = out.split("Top scripts", 1)[1]
    assert "| script | calls | top APIs |" in top
    fb = "| connect.facebook.net/en_US/fbevents.js | 10 | "
    assert fb + "Navigator.userAgent.get (4), Screen.width.get (3), Navigator.deviceMemory.get (2) |" in top
    assert "Window.matchMedia" not in top.split(fb, 1)[1].split("\n", 1)[0]
    assert top.index(fb) < top.index("| news.com/app.js | 5 | Document.cookie.get (5) |")


def test_script_label_survives_a_bad_port_and_hides_blob_and_data_ids():
    assert r.script_label("https://cdn.example.com:99999/x.js") == "cdn.example.com/x.js"
    assert r.script_label("https://cdn.example.com:abc/x.js") == "cdn.example.com/x.js"
    assert r.script_label("blob:https://www.facebook.com/0f8c6a2e-1111-2222-3333-444455556666") == "blob:"
    assert r.script_label("data:text/javascript;base64,QUJD") == "data:"
    out = r.render([ev("Screen.width.get", "https://a.com", "https://a.com",
                       script="https://a.com:bad/x.js")], [], [])
    assert "| a.com/x.js |" in out


def test_buffer_note_reports_discarded_chunks(tmp_path):
    p = write_trace(tmp_path, [ev("Screen.width.get", "https://a.com", "https://a.com")])
    data = json.loads(p.read_text())
    buf = [{"buffer_size": 209715200, "chunks_discarded": 21683},
           {"buffer_size": 262144, "chunks_discarded": 0}]
    data["metadata"] = {"trace_processor_stats": {"traced_buf": buf}}
    p.write_text(json.dumps(data))
    note = r.buffer_note(r.load_trace(p))
    assert "21683" in note and "lower bounds" in note
    assert len(r.events_of(r.load_trace(p))) == 1
    buf[0]["chunks_discarded"] = 0
    p.write_text(json.dumps(data))
    assert "no chunks discarded" in r.buffer_note(r.load_trace(p))
    assert "not in the trace" in r.buffer_note(r.load_trace(write_trace(tmp_path, [], wrap=False)))
    assert "lower bounds" in r.render([], [], [], buffer="x lower bounds")


def test_report_parses_as_python_3_9():
    """The Windows host runs the report under Python 3.9.13."""
    import ast
    src = pathlib.Path(r.__file__).read_text()
    ast.parse(src, feature_version=(3, 9))
    assert ".total()" not in src

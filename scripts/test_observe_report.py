"""observe_report.py on hand-made fixtures shaped like the real files."""
import collections
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
    assert "## Not observable" in out and "getTimezoneOffset" in out and "NoAllocDirectCall" not in out


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


def x(name, ts, dur, pid=1, tid=1, cat="v8", **args):
    return {"name": name, "cat": cat, "ph": "X", "pid": pid, "tid": tid, "ts": ts, "dur": dur,
            "args": args}


def rcs(ts, dur, stats, **kw):
    return x("V8.Execute", ts, dur, **{"runtime-call-stats": stats}, **kw)


# the dump names a C++ builtin's counter by the bare builtin name (box trace, 2026-10-13)
CTOR = "DateTimeFormatConstructor"
RO = "DateTimeFormatPrototypeResolvedOptions"
SLO = "DateTimeFormatSupportedLocalesOf"
APP = "https://a.com/app.js"


def at(e, ts, **kw):
    return dict(e, ts=ts, **kw)


def test_intl_counts_sum_dumps_and_keep_only_intl_names():
    events = [x("v8.run", 0, 100, fileName=APP),
              rcs(10, 20, {CTOR: [2, 5.0], "ArrayPrototypePush": [9, 1.0], "Runtime_X": [1, 0.1],
                           "DeserializeIsolate": [1, 496]}),
              rcs(40, 20, {CTOR: [1, 1.0], RO: [3, 2.0], "NumberPrototypeToLocaleString": [1, 1.0]}),
              at(ev("Navigator.userAgent.get", "https://a.com", "https://a.com"), 200)]
    s, sc = "https://a.com", "a.com/app.js"
    assert r.intl_counts(events) == {(s, sc, CTOR): 3, (s, sc, RO): 3,
                                     (s, sc, "NumberPrototypeToLocaleString"): 1}


def test_intl_counts_accept_a_dump_exported_as_a_json_string():
    events = [rcs(10, 20, json.dumps({SLO: [4, 1.0]})),
              ev("Navigator.userAgent.get", "https://a.com", "https://a.com")]
    assert r.intl_counts(events) == {("https://a.com", "(unknown)", SLO): 4}


def test_intl_script_falls_back_to_the_one_observer_script_in_the_slice():
    inside = at(ev("Navigator.userAgent.get", "https://n.com", "https://n.com", script=FBQ), 15)
    events = [x("v8.callFunction", 0, 100), rcs(10, 20, {RO: [1, 0.1]}), inside, inside]
    assert r.intl_counts(events) == {
        ("https://n.com", "connect.facebook.net/en_US/fbevents.js", RO): 1}
    other = dict(inside, args=dict(inside["args"], script="https://n.com/app.js"))
    events = [rcs(10, 20, {RO: [1, 0.1]}), inside, other]
    assert r.intl_counts(events) == {("https://n.com", "(unknown)", RO): 1}


def test_intl_v8_run_on_another_thread_or_cut_off_does_not_attribute():
    obs = ev("Screen.width.get", "https://a.com", "https://a.com")
    events = [x("v8.run", 0, 100, tid=2, fileName=APP), rcs(10, 20, {RO: [1, 0.1]}), obs]
    assert r.intl_counts(events) == {("https://a.com", "(unknown)", RO): 1}
    # an incomplete slice (the trace stopped inside it) is exported with dur -1
    events = [x("v8.run", 0, -1, fileName=APP), rcs(10, 20, {RO: [1, 0.1]}), obs]
    assert r.intl_counts(events) == {("https://a.com", "(unknown)", RO): 1}


def test_intl_site_comes_from_the_pid():
    events = [rcs(10, 20, {CTOR: [1, 0.1]}, pid=7)]
    assert r.intl_counts(events) == {("(site unknown)", "(unknown)", CTOR): 1}
    # a worker's events carry no site: its origin stands in, as in the per-site tables
    w = dict(ev("WorkerNavigator.hardwareConcurrency.get", "https://a.com", ""), pid=7)
    assert r.intl_counts(events + [w]) == {("https://a.com", "(unknown)", CTOR): 1}


def test_intl_site_prefers_the_page_site_over_worker_origins():
    # a busy worker must not move the page's Intl rows under the worker's origin
    page = [dict(ev("Screen.width.get", "https://fb.com", "https://fb.com"), pid=3)] * 3
    worker = [dict(ev("WorkerNavigator.hardwareConcurrency.get", "https://www.fb.com", ""), pid=3)] * 5
    events = [rcs(10, 20, {CTOR: [1, 0.1]}, pid=3)] + page + worker
    assert r.intl_counts(events) == {("https://fb.com", "(unknown)", CTOR): 1}


def test_intl_names_cover_the_locale_builtins():
    # CPP builtin names from this pin's builtins-definitions.h (box, 2026-10-13)
    for name in ("SegmentsPrototypeContaining", "SegmentIteratorPrototypeNext",
                 "StringPrototypeLocaleCompareIntl", "StringPrototypeLocaleCompare",
                 "TemporalInstantPrototypeToLocaleString", "StringPrototypeToLocaleLowerCase",
                 "LocalePrototypeGetTimeZones", "IntlSupportedValuesOf", "SegmenterConstructor"):
        assert r.INTL.match(name), name
    for name in ("Runtime_FormatList", "API_Locale", "StringPrototypeNormalizeIntl",
                 "ArrayPrototypePush", "GC_Custom_SlowAllocateRaw", "DeserializeIsolate"):
        assert not r.INTL.match(name), name


def test_intl_counts_scale_with_a_recon_sized_trace():
    import time
    obs = [dict(ev("Screen.width.get", "https://a.com", "https://a.com"), ts=1000 * i, tid=1 + i % 50)
           for i in range(25000)]
    slices = [rcs(1000 * i + 1, 10, {CTOR: [1, 0.1]}, tid=1 + i % 50) for i in range(3000)]
    t = time.perf_counter()
    c = r.intl_counts(slices + obs)
    assert time.perf_counter() - t < 1.5
    assert sum(c.values()) == 3000


def test_intl_blind_only_when_no_dump_holds_a_counter():
    assert r.intl_counts([ev("Screen.width.get", "o", "s")]) is None  # no V8 slices
    assert r.intl_counts([rcs(10, 20, {})]) is None  # v8 on, runtime_stats off
    assert r.intl_counts([rcs(10, 20, json.dumps({}))]) is None
    assert r.intl_counts([rcs(10, 20, {"Runtime_X": [1, 0.1]})]) == {}  # counting on, no Intl


def test_render_intl_section_states():
    assert "Intl: blind (no V8 runtime call stats in this trace)" in r.render([], [], [])
    assert "Intl: none called" in r.render([], [], [], intl={})
    out = r.render([], [], [], intl={("https://a.com", "a.com/app.js", CTOR): 3,
                                     ("https://a.com", "a.com/app.js", RO): 5})
    assert "## V8 built-ins (Intl)" in out
    assert "| site | script | builtin | calls |" in out
    assert (out.index(f"| https://a.com | a.com/app.js | {RO} | 5 |")
            < out.index(f"| https://a.com | a.com/app.js | {CTOR} | 3 |"))
    assert "v8.run" in out and "blind" not in out
    assert out.index("## V8 built-ins (Intl)") < out.index("## Not observable")


def lev(typ, target="Window", opts="", script="https://a.com/app.js", ts=1, site="https://a.com"):
    e = ev(r.LISTENER, "https://a.com", site, script=script)
    e["ts"] = ts
    e["args"].update(type=typ, target=target, opts=opts)
    return e


def test_listener_types_are_grouped_and_unknown_types_are_never_named():
    secret = "stream-4711-private-id"
    events = [lev("wheel", opts="capture"), lev("wheel", opts="capture"), lev("keydown", "Document"),
              lev("visibilitychange", "Document"), lev("devicemotion"), lev("paste", "HTMLDivElement"),
              lev(secret), lev("another-custom-type")]
    md = r.render(r.events_of(events), [], [])
    assert secret not in md and "another-custom-type" not in md
    assert "Listener types outside the known set: 2 distinct" in md
    c = r.surface_counts(events)["https://a.com"][("https://a.com", "a.com/app.js")]
    assert c[f"{r.LISTENER}[wheel] target=Window opts=capture"] == 2
    assert c[f"{r.LISTENER}[other] target=Window"] == 2
    assert r.group_of(f"{r.LISTENER}[wheel] target=Window") == "input-events"
    assert r.group_of(f"{r.LISTENER}[visibilitychange] target=Document") == "focus-visibility"
    assert r.group_of(f"{r.LISTENER}[devicemotion] target=Window") == "motion"
    assert r.group_of(f"{r.LISTENER}[paste] target=HTMLDivElement") == "clipboard"
    assert r.group_of(f"{r.LISTENER}[other] target=Window") == "listeners-other"


def test_behaviour_members_have_their_groups():
    for name, group in [("Performance.now", "timing"), ("Window.requestAnimationFrame", "timing"),
                        ("Window.setInterval", "timing"), ("WorkerGlobalScope.setTimeout", "timing"),
                        ("Document.hidden.get", "focus-visibility"), ("Document.hasFocus", "focus-visibility"),
                        ("Clipboard.readText", "clipboard"), ("Document.execCommand", "clipboard"),
                        ("DeviceOrientationEvent.alpha.get", "motion"), ("Accelerometer.constructor", "motion")]:
        assert r.group_of(name) == group, name
    assert r.group_of("Document.title.get") == "other"


def test_timing_rate_separates_a_loop_from_a_single_call():
    loop = []
    for i in range(61):  # 61 frames over one second
        e = ev("Window.requestAnimationFrame", "https://a.com", "https://a.com", script="https://a.com/loop.js")
        e["ts"] = 1_000_000 + i * 16_667
        loop.append(e)
    once = ev("Performance.now", "https://a.com", "https://a.com", script="https://a.com/once.js")
    md = r.render(r.events_of(loop + [once]), [], [])
    rates = r.timing_rates(loop + [once])["https://a.com"]
    assert rates[("Window.requestAnimationFrame", "a.com/loop.js")][0] == 61
    assert 59 < rates[("Window.requestAnimationFrame", "a.com/loop.js")][1] < 61
    assert rates[("Performance.now", "a.com/once.js")] == (1, None)
    assert "Timing call rates" in md


def test_not_observable_names_what_dispatch_counts_do_not_cover():
    md = r.render([], [], [])
    assert "per-script dispatch attribution" in md and "dispatch counts" not in md


def dev(typ, dispatches, handlers, target="Element", trusted="false", ts=1):
    return {"name": r.DISPATCH, "cat": CAT, "ph": "I", "pid": 1, "tid": 1, "ts": ts,
            "args": {"type": typ, "target": target, "trusted": trusted, "dispatches": str(dispatches),
                     "handlers": str(handlers), "window_ms": "5"}}


def test_dispatch_rows_sum_flushes_rate_and_join_to_registrations():
    events = [lev("click", "Element", script="https://a.com/a.js"),
              lev("click", "Element", script="https://a.com/b.js"),
              lev("keydown", "Document"), lev("scroll", "DOMWindow"),
              dev("click", 256, 768, ts=1_000_000), dev("click", 512, 1536, ts=3_000_000),
              dev("click", 5, 5, trusted="true"), dev("wheel", 3, 3, target="DOMWindow"),
              dev("mystery-type-7", 2, 2), dev("other-mystery", 4, 4)]
    rows = {(d["type"], d["target"], d["trusted"]): d for d in r.dispatch_rows(events)}
    c = rows[("click", "Element", "false")]
    assert (c["dispatches"], c["handlers"], c["group"]) == (768, 2304, "input-events")
    assert abs(c["rate"] - 384.0) < 1e-6  # 768 over the 2 s between the first and last flush
    assert c["registered_by"] == ["a.com/a.js", "a.com/b.js"]
    assert rows[("click", "Element", "true")]["rate"] is None
    assert rows[("wheel", "DOMWindow", "false")]["registered_by"] == []
    o = rows[("[other]", "Element", "false")]
    assert (o["dispatches"], o["types"]) == (6, 2)
    md = r.render(r.events_of(events), [], [])
    assert "## Listener dispatches" in md
    assert "| input-events | click | Element | false | 768 | 2304 | 384.0 | a.com/a.js, a.com/b.js |" in md
    assert "[other] (2 types)" in md
    assert "mystery-type-7" not in md and "other-mystery" not in md
    assert "Registered but never fired: keydown, scroll" in md
    assert "Fired with no registration seen: wheel, 2 other" in md
    assert "dispatch counts are floor values; up to 255 per type unflushed" in md


def test_dispatch_section_is_absent_without_dispatch_events():
    md = r.render(r.events_of([lev("click")]), [], [])
    assert "Listener dispatches" not in md and "floor values" not in md


def test_dispatch_worker_target_joins_worker_global_scope_registrations():
    events = [lev("message", "DedicatedWorkerGlobalScope", script="https://a.com/w.js"),
              dev("message", 3, 3, target="Worker")]
    assert r.dispatch_rows(events)[0]["registered_by"] == ["a.com/w.js"]


def cost_netlog(tmp_path):
    names = ["URL_REQUEST_START_JOB", "URL_REQUEST_JOB_BYTES_READ", "URL_REQUEST_JOB_FILTERED_BYTES_READ",
             "HTTP_TRANSACTION_SEND_REQUEST", "HTTP_TRANSACTION_QUIC_SEND_REQUEST_HEADERS",
             "HTTP_TRANSACTION_READ_RESPONSE_HEADERS"]
    t = {n: i for i, n in enumerate(names)}

    def e(sid, name, **p):
        # load_requests keeps only PHASE_BEGIN start-job events, so the fixture serves both readers
        return {"source": {"id": sid}, "type": t[name], "phase": 1 if name == "URL_REQUEST_START_JOB" else 0, "params": p}
    ev = [e(1, "URL_REQUEST_START_JOB", url="https://static.xx.fbcdn.net/a.js?x=1", method="GET"),
          e(1, "HTTP_TRANSACTION_QUIC_SEND_REQUEST_HEADERS"),
          e(1, "HTTP_TRANSACTION_READ_RESPONSE_HEADERS", headers=["content-type: application/javascript; charset=utf-8"]),
          e(1, "URL_REQUEST_JOB_BYTES_READ", byte_count=300), e(1, "URL_REQUEST_JOB_FILTERED_BYTES_READ", byte_count=1000),
          e(2, "URL_REQUEST_START_JOB", url="https://static.xx.fbcdn.net/b.css", method="GET"),
          e(2, "HTTP_TRANSACTION_READ_RESPONSE_HEADERS", headers=["Content-Type: text/css"]),
          e(2, "URL_REQUEST_JOB_BYTES_READ", byte_count=50), e(2, "URL_REQUEST_JOB_FILTERED_BYTES_READ", byte_count=200),
          e(3, "URL_REQUEST_START_JOB", url="https://www.facebook.com/ajax/bz?q=secret", method="POST"),
          e(3, "HTTP_TRANSACTION_SEND_REQUEST"), e(3, "URL_REQUEST_JOB_BYTES_READ", byte_count=10)]
    p = tmp_path / "net.json"
    p.write_text(json.dumps({"constants": {"logEventTypes": t, "logEventPhase": {"PHASE_BEGIN": 1, "PHASE_NONE": 0}},
                             "events": ev}))
    return p


def test_costs_split_network_cache_decoded_by_host_and_kind(tmp_path):
    c = r.load_costs(cost_netlog(tmp_path))
    h = c["by_host"]["static.xx.fbcdn.net"]
    assert (h["n"], h["network"], h["cache"], h["decoded"]) == (2, 300, 50, 1200)
    assert c["by_kind"]["js"]["network"] == 300 and c["by_kind"]["css"]["cache"] == 50
    assert c["by_kind"]["beacon"]["n"] == 1
    assert c["posts"] == {"www.facebook.com/ajax/bz": 1}


def test_costs_of_a_cut_netlog_is_none_and_renders_a_line(tmp_path):
    p = tmp_path / "net.json"
    p.write_text('{"constants": {"logEventTypes": {}}, "events": [{"source"')
    assert r.load_costs(p) is None
    assert "netlog unreadable" in r.render_costs(None)


def test_render_costs_never_prints_a_query(tmp_path):
    out = r.render_costs(r.load_costs(cost_netlog(tmp_path)))
    assert "secret" not in out and "x=1" not in out
    assert "static.xx.fbcdn.net" in out


def tl(name, ts, dur, url, tid=1):
    return {"name": name, "cat": "devtools.timeline", "ph": "X", "pid": 1, "tid": tid, "ts": ts, "dur": dur,
            "args": {"data": {"url": url}}}


def test_cpu_counts_nested_slices_once_and_labels_scripts():
    A = "https://static.xx.fbcdn.net/rsrc.php/v3/a.js?x=1"
    ev = [tl("FunctionCall", 0, 5000, A), tl("FunctionCall", 1000, 1000, A),
          tl("v8.compile", 10000, 2000, A), tl("EvaluateScript", 0, 3000, A, tid=2)]
    c = r.cpu_by_script(ev)
    assert c["static.xx.fbcdn.net/rsrc.php/v3/a.js"] == {"run": 8.0, "compile": 2.0}


def test_ram_summary_peak_and_mean(tmp_path):
    p = tmp_path / "ram.json"
    p.write_text(json.dumps({"interval_s": 5, "samples": [
        {"t": 0, "by_type": {"renderer": 100 * 2**20, "browser": 50 * 2**20}},
        {"t": 5, "by_type": {"renderer": 300 * 2**20}}]}))
    s = r.ram_summary(p)
    assert s["renderer"] == {"peak_mb": 300.0, "mean_mb": 200.0, "samples": 2}
    assert r.ram_summary(tmp_path / "absent.json") is None
    assert "renderer" in r.render_ram(s)


CH = {"arm": "3w", "posts_captured": 3, "posts_missing": 1,
      "endpoints": {"www.facebook.com/ajax/bz": {"count": 2, "bytes": 100, "kinds": {"form": 2},
                    "initiators": {"static.xx.fbcdn.net/rsrc.php/v3/a.js": 2},
                    "fields": {"q[].dm": {"count": 2, "classes": {"int": 2}}}},
                    "www.facebook.com/ajax/bnzai": {"count": 1, "bytes": 0, "kinds": {"missing": 1},
                    "initiators": {"(no script)": 1}, "fields": {}}},
      "ws": {"gateway.facebook.com/ws/realtime": {"frames_sent": 1, "frames_received": 2, "bytes_sent": 10,
             "bytes_received": 20, "topics": {"/t_ms": {"count": 1, "fields": {}}}}}}
MT = [{"endpoint": "www.facebook.com/ajax/bz", "field": "q[].dm", "surface": "navigator.deviceMemory",
       "encoding": "exact", "weak": True, "count": 2},
      {"endpoint": "www.facebook.com/ajax/bz", "field": "q[].tz", "surface": "timezone",
       "encoding": "exact", "weak": False, "count": 2}]


def test_channels_list_fields_classes_ws_and_coverage():
    out = r.render_channels(CH, {"posts": {"www.facebook.com/ajax/bz": 2, "www.facebook.com/ajax/bnzai": 1,
                                           "www.facebook.com/ajax/qm/": 4}})
    assert "`q[].dm`" in out and "int" in out
    assert "/t_ms" in out
    assert "captured 3 of 7 POSTs in the netlog (1 without a body)" in out


def test_weak_matches_are_listed_apart():
    out = r.render_matches(MT)
    strong, weak = out.split("Weak matches")
    assert "timezone" in strong and "deviceMemory" not in strong
    assert "deviceMemory" in weak


def test_join_puts_reads_next_to_the_channels_a_script_sent():
    reads = {"static.xx.fbcdn.net/rsrc.php/v3/a.js": collections.Counter({"Navigator.deviceMemory.get": 820})}
    out = r.render_join(CH, MT, reads)
    assert "static.xx.fbcdn.net/rsrc.php/v3/a.js" in out
    assert "Navigator.deviceMemory.get 820" in out and "www.facebook.com/ajax/bz" in out


def test_main_runs_without_a_trace(tmp_path, capsys):
    net = cost_netlog(tmp_path)
    (tmp_path / "channels.json").write_text(json.dumps(CH))
    (tmp_path / "matches.json").write_text(json.dumps(MT))
    sys.argv = ["observe_report.py", "-", str(net), "--channels", str(tmp_path / "channels.json"),
                "--matches", str(tmp_path / "matches.json")]
    r.main()
    out = capsys.readouterr().out
    assert "## Cost" in out and "## Channels" in out and "## Surfaces sent" in out


def test_coverage_counts_only_posts_to_hosts_the_driver_watched():
    out = r.render_channels(CH, {"posts": {"www.facebook.com/ajax/bz": 2, "www.facebook.com/ajax/bnzai": 1,
                                           "content-autofill.googleapis.com/v1/pages/x": 5,
                                           "example.org/collect": 1}})
    assert "captured 3 of 3 POSTs in the netlog (1 without a body)" in out
    assert "6 POSTs to other hosts: content-autofill.googleapis.com, example.org" in out
    assert "/v1/pages" not in out and "/collect" not in out


POP = "scontent.xyz9-1.fna.fbcdn.net"  # synthetic: a POP-style name, never a real code


def test_public_host_collapses_pop_style_media_hosts():
    assert r.public_host(POP) == "scontent.*.fbcdn.net"
    assert r.public_host("scontent-xyz9-1.xx.fbcdn.net") == "scontent.*.fbcdn.net"
    assert r.public_host("video.xyz9-1.fna.fbcdn.net") == "*.fna.fbcdn.net"
    assert r.public_host("media.xyz9-1.fna.whatsapp.net") == "*.fna.whatsapp.net"
    assert r.public_host("static.xx.fbcdn.net") == "static.xx.fbcdn.net"
    assert r.public_host("www.facebook.com") == "www.facebook.com"
    assert r.public_endpoint(POP + "/v/t1/a.jpg") == "scontent.*.fbcdn.net/v/t1/a.jpg"
    assert r.public_endpoint("www.facebook.com/ajax/bz") == "www.facebook.com/ajax/bz"


def pop_netlog(tmp_path, with_encoding_header=False):
    names = ["URL_REQUEST_START_JOB", "URL_REQUEST_JOB_BYTES_READ", "URL_REQUEST_JOB_FILTERED_BYTES_READ",
             "HTTP_TRANSACTION_SEND_REQUEST", "HTTP_TRANSACTION_READ_RESPONSE_HEADERS"]
    t = {n: i for i, n in enumerate(names)}

    def e(sid, name, **p):
        return {"source": {"id": sid}, "type": t[name], "phase": 1 if name == "URL_REQUEST_START_JOB" else 0, "params": p}
    hdrs = ["Content-Type: video/mp4"] + (["Content-Encoding: br"] if with_encoding_header else [])
    ev = [e(1, "URL_REQUEST_START_JOB", url="https://" + POP + "/v/a.mp4?sig=secret", method="GET"),
          e(1, "HTTP_TRANSACTION_SEND_REQUEST"), e(1, "HTTP_TRANSACTION_READ_RESPONSE_HEADERS", headers=hdrs),
          e(1, "URL_REQUEST_JOB_FILTERED_BYTES_READ", byte_count=5000)]
    p = tmp_path / "net.json"
    p.write_text(json.dumps({"constants": {"logEventTypes": t, "logEventPhase": {"PHASE_BEGIN": 1, "PHASE_NONE": 0}},
                             "events": ev}))
    return p


def test_identity_media_without_a_raw_event_counts_on_the_network(tmp_path):
    # no Content-Encoding: the job logs only FILTERED_BYTES_READ, and raw equals decoded
    c = r.load_costs(pop_netlog(tmp_path))
    h = c["by_host"]["scontent.*.fbcdn.net"]
    assert (h["n"], h["network"], h["cache"], h["decoded"]) == (1, 5000, 0, 5000)
    assert not h.get("approx") and POP not in c["by_host"]
    out = r.render_costs(c)
    assert "xyz9" not in out and "decoded used" not in out and "scontent.*.fbcdn.net" in out


def test_encoded_response_without_a_raw_event_uses_decoded_and_is_marked(tmp_path):
    c = r.load_costs(pop_netlog(tmp_path, with_encoding_header=True))
    h = c["by_host"]["scontent.*.fbcdn.net"]
    assert h["network"] == 5000 and h["approx"]
    assert "(decoded used)" in r.render_costs(c)


def test_request_table_and_script_labels_collapse_pop_hosts(tmp_path):
    reqs = r.load_requests(pop_netlog(tmp_path))
    assert reqs[0][1] == "scontent.*.fbcdn.net"
    assert r.script_label("https://" + POP + "/x.js?q=1") == "scontent.*.fbcdn.net/x.js"
    ch = {"arm": "x", "posts_captured": 0, "posts_missing": 0, "ws": {},
          "endpoints": {POP + "/upload": {"count": 1, "bytes": 1, "kinds": {"form": 1}, "initiators": {},
                                          "fields": {}}}}
    assert "xyz9" not in r.render_channels(ch, {"posts": {POP + "/upload": 1}})


def site_netlog(tmp_path):
    names = ["URL_REQUEST_START_JOB", "URL_REQUEST_JOB_BYTES_READ", "HTTP_TRANSACTION_SEND_REQUEST",
             "HTTP_TRANSACTION_READ_RESPONSE_HEADERS"]
    t = {n: i for i, n in enumerate(names)}

    def e(sid, name, **p):
        return {"source": {"id": sid}, "type": t[name], "phase": 1 if name == "URL_REQUEST_START_JOB" else 0, "params": p}

    def job(sid, url, nik, n, ct):
        return [e(sid, "URL_REQUEST_START_JOB", url=url, method="GET", network_isolation_key=nik),
                e(sid, "HTTP_TRANSACTION_SEND_REQUEST"),
                e(sid, "HTTP_TRANSACTION_READ_RESPONSE_HEADERS", headers=["Content-Type: " + ct]),
                e(sid, "URL_REQUEST_JOB_BYTES_READ", byte_count=n)]
    ev = (job(1, "https://static.xx.fbcdn.net/a.js", "https://facebook.com https://facebook.com", 100, "text/javascript")
          + job(2, "https://optimizationguide-pa.googleapis.com/v1/x", "", 4000, "text/html")
          + job(3, "https://edgedl.example.net/c.crx", "chrome://newtab chrome://newtab", 50, "text/html"))
    p = tmp_path / "net.json"
    p.write_text(json.dumps({"constants": {"logEventTypes": t, "logEventPhase": {"PHASE_BEGIN": 1, "PHASE_NONE": 0}},
                             "events": ev}))
    return p


def test_costs_split_by_top_level_site_and_browser_internal(tmp_path):
    c = r.load_costs(site_netlog(tmp_path))
    assert c["by_site_kind"]["https://facebook.com"] == {"js": {"n": 1, "network": 100, "cache": 0, "decoded": 100}}
    b = c["by_site_kind"]["browser"]["html"]
    assert (b["n"], b["network"]) == (2, 4050)
    out = r.render_costs(c)
    assert out.index("https://facebook.com") < out.index("browser-internal")

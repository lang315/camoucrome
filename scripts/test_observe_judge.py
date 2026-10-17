"""observe_judge.py on hand-made fixtures shaped like the host's arm directories."""
import json
import pathlib
import sqlite3
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import observe_judge as j  # noqa: E402

CAT = "disabled-by-default-camou.observe"
FB = "https://facebook.com"


def ev(name, ts=1_000_000, site=FB, origin="https://www.facebook.com",
       script="https://static.xx.fbcdn.net/rsrc.php/v4/a.js?_nc_x=SECRETQ"):
    return {"name": name, "cat": CAT, "ph": "I", "pid": 1, "tid": 1, "ts": ts,
            "args": {"origin": origin, "site": site, "script": script}}


def rcs(ts, stats):
    return {"name": "V8.Execute", "cat": "v8", "ph": "X", "pid": 1, "tid": 1, "ts": ts,
            "dur": 10, "args": {"runtime-call-stats": stats}}


def make_arm(tmp_path, events=None, discarded=0, buffer_stats=True, net_span_ms=30_000,
             cookies=(("datr", "SECRETVAL"),), run=None, bom=False, trace=True, net=True):
    d = tmp_path / "arm"
    d.mkdir(parents=True, exist_ok=True)
    if events is None:
        events = [ev("Navigator.userAgent.get"), ev("Navigator.userAgent.get", ts=31_000_000),
                  ev("HTMLCanvasElement.toDataURL"),
                  rcs(2_000_000, {"DateTimeFormatConstructor": [4, 1.0]})]
    if trace:
        data = {"traceEvents": events}
        if buffer_stats:
            data["metadata"] = {"trace_processor_stats": {"traced_buf": [
                {"buffer_size": 1, "chunks_discarded": discarded}]}}
        (d / "trace.json").write_text(json.dumps(data))
    if net:
        start = {"type": 7, "phase": 1, "time": "1000", "params": {
            "url": "https://www.facebook.com/ajax/bz?__a=1&fb_dtsg=SECRETQ", "method": "POST",
            "network_isolation_key": "https://facebook.com https://facebook.com",
            "site_for_cookies": ""}}
        end = dict(start, phase=2, time=str(1000 + net_span_ms))
        (d / "net.json").write_text(json.dumps({
            "constants": {"logEventTypes": {"URL_REQUEST_START_JOB": 7},
                          "logEventPhase": {"PHASE_BEGIN": 1, "PHASE_END": 2}},
            "events": [start, end]}))
    con = sqlite3.connect(d / "cookies.db")
    con.execute("create table cookies (host_key text, name text, value text, "
                "encrypted_value blob, expires_utc integer, is_httponly integer)")
    for name, value in cookies:
        con.execute("insert into cookies values ('.facebook.com', ?, ?, x'00', 1, 1)", (name, value))
    con.commit()
    con.close()
    if run is None:
        run = {"session": 1, "session_state": "Active", "report_rc": 0, "left": 0,
               "low_memory_kill": False, "gpu_exit_lines": 0}
    if run != "absent":
        (d / "run.json").write_text(("\ufeff" if bom else "") + json.dumps(run), encoding="utf-8")
    return d


def test_summary_counts_groups_members_intl_requests_cookies(tmp_path):
    s = j.summarize(make_arm(tmp_path))
    assert s["members"] == {"Navigator.userAgent.get": 2, "HTMLCanvasElement.toDataURL": 1}
    assert s["groups"] == {"navigator": 2, "canvas": 1, "intl": 4}
    assert s["intl"] == {"DateTimeFormatConstructor": 4}
    assert s["requests"] == {"total": 1, "ajax_bz": 1}
    assert s["cookies"] == [".facebook.com:datr"]
    assert s["coverage"] == {"trace_s": 30.0, "net_s": 30.0, "discarded": 0}
    assert s["run"]["session"] == 1


def test_summary_counts_only_the_facebook_site(tmp_path):
    events = [ev("Screen.width.get", site="https://google.com"), ev("Navigator.platform.get")]
    s = j.summarize(make_arm(tmp_path, events=events))
    assert s["members"] == {"Navigator.platform.get": 1}


def test_summary_never_carries_queries_script_paths_or_cookie_values(tmp_path):
    out = json.dumps(j.summarize(make_arm(tmp_path)))
    for leak in ("SECRETQ", "SECRETVAL", "fbcdn", "rsrc.php", "?", "fb_dtsg"):
        assert leak not in out, leak


def test_summary_intl_none_when_blind(tmp_path):
    s = j.summarize(make_arm(tmp_path, events=[ev("Navigator.userAgent.get")]))
    assert s["intl"] is None and "intl" not in s["groups"]


def test_summary_reads_a_bom_run_json(tmp_path):
    assert j.summarize(make_arm(tmp_path, bom=True))["run"]["session_state"] == "Active"


def test_summary_missing_trace_or_netlog_raises_missing_input(tmp_path):
    with pytest.raises(j.MissingInput, match="trace"):
        j.summarize(make_arm(tmp_path / "a", trace=False))
    with pytest.raises(j.MissingInput, match="netlog"):
        j.summarize(make_arm(tmp_path / "b", net=False))


def test_judge_parses_as_python_3_9():
    """The Windows host runs Python 3.9.13."""
    import ast
    ast.parse(pathlib.Path(j.__file__).read_text(), feature_version=(3, 9))

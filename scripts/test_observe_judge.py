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


BASE = {"1": {"required": ["navigator", "canvas", "intl"], "runs": [
    {"groups": {"navigator": 2, "canvas": 1, "intl": 4}, "intl": {}, "requests": {}}]}}


def verdict(tmp_path, arm=1, base=BASE, **kw):
    return j.judge(make_arm(tmp_path, **kw), arm, base)


def test_pass_when_measured_and_every_required_group_seen(tmp_path):
    v, rows = verdict(tmp_path)
    assert v == "PASS"
    assert ("PASS", "canvas 1") in rows


@pytest.mark.parametrize("kw,why", [
    ({"run": "absent"}, "run.json missing"),
    ({"run": {"session": 0, "session_state": "Active", "report_rc": 0, "left": 0}}, "session=0"),
    ({"run": {"session": 1, "session_state": "Disc", "report_rc": 0, "left": 0}}, "session_state=Disc"),
    ({"run": {"session": 1, "session_state": "Active", "report_rc": 1, "left": 0}}, "report_rc=1"),
    ({"run": {"session": 1, "session_state": "Active", "report_rc": 0, "left": 3}}, "left=3"),
    ({"run": {"session": 1, "session_state": "Active", "report_rc": 0, "left": 0,
              "low_memory_kill": True}}, "low-memory"),
    ({"run": {"session": 1, "session_state": "Active", "report_rc": 0, "left": 0,
              "gpu_exit_lines": 1}}, "gpu-crash"),
    ({"discarded": 7}, "buffer full"),
    ({"buffer_stats": False}, "buffer stats missing"),
    ({"net_span_ms": 60_000}, "trace short"),
    ({"events": [ev("Navigator.userAgent.get")]}, "intl blind"),
    ({"trace": False}, "no trace"),
    ({"net": False}, "no netlog"),
])
def test_unmeasured_causes(tmp_path, kw, why):
    v, rows = verdict(tmp_path, **kw)
    assert v == "UNMEASURED"
    assert any(level == "UNMEASURED" and why in text for level, text in rows), rows


def test_arm3_without_login_cookies_is_session_expired(tmp_path):
    v, rows = verdict(tmp_path, arm=3, base={})
    assert v == "UNMEASURED"
    assert any("session expired" in t and "-Arm 2" in t for _l, t in rows)
    v, _ = verdict(tmp_path / "x", arm=3, base={},
                   cookies=(("c_user", "1"), ("xs", "2"), ("datr", "3")))
    assert v == "PASS"


def test_fail_when_a_required_group_is_gone(tmp_path):
    base = {"1": {"required": ["navigator", "webgpu"], "runs": []}}
    v, rows = verdict(tmp_path, base=base)
    assert v == "FAIL" and ("FAIL", "webgpu 0") in rows


def test_intl_measured_but_empty_fails_a_required_intl(tmp_path):
    events = [ev("Navigator.userAgent.get"), ev("HTMLCanvasElement.toDataURL"),
              ev("Navigator.userAgent.get", ts=31_000_000),
              rcs(2_000_000, {"ArrayPrototypePush": [1, 1.0]})]
    v, rows = verdict(tmp_path, events=events)
    assert v == "FAIL" and ("FAIL", "intl 0") in rows


def test_unmeasured_wins_over_fail(tmp_path):
    base = {"1": {"required": ["webgpu"], "runs": []}}
    assert verdict(tmp_path, base=base, discarded=1)[0] == "UNMEASURED"


def test_drift_and_new_groups_are_info_only(tmp_path):
    base = {"1": {"required": ["navigator"], "runs": [{"groups": {"navigator": 50}}]}}
    v, rows = verdict(tmp_path, base=base)
    assert v == "PASS"
    assert ("INFO", "navigator 2 vs baseline [50]") in rows
    assert ("INFO", "new group canvas 1") in rows


def test_empty_baseline_requires_nothing(tmp_path):
    assert verdict(tmp_path, base={})[0] == "PASS"


def test_baseline_requires_groups_seen_in_every_run(tmp_path):
    a = {"groups": {"navigator": 2, "canvas": 1}, "intl": {}, "requests": {"total": 1}}
    b = {"groups": {"navigator": 5, "audio": 9}, "intl": {}, "requests": {"total": 2}}
    base = j.make_baseline({1: [a, b]})
    assert base["1"]["required"] == ["navigator"]
    assert [x["groups"] for x in base["1"]["runs"]] == [a["groups"], b["groups"]]


def test_cli_exit_codes_and_usage_errors(tmp_path, capsys):
    arm = make_arm(tmp_path / "a")
    bfile = tmp_path / "b.json"
    bfile.write_text(json.dumps(BASE))
    assert j.main(["judge", "--baseline", str(bfile), "--arm", "1", str(arm)]) == 0
    assert "arm1 PASS" in capsys.readouterr().out
    bfile.write_text(json.dumps({"1": {"required": ["webgpu"], "runs": []}}))
    assert j.main(["judge", "--baseline", str(bfile), "--arm", "1", str(arm)]) == 1
    assert j.main(["judge", "--baseline", str(tmp_path / "none.json"), "--arm", "1", str(arm)]) == 2
    out = tmp_path / "base.json"
    assert j.main(["baseline", "--arm", "1", str(arm), "-o", str(out)]) == 0
    assert json.loads(out.read_text())["1"]["required"] == ["canvas", "intl", "navigator"]
    so = tmp_path / "s.json"
    j.main(["judge", "--baseline", str(out), "--arm", "1", str(arm), "--summary-out", str(so)])
    assert json.loads(so.read_text())["groups"]["canvas"] == 1


def run_cli(*args):
    import subprocess
    return subprocess.run([sys.executable, j.__file__, *args], capture_output=True, text=True)


@pytest.mark.parametrize("break_it,err", [
    (lambda d: (d / "run.json").write_text("{"), "JSONDecodeError"),
    (lambda d: (d / "cookies.db").write_bytes(b"not a database, padded" * 64), "DatabaseError"),
])
def test_cli_judge_crash_is_unmeasured_not_fail(tmp_path, break_it, err):
    """observe-auto reads exit 1 as FAIL; a crash measured nothing."""
    arm = make_arm(tmp_path / "a")
    break_it(arm)
    bfile = tmp_path / "b.json"
    bfile.write_text(json.dumps(BASE))
    p = run_cli("judge", "--baseline", str(bfile), "--arm", "1", str(arm))
    assert p.returncode == 3, p.stdout + p.stderr
    assert f"UNMEASURED arm1 judge error ({err})" in p.stdout


@pytest.mark.parametrize("base", [[], {"3": {"required": ["navigator"], "runs": []}}])
def test_cli_judge_refuses_a_baseline_that_is_not_for_this_arm(tmp_path, base):
    arm = make_arm(tmp_path / "a")
    bfile = tmp_path / "b.json"
    bfile.write_text(json.dumps(base))
    p = run_cli("judge", "--baseline", str(bfile), "--arm", "1", str(arm))
    assert p.returncode == 2, p.stdout + p.stderr
    assert "usage error: baseline" in p.stderr


def test_empty_required_says_pass_means_measured_only(tmp_path):
    v, rows = verdict(tmp_path, base={})
    assert v == "PASS"
    assert ("INFO", "baseline requires 0 groups: PASS means measured only") in rows


@pytest.mark.parametrize("kw,why", [
    ({"events": [ev("Navigator.userAgent.get")]}, "intl blind"),
    ({"run": "absent"}, "run.json missing"),
    ({"trace": False}, "no trace"),
])
def test_baseline_refuses_an_unmeasured_run(tmp_path, capsys, kw, why):
    good = make_arm(tmp_path / "good")
    bad = make_arm(tmp_path / "bad", **kw)
    out = tmp_path / "base.json"
    rc = j.main(["baseline", "--arm", "1", str(good), "--arm", "1", str(bad), "-o", str(out)])
    assert rc == 2
    assert why in capsys.readouterr().err
    assert not out.exists()

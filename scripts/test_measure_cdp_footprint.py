"""Orchestrator of the CDP footprint harness, with one fake script standing in for the drivers and the browser."""
import json
import pathlib
import re
import sys
import urllib.request

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import measure_cdp_footprint as m  # noqa: E402

FAKE = r'''
import json, os, re, sys, time, urllib.parse, urllib.request
a = sys.argv[1:]
def opt(k): return a[a.index(k) + 1] if k in a else None
role_driver = "--exe" in a
profile = opt("--profile") if role_driver else next(x for x in a if x.startswith("--user-data-dir="))[16:]
arm = re.search(r"[LDF]-(none|tdp-main|tdp|red)-", profile.replace("\\", "/")).group(1)
mode = os.environ.get("FAKE_MODE", "pass")
os.makedirs(profile, exist_ok=True)
if mode != "nolog":
    open(os.path.join(profile, "chrome_debug.log"), "w").write("[1:2] GPU process exited unexpectedly: exit_code=8\n" if mode == "gpu" else "ok\n")
url = opt("--url") if role_driver else a[-1]
if "/probe.html" in url and mode != "nopost":
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    flag = arm == "red" or (mode == "tdpflag" and arm == "tdp")
    urllib.request.urlopen(urllib.request.Request(url.split("/probe.html")[0] + "/result?arm=%s&run=%s" % (arm, q["run"][0]),
                           json.dumps({"L1": flag, "L2": [1.0, 2.0, 3.0]}).encode()))
if role_driver and opt("--mode") == "detector" and mode == "noout" and arm == "tdp":
    sys.exit(0)
if role_driver and opt("--mode") == "detector":
    t = "\U0001f534 runtimeEnableLeak\t1ms\t" if arm == "red" else "\U0001f7e2 runtimeEnableLeak\t1ms\t"
    json.dump({"driver": "fake", "text": t}, open(opt("--out"), "w"))
    sys.exit(0)
if role_driver and opt("--mode") == "facebook":
    sys.exit(0)
if role_driver:
    sys.stdin.read()  # EOF ends the driver
    json.dump({"driver": "fake", "text": "SECRET PAGE TEXT", "error": "boom" if mode == "drverr" else None}, open(opt("--out"), "w"))
else:
    time.sleep(60)
'''


@pytest.fixture
def env(tmp_path, monkeypatch):
    fake = tmp_path / "fake.py"
    fake.write_text(FAKE)
    exe = tmp_path / "fakechrome"
    exe.write_text(f"#!{sys.executable}\nimport runpy,sys\nsys.argv=sys.argv[:1]+sys.argv[1:]\nrunpy.run_path({str(fake)!r}, run_name='__main__')\n")
    exe.chmod(0o755)
    monkeypatch.setattr(m, "identity", lambda: ({}, ["--enable-logging", "--v=0"]))
    monkeypatch.setattr(m, "gate", lambda: None)
    monkeypatch.setattr(m, "driver_cmd", lambda drivers, arm: [sys.executable, str(fake)])
    monkeypatch.setattr(m, "FB_WAIT", 1)
    monkeypatch.setattr(m, "on_host", lambda: True)

    def run(*extra, mode="pass"):
        monkeypatch.setenv("FAKE_MODE", mode)
        out = tmp_path / "out"
        out.mkdir(exist_ok=True)
        rc = m.main(["--exe", str(exe), "--drivers", str(tmp_path), "--out", str(out), "--l-timeout", "2", *extra])
        return rc, json.loads((out / "table.json").read_text()), out
    return run


def test_arm_order_alternates(env):
    rc, t, _ = env("--groups", "L,D")
    assert t["order"]["L"] == ["none", "tdp", "tdp-main", "red"]
    assert t["order"]["D"] == ["red", "tdp-main", "tdp"]  # reversed; none has no reader


def test_no_post_times_out_unmeasured(env):
    rc, t, _ = env("--groups", "L", mode="nopost")
    assert rc == 3 and set(t["rows"]["L1"].values()) == {"UNMEASURED"}


def test_exit_1_when_tdp_fails(env, monkeypatch):
    monkeypatch.setattr(m.rows, "judge_row", lambda row, r: {"tdp": "FAIL", "tdp-main": "PASS", "red": "FAIL"})
    rc, t, _ = env("--groups", "L")
    assert rc == 1


def test_exit_3_when_only_unmeasured(env, monkeypatch):
    monkeypatch.setattr(m.rows, "judge_row", lambda row, r: {"tdp": "PASS", "tdp-main": "UNMEASURED", "red": "FAIL"})
    rc, t, _ = env("--groups", "L")
    assert rc == 3


def test_all_pass_exit_0(env, monkeypatch):
    monkeypatch.setattr(m.rows, "judge_row", lambda row, r: {"tdp": "PASS", "tdp-main": "PASS", "red": "FAIL"})
    rc, t, _ = env("--groups", "L")
    assert rc == 0


def test_empty_table_exit_3(env):
    rc, t, _ = env("--groups", "X")
    assert t["rows"] == {} and rc == 3


def test_red_fail_alone_does_not_fail(env):
    assert m.exit_code({"L1": {"none": "PASS", "tdp": "PASS", "tdp-main": "PASS", "red": "FAIL"}}) == 0


def test_real_flag_row_fails_tdp(env):
    rc, t, _ = env("--groups", "L", mode="tdpflag")
    assert t["rows"]["L1"] == {"tdp": "FAIL", "tdp-main": "PASS", "red": "FAIL"}


def test_late_result_without_done_is_unmeasured(env, monkeypatch):
    monkeypatch.setattr(m, "_ok", lambda url: False)  # the result file exists, /done never held
    rc, t, _ = env("--groups", "L")
    assert set(t["rows"]["L1"].values()) == {"UNMEASURED"}


def test_gpu_crash_is_unmeasured(env):
    rc, t, _ = env("--groups", "L", mode="gpu")
    assert set(t["rows"]["L1"].values()) == {"UNMEASURED"} and any("GPU process crashed" in n for n in t["notes"])


def test_driver_without_out_is_unmeasured(env):
    rc, t, _ = env("--groups", "D", mode="noout")  # only the tdp driver exits without --out; red still trips the control
    r = t["rows"]["D.rebrowser.runtimeEnableLeak"]
    assert (r["tdp"], r["tdp-main"], r["red"]) == ("UNMEASURED", "PASS", "FAIL")


def test_gate_exception_is_unmeasured(env, monkeypatch):
    def boom():
        raise OSError("quser missing")
    monkeypatch.setattr(m, "gate", boom)
    rc, t, _ = env("--groups", "L")
    assert rc == 3 and "L none: gate error OSError" in t["notes"]


def test_d_rows_status_mapping():
    red = {"runtimeEnableLeak": "fail", "a": "fail", "b": "fail"}
    r = m.d_rows({("red", "rebrowser"): red, ("tdp", "rebrowser"): {"runtimeEnableLeak": "pass", "a": "pass", "b": "not triggered"}}, ["red", "tdp"])
    assert (r["D.rebrowser.a"]["tdp"], r["D.rebrowser.b"]["tdp"]) == ("PASS", "UNMEASURED")


def test_d_dead_control_is_per_row():
    red = {"runtimeEnableLeak": "fail", "a": "pass"}  # red trips one row, not the other
    r = m.d_rows({("red", "rebrowser"): red, ("tdp", "rebrowser"): {"runtimeEnableLeak": "pass", "a": "pass"}}, ["red", "tdp"])
    assert r["D.rebrowser.runtimeEnableLeak"]["tdp"] == "PASS" and r["D.rebrowser.a"] == {"red": "UNMEASURED", "tdp": "UNMEASURED", "none": "n/a"}


def test_creepjs_rows_never_counted():
    t = m.d_rows({}, ["tdp"])
    assert t["D.creepjs.lies"]["tdp"] == "UNMEASURED"
    assert m.exit_code({"D.creepjs.lies": {"tdp": "UNMEASURED", "tdp-main": "UNMEASURED"}, "L1": {"tdp": "PASS", "tdp-main": "PASS"}}) == 0


def test_gate_failure_is_unmeasured(env, monkeypatch):
    monkeypatch.setattr(m, "gate", lambda: "low-memory")
    rc, t, _ = env("--groups", "L")
    assert rc == 3 and "L none: low-memory" in t["notes"]


def test_d_group_verdicts_and_dead_control(env):
    rc, t, _ = env("--groups", "D")
    r = t["rows"]["D.rebrowser.runtimeEnableLeak"]
    assert r == {"none": "n/a", "tdp": "PASS", "tdp-main": "PASS", "red": "FAIL"} and rc == 0  # creepjs rows are UNMEASURED and not counted
    assert set(t["rows"]["D.creepjs.lies"].values()) == {"UNMEASURED", "n/a"}
    assert m.d_rows({("red", "rebrowser"): {"runtimeEnableLeak": "pass"}, ("tdp", "rebrowser"): {"runtimeEnableLeak": "pass"}},
                    ["red", "tdp"])["D.rebrowser.runtimeEnableLeak"]["tdp"] == "UNMEASURED"


def test_raw_deleted_after_judge(env, monkeypatch):
    seen, alive = [], []

    def summ(d):
        alive.append([p.exists() for p in seen])  # earlier arms' raw must be gone already
        seen.append(d)
        return {"groups": {"g": 1}, "intl": None, "requests": {"total": 3, "ajax_bz": 0}}
    monkeypatch.setattr(m.observe_judge, "summarize", summ)
    rc, t, out = env("--groups", "L,F")
    assert len(seen) == 4 and not any(map(any, alive)) and not (out / "raw").exists()
    assert t["rows"]["F.observer"] == {"none": "PASS", "tdp": "UNMEASURED", "tdp-main": "UNMEASURED", "red": "PASS"}  # red = none: dead control
    assert "F: red shows no difference from none; differences are leads only" in t["notes"]
    assert "SECRET" not in (out / "table.json").read_text() + (out / "table.md").read_text()
    env("--groups", "L", "--keep-raw")
    assert (out / "raw").exists()


def _fb_summ(by_arm):
    def summ(d):
        return by_arm[re.search(r"F-(none|tdp-main|tdp|red)-", str(d)).group(1)]
    return summ


def _sum(groups, bz=0):
    return {"groups": groups, "intl": None, "requests": {"total": 3, "ajax_bz": bz}}


def test_f_live_control_keeps_verdicts(env, monkeypatch):
    by = {"none": _sum({"g": 1}), "tdp": _sum({"g": 1}), "tdp-main": _sum({"g": 1, "x": 1}), "red": _sum({})}
    by["red"] = _sum({"g": 1, "y": 1})
    monkeypatch.setattr(m.observe_judge, "summarize", _fb_summ(by))
    rc, t, _ = env("--groups", "F")
    assert t["rows"]["F.observer"] == {"none": "PASS", "tdp": "PASS", "tdp-main": "FAIL", "red": "FAIL"} and rc == 1


def test_f_ajax_bz_is_information_only(env, monkeypatch):
    by = {"none": _sum({"g": 1}, 1), "tdp": _sum({"g": 1}, 9), "tdp-main": _sum({"g": 1}, 9), "red": _sum({"g": 1, "y": 1}, 1)}
    monkeypatch.setattr(m.observe_judge, "summarize", _fb_summ(by))
    rc, t, _ = env("--groups", "F")
    assert t["rows"]["F.observer"]["tdp"] == "PASS"
    assert any(l.startswith("ajax_bz") for l in t["details"]["F.observer tdp"])


def test_driver_error_in_out_is_unmeasured(env):
    rc, t, _ = env("--groups", "L", mode="drverr")
    assert set(t["rows"]["L1"].values()) == {"UNMEASURED"}


def test_l_timing_details_are_numbers(env):
    rc, t, _ = env("--groups", "L")
    assert t["details"]["L.timing L2"]["tdp"] == {"min": 1.0, "median": 2.0, "max": 3.0}


def test_entry_exception_exits_3(monkeypatch, capsys):
    def boom(argv=None):
        raise RuntimeError("SECRET")
    monkeypatch.setattr(m, "main", boom)
    assert m.entry([]) == 3 and "UNMEASURED: RuntimeError" in capsys.readouterr().out


def test_missing_debug_log_is_unmeasured(env):
    rc, t, _ = env("--groups", "L", mode="nolog")
    assert set(t["rows"]["L1"].values()) == {"UNMEASURED"} and any("no debug log" in n for n in t["notes"])


def test_group_f_refused_off_host(env, monkeypatch):
    monkeypatch.setattr(m, "on_host", lambda: False)
    rc, t, _ = env("--groups", "F")
    assert set(t["rows"]["F.observer"].values()) == {"UNMEASURED"} and rc == 3 and "F: not run off-host" in t["notes"]


def test_reap_ends_orphan_with_profile_path(tmp_path):
    import subprocess
    prof = tmp_path / "profile-xyz"
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", str(prof)])
    m.reap(prof)
    assert p.wait(10) is not None
    assert p.returncode != 0

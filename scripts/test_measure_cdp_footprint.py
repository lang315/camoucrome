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
url = opt("--url") if role_driver else a[-1]
if "/probe.html" in url and mode != "nopost":
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    flag = arm == "red" or (mode == "tdpflag" and arm == "tdp")
    urllib.request.urlopen(urllib.request.Request(url.split("/probe.html")[0] + "/result?arm=%s&run=%s" % (arm, q["run"][0]),
                           json.dumps({"L1": flag}).encode()))
if role_driver and opt("--mode") == "detector":
    t = "\U0001f534 runtimeEnableLeak\t1ms\t" if arm == "red" else "\U0001f7e2 runtimeEnableLeak\t1ms\t"
    json.dump({"driver": "fake", "text": t}, open(opt("--out"), "w"))
    sys.exit(0)
if role_driver and opt("--mode") == "facebook":
    sys.exit(0)
if role_driver:
    sys.stdin.read()  # EOF ends the driver
    json.dump({"driver": "fake", "text": "SECRET PAGE TEXT"}, open(opt("--out"), "w"))
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


def test_exit_codes(env):
    rc, t, _ = env("--groups", "L", mode="tdpflag")
    assert rc == 1 and t["rows"]["L1"] == {"tdp": "FAIL", "tdp-main": "PASS", "red": "FAIL"}
    rc, t, _ = env("--groups", "L", mode="pass")
    assert rc == 3


def test_row_fail_is_exit_1(env, monkeypatch):
    monkeypatch.setattr(m.rows, "judge_row", lambda row, r: {"tdp": "FAIL", "tdp-main": "PASS", "red": "FAIL"})
    rc, t, _ = env("--groups", "L")
    assert rc == 1


def test_gate_failure_is_unmeasured(env, monkeypatch):
    monkeypatch.setattr(m, "gate", lambda: "low-memory")
    rc, t, _ = env("--groups", "L")
    assert rc == 3 and "L none: low-memory" in t["notes"]


def test_d_group_verdicts_and_dead_control(env):
    rc, t, _ = env("--groups", "D")
    r = t["rows"]["D.rebrowser.runtimeEnableLeak"]
    assert r == {"none": "n/a", "tdp": "PASS", "tdp-main": "PASS", "red": "FAIL"} and rc == 3  # creepjs and dbi_bot rows have no text: UNMEASURED
    assert m.d_rows({("red", "rebrowser"): {"runtimeEnableLeak": "pass"}, ("tdp", "rebrowser"): {"runtimeEnableLeak": "pass"}},
                    ["red", "tdp"])["D.rebrowser.runtimeEnableLeak"]["tdp"] == "UNMEASURED"


def test_raw_deleted_after_judge(env, monkeypatch):
    seen = []

    def summ(d):
        seen.append(d)
        return {"groups": {"g": 1}, "intl": None, "requests": {"total": 3, "ajax_bz": 0}}
    monkeypatch.setattr(m.observe_judge, "summarize", summ)
    rc, t, out = env("--groups", "L,F")
    assert len(seen) == 4 and not (out / "raw").exists()
    assert t["rows"]["F.observer"] == {"none": "PASS", "tdp": "PASS", "tdp-main": "PASS", "red": "PASS"}
    assert "SECRET" not in (out / "table.json").read_text() + (out / "table.md").read_text()
    env("--groups", "L", "--keep-raw")
    assert (out / "raw").exists()

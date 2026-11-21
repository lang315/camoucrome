"""Orchestrator of the driver probes, with one fake script standing in for the drivers and the browser."""
import json
import pathlib
import socket
import sys
import urllib.parse

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import measure_driver_probes as m  # noqa: E402

FAKE = r'''
import json, os, socket, sys, urllib.parse, urllib.request
a = sys.argv[1:]
def opt(k): return a[a.index(k) + 1] if k in a else None
driver = "--exe" in a
url = opt("--url") if driver else a[-1]
arm = os.environ["FAKE_ARM"] if driver else "none"
u = urllib.parse.urlparse(url)
host, port = u.hostname, u.port
LEAK = os.environ.get("FAKE_LEAK", "red")
if u.path == "/l9.html":
    q = urllib.parse.parse_qs(u.query)
    frame = "    at HTMLInputElement.<anonymous> (http://127.0.0.1:%d/l9.html?arm=x&run=y:1:1)" % port
    stack = "Error\n" + frame + ("\n    at pptr:footprint:1:1" if arm == LEAK else "")
    fires = [{"type": t, "stack": stack, "sites": [], "script": "null"} for t in @EVENTS@]
    urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:%d/result?arm=%s&run=%s" % (port, q["arm"][0], q["run"][0]), json.dumps(fires).encode()))
if u.path == "/h.html":
    cond = urllib.parse.parse_qs(u.query)["c"][0]
    def req(hdrs):
        for kind in ("fetch", "xhr"):
            for i in range(3):
                s = socket.create_connection((host, port))
                s.sendall(("GET /hdr?c=%s&k=%s&i=%d HTTP/1.1\r\n" % (cond, kind, i) + "".join("%s: 1\r\n" % h for h in hdrs) + "\r\n").encode())
                s.recv(4096); s.close()
    base = ["Host", "Accept", "X-A"]
    if driver:
        for c in ("plain", "route", "override"):
            cond = c
            h = list(base)
            if arm == LEAK and c != "plain": h = ["host", "x-a", "accept"]  # reordered and lower-cased
            if c == "override": h.append("X-Probe")
            req(h)
    else:
        req(base)
if driver:
    json.dump({"driver": arm, "acts": {}, "error": None}, open(opt("--out"), "w"))
'''


@pytest.fixture
def env(tmp_path, monkeypatch):
    from driver_probes_rows import EVENTS
    fake = tmp_path / "fake.py"
    fake.write_text(FAKE.replace("@EVENTS@", repr(list(EVENTS))))
    exe = tmp_path / "fakechrome"
    exe.write_text(f"#!{sys.executable}\nimport runpy\nrunpy.run_path({str(fake)!r}, run_name='__main__')\n")
    exe.chmod(0o755)

    def cmd(drivers, arm):
        w = tmp_path / f"drv-{arm}"
        w.write_text(f"#!/bin/sh\nFAKE_ARM={arm} exec {sys.executable} {fake} \"$@\"\n")
        w.chmod(0o755)
        return [str(w)]
    monkeypatch.setattr(m, "driver_cmd", cmd)

    def run(*extra, leak="red"):
        monkeypatch.setenv("FAKE_LEAK", leak)
        out = tmp_path / "out"
        rc = m.main(["--exe", str(exe), "--drivers", str(tmp_path), "--out", str(out), "--timeout", "20", *extra])
        return rc, json.loads((out / "table.json").read_text())
    return run


def test_l9_red_fails_clean_arm_passes(env):
    rc, t = env("--groups", "L9", "--arms", "control,rod,red")
    assert all(v["red"] == "FAIL" and v["rod"] == "PASS" for v in t["rows"].values()) and len(t["rows"]) == 10
    assert rc == 0  # red is the control: its FAILs are expected


def test_l9_leaking_driver_with_a_live_red_exits_1(env):
    rc, t = env("--groups", "L9", "--arms", "control,rod,red", leak="rod")
    assert all(v["rod"] == "UNMEASURED" and v["red"] == "UNMEASURED" for v in t["rows"].values())  # red passes: dead control
    assert rc == 3


def test_exit_1_when_a_driver_fails():
    assert m.exit_code({"r": {"tdp": "FAIL", "red": "FAIL"}}) == 1
    assert m.exit_code({"r": {"tdp": "PASS", "red": "FAIL"}}) == 0
    assert m.exit_code({"r": {"tdp": "UNMEASURED", "red": "FAIL"}}) == 3


def test_h_reordered_lowercased_red_fails_clean_passes_override_modulo_added(env):
    rc, t = env("--groups", "H", "--arms", "control,rod,red")
    for row, v in t["rows"].items():
        assert v["red"] == "FAIL", row
        assert v["control"] == "PASS", row  # the added X-Probe is removed before comparing, and its landing is reported
        assert v["rod"] == "PASS", row
    assert any("landing" in k for k in t["details"])


def test_h_dead_control_when_red_is_clean(env):
    rc, t = env("--groups", "H", "--arms", "control,red", leak="nobody")
    assert {c for v in t["rows"].values() for c in v.values()} <= {"UNMEASURED", "n/a"}

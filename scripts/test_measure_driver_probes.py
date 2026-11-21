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
    T = @TARGET@
    fires = [{"type": t, "target": T[t], "stack": stack, "sites": [], "script": "null"} for t in @EVENTS@]
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
            if c == "override": h = ["Host", "X-A", "Accept", "X-Probe"]  # Chromium rebuilds the list on override, for every driver
            if arm == LEAK and c != "plain": h = ["host", "x-a", "accept"] + (["x-probe"] if c == "override" else [])  # reordered, lower-cased
            if arm == os.environ.get("FAKE_NOROUTE") and c != "plain": h = list(base)  # the handler never fired: an unrouted request
            req(h)
    else:
        req(base)
if driver:
    acts = {k: "ok:x" for k in ("focus", "type", "blur", "click", "select", "scroll")}
    for na in os.environ.get("FAKE_NA", "").split(","):
        if na.startswith(arm + ":"): acts[na.split(":")[1]] = "n/a: no API"
    json.dump({"driver": arm, "acts": acts, "error": None}, open(opt("--out"), "w"))
'''


@pytest.fixture
def env(tmp_path, monkeypatch):
    from driver_probes_rows import EVENTS, TARGET
    fake = tmp_path / "fake.py"
    fake.write_text(FAKE.replace("@EVENTS@", repr(list(EVENTS))).replace("@TARGET@", repr(TARGET)))
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


def test_h_rows_red_fails_clean_passes_and_chromium_rebuild_is_its_own_row(env):
    rc, t = env("--groups", "H", "--arms", "control,rod,red")
    for row, v in t["rows"].items():
        if row.endswith("chromium-rebuild"):
            assert v == {"control": "FAIL"}, row  # raw CDP override FAILs: that is Chromium, not a driver
            continue
        assert v["red"] == "FAIL" and v["rod"] == "PASS", row
    assert any("landing" in k for k in t["details"])
    assert rc == 0  # the raw-CDP FAIL is not a driver cell


def test_h_route_handler_that_never_fires_is_not_a_pass(env):
    import os
    os.environ["FAKE_NOROUTE"] = "rod"
    try:
        rc, t = env("--groups", "H", "--arms", "control,rod,red")
    finally:
        del os.environ["FAKE_NOROUTE"]
    assert t["rows"]["H.fetch.route.vs-plain"]["rod"] == "UNMEASURED"  # no X-Probe landed: interception unproved
    assert t["rows"]["H.xhr.override.vs-rawcdp"]["rod"] == "FAIL"  # override never landed


def test_l9_an_action_that_is_na_voids_its_rows_even_if_another_action_fires_the_event(env, monkeypatch):
    monkeypatch.setenv("FAKE_NA", "rod:focus")
    rc, t = env("--groups", "L9", "--arms", "control,rod,red")
    assert t["rows"]["L9.focus"]["rod"] == "UNMEASURED" and t["rows"]["L9.click"]["rod"] == "PASS"


def test_h_dead_control_when_red_is_clean(env):
    rc, t = env("--groups", "H", "--arms", "control,red", leak="nobody")
    cells = {c for k, v in t["rows"].items() if not k.endswith("chromium-rebuild") for c in v.values()}
    assert cells <= {"UNMEASURED", "n/a"}

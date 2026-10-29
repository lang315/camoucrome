#!/usr/bin/env python3
"""Dry run of observe_drive.py against a local page (no facebook): the driver's rows, each RED-able.

  D1  the POST of the page is captured: channels.json has the endpoint with field q[].name, at least 2 POSTs, and the
      resources dirs hold one script (both pages include the same app.js) and two documents
  D2  matches.json maps q[].dm to navigator.deviceMemory (weak) and q[].tz to timezone, with NO --truth-url, so the default
      truth page (served on 127.0.0.1, a secure context) is what is proven
  D3  the value canary is in capture/requests.jsonl (the capture saw it) and in no file that leaves the host
  D4  a checkpoint page under --expect-session exits 4 and prints CHECKPOINT
  D5  the wheel reached the page: the title the page counts wheel events into is greater than 0

  verify_observe_drive.py [--exe CHROME] [--red D1|D2|D4|D5] [--keep]
--red makes one row fail on purpose (D3 is made RED by hand: let value_class return the value). Needs patchright and the
camoucrome client in the interpreter (the box venv, or the observe venv on the host). Exit 0 and ALL_PASS, else 1.
"""
import argparse
import base64
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import observe_drive_testpage as page  # noqa: E402

CANARY = page.CANARY
HOSTS = ["--post-hosts", "127.0.0.1", "--resource-hosts", "127.0.0.1", "--doc-hosts", "127.0.0.1"]


def drive(exe, out, args, timeout=180):
    cmd = [sys.executable, str(HERE / "observe_drive.py"), "--arm", "dry", "--exe", exe, "--profile", str(out / "profile"),
           "--out", str(out / "arm"), "--headless", *args]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr, out / "arm"


def load(arm, name, default=None):
    try:
        return json.loads((arm / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def count(arm, sub):
    d = arm / "resources" / sub
    return len(list(d.iterdir())) if d.is_dir() else 0


def canary_in_capture(arm):
    for line in (arm / "capture" / "requests.jsonl").read_text(encoding="utf-8").splitlines() if (arm / "capture" / "requests.jsonl").exists() else []:
        try:
            if CANARY.encode() in base64.b64decode(json.loads(line)["body_b64"]):
                return True
        except (ValueError, KeyError):
            continue
    return False


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe")
    ap.add_argument("--red", choices=["D1", "D2", "D4", "D5"])
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args(argv)
    exe = a.exe
    if not exe:
        import lib_shell
        exe = str(lib_shell.CHROME)
    srv, port = page.serve(0)
    base = f"http://127.0.0.1:{port}"
    work = pathlib.Path(tempfile.mkdtemp(prefix="obsdrive-"))
    rows, notes = {}, []
    try:
        main_args = ["--url", base + "/", "--url", base + "/second", "--settle", "2", "--wheel", "5"]
        hosts = HOSTS
        if a.red == "D1":
            hosts = ["--post-hosts", "example.invalid", "--resource-hosts", "127.0.0.1", "--doc-hosts", "127.0.0.1"]
        if a.red == "D2":
            main_args.append("--no-truth")
        if a.red == "D5":
            main_args[main_args.index("--wheel") + 1] = "0"
        rc, out, err, arm = drive(exe, work / "main", [*main_args, *hosts])
        if rc != 0:
            notes.append(f"main run rc={rc}: {err.strip()[-200:]}")
        ch = load(arm, "channels.json", {})
        ep = ch.get("endpoints", {}).get(f"127.0.0.1:{port}/ajax/bz", {})
        rows["D1 the page's POST is captured, one script and two documents saved"] = (
            "q[].name" in ep.get("fields", {}) and ch.get("posts_captured", 0) >= 2
            and count(arm, "js") == 1 and count(arm, "html") == 2)
        m = load(arm, "matches.json", [])
        rows["D2 q[].dm -> navigator.deviceMemory (weak) and q[].tz -> timezone"] = (
            any(r["field"] == "q[].dm" and r["surface"] == "navigator.deviceMemory" and r["weak"] for r in m)
            and any(r["field"] == "q[].tz" and r["surface"] == "timezone" for r in m))
        leaked = [n for n in ("channels.json", "matches.json") if CANARY in (arm / n).read_text(encoding="utf-8")] \
            if (arm / "channels.json").exists() and (arm / "matches.json").exists() else ["missing output"]
        rows["D3 the canary is captured on the host and in no file that leaves"] = canary_in_capture(arm) and not leaked
        if leaked:
            notes.append(f"D3 files: {leaked}")
        titles = re.findall(r"TITLE=wheels=(\d+)", out)
        rows["D5 the wheel reached the page"] = bool(titles) and int(titles[-1]) > 0
        d4_args = ["--url", base + "/checkpoint/", "--settle", "1", "--wheel", "2", *HOSTS]
        if a.red != "D4":
            d4_args.append("--expect-session")
        rc4, out4, err4, _ = drive(exe, work / "d4", d4_args)
        rows["D4 a checkpoint page under --expect-session exits 4 with CHECKPOINT"] = rc4 == 4 and "CHECKPOINT" in out4
        if rc4 not in (0, 4):
            notes.append(f"D4 run rc={rc4}: {err4.strip()[-200:]}")
    finally:
        srv.shutdown()
        if not a.keep:
            shutil.rmtree(work, ignore_errors=True)
    for name in sorted(rows):
        print(f"{'PASS' if rows[name] else 'FAIL'}  {name}")
    for n in notes:
        print("  " + n)
    ok = all(rows.values()) and len(rows) == 5
    print(f"{sum(rows.values())} PASS {len(rows) - sum(rows.values())} FAIL")
    print("ALL_PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

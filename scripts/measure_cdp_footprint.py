#!/usr/bin/env python3
"""CDP footprint harness orchestrator: one fork binary, four arms (none, tdp, tdp-main, red), three row groups
(L local probe page, D public detectors, F facebook logged out). Runs on the Windows host in the owner's session
(session 1, via run-interactive.ps1). Writes <out>/table.json and <out>/table.md: verdicts, names and counts only.

  python measure_cdp_footprint.py --exe PATH --drivers DIR --out DIR [--groups L,D,F] [--arms none,tdp,tdp-main,red]
                                  [--l-timeout 90] [--keep-raw]

Exit 0: all measured, no FAIL. 1: any FAIL (the red control's FAIL is the expected one and does not count). 3: any UNMEASURED, no FAIL."""
import argparse
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "client" / "python"))
import cdp_footprint_rows as rows  # noqa: E402
import cdp_footprint_server  # noqa: E402
import observe_judge  # noqa: E402
import step2_rows  # noqa: E402

ARMS = ("none", "tdp", "tdp-main", "red")
SEED = 20261120
FACEBOOK = "https://www.facebook.com/"
FB_WAIT = 60            # seconds a none-arm facebook load stays open (the drivers wait 60 s themselves)
DETECTOR_TIMEOUT = 180  # bound on a driver's own exit, detector mode
FACEBOOK_TIMEOUT = 200  # same, facebook mode
STOP_WAIT = 45          # after stdin is closed
TRACE_CATS = "-*,disabled-by-default-camou.observe"
NA = "n/a"


def identity():
    from camoucrome import gen, launcher
    ident = gen.generate("windows", seed=SEED)
    # the drivers add the debugging transport and --user-data-dir themselves; the none arm has no reader for a pipe
    argv = [a for a in launcher.build_args(window=ident["launch"].get("window"), dpr=ident["launch"].get("dpr"), headless=False)
            if a != "--remote-debugging-pipe"] + ["--enable-logging", "--v=0"]
    return launcher.build_env(ident["config"]), argv


def gate():
    """None when a launch may start, else the reason it may not (observe-auto.ps1 Get-Gate, plus the proxy check)."""
    if os.name != "nt":
        return None

    def ps(cmd):
        return subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=60).stdout.strip()

    if not any(re.search(r"\sActive\s", ln) for ln in subprocess.run(["quser"], capture_output=True, text=True).stdout.splitlines()):
        return "no active session"
    if ps("(Get-Process ninja,siso -ErrorAction SilentlyContinue | Measure-Object).Count") not in ("", "0"):
        return "native build running"
    kib = int(ps("(Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory") or 0)
    if kib < 8 * 1024 * 1024:
        return f"low-memory {kib / 1048576:.1f} GB < 8 GB"
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as k:
        try:
            if winreg.QueryValueEx(k, "ProxyEnable")[0] != 0:
                return "proxy enabled"
        except FileNotFoundError:
            pass
    return None


def gpu_crashed(profile):
    log = pathlib.Path(profile) / "chrome_debug.log"
    return log.exists() and "GPU process exited unexpectedly" in log.read_text(encoding="utf-8", errors="replace")


def driver_cmd(drivers, arm):
    return [str(pathlib.Path(drivers) / ("reddrive.exe" if arm == "red" else "tdpdrive.exe"))]


def kill_tree(p):
    if p.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
    else:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def wait_until(pred, timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.5)
    return pred()


def launch_none(exe, argv, env, profile, url, wait_s, until=None):
    """The browser as a user opens it: no driver. After wait_s (or once until() holds) close the window gracefully."""
    p = subprocess.Popen([exe, *argv, "--user-data-dir=" + str(profile), url], env=env, start_new_session=os.name != "nt",
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if until:
            wait_until(until, wait_s)
        else:
            time.sleep(wait_s)
    finally:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(p.pid)], capture_output=True)
        else:
            p.terminate()
        try:
            p.wait(15)
        except subprocess.TimeoutExpired:
            kill_tree(p)
            p.wait()


def run_driver(cmd, wait):
    """stdin stays open (EOF stops a driver at once). wait(p) blocks until the arm is done; then stdin closes and the
    driver gets STOP_WAIT s to write --out and exit before its tree is killed."""
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=os.name != "nt")
    try:
        wait(p)
    finally:
        try:
            p.stdin.close()
        except OSError:
            pass
        try:
            p.wait(STOP_WAIT)
        except subprocess.TimeoutExpired:
            kill_tree(p)
            p.wait()


def exe_version(path):
    if os.name != "nt":
        return "unknown"
    p = subprocess.run(["powershell", "-NoProfile", "-Command", f"(Get-Item -LiteralPath '{path}').VersionInfo.ProductVersion"],
                       capture_output=True, text=True, timeout=60)
    return p.stdout.strip() or "unknown"


def arm_order(i, arms):
    return list(arms) if i % 2 == 0 else list(reversed(arms))


class Run:
    def __init__(self, a, env, argv):
        self.a, self.env, self.argv = a, env, argv
        self.raw = pathlib.Path(a.out) / "raw"
        self.n = 0
        self.notes = []
        (self.raw / "results").mkdir(parents=True, exist_ok=True)
        self.srv, self.port = cdp_footprint_server.serve(self.raw / "results")

    def rid(self, group, arm):
        self.n += 1
        return f"{group}-{arm}-{self.n}-{uuid.uuid4().hex[:8]}"

    def launch(self, group, arm, mode, url, wait_s, flags_for=None, until=None, driver_timeout=None):
        """One launch of one arm. Returns (run dir, driver --out path or None) or None when a gate stopped it."""
        try:
            reason = gate()
        except Exception as e:  # noqa: BLE001 - a gate that cannot be read is a gate that failed
            reason = f"gate error {type(e).__name__}"
        if reason:
            self.notes.append(f"{group} {arm}: {reason}")
            return None
        d = self.raw / self.rid(group, arm)
        profile, out = d / "profile", d / "driver.json"
        profile.mkdir(parents=True)
        argv = [*self.argv, *(flags_for(d) if flags_for else [])]
        if arm == "none":
            launch_none(self.a.exe, argv, self.env, profile, url, wait_s, until)
        else:
            (d / "args.json").write_text(json.dumps(argv))
            (d / "env.json").write_text(json.dumps(self.env))
            cmd = driver_cmd(self.a.drivers, arm) + ["--exe", self.a.exe, "--args-json", str(d / "args.json"), "--env-json", str(d / "env.json"),
                                                     "--profile", str(profile), "--mode", mode, "--url", url, "--out", str(out)]
            if arm == "tdp-main":
                cmd.append("--main-world")
            run_driver(cmd, (lambda p: wait_until(until, wait_s)) if until else (lambda p: wait_until(lambda: p.poll() is not None, driver_timeout)))
        if gpu_crashed(profile):
            self.notes.append(f"{group} {arm}: GPU process crashed")
            return None
        return d, out

    def driver_text(self, got):
        try:
            return json.loads(got[1].read_text(encoding="utf-8")).get("text")
        except (OSError, ValueError):
            return None

    def group_L(self, order):
        results = {}
        for arm in order:
            run = self.rid("L", arm)  # the probe's run id; a stale file can never satisfy /done
            done = lambda r=run, a=arm: _ok(f"http://127.0.0.1:{self.port}/done?arm={a}&run={r}")  # noqa: E731
            url = f"http://127.0.0.1:{self.port}/probe.html?arm={arm}&run={run}"
            got = self.launch("L", arm, "probe", url, self.a.l_timeout, until=done)
            f = self.raw / "results" / f"{arm}-{run}.json"
            # a result counts only if /done held in time: a late or partial file of a timed-out arm is not a measurement
            results[arm] = json.loads(f.read_text(encoding="utf-8")) if got and done() and f.exists() else None
        return {row: rows.judge_row(row, results) for row in rows.CLASS}

    def group_D(self, order):
        parsed = {}
        sites = {"rebrowser": ("https://bot-detector.rebrowser.net/", step2_rows.parse_rebrowser),  # measure_step2.DETECTORS
                 "dbi_bot": ("https://deviceandbrowserinfo.com/are_you_a_bot", step2_rows.parse_dbi),  # measure_step2.DETECTORS
                 "creepjs": (f"http://127.0.0.1:{self.port}/creepjs/index.html", step2_rows.parse_colon)}
        for arm in (x for x in order if x != "none"):
            for name, (url, parse) in sites.items():
                got = self.launch("D", arm, "detector", url, 0, driver_timeout=DETECTOR_TIMEOUT)
                text = self.driver_text(got) if got else None
                parsed[arm, name] = parse(text) if text else None
        return d_rows(parsed, [a for a in order if a != "none"])

    def group_F(self, order):
        sums = {}
        for arm in order:
            def flags(d):
                return [f"--trace-startup={TRACE_CATS}", "--trace-startup-format=json", f"--trace-startup-file={d / 'trace.json'}",
                        "--trace-startup-duration=0", "--trace-startup-record-mode=record-as-much-as-possible", f"--log-net-log={d / 'net.json'}"]
            got = self.launch("F", arm, "facebook", FACEBOOK, FB_WAIT, flags_for=flags, driver_timeout=FACEBOOK_TIMEOUT)
            try:
                s = observe_judge.summarize(got[0]) if got else None
            except observe_judge.MissingInput:
                s = None
            if got and not self.a.keep_raw:
                shutil.rmtree(got[0], ignore_errors=True)  # raw trace, netlog and profile are gone once judged
            sums[arm] = {"groups": s["groups"], "intl": s["intl"], "requests": s["requests"]["total"], "ajax_bz": s["requests"]["ajax_bz"]} if s else None
        v, details = {}, {}
        for arm in order:
            if sums.get(arm) is None or sums.get("none") is None:
                v[arm] = rows.UNMEASURED
                continue
            if arm == "none":
                v[arm] = rows.PASS
                continue
            lines = rows.judge_observer(sums["none"], sums[arm])
            details[arm] = lines
            v[arm] = rows.UNMEASURED if lines and lines[0].startswith("UNMEASURED") else (rows.FAIL if lines else rows.PASS)
        return {"F.observer": v}, details


def _ok(url):
    try:
        return urllib.request.urlopen(url, timeout=5).status == 200
    except (urllib.error.URLError, OSError):
        return False


def _flagged(value):
    m = re.match(r"\D*(\d+)", value or "")
    return None if not m else int(m.group(1)) > 0  # shortcut: CreepJS's lines read "<n>% ..." or "<n>"; a line with no leading number is unmeasured


def d_rows(parsed, driven):
    v = lambda ok: rows.UNMEASURED if ok is None else (rows.FAIL if ok else rows.PASS)  # noqa: E731
    table = {}
    for arm in driven:
        rb, dbi, cj = parsed.get((arm, "rebrowser")), parsed.get((arm, "dbi_bot")), parsed.get((arm, "creepjs"))
        for t, s in (rb or {}).items():
            table.setdefault(f"D.rebrowser.{t}", {})[arm] = v({"pass": False, "fail": True}.get(s))  # "not triggered" etc. is no pass
        for f, b in (dbi or {}).items():
            table.setdefault(f"D.dbi_bot.{f}", {})[arm] = v(b)
        for row, key in (("headless", "headless"), ("lies", "lies")):
            line = next((val for k, val in (cj or {}).items() if key in k.lower()), None)
            table.setdefault(f"D.creepjs.{row}", {})[arm] = v(_flagged(line))
    for r in table.values():
        for arm in driven:
            r.setdefault(arm, rows.UNMEASURED)
        r["none"] = NA
    if (parsed.get(("red", "rebrowser")) or {}).get("runtimeEnableLeak") != "fail":  # dead control: red must trip runtimeEnableLeak
        table = {r: {a: (NA if a == "none" else rows.UNMEASURED) for a in v_} for r, v_ in table.items()}
    return table


def exit_code(table):
    # Only the tdp and tdp-main verdicts count: red is a positive control whose FAILs are expected on every group
    # (a dead control already turns the tdp cells UNMEASURED), and none is the baseline.
    cells = [c for v in table.values() for a, c in v.items() if a in ("tdp", "tdp-main")]
    if rows.FAIL in cells:
        return 1
    return 3 if not table or rows.UNMEASURED in cells else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--exe", required=True)
    ap.add_argument("--drivers", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--groups", default="L,D,F")
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--l-timeout", type=float, default=90)
    ap.add_argument("--keep-raw", action="store_true")
    a = ap.parse_args(argv)
    arms = [x for x in ARMS if x in a.arms.split(",")]
    env, args = identity()
    r = Run(a, env, args)
    table, details, order = {}, {}, {}
    try:
        for i, g in enumerate(a.groups.split(",")):
            order[g] = arm_order(i, arms)
            if g == "L":
                table.update(r.group_L(order[g]))
            elif g == "D":
                order[g] = [x for x in order[g] if x != "none"]
                table.update(r.group_D(order[g]))
            elif g == "F":
                t, det = r.group_F(order[g])
                table.update(t)
                details.update({f"F.observer {k}": v for k, v in det.items()})
    finally:
        r.srv.shutdown()
        if not a.keep_raw:
            shutil.rmtree(r.raw, ignore_errors=True)
    out = pathlib.Path(a.out)
    (out / "table.json").write_text(json.dumps({"version": exe_version(a.exe), "rows": table, "order": order, "details": details,
                                                "notes": r.notes}, indent=1), encoding="utf-8")
    (out / "table.md").write_text(f"Fork build {exe_version(a.exe)}\n\n" + rows.render(table) + "\n", encoding="utf-8")
    return exit_code(table)


if __name__ == "__main__":
    sys.exit(main())

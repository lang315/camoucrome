#!/usr/bin/env python3
"""Driver probes: L9 (stacks a page reads during driver actions) and H (header order and case of routed requests).
One browser binary, local pages only, a fresh temp profile per launch, only the processes this script started are killed.
The control of L9 is `control`: raw CDP input and DOM.focus (no eval, no Runtime.enable), because a CDP-free OS input
path is not available on every box; H also has `none` (no driver at all). `red` is the positive control of both groups:
a row where it does not FAIL is UNMEASURED for every arm.

  python measure_driver_probes.py --exe PATH --drivers DIR --out DIR [--groups L9,H] [--arms control,tdp,...]
                                  [--timeout 120] [--keep-raw]
DIR holds the built tdpdrive, reddrive, roddrive; patchright arm runs cdp_footprint/pwdrive.py under this interpreter.
Writes <out>/table.json (verdicts, details with the offending frame classes) and <out>/table.md.
Exit 0: no FAIL among the measured drivers; 1: a FAIL; 3: an UNMEASURED and no FAIL."""
import argparse
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.parse
import uuid

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import driver_probes_rows as rows  # noqa: E402
import raw_http_server  # noqa: E402
from cdp_footprint_rows import FAIL, PASS, UNMEASURED  # noqa: E402

ARMS = ("control", "tdp", "tdp-main", "patchright", "rod", "red")
H_ARMS = ("none", "control", "tdp", "patchright", "rod", "red")  # tdp-main only changes the eval world: no header difference
DRIVERS = ("tdp", "tdp-main", "patchright", "rod")  # red is the positive control: its FAILs are expected and never counted
BROWSER_ARGS = ["--no-first-run", "--no-default-browser-check"]


def driver_cmd(drivers, arm):
    d = pathlib.Path(drivers)
    if arm == "patchright":
        return [sys.executable, str(HERE / "cdp_footprint" / "pwdrive.py")]
    return {"control": [str(d / "reddrive"), "--native"], "red": [str(d / "reddrive")], "tdp": [str(d / "tdpdrive")],
            "tdp-main": [str(d / "tdpdrive"), "--main-world"], "rod": [str(d / "roddrive")]}[arm]


def kill_group(p):
    """End the process group this script started (browser helpers included). Never a name match."""
    if p.poll() is None:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        p.wait()


def run_proc(cmd, timeout, env=None, until=None):
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, env=env)
    try:
        end = time.monotonic() + timeout
        while time.monotonic() < end and p.poll() is None and not (until and until()):
            time.sleep(0.3)
    finally:
        kill_group(p)


class Run:
    def __init__(self, a):
        self.a = a
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="driverprobes-"))
        (self.tmp / "results").mkdir()
        self.sock, self.port, self.log = raw_http_server.serve(self.tmp / "results")
        self.base = f"http://127.0.0.1:{self.port}"
        self.notes = []
        self.acts = {}

    def profile(self, tag):
        d = self.tmp / f"{tag}-{uuid.uuid4().hex[:6]}"
        d.mkdir()
        return d

    def launch(self, group, arm, url, mode):
        """One launch: a driver (or, for H's none arm, the bare browser). Returns the driver's result dict or None."""
        d = self.profile(f"{group}-{arm}")
        out = d / "driver.json"
        if arm == "none":
            cmd = [self.a.exe, *BROWSER_ARGS, "--user-data-dir=" + str(d / "profile"), url]
            run_proc(cmd, 8)
            return {"driver": "none", "acts": {}, "error": None}
        (d / "args.json").write_text(json.dumps(BROWSER_ARGS))
        cmd = driver_cmd(self.a.drivers, arm) + ["--exe", self.a.exe, "--args-json", str(d / "args.json"), "--profile", str(d / "profile"),
                                                 "--mode", mode, "--url", url, "--out", str(out)]
        run_proc(cmd, self.a.timeout)  # the driver closes its browser and writes --out last, then exits
        try:
            return json.loads(out.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.notes.append(f"{group} {arm}: driver wrote no result")
            return None

    def group_L9(self, arms):
        results = {}
        for arm in arms:
            run = uuid.uuid4().hex[:8]
            got = self.launch("L9", arm, f"{self.base}/l9.html?arm={arm.replace('-', '_')}&run={run}", "l9")
            f = self.tmp / "results" / f"{arm.replace('-', '_')}-{run}.json"
            ok = got is not None and got.get("error") is None and f.exists()
            if got:
                self.acts[f"L9 {arm}"] = got.get("acts") or {}
                if got.get("error"):
                    self.notes.append(f"L9 {arm}: driver error {got['error'][:80]}")
            by = {}
            for fire in (json.loads(f.read_text(encoding="utf-8")) if ok else []):
                by.setdefault(fire["type"], []).append(fire)
            results[arm] = by if ok else None
        table, details = {}, {}
        for ev in rows.EVENTS:
            table[f"L9.{ev}"] = {"control": rows.NA_CELL, **rows.judge_stack_row(ev, results, self.acts_by_arm(arms))}
            for a in arms:
                if a != "control" and results.get(a) and results.get("control"):
                    ex = rows.extras(results["control"].get(ev) or [{"stack": "", "script": None}], results[a].get(ev) or [])
                    if ex:
                        details[f"L9.{ev} {a}"] = ex
        for a in arms:
            if results.get(a) is not None:
                details[f"L9 fires {a}"] = {ev: len(v) for ev, v in sorted(results[a].items())}
        return table, details

    def acts_by_arm(self, arms):
        return {a: self.acts.get(f"L9 {a}") or {} for a in arms}

    def samples(self, start):
        """(cond, kind) -> list of header-name lists, from the raw log entries after index start."""
        out = {}
        for target, raw in self.log[start:]:
            u = urllib.parse.urlparse(target)
            if u.path != "/hdr":
                continue
            q = urllib.parse.parse_qs(u.query)
            out.setdefault((q["c"][0], q["k"][0]), []).append(rows.parse_request(raw)[1])
        return out

    def group_H(self, arms):
        per, details = {}, {}
        for arm in arms:
            start = len(self.log)
            if arm == "none":
                self.launch("H", arm, f"{self.base}/h.html?c=none", "headers")
            else:
                got = self.launch("H", arm, f"{self.base}/h.html?c=boot", "headers")
                if got:
                    self.acts[f"H {arm}"] = got.get("acts") or {}
            per[arm] = self.samples(start)
            for (cond, kind), v in per[arm].items():
                details[f"H.sample {arm} {cond} {kind}"] = ",".join(v[0])
        table = {}
        for kind in ("fetch", "xhr"):
            def have(arm, cond):
                return per.get(arm, {}).get((cond, kind))

            def proved(arm):  # interception ran for this arm and kind: its own override landed X-Probe on every request
                got = have(arm, "override")
                return bool(got) and all(rows.landing(s, "X-Probe") is not None for s in got)

            def put(row, cells):
                if cells.get("red") != FAIL:  # the dead-control rule: red must FAIL the row itself
                    cells = {a: (rows.NA_CELL if cells[a] == rows.NA_CELL else UNMEASURED) for a in cells}
                table[row] = cells

            for vs in ("plain", "none"):  # route unchanged: only meaningful where interception is proved to have run
                cells = {}
                for arm in arms:
                    got = have(arm, "route")
                    if arm == "none" or (vs == "plain" and arm == "tdp"):  # tdp's plain is already routed: only vs-none says anything
                        cells[arm] = rows.NA_CELL
                    elif not got or not proved(arm):
                        cells[arm] = UNMEASURED
                    else:
                        base = have("none" if vs == "none" else arm, "none" if vs == "none" else "plain")
                        cells[arm], why = rows.judge_headers(base, got)
                        if why:
                            details[f"H.{kind}.route.vs-{vs} {arm}"] = why
                put(f"H.{kind}.route.vs-{vs}", cells)
            # override: Chromium itself rebuilds the list, so drivers are judged against raw CDP's override, not against plain
            cells = {}
            for arm in arms:
                got = have(arm, "override")
                if arm in ("none", "control"):
                    cells[arm] = rows.NA_CELL
                elif not got:
                    cells[arm] = UNMEASURED
                else:
                    cells[arm], why = rows.judge_headers(have("control", "override"), got, required="X-Probe")
                    if why:
                        details[f"H.{kind}.override.vs-rawcdp {arm}"] = why
                    if (i := rows.landing(got[0], "X-Probe")) is not None:
                        details[f"H.{kind}.override.vs-rawcdp {arm} landing"] = f"X-Probe at {i} of {len(got[0])}"
            put(f"H.{kind}.override.vs-rawcdp", cells)
            # information, no driver verdict: what Chromium does to the list when raw CDP overrides headers
            base, got = have("none", "none"), have("control", "override")
            if base and got:
                v, why = rows.judge_headers(base, got, added="X-Probe")
                table[f"H.{kind}.override.chromium-rebuild"] = {"control": v}
                details[f"H.{kind}.override.chromium-rebuild"] = why
        return table, details


def exit_code(table):
    cells = [c for v in table.values() for a, c in v.items() if a in DRIVERS]
    if FAIL in cells:
        return 1
    return 3 if not cells or UNMEASURED in cells else 0


def render(table, arms):
    lines = ["| row | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
    lines += [f"| {r} | " + " | ".join(v.get(a, "") for a in arms) + " |" for r, v in table.items()]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--exe", required=True)
    ap.add_argument("--drivers", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--groups", default="L9,H")
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--timeout", type=float, default=120)
    a = ap.parse_args(argv)
    want = a.arms.split(",")
    r = Run(a)
    table, details = {}, {}
    try:
        for g in a.groups.split(","):
            if g == "L9":
                t, d = r.group_L9([x for x in ARMS if x in want])
            elif g == "H":
                t, d = r.group_H([x for x in H_ARMS if x in want or x == "none"])
            else:
                raise SystemExit(f"unknown group {g}")
            table.update(t)
            details.update(d)
    finally:
        r.sock.close()
        shutil.rmtree(r.tmp, ignore_errors=True)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "table.json").write_text(json.dumps({"rows": table, "details": details, "acts": r.acts, "notes": r.notes}, indent=1), encoding="utf-8")
    shown = [x for x in ("none", *ARMS) if any(x in v for v in table.values())]
    (out / "table.md").write_text(render(table, shown) + "\n\n" + "\n".join("note: " + n for n in r.notes) + "\n", encoding="utf-8")
    return exit_code(table)


def entry(argv=None):
    try:
        return main(argv)
    except Exception as e:  # noqa: BLE001 - a crash is UNMEASURED; type and message only
        print(f"UNMEASURED: {type(e).__name__}: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(entry())

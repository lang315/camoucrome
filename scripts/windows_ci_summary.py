"""The verdict and summary of one on-demand Windows CI run (spec 2026-10-28 §2.5).

The host driver (scripts/windows/windows-ci.ps1) gathers a run record as JSON; this module
decides the verdict and writes summary.md, so the logic is tested on the Mac.

Precedence, first match wins:
  1. SKIPPED (exit 0, no work done): lock held (never overridden by forced); observe in use
     without forced; nothing changed since the tested commit without forced; session not
     Active; commit headroom below 8 GB; a native build running.
  2. FAIL (exit 1): build exit non-zero, timed out, or 0 steps; a green row failed or fewer
     rows than expected; a known-failure row that passed; a red entry with red_seen false.
  3. UNMEASURED (exit 2): the build's exit code was not read (null); gpu_crashes > 0; not_measured beyond allowed_not_measured; headroom
     or session lost mid-run.
  4. PASS (exit 0).
FAIL outranks UNMEASURED: a run that proved a break is not hidden by a GPU crash elsewhere.
forced (a reason string) lifts the observe and nothing-changed skips and prints `FORCED: <reason>`.

  python windows_ci_summary.py --record record.json --out summary.md   prints the RESULT line
"""
import argparse
import datetime
import json
import sys

MIN_HEADROOM_GB = 8
EXIT = {"PASS": 0, "FAIL": 1, "UNMEASURED": 2, "SKIPPED": 0}


def run_id(now_utc):
    """YYYYMMDDTHHMMSSZ of an aware UTC datetime; anything else is a bug upstream."""
    if now_utc.tzinfo is None or now_utc.utcoffset() != datetime.timedelta(0):
        raise ValueError("run_id needs an aware UTC datetime")
    return now_utc.strftime("%Y%m%dT%H%M%SZ")


def _parse_utc(s):
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


def _skip(r):
    forced = r.get("forced")
    pre = r["preconditions"]
    if str(r["lock"]).startswith("held"):
        return "lock held: " + str(r["lock"])[len("held:"):]
    if r.get("observe_in_use") and not forced:
        return "observe in use: " + r["observe_in_use"]
    if r["commit"] == r["tested_commit"] and not forced:
        return "nothing changed"
    if not pre["session_active"]:
        return "session not Active"
    if pre["commit_headroom_gb"] < MIN_HEADROOM_GB:
        return f"commit headroom {pre['commit_headroom_gb']} GB below {MIN_HEADROOM_GB} GB"
    if pre["native_build_running"]:
        return "native build running"
    return None


def _fails(r):
    out = []
    b = r["build"]
    if b["timed_out"]:
        out.append("build timed out")
    elif b["exit"] is not None and b["exit"] != 0:
        out.append(f"build exit {b['exit']}")
    elif b["steps"] == 0:
        out.append("build reported 0 steps")
    for e in r["verify"]["red"]:
        if not e["red_seen"]:
            out.append(f"red did not go red: {e['script']}")
    for e in r["verify"]["green"]:
        if e["fails"]:
            out.append(f"{e['script']}: {e['fails']} row(s) failed")
        if e["rows"] < e["expected"]:
            out.append(f"{e['script']}: {e['rows']} rows, expected {e['expected']}")
        if e.get("known_fail_passed"):
            out.append(f"{e['script']}: known failure passed")
    return out


def _unmeasured(r):
    out = []
    if r["build"]["exit"] is None:
        out.append("build exit code not read (driver could not read the process exit code)")
    for e in r["verify"]["green"]:
        if e["gpu_crashes"] > 0:
            out.append(f"{e['script']}: gpu crash count {e['gpu_crashes']}")
        if e["not_measured"] > e.get("allowed_not_measured", 0):
            out.append(f"{e['script']}: {e['not_measured']} NOT MEASURED")
    if r.get("headroom_lost"):
        out.append("commit headroom lost mid-run")
    if r.get("session_lost"):
        out.append("session not Active mid-run")
    return out


def _classify(r):
    s = _skip(r)
    if s:
        return "SKIPPED", [s]
    f = _fails(r)
    if f:
        return "FAIL", f
    u = _unmeasured(r)
    if u:
        return "UNMEASURED", u
    return "PASS", []


def verdict(r):
    name = _classify(r)[0]
    return name, EXIT[name]


def reason(r):
    """The first reason behind the verdict, empty for PASS."""
    return "; ".join(_classify(r)[1])


def render_summary(r):
    name, reasons = _classify(r)
    rid = run_id(_parse_utc(r["started_utc"]))
    b = r["build"]
    L = [f"RESULT {name} {rid}", ""]
    if r.get("forced"):
        L.append(f"FORCED: {r['forced']}")
    L += [f"- verdict: {name}" + (" (" + "; ".join(reasons) + ")" if reasons else ""),
          f"- commit: {r['commit'][:7]} (last tested {str(r['tested_commit'])[:7]})",
          f"- started: {r['started_utc']}",
          f"- ended: {r['ended_utc']}"]
    if name != "SKIPPED":
        L.append(f"- build: {b['steps']} steps, {b['seconds']} s, exit {b['exit']}")
        for e in r["verify"]["red"]:
            L.append(f"- red {e['script']}: {e['rows']} rows, " + ("red seen" if e["red_seen"] else "red did not go red"))
        for e in r["verify"]["green"]:
            L.append(f"- green {e['script']}: {e['rows']}/{e['expected']} rows, {e['fails']} fail, "
                     f"{e['not_measured']} not measured, gpu crashes {e['gpu_crashes']}")
    prev = r.get("previous_stock_version")
    sv = r["stock_version"]
    L.append(f"- stock Chrome: {prev} -> {sv}" if prev and prev != sv else f"- stock Chrome: {sv}")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--record", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    with open(a.record, encoding="utf-8") as f:
        r = json.load(f)
    s = render_summary(r)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(s)
    print(s.splitlines()[0])
    return verdict(r)[1]


if __name__ == "__main__":
    sys.exit(main())

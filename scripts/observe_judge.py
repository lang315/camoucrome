"""Summarise and judge an unattended observer recon arm (names and counts only).

  python observe_judge.py summary ARM_DIR
  python observe_judge.py baseline --arm N DIR [--arm N DIR ...] -o FILE
  python observe_judge.py judge --baseline FILE --arm N DIR [--summary-out FILE]

judge exits 0 PASS, 1 FAIL, 3 UNMEASURED; 2 is a usage error.
"""
import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import observe_report as r  # noqa: E402

SITE = "https://facebook.com"
LOGGED_IN = ("c_user", "xs")
SLACK_S = 5


class MissingInput(Exception):
    pass


def _json(path):
    with open(path, encoding="utf-8-sig") as f:  # PowerShell may write a BOM
        return json.load(f)


def coverage(data, net):
    evs = [e for e in r.all_events(data) if e.get("ph") != "M" and e.get("ts", 0) > 0]
    trace_s = (max(e["ts"] for e in evs) - min(e["ts"] for e in evs)) / 1e6 if evs else 0.0
    times = [int(e["time"]) for e in net.get("events", []) if "time" in e]
    net_s = (max(times) - min(times)) / 1e3 if times else 0.0
    meta = data.get("metadata", {}) if isinstance(data, dict) else {}
    bufs = r._find(meta, "traced_buf")
    discarded = sum(b.get("chunks_discarded", 0) for b in bufs) if bufs else None
    return {"trace_s": round(trace_s, 1), "net_s": round(net_s, 1), "discarded": discarded}


def summarize(arm_dir):
    d = pathlib.Path(arm_dir)
    try:
        data = _json(d / "trace.json")
    except (OSError, ValueError) as e:
        raise MissingInput(f"no trace ({type(e).__name__})")
    try:
        net = _json(d / "net.json")
    except (OSError, ValueError) as e:
        raise MissingInput(f"no netlog ({type(e).__name__})")
    members = collections.Counter()
    for per_script in r.surface_counts(r.events_of(data)).get(SITE, {}).values():
        members.update(per_script)
    groups = collections.Counter()
    for api, n in members.items():
        groups[r.group_of(api)] += n
    intl = r.intl_counts(r.all_events(data))
    if intl is not None:
        per = collections.Counter()
        for (site, _script, builtin), n in intl.items():
            if site == SITE:
                per[builtin] += n
        intl = dict(per)
        if intl:
            groups["intl"] = sum(intl.values())
    # shortcut: the netlog is parsed twice (arm 3's is ~110 MB, a few seconds); pass the parsed dict if runs get slow
    reqs = r.load_requests(d / "net.json")
    db, prev = d / "cookies.db", d / "summary.json"
    if db.exists():
        cookies = sorted(f"{h}:{n}" for h, n, *_ in r.load_cookie_names(db))
    elif prev.exists():  # observe-auto deletes cookies.db after its judge wrote the names here
        cookies = _json(prev).get("cookies", [])
    else:
        cookies = []
    run = _json(d / "run.json") if (d / "run.json").exists() else None
    return {"groups": dict(groups), "members": dict(members), "intl": intl, "cookies": cookies,
            "requests": {"total": len(reqs), "ajax_bz": sum("/ajax/bz" in p for _s, _h, p, _m in reqs)},
            "coverage": coverage(data, net), "run": run}


EXIT = {"PASS": 0, "FAIL": 1, "UNMEASURED": 3}
EXPIRED = ("session expired: log in with recon.ps1 -Site facebook -Arm 2 -Intl "
           "and refresh the backup")


def unmeasured(s, arm):
    run = s["run"]
    if run is None:
        return ["run.json missing"]
    why = []
    if run.get("session") != 1:
        why.append(f"session={run.get('session')}")
    if run.get("session_state") != "Active":
        why.append(f"session_state={run.get('session_state')}")
    if run.get("report_rc") != 0:
        why.append(f"report_rc={run.get('report_rc')}")
    if run.get("left"):
        why.append(f"left={run.get('left')}")
    if run.get("low_memory_kill"):
        why.append("low-memory")
    if run.get("gpu_exit_lines"):
        why.append(f"gpu-crash lines={run.get('gpu_exit_lines')}")
    c = s["coverage"]
    if c["discarded"] is None:
        why.append("buffer stats missing")
    elif c["discarded"]:
        why.append(f"buffer full ({c['discarded']} chunks discarded)")
    if c["trace_s"] < c["net_s"] - SLACK_S:
        why.append(f"trace short ({c['trace_s']} s of {c['net_s']} s)")
    if s["intl"] is None:
        why.append("intl blind")
    if arm == 3 and not all(f".facebook.com:{n}" in s["cookies"] for n in LOGGED_IN):
        why.append(EXPIRED)
    return why


def make_baseline(by_arm):
    out = {}
    for arm, sums in by_arm.items():
        seen = [{g for g, n in s["groups"].items() if n > 0} for s in sums]
        out[str(arm)] = {"required": sorted(set.intersection(*seen)) if seen else [],
                         "runs": [{k: s.get(k) for k in ("groups", "intl", "requests")} for s in sums]}
    return out


def judge(arm_dir, arm, base, summary_out=None):
    try:
        s = summarize(arm_dir)
    except MissingInput as e:
        return "UNMEASURED", [("UNMEASURED", str(e))]
    if summary_out:
        pathlib.Path(summary_out).write_text(json.dumps(s, indent=1, sort_keys=True))
    ref = base.get(str(arm), {})
    req, runs = ref.get("required", []), ref.get("runs", [])
    rows = [("UNMEASURED", w) for w in unmeasured(s, arm)]
    if not req:
        rows.append(("INFO", "baseline requires 0 groups: PASS means measured only"))
    for g in req:
        n = s["groups"].get(g, 0)
        rows.append(("PASS" if n > 0 else "FAIL", f"{g} {n}"))
    for g in req:
        rows.append(("INFO", f"{g} {s['groups'].get(g, 0)} vs baseline "
                             f"{[x.get('groups', {}).get(g, 0) for x in runs]}"))
    for g in sorted(set(s["groups"]) - set(req)):
        rows.append(("INFO", f"new group {g} {s['groups'][g]}"))
    known = set().union(*[set((x.get("intl") or {})) for x in runs]) if runs else set()
    for b in sorted(set(s["intl"] or {}) - known):
        rows.append(("INFO", f"new intl builtin {b} {s['intl'][b]}"))
    rows.append(("INFO", f"requests {s['requests']['total']} ajax_bz {s['requests']['ajax_bz']}"))
    levels = {lvl for lvl, _ in rows}
    v = "UNMEASURED" if "UNMEASURED" in levels else "FAIL" if "FAIL" in levels else "PASS"
    return v, rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("summary")
    p.add_argument("arm_dir")
    p = sub.add_parser("baseline")
    p.add_argument("--arm", nargs=2, action="append", metavar=("N", "DIR"), required=True)
    p.add_argument("-o", required=True)
    p = sub.add_parser("judge")
    p.add_argument("--baseline", required=True)
    p.add_argument("--arm", nargs=2, metavar=("N", "DIR"), required=True)
    p.add_argument("--summary-out")
    a = ap.parse_args(argv)
    if a.cmd == "summary":
        print(json.dumps(summarize(a.arm_dir), indent=1, sort_keys=True))
        return 0
    if a.cmd == "baseline":
        by_arm = collections.defaultdict(list)
        for n, d in a.arm:
            # an unmeasured run would silently drop groups from the required set
            try:
                s = summarize(d)
                why = unmeasured(s, int(n))
            except MissingInput as e:
                why = [str(e)]
            if why:
                print(f"usage error: {d} is unmeasured: {'; '.join(why)}", file=sys.stderr)
                return 2
            by_arm[int(n)].append(s)
        pathlib.Path(a.o).write_text(json.dumps(make_baseline(by_arm), indent=1, sort_keys=True))
        return 0
    arm = int(a.arm[0])
    try:
        base = _json(a.baseline)
    except (OSError, ValueError) as e:
        print(f"usage error: baseline {a.baseline}: {e}", file=sys.stderr)
        return 2
    # a calibrated baseline without this arm would pass it on zero groups; {} is calibration
    if not isinstance(base, dict) or (base and str(arm) not in base):
        print(f"usage error: baseline {a.baseline} has no entry for arm {arm}", file=sys.stderr)
        return 2
    try:
        v, rows = judge(a.arm[1], arm, base, a.summary_out)
    except Exception as e:  # a crash measured nothing, and exit 1 would read as FAIL
        v, rows = "UNMEASURED", [("UNMEASURED", f"judge error ({type(e).__name__})")]
    for level, text in rows:
        print(f"{level} arm{arm} {text}")
    print(f"arm{arm} {v}")
    return EXIT[v]


if __name__ == "__main__":
    sys.exit(main())

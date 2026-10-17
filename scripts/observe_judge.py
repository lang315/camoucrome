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
    db = d / "cookies.db"
    cookies = sorted(f"{h}:{n}" for h, n, *_ in r.load_cookie_names(db)) if db.exists() else []
    run = _json(d / "run.json") if (d / "run.json").exists() else None
    return {"groups": dict(groups), "members": dict(members), "intl": intl, "cookies": cookies,
            "requests": {"total": len(reqs), "ajax_bz": sum("/ajax/bz" in p for _s, _h, p, _m in reqs)},
            "coverage": coverage(data, net), "run": run}

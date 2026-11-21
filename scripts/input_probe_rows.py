"""Judge of the input probes (plan 2026-11-21-input-probes.md, rows I1-I6). Pure: a snapshot of page.html's log in,
metrics and verdicts out. A driven arm FAILs a row when it is distinguishable from the control (stock Chrome under OS
input) beyond the control's own run-to-run spread."""
import statistics

EDGE_MS = 2.5          # camoufox #978: "within 2.5 ms of a rAF callback"
DPR_EPS = 2e-3         # float32 clientX: a pointer on device pixels shows its grid up to ~1e-4 device px


def _med(v):
    return statistics.median(v) if v else None


def evs(log, *types, trusted=True):
    return [e for e in log["ev"] if e["t"] in types and (e["tr"] or not trusted)]


def frame_ms(log):
    r = [a for a, _ in log["raf"]]
    d = [b - a for a, b in zip(r, r[1:]) if b > a]
    return _med(d)


def i1(log):
    """Moves against rAF ticks. Chrome dispatches input at frame start, so a real pointer gives at most one mousemove
    per frame (`multi`: share of frames with more), the dispatch ends just before the rAF callback (`aligned`: share of
    moves whose dispatch lies within EDGE_MS before the next tick) and the gaps are whole frames or more."""
    mv = evs(log, "mousemove")
    ticks = [n for _, n in log["raf"]]
    f = frame_ms(log)
    if not mv or not f or len(ticks) < 10:
        return None
    per, lead = {}, []
    for e in mv:
        nxt = next((t for t in ticks if t >= e["now"]), None)
        if nxt is None:
            continue
        per[nxt] = per.get(nxt, 0) + 1
        lead.append(nxt - e["now"])
    gaps = [b["ts"] - a["ts"] for a, b in zip(mv, mv[1:])]
    return {"moves": len(mv), "frame_ms": f,
            "multi": sum(1 for c in per.values() if c > 1) / len(per) if per else None,
            "aligned": sum(1 for x in lead if x <= EDGE_MS) / len(lead) if lead else None,
            "gap_med": _med(gaps), "gap_min": min(gaps) if gaps else None,
            "short": sum(1 for g in gaps if g < f * 0.5) / len(gaps) if gaps else None}


def i2(log):
    """getCoalescedEvents().length and getPredictedEvents().length per pointermove."""
    pm = [e for e in evs(log, "pointermove") if e["cs"] >= 0]
    if not pm:
        return None
    c = [e["cs"] for e in pm]
    return {"moves": len(pm), "coalesced_med": _med(c), "coalesced_max": max(c),
            "multi": sum(1 for x in c if x > 1) / len(c),
            "predicted": sum(1 for e in pm if e["ps"] > 0) / len(pm)}


def i3(log):
    """The device-pixel grid, from pointermove (a MouseEvent's clientX is whole CSS px; a PointerEvent's is not). A pointer
    on whole device pixels has clientX*dpr integral up to the viewport's fixed offset, so each axis shows ONE fractional
    part. `off_share`: the share of values off their axis's modal fractional part (circular, tolerance DPR_EPS)."""
    dpr = log["meta"]["dpr"]
    mv = [e for e in evs(log, "pointermove") if e["x"] is not None]
    if not mv:
        return None
    off = []
    for k in ("x", "y"):
        fr = [(e[k] * dpr) % 1.0 for e in mv]
        mode = statistics.mode(round(f, 3) for f in fr)
        off += [min(abs(f - mode), 1 - abs(f - mode)) > DPR_EPS for f in fr]
    return {"moves": len(mv), "dpr": dpr, "off_share": sum(off) / len(off)}


def _runs(log, kinds):
    return [e for e in log["ev"] if e["t"] in kinds]


EXIT = ("pointerout", "pointerleave", "mouseout", "mouseleave")
ENTER = ("pointerover", "pointerenter", "mouseover", "mouseenter")


def i4(log):
    """Leaving the viewport. `outside`: moves and overs carrying coordinates outside the viewport; `exit_depth`: px an out event's position lies past the edge; `exit`: the types fired from
    the last in-viewport move to the end of the exit; `exit_rt`: relatedTarget of the mouseout (null for a real exit)."""
    m = log["meta"]
    iw, ih = m["iw"], m["ih"]
    ev = [e for e in log["ev"] if e["tr"] and e["x"] is not None]
    if not ev:
        return None
    pointer = [e for e in ev if e["t"] in ("pointermove", "mousemove", "pointerover", "mouseover")]
    outside = [e for e in pointer if not (0 <= e["x"] < iw and 0 <= e["y"] < ih)]
    # an out event carries the exit position, a few px past the edge for a real pointer: how far is what a driver gets wrong
    depth = [max(-e["x"], e["x"] - iw + 1, -e["y"], e["y"] - ih + 1, 0) for e in ev if e["t"] in ("pointerout", "mouseout")]
    exits = [i for i, e in enumerate(log["ev"]) if e["t"] == "mouseleave" and e["tr"]]
    sigs = []
    for i in exits:
        j = i
        while j > 0 and log["ev"][j - 1]["t"] in EXIT:
            j -= 1
        sigs.append(",".join(e["t"] for e in log["ev"][j:i + 1]))
    outs = [e for e in log["ev"] if e["t"] == "mouseout" and e["tr"]]
    return {"exits": len(exits), "exit_sig": sorted(set(sigs)), "outside": len(outside), "exit_depth": max(depth) if depth else None,
            "exit_rt": sorted({e["rt"] for e in outs}),
            "reenter": sorted({e["t"] for e in log["ev"] if e["t"] in ENTER and e["tr"]})}


def i5(log):
    """Button sequences per gesture: the types in order from each mousedown to the next gesture's start, the `detail`
    of every click, the number of dblclick."""
    seq = [e for e in log["ev"] if e["tr"] and e["t"] in ("mousedown", "mouseup", "click", "dblclick", "contextmenu")]
    right = ",".join(f"{e['t']}" for e in seq if e["t"] in ("mousedown", "mouseup", "contextmenu") and (e["t"] == "contextmenu" or e["b"] == 2))
    left = [e for e in seq if e["t"] in ("mousedown", "mouseup", "click", "dblclick") and e["b"] == 0]
    return {"right": right, "click_detail": [e["d"] for e in left if e["t"] == "click"],
            "dblclick": sum(1 for e in left if e["t"] == "dblclick"), "contextmenu": sum(1 for e in seq if e["t"] == "contextmenu")}


def i6(log):
    """A held key: first-repeat delay and repeat interval from keydown timeStamps, and the repeat flags."""
    kd = evs(log, "keydown")
    if len(kd) < 3:
        return None
    t0 = kd[0]["ts"]
    rep = [e for e in kd[1:] if e["rep"]]
    gaps = [b["ts"] - a["ts"] for a, b in zip(kd[1:], kd[2:])]
    return {"downs": len(kd), "first_rep": kd[0]["rep"], "repeats": len(rep), "flags_ok": len(rep) == len(kd) - 1,
            "delay": (rep[0]["ts"] - t0) if rep else None, "interval_med": _med(gaps),
            "interval_sd": statistics.pstdev(gaps) if len(gaps) > 1 else None}


ROWS = {"I1": i1, "I2": i2, "I3": i3, "I4": i4, "I5": i5, "I6": i6}
MIN_N = 4               # runs per group (each control rate, and the arm) a verdict needs
WIDEN = 0.25            # a numeric verdict widens the control's range by this fraction of it (never less than the floor)
EXPECT_DPR = 1.25       # the probes run at this device scale factor; I3 means nothing at 1
# metric -> (kind, floor). num: the arm's median must lie in the control's range widened by max(floor, WIDEN * range);
# share: the same for a 0..1 share, UNMEASURED when the control's own range is 0.5 or more (it could never FAIL);
# zero: control and arm both 0; eq: every arm value is one of the control's; info: reported, never judged.
SPEC = {
    "I1": {"multi": ("share", 0.05), "aligned": ("share", 0.10), "short": ("share", 0.10), "gap_med": ("num", 2.0)},
    "I2": {"multi": ("share", 0.10), "coalesced_max": ("num", 1.0), "predicted": ("share", 0.10)},
    "I3": {"off_share": ("share", 0.05)},
    "I4": {"exit_sig": ("eq", 0), "outside": ("zero", 0), "exit_depth": ("num", 6.0), "exit_rt": ("eq", 0), "reenter": ("eq", 0)},
    "I5": {"right": ("eq", 0), "click_detail": ("eq", 0), "dblclick": ("eq", 0), "contextmenu": ("eq", 0)},
    # The key timing is authored by the harness in every arm (the control from the host's keyboard settings, the driven arms
    # from a fixed 500/33 ms), so it says nothing about Chrome: reported as info. Only what Chrome makes is judged.
    "I6": {"flags_ok": ("eq", 0), "first_rep": ("eq", 0), "delay": ("info", 0), "interval_med": ("info", 0), "interval_sd": ("info", 0)},
}


def metric_verdict(kind, floor, ctl, arm, min_n=MIN_N):
    """ctl, arm: one value per run (None: the run lacked the metric). Returns (PASS|FAIL|UNMEASURED|INFO, note)."""
    if kind == "info":
        return "INFO", ""
    c, a = [v for v in ctl if v is not None], [v for v in arm if v is not None]
    if len(c) < min_n or len(a) < min_n:
        return "UNMEASURED", f"n ctl {len(c)}/{len(ctl)}, arm {len(a)}/{len(arm)} (need {min_n}; {len(ctl) - len(c) + len(arm) - len(a)} run(s) lack the metric)"
    if kind in ("num", "share"):
        lo, hi = min(c), max(c)
        if kind == "share" and hi - lo >= 0.5:
            return "UNMEASURED", f"control range {lo:.2f}-{hi:.2f} is 0.5 wide or more: no arm could FAIL"
        m = max(floor, WIDEN * (hi - lo))
        med = statistics.median(a)
        return ("PASS" if lo - m <= med <= hi + m else "FAIL"), f"ctl {lo:.3g}-{hi:.3g} +-{m:.3g}"
    if kind == "zero":   # a real pointer never reports outside the viewport: the control must show 0 and so must the arm
        return ("PASS" if max(c) == 0 and max(a) == 0 else "FAIL"), ""
    key = repr
    return ("PASS" if {key(v) for v in a} <= {key(v) for v in c} else "FAIL"), ""


FRAME_OK = (14.0, 18.0)   # the host's VDD runs 60 Hz; a remote display adapter (RDP) paces rAF at ~32 Hz (measured 2026-11-21)


def presence(log, row):
    """Absence-style PASSes need the surface to exist: None when it does, else why the run measured nothing."""
    m = log.get("meta") or {}
    if not m.get("secure"):
        return "not a secure context"
    if row == "I2" and not m.get("coalesced_fn"):
        return "getCoalescedEvents is not a function"
    if row == "I3" and m.get("dpr") != EXPECT_DPR:
        return f"dpr {m.get('dpr')} is not {EXPECT_DPR}: whole CSS pixels pass the grid trivially"
    if not [e for e in log["ev"] if e["tr"]]:
        return "no trusted event arrived"
    if row == "I5" and not [e for e in log["ev"] if e["tr"] and e["t"] == "mousedown"]:
        return "no mousedown arrived: no click was measured"
    f = frame_ms(log)
    if row == "I1" and not (f and FRAME_OK[0] <= f <= FRAME_OK[1]):
        return f"rAF interval {f and round(f, 1)} ms is not the 60 Hz display's (live RDP session?)"
    return None


def judge(row, ctl, arm_logs):
    """Per metric: (verdict, arm values, note); plus "_row": the row's verdict. ctl: {group: logs} (a control per pointer rate,
    never pooled) or a list for one group. The ROW is judged per group: a group PASSes the row only when it passes EVERY
    judged metric, because the metrics of one pointer must agree on one polling rate (an arm that matches 125 Hz on one metric
    and 1000 Hz on another is no mouse). The row PASSes when one group does, FAILs when none does and some group fails it,
    else it is UNMEASURED. A metric's own verdict is the best any group gives it and is for reading only. A run with the
    surface missing makes the whole row UNMEASURED: {"_": ("UNMEASURED", why)}."""
    groups = ctl if isinstance(ctl, dict) else {"ctl": ctl}
    for logs in (*groups.values(), arm_logs):
        for lg in logs:
            why = presence(lg, row)
            if why:
                return {"_": ("UNMEASURED", why)}
    am = [ROWS[row](lg) for lg in arm_logs]
    gm = {g: [ROWS[row](lg) for lg in logs] for g, logs in groups.items()}
    out, by_group = {}, {g: [] for g in groups}
    for name, (kind, floor) in SPEC[row].items():
        a = [x[name] if x else None for x in am]
        per = {g: metric_verdict(kind, floor, [x[name] if x else None for x in cm], a) for g, cm in gm.items()}
        for g, (v, _) in per.items():
            by_group[g].append(v)
        vs = [v for v, _ in per.values()]
        verdict = "INFO" if kind == "info" else "PASS" if "PASS" in vs else "FAIL" if "FAIL" in vs else "UNMEASURED"
        out[name] = (verdict, a, "; ".join(f"{g}: {v} {n}".strip() for g, (v, n) in per.items()))
    rows = {g: "FAIL" if "FAIL" in vs else "UNMEASURED" if "UNMEASURED" in vs else "PASS" for g, vs in by_group.items()}
    row_v = "PASS" if "PASS" in rows.values() else "FAIL" if "FAIL" in rows.values() else "UNMEASURED"
    out["_row"] = (row_v, None, "; ".join(f"{g}: {v}" for g, v in rows.items()))
    return out


def row_verdict(per_metric):
    if "_row" in per_metric:
        return per_metric["_row"][0]
    v = [x[0] for x in per_metric.values()]
    return "FAIL" if "FAIL" in v else "UNMEASURED" if "UNMEASURED" in v else "PASS"

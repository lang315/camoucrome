"""Judge of the input probes (plan 2026-11-21-input-probes.md, rows I1-I6). Pure: a snapshot of page.html's log in,
metrics and verdicts out. A driven arm FAILs a row when it is distinguishable from the control (stock Chrome under OS
input) beyond the control's own run-to-run spread."""
import random
import statistics

MIN_GAPS = 50          # I2b needs this many coalesced stamp gaps in a run before it says anything
MIN_RAW = 50           # I7 needs this many pointerrawupdate events
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
    # only moves inside the logged tick range: one before the first tick has no tick of its own (P0b 2026-11-22: it was paired
    # with a far later one). `covered` is the share judged; the row is UNMEASURED below COVERED_MIN (see presence).
    inside = [e for e in mv if ticks[0] <= e["now"] <= ticks[-1]]
    per, lead = {}, []
    for e in inside:
        nxt = next((t for t in ticks if t >= e["now"]), None)
        per[nxt] = per.get(nxt, 0) + 1
        lead.append(nxt - e["now"])
    gaps = [b["ts"] - a["ts"] for a, b in zip(mv, mv[1:])]
    return {"moves": len(mv), "covered": len(inside) / len(mv), "frame_ms": f,
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


def i2b(log):
    """Spacing of the getCoalescedEvents() timeStamps inside one pointermove: a mouse reports every 8 ms (125 Hz) or 1 ms
    (1000 Hz), so the samples of one frame are that far apart. Median and sd over every intra-event gap."""
    gaps = []
    for e in evs(log, "pointermove"):
        c = e.get("cts") or []
        gaps += [b - a for a, b in zip(c, c[1:])]
    if len(gaps) < MIN_GAPS:   # a handful of gaps is not a spacing
        return None
    med = _med(gaps)
    # the shape: stock's gaps at 125 Hz are a peak (56 % within +-0.25 ms of the median) with a tail (the rest, some of it
    # 2 ms or more away): the median and sd alone cannot tell that from a flat jitter of the same sd
    return {"spacing_n": len(gaps), "spacing_med": med, "spacing_sd": statistics.pstdev(gaps),
            "core_share": sum(1 for g in gaps if abs(g - med) <= 0.25) / len(gaps),
            "tail_share": sum(1 for g in gaps if abs(g - med) > 2.0) / len(gaps)}


def i2c(log):
    """Two properties of the coalesced lists. `whole_share`: the share of intra-event stamp gaps that are whole ms
    (abs(gap - round(gap)) < 0.05): the control's stamps may be OS-quantized, ours continuous; INFO until the control's shape is
    known. `repeat`: neighbouring coalesced samples (across the flattened lists, in order) at the same (x, y), which stock
    drops on Windows; `repeat_share` is it over the neighbour pairs. Needs the page's `cxy`."""
    gaps, pos = [], []
    for e in evs(log, "pointermove"):
        c = e.get("cts") or []
        gaps += [b - a for a, b in zip(c, c[1:])]
        pos += e.get("cxy") or []
    if not gaps:
        return None
    rep = sum(1 for a, b in zip(pos, pos[1:]) if a == b) if pos else None
    return {"gaps": len(gaps), "whole_share": sum(1 for g in gaps if abs(g - round(g)) < 0.05) / len(gaps),
            "repeat": rep, "repeat_share": rep / (len(pos) - 1) if pos and len(pos) > 1 else None}


def i7(log):
    """pointerrawupdate: `lat_sd`, the sd of now - timeStamp (a real mouse delivers each report as it arrives, so the latency
    is steady; a burst forwarded back to back makes it grow within the burst), and `pairs`, the neighbouring events whose
    `now` lie within 0.5 ms but whose timeStamps are 2 ms or more apart; `pair_share` is it over the neighbour pairs."""
    raw = evs(log, "pointerrawupdate")
    if len(raw) < MIN_RAW:   # a handful of events is not a latency
        return None
    pairs = sum(1 for a, b in zip(raw, raw[1:]) if abs(b["now"] - a["now"]) < 0.5 and abs(b["ts"] - a["ts"]) >= 2.0)
    return {"raw": len(raw), "lat_sd": statistics.pstdev([e["now"] - e["ts"] for e in raw]), "pairs": pairs,
            "pair_share": pairs / (len(raw) - 1)}


def after_skip(log, thr=25.0, cap=None):
    """Pointermoves that ride a frame arriving more than `thr` ms after the one before (a skipped frame), read from the page's
    own rAF ticks and the move's `now`, never from head timeStamps: an authored stamp run is contiguous, so a merged
    two-bucket list always shows a 2-frame head gap. With `cap`, only moves whose coalesced list is longer than it."""
    ticks = [n for _, n in log["raf"]]
    out = 0
    for e in evs(log, "pointermove"):
        if cap is not None and e["cs"] <= cap:
            continue
        i = next((k for k, t in enumerate(ticks) if t >= e["now"]), None)
        if i and ticks[i] - ticks[i - 1] > thr:
            out += 1
    return out


def i3(log):
    """The device-pixel grid, from pointermove (a MouseEvent's clientX is whole CSS px; a PointerEvent's is not). A pointer
    on whole device pixels has clientX*dpr integral up to the viewport's fixed offset, so each axis shows ONE fractional
    part. `off_share`: the share of values off their axis's modal fractional part (circular, tolerance DPR_EPS)."""
    dpr = log["meta"]["dpr"]
    mv = [e for e in evs(log, "pointermove") if e["x"] is not None]
    if not mv:
        return None
    off, modes = [], {}
    for k in ("x", "y"):
        fr = [(e[k] * dpr) % 1.0 for e in mv]
        modes[k] = statistics.mode(round(f, 3) for f in fr)
        off += [min(abs(f - modes[k]), 1 - abs(f - modes[k])) > DPR_EPS for f in fr]
    # fx, fy: the axis's modal fractional part. A real pointer lands on k/dsf in ROOT-WINDOW DIP and the view sits at an integer DIP
    # origin o in its window, so frac(clientY*dpr) = frac(-dsf*o_y) (host H2 control: x 0.00, y 0.25 at origin (8, 87)). A single
    # fraction per axis is not enough: it must be the control's.
    return {"moves": len(mv), "dpr": dpr, "off_share": sum(off) / len(off), "fx": modes["x"] % 1.0, "fy": modes["y"] % 1.0}


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


ROWS = {"I1": i1, "I2": i2, "I2b": i2b, "I2c": i2c, "I3": i3, "I4": i4, "I5": i5, "I6": i6, "I7": i7}
MIN_N = 4               # runs per group (each control rate, and the arm) a verdict needs
WIDEN = 0.25            # a numeric verdict widens the control's range by this fraction of it (never less than the floor)
COVERED_MIN = 0.9      # I1: the share of moves that lie inside the logged tick range a verdict needs
EXPECT_DPR = 1.25       # the probes run at this device scale factor; I3 means nothing at 1
# metric -> (kind, floor). pool: the arm's mean over runs minus the control's, within +-floor (a run-level bootstrap interval wider than floor is UNMEASURED); num: the arm's median must lie in the control's range widened by max(floor, WIDEN * range);
# share: the same for a 0..1 share, UNMEASURED when the control's own range is 0.5 or more (it could never FAIL);
# zero: control and arm both 0; eq: every arm value is one of the control's; info: reported, never judged.
SPEC = {
    "I1": {"multi": ("share", 0.05), "aligned": ("share", 0.10), "short": ("share", 0.10), "gap_med": ("num", 2.0),
           "covered": ("info", 0)},   # the share of moves inside the tick log: the row is UNMEASURED below COVERED_MIN (presence)
    "I2": {"multi": ("share", 0.10), "coalesced_max": ("num", 1.0), "predicted": ("share", 0.10)},
    # per-rate groups: the control's range is 8 ms at 125 Hz and 1 ms at 1000 Hz, so a floor this small keeps the rates apart
    "I2b": {"spacing_med": ("pool", 0.25), "spacing_sd": ("pool", 0.40), "core_share": ("pool", 0.10), "tail_share": ("pool", 0.05)},
    # whole_share: the control's stamps are partly whole ms (host 2026-11-22, 4-6 runs: .17-.28; chance for the 0.05 window is .10),
    # the pooled value of ours must lie within +-.12 of the control's pooled value (kind "pool"): a continuous stamp (.09-.10) fails. repeats: stock drops same-position moves
    "I2c": {"whole_share": ("pool", 0.12), "repeat_share": ("pool", 0.01), "repeat": ("info", 0)},
    # pointerrawupdate: the sd of now - timeStamp is the control's (floor 0.5 ms), back-to-back events are not (a back-to-back burst has pair_share ~.5)
    "I7": {"lat_sd": ("num", 0.5), "pair_share": ("share", 0.02), "pairs": ("info", 0)},
    "I3": {"off_share": ("share", 0.05), "fx": ("mode", DPR_EPS), "fy": ("mode", DPR_EPS)},
    "I4": {"exit_sig": ("eq", 0), "outside": ("zero", 0), "exit_depth": ("num", 6.0), "exit_rt": ("eq", 0), "reenter": ("eq", 0)},
    "I5": {"right": ("eq", 0), "click_detail": ("eq", 0), "dblclick": ("eq", 0), "contextmenu": ("eq", 0)},
    # The key timing is authored by the harness in every arm (the control from the host's keyboard settings, the driven arms
    # from a fixed 500/33 ms), so it says nothing about Chrome: reported as info. Only what Chrome makes is judged.
    "I6": {"flags_ok": ("eq", 0), "first_rep": ("eq", 0), "delay": ("info", 0), "interval_med": ("info", 0), "interval_sd": ("info", 0)},
}


def pool_diff(ctl, arm, draws=2000):
    """Pooled difference arm - control (the mean of the per-run values) and its 95 % interval from a run-level bootstrap
    (runs are the clusters: resample the control's runs and the arm's runs, each with replacement; seeded, so a rerun agrees)."""
    rng = random.Random(0)
    mean = lambda v: sum(v) / len(v)
    d = sorted(mean(rng.choices(arm, k=len(arm))) - mean(rng.choices(ctl, k=len(ctl))) for _ in range(draws))
    return mean(arm) - mean(ctl), d[int(0.025 * draws)], d[int(0.975 * draws)]


def metric_verdict(kind, floor, ctl, arm, min_n=MIN_N):
    """ctl, arm: one value per run (None: the run lacked the metric). Returns (PASS|FAIL|UNMEASURED|INFO, note)."""
    if kind == "info":
        return "INFO", ""
    c, a = [v for v in ctl if v is not None], [v for v in arm if v is not None]
    if len(c) < min_n or len(a) < min_n:
        return "UNMEASURED", f"n ctl {len(c)}/{len(ctl)}, arm {len(a)}/{len(arm)} (need {min_n}; {len(ctl) - len(c) + len(arm) - len(a)} run(s) lack the metric)"
    if kind == "pool":
        # pooled over the runs, not the control's range in this session: that range moves between host sessions (-14 / -15 / run 7)
        # while the pooled value does not (core_share .593 / .595, whole_share .282 / .255 across sessions s1 / s2). `floor` is the
        # tolerance on the pooled difference, measured between sessions (see measurements/2026-11-22-input-band-judge.md).
        d, lo, hi = pool_diff(c, a)
        note = f"diff {d:+.3g} [{lo:+.3g}, {hi:+.3g}] tol +-{floor:g}"
        if (hi - lo) / 2 > floor:   # the interval is wider than the tolerance: too few runs to tell
            return "UNMEASURED", note + " (interval wider than the tolerance)"
        return ("PASS" if abs(d) <= floor else "FAIL"), note
    if kind in ("num", "share"):
        lo, hi = min(c), max(c)
        if kind == "share" and hi - lo >= 0.5:
            return "UNMEASURED", f"control range {lo:.2f}-{hi:.2f} is 0.5 wide or more: no arm could FAIL"
        m = max(floor, WIDEN * (hi - lo))
        med = statistics.median(a)
        return ("PASS" if lo - m <= med <= hi + m else "FAIL"), f"ctl {lo:.3g}-{hi:.3g} +-{m:.3g}"
    if kind == "mode":   # a fractional part (circular): every arm value within `floor` of one the control shows. Same window, same view origin.
        def near(x, y):
            return min(abs(x - y), 1 - abs(x - y)) <= floor
        moot = all(near(w, 0.0) for w in c)
        note = "control fraction 0: the view origin is moot at this layout" if moot else f"ctl modal fractions {sorted({round(w, 3) for w in c})}"
        return ("PASS" if all(any(near(v, w) for w in c) for v in a) else "FAIL"), note
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
    if row in ("I2", "I2b") and not m.get("coalesced_fn"):
        return "getCoalescedEvents is not a function"
    if row == "I3" and m.get("dpr") != EXPECT_DPR:
        return f"dpr {m.get('dpr')} is not {EXPECT_DPR}: whole CSS pixels pass the grid trivially"
    if not [e for e in log["ev"] if e["tr"]]:
        return "no trusted event arrived"
    if row == "I7" and not [e for e in log["ev"] if e["tr"] and e["t"] == "pointerrawupdate"]:
        return "no pointerrawupdate arrived (not a secure context, or the listener saw no move)"
    if row == "I5" and not [e for e in log["ev"] if e["tr"] and e["t"] == "mousedown"]:
        return "no mousedown arrived: no click was measured"
    f = frame_ms(log)
    if row == "I1" and not (f and FRAME_OK[0] <= f <= FRAME_OK[1]):
        return f"rAF interval {f and round(f, 1)} ms is not the 60 Hz display's (live RDP session?)"
    if row == "I1":
        m1 = i1(log)
        if m1 and m1["covered"] < COVERED_MIN:
            return f"covered {m1['covered']:.2f} < {COVERED_MIN}: the tick log does not span the moves"
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
    if row == "I3":   # the view origin (the lattice fractions) moves with the chrome above the page: an infobar changes it
        chrome = lambda lg: lg["meta"].get("oh", 0) - lg["meta"].get("ih", 0)
        ctl_h, arm_h = {chrome(lg) for logs in groups.values() for lg in logs}, {chrome(lg) for lg in arm_logs}
        if not arm_h <= ctl_h:
            return {"_": ("UNMEASURED", f"outerHeight - innerHeight differs: control {sorted(ctl_h)}, arm {sorted(arm_h)} (an infobar? the view origin is not the control's)")}
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

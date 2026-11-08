#!/usr/bin/env python3
"""Fit the human-input timing model from public datasets; write aggregates only.

    calibrate_human_input.py --keyrecs free-text.csv --boun <session files...> \
        [--out settings/human_input.json]

Sources (both CC BY 4.0, which allows derived statistics with attribution):
  keyrecs  KeyRecs, Zenodo 10.5281/zenodo.7886743, free-text.csv (key press/release
           latencies per digraph, in seconds).
  boun     Bogazici University Mouse Dynamics Dataset, Mendeley w6cxr8yc7p
           (timestamped mouse events with Pressed/Released state).
Raw rows are read from a path outside the repo and never written. Fields no
dataset gives keep a named default and say so ("maintainer default, unsourced").
Run outside the repo tree, e.g. data under /private/tmp.
"""
import argparse
import collections
import csv
import datetime
import json
import math
import pathlib
import sys

REFS = {
    "keyrecs": {
        "dataset": "KeyRecs: A keystroke dynamics and typing pattern recognition dataset (free-text.csv)",
        "licence": "CC BY 4.0",
        "url": "https://zenodo.org/records/7886743",
        "cite": "Pinto Praca I. et al., KeyRecs, Data in Brief 2023, doi:10.1016/j.dib.2023.109509; Zenodo doi:10.5281/zenodo.7886743",
    },
    "boun": {
        "dataset": "Bogazici University Mouse Dynamics Dataset",
        "licence": "CC BY 4.0",
        "url": "https://data.mendeley.com/datasets/w6cxr8yc7p/2",
        "cite": "Bogazici University Mouse Dynamics Dataset, Mendeley Data, V2 (doi:10.17632/w6cxr8yc7p.2); data article PMC8141654",
    },
    "maintainer": {
        "dataset": "maintainer default, unsourced",
        "licence": "n/a",
        "url": "",
        "cite": "Chosen by the maintainers in PR #156; no dataset gives it",
    },
}

# What no dataset gives. Same values as client/go/rodclient/human.go before the
# generated file (PR #156), so an unmeasured field behaves as it did.
DEFAULTS = {
    "flight_before_shift": {"factor": 1.25},
    "pause": {"chance": 0.03, "median_ms": 500.0, "sigma": 0.40, "min_ms": 300.0, "max_ms": 900.0},
    "settle": {"median_ms": 120.0, "sigma": 0.40, "min_ms": 40.0, "max_ms": 400.0},
    "tremor": {"median_ms": 190.0, "sigma": 0.30, "min_ms": 120.0, "max_ms": 300.0,
               "px": 2.0, "sigma_px": 0.8},
    "click_point": {"spread": 1.0 / 6, "inner": 0.35, "min_box": 8.0},
    "rollover_max_down": {"keys": 2},
    # Fields a dataset overrides when it is fitted; the same values stand in
    # when the dataset is not given (a test, or a partial run).
    "dwell": {"median_ms": 95.0, "sigma": 0.30, "min_ms": 40.0, "max_ms": 250.0},
    "flight": {"median_ms": 160.0, "sigma": 0.45, "min_ms": 60.0, "max_ms": 600.0},
    "flight_after_punct": {"factor": 1.4},
    "shift_lead": {"median_ms": 55.0, "sigma": 0.30, "min_ms": 35.0, "max_ms": 90.0},
    "shift_release": {"median_ms": 30.0, "sigma": 0.50, "min_ms": 10.0, "max_ms": 60.0},
    "click_hold": {"median_ms": 85.0, "sigma": 0.30, "min_ms": 40.0, "max_ms": 200.0},
    "rollover": {"chance": 0.15, "median_ms": 40.0, "sigma": 0.6, "min_ms": 5.0, "max_ms": 150.0},
    "typos": {"rate": 0.01, "run_len_probs": [0.6, 0.3, 0.1]},
    "typos_notice": {"median_ms": 400.0, "sigma": 0.5, "min_ms": 150.0, "max_ms": 1500.0},
    "backspace_dwell": {"median_ms": 85.0, "sigma": 0.3, "min_ms": 40.0, "max_ms": 200.0},
    "backspace_flight": {"median_ms": 150.0, "sigma": 0.4, "min_ms": 60.0, "max_ms": 500.0},
    "typos_retype": {"median_ms": 250.0, "sigma": 0.5, "min_ms": 80.0, "max_ms": 1000.0},
    "digraph": {},
}


# ---- statistics -----------------------------------------------------------

def fit_lognormal(xs):
    """MLE of a lognormal: mean and SD of ln x. Returns (mu, sigma)."""
    ls = [math.log(x) for x in xs]
    n = len(ls)
    mu = sum(ls) / n
    var = sum((v - mu) ** 2 for v in ls) / n
    return mu, math.sqrt(var)


def lognormal_from_mean_sd(mean, sd):
    """Lognormal (mu, sigma) with the given arithmetic mean and SD.

    For a published mean/SD: sigma^2 = ln(1 + sd^2/mean^2), mu = ln(mean) - sigma^2/2.
    """
    s2 = math.log(1 + (sd / mean) ** 2)
    return math.log(mean) - s2 / 2, math.sqrt(s2)


def quantile(xs, q):
    """Linear-interpolated quantile, q in [0, 1]."""
    s = sorted(xs)
    pos = q * (len(s) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def _r(x):
    return float(f"{x:.4g}")


def dist(xs_ms, ref, date, lo_q=0.005, hi_q=0.995):
    """A lognormal field: median, sigma, clamp quantiles, with its source."""
    mu, sigma = fit_lognormal(xs_ms)
    return {"median_ms": _r(math.exp(mu)), "sigma": _r(sigma),
            "min_ms": _r(quantile(xs_ms, lo_q)), "max_ms": _r(quantile(xs_ms, hi_q)),
            "n": len(xs_ms), "source": ref, "date": date}


def default(name, date=None):
    d = dict(DEFAULTS[name])
    d.update({"source": "maintainer", "date": date})
    return d


# ---- keystrokes (KeyRecs) -------------------------------------------------

MAX_FLIGHT_S = 1.0     # a longer keyDown-to-keyDown is a pause, modelled apart
MAX_DWELL_S = 0.5      # a longer hold is a stuck key, not typing
PUNCT = set(".,;:!?'-\"()")


def _typing(k):
    return len(k) == 1 or k == "Space"


def _f(s):
    try:
        return float(s)
    except ValueError:
        return None


def keyrecs_params(path, digraph_min_n=300, date=None):
    """Fields KeyRecs gives, from free-text.csv. Times in the file are seconds."""
    rows = []
    with open(path, newline="") as fh:
        rd = csv.reader(fh)
        next(rd)
        for r in rd:
            if len(r) >= 9:
                rows.append(r)
    dwell, flight, overlap, roll, n_pairs = [], [], [], 0, 0
    after_punct, after_letter = [], []
    lead, release = [], []
    bs_dwell, bs_flight, retype, notice = [], [], [], []
    digraphs = collections.defaultdict(list)
    n_typing, runs = 0, []
    i = 0
    while i < len(rows):
        p, s, k1, k2, d11, dd, _du, ud, uu = rows[i][:9]
        d11, dd, ud, uu = _f(d11), _f(dd), _f(ud), _f(uu)
        if _typing(k1):
            n_typing += 1
            if d11 is not None and 0 < d11 <= MAX_DWELL_S:
                dwell.append(d11 * 1000)
        if k1 == "Backspace" and d11 is not None and 0 < d11 <= MAX_DWELL_S:
            bs_dwell.append(d11 * 1000)
        if _typing(k1) and _typing(k2) and dd is not None and 0 < dd < MAX_FLIGHT_S:
            if k1.isalpha() and k2.isalpha():
                flight.append(dd * 1000)  # within a word; word-boundary pauses are modelled apart
            n_pairs += 1
            if ud is not None and ud < 0:
                roll += 1
                overlap.append(-ud * 1000)
            if k1 == "Space" or k1 in PUNCT:
                after_punct.append(dd * 1000)
            elif k1.isalpha():
                after_letter.append(dd * 1000)
            if k1.isalpha() and k2.isalpha():
                digraphs[(k1 + k2).lower()].append(dd * 1000)
        # Shift for a capital: pressed before the letter (DD < 0 on letter->Shift),
        # let go after it (UU > 0).
        if k1.isalpha() and k1.isupper() and k2 == "Shift" and dd is not None and -0.3 < dd < 0:
            lead.append(-dd * 1000)
            if uu is not None and 0 < uu < 0.2:
                release.append(uu * 1000)
        if k1 == "Backspace" and k2 == "Backspace" and dd is not None and 0.03 < dd < MAX_FLIGHT_S:
            bs_flight.append(dd * 1000)
        if k1 == "Backspace" and _typing(k2) and dd is not None and 0.03 < dd < MAX_FLIGHT_S:
            retype.append(dd * 1000)
        # a correction run: key -> Backspace, then Backspace -> Backspace ..., then Backspace -> key
        if _typing(k1) and k2 == "Backspace":
            if dd is not None and 0.03 < dd < 3.0:
                notice.append(dd * 1000)
            length, j = 1, i + 1
            while (j < len(rows) and rows[j][0] == p and rows[j][1] == s
                   and rows[j][2] == "Backspace" and rows[j][3] == "Backspace"):
                length += 1
                j += 1
            runs.append(length)
            i = j
            continue
        i += 1

    out = {}
    # an empty sample (a partial file) keeps the default, as every other field does
    out["dwell"] = dist(dwell, "keyrecs", date) if dwell else default("dwell", date)
    out["flight"] = dist(flight, "keyrecs", date) if flight else default("flight", date)
    if len(after_punct) >= 100 and len(after_letter) >= 100:
        out["flight_after_punct"] = {
            "factor": _r(quantile(after_punct, 0.5) / quantile(after_letter, 0.5)),
            "n": len(after_punct), "source": "keyrecs", "date": date}
    if n_pairs:
        ov = dist(overlap, "keyrecs", date) if len(overlap) >= 30 else default("rollover", date)
        ov.update({"chance": _r(roll / n_pairs), "n": roll, "pairs": n_pairs, "source": "keyrecs"})
        out["rollover"] = ov
    if len(lead) >= 100:
        out["shift_lead"] = dist(lead, "keyrecs", date, 0.05, 0.95)
    if len(release) >= 100:
        out["shift_release"] = dist(release, "keyrecs", date, 0.05, 0.95)
    if len(bs_dwell) >= 100:
        out["backspace_dwell"] = dist(bs_dwell, "keyrecs", date)
    if len(bs_flight) >= 100:
        out["backspace_flight"] = dist(bs_flight, "keyrecs", date)
    if len(retype) >= 100:
        out["typos_retype"] = dist(retype, "keyrecs", date)
    if len(notice) >= 100:
        out["typos_notice"] = dist(notice, "keyrecs", date)
    if runs:
        # runs of 3 or more fold into the last bucket
        cnt = collections.Counter(min(r, 3) for r in runs)
        probs = [_r(cnt.get(b, 0) / len(runs)) for b in (1, 2, 3)]
        out["typos"] = {"rate": _r(len(runs) / n_typing), "runs": len(runs), "chars": n_typing,
                        "run_len_probs": probs, "source": "keyrecs", "date": date,
                        "note": "corrections per typed key from Backspace runs; transcription task"}
    out["digraph"] = {
        k: {"median_ms": _r(quantile(v, 0.5)), "n": len(v)}
        for k, v in sorted(digraphs.items(), key=lambda kv: -len(kv[1]))
        if len(v) >= digraph_min_n}
    if out["digraph"]:
        out["digraph"] = {"source": "keyrecs", "date": date, "min_n": digraph_min_n,
                          "pairs": out["digraph"]}
    else:
        out["digraph"] = default("digraph", date)
    return out


# ---- mouse (Bogazici) -----------------------------------------------------

MAX_CLICK_S = 0.5   # a longer press is a drag, not a click
MIN_CLICK_S = 0.01  # a shorter one is a logging artefact: no switch closes and opens in under 10 ms


def _col(header, *names):
    low = [h.strip().lower() for h in header]
    for n in names:
        for i, h in enumerate(low):
            if n in h:
                return i
    raise ValueError(f"no column like {names} in {header}")


def boun_params(paths, date=None):
    """click_hold from Pressed -> Released of the left button, in session files."""
    holds = []
    files = []
    for p in paths:
        p = pathlib.Path(p)
        files += sorted(p.glob("*.csv")) if p.is_dir() else [p]
    for path in files:
        with open(path, newline="") as fh:
            rd = csv.reader(fh)
            header = next(rd)
            t_i = _col(header, "client timestamp", "timestamp")
            b_i = _col(header, "button")
            s_i = _col(header, "state")
            down = None
            for r in rd:
                if len(r) <= max(t_i, b_i, s_i):
                    continue
                t = _f(r[t_i])
                if t is None or r[b_i] != "Left":
                    continue
                if r[s_i] == "Pressed":
                    down = t
                elif r[s_i] == "Released" and down is not None:
                    if MIN_CLICK_S <= t - down <= MAX_CLICK_S:
                        holds.append((t - down) * 1000)
                    down = None
    out = {}
    if holds:
        out["click_hold"] = dist(holds, "boun", date)
        out["click_hold"]["session_files"] = len(files)
    return out


# ---- assembly -------------------------------------------------------------

def assemble(keyrecs=None, boun=None, date=None):
    out = {"schema": 1, "refs": REFS}
    for name in DEFAULTS:
        out[name] = default(name, date)
    for part in (keyrecs, boun):
        if part:
            out.update(part)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--keyrecs", type=pathlib.Path)
    ap.add_argument("--boun", type=pathlib.Path, nargs="*", default=[])
    ap.add_argument("--date", default=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"))
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("settings/human_input.json"))
    a = ap.parse_args(argv)
    here = pathlib.Path(__file__).resolve().parent.parent
    for p in [a.keyrecs, *a.boun]:
        if p and here in p.resolve().parents:
            sys.exit(f"refusing raw data inside the repo tree: {p}")
    kr = keyrecs_params(a.keyrecs, date=a.date) if a.keyrecs else None
    bn = boun_params(a.boun, date=a.date) if a.boun else None
    doc = assemble(kr, bn, a.date)
    a.out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()

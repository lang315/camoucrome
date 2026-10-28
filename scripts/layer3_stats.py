"""Roadmap step 5: the challenge-rate difference between the fork and stock, per vendor, with an interval
(spec 2026-10-24-step5-layer3-design.md, 5).

A pair is one round on one site: both arms on the same exit IP. A pair with an unknown arm is dropped from the rates
and counted. d = rate_fork - rate_stock, positive = the fork is challenged more.
Primary interval: a percentile bootstrap clustered by site (sites resampled, then pairs within each), each site's
difference weighted equally. Fallback beside it: the paired Agresti-Min interval on the pooled pairs (it ignores the
site effect, so it is narrower).
Reported numbers: d is the equal-weight mean of per-site differences (what the bootstrap interval is about);
d_pooled = rate_fork - rate_stock is the pooled-pair difference; they differ when sites have unequal pair counts.
With 3 sites the clustered interval is coarse (few distinct site resamples): read it beside the paired interval.
A zero-width interval ("degenerate") means no variation was observed, not certainty."""
import math
import random

Z = 1.959964


def pairs_from(rows):
    """rows: [{"site", "round", "arm": "S"|"F", "challenged": bool|None}] -> {site: [(s, f)]}, unknown count.
    None = unknown outcome."""
    by = {}
    for r in rows:
        arms = by.setdefault((r["site"], r["round"]), {})
        arms[r["arm"]] = None if r["arm"] in arms else r["challenged"]  # a duplicate row makes the pair unknown
    sites, unknown = {}, 0
    for (site, _), arms in sorted(by.items()):
        if set(arms) != {"S", "F"} or None in arms.values():
            unknown += 1
            continue
        sites.setdefault(site, []).append((arms["S"], arms["F"]))
    return sites, unknown


def _site_diff(prs):
    return sum(f - s for s, f in prs) / len(prs)


def rates(sites):
    allp = [p for prs in sites.values() for p in prs]
    n = len(allp)
    if not n:
        return None, None, 0
    return sum(s for s, _ in allp) / n, sum(f for _, f in allp) / n, n


def bootstrap_ci(sites, resamples=10000, seed=1):
    """(d, lo, hi): equal weight per site, sites then pairs resampled."""
    names = sorted(sites)
    d = sum(_site_diff(sites[k]) for k in names) / len(names)
    rng = random.Random(seed)
    out = []
    for _ in range(resamples):
        total = 0.0
        for _ in names:
            prs = sites[rng.choice(names)]
            total += _site_diff([rng.choice(prs) for _ in prs])
        out.append(total / len(names))
    out.sort()
    return d, out[int(0.025 * resamples)], out[min(resamples - 1, int(0.975 * resamples))]


def paired_ci(sites):
    """Agresti-Min: half a pair added to each of the four cells. (d, lo, hi, b, c) with b = fork-only, c = stock-only."""
    allp = [p for prs in sites.values() for p in prs]
    n = len(allp)
    b = sum(1 for s, f in allp if f and not s)
    c = sum(1 for s, f in allp if s and not f)
    n2, b2, c2 = n + 2, b + 0.5, c + 0.5
    d = (b2 - c2) / n2
    se = math.sqrt(max(0.0, (b2 + c2) - (b2 - c2) ** 2 / n2)) / n2
    return d, max(-1.0, d - Z * se), min(1.0, d + Z * se), b, c


def mcnemar_exact_p(b, c):
    """Two-sided exact binomial p of b vs c discordant pairs under 'no difference'."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def order_effect(rows):
    """Challenged rate of the arm visited second minus first, over pairs with both known. rows carry "order": "SF"|"FS"."""
    first, second = [], []
    by = {}
    for r in rows:
        by.setdefault((r["site"], r["round"]), {})[r["arm"]] = r
    for arms in by.values():
        if set(arms) != {"S", "F"} or any(a["challenged"] is None for a in arms.values()):
            continue
        order = arms["S"].get("order")
        if order not in ("SF", "FS"):
            continue
        a, b = (arms["S"], arms["F"]) if order == "SF" else (arms["F"], arms["S"])
        first.append(a["challenged"])
        second.append(b["challenged"])
    if not first:
        return None
    return sum(second) / len(second) - sum(first) / len(first)


def vendor_row(rows, resamples=10000, seed=1):
    """One vendor's numbers from its rows."""
    sites, unknown = pairs_from(rows)
    s, f, n = rates(sites)
    if not n:
        return {"n": 0, "unknown": unknown, "unmeasured": True}
    d, lo, hi = bootstrap_ci(sites, resamples, seed)
    pd, plo, phi, b, c = paired_ci(sites)
    return {"n": n, "unknown": unknown, "sites": len(sites), "rate_stock": s, "rate_fork": f, "d": d, "d_pooled": f - s, "lo": lo, "hi": hi,
            "degenerate": hi == lo,
            "paired": {"d": pd, "lo": plo, "hi": phi, "b": b, "c": c, "p": mcnemar_exact_p(b, c)},
            "order_effect": order_effect(rows), "unmeasured": unknown / (n + unknown) > 0.10}


def runs_agree(row_a, row_b):
    """Do two runs agree for one vendor? The difference of their d values, with the half-widths added in quadrature
    (independent runs), must contain 0."""
    if row_a.get("unmeasured") or row_b.get("unmeasured"):
        return None
    wa, wb = (row_a["hi"] - row_a["lo"]) / 2, (row_b["hi"] - row_b["lo"]) / 2
    return abs(row_b["d"] - row_a["d"]) <= math.hypot(wa, wb)


# --- first-visitor design (docs plan 2026-10-28-px-arms-n-s2.md, section 3): independent visits, no pairs ---

EQUIV_MARGIN = 0.15  # fixed before the run (plan section 3)


def _wilson(x, n, z):
    if n == 0:
        return 0.0, 0.0, 1.0
    p = x / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return p, max(0.0, c - h), min(1.0, c + h)


def newcombe_diff(x1, n1, x2, n2, conf=0.95):
    """(p1 - p2, lo, hi): Newcombe-Wilson hybrid score interval, method 10. With either n at 0 nothing is known: (diff, -1, 1)."""
    from statistics import NormalDist
    z = NormalDist().inv_cdf(1 - (1 - conf) / 2)
    p1, l1, u1 = _wilson(x1, n1, z)
    p2, l2, u2 = _wilson(x2, n2, z)
    d = p1 - p2
    if n1 == 0 or n2 == 0:
        return d, -1.0, 1.0
    return d, d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2), d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)


def gate_g0(f_x, f_n, s_x, s_n):
    """Does the baseline gap reproduce? Passed only when the 95% lower bound of rate(F) - rate(S) is above 0."""
    d, lo, hi = newcombe_diff(f_x, f_n, s_x, s_n)
    return {"passed": lo > 0, "d": d, "lo": lo, "hi": hi}


def _unmeasured(c):
    x, n, u = c
    return n == 0 or u / (n + u) > 0.10


def arm_diffs(counts, gate):
    """counts: arm -> (challenged, measured, unknown), with S and F. For X in N, S2 (those present): d_X = rate(F) - rate(X) at 97.5%,
    carries_part (lo > 0), carries_all (also rate(X) - rate(S) inside +/-EQUIV_MARGIN at 95%). A failed gate gives no arm reading;
    an arm over 10% unknown is "UNMEASURED", so is the whole reading when S or F is."""
    if _unmeasured(counts["S"]) or _unmeasured(counts["F"]):
        return {"conclusion": "UNMEASURED"}
    if not gate["passed"]:
        return {"conclusion": "gap not reproduced"}
    (fx, fn, _), (sx, sn, _) = counts["F"], counts["S"]
    out = {}
    for arm in ("N", "S2"):
        if arm not in counts:
            continue
        if _unmeasured(counts[arm]):
            out[arm] = "UNMEASURED"
            continue
        ax, an, _ = counts[arm]
        d, lo, hi = newcombe_diff(fx, fn, ax, an, conf=0.975)
        _, elo, ehi = newcombe_diff(ax, an, sx, sn)
        part = lo > 0
        out[arm] = {"d": d, "lo": lo, "hi": hi, "carries_part": part,
                    "carries_all": part and -EQUIV_MARGIN <= elo and ehi <= EQUIV_MARGIN, "equiv_lo": elo, "equiv_hi": ehi}
    return out

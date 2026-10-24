"""The statistics on constructed data: a planted difference is found, none is not, the interval covers, runs compare."""
import random

import pytest

import layer3_stats as ls


def rows(spec, rounds=20, seed=1, order="SF"):
    """spec: {site: (p_stock, p_fork)} -> rows with independently drawn outcomes."""
    rng = random.Random(seed)
    out = []
    for site, (ps, pf) in spec.items():
        for r in range(rounds):
            out.append({"site": site, "round": r, "arm": "S", "challenged": rng.random() < ps, "order": order})
            out.append({"site": site, "round": r, "arm": "F", "challenged": rng.random() < pf, "order": order})
    return out


def test_a_planted_difference_excludes_zero():
    v = ls.vendor_row(rows({"a": (0.0, 1.0), "b": (0.0, 1.0), "c": (0.0, 1.0)}))
    assert v["d"] == 1.0 and v["lo"] > 0 and v["paired"]["lo"] > 0 and v["paired"]["p"] < 1e-6


def test_identical_arms_include_zero():
    v = ls.vendor_row(rows({"a": (1.0, 1.0), "b": (1.0, 1.0), "c": (1.0, 1.0)}))
    assert v["d"] == 0 and v["lo"] <= 0 <= v["hi"] and v["paired"]["b"] == 0 and v["paired"]["c"] == 0


def test_unknown_pairs_are_dropped_and_counted():
    data = rows({"a": (0.5, 0.5)}, rounds=10)
    data[0]["challenged"] = None
    v = ls.vendor_row(data)
    assert v["n"] == 9 and v["unknown"] == 1 and not v["unmeasured"]


def test_more_than_ten_percent_unknown_is_unmeasured():
    data = rows({"a": (0.5, 0.5)}, rounds=10)
    for r in data[:4:2]:
        r["challenged"] = None  # 2 of 10 pairs
    assert ls.vendor_row(data)["unmeasured"] is True


def test_no_usable_pairs_is_unmeasured():
    assert ls.vendor_row([])["unmeasured"] and ls.vendor_row([{"site": "a", "round": 0, "arm": "S", "challenged": True}])["n"] == 0


def test_the_bootstrap_is_deterministic_for_a_seed_and_the_interval_brackets_d():
    sites, _ = ls.pairs_from(rows({"a": (0.3, 0.5), "b": (0.4, 0.4), "c": (0.2, 0.6)}))
    a = ls.bootstrap_ci(sites, 2000, seed=7)
    assert a == ls.bootstrap_ci(sites, 2000, seed=7) and a[1] <= a[0] <= a[2]


def test_coverage_on_stock_against_stock_is_near_nominal():
    miss = 0
    trials = 100
    for t in range(trials):
        sites, _ = ls.pairs_from(rows({"a": (0.4, 0.4), "b": (0.4, 0.4), "c": (0.4, 0.4)}, seed=100 + t))
        d, lo, hi = ls.bootstrap_ci(sites, 300, seed=t)
        miss += not (lo <= 0 <= hi)
    assert miss <= 12, f"{miss} of {trials} A/A intervals excluded 0"  # nominal 5; the bound leaves room for the small number of sites


def test_a_real_difference_is_found_most_of_the_time():
    found = 0
    for t in range(40):
        sites, _ = ls.pairs_from(rows({"a": (0.2, 0.7), "b": (0.2, 0.7), "c": (0.2, 0.7)}, seed=500 + t))
        d, lo, hi = ls.bootstrap_ci(sites, 300, seed=t)
        found += lo > 0
    assert found >= 36


def test_mcnemar_exact_p_matches_known_values():
    assert ls.mcnemar_exact_p(0, 0) == 1.0
    assert ls.mcnemar_exact_p(5, 5) == 1.0
    assert ls.mcnemar_exact_p(9, 1) == pytest.approx(0.021484375)


def test_order_effect_is_second_minus_first():
    # the second-visited arm is challenged in every pair, the first in none
    data = []
    for r in range(10):
        order = "SF" if r % 2 == 0 else "FS"
        first, second = ("S", "F") if order == "SF" else ("F", "S")
        data.append({"site": "a", "round": r, "arm": first, "challenged": False, "order": order})
        data.append({"site": "a", "round": r, "arm": second, "challenged": True, "order": order})
    assert ls.order_effect(data) == 1.0
    assert ls.order_effect([]) is None


def test_runs_agree_when_the_difference_of_d_is_inside_the_combined_interval():
    a = {"d": 0.10, "lo": 0.0, "hi": 0.20}
    assert ls.runs_agree(a, {"d": 0.14, "lo": 0.02, "hi": 0.26}) is True
    assert ls.runs_agree(a, {"d": 0.60, "lo": 0.50, "hi": 0.70}) is False
    assert ls.runs_agree(a, {"unmeasured": True}) is None

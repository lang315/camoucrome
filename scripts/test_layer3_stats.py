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


def _pair(site, r, s, f, order="SF"):
    return [{"site": site, "round": r, "arm": "S", "challenged": s, "order": order},
            {"site": site, "round": r, "arm": "F", "challenged": f, "order": order}]


def test_d_is_the_site_mean_and_d_pooled_is_the_pair_pool():
    data = _pair("a", 0, False, True)  # site a: d = 1, one pair
    for r in range(3):
        data += _pair("b", r, True, True)  # site b: d = 0, three pairs
    v = ls.vendor_row(data, resamples=200)
    assert v["d"] == 0.5 and v["d_pooled"] == 0.25 and v["rate_fork"] - v["rate_stock"] == v["d_pooled"]


def test_order_effect_ignores_rows_without_or_with_invalid_order():
    data = _pair("a", 0, False, True)
    for r in data:
        del r["order"]
    assert ls.order_effect(data) is None
    assert ls.vendor_row(data, resamples=50)["order_effect"] is None
    mixed = _pair("a", 0, False, True, "SF") + _pair("a", 1, True, False, "XX")
    assert ls.order_effect(mixed) == 1.0


def test_degenerate_flags_a_zero_width_interval():
    assert ls.vendor_row(rows({"a": (1.0, 1.0), "b": (1.0, 1.0), "c": (1.0, 1.0)}), resamples=200)["degenerate"] is True
    assert ls.vendor_row(rows({"a": (0.3, 0.6), "b": (0.4, 0.5), "c": (0.2, 0.7)}), resamples=200)["degenerate"] is False
    assert "degenerate" not in ls.vendor_row([])


def test_a_duplicate_row_makes_the_pair_unknown():
    data = _pair("a", 0, False, False) + _pair("a", 1, False, False)
    data.append({"site": "a", "round": 1, "arm": "F", "challenged": True, "order": "SF"})
    sites, unknown = ls.pairs_from(data)
    assert unknown == 1 and sites == {"a": [(False, False)]}


# --- first-visitor design: Newcombe-Wilson difference, gate G0, arm readings (px-arms plan section 3) ---

def test_newcombe_diff_matches_the_published_example():
    # Newcombe 1998, Stat Med 17:873, 56/70 against 48/80, method 10: 0.2000 (0.0524, 0.3339)
    d, lo, hi = ls.newcombe_diff(56, 70, 48, 80)
    assert d == pytest.approx(0.2) and lo == pytest.approx(0.0524, abs=5e-4) and hi == pytest.approx(0.3339, abs=5e-4)


def test_newcombe_diff_wider_at_higher_confidence_and_n0_is_uninformative():
    _, lo95, hi95 = ls.newcombe_diff(14, 36, 3, 36)
    _, lo975, hi975 = ls.newcombe_diff(14, 36, 3, 36, conf=0.975)
    assert lo975 < lo95 < hi95 < hi975
    assert ls.newcombe_diff(0, 0, 3, 36)[1:] == (-1.0, 1.0)
    assert ls.newcombe_diff(0, 0, 0, 0) == (0.0, -1.0, 1.0)


def test_gate_g0_passes_on_a_clear_gap_and_fails_on_none():
    g = ls.gate_g0(14, 36, 3, 36)
    assert g["passed"] and g["lo"] > 0 and g["d"] == pytest.approx(11 / 36)
    assert not ls.gate_g0(5, 36, 5, 36)["passed"]


def test_gate_g0_lo_exactly_zero_is_not_passed(monkeypatch):
    monkeypatch.setattr(ls, "newcombe_diff", lambda *a, **k: (0.3, 0.0, 0.6))
    assert ls.gate_g0(1, 2, 3, 4)["passed"] is False
    monkeypatch.setattr(ls, "newcombe_diff", lambda *a, **k: (0.3, 1e-9, 0.6))
    assert ls.gate_g0(1, 2, 3, 4)["passed"] is True


def test_gate_g0_with_no_visits_is_not_passed():
    assert ls.gate_g0(0, 0, 0, 0)["passed"] is False


def counts(**over):
    base = {"S": (3, 36, 0), "F": (14, 36, 0), "N": (13, 36, 0), "S2": (3, 36, 1)}
    base.update(over)
    return base


def test_arm_diffs_gate_failure_gives_no_arm_reading():
    c = counts(F=(4, 36, 0))
    out = ls.arm_diffs(c, ls.gate_g0(4, 36, 3, 36))
    assert out == {"conclusion": "gap not reproduced"}


def test_arm_diffs_reads_part_and_all():
    c = counts()
    out = ls.arm_diffs(c, ls.gate_g0(14, 36, 3, 36))
    assert out["N"]["carries_part"] is False and out["N"]["carries_all"] is False  # N is as challenged as F
    s2 = out["S2"]  # S2 looks like S: it carries the gap
    assert s2["carries_part"] is True and s2["d"] == pytest.approx(11 / 36) and s2["lo"] > 0
    assert s2["carries_all"] is True and s2["equiv_hi"] <= 0.15
    assert ls.arm_diffs(counts(S2=(8, 36, 0)), ls.gate_g0(14, 36, 3, 36))["S2"]["carries_all"] is False  # 0.14 apart: not inside


def test_arm_diffs_carries_all_needs_a_tight_equivalence_interval():
    c = {"S": (300, 1000, 0), "F": (700, 1000, 0), "N": (300, 1000, 0), "S2": (500, 1000, 0)}
    out = ls.arm_diffs(c, ls.gate_g0(700, 1000, 300, 1000))
    assert out["N"]["carries_part"] and out["N"]["carries_all"]
    assert out["S2"]["carries_part"] and not out["S2"]["carries_all"]  # halfway: equivalent to neither


def test_arm_diffs_uses_97_5_percent_for_the_primary():
    c = counts()
    d = ls.arm_diffs(c, ls.gate_g0(14, 36, 3, 36))["S2"]
    _, lo, hi = ls.newcombe_diff(14, 36, 3, 36, conf=0.975)
    assert (d["lo"], d["hi"]) == (lo, hi)


def test_arm_diffs_an_arm_with_over_ten_percent_unknown_is_unmeasured():
    c = counts(N=(10, 30, 6))  # 6 / 36 > 0.10
    out = ls.arm_diffs(c, ls.gate_g0(14, 36, 3, 36))
    assert out["N"] == "UNMEASURED" and isinstance(out["S2"], dict)


def test_arm_diffs_exactly_ten_percent_unknown_is_measured_and_no_visits_is_not():
    c = counts(N=(10, 36, 4))  # 4 / 40 == 0.10: not above
    assert isinstance(ls.arm_diffs(c, ls.gate_g0(14, 36, 3, 36))["N"], dict)
    c = counts(N=(0, 0, 0))
    assert ls.arm_diffs(c, ls.gate_g0(14, 36, 3, 36))["N"] == "UNMEASURED"


def test_arm_diffs_unmeasured_baseline_makes_everything_unmeasured():
    c = counts(S=(3, 30, 6))
    assert ls.arm_diffs(c, ls.gate_g0(14, 36, 3, 30)) == {"conclusion": "UNMEASURED"}


def test_arm_diffs_skips_an_arm_that_was_not_run():
    c = {"S": (3, 36, 0), "F": (14, 36, 0), "N": (13, 36, 0)}
    assert set(ls.arm_diffs(c, ls.gate_g0(14, 36, 3, 36))) == {"N"}

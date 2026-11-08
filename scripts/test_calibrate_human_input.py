"""calibrate_human_input.py recovers known parameters from synthetic fixtures.

The fixtures mimic the two public datasets' column layouts (KeyRecs free-text.csv,
Bogazici mouse sessions) with values drawn from a KNOWN lognormal, so a fit that
measures nothing (e.g. returns defaults) fails here.
"""
import csv
import math
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import calibrate_human_input as cal  # noqa: E402

HEADER = ["participant", "session", "key1", "key2", "DU.key1.key1", "DD.key1.key2",
          "DU.key1.key2", "UD.key1.key2", "UU.key1.key2 ", ""]


def draw(rng, median, sigma):
    return median * math.exp(sigma * rng.gauss(0, 1))


def test_fit_lognormal_recovers_known():
    rng = random.Random(1)
    xs = [draw(rng, 95.0, 0.30) for _ in range(20000)]
    mu, sigma = cal.fit_lognormal(xs)
    assert abs(math.exp(mu) - 95.0) / 95.0 < 0.02
    assert abs(sigma - 0.30) < 0.01


def test_lognormal_from_mean_sd_round_trips():
    # a lognormal with median 100 and sigma 0.4 has this mean and sd
    sigma = 0.4
    mean = 100 * math.exp(sigma**2 / 2)
    sd = mean * math.sqrt(math.exp(sigma**2) - 1)
    mu2, s2 = cal.lognormal_from_mean_sd(mean, sd)
    assert abs(math.exp(mu2) - 100) < 1e-6
    assert abs(s2 - sigma) < 1e-9


def test_quantile_interpolates():
    assert cal.quantile([1, 2, 3, 4, 5], 0.5) == 3
    assert cal.quantile([0, 10], 0.25) == 2.5


def write_keyrecs(path, rng, n, dwell=(0.095, 0.30), flight=(0.06, 0.45), p_roll=0.20):
    """Letter pairs; UD<0 (overlap) with probability p_roll, as KeyRecs encodes rollover."""
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for i in range(n):
            d1 = draw(rng, *dwell)
            dd = d1 + draw(rng, *flight)  # key 2 down after key 1 up, so no overlap
            if rng.random() < p_roll:
                dd = rng.uniform(0.5, 0.9) * d1  # next key down before key1 up
            ud = dd - d1
            w.writerow(["p001", 1, "e", "t", round(d1, 4), round(dd, 4), round(dd + 0.09, 4),
                        round(ud, 4), round(ud + 0.09 - d1, 4), ""])


def test_keyrecs_recovers_dwell_flight_and_rollover(tmp_path):
    rng = random.Random(2)
    p = tmp_path / "free-text.csv"
    write_keyrecs(p, rng, 30000)
    out = cal.keyrecs_params(p)
    assert abs(out["dwell"]["median_ms"] - 95) / 95 < 0.03
    assert abs(out["dwell"]["sigma"] - 0.30) < 0.02
    assert abs(out["rollover"]["chance"] - 0.20) < 0.02
    assert out["rollover"]["n"] > 1000
    assert out["dwell"]["n"] == 30000


def test_keyrecs_digraph_table_needs_min_count(tmp_path):
    rng = random.Random(3)
    p = tmp_path / "free-text.csv"
    write_keyrecs(p, rng, 500)  # only the pair "et", 500 times
    out = cal.keyrecs_params(p, digraph_min_n=200)
    assert list(out["digraph"]["pairs"]) == ["et"]
    out = cal.keyrecs_params(p, digraph_min_n=501)
    assert "pairs" not in out["digraph"]


def test_keyrecs_backspace_runs_give_typo_rate(tmp_path):
    p = tmp_path / "free-text.csv"
    with open(p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        # 100 letter->letter rows, then 2 correction runs of lengths 1 and 2
        for _ in range(100):
            w.writerow(["p", 1, "a", "b", 0.09, 0.2, 0.29, 0.11, 0.2, ""])
        w.writerow(["p", 1, "a", "Backspace", 0.09, 0.5, 0.6, 0.4, 0.5, ""])
        w.writerow(["p", 1, "Backspace", "b", 0.09, 0.2, 0.3, 0.1, 0.2, ""])
        w.writerow(["p", 1, "a", "Backspace", 0.09, 0.6, 0.7, 0.5, 0.6, ""])
        w.writerow(["p", 1, "Backspace", "Backspace", 0.08, 0.15, 0.2, 0.07, 0.12, ""])
        w.writerow(["p", 1, "Backspace", "b", 0.09, 0.2, 0.3, 0.1, 0.2, ""])
    out = cal.keyrecs_params(p)
    assert out["typos"]["runs"] == 2
    assert abs(out["typos"]["run_len_probs"][0] - 0.5) < 1e-9  # one run of length 1
    assert abs(out["typos"]["run_len_probs"][1] - 0.5) < 1e-9  # one run of length 2


def test_boun_hold_from_press_release(tmp_path):
    rng = random.Random(4)
    p = tmp_path / "session_1"
    t = 0.0
    with open(p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["client timestamp", "button", "state", "x", "y"])
        for _ in range(5000):
            t += 1.0
            w.writerow([round(t, 4), "NoButton", "Move", 10, 10])
            hold = draw(rng, 0.085, 0.30)
            w.writerow([round(t + 0.1, 4), "Left", "Pressed", 10, 10])
            w.writerow([round(t + 0.1 + hold, 4), "Left", "Released", 10, 10])
    out = cal.boun_params([p])
    assert abs(out["click_hold"]["median_ms"] - 85) / 85 < 0.03
    assert abs(out["click_hold"]["sigma"] - 0.30) < 0.02
    assert out["click_hold"]["n"] == 5000


def test_boun_accepts_a_directory(tmp_path):
    (tmp_path / "s").mkdir()
    for i in range(2):
        with open(tmp_path / "s" / f"session_{i}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["client_timestamp", "x", "y", "button", "state", "window"])
            w.writerow([1.0, 1, 1, "Left", "Pressed", "w"])
            w.writerow([1.09, 1, 1, "Left", "Released", "w"])
    out = cal.boun_params([tmp_path / "s"])
    assert out["click_hold"]["n"] == 2

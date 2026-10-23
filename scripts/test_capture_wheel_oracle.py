"""capture_wheel_oracle's pure parts: summary of a page log, and the RED gate."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import capture_wheel_oracle as c  # noqa: E402


def ev(dy, wdy, mode=0, t=0.0):
    return {"dx": 0, "dy": dy, "dz": 0, "mode": mode, "wdx": 0, "wdy": wdy, "trusted": True, "t": t}


def log(wheel, scroll, dpr=1):
    return {"wheel": wheel, "scroll": scroll, "dpr": dpr, "ua": "x"}


REAL = log([ev(100, -120, t=0), ev(100, -120, t=40), ev(100, -120, t=80)],
           [{"y": y, "t": t} for y, t in [(20, 10), (90, 60), (170, 110), (260, 160), (300, 210)]])
CDP = log([ev(300, -120)], [{"y": 300, "t": 5}])


def test_summarize():
    s = c.summarize(REAL)
    assert (s["n_wheel"], s["dy"], s["wdy"], s["modes"], s["trusted"]) == (3, [100, 100, 100], [-120, -120, -120], [0], True)
    assert (s["n_scroll"], s["scroll_ms"], s["final_y"], s["dpr"]) == (5, 200, 300, 1)
    e = c.summarize(log([], []))
    assert (e["n_wheel"], e["n_scroll"], e["scroll_ms"], e["final_y"]) == (0, 0, 0, 0)


def test_red_gate_passes_when_arms_differ():
    assert c.red_gate({"real3": c.summarize(REAL), "cdp300": c.summarize(CDP)}) == []


def test_red_gate_flags_identical_arms():
    s = c.summarize(CDP)
    problems = c.red_gate({"real3": s, "cdp300": s})
    assert len(problems) == 3


def test_red_gate_flags_a_real_arm_that_saw_nothing():
    problems = c.red_gate({"real3": c.summarize(log([], [])), "cdp300": c.summarize(CDP)})
    assert any("no wheel event" in p for p in problems)


def test_compare_accepts_a_fork_that_scrolls_like_the_real_wheel():
    fork = log([ev(100, -120, t=0), ev(100, -120, t=30), ev(100, -120, t=75)],
               [{"y": y, "t": t} for y, t in [(30, 12), (110, 70), (190, 120), (300, 240)]])
    assert c.compare(c.summarize(fork), c.summarize(REAL)) == []


def test_compare_names_each_leaf_a_stock_cdp_wheel_misses():
    problems = c.compare(c.summarize(CDP), c.summarize(REAL))
    assert [p.split(":")[0] for p in problems] == ["n_wheel", "dy", "wdy", "n_scroll", "scroll_ms"]


def test_compare_refuses_an_unanimated_fork_with_the_right_notches():
    fork = log([ev(100, -120), ev(100, -120), ev(100, -120)], [{"y": 300, "t": 5}])
    assert [p.split(":")[0] for p in c.compare(c.summarize(fork), c.summarize(REAL))] == ["n_scroll", "scroll_ms"]

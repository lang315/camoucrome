"""capture_wheel_oracle's pure parts: summary of a page log, and the RED gate."""
import json
import pathlib
import sys

import pytest

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


def test_compare_checks_every_exact_leaf():
    real = c.summarize(REAL)
    for k, v in [("modes", [1]), ("trusted", False), ("final_y", 299), ("dpr", 1.25)]:
        assert [p.split(":")[0] for p in c.compare({**real, k: v}, real)] == [k]


def test_compare_band_edges_are_inclusive():
    real = c.summarize(REAL)  # n_scroll 5, scroll_ms 200
    assert c.compare({**real, "n_scroll": 2.5, "scroll_ms": 300}, real) == []
    assert [p.split(":")[0] for p in c.compare({**real, "scroll_ms": 301}, real)] == ["scroll_ms"]


def test_compare_refuses_a_real_arm_that_saw_nothing():
    empty = c.summarize(log([], []))
    with pytest.raises(ValueError):
        c.compare(empty, empty)


class Host:
    """Stands in for winhost.cdp_eval: answers by whether humanize is on."""

    def __init__(self, on, off, raises=None):
        self.on, self.off, self.raises, self.calls = on, off, raises, []

    def __call__(self, page, **kw):
        self.calls.append(kw)
        if self.raises:
            raise self.raises
        return self.on if json.loads(kw["env"]["CAMOU_CONFIG"])["humanize:enabled"] else self.off


@pytest.fixture
def baseline(monkeypatch, tmp_path):
    out = tmp_path / "wheel.json"
    out.write_text(json.dumps({"arms": {"real3": {"summary": c.summarize(REAL)}}}))
    monkeypatch.setattr(c, "OUT", out)


def test_fork_arms_launches_the_fork_strict_with_humanize_off_then_on(monkeypatch, baseline):
    host = Host(on=REAL, off=CDP)
    monkeypatch.setattr(c.winhost, "cdp_eval", host)
    assert c.fork_arms(r"D:\f\chrome.exe") == 0
    assert [json.loads(k["env"]["CAMOU_CONFIG"]) for k in host.calls] == [
        {"humanize:enabled": False}, {"humanize:enabled": True}]
    assert all(k["exe"] == r"D:\f\chrome.exe" and k["env"]["CAMOU_CONFIG_STRICT"] == "1"
               and k["window_style"] == "Normal" for k in host.calls)


def test_fork_arms_exit_codes(monkeypatch, baseline):
    cases = [(Host(on=CDP, off=CDP), 1),               # humanize on still stock: mismatch
             (Host(on=REAL, off=REAL), 2),             # off reads like the real wheel: RED failed
             (Host(on=REAL, off=log([], [])), 2),      # off saw no wheel event: measured nothing
             (Host(on=REAL, off=CDP, raises=RuntimeError("no CDP result")), 3)]  # UNMEASURED
    for host, rc in cases:
        monkeypatch.setattr(c.winhost, "cdp_eval", host)
        assert c.fork_arms("x") == rc


def test_main_refuses_a_fork_flag_without_exactly_one_exe(monkeypatch):
    monkeypatch.setattr(c, "fork_arms", lambda exe: pytest.fail("ran"))
    monkeypatch.setattr(c.winhost, "powershell", lambda *a, **k: pytest.fail("captured the real wheel"))
    for argv in (["x", "--fork"], ["x", "--fork", "a", "b"]):
        monkeypatch.setattr(c.sys, "argv", argv)
        assert c.main() == 2

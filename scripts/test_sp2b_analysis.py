import unittest

import pytest

import sp2b_analysis as a


def ev(xs, t0=60.0):
    return [{"x": float(x), "y": 0.0, "t": t0 + 17 * i} for i, x in enumerate(xs)]


def burst(xs):
    """Events delivered in one frame: timestamps 0.1 ms apart."""
    return [{"x": float(x), "y": 0.0, "t": 100.0 + 0.1 * i} for i, x in enumerate(xs)]


class TracesPathTest(unittest.TestCase):
    def test_healthy_paths_pass(self):
        for xs in ([202, 299, 335, 363, 406, 418, 420],
                   [300, 381, 399, 398, 422, 422, 420],  # slow start, span 122
                   [342, 380, 400, 415, 420]):  # span 78, the former flake
            ok, note = a.traces_path(ev(xs), 320.0)
            self.assertTrue(ok, xs)
            self.assertEqual(note, "")

    def test_clustered_burst_fails(self):  # RED fixture: coalesced at the target
        ok, note = a.traces_path(ev([420] * 7), 320.0)
        self.assertFalse(ok)
        self.assertIn("n=7", note)
        self.assertIn("t=[", note)

    def test_events_repeating_the_endpoint_over_time_fail(self):  # a broken hook, not a late first sample
        ok, _ = a.traces_path(ev([420] * 7), 320.0)  # 17 ms apart: spread in time, no movement
        self.assertFalse(ok)

    def test_small_cluster_spread_in_time_passes(self):
        # Same shape as the real late-first-sample run (3 events, 17 ms apart, moving
        # to the target): since the time rule it passes. A burst of it still fails.
        ok, note = a.traces_path(ev([412, 416, 420]), 320.0)
        self.assertTrue(ok)
        self.assertIn("time spread", note)
        self.assertFalse(a.traces_path(burst([412, 416, 420]), 320.0)[0])

    def test_burst_at_the_target_fails(self):
        self.assertFalse(a.traces_path(burst([420] * 7), 320.0)[0])

    def test_overshoot_paths_pass(self):  # measured on the host: the path passes the target and returns
        for xs in ([446, 439, 417, 420], [413, 421, 420, 420]):
            ok, note = a.traces_path(ev(xs), 320.0, 33.2)
            self.assertTrue(ok, xs)
            self.assertIn("time spread", note)

    def test_fewer_than_two_events_fails(self):
        self.assertFalse(a.traces_path(ev([420]), 320.0)[0])
        self.assertFalse(a.traces_path([], 320.0)[0])

    def test_bar_is_a_tenth_of_the_path(self):
        self.assertFalse(a.traces_path(ev([388, 420]), 320.0)[0])  # span 32, not above
        self.assertTrue(a.traces_path(ev([387, 420]), 320.0)[0])   # span 33

    def test_time_spread_passes_a_small_span_at_30_fps(self):  # real failing run, -11 zip on the host
        real = [{"x": x, "y": 0.0, "t": t} for x, t in zip([416, 416, 418, 420], [69.9, 89.7, 107.3, 123.3])]
        ok, note = a.traces_path(real, 320.0, 33.2)
        self.assertTrue(ok)
        self.assertIn("time spread", note)
        self.assertIn("t=[69.9", note)

    def test_time_spread_needs_three_increasing_events_over_a_frame(self):
        self.assertFalse(a.traces_path(burst([416, 418, 420, 420]), 320.0, 33.2)[0])  # 0.3 ms range
        two = [{"x": 416.0, "t": 0.0}, {"x": 420.0, "t": 100.0}]
        self.assertFalse(a.traces_path(two, 320.0, 16.7)[0])
        same_t = [{"x": 416.0, "t": 0.0}, {"x": 418.0, "t": 0.0}, {"x": 420.0, "t": 100.0}]
        self.assertFalse(a.traces_path(same_t, 320.0, 16.7)[0])  # not strictly increasing
        short = [{"x": 416.0 + i, "t": 10.0 * i} for i in range(4)]  # 30 ms vs 33.2 ms frame
        self.assertFalse(a.traces_path(short, 320.0, 33.2)[0])

    def test_median_gap(self):
        self.assertEqual(a.median_gap([0, 33, 66, 100]), 33)
        self.assertEqual(a.median_gap([0, 33]), a.DEFAULT_FRAME_MS)
        self.assertEqual(a.median_gap([]), a.DEFAULT_FRAME_MS)


if __name__ == "__main__":
    unittest.main()


def test_evidence_carries_count_positions_and_timestamps():
    ev = a.evidence([{"x": 100.4, "t": 1.04}, {"x": 420.0, "t": 18.5}])
    assert ev == "n=2 x=[100, 420] t=[1.0, 18.5]"
    assert a.evidence([]) == "n=0 x=[] t=[]"


BURST = [{"x": 420.0, "y": 260.0, "t": 100.0 + i * 0.1} for i in range(7)]
SMOOTH = [16.7 * i for i in range(60)]


def test_throttled_frames_make_a_clustered_trace_unmeasured_not_fail():
    assert a.traces_path(BURST, 320.0)[0] is False  # the trace alone is a FAIL
    assert a.throttled(SMOOTH, ["visible"]) is None  # normal frames: stays a FAIL
    assert "median frame interval 300 ms" in a.throttled([300.0 * i for i in range(12)], ["visible"])
    assert "not visible" in a.throttled(SMOOTH, ["visible", "hidden"])
    assert "only 2 animation frames" in a.throttled([0.0, 16.7], ["visible"])


def _main_with(monkeypatch, capsys, humanized_events, frames):
    import verify_sp2b as v
    one = [{"x": 420.0, "y": 260.0, "t": 1.0}]
    runs = iter([(one, None, ([], [])), (humanized_events, None, frames)])
    monkeypatch.setattr(v, "run", lambda config: next(runs))
    with pytest.raises(SystemExit) as e:
        v.main()
    return e.value.code, capsys.readouterr().out


def test_main_clustered_trace_on_throttled_frames_is_unmeasured(monkeypatch, capsys):
    rc, out = _main_with(monkeypatch, capsys, BURST, ([300.0 * i for i in range(12)], ["visible"]))
    assert rc == 3
    assert "UNMEASURED humanize session: frames throttled, median frame interval 300 ms" in out
    assert "FAIL" not in out


def test_main_the_same_trace_on_normal_frames_still_fails(monkeypatch, capsys):
    rc, out = _main_with(monkeypatch, capsys, BURST, (SMOOTH, ["visible"]))
    assert rc == 1
    assert "FAIL  3 humanize:enabled events trace the path" in out
    assert "UNMEASURED" not in out

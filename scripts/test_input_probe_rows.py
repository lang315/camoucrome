"""Tests of input_probe_rows: each row has a good log (a real-input shape), a planted bad one that must FAIL (RED), and
the presence guard."""
import unittest

import input_probe_rows as R

F = 16.7


def ev(t, ts, x=100.0, y=100.0, now=None, **kw):
    e = {"n": 0, "t": t, "ts": ts, "now": ts if now is None else now, "x": x, "y": y, "b": 0, "bs": 0, "d": 0, "rep": None,
         "key": None, "rt": None, "cs": -1, "ps": -1, "tr": True, "pt": "mouse"}
    e.update(kw)
    return e


def log(events, dpr=1.0, secure=True, coalesced=True, oh=600):
    ticks = [[i * F, i * F] for i in range(200)]
    for i, e in enumerate(events):
        e["n"] = i
    return {"meta": {"dpr": dpr, "iw": 800, "ih": 600, "ow": 800, "oh": oh, "secure": secure, "coalesced_fn": coalesced},
            "ev": events, "raf": ticks}


def many(make, n=R.MIN_N):
    return [make(i) for i in range(n)]


def real_moves(n=60, phase=1.0, per_frame=1):
    """One dispatch per frame, `phase` ms before the tick, whole-frame gaps."""
    out = []
    for i in range(1, n + 1):
        for _ in range(per_frame):
            out.append(ev("mousemove", i * F - 5, x=float(i * 3), y=50.0, now=i * F - phase))
    return out


def burst_moves(n=60):
    """RED: every move at the same instant, several per frame."""
    return [ev("mousemove", 100.0, x=float(i), y=50.0, now=100.0) for i in range(n)]


class I1(unittest.TestCase):
    def test_real(self):
        m = R.i1(log(real_moves()))
        self.assertEqual(m["multi"], 0)
        self.assertEqual(m["aligned"], 1.0)

    def test_red_zero_interval_fails(self):
        ctl = [log(real_moves(phase=p)) for p in (0.5, 1.0, 1.5, 0.8)]
        bad = many(lambda i: log(burst_moves()))
        v = R.judge("I1", ctl, bad)
        self.assertEqual(R.row_verdict(v), "FAIL")
        self.assertEqual(v["multi"][0], "FAIL")

    def test_real_passes(self):
        ctl = [log(real_moves(phase=p)) for p in (0.5, 1.0, 1.5, 0.8)]
        self.assertEqual(R.row_verdict(R.judge("I1", ctl, many(lambda i: log(real_moves(phase=1.2))))), "PASS")


class I1Covered(unittest.TestCase):
    """2026-11-22 P0b: page.html once kept only the last 6000 ticks; moves older than the first tick were paired with a far
    later one, so `aligned` read the covered share (.42), not the browser."""

    def ring_log(self, drop):
        """real_moves(), but the tick log lost its first `drop` ticks (the old ring)"""
        lg = log(real_moves())
        lg["raf"] = lg["raf"][drop:]
        return lg

    def test_full_ring_is_covered(self):
        m = R.i1(log(real_moves()))
        self.assertEqual(m["covered"], 1.0)
        self.assertEqual(m["aligned"], 1.0)

    def test_old_ring_judges_only_covered_moves(self):
        m = R.i1(self.ring_log(30))      # ticks 30.. : the moves before them have no tick
        self.assertAlmostEqual(m["covered"], 0.5, delta=0.05)
        self.assertEqual(m["aligned"], 1.0)   # among the covered moves, as P0b found

    def test_old_ring_is_unmeasured_not_fail(self):
        ctl = [log(real_moves(phase=p)) for p in (0.5, 1.0, 1.5, 0.8)]
        v = R.judge("I1", ctl, many(lambda i: self.ring_log(30)))
        self.assertEqual(R.row_verdict(v), "UNMEASURED")
        self.assertIn("covered", v["_"][1])

    def test_covered_ring_passes(self):
        ctl = [log(real_moves(phase=p)) for p in (0.5, 1.0, 1.5, 0.8)]
        self.assertEqual(R.row_verdict(R.judge("I1", ctl, many(lambda i: self.ring_log(2)))), "PASS")


class I2b(unittest.TestCase):
    """spacing of the getCoalescedEvents() timeStamps inside one pointermove"""

    def pm(self, step, n=30, k=4, sd=0.0):
        out = []
        for i in range(n):
            base = i * F * 10
            out.append(ev("pointermove", base, cs=k, ps=1,
                          cts=[base - (k - 1 - j) * step + ((-1) ** j) * sd for j in range(k)]))
        return out

    def groups(self):
        return {"ctl125": [log(self.pm(8.0, sd=0.1)) for _ in range(4)], "ctl1000": [log(self.pm(1.0, k=17, sd=0.05)) for _ in range(4)]}

    def test_metrics(self):
        m = R.i2b(log(self.pm(8.0)))
        self.assertAlmostEqual(m["spacing_med"], 8.0)
        self.assertEqual(m["spacing_n"], 90)

    def test_matching_rate_passes(self):
        self.assertEqual(R.row_verdict(R.judge("I2b", self.groups(), many(lambda i: log(self.pm(8.1, sd=0.1))))), "PASS")
        self.assertEqual(R.row_verdict(R.judge("I2b", self.groups(), many(lambda i: log(self.pm(1.05, k=17, sd=0.05))))), "PASS")

    def shaped(self, core, n=200, tail=0.1, k=2):
        """one gap per pointermove: `core` of them 8.0 +-0.1, `tail` of them 4 or 12, the rest 8 +-1.5 (the control's shape: a peak and a tail)"""
        out = []
        for i in range(n):
            f = (i * 0.618) % 1.0
            g = 8.0 + (0.1 if i % 2 else -0.1) if f < core else (4.0 + (i % 2) * 8.0 if f < core + tail else 8.0 + (1.5 if i % 2 else -1.5))
            out.append(ev("pointermove", i * 100.0, cs=2, ps=1, cts=[i * 100.0 - g, i * 100.0]))
        return out

    def test_gap_shape_metrics(self):
        m = R.i2b(log(self.shaped(0.6)))
        self.assertAlmostEqual(m["core_share"], 0.6, delta=0.05)
        self.assertAlmostEqual(m["tail_share"], 0.1, delta=0.05)

    def test_red_flat_spread_fails_the_shape(self):
        """same median and sd as the control, but no peak: the uniform +-3 ms jitter of option B"""
        groups = {"ctl125": [log(self.shaped(0.6)) for _ in range(4)]}
        flat = many(lambda i: log([ev("pointermove", j * 100.0, cs=2, ps=1, cts=[j * 100.0 - (8.0 + ((j * 0.618) % 1.0 - 0.5) * 6), j * 100.0]) for j in range(200)]))
        v = R.judge("I2b", groups, flat)
        self.assertEqual(v["core_share"][0], "FAIL")
        self.assertEqual(R.row_verdict(v), "FAIL")
        self.assertEqual(R.row_verdict(R.judge("I2b", groups, many(lambda i: log(self.shaped(0.6))))), "PASS")

    def test_too_few_gaps_are_not_a_verdict(self):
        few = self.pm(8.0, n=R.MIN_GAPS // 3 - 1)
        self.assertIsNone(R.i2b(log(few)))
        self.assertEqual(R.row_verdict(R.judge("I2b", self.groups(), many(lambda i: log(few)))), "UNMEASURED")

    def test_red_equal_stamps_fail(self):
        v = R.judge("I2b", self.groups(), many(lambda i: log(self.pm(0.0))))
        self.assertEqual(R.row_verdict(v), "FAIL")

    def test_red_wrong_rate_fails(self):
        self.assertEqual(R.row_verdict(R.judge("I2b", self.groups(), many(lambda i: log(self.pm(4.0))))), "FAIL")

    def test_red_one_sample_per_frame_is_not_pass(self):
        single = [ev("pointermove", i * F, cs=1, ps=0, cts=[i * F]) for i in range(30)]
        self.assertNotEqual(R.row_verdict(R.judge("I2b", self.groups(), many(lambda i: log(single)))), "PASS")


class I2(unittest.TestCase):
    def pm(self, cs, n=30):
        return [ev("pointermove", i * F, cs=cs, ps=0) for i in range(n)]

    def test_red_single_sample_fails(self):
        ctl = [log(self.pm(c)) for c in (8, 16, 9, 12)]
        v = R.judge("I2", ctl, many(lambda i: log(self.pm(1))))
        self.assertEqual(R.row_verdict(v), "FAIL")

    def test_coalesced_max_alone_fails(self):
        """control max 3 (125 Hz) and 17 (1000 Hz) against an arm that never coalesces: the metric itself must FAIL"""
        groups = {"ctl125": [log(self.pm(3)) for _ in range(4)], "ctl1000": [log(self.pm(17)) for _ in range(4)]}
        v = R.judge("I2", groups, many(lambda i: log(self.pm(1))))
        self.assertEqual(v["coalesced_max"][0], "FAIL")
        self.assertEqual(R.judge("I2", groups, many(lambda i: log(self.pm(3))))["coalesced_max"][0], "PASS")

    def test_missing_function_is_unmeasured(self):
        v = R.judge("I2", many(lambda i: log(self.pm(8), coalesced=False)), many(lambda i: log(self.pm(8))))
        self.assertEqual(R.row_verdict(v), "UNMEASURED")


class I3(unittest.TestCase):
    def test_grid(self):
        # real: whole device pixels, a fixed y offset of .25 device px
        on = [ev("pointermove", i, x=i / 1.25, y=(i + 0.25) / 1.25) for i in range(1, 40)]
        off = [ev("pointermove", i, x=i * 0.9 + 0.13, y=i * 0.7 + 0.31) for i in range(1, 40)]
        self.assertLess(R.i3(log(on, dpr=1.25))["off_share"], 0.01)
        ctl = [log(on, dpr=1.25)] * 4
        self.assertEqual(R.row_verdict(R.judge("I3", ctl, [log(off, dpr=1.25)] * 4)), "FAIL")
        self.assertEqual(R.row_verdict(R.judge("I3", ctl, ctl)), "PASS")

    def test_modal_fraction_must_be_the_controls(self):
        """host H2 control: view origin (8, 87) at dsf 1.25 -> x 0.00, y 0.25. A lattice with y 0 (origin-blind snap) is ON a grid
        and passes off_share, but is not the control's: FAIL on fy. A lattice at the control's fractions PASSes."""
        ctl = [log([ev("pointermove", i, x=i / 1.25, y=(i + 0.25) / 1.25) for i in range(1, 40)], dpr=1.25)] * 4
        blind = [log([ev("pointermove", i, x=i / 1.25, y=i / 1.25) for i in range(1, 40)], dpr=1.25)] * 4
        m = R.i3(ctl[0])
        self.assertAlmostEqual(m["fx"], 0.0, places=3)
        self.assertAlmostEqual(m["fy"], 0.25, places=3)
        v = R.judge("I3", ctl, blind)
        self.assertEqual(v["off_share"][0], "PASS")
        self.assertEqual(v["fy"][0], "FAIL")
        self.assertEqual(v["fx"][0], "PASS")
        self.assertEqual(R.row_verdict(v), "FAIL")
        self.assertEqual(R.row_verdict(R.judge("I3", ctl, ctl)), "PASS")

    def test_an_infobar_makes_the_row_unmeasured(self):
        """outerHeight - innerHeight is the chrome above the page; an arm with another one has another view origin"""
        on = [ev("pointermove", i, x=i / 1.25, y=(i + 0.25) / 1.25) for i in range(1, 40)]
        ctl = [log(on, dpr=1.25, oh=600)] * 4
        v = R.judge("I3", ctl, [log(on, dpr=1.25, oh=640)] * 4)
        self.assertEqual(R.row_verdict(v), "UNMEASURED")
        self.assertIn("infobar", v["_"][1])
        self.assertEqual(R.row_verdict(R.judge("I3", ctl, ctl)), "PASS")

    def test_zero_control_fraction_says_the_origin_is_moot(self):
        zero = [log([ev("pointermove", i, x=i / 1.25, y=i / 1.25) for i in range(1, 40)], dpr=1.25)] * 4
        v = R.judge("I3", zero, zero)
        self.assertIn("moot", v["fy"][2])
        self.assertEqual(R.row_verdict(v), "PASS")

    def test_dpr_one_is_unmeasured(self):
        on = [ev("pointermove", i, x=float(i), y=float(i)) for i in range(1, 40)]
        self.assertEqual(R.row_verdict(R.judge("I3", [log(on, dpr=1.0)] * 4, [log(on, dpr=1.0)] * 4)), "UNMEASURED")


class I4(unittest.TestCase):
    good = ["pointerout", "pointerleave", "mouseout", "mouseleave"]

    def exit(self, types, x=-5.0, rt="null"):
        return [ev("mousemove", 0.0, x=2.0, y=50.0)] + [ev(t, 1.0, x=x, y=50.0, rt=rt) for t in types]

    def test_outside_coordinates_fail(self):
        ctl = [log(self.exit(self.good, x=0.0))] * 4
        # control reports no coordinate outside; the arm sends a move at x=-5
        bad = log(self.exit(self.good, x=0.0) + [ev("mousemove", 2.0, x=-5.0, y=50.0)])  # a move outside, as no real pointer sends
        self.assertEqual(R.judge("I4", ctl, [bad] * 4)["outside"][0], "FAIL")

    def test_exit_far_past_the_edge_fails(self):
        ctl = [log(self.exit(self.good, x=-3.0))] * 4
        self.assertEqual(R.judge("I4", ctl, [log(self.exit(self.good, x=-60.0))] * 4)["exit_depth"][0], "FAIL")
        self.assertEqual(R.judge("I4", ctl, [log(self.exit(self.good, x=-5.0))] * 4)["exit_depth"][0], "PASS")

    def test_order(self):
        ctl = [log(self.exit(self.good, x=0.0))] * 4
        bad = log(self.exit(["mouseout", "mouseleave"], x=0.0))
        self.assertEqual(R.judge("I4", ctl, [bad] * 4)["exit_sig"][0], "FAIL")
        self.assertEqual(R.judge("I4", ctl, [log(self.exit(self.good, x=0.0))] * 4)["exit_sig"][0], "PASS")


class I5(unittest.TestCase):
    def clicks(self, details, right_order, dbl):
        out = []
        for d in details:
            out += [ev("mousedown", 0, d=d), ev("mouseup", 1, d=d), ev("click", 1, d=d)]
        if dbl:
            out.append(ev("dblclick", 2, d=2))
        for t in right_order:
            out.append(ev(t, 3, b=2))
        return log(out)

    def test_red(self):
        ctl = [self.clicks([1, 2, 3], ["mousedown", "mouseup", "contextmenu"], True)] * 4
        for bad in (self.clicks([1, 1, 1], ["mousedown", "mouseup", "contextmenu"], True),   # detail always 1
                    self.clicks([1, 2, 3], ["mousedown", "mouseup"], True),                  # no contextmenu
                    self.clicks([1, 2, 3], ["mousedown", "contextmenu", "mouseup"], True),   # other order
                    self.clicks([1, 2, 3], ["mousedown", "mouseup", "contextmenu"], False)):  # no dblclick
            self.assertEqual(R.row_verdict(R.judge("I5", ctl, [bad] * 4)), "FAIL")
        self.assertEqual(R.row_verdict(R.judge("I5", ctl, ctl)), "PASS")

    def test_no_click_at_all_is_unmeasured(self):
        only_move = log([ev("mousemove", i * 10.0) for i in range(10)])
        self.assertEqual(R.row_verdict(R.judge("I5", [only_move] * 4, [only_move] * 4)), "UNMEASURED")


class I6(unittest.TestCase):
    def keys(self, delay, step, n=20, flag=True):
        out = [ev("keydown", 0.0, rep=False, key="a")]
        for i in range(n):
            out.append(ev("keydown", delay + i * step, rep=flag, key="a"))
        return log(out)

    def test_red(self):
        ctl = [self.keys(500, 33), self.keys(500, 34), self.keys(501, 33), self.keys(500, 33)]
        self.assertEqual(R.row_verdict(R.judge("I6", ctl, ctl)), "PASS")
        self.assertEqual(R.row_verdict(R.judge("I6", ctl, [self.keys(500, 33, flag=False)] * 4)), "FAIL")   # no repeat flag

    def test_key_timing_is_info_not_judged(self):
        """the timing is the harness's own in every arm: an arm with no initial delay still PASSes, its numbers are INFO"""
        ctl = [self.keys(500, 33)] * 4
        v = R.judge("I6", ctl, [self.keys(30, 5)] * 4)
        self.assertEqual(R.row_verdict(v), "PASS")
        self.assertEqual(v["delay"][0], "INFO")


class Presence(unittest.TestCase):
    def test_slow_raf_is_unmeasured(self):
        slow = log(real_moves())
        slow["raf"] = [[i * 31.3, i * 31.3] for i in range(100)]
        self.assertEqual(R.row_verdict(R.judge("I1", [slow] * 4, [slow] * 4)), "UNMEASURED")

    def test_nothing_arrived(self):
        self.assertEqual(R.row_verdict(R.judge("I4", [log([])] * 4, [log([])] * 4)), "UNMEASURED")

    def test_insecure(self):
        lg = log([ev("mousemove", 1.0)], secure=False)
        self.assertEqual(R.row_verdict(R.judge("I3", [lg] * 4, [lg] * 4)), "UNMEASURED")


class Judging(unittest.TestCase):
    def pm(self, cs, n=30):
        return [ev("pointermove", i * F, cs=cs, ps=0) for i in range(n)]

    def test_min_n(self):
        three = [log(self.pm(8))] * 3
        v = R.judge("I2", three, [log(self.pm(1))] * 4)
        self.assertEqual(R.row_verdict(v), "UNMEASURED")
        self.assertIn("need 4", v["multi"][2])

    def test_runs_without_the_metric_are_counted(self):
        v, note = R.metric_verdict("num", 1.0, [3.0, 3.0, None, None, 3.0], [1.0] * 4)
        self.assertEqual(v, "UNMEASURED")
        self.assertIn("2 run(s) lack the metric", note)

    def test_rates_are_judged_apart_and_an_arm_matching_one_passes(self):
        groups = {"ctl125": [log(self.pm(3)) for _ in range(4)], "ctl1000": [log(self.pm(17)) for _ in range(4)]}
        v = R.judge("I2", groups, [log(self.pm(17)) for _ in range(4)])
        self.assertEqual(v["coalesced_max"][0], "PASS")
        self.assertIn("ctl125: FAIL", v["coalesced_max"][2])
        self.assertIn("ctl1000: PASS", v["coalesced_max"][2])

    def test_mixed_rates_do_not_pass_the_row(self):
        """an arm with the coalesced count of 1000 Hz but the coalesced SHARE of 125 Hz matches one rate per metric and no
        real mouse: each metric passes against some group, the row must FAIL"""
        def pms(cs, share, n=40):   # `share` of the moves carry cs samples, the rest 1
            k = int(n * share)
            return [ev("pointermove", i * F, cs=cs if i < k else 1, ps=0) for i in range(n)]
        groups = {"ctl125": [log(pms(3, 0.9)) for _ in range(4)], "ctl1000": [log(pms(17, 0.2)) for _ in range(4)]}
        mix = [log(pms(17, 0.9)) for _ in range(4)]       # max 17 as ctl1000, share .9 as ctl125
        v = R.judge("I2", groups, mix)
        self.assertEqual(v["coalesced_max"][0], "PASS")
        self.assertEqual(v["multi"][0], "PASS")
        self.assertEqual(R.row_verdict(v), "FAIL")
        # one consistent rate passes
        self.assertEqual(R.row_verdict(R.judge("I2", groups, [log(pms(3, 0.9)) for _ in range(4)])), "PASS")
        self.assertEqual(R.row_verdict(R.judge("I2", groups, [log(pms(17, 0.2)) for _ in range(4)])), "PASS")

    def test_a_wide_control_share_cannot_fail(self):
        v, note = R.metric_verdict("share", 0.1, [0.0, 0.3, 0.6, 0.9], [0.99] * 4)
        self.assertEqual(v, "UNMEASURED")
        self.assertIn("no arm could FAIL", note)

    def test_range_is_widened_by_a_fraction_not_the_whole_range(self):
        ctl = [10.0, 20.0, 15.0, 12.0]            # range 10, widening max(floor 1, 2.5)
        self.assertEqual(R.metric_verdict("num", 1.0, ctl, [22.0] * 4)[0], "PASS")
        self.assertEqual(R.metric_verdict("num", 1.0, ctl, [23.0] * 4)[0], "FAIL")   # the old rule allowed up to 30


class I7(unittest.TestCase):
    """pointerrawupdate: a real mouse delivers each report as it arrives, so now - timeStamp is a small constant-ish latency;
    a burst forwarded back to back shows several events at one `now` whose timeStamps lie 8 ms apart (PR #244 review item 1)."""

    def raw(self, n=60, burst=1, lat=1.0, step=8.0, jitter=0.1):
        out = []
        for i in range(n):
            base = i * step * burst
            for j in range(burst):
                ts = base + j * step
                now = base + (burst - 1) * step + lat if burst > 1 else ts + lat + ((-1) ** i) * jitter
                out.append(ev("pointerrawupdate", ts, now=now))
        return out

    def groups(self):
        return {"ctl125": [log(self.raw(jitter=j)) for j in (0.1, 0.15, 0.2, 0.12)]}

    def test_metrics(self):
        m = R.i7(log(self.raw(burst=2)))
        self.assertEqual(m["pairs"], 60)
        self.assertGreater(m["lat_sd"], 3.0)
        self.assertEqual(R.i7(log(self.raw()))["pairs"], 0)

    def test_real_time_passes(self):
        v = R.judge("I7", self.groups(), many(lambda i: log(self.raw(jitter=0.13))))
        self.assertEqual(R.row_verdict(v), "PASS")

    def test_red_back_to_back_burst_fails(self):
        v = R.judge("I7", self.groups(), many(lambda i: log(self.raw(burst=2))))
        self.assertEqual(R.row_verdict(v), "FAIL")
        self.assertEqual(v["pair_share"][0], "FAIL")

    def test_a_handful_of_raw_events_is_not_a_verdict(self):
        """two raw events must not decide the row: a minimum count"""
        v = R.judge("I7", self.groups(), many(lambda i: log(self.raw(n=R.MIN_RAW - 1))))
        self.assertEqual(R.row_verdict(v), "UNMEASURED")

    def test_no_raw_events_is_unmeasured(self):
        v = R.judge("I7", self.groups(), many(lambda i: log([ev("pointermove", i * 8.0, cs=1, ps=0) for i in range(30)])))
        self.assertEqual(R.row_verdict(v), "UNMEASURED")


class I2c(unittest.TestCase):
    """quantization of the coalesced stamps (INFO) and repeated positions inside the coalesced lists"""

    def pm(self, gap, xy_step=1.0, n=20, k=4):
        out = []
        for i in range(n):
            base = i * 100.0
            out.append(ev("pointermove", base, cs=k, ps=0, cts=[base - (k - 1 - j) * gap for j in range(k)],
                          cxy=[[float(i * 10 + j * xy_step), 5.0] for j in range(k)]))
        return out

    def test_whole_ms_share(self):
        self.assertEqual(R.i2c(log(self.pm(8.0)))["whole_share"], 1.0)
        self.assertEqual(R.i2c(log(self.pm(8.37)))["whole_share"], 0.0)

    def test_repeat_counts_neighbours_on_one_point(self):
        m = R.i2c(log(self.pm(8.0, xy_step=0.0)))
        self.assertEqual(m["repeat"], 20 * 3)
        self.assertEqual(R.i2c(log(self.pm(8.0)))["repeat"], 0)

    def test_red_repeats_fail(self):
        groups = {"ctl125": [log(self.pm(8.0)) for _ in range(4)]}
        v = R.judge("I2c", groups, many(lambda i: log(self.pm(8.0, xy_step=0.0))))
        self.assertEqual(v["repeat_share"][0], "FAIL")
        self.assertEqual(R.row_verdict(v), "FAIL")
        self.assertEqual(v["whole_share"][0], "PASS")

    def quant(self, share, n=200):
        """gaps of one coalesced pair per move: `share` of them whole ms (8.0), the rest 8.37"""
        return [ev("pointermove", i * 100.0, cs=2, ps=0, cts=[i * 100.0 - (8.0 if (i * 0.618) % 1.0 < share else 8.37), i * 100.0],
                   cxy=[[float(i), 1.0], [float(i) + 1, 1.0]]) for i in range(n)]

    def test_red_continuous_stamps_fail_against_a_quantized_control(self):
        """the control's stamps are partly whole ms (host: .17-.28); ours continuous (.10 is chance for the window)"""
        groups = {"ctl125": [log(self.quant(0.25)) for _ in range(4)]}
        v = R.judge("I2c", groups, many(lambda i: log(self.quant(0.0))))
        self.assertEqual(v["whole_share"][0], "FAIL")
        self.assertEqual(R.row_verdict(v), "FAIL")
        self.assertEqual(R.row_verdict(R.judge("I2c", groups, many(lambda i: log(self.quant(0.25))))), "PASS")

    def test_clean_passes(self):
        groups = {"ctl125": [log(self.pm(8.0)) for _ in range(4)]}
        self.assertEqual(R.row_verdict(R.judge("I2c", groups, many(lambda i: log(self.pm(8.0))))), "PASS")

    def test_page_without_positions_is_unmeasured(self):
        lg = lambda: log([ev("pointermove", i * 100.0, cs=2, ps=0, cts=[i * 100.0 - 8, i * 100.0]) for i in range(20)])
        groups = {"ctl125": [lg() for _ in range(4)]}
        self.assertEqual(R.row_verdict(R.judge("I2c", groups, many(lambda i: lg()))), "UNMEASURED")


class PooledBand(unittest.TestCase):
    """I2b / I2c metrics are judged on the pooled difference with a run-level interval, not on the control's range in the same
    session. Per-run values are the host's (-15 = s1, a second session = s2, 2026-11-22, 6 runs each, 125 Hz control)."""
    CTL1 = {"core_share": [.571, .574, .533, .626, .629, .624], "whole_share": [.278, .291, .266, .276, .290, .278],
            "spacing_sd": [1.143, 1.356, 1.340, 1.092, 1.305, 1.089], "tail_share": [.069, .143, .111, .103, .139, .098]}
    CTL2 = {"core_share": [.603, .563, .607, .605, .608, .594], "whole_share": [.273, .249, .258, .259, .233, .262],
            "spacing_sd": [1.053, 1.062, 1.190, .969, 1.018, 1.194], "tail_share": [.095, .090, .102, .078, .078, .094]}
    HUMAN1 = {"core_share": [.400, .427, .465, .449, .477, .461], "whole_share": [.194, .160, .244, .116, .201, .200]}
    HUMAN2 = {"core_share": [.377, .403, .432, .510, .407, .476], "whole_share": [.201, .229, .158, .238, .271, .231]}
    RAWH = {"core_share": [.347, .395, .388, .381, .402, .388], "spacing_sd": [2.653, 2.252, 2.158, 2.346, 2.213, 2.368]}

    def v(self, row, name, ctl, arm):
        kind, tol = R.SPEC[row][name]
        return R.metric_verdict(kind, tol, ctl, arm)[0]

    def test_interval_is_seeded_and_brackets_the_difference(self):
        d, lo, hi = R.pool_diff(self.CTL1["core_share"], self.HUMAN1["core_share"])
        self.assertEqual((d, lo, hi), R.pool_diff(self.CTL1["core_share"], self.HUMAN1["core_share"]))
        self.assertTrue(lo < d < hi)

    def test_red_old_range_flips_human_whole_share_between_sessions(self):
        """the old rule: s1's human (.12-.24) falls under its control (.266-.291) -.05, s2's (.16-.27) does not"""
        old = lambda ctl, arm: R.metric_verdict("share", 0.05, ctl, arm)[0]
        self.assertEqual(old(self.CTL1["whole_share"], self.HUMAN1["whole_share"]), "FAIL")
        self.assertEqual(old(self.CTL2["whole_share"], self.HUMAN2["whole_share"]), "PASS")

    def test_stable_human_whole_share(self):
        for ctl, h in ((self.CTL1, self.HUMAN1), (self.CTL2, self.HUMAN2), (self.CTL1, self.HUMAN2), (self.CTL2, self.HUMAN1)):
            self.assertEqual(self.v("I2c", "whole_share", ctl["whole_share"], h["whole_share"]), "PASS")

    def test_stable_human_core_share_fails_in_every_session(self):
        for ctl, h in ((self.CTL1, self.HUMAN1), (self.CTL2, self.HUMAN2), (self.CTL1, self.HUMAN2), (self.CTL2, self.HUMAN1)):
            self.assertEqual(self.v("I2b", "core_share", ctl["core_share"], h["core_share"]), "FAIL")

    def test_control_of_one_session_passes_against_the_other(self):
        for row, names in (("I2b", ("core_share", "spacing_sd", "tail_share")), ("I2c", ("whole_share",))):
            for n in names:
                self.assertEqual(self.v(row, n, self.CTL1[n], self.CTL2[n]), "PASS", n)
                self.assertEqual(self.v(row, n, self.CTL2[n], self.CTL1[n]), "PASS", n)

    def test_red_continuous_stamps_fail_i2c(self):
        cont = [.09, .10, .095, .10, .09, .10]
        for ctl in (self.CTL1, self.CTL2):
            self.assertEqual(self.v("I2c", "whole_share", ctl["whole_share"], cont), "FAIL")

    def test_red_rawh_fails_i2b(self):
        for n in ("core_share", "spacing_sd"):
            self.assertEqual(self.v("I2b", n, self.CTL1[n], self.RAWH[n]), "FAIL", n)
            self.assertEqual(self.v("I2b", n, self.CTL2[n], self.RAWH[n]), "FAIL", n)

    def test_too_few_runs_are_unmeasured(self):
        self.assertEqual(self.v("I2b", "core_share", self.CTL1["core_share"], self.RAWH["core_share"][:3]), "UNMEASURED")

    def test_wide_interval_is_unmeasured(self):
        self.assertEqual(self.v("I2c", "whole_share", self.CTL1["whole_share"], [.0, .5, .0, .5, .0, .5]), "UNMEASURED")


class AfterSkip(unittest.TestCase):
    """review item 2: a frame is skipped when the rAF tick the event rides on follows its predecessor by > 25 ms. The head
    timeStamp gap says nothing: an authored stamp run is contiguous."""

    def test_uses_ticks_not_head_stamps(self):
        lg = log([ev("pointermove", 100.0, now=100.0, cs=2), ev("pointermove", 200.0, now=200.0, cs=2)])
        lg["raf"] = [[t, t] for t in (0.0, 16.7, 33.4, 50.1, 66.8, 83.5, 100.2, 116.9, 133.6, 150.3, 167.0, 183.7, 200.4)]
        self.assertEqual(R.after_skip(lg, 25.0), 0)        # head gap 100 ms, every frame on time
        lg["raf"] = [[t, t] for t in (0.0, 16.7, 33.4, 50.1, 66.8, 83.5, 100.2, 150.0, 166.7, 183.4, 200.1)]
        lg["ev"][0]["now"] = 110.0                         # rides the tick at 150.0, 49.8 ms after the one before
        self.assertEqual(R.after_skip(lg, 25.0), 1)        # only the first move rides the late tick


class PageLogs(unittest.TestCase):
    def test_page_logs_what_i7_and_i2c_read(self):
        import pathlib
        page = (pathlib.Path(__file__).parent / "input_probe" / "page.html").read_text(encoding="utf-8")
        self.assertIn("'pointerrawupdate'", page)
        self.assertIn("cxy: cxy(e)", page)


if __name__ == "__main__":
    unittest.main()

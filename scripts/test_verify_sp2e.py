import unittest

import sp2e_analysis as a


class OrderTest(unittest.TestCase):
    def test_moves_then_wheels_green(self):
        ev = [("m", i) for i in range(90)] + [("w", 100), ("w", 101), ("w", 102)]
        self.assertEqual(a.order_violations(ev), [])

    def test_moves_wheels_moves_green(self):
        ev = ([("m", i) for i in range(40)] + [("w", 40), ("w", 41), ("w", 42)]
              + [("m", 43 + i) for i in range(50)])
        self.assertEqual(a.order_violations(ev), [])

    def test_old_interleaved_is_flagged(self):  # RED control: runs [w1,m5,w1,m3,w1,m2]
        ev = ([("w", 1)] + [("m", 2 + i) for i in range(5)] + [("w", 8)]
              + [("m", 9 + i) for i in range(3)] + [("w", 12)] + [("m", 13), ("m", 14)])
        self.assertTrue(a.order_violations(ev))

    def test_move_between_notches_is_flagged(self):
        ev = [("m", 1), ("w", 2), ("m", 3), ("w", 4), ("w", 5), ("m", 6)]
        self.assertTrue(a.order_violations(ev))

    def test_wrong_wheel_count(self):
        self.assertTrue(a.order_violations([("m", 1), ("w", 2), ("m", 3)]))

    def test_backwards_time(self):
        ev = [("m", 1), ("w", 5), ("w", 6), ("w", 7), ("m", 3)]
        self.assertTrue(a.order_violations(ev))

    def test_moves_only_or_empty(self):
        self.assertTrue(a.order_violations([("m", 1), ("m", 2)]))
        self.assertTrue(a.order_violations([]))


class StatsTest(unittest.TestCase):
    def test_strict(self):
        self.assertTrue(a.strictly_increasing([1, 2, 3]))
        self.assertFalse(a.strictly_increasing([1, 2, 2]))
        self.assertFalse(a.strictly_increasing([3, 2]))

    def test_span(self):
        self.assertTrue(a.span_in_bounds([0, 80], 80, 1200))
        self.assertFalse(a.span_in_bounds([0, 79.9], 80, 1200))
        self.assertFalse(a.span_in_bounds([0, 1200.1], 80, 1200))
        self.assertFalse(a.span_in_bounds([5], 80, 1200))

    def test_visible_floor_fixture(self):
        # 3 px move: 80 ms path, first gap unseen -> ~64 ms page span is GREEN
        self.assertTrue(a.span_in_bounds([0, 20, 40, 64], a.VISIBLE_MIN_MS, a.MAX_TIME_MS))
        self.assertFalse(a.span_in_bounds([0, 15, 30], a.VISIBLE_MIN_MS, a.MAX_TIME_MS))
        self.assertAlmostEqual(a.VISIBLE_MIN_MS, 59.17, places=1)

    def test_gaps(self):
        s = a.gap_stats([0, 10, 20, 30, 100])
        self.assertEqual(s["median"], 10)
        self.assertEqual(s["max"], 70)
        self.assertEqual(a.gap_stats([1]), {"n": 0})

    def test_self_test(self):
        self.assertTrue(a.self_test())


class OverflowTest(unittest.TestCase):
    T = [100 + 40 * i for i in range(14)]

    def test_in_order_green(self):
        xs = [x for t in self.T for x in (t - 20, t)]
        self.assertEqual(a.final_order_violations(xs, self.T), [])

    def test_target13_before_5_is_red(self):
        xs = [x for t in self.T[:5] for x in (t - 20, t)]
        xs.append(self.T[13])  # the refused move's single stock event overtakes
        xs += [x for t in self.T[5:13] for x in (t - 20, t)]
        v = a.final_order_violations(xs, self.T)
        self.assertTrue(v)

    def test_missing_target(self):
        self.assertTrue(a.final_order_violations([100, 140], self.T))

    def test_deadline_from_design(self):
        self.assertAlmostEqual(a.REPLY_DEADLINE_S, 14.65, places=2)


class ZeroLengthTest(unittest.TestCase):
    def test_tail_green(self):
        ev = [(1, 1, 1.0), (5, 1, 2.0), (9, 1, 3.0), (9, 1, 4.0)]
        self.assertEqual(a.tail_violations(ev, (9, 1)), [])

    def test_tail_green_when_deduped(self):
        self.assertEqual(a.tail_violations([(1, 1, 1.0), (9, 1, 3.0)], (9, 1)), [])

    def test_forwarded_immediately_is_red(self):
        ev = [(9, 1, 0.5), (1, 1, 1.0), (5, 1, 2.0), (9, 1, 3.0)]
        self.assertTrue(a.tail_violations(ev, (9, 1)))

    def test_no_event(self):
        self.assertTrue(a.tail_violations([(1, 1, 1.0)], (9, 1)))

    def test_reply_order(self):
        self.assertTrue(a.reply_before([3, 4], 3, 4))
        self.assertFalse(a.reply_before([4, 3], 3, 4))
        self.assertFalse(a.reply_before([3], 3, 4))


if __name__ == "__main__":
    unittest.main()

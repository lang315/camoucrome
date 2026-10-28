import unittest

import sp2e_analysis as a


class OrderTest(unittest.TestCase):
    def test_good(self):
        ev = [("m", 1), ("m", 2), ("w", 3), ("w", 4), ("w", 5), ("m", 6)]
        self.assertEqual(a.order_violations(ev), [])

    def test_interleaved_is_flagged(self):  # RED control for the checker
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

    def test_gaps(self):
        s = a.gap_stats([0, 10, 20, 30, 100])
        self.assertEqual(s["median"], 10)
        self.assertEqual(s["max"], 70)
        self.assertEqual(a.gap_stats([1]), {"n": 0})

    def test_self_test(self):
        self.assertTrue(a.self_test())


if __name__ == "__main__":
    unittest.main()

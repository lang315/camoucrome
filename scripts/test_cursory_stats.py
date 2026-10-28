import math
import unittest

import cursory_stats as cs


def line(n=11, dur=100):
    return [(i * 10.0, 0.0, i * dur // (n - 1)) for i in range(n)]


class KsTest(unittest.TestCase):
    def test_identical_is_zero(self):
        self.assertEqual(cs.ks_statistic([1, 2, 3], [1, 2, 3]), 0.0)

    def test_disjoint_is_one(self):
        self.assertEqual(cs.ks_statistic([1, 2, 3], [10, 11, 12]), 1.0)

    def test_half_shift(self):
        self.assertAlmostEqual(cs.ks_statistic([1, 2, 3, 4], [3, 4, 5, 6]), 0.5)

    def test_critical(self):
        self.assertAlmostEqual(cs.critical(200, 200), 1.36 * math.sqrt(2 / 200))


class FeaturesTest(unittest.TestCase):
    def test_line(self):
        f = cs.features(line())
        self.assertEqual(f["duration"], 100)
        self.assertAlmostEqual(f["efficiency"], 1.0)
        self.assertAlmostEqual(f["curvature"], 0.0)
        self.assertAlmostEqual(f["mean_speed"], 1.0)

    def test_symmetric_speed_peaks_mid(self):
        xs = [0, 1, 3, 6, 9, 11, 12]  # fastest segments in the middle
        s = [(x, 0.0, i) for i, x in enumerate(xs)]
        self.assertAlmostEqual(cs.features(s)["peak_pos"], 0.5, delta=0.1)

    def test_detour_lowers_efficiency(self):
        s = [(0, 0, 0), (5, 5, 1), (10, 0, 2)]
        self.assertLess(cs.features(s)["efficiency"], 1.0)
        self.assertGreater(cs.features(s)["curvature"], 0.5)


if __name__ == "__main__":
    unittest.main()

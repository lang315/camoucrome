import unittest
import measure_cdp_timing as m

class GapStats(unittest.TestCase):
    def test_even_cadence(self):
        s = m.gap_stats([0, 16.7, 33.4, 50.1, 66.8])
        self.assertEqual(s["n"], 4)
        self.assertAlmostEqual(s["median"], 16.7, places=3)
        self.assertAlmostEqual(s["stdev"], 0.0, places=3)

    def test_one_stall_is_visible(self):
        s = m.gap_stats([0, 16, 32, 120, 136])
        self.assertEqual(s["max"], 88)
        self.assertGreater(s["stdev"], 30)

    def test_too_few_stamps(self):
        self.assertEqual(m.gap_stats([5.0])["n"], 0)

if __name__ == "__main__":
    unittest.main()

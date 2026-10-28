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

class Title(unittest.TestCase):
    def test_full_title_drops_warmup(self):
        import json
        s = m.parse_title(json.dumps(list(range(m.N + 1))))
        self.assertEqual(len(s), m.N)
        self.assertEqual(s[0], 1)

    def test_truncated_title_raises(self):
        with self.assertRaises(RuntimeError):
            m.parse_title("[1, 2, 3]")

    def test_driver_error_is_recorded(self):
        def boom(base):
            raise ValueError("x")
        self.assertEqual(m.run_driver(boom, "b"),
                         {"error": "ValueError('x')"})

class ExitCode(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(m.exit_code({"a": {"n": 3}, "go": "not available"}), 0)

    def test_any_error_fails(self):
        self.assertEqual(m.exit_code({"a": {"n": 3}, "b": {"error": "x"}}), 1)

if __name__ == "__main__":
    unittest.main()

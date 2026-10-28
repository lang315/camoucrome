import unittest

import sp2b_analysis as a


def ev(xs, t0=60.0):
    return [{"x": float(x), "y": 0.0, "t": t0 + 17 * i} for i, x in enumerate(xs)]


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

    def test_small_cluster_fails(self):
        self.assertFalse(a.traces_path(ev([412, 416, 420]), 320.0)[0])

    def test_fewer_than_two_events_fails(self):
        self.assertFalse(a.traces_path(ev([420]), 320.0)[0])
        self.assertFalse(a.traces_path([], 320.0)[0])

    def test_bar_is_a_tenth_of_the_path(self):
        self.assertFalse(a.traces_path(ev([388, 420]), 320.0)[0])  # span 32, not above
        self.assertTrue(a.traces_path(ev([387, 420]), 320.0)[0])   # span 33


if __name__ == "__main__":
    unittest.main()

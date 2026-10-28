import gzip, json, os, tempfile, unittest
import gen_cursory_table as g

REC = [
    {"start": [0, 0], "end": [10, 0], "points": [[0, 0], [5, 1], [10, 0]],
     "dx": 10, "dy": 0, "length": 10.2, "timing": [0, 7, 14]},
    {"start": [5, 5], "end": [5, 25], "points": [[5, 5], [5, 25]],
     "dx": 0, "dy": 20, "length": 20.0, "timing": [100, 130]},
]

class Gen(unittest.TestCase):
    def test_render_counts(self):
        h, c = g.render(REC)
        self.assertIn("kRecordingCount = 2", c)
        self.assertIn("kPointCount = 5", c)

    def test_timing_is_relative_to_first_point(self):
        _, c = g.render(REC)
        self.assertIn("0, 7, 14, 0, 30", c)   # second recording starts at 0, not 100

    def test_rejects_unrepresentable(self):
        bad = [dict(REC[0], timing=[0, 7, 70000])]
        with self.assertRaises(ValueError):
            g.render(bad)
        bad = [dict(REC[0], points=[[0, 0], [40000, 0], [10, 0]])]
        with self.assertRaises(ValueError):
            g.render(bad)

    def test_rejects_non_monotonic_timing(self):
        with self.assertRaises(ValueError):
            g.render([dict(REC[0], timing=[0, 7, 3])])

    def test_pinned_snapshot_is_the_real_one(self):
        recs = g.load(g.SNAPSHOT)
        self.assertEqual(len(recs), 2356)
        self.assertEqual(sum(len(r["points"]) for r in recs), 112984)

    def test_check_missing_files(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(g.main(["--check", "--out-dir", d]), 1)

    def test_check_fresh_then_stale(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(g.main(["--out-dir", d]), 0)
            self.assertEqual(g.main(["--check", "--out-dir", d]), 0)
            p = os.path.join(d, "cursory_data.cc")
            with open(p, "rb") as f:
                raw = bytearray(f.read())
            i = raw.index(b"kPointCount = ") + len(b"kPointCount = ")
            raw[i] = ord("9") if raw[i] != ord("9") else ord("8")
            with open(p, "wb") as f:
                f.write(raw)
            self.assertEqual(g.main(["--check", "--out-dir", d]), 1)

    def test_check_detects_moved_snapshot_hash(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(g.main(["--out-dir", d]), 0)
            old = g.PINNED_SHA256
            g.PINNED_SHA256 = "0" * 64
            try:
                self.assertEqual(g.main(["--check", "--out-dir", d]), 1)
            finally:
                g.PINNED_SHA256 = old

if __name__ == "__main__":
    unittest.main()

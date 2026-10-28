"""The DRIVERS list of verify_sp6b_driver: the Go spike rows and the per-driver
C1 floor. Importing the verify is safe off the box (it only resolves paths)."""
import unittest

import verify_sp6b_driver as v

OLD = [("python-stock", "RED"), ("python-patchright", "GREEN"), ("go-stock", "RED"),
       ("go-patchright", "GREEN"), ("node-stock", "RED"), ("node-patchright", "GREEN")]


def rows():
    return {d[0]: d for d in v.DRIVERS}


def run_check(min_methods, sends=12):
    log = '"method":"X"\n' * sends
    rep = {"windowKeys": [], "webdriver": False, "initScript": "number", "ownNames": 1,
           "timesMs": [1.0], "ua": ""}
    base = {"windowKeys": [], "ownNames": 0, "timesMs": [1.0]}
    r = v.check("x", {"report": rep, "argv": []}, log, base, min_methods)
    return r["C1 no Runtime.enable, logger alive"][0]


class DriversTest(unittest.TestCase):
    def test_old_rows_unchanged(self):
        self.assertEqual([(d[0], d[1]) for d in v.DRIVERS[:6]], OLD)
        self.assertTrue(all(len(d) == 3 for d in v.DRIVERS[:6]))

    def test_new_rows(self):
        r = rows()
        self.assertEqual(r["go-rod-own-launcher"][1], "GREEN")
        self.assertEqual(r["go-chromedp-control"][1], "RED")
        self.assertIn("--no-default-device", r["go-rod-own-launcher"][2])
        self.assertEqual(r["go-rod-own-launcher"][3], {"min_methods": 10})

    def test_min_methods_override_not_vacuous(self):
        self.assertTrue(run_check(10))
        self.assertFalse(run_check(v.MIN_METHODS))


if __name__ == "__main__":
    unittest.main()

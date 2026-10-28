"""The DRIVERS list of verify_sp6b_driver: the go-rodclient row and the per-driver
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

    def test_rodclient_row(self):
        r = rows()["go-rodclient"]
        self.assertEqual(r[1], "GREEN")
        self.assertNotIn("--no-default-device", r[2])  # the wrapper owns it
        self.assertIn("--label", r[2])
        self.assertEqual(r[3], {"min_methods": 10})
        self.assertEqual(len(v.DRIVERS), 7)
        self.assertEqual(r[2][0], v.RODCLIENT_PROBE)
        self.assertTrue(v.RODCLIENT_PROBE.endswith("/camoucrome-go/camoucrome-probe-rodclient")
                        or "CAMOU_RODCLIENT_PROBE" in __import__("os").environ)

    def test_min_methods_override_not_vacuous(self):
        self.assertTrue(run_check(10))
        self.assertFalse(run_check(v.MIN_METHODS))


C1 = "C1 no Runtime.enable, logger alive"


class VerdictTest(unittest.TestCase):
    def test_red_passes_when_c1_fails(self):
        self.assertTrue(v.verdict_of("RED", {C1: (False, "")}))

    def test_red_fails_when_c1_passes(self):
        self.assertFalse(v.verdict_of("RED", {C1: (True, "")}))

    def test_green_uses_all_rows(self):
        self.assertFalse(v.verdict_of("GREEN", {C1: (True, ""), "x": (False, "")}))

    def test_main_unpacks_both_tuple_shapes(self):
        for d in v.DRIVERS:
            label, expected, cmd, *opts = d
            self.assertLessEqual(len(opts), 1)


class JudgeRowTest(unittest.TestCase):
    """The per-row loop body of main(), run with a fake result/log/base."""

    def judge(self, label, sends, enables):
        d = rows()[label]
        log = '"method":"X"\n' * sends + '"method":"Runtime.enable"\n' * enables
        rep = {"windowKeys": [], "webdriver": False, "initScript": "number", "ownNames": 1,
               "timesMs": [1.0], "ua": "ua"}
        base = {"windowKeys": [], "ownNames": 0, "timesMs": [1.0]}
        return v.judge_row(d[0], d[1], d[3] if len(d) > 3 else {},
                           {"report": rep, "argv": []}, log, base)

    def test_old_three_tuple_row(self):
        ok, lines = self.judge("go-stock", 5, 0)
        self.assertTrue(ok)  # RED: C1 fails on the 5-send log

    def test_rodclient_row_opts_reach_check(self):
        ok, lines = self.judge("go-rodclient", 12, 0)
        self.assertTrue(any("ok   C1" in l for l in lines))


if __name__ == "__main__":
    unittest.main()

"""Tests of the pure parts of measure_input_probes: paths, phase split, the report on synthetic records."""
import contextlib
import io
import json
import os
import pathlib
import tempfile
import unittest

import measure_input_probes as M
import test_input_probe_rows as T


class Paths(unittest.TestCase):
    def test_path_spacing_and_ends(self):
        p = M.path((0, 0), (100, 50), 1000, 125)
        self.assertEqual(len(p), 126)
        self.assertEqual((p[0][1:], p[-1][1:]), ((0, 0), (100, 50)))
        self.assertAlmostEqual(p[1][0] - p[0][0], 8.0)

    def test_slow_control_stretches_only_the_move_sweeps(self):
        class Rec:
            def __init__(self):
                self.d = []

            def sweep(self, p0, p1, dur, hz=None, bow=0.0):
                self.d.append(dur)
        fast, slow = Rec(), Rec()
        M.gesture(fast, "move", 800, 600, None)
        M.gesture(slow, "move", 800, 600, None, slow=M.SLOW)
        self.assertEqual(slow.d, [d * M.SLOW for d in fast.d])
        self.assertEqual(M.gesture_slow("ctl125slow"), M.SLOW)
        self.assertEqual([M.gesture_slow(a) for a in ("ctl125", "rawh", "red")], [1, 1, 1])

    def test_edge_legs_leave_the_viewport(self):
        for _, e in M.edge_legs(800, 600):
            self.assertTrue(e[0] < 0 or e[0] > 800 or e[1] < 0 or e[1] > 600)


class Split(unittest.TestCase):
    def test_only_the_rows_phase(self):
        snap = {"meta": {}, "raf": [], "ev": [{"ph": "move", "t": "a"}, {"ph": "edge", "t": "b"}, {"ph": "cal", "t": "c"}]}
        self.assertEqual([e["t"] for e in M.split(snap, "I4")["ev"]], ["b"])
        self.assertEqual([e["t"] for e in M.split(snap, "I1")["ev"]], ["a"])


class Report(unittest.TestCase):
    def snap(self, moves):
        lg = T.log(moves)
        for e in lg["ev"]:
            e["ph"] = "move"
        return lg

    def put(self, d, arm, i, rec):
        (d / f"{arm}-{i}.json").write_text(json.dumps({"arm": arm, "run": i, "unmeasured": None, **rec}))

    def report(self, d):
        class A:
            dir = str(d)
        with contextlib.redirect_stdout(io.StringIO()):
            M.cmd_report(A)
        return (d / "table.md").read_text()

    def test_red_arm_fails_and_human_other_rows_are_na(self):
        d = pathlib.Path(tempfile.mkdtemp())
        for arm in M.CTL:
            for i, p in enumerate((0.5, 1.0, 1.5, 0.8)):
                self.put(d, arm, i, {"snap": self.snap(T.real_moves(phase=p))})
        for i in range(4):
            self.put(d, "red", i, {"snap": self.snap(T.burst_moves())})
            self.put(d, "human", i, {"snap": self.snap(T.real_moves())})
        t = self.report(d)
        self.assertRegex(t, r"\| I1 \| red \| 4 \| FAIL")           # synthetic burst: the planted case fails on a fixture
        self.assertRegex(t, r"\| I1 \| human \| 4 \| PASS")
        self.assertIn("| I5 | human | 0 | n/a (no API)", t)
        self.assertIn("cannot fail live", t)

    def test_slow_control_is_a_group_only_when_it_ran(self):
        d = pathlib.Path(tempfile.mkdtemp())
        for arm in ("ctl125", "ctl1000"):
            for i, p in enumerate((0.5, 1.0, 1.5, 0.8)):
                self.put(d, arm, i, {"snap": self.snap(T.real_moves(phase=p))})
        for i in range(4):
            self.put(d, "red", i, {"snap": self.snap(T.burst_moves())})
        t = self.report(d)
        self.assertNotIn("ctl125slow", t)                           # an old run's report is unchanged
        self.assertRegex(t, r"\| I1 \| red \| 4 \| FAIL")
        for i in range(4):                                          # a slow control that looks like the arm
            self.put(d, "ctl125slow", i, {"snap": self.snap(T.burst_moves())})
        t = self.report(d)
        self.assertRegex(t, r"\| I1 \| red \| 4 \| PASS \| per rate: ctl125: FAIL; ctl1000: FAIL; ctl125slow: PASS")
        self.assertNotRegex(t, r"\| I\d \| ctl125slow \|")          # a control is never judged as an arm

    def test_summary_has_the_move_phase_seconds(self):
        d = pathlib.Path(tempfile.mkdtemp())
        pms = [T.ev("pointermove", i * 100.0, now=i * 100.0, cs=2) for i in range(60)]     # 5.9 s first to last
        for i in range(4):
            self.put(d, "rawh", i, {"snap": self.snap([dict(e) for e in pms])})
        t = self.report(d)
        self.assertIn("| move s |", t)
        row = next(ln for ln in t.splitlines() if ln.startswith("| rawh | 4 |"))
        self.assertTrue(row.endswith("| 5.9 |"), row)

    def test_run_that_raised_is_unmeasured_not_a_keyerror(self):
        d = pathlib.Path(tempfile.mkdtemp())
        self.put(d, "raw", 0, {"unmeasured": "error: OSError: SendInput injected fewer events"})   # no snap
        t = self.report(d)
        self.assertRegex(t, r"\| I1 \| raw \| 0 \| UNMEASURED \| error: OSError")

    def test_run_arm_turns_an_exception_into_a_record(self):
        """off Windows the control arm raises at si.aware(): the run must still leave a record that says UNMEASURED"""
        d = pathlib.Path(tempfile.mkdtemp())
        srv, st = M.serve(d)
        try:
            class A:
                stock_exe = fork_exe = "x"
                fork_version = "157.0.8103.51"
            rec = M.run_arm("ctl125", 0, A, srv, st, d)
        finally:
            srv.shutdown()
        self.assertTrue(rec["unmeasured"].startswith("error:"), rec["unmeasured"])
        self.assertEqual(json.loads((d / "ctl125-0.json").read_text())["unmeasured"], rec["unmeasured"])


class Browser(unittest.TestCase):
    def test_wrong_browser(self):
        real = M.running_exe
        try:
            M.running_exe = lambda udd: ("D:\\stock\\chrome.exe", "158.0.8200.1")
            self.assertIn("version 158", M.wrong_browser("u", "D:\\stock\\chrome.exe", "157.0.8103.51", pin_exact=False))
            M.running_exe = lambda udd: ("C:\\Program Files\\chrome.exe", "157.0.8103.50")
            self.assertIn("not", M.wrong_browser("u", "D:\\stock\\chrome.exe", "157.0.8103.51", pin_exact=False))
            M.running_exe = lambda udd: (os.path.abspath("chrome.exe"), "157.0.8103.50")
            self.assertIsNone(M.wrong_browser("u", "chrome.exe", "157.0.8103.51", pin_exact=False))          # stock: any patch of the build
            self.assertIn("exactly", M.wrong_browser("u", "chrome.exe", "157.0.8103.51", pin_exact=True))   # fork: the pin
            M.running_exe = lambda udd: None
            self.assertIn("no browser", M.wrong_browser("u", "chrome.exe", "157.0.8103.51", pin_exact=True))
        finally:
            M.running_exe = real

    def test_adapter_names_never_leave_as_a_gpu_string(self):
        self.assertEqual(M.adapter_kind("Virtual Display Driver"), "vdd")
        self.assertEqual(M.adapter_kind("Microsoft Remote Display Adapter"), "rdp")
        self.assertEqual(M.adapter_kind("Vendor Model 1234"), "gpu")

    def test_no_wsl_user_means_no_launch(self):
        saved = os.environ.pop("CAMOU_WSL_USER", None)
        try:
            self.assertIn("CAMOU_WSL_USER", M.launch_problem())
        finally:
            if saved is not None:
                os.environ["CAMOU_WSL_USER"] = saved


if __name__ == "__main__":
    unittest.main()

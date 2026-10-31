"""verify_light_flag.leaf_diff without a browser: what the gate calls a difference and what it calls noise."""
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lib_shell  # noqa: E402,F401 - imported before CAMOU_CLIENT, as in test_verify_host_oracle.py
os.environ["CAMOU_CLIENT"] = str(HERE.parent)
import verify_light_flag as V  # noqa: E402

BASE = {"perfMem": {"jsHeapSizeLimit": 4294705152}, "nav": {"hc": 8}, "timing": {"t": 1.5}}


def test_identical_captures_have_no_line_and_no_noise():
    assert V.leaf_diff(BASE, BASE, BASE) == ([], [])


def test_the_red_heap_cap_is_one_line_on_js_heap_size_limit():
    flagged = {**BASE, "perfMem": {"jsHeapSizeLimit": 536870912}}
    assert V.leaf_diff(BASE, BASE, flagged) == ([], [("perfMem.jsHeapSizeLimit", 4294705152, 536870912)])


def test_a_leaf_that_moves_between_flagless_captures_is_noise_and_listed():
    b2 = {**BASE, "timing": {"t": 2.5}}
    flagged = {**BASE, "timing": {"t": 9.0}}
    assert V.leaf_diff(BASE, b2, flagged) == (["timing.t"], [])


def test_a_leaf_missing_in_the_flagged_capture_is_a_line():
    flagged = {"perfMem": BASE["perfMem"], "timing": BASE["timing"]}
    assert V.leaf_diff(BASE, BASE, flagged) == ([], [("nav.hc", 8, "<absent>")])

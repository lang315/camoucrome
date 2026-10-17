"""verify_d_pointer_touch's V1 verdict without a browser."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_d_pointer_touch as v  # noqa: E402

NONE = {"pointer": "none", "hover": "none", "anyFine": False, "anyCoarse": False, "anyNone": True,
        "anyHover": False, "maxTouchPoints": 0, "ontouchstart": False, "keys": ["a"]}
FINE = {**NONE, "pointer": "fine", "hover": "hover", "anyFine": True, "anyNone": False, "anyHover": True}


def test_v1_passes_on_a_mouseless_host_when_the_claim_changes_it():
    assert v.v1_status(NONE, FINE, host_has_mouse=False) == "PASS"


def test_v1_fails_when_the_claim_changes_nothing_on_a_mouseless_host():
    assert v.v1_status(NONE, NONE, host_has_mouse=False) == "FAIL"


def test_v1_is_not_measured_when_the_host_already_has_a_mouse():
    # Every interactive Windows session has one (step2b, 2026-10-13): there V1 cannot be its RED.
    assert v.v1_status(FINE, FINE, host_has_mouse=True) == "NOT MEASURED"


def test_v1_still_fails_a_fine_pointer_on_a_mouseless_host():
    # Final review: the measured value must not decide the skip, or a regression to
    # pointer: fine on Linux would print NOT MEASURED instead of FAIL.
    assert v.v1_status(FINE, FINE, host_has_mouse=False) == "FAIL"


def test_host_has_mouse_is_false_off_windows():
    if os.name != "nt":
        assert v.host_has_mouse() is False

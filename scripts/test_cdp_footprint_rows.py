"""Row judges of the CDP footprint harness (pure; no browser)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cdp_footprint_rows import (FAIL, PASS, UNMEASURED, judge_click, judge_flag, judge_keys,  # noqa: E402
                                judge_observer, judge_row, judge_timing, render)


def test_timing_overlap_pass():
    assert judge_timing([24, 25] * 5, [25, 26] * 5) == PASS


def test_timing_no_overlap_fail():
    d = [21, 21.3, 22.5, 23.9, 24.4, 24.5, 24.9, 25.6, 26.3]
    e = [26.7, 27, 28, 28.8, 29.5, 29.6, 29.8, 30.1, 30.5]
    assert judge_timing(d, e) == FAIL  # arm slower than the baseline
    assert judge_timing(e, d) == UNMEASURED  # arm faster and disjoint: not a footprint


def test_timing_short_unmeasured():
    assert judge_timing([1.0] * 8, [1.0] * 9) == UNMEASURED
    assert judge_timing([1.0] * 9, [1.0] * 8) == UNMEASURED


def _typed(c):
    ev = [{"type": "keydown", "key": c}, {"type": "keypress", "key": c},
          {"type": "beforeinput", "data": c}, {"type": "input", "data": c},
          {"type": "keyup", "key": c}]
    return [dict({"key": None, "data": None, "isTrusted": True}, **e) for e in ev]


def _typed_all(text):
    return [e for c in text for e in _typed(c)]


def test_keys_full_sequence_pass():
    for s in ("camou footprint", "Tiếng Việt có dấu"):
        assert judge_keys(_typed_all(s), s) == PASS


def test_keys_insert_text_fail():
    ev = [{"type": "beforeinput", "data": "ế", "key": None, "isTrusted": True},
          {"type": "input", "data": "ế", "key": None, "isTrusted": True}]
    assert judge_keys(ev, "ế") == FAIL


def test_keys_judged_per_char():
    ev = _typed_all("ab") + [{"type": "input", "data": "ệ", "key": None, "isTrusted": True}]
    assert judge_keys(ev, "abệ") == FAIL
    assert judge_keys(ev, "ab") == PASS


def test_keys_empty_unmeasured():
    assert judge_keys([], "a") == UNMEASURED


def _click(**kw):
    base = {"isTrusted": True, "screenX": 260, "screenY": 353, "clientX": 250, "clientY": 200,
            "button": 0, "pointerId": None, "pointerType": None, "isPrimary": None}
    return dict(base, **kw)


def _sp2b4():
    return [
        _click(type="pointerdown", buttons=1, detail=0, pointerId=1, pointerType="mouse", isPrimary=True),
        _click(type="mousedown", buttons=1, detail=1),
        _click(type="pointerup", buttons=0, detail=0, pointerId=1, pointerType="mouse", isPrimary=True),
        _click(type="mouseup", buttons=0, detail=1),
        _click(type="click", buttons=0, detail=1, pointerId=1, pointerType="mouse", isPrimary=False),
    ]


def test_click_sp2b4_shape_pass():
    assert judge_click(_sp2b4()) == PASS


def test_click_untrusted_fail():
    f = _sp2b4()
    f[2]["isTrusted"] = False
    assert judge_click(f) == FAIL


def test_click_offset_and_empty():
    f = _sp2b4()
    f[4]["screenX"] = 0
    assert judge_click(f) == FAIL
    assert judge_click([]) == UNMEASURED


def _l1(v):
    return {"L1": v}


def test_missing_result_is_unmeasured():
    r = judge_row("L1", {"none": _l1(False), "tdp": None, "tdp-main": _l1(False), "red": _l1(True)})
    assert r == {"tdp": UNMEASURED, "tdp-main": PASS, "red": FAIL}


def test_dead_control_makes_row_unmeasured():
    r = judge_row("L1", {"none": _l1(False), "tdp": _l1(True), "tdp-main": _l1(False), "red": _l1(False)})
    assert r == {"tdp": UNMEASURED, "tdp-main": UNMEASURED, "red": UNMEASURED}


def test_none_missing_all_unmeasured():
    r = judge_row("L1", {"none": None, "tdp": _l1(False), "tdp-main": _l1(False), "red": _l1(True)})
    assert set(r.values()) == {UNMEASURED}


def test_row_l3_and_l8_and_l5():
    ok = {"tdp": {"L3": []}, "tdp-main": {"L3": ["x.js"]}, "red": {"L3": ["x.js"]}, "none": {"L3": []}}
    assert judge_row("L3", ok) == {"tdp": PASS, "tdp-main": FAIL, "red": FAIL}
    h = {"webdriver": False, "keys": 3, "hash": "a"}
    l8 = {"none": {"L8": h}, "tdp": {"L8": h}, "tdp-main": {"L8": dict(h, hash="b")}, "red": {"L8": dict(h, webdriver=True)}}
    assert judge_row("L8", l8) == {"tdp": PASS, "tdp-main": FAIL, "red": FAIL}
    s = "camou footprint"
    good, bad = {"L5a": _typed_all(s)}, {"L5a": [{"type": "input", "data": "c", "key": None}]}
    assert judge_row("L5a", {"none": good, "tdp": good, "tdp-main": good, "red": bad}) == \
        {"tdp": PASS, "tdp-main": PASS, "red": FAIL}


def test_row_timing():
    a, b = [24, 25] * 5, [40, 41] * 5
    r = judge_row("L2", {"none": {"L2": a}, "tdp": {"L2": a}, "tdp-main": {"L2": b}, "red": {"L2": b}})
    assert r == {"tdp": PASS, "tdp-main": FAIL, "red": FAIL}


def test_empty_observer_summary_is_unmeasured():
    full = {"groups": {"a": 1}, "intl": [], "requests": 1, "ajax_bz": 2}
    empty = {"groups": {}, "intl": [], "requests": 0, "ajax_bz": 0}
    assert judge_observer(full, empty) == ["UNMEASURED empty summary"]
    assert judge_observer(empty, full) == ["UNMEASURED empty summary"]
    arm = {"groups": {"b": 1}, "intl": [], "requests": 1, "ajax_bz": 5}
    assert judge_observer(full, arm) == ["+b", "-a", "ajax_bz 2->5"]


def test_render():
    out = render({"L2": {"none": PASS, "tdp": FAIL}})
    assert "| L2 |" in out and "L2 tdp (class 1)" in out


def test_keys_repeated_char_first_occurrence_incomplete_fails():
    first = [e for e in _typed("o") if e["type"] != "keypress"]
    assert judge_keys(first + _typed("o"), "oo") == FAIL
    assert judge_keys(_typed("o") + _typed("o"), "oo") == PASS


def test_row_l7():
    good, bad = {"L7": _sp2b4()}, {"L7": [dict(f, isTrusted=False) for f in _sp2b4()]}
    assert judge_row("L7", {"none": None, "tdp": good, "tdp-main": good, "red": bad}) == \
        {"tdp": PASS, "tdp-main": PASS, "red": FAIL}


def test_missing_key_is_unmeasured_not_keyerror():
    ok = {"L3": ["x.js"], "L2": [1.0] * 9}
    r = judge_row("L3", {"none": {}, "tdp": {}, "tdp-main": {"L3": []}, "red": ok})
    assert r == {"tdp": UNMEASURED, "tdp-main": PASS, "red": FAIL}
    r = judge_row("L2", {"none": {}, "tdp": ok, "tdp-main": ok, "red": ok})
    assert set(r.values()) == {UNMEASURED}
    assert judge_flag(None, None) == UNMEASURED


def test_keys_untrusted_events_do_not_count():
    s = "ab"
    ev = [dict(e, isTrusted=False) for e in _typed_all(s)]
    assert judge_keys(ev, s) == FAIL

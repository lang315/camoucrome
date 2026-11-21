import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import driver_probes_rows as r  # noqa: E402
from cdp_footprint_rows import FAIL, PASS, UNMEASURED  # noqa: E402


def fire(*frames, sites=None, script=None):
    return {"type": "focus", "stack": "Error\n" + "\n".join(frames), "sites": sites or [], "script": script}


LISTENER = "    at HTMLInputElement.<anonymous> (http://127.0.0.1:5001/l9.html?arm=a&run=r1:12:9)"
LISTENER2 = "    at HTMLInputElement.<anonymous> (http://127.0.0.1:6002/l9.html?arm=b&run=r2:12:9)"
DRIVER = "    at HTMLInputElement.focus (pptr:footprint:1:2)"


def test_norm_frame_drops_host_query_position():
    assert r.norm_frame(LISTENER) == r.norm_frame(LISTENER2) == "at HTMLInputElement.<anonymous> (l9.html)"


def test_same_frames_pass_across_ports_and_queries():
    assert r.judge_stack([fire(LISTENER)], [fire(LISTENER2)]) == PASS


def test_driver_frame_fails():
    assert r.judge_stack([fire(LISTENER)], [fire(LISTENER2, DRIVER)]) == FAIL


def test_frame_the_control_lacks_fails_without_a_marker():
    assert r.judge_stack([fire(LISTENER)], [fire(LISTENER, "    at foo (http://127.0.0.1:1/other.js:1:1)")]) == FAIL


def test_marker_fails_even_if_the_control_has_it():
    assert r.judge_stack([fire(LISTENER, DRIVER)], [fire(LISTENER, DRIVER)]) == FAIL


def test_current_script_and_callsites_count():
    assert r.judge_stack([fire(LISTENER)], [fire(LISTENER, script="[object HTMLScriptElement]")]) == FAIL
    assert r.judge_stack([fire(LISTENER, sites=["a|l9.html|false"])], [fire(LISTENER, sites=["a|l9.html|false", "b|pptr:x|true"])]) == FAIL


def test_nothing_fired_is_unmeasured_never_pass():
    assert r.judge_stack([fire(LISTENER)], []) == UNMEASURED
    assert r.judge_stack([fire(LISTENER)], None) == UNMEASURED
    assert r.judge_stack(None, [fire(LISTENER)]) == UNMEASURED


def test_row_needs_red_to_fail():
    res = {"control": {"focus": [fire(LISTENER)]}, "tdp": {"focus": [fire(LISTENER)]}, "red": {"focus": [fire(LISTENER)]}}
    assert r.judge_stack_row("focus", res) == {"tdp": UNMEASURED, "red": UNMEASURED}  # dead control: red did not fail
    res["red"] = {"focus": [fire(LISTENER, DRIVER)]}
    assert r.judge_stack_row("focus", res) == {"tdp": PASS, "red": FAIL}
    res["tdp"] = {"focus": [fire(LISTENER, DRIVER)]}
    assert r.judge_stack_row("focus", res)["tdp"] == FAIL


def test_parse_request_keeps_order_and_case():
    raw = b"GET /h?x=1 HTTP/1.1\r\nHost: a\r\nx-lower: 1\r\nAccept: */*\r\n\r\n"
    assert r.parse_request(raw) == ("GET /h?x=1 HTTP/1.1", ["Host", "x-lower", "Accept"])


B = ["Host", "Accept", "X-A", "User-Agent"]


def test_headers_same_passes():
    assert r.judge_headers([B, B], [B, B])[0] == PASS


def test_headers_reordered_lowercased_or_dropped_fail():
    assert r.judge_headers([B, B], [["Host", "X-A", "Accept", "User-Agent"]] * 2)[0] == FAIL
    assert r.judge_headers([B, B], [["Host", "Accept", "x-a", "User-Agent"]] * 2)[0] == FAIL
    assert r.judge_headers([B, B], [["Host", "Accept", "X-A"]] * 2)[0] == FAIL


def test_added_header_is_removed_case_insensitively_and_position_reported():
    arm = ["Host", "Accept", "x-probe", "X-A", "User-Agent"]
    assert r.judge_headers([B, B], [arm, arm], added="X-Probe")[0] == PASS
    assert r.landing(arm, "X-Probe") == 2
    assert r.judge_headers([B, B], [arm, arm])[0] == FAIL  # not declared as added: a set difference


def test_unstable_or_thin_samples_are_unmeasured_and_unstable_arm_fails():
    assert r.judge_headers([B], [B, B])[0] == UNMEASURED
    assert r.judge_headers([B, ["Host"]], [B, B])[0] == UNMEASURED
    assert r.judge_headers([B, B], [B, ["Host"]])[0] == FAIL


def test_override_that_never_landed_fails_not_passes():
    assert r.judge_headers([B, B], [B, B], added="X-Probe")[0] == FAIL


def test_stack_row_needs_the_owning_action_ok():
    res = {"control": {"focus": [fire(LISTENER)]}, "rod": {"focus": [fire(LISTENER)]}, "red": {"focus": [fire(LISTENER, DRIVER)]}}
    ok = {"focus": "ok:x"}
    acts = {"control": ok, "rod": {"focus": "n/a: no API", "click": "ok:x"}, "red": ok}
    assert r.judge_stack_row("focus", res, acts) == {"rod": UNMEASURED, "red": FAIL}
    acts["rod"] = {"focus": "error:boom"}
    assert r.judge_stack_row("focus", res, acts)["rod"] == UNMEASURED
    acts["rod"] = ok
    assert r.judge_stack_row("focus", res, acts)["rod"] == PASS
    acts["control"] = {"focus": "n/a"}  # control's action did not run: nothing to compare with
    assert r.judge_stack_row("focus", res, acts) == {"rod": UNMEASURED, "red": UNMEASURED}


def test_required_header_compares_against_the_reference_override():
    raw = ["Host", "X-A", "X-Probe"]
    assert r.judge_headers([raw, raw], [raw, raw], required="X-Probe")[0] == PASS
    assert r.judge_headers([raw, raw], [["Host", "x-a", "X-Probe"]] * 2, required="X-Probe")[0] == FAIL
    assert r.judge_headers([raw, raw], [["Host", "X-A"]] * 2, required="X-Probe")[0] == FAIL
    assert r.judge_headers([["Host"]] * 2, [raw, raw], required="X-Probe")[0] == UNMEASURED

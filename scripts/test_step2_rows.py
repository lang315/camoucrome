"""step2_rows and oracle_rules without a browser (roadmap step 2)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_oracle_rules_shared():
    import oracle_rules
    assert "screen.width" in oracle_rules.SHAPE_ONLY and "audioFp" in oracle_rules.SHAPE_ONLY
    assert oracle_rules.flatten({"a": {"b": 1, "c": [2]}, "d": None}) == {"a.b": 1, "a.c": [2], "d": None}


import json
import pathlib

import pytest

import step2_rows as r

FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "step2"


def test_equal_rows_are_not_listed():
    assert r.label_rows({"x": 1}, {"x": 1}) == []


def test_unknown_difference_is_unexpected():
    assert r.label_rows({"oracle.nav.platform": "Win32"}, {"oracle.nav.platform": "Linux"}) == [
        ("oracle.nav.platform", "Win32", "Linux", "unexpected", "")]


def test_shape_only_leaf_value_difference_is_expected_same_type():
    [(name, _, _, label, reason)] = r.label_rows({"oracle.screen.width": 1920}, {"oracle.screen.width": 1536})
    assert (name, label) == ("oracle.screen.width", "expected") and reason


def test_shape_only_leaf_type_change_is_unexpected():
    [(_, _, _, label, _)] = r.label_rows({"oracle.screen.width": 1920}, {"oracle.screen.width": "1536"})
    assert label == "unexpected"


def test_shape_only_prefix_does_not_swallow_a_longer_name():
    # SHAPE_ONLY has nav.language; nav.languagesX is a different leaf.
    [(_, _, _, label, _)] = r.label_rows({"oracle.nav.languagesX": 1}, {"oracle.nav.languagesX": 2})
    assert label == "unexpected"


def test_absent_on_one_side_is_unexpected():
    [(_, c, f, label, _)] = r.label_rows({"oracle.nav.share": "function"}, {})
    assert (c, f, label) == ("function", "<absent>", "unexpected")


def test_volatile_row():
    [(_, _, _, label, _)] = r.label_rows({"net.ja3": "a"}, {"net.ja3": "b"})
    assert label == "volatile"


def test_unmeasured_wins():
    [(_, _, _, label, _)] = r.label_rows({"det.pixelscan": "UNMEASURED"}, {"det.pixelscan.x": 1})[:1]
    assert label == "unmeasured"


def test_argv_parity_allows_profile_and_accept_lang_only():
    c = ["chrome.exe", "--no-first-run", "--user-data-dir=C:\\a", "--remote-debugging-pipe"]
    f = ["chrome.exe", "--no-first-run", "--user-data-dir=C:\\b", "--remote-debugging-pipe", "--accept-lang=en-US"]
    assert r.argv_problems(c, f) == []


def test_argv_parity_allows_identity_window_and_dpr():
    c = ["chrome.exe", "--no-first-run"]
    f = ["chrome.exe", "--no-first-run", "--window-size=1536,816", "--force-device-scale-factor=1.25"]
    assert r.argv_problems(c, f) == []


def test_argv_parity_flags_extra_arg():
    c = ["chrome.exe", "--no-first-run"]
    f = ["chrome.exe", "--no-first-run", "--use-angle=swiftshader"]
    assert r.argv_problems(c, f) == ["fork only: --use-angle=swiftshader"]


def test_argv_parity_refuses_unread_argv():
    assert r.argv_problems([], ["chrome.exe"]) == ["argv not read: control=0 fork=1 elements"]


def test_version_precondition():
    assert r.version_problems({"control": "154.0.8037.93", "fork": "154.0.8037.93"}, "154.0.8037.93") == []
    assert r.version_problems({"control": "156.0.1.1", "fork": "154.0.8037.93"}, "154.0.8037.93") == [
        "control is 156.0.1.1, the pin is 154.0.8037.93"]


def test_network_rows_from_fixture():
    rows = r.network_rows(json.loads((FIX / "peet.json").read_text()))
    assert set(rows) == {"net.http_version", "net.ja4", "net.ja3", "net.akamai", "net.h2_order", "net.user_agent"}
    assert rows["net.ja4"] and rows["net.akamai"]
    assert rows["net.h2_order"][0].startswith(":")  # pseudo-headers first, names only


def test_stability_rows():
    rows = r.stability_rows({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 4})
    assert rows == {"stab.compared": 3, "stab.changed": ["b", "c"]}


def test_link_rows():
    assert r.link_rows({"a": 1, "b": 2}, {"a": 1, "b": 3}) == {"link.total": 2, "link.shared": ["a"]}


def test_parse_tabbed():
    assert r.parse_tabbed("Test\tResult\nWebDriver (New)\tmissing (passed)\nplain line\n") == {
        "Test": "Result", "WebDriver (New)": "missing (passed)"}


def test_parse_colon_keeps_first_and_skips_long_keys():
    text = "WebGL: ANGLE (Intel)\nWebGL: second\n" + "x" * 50 + ": no\nempty:\n"
    assert r.parse_colon(text) == {"WebGL": "ANGLE (Intel)"}


def test_line_diff_is_a_multiset_diff():
    assert r.line_diff("a\nb\nb\n", "b\nc\n") == (["a", "b"], ["c"])


def test_compare_runs_skips_volatile_and_reports_the_rest():
    a = {"rows": {"network": {"fork": {"headless": {"net.ja3": "1", "net.ja4": "x"}}}}}
    b = {"rows": {"network": {"fork": {"headless": {"net.ja3": "2", "net.ja4": "y"}}}}}
    assert r.compare_runs(a, b) == [("network/fork/headless/net.ja4", "x", "y")]


def test_render_tables_labels_and_unmeasured():
    doc = {"run": "t", "versions": {"control": "1", "fork": "1"}, "flags": {}, "errors": {"noise/fork/headed": "boom"},
           "rows": {"noise": {"control": {"headless": {"noise.canvas2d": 1}, "headed": {"noise.canvas2d": 1}},
                              "fork": {"headless": {"noise.canvas2d": 7}, "headed": None}}}}
    md = r.render_tables(doc, {})
    assert "| noise.canvas2d | 1 | 7 | unexpected |" in md
    assert "## noise / headed" in md and "UNMEASURED: boom" in md

"""verify_canvas_golden's pure parts: the golden compare and the capture document (no browser)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_canvas_golden as g  # noqa: E402


def _full(h="a"):
    return {name: h * 64 for name in g.CASE_NAMES}


def test_case_names_count_matches_expected():
    assert len(g.CASE_NAMES) == g.EXPECTED_CASES == 24
    assert len(set(g.CASE_NAMES)) == 24


def test_check_reports_each_differing_case():
    golden, now = _full("a"), _full("a")
    now["harness_ops_64"] = "b" * 64
    now["text"] = "c" * 64
    rc, lines = g.check(golden, now)
    assert rc == 1
    assert len(lines) == 2
    assert any("harness_ops_64" in l for l in lines) and any("text" in l for l in lines)


def test_check_passes_when_equal():
    assert g.check(_full(), _full()) == (0, [])


def test_check_refuses_wrong_case_count():
    now = _full()
    del now["over_cap"]
    rc, lines = g.check(_full(), now)
    assert rc == 1 and any("over_cap" in l for l in lines)
    rc, lines = g.check(now, _full())
    assert rc == 1 and any("golden" in l for l in lines)


def test_capture_output_has_only_case_hashes():
    doc = g.capture_doc(_full("d"))
    assert set(doc) == set(g.CASE_NAMES)
    assert all(len(v) == 64 for v in doc.values())


def test_capture_refuses_a_missing_or_malformed_hash():
    bad = _full()
    bad["text"] = "nothex"
    try:
        g.capture_doc(bad)
    except ValueError:
        return
    raise AssertionError("capture_doc accepted a malformed hash")

"""verify_observe.off_arm on synthetic event lists (the browser run is on the box)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import verify_observe as v  # noqa: E402

CAMOU = {"name": "Navigator.userAgent.get", "cat": v.CATEGORY}
OTHER = {"name": "ParseHTML", "cat": "blink"}


def test_off_arm_needs_zero_camou_events_and_some_other_events():
    assert v.off_arm([OTHER, OTHER]) == (True, 0, 2)
    assert v.off_arm([OTHER, CAMOU]) == (False, 1, 1)
    # an empty trace measured nothing: tracing may not have run at all
    assert v.off_arm([]) == (False, 0, 0)
    assert v.off_arm([{"name": "thread_name", "cat": "__metadata"}]) == (False, 0, 0)
    assert v.off_arm(None) == (False, None, None)


def test_hot_rows_need_exact_counts_for_both_fast_paths():
    main, top = "http://127.0.0.1:9", "http://127.0.0.1"
    hot = main + "/hot.html"
    n = 5
    exact = {("CanvasRenderingContext2D.fillRect", main, top, hot): n,
             ("CanvasRenderingContext2D.lineWidth.set", main, top, hot): n}
    assert [ok for ok, _ in v.hot_rows(exact, main, top, n, 0)] == [True, True]
    # a fast path skipping the hook shows up as a short count
    short = dict(exact)
    short[("CanvasRenderingContext2D.fillRect", main, top, hot)] = n - 2
    assert [ok for ok, _ in v.hot_rows(short, main, top, n, 0)] == [False, True]
    # --red bumps every expectation by one
    assert [ok for ok, _ in v.hot_rows(exact, main, top, n, 1)] == [False, False]
    # events from another script do not count
    other = {("CanvasRenderingContext2D.fillRect", main, top, main + "/x.js"): n,
             ("CanvasRenderingContext2D.lineWidth.set", main, top, hot): n}
    assert [ok for ok, _ in v.hot_rows(other, main, top, n, 0)] == [False, True]

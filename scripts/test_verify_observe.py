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


def test_intl_rows_need_exact_counts_per_script():
    site, main, worker = "http://127.0.0.1", "127.0.0.1:9/probe.html", "127.0.0.1:9/worker.js"
    exact = {(site, s, n): 3 for s in (main, worker) for n in v.INTL_ROWS}
    assert all(ok for ok, _ in v.intl_rows(exact, site, (main, worker), 3, 0))
    assert len(v.intl_rows(exact, site, (main, worker), 3, 0)) == 6
    # --red bumps every expectation by one
    assert not any(ok for ok, _ in v.intl_rows(exact, site, (main, worker), 3, 1))
    short = dict(exact)
    short[(site, worker, v.INTL_ROWS[0])] = 2
    assert [ok for ok, _ in v.intl_rows(short, site, (main, worker), 3, 0)].count(False) == 1
    # a blind trace fails every row instead of raising
    assert not any(ok for ok, _ in v.intl_rows(None, site, (main, worker), 3, 0))


def test_blind_arm_needs_v8_slices_and_no_counters():
    ex = {"name": "V8.Execute", "cat": "v8", "ph": "X", "pid": 1, "tid": 1, "ts": 0, "dur": 1,
          "args": {}}
    assert v.blind_arm([ex]) == (True, 1)
    assert v.blind_arm([dict(ex, args={"runtime-call-stats": {}})]) == (True, 1)
    assert v.blind_arm([dict(ex, args={"runtime-call-stats": {"Runtime_X": [1, 0.1]}})]) == (False, 1)
    # no V8 slices: v8 tracing never ran, so "blind" would have measured nothing
    assert v.blind_arm([OTHER]) == (False, 0)
    assert v.blind_arm(None) == (False, None)


def test_intl_filters_extend_the_default_recipe():
    assert v.INTL_FILTER == "-*,disabled-by-default-camou.observe,v8,disabled-by-default-v8.runtime_stats"
    assert v.NO_RCS_FILTER == "-*,disabled-by-default-camou.observe,v8"
    # bare builtin names, as the runtime-call-stats dump writes them
    assert v.INTL_ROWS == ("DateTimeFormatConstructor", "DateTimeFormatPrototypeResolvedOptions",
                           "DateTimeFormatSupportedLocalesOf")
    assert "Intl.DateTimeFormat.supportedLocalesOf" in v.PROBE and "resolvedOptions" in v.WORKER


MAIN, FRAME, TOP = "http://127.0.0.1:1", "http://localhost:1", "http://127.0.0.1"


def _api(name, n, origin=MAIN, site=TOP):
    return [{"name": name, "args": {"origin": origin, "site": site, "script": ""}} for _ in range(n)]


def _lis(typ, target, opts="", n=1, origin=MAIN, site=TOP):
    return [{"name": v.LISTENER if hasattr(v, "LISTENER") else v.observe_report.LISTENER,
             "args": {"origin": origin, "site": site, "script": "", "type": typ, "target": target,
                      "opts": opts}} for _ in range(n)]


def _exact_behaviour_trace(k=3):
    ev = []
    ev += _lis("wheel", "Window", "", k) + _lis("wheel", "Window", "passive")
    ev += _lis("keydown", "Document", "capture", 2) + _lis("visibilitychange", "Document", "", 2)
    ev += _lis("pointermove", "HTMLDivElement", "once") + _lis("devicemotion", "Window")
    ev += _lis("deviceorientation", "Window") + _lis("click", "HTMLDivElement")
    ev += _lis("message", "DedicatedWorkerGlobalScope", "", 2, site="")
    ev += _lis("touchstart", "Window", "", 1, origin=FRAME) + _lis("probe-custom-type-xyz", "Window")
    ev += _api("Performance.now", k) + _api("Performance.now", k, site="")
    ev += _api("Window.requestAnimationFrame", k) + _api("Window.setTimeout", k)
    ev += _api("Window.setInterval", k) + _api("WorkerGlobalScope.setTimeout", k, site="")
    for n in ("Document.hidden.get", "Document.visibilityState.get", "Document.webkitHidden.get",
              "Document.hasFocus", "Clipboard.writeText", "Clipboard.readText",
              "DeviceOrientationEvent.constructor", "DeviceOrientationEvent.alpha.get",
              "DeviceMotionEvent.constructor", "DeviceMotionEvent.acceleration.get"):
        ev += _api(n, k)
    for n in ("ClipboardItem.constructor", "Document.execCommand", "Accelerometer.constructor"):
        ev += _api(n, 1)
    return ev


def test_behaviour_rows_pass_on_the_exact_trace_and_fail_when_off_by_one():
    rows = v.behave_rows(_exact_behaviour_trace(), MAIN, FRAME, TOP, 3, 0)
    assert rows and all(ok for ok, _ in rows), [t for ok, t in rows if not ok]
    bumped = v.behave_rows(_exact_behaviour_trace(), MAIN, FRAME, TOP, 3, 1)
    assert [t for ok, t in bumped if ok] == ["L8 report never prints a type outside the known set"]


def test_behaviour_rows_fail_on_an_observer_without_the_slice():
    """The RED the box run must show: no events, so every positive row fails; the five
    not-allow-listed controls and the report-text row stay green."""
    rows = v.behave_rows([], MAIN, FRAME, TOP, 3, 0)
    green = sorted(t.split(":")[0] for ok, t in rows if ok)
    assert green == sorted(["L8 report never prints a type outside the known set"]
                           + [f"N1 {n} (not allow-listed)" for n in (
                               "Performance.mark", "Document.title.get", "Window.clearTimeout",
                               "Window.cancelAnimationFrame", "EventTarget.removeEventListener")])

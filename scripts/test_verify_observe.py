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


def _api(name, n, origin=MAIN, site=TOP, script=MAIN + "/behave.html"):
    return [{"name": name, "args": {"origin": origin, "site": site, "script": script}} for _ in range(n)]


def _lis(typ, target, opts="", n=1, origin=MAIN, site=TOP):
    return [{"name": v.LISTENER if hasattr(v, "LISTENER") else v.observe_report.LISTENER,
             "args": {"origin": origin, "site": site, "script": "", "type": typ, "target": target,
                      "opts": opts}} for _ in range(n)]


def _exact_behaviour_trace(k=3):
    ev = []
    ev += _lis("wheel", "DOMWindow", "", k) + _lis("wheel", "DOMWindow", "passive")
    ev += _lis("keydown", "Document", "capture", 2) + _lis("visibilitychange", "Document", "", 2)
    ev += _lis("pointermove", "Element", "once") + _lis("devicemotion", "DOMWindow")
    ev += _lis("deviceorientation", "DOMWindow") + _lis("click", "Element")
    ev += _lis("message", "DedicatedWorkerGlobalScope", "", 2, site="")
    ev += _lis("touchstart", "DOMWindow", "passive", 1, origin=FRAME) + _lis("probe-custom-type-xyz", "DOMWindow")
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
    # Blink's own construction after motion listeners exist: no script on the stack
    ev += _api("DeviceOrientationEvent.constructor", 1, script="") + _api("DeviceMotionEvent.constructor", 1, script="")
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


def test_invisibility_rows_need_native_accessors_and_identical_signatures():
    sig = {"main": {"now": "function now() { [native code] }", "ael": "function addEventListener() { [native code] }",
                    "st": "function setTimeout() { [native code] }", "keys": "a,b"},
           "worker": {"now": "function now() { [native code] }", "ael": "function addEventListener() { [native code] }",
                      "st": "function setTimeout() { [native code] }", "keys": "a"}}
    assert all(ok for ok, _ in v.invisibility_rows(sig, dict(sig)))
    patched = {**sig, "main": {**sig["main"], "now": "function now() { return 1; }"}}
    bad = [t for ok, t in v.invisibility_rows(patched, patched) if not ok]
    assert bad == ["main now.toString() is native: 'function now() { return 1; }'"]
    drift = {**sig, "main": {**sig["main"], "keys": "a,b,__camou"}}
    assert [t for ok, t in v.invisibility_rows(drift, sig) if not ok][0].startswith("page-visible signature identical")
    assert not v.invisibility_rows({}, {})[0][0]


def _dev(typ, dispatches, handlers, target="Element", trusted="false"):
    return {"name": v.DISPATCH_EVENT, "cat": v.CATEGORY, "ts": 1, "args": {
        "type": typ, "target": target, "trusted": trusted, "dispatches": str(dispatches),
        "handlers": str(handlers), "window_ms": "1"}}


def _exact_dispatch_trace():
    ev = [_dev("d1", 1, 3) for _ in range(1000)] + [_dev("d2", 1, 1) for _ in range(3)]
    ev += [_dev("d4", 1, 3, target="Worker")]
    ev += [_dev(f"d5x{i}", 1, 1) for i in range(100)]
    return ev


def test_dispatch_rows_pass_on_the_exact_trace_and_fail_when_off_by_one():
    rows = v.dispatch_rows_check(_exact_dispatch_trace(), 0, True)
    assert len(rows) == 10 and all(ok for ok, _ in rows), [t for ok, t in rows if not ok]
    bumped = v.dispatch_rows_check(_exact_dispatch_trace(), 1, True)
    assert [t for ok, t in bumped if ok] == ["D5 report never prints a custom type"]
    short = [e for e in _exact_dispatch_trace() if e["args"]["type"] != "d2"]
    assert [t.split(" ")[0] for ok, t in v.dispatch_rows_check(short, 0, True) if not ok] == ["D2", "D2"]
    # script-made events must not count as trusted ones
    assert not v.dispatch_rows_check(_exact_dispatch_trace() + [_dev("d1", 1, 3, trusted="true")], 0, True)[2][0]


def test_dispatch_rows_fail_on_an_observer_without_the_slice():
    """The RED the box run must show: no events, every positive row fails; the zero-expectation
    controls (trusted d1, removed listener) and the report-text row stay green."""
    green = [t.split(":")[0] for ok, t in v.dispatch_rows_check([], 0, True) if ok]
    assert green == ["D1 d1 trusted dispatches", "D3 listener removed before dispatch counts",
                     "D5 report never prints a custom type"]
    assert [t for ok, t in v.dispatch_rows_check([], 0, False) if ok] == ["D5 report never prints a custom type"]


def test_dispatch_production_rows_use_bounds_and_the_floor_warning():
    # 3 flushes of 256 per key, the tail unflushed; 40 of 100 distinct keys evicted and flushed
    ev = [_dev("d1", 256, 768) for _ in range(3)] + [_dev(f"d5x{i}", 1, 1) for i in range(40)]
    ev += [{"name": v.observe_report.LISTENER, "cat": v.CATEGORY, "ts": 1, "args": {
        "type": "click", "target": "Element", "script": ""}}]
    assert all(ok for ok, _ in v.dispatch_rows_check(ev, 0, False))
    assert not any(ok for ok, _ in v.dispatch_rows_check(ev, 1, False)[:3])
    low = [_dev("d1", 256, 768) for _ in range(2)]
    assert not v.dispatch_rows_check(low, 0, False)[0][0]


def test_n_dispatch_row_needs_zero_dispatch_events():
    assert v.n_dispatch_row([], 0)[0]
    assert v.n_dispatch_row([CAMOU], 0)[0]
    assert not v.n_dispatch_row([_dev("d1", 1, 1)], 0)[0]
    assert not v.n_dispatch_row([], 1)[0]  # --red


def test_trusted_mouse_row_needs_a_trusted_mousemove():
    assert v.trusted_mouse_row([_dev("mousemove", 4, 4, trusted="true")], 0)[0]
    assert not v.trusted_mouse_row([_dev("mousemove", 4, 4)], 0)[0]
    assert not v.trusted_mouse_row([], 0)[0]
    assert not v.trusted_mouse_row([_dev("mousemove", 4, 4, trusted="true")], 1)[0]

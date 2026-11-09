"""Pure check for verify_sp2b.py criterion 3, kept apart so it runs without a
browser (`python3 scripts/sp2b_analysis.py --self-test`, and test_sp2b_analysis.py).
"""

import sys

# The TARGET move in verify_sp2b.py covers 320 px in x. The bar is a fraction of
# that distance. A synchronous burst coalesces at the target (span 0 to a few
# px); a path delivered over time spans far more. Measured on 2026-10-28 (issue
# 56): 50 runs on the 156 component build gave a delivered span of 108 px at
# the least (median 250, 5 to 7 events at about 17 ms); the runs that failed
# the old bar of 0.3 (96 px) on three other binaries measured 78, 81 and 83 px.
# They are the late-first-sample tail: the first mousemove arrives about 65 to
# 80 ms in and already sits well along the path. 0.1 (32 px) is under every
# delivered span seen (2.4 times under the smallest) and far above a burst, so
# it keeps the check's purpose without failing on the tail.
#
# That distribution is not universal. The 108 px figure is a 60 fps component
# build. The Windows host's release build runs headless at about 30 fps (median
# rAF gap 33 ms), and the path is front-loaded, so the first delivered frame can
# already sit at 97% of it: 2 of 30 runs on the -11 zip measured x_span 4 and 23
# with events 15 to 20 ms apart and a last event on the target. Those are not a
# burst. So the x-span rule has an OR beside it: the events are spread in time.
SPAN_FRACTION = 0.1

# Fallback frame gap when the rAF samples are missing (60 fps).
DEFAULT_FRAME_MS = 16.7


# A window whose frames are throttled (occluded, minimised, a disconnected RDP
# client) coalesces the whole humanized path into one frame: x_span=0, a FAIL
# that measures the window, not the hook (seen in an earlier release's verify
# set; the failures passed with RDP connected). Frames are sampled by a rAF
# loop over the roughly 1.1 s the session runs; a healthy page delivers about 60.
MAX_MEDIAN_FRAME_MS = 50.0
MIN_FRAMES = 10


def throttled(frames, visibility):
    """A note when the page's frames were throttled during the run, else None.

    `frames` are rAF timestamps (ms), `visibility` every document.visibilityState
    seen. Judged only for a run that would FAIL: throttling then makes it UNMEASURED."""
    if any(v != "visible" for v in visibility):
        return f"document not visible: {sorted(set(visibility))}"
    if len(frames) < MIN_FRAMES:
        return f"only {len(frames)} animation frames (want >= {MIN_FRAMES})"
    gaps = sorted(b - a for a, b in zip(frames, frames[1:]))
    median = gaps[len(gaps) // 2]
    if median > MAX_MEDIAN_FRAME_MS:
        return f"median frame interval {median:.0f} ms (want <= {MAX_MEDIAN_FRAME_MS:.0f})"
    return None


def x_span(events):
    xs = [e["x"] for e in events]
    return max(xs) - min(xs) if xs else 0.0


def evidence(events):
    """`n=.. x=[..] t=[..]` of a recorded move: what a failing row needs to be read."""
    xs = [round(e["x"]) for e in events]
    ts = [round(e["t"], 1) for e in events]
    return f"n={len(events)} x={xs} t={ts}"


def median_gap(frames):
    """Median rAF interval (ms) of the run, DEFAULT_FRAME_MS when fewer than 3 samples."""
    gaps = sorted(b - a for a, b in zip(frames or [], (frames or [])[1:]))
    return gaps[len(gaps) // 2] if len(frames or []) >= 3 else DEFAULT_FRAME_MS


def spread_in_time(events, gap_ms):
    """n >= 3, strictly increasing timestamps, last - first > one frame gap (delivered
    over several frames, which a coalesced burst is not), and the events MOVE: at
    least two distinct x. Without that a broken hook that repeats the end point over
    time would pass. x need not be monotonic: the humanized path overshoots the
    target and returns (x=[446, 439, 417, 420] measured on the host)."""
    ts = [e["t"] for e in events]
    xs = [e["x"] for e in events]
    return (len(ts) >= 3 and all(b > a for a, b in zip(ts, ts[1:]))
            and ts[-1] - ts[0] > gap_ms
            and len(set(xs)) >= 2)


def traces_path(events, path_dx, gap_ms=DEFAULT_FRAME_MS):
    """(ok, note): the delivered mousemoves cover a real part of the path.

    Passes when x_span > bar, or when the events are spread in time (then the
    note names that rule). The note of a failing run carries the evidence: count,
    x positions and timestamps, so the next flake is read from the output.
    """
    if len(events) < 2:
        return False, "criterion 3: fewer than two events, no path to trace"
    span = x_span(events)
    if span > path_dx * SPAN_FRACTION:
        return True, ""
    if spread_in_time(events, gap_ms):
        return True, (f"criterion 3: passed by time spread (x_span={span:.0f} <= bar "
                      f"{path_dx * SPAN_FRACTION:.0f}; {events[-1]['t'] - events[0]['t']:.0f} ms "
                      f"> frame gap {gap_ms:.1f} ms); {evidence(events)}")
    return False, (f"criterion 3: events clustered, x_span={span:.0f} of path "
                   f"{path_dx:.0f}, bar {path_dx * SPAN_FRACTION:.0f}; "
                   f"{evidence(events)}")


def _self_test():
    burst = [{"x": 420.0, "y": 260.0, "t": 100.0 + i * 0.1} for i in range(7)]
    assert traces_path(burst, 320.0)[0] is False  # RED fixture: a clustered burst
    two = [{"x": 415.0, "t": 1.0}, {"x": 420.0, "t": 2.0}]
    assert traces_path(two, 320.0)[0] is False
    late_start = [{"x": x, "t": 60.0 + 17 * i}
                  for i, x in enumerate([342, 380, 400, 415, 420])]  # 78 px
    assert traces_path(late_start, 320.0)[0] is True  # the former flake
    assert traces_path([{"x": 420.0, "t": 1.0}], 320.0)[0] is False
    real = [{"x": x, "t": t} for x, t in zip([416, 416, 418, 420], [69.9, 89.7, 107.3, 123.3])]
    assert traces_path(real, 320.0, 33.2)[0] is True  # 2 of 30 on the host, 33 ms frames
    assert "time spread" in traces_path(real, 320.0, 33.2)[1]
    tight = [{"x": 420.0, "t": 100.0 + i * 1.25} for i in range(4)]  # 4 events in 3.75 ms
    assert traces_path(tight, 320.0, 33.2)[0] is False
    stuck = [{"x": 420.0, "t": 100.0 + 17 * i} for i in range(7)]  # spread in time, no movement
    assert traces_path(stuck, 320.0, 16.7)[0] is False
    for xs in ([446, 439, 417, 420], [413, 421, 420, 420]):  # overshoot paths seen on the host
        assert traces_path([{"x": float(x), "t": 100.0 + 17 * i} for i, x in enumerate(xs)], 320.0, 16.7)[0] is True
    ok, note = traces_path(burst, 320.0)
    assert "n=7" in note and "x=[420" in note
    print("sp2b_analysis self-test OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        _self_test()

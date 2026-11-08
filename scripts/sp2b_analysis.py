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
SPAN_FRACTION = 0.1


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


def traces_path(events, path_dx):
    """(ok, note): the delivered mousemoves cover a real part of the path.

    The note carries the evidence a failing run needs: count, x positions and
    timestamps, so the next flake is read from the output instead of rerun.
    """
    if len(events) < 2:
        return False, "criterion 3: fewer than two events, no path to trace"
    span = x_span(events)
    if span > path_dx * SPAN_FRACTION:
        return True, ""
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
    ok, note = traces_path(burst, 320.0)
    assert "n=7" in note and "x=[420" in note
    print("sp2b_analysis self-test OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        _self_test()

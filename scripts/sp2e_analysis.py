"""Pure checks behind verify_sp2e.py: no browser, no CDP, runnable on the Mac.

Events are page-side records; timestamps are `Event.timeStamp` in ms.
"""
import statistics


def strictly_increasing(ts):
    return all(b > a for a, b in zip(ts, ts[1:]))


def span(ts):
    return ts[-1] - ts[0] if ts else 0.0


def span_in_bounds(ts, lo, hi):
    return len(ts) >= 2 and lo <= span(ts) <= hi


def gap_stats(ts):
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    if not gaps:
        return {"n": 0}
    return {"n": len(gaps), "median": statistics.median(gaps),
            "p95": sorted(gaps)[int(0.95 * (len(gaps) - 1))], "max": max(gaps)}


def order_violations(events, wheels=3):
    """events: [(kind, timestamp)], kind 'm' (mousemove) or 'w' (wheel).
    The un-awaited move, wheel, move must arrive as m+ w{wheels} m+ with
    non-decreasing timestamps. Returns a list of violation strings (empty = ok)."""
    out = []
    runs = []
    for kind, _ in events:
        if runs and runs[-1][0] == kind:
            runs[-1][1] += 1
        else:
            runs.append([kind, 1])
    shape = [(k, n) for k, n in runs]
    if [k for k, _ in shape] != ["m", "w", "m"]:
        out.append("runs %s, want m,w,m (interleaved or missing)" % (shape,))
    else:
        if shape[1][1] != wheels:
            out.append("%d wheel events, want %d" % (shape[1][1], wheels))
    ts = [t for _, t in events]
    if any(b < a for a, b in zip(ts, ts[1:])):
        out.append("timestamps go backwards")
    return out


def self_test():
    """Fixtures incl. a deliberately interleaved log the checker must flag."""
    good = [("m", 1), ("m", 2), ("w", 3), ("w", 4), ("w", 5), ("m", 6), ("m", 7)]
    assert order_violations(good) == []
    inter = [("m", 1), ("w", 2), ("m", 3), ("w", 4), ("w", 5), ("m", 6)]
    assert order_violations(inter), "interleaved log not flagged"
    assert order_violations([("m", 1), ("w", 2), ("w", 3), ("m", 4)]), "2 wheels not flagged"
    assert order_violations([("w", 1), ("w", 2), ("w", 3), ("m", 4)]), "missing first path not flagged"
    assert strictly_increasing([1, 2, 3]) and not strictly_increasing([1, 2, 2])
    assert span_in_bounds([0, 100, 500], 80, 1200) and not span_in_bounds([0, 10], 80, 1200)
    assert gap_stats([0, 10, 20, 40])["median"] == 10
    return True

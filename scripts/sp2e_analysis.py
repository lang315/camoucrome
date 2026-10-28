"""Pure checks behind verify_sp2e.py: no browser, no CDP, runnable on the Mac.

Events are page-side records; timestamps are `Event.timeStamp` in ms.
"""
import statistics

# Page-visible span lower bound. The browser clamps a path to >= minTime
# (default 80 ms), but path[0] (offset 0) is never posted: the page sees events
# from the FIRST POSTED point, so its span is the path time minus the first
# gap, one 60 Hz recording period (16.7 ms). 1.25 periods of slack covers a
# late first event: 80 - 1.25 * 16.7 = 59.2 ms.
MIN_TIME_MS = 80
PERIOD_MS = 1000 / 60
VISIBLE_MIN_MS = MIN_TIME_MS - 1.25 * PERIOD_MS
MAX_TIME_MS = 1200
# kMaxDurationMs (cursory.h): no path, whatever the bounds, lasts longer.
HARD_CAP_MS = 10000


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
    The scheduler's guarantee is NO INTERLEAVING: each item's events are
    contiguous. The order of the items is not asserted (a wheel first waits
    for a renderer visual-state round trip, so it can reach the scheduler after
    a later move). So: the wheel notches form exactly ONE run of `wheels`
    events, and no move event sits between them; moves are then m* w{n} m*.
    Timestamps must not go backwards. Returns violation strings (empty = ok)."""
    out = []
    runs = []
    for kind, _ in events:
        if runs and runs[-1][0] == kind:
            runs[-1][1] += 1
        else:
            runs.append([kind, 1])
    wruns = [n for k, n in runs if k == "w"]
    if wruns != [wheels]:
        out.append("wheel runs %s, want one run of %d (interleaved or missing); runs=%s"
                   % (wruns, wheels, [(k, n) for k, n in runs]))
    ts = [t for _, t in events]
    if any(b < a for a, b in zip(ts, ts[1:])):
        out.append("timestamps go backwards")
    return out


# Row 10 reply deadline, from the design: booked time is capped at 10 s
# (HARD_CAP_MS); a command the cap refuses is posted at queue end + 1 ms, so its
# reply waits for the queue: at most cap + the last accepted item's own
# duration (1 s, minTime = maxTime = 1000). 15 % margin on that, plus 2 s of
# transport/scheduling slack.
OVERFLOW_PATH_S = 1.0
REPLY_DEADLINE_S = (HARD_CAP_MS / 1000 + OVERFLOW_PATH_S) * 1.15 + 2


def final_order_violations(xs, targets):
    """xs: page mousemove x values in arrival order; targets: the x each
    un-awaited command ends at, in submission order. The LAST event at each
    target is that command's final event; those must appear in submission
    order and the page's very last event must be the last target."""
    out = []
    last = {}
    for i, x in enumerate(xs):
        last[x] = i
    seen = [t for t in targets if t in last]
    if len(seen) != len(targets):
        out.append("%d of %d targets seen" % (len(seen), len(targets)))
    idx = [last[t] for t in seen]
    if any(b < a for a, b in zip(idx, idx[1:])):
        out.append("final events out of submission order: %s" % (seen,))
    if not xs or xs[-1] != targets[-1]:
        out.append("last page event %s is not the last target %s" % (xs[-1:], targets[-1]))
    return out


def tail_violations(events, target):
    """events: [(x, y, t)] in arrival order. A zero-length move to `target`
    queued behind the move that ends there: every event at `target` must be a
    contiguous tail (nothing overtook the path), timestamps non-decreasing."""
    out = []
    at = [i for i, (x, y, _) in enumerate(events) if (x, y) == target]
    if not at:
        return ["no event at the target"]
    if at != list(range(at[0], len(events))):
        out.append("events at the target are not the tail (stock overtook the path): %s of %d" % (at, len(events)))
    ts = [t for _, _, t in events]
    if any(b < a for a, b in zip(ts, ts[1:])):
        out.append("timestamps go backwards")
    return out


def reply_before(arrival, first, second):
    """arrival: reply ids in the order they came; both must be present."""
    return first in arrival and second in arrival and arrival.index(first) < arrival.index(second)


def self_test():
    """Fixtures incl. a deliberately interleaved log the checker must flag."""
    good = [("m", 1), ("m", 2), ("w", 3), ("w", 4), ("w", 5), ("m", 6), ("m", 7)]
    assert order_violations(good) == []
    assert order_violations([("m", i) for i in range(90)] + [("w", 100 + i) for i in range(3)]) == []
    inter = [("w", 1), ("m", 2), ("m", 3), ("w", 4), ("m", 5), ("w", 6)]
    assert order_violations(inter), "interleaved log not flagged"
    assert order_violations([("m", 1), ("w", 2), ("m", 3), ("w", 4), ("w", 5), ("m", 6)]), "split notches not flagged"
    assert order_violations([("m", 1), ("w", 2), ("w", 3), ("m", 4)]), "2 wheels not flagged"
    assert order_violations([("w", 1), ("w", 2), ("w", 3), ("m", 4)]) == []  # order of items is not asserted
    assert strictly_increasing([1, 2, 3]) and not strictly_increasing([1, 2, 2])
    assert span_in_bounds([0, 100, 500], 80, 1200) and not span_in_bounds([0, 10], 80, 1200)
    assert gap_stats([0, 10, 20, 40])["median"] == 10
    tg = [100 + 40 * i for i in range(14)]
    ok = [x for t in tg for x in (t - 20, t)]
    assert final_order_violations(ok, tg) == []
    # old behaviour: refused target 13 was ONE stock event that overtook the queue
    bad = [x for t in tg[:13] for x in (t - 20, t)]
    bad.insert(10, tg[13])
    assert final_order_violations(bad, tg), "overtaking stock event not flagged"
    assert reply_before([1, 2], 1, 2) and not reply_before([2, 1], 1, 2)
    assert tail_violations([(5, 5, 1), (9, 9, 2), (9, 9, 3)], (9, 9)) == []
    assert tail_violations([(9, 9, 1), (5, 5, 2), (9, 9, 3)], (9, 9)), "early target event not flagged"
    return True

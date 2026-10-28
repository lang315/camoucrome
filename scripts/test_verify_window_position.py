import verify_window_position as v


def test_tally_counts_agreeing_seeds():
    rows = [(1, {"left": 10, "top": 20}, [10, 20]), (2, {"left": 0, "top": 0}, [0, 48])]
    assert v.tally(rows) == (1, 2)

import capture_click_oracle as o


def click(t0, hold, dwell, dx=3.0, dy=-2.0, W=64, approach=(1.0, 0.0)):
    cx, cy = 500.0, 400.0
    lx, ly = cx + dx - 40 * approach[0], cy + dy - 40 * approach[1]
    moves = [[t0 - 30, lx, ly, 1, 0.0, 0.0], [t0, cx + dx, cy + dy, 1, 0.0, 0.0]]
    return {"t_show": t0 - 400, "moves": moves, "rect": [cx - W / 2, cy - W / 2, W, W], "size": W,
            "down": {"t": t0 + dwell, "x": cx + dx, "y": cy + dy, "trusted": True, "pointerType": "mouse", "button": 0, "detail": 1},
            "up": {"t": t0 + dwell + hold, "x": cx + dx, "y": cy + dy, "trusted": True, "pointerType": "mouse", "button": 0, "detail": 1}}


def human(n=120):
    return [click(1000.0 * i, 60 + (i * 7) % 90, 80 + (i * 11) % 120, dx=(i % 9) - 4, dy=(i % 7) - 3,
                  W=(16, 32, 64, 128, 320)[i % 5]) for i in range(n)]


def test_gate_passes_human_like_clicks():
    assert o.gate(human(), grid_check=True) == []


def test_gate_fails_the_cdp_red_arm():
    red = [click(1000.0 * i, 0.4, 0.3, dx=0, dy=0) for i in range(40)]
    problems = o.gate(red, grid_check=True)
    assert any("hold median" in p for p in problems)
    assert any("dwell median" in p for p in problems)
    assert any("offset SD" in p for p in problems)


def test_gate_flags_rdp_timer_grid():
    grid = [click(1000.0 * i, 15.625 * (3 + i % 6), 90) for i in range(60)]
    assert any("15.6 ms grid" in p for p in o.gate(grid, grid_check=True))
    assert not any("15.6 ms grid" in p for p in o.gate(grid, grid_check=False))


def test_knots_are_21_and_monotonic_with_p100_as_p99():
    k = o.knots(list(range(1000)))
    assert len(k) == 21 and k == sorted(k)
    assert k[0] == 0 and abs(k[-1] - 989.01) < 1e-9  # p99 of 0..999, not the max


def test_summary_drops_warmup_and_counts_sessions():
    s = o.summarize({"mac-s1": {"clicks": human(110), "scrolls": []},
                     "mac-s2": {"clicks": human(110), "scrolls": []}})
    assert s["n_sessions"] == 2 and s["n_clicks"] == 200  # 10 warm-up dropped per session
    assert set(s["offset"]) == {"along", "across", "xy_corr"}
    assert len(s["hold_ms"]) == 21 and len(s["dwell_ms"]) == 21


def test_pack_roundtrip():
    data = {"clicks": human(3)}
    assert o.unpack(o.pack_js_equivalent(data)) == data

"""verdicts() of measure_canvas_noise: the spike's P1-P5 and the redesign's S1/S2 rows."""
import measure_canvas_noise as m


def cell(**kw):
    base = {"text": "t0", "shape": "s0", "textBig": "b0", "textCpu": "c0", "solid": 1, "solidColours": 1,
            "edge": 2, "line": 3, "roundtrip": True, "copy": True, "bitmap": True, "shift": True,
            "glClear": 4, "glClearColours": 1}
    base.update(kw)
    return base


def seeded(n=8, **kw):
    return [cell(text=f"t{i}", shape=f"s{i}", textBig=f"b{i}", textCpu=f"c{i}", **kw) for i in range(1, n + 1)]


def ok(stock, unconfigured, seeds, prefix):
    """The verdict of the one row whose name starts with `prefix`."""
    hits = [v for name, v, _ in m.verdicts(stock, unconfigured, seeds) if name.startswith(prefix)]
    assert len(hits) == 1, (prefix, hits)
    return hits[0]


def test_all_pass():
    rows = m.verdicts(cell(), cell(), seeded())
    assert len(rows) == 9
    assert all(v for _, v, _ in rows), rows


def test_p1_fails_on_too_few_distinct_hashes():
    s = seeded()
    for c in s[:4]:
        c["textBig"] = "b1"
    assert ok(cell(), cell(), s, "P1 ") is False


def test_p1_fails_when_a_seed_equals_stock():
    s = seeded()
    s[0]["textBig"] = "b0"
    assert ok(cell(), cell(), s, "P1 ") is False


def test_p3_fails_on_a_flat_difference_or_round_trip():
    assert ok(cell(), cell(), seeded(solid=9), "P3 ") is False
    assert ok(cell(), cell(), seeded(roundtrip=False), "P3 ") is False


def test_p4_fails_when_a_copy_disagrees():
    assert ok(cell(), cell(), seeded(bitmap=False), "P4 ") is False


def test_p5_unmeasured_when_stock_itself_shifts_unequal():
    assert ok(cell(shift=False), cell(shift=False), seeded(), "P5 ") is None


def test_s2_text_needs_six_distinct_shape_needs_all():
    s = seeded()
    s[0]["text"] = s[1]["text"] = s[2]["text"] = "t2"
    assert ok(cell(), cell(), s, "S2 oracle text") is True     # 6 distinct of 8
    s[3]["shape"] = s[4]["shape"]
    assert ok(cell(), cell(), s, "S2 oracle shape") is False   # 7 of 8


def test_s1_fails_on_more_than_one_colour():
    assert ok(cell(), cell(), seeded(solidColours=3), "S1 ") is False
    assert ok(cell(), cell(), seeded(glClearColours=5), "S1 ") is False


def test_rule5_fails_when_unconfigured_differs_from_stock():
    assert ok(cell(), cell(text="x"), seeded(), "rule 5") is False


def test_missing_webgl_in_a_seed_makes_s1_and_p3_unmeasured_and_names_it():
    s = seeded()
    s[2] = {**s[2], "glClear": "no context"}
    del s[2]["glClearColours"]
    rows = {n[:2]: (v, d) for n, v, d in m.verdicts(cell(), cell(), s)}
    for p in ("S1", "P3"):
        v, d = rows[p]
        assert v is None and "seed 3" in d, (p, v, d)


def test_missing_webgl_in_stock_makes_s1_and_p3_unmeasured():
    stock = cell(glClear="no context")
    del stock["glClearColours"]
    rows = {n[:2]: (v, d) for n, v, d in m.verdicts(stock, cell(), seeded())}
    for p in ("S1", "P3"):
        assert rows[p][0] is None and "stock" in rows[p][1], (p, rows[p])

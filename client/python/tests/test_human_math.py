import json, math, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camoucrome import human_math as m  # noqa: E402

VEC = json.loads((pathlib.Path(__file__).resolve().parents[3] / "settings" / "human_click_vectors.json").read_text())


def stream(xs):
    it = iter(xs)
    return lambda: next(it)


def test_splitmix64_anchor():
    assert m.splitmix64(0) == 0xE220A8397B1DCDAF  # published SplitMix64 first output for state 0


def test_profile_scale_bounds_and_absent_seed():
    assert m.profile_scale(None, "hold") == 1.0
    vals = [m.profile_scale(s, "hold") for s in range(1, 2000)]
    assert 0.8 <= min(vals) and max(vals) <= 1.25 and max(vals) / min(vals) > 1.5
    assert m.profile_scale(7, "hold") != m.profile_scale(7, "offset")


def test_sample_knots_interpolates():
    k = [float(i * 10) for i in range(21)]
    assert m.sample_knots(k, 0.0) == 0.0
    assert math.isclose(m.sample_knots(k, 0.5), 100.0)
    assert math.isclose(m.sample_knots(k, 0.99999999), 200.0, rel_tol=1e-6)


def test_click_position_centre_cases():
    base = dict(x=10, y=10, w=100, h=40, n=1, bl=2, bt=2, t=False, vw=800, vh=600, scroller="document")
    model = {"along": {"a": 2.0, "b": 0.05}, "across": {"a": 1.5, "b": 0.04}}
    assert m.click_position({**base, "w": 3}, None, model, 1.0, stream([0.5] * 4)) is None
    assert m.click_position({**base, "t": True}, None, model, 1.0, stream([0.5] * 4)) is None
    assert m.click_position({**base, "n": 2}, None, model, 1.0, stream([0.5] * 4)) is None
    x, y = m.click_position(base, None, model, 1.0, stream([0.3, 0.1]))
    assert 0 <= x + 2 <= 100 and 0 <= y + 2 <= 40  # padding-box relative, inside the border box


def test_next_burst_visible_is_none():
    geo = dict(x=0, y=100, w=10, h=10, vw=800, vh=600)
    assert m.next_burst(geo, 0.3, [3.0] * 21, [200.0] * 21, stream([0.5])) is None


def test_vectors_match():
    for x, y in VEC["splitmix64"]:
        assert m.splitmix64(int(x, 16)) == int(y, 16)
    for c in VEC["profile_scale"]:
        assert math.isclose(m.profile_scale(c["seed"], c["salt"]), c["scale"], rel_tol=1e-12)
    for c in VEC["sample_knots"]:
        assert math.isclose(m.sample_knots(c["knots"], c["u"]), c["value"], rel_tol=1e-12)
    for c in VEC["edge_entry"]:
        assert all(math.isclose(a, b, abs_tol=1e-9) for a, b in zip(m.edge_entry(c["w"], c["h"], *c["u"]), c["point"]))
    for c in VEC["click_position"]:
        got = m.click_position(c["geo"], c["last"], c["model"], c["scale"], stream(c["rand"]))
        assert (got is None) == (c["position"] is None)
        if got:
            assert all(math.isclose(a, b, abs_tol=1e-9) for a, b in zip(got, c["position"]))
    for c in VEC["next_burst"]:
        got = m.next_burst(c["geo"], c["landing"], c["burst"], c["pause"], stream(c["rand"]))
        assert (got is None) == (c["out"] is None) and (got is None or (got[0] == c["out"][0] and math.isclose(got[1], c["out"][1])))

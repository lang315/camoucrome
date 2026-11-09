"""camoucrome.human: click, hold and type on a patchright Page, against a fake page that records every call.
Virtual clock: each recorded call carries the time the injected sleep has advanced to, so dwell, overlap and
the "at most 2 keys down" rule are read from the timeline, not from the implementation."""
import asyncio
import pathlib
import random
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camoucrome import human  # noqa: E402
from camoucrome import human_params as P  # noqa: E402

BOX = {"x": 100.0, "y": 200.0, "width": 200.0, "height": 40.0}


class Flat:
    """rng with no randomness: every draw is the median, no rollover, no pause, no typo."""

    def random(self):
        return 0.99

    def gauss(self, mu, sigma):
        return 0.0


class Boom(Exception):
    pass


class Fake:
    """A sync patchright-shaped page. `fail_at`: raise Boom from the Nth sleep."""

    def __init__(self, fail_at=None):
        self.t = 0.0
        self.calls = []  # (t_ms, name, args)
        self.sleeps = 0
        self.fail_at = fail_at
        self.pos = (0.0, 0.0)
        self.viewport_size = {"width": 1280, "height": 720}
        page = self

        class Mouse:
            def move(self, x, y, **kw):
                page.pos = (x, y)
                page.rec("move", x, y)

            def down(self, **kw):
                page.rec("down", page.pos)

            def up(self, **kw):
                page.rec("up", page.pos)

        class Keyboard:
            def down(self, key):
                page.rec("kdown", key)

            def up(self, key):
                page.rec("kup", key)

            def insert_text(self, text):
                page.rec("insert", text)

        class Loc:
            first = None

            def __init__(self, sel):
                self.sel = sel
                self.first = self

            def scroll_into_view_if_needed(self, **kw):
                page.rec("scroll", self.sel)

            def bounding_box(self, **kw):
                return dict(BOX)

            def focus(self, **kw):
                page.rec("focus", self.sel)

        self.mouse, self.keyboard, self._loc = Mouse(), Keyboard(), Loc

    def locator(self, sel):
        return self._loc(sel)

    def rec(self, name, *args):
        self.calls.append((self.t, name, args))

    def sleep(self, seconds):
        self.sleeps += 1
        if self.fail_at is not None and self.sleeps >= self.fail_at:
            raise Boom("sleep failed")
        self.t += seconds * 1000.0

    def names(self, *keep):
        return [(n, a[0] if a else None) for _, n, a in self.calls if n in keep]


class AFake(Fake):
    """The async-API shape: every method a coroutine."""

    def __init__(self, **kw):
        super().__init__(**kw)
        for obj in (self.mouse, self.keyboard):
            for name in [n for n in dir(obj) if not n.startswith("_")]:
                setattr(obj, name, _acoro(getattr(obj, name)))
        base = self._loc

        class ALoc(base):
            pass

        for name in ("scroll_into_view_if_needed", "bounding_box", "focus"):
            setattr(ALoc, name, _acoro_method(getattr(base, name)))
        self._loc = ALoc

    async def asleep(self, seconds):
        Fake.sleep(self, seconds)


def _acoro(bound):
    async def inner(*a, **kw):
        return bound(*a, **kw)
    return inner


def _acoro_method(fn):
    async def inner(self, *a, **kw):
        return fn(self, *a, **kw)
    return inner


def typed(page, text, **kw):
    human.type(page, "#f", text, sleep=page.sleep, **kw)


def key_events(page):
    """[(t, 'kdown'|'kup', key)] without Shift: the typed keys only."""
    return [(t, n, a[0]) for t, n, a in page.calls if n in ("kdown", "kup") and a[0] != "Shift"]


def down_counts(page):
    n, worst = 0, 0
    for _, name, a in page.calls:
        if name == "kdown" and a[0] != "Shift":
            n += 1
        elif name == "kup" and a[0] != "Shift":
            n -= 1
        worst = max(worst, n)
    return worst, n


def field_value(page):
    v = ""
    for _, n, a in page.calls:
        if n == "insert":
            v += a[0]
        elif n == "kdown":
            k = a[0]
            if k == "Backspace":
                v = v[:-1]
            elif k == "Enter":
                v += "\n"
            elif k == "Tab":
                v += "\t"
            elif len(k) == 1:
                v += k
    return v


def test_hello_world_exact_sequence():
    page = Fake()
    human.type(page, "#f", "Hello, World!", rng=Flat(), sleep=page.sleep)
    want = [("focus", "#f")]
    for ch in "Hello, World!":
        if ch.isupper() or ch == "!":
            want += [("kdown", "Shift"), ("kdown", ch), ("kup", ch), ("kup", "Shift")]
        else:
            want += [("kdown", ch), ("kup", ch)]
    assert page.names("focus", "kdown", "kup", "insert") == want


def test_same_seed_same_trace():
    a, b = Fake(), Fake()
    typed(a, "The quick brown fox, Jumps!", rng=random.Random(5))
    typed(b, "The quick brown fox, Jumps!", rng=random.Random(5))
    assert a.calls == b.calls


def test_every_key_has_a_positive_dwell():
    page = Fake()
    typed(page, "dwell time matters, Really.", rng=random.Random(1))
    downs = {}
    n = 0
    for t, name, key in key_events(page):
        if name == "kdown":
            downs.setdefault(key, []).append(t)
        else:
            t0 = downs[key].pop(0)
            assert t - t0 >= P.DWELL_MIN_MS - 1e-6, (key, t - t0)
            n += 1
    assert n > 20
    assert all(not v for v in downs.values())


def test_shift_brackets_and_shared_press():
    page = Fake()
    typed(page, "aBCd", rng=Flat())
    seq = [(n, k) for _, n, k in [(t, n, a[0]) for t, n, a in page.calls if n in ("kdown", "kup")]]
    assert seq == [("kdown", "a"), ("kup", "a"), ("kdown", "Shift"), ("kdown", "B"), ("kup", "B"), ("kdown", "C"),
                   ("kup", "C"), ("kup", "Shift"), ("kdown", "d"), ("kup", "d")]
    t = {(n, k): tt for tt, n, k in [(t, n, a[0]) for t, n, a in page.calls if n in ("kdown", "kup")]}
    assert t[("kdown", "B")] - t[("kdown", "Shift")] >= P.SHIFT_LEAD_MEDIAN_MS - 1e-6
    assert t[("kup", "Shift")] > t[("kup", "C")]


def test_off_layout_rune_is_insert_text_without_keys():
    page = Fake()
    typed(page, "aéb", rng=Flat())
    assert page.names("kdown", "insert") == [("kdown", "a"), ("insert", "é"), ("kdown", "b")]


def test_crlf_is_one_enter():
    page = Fake()
    typed(page, "a\r\nb", rng=Flat())
    assert page.names("kdown") == [("kdown", "a"), ("kdown", "Enter"), ("kdown", "b")]


def test_overlap_rate_matches_calibrated_chance():
    page = Fake()
    rnd = random.Random(11)
    text = ""
    prev = ""
    while len(text) < 3000:  # no repeated letter: a physical key cannot go down twice
        c = rnd.choice("abcdefghijklmnopqrstuvwxyz")
        if c != prev:
            text += c
            prev = c
    typed(page, text, rng=random.Random(3))
    ev = key_events(page)
    pairs = overlaps = 0
    last_up = {}
    order = [(n, k) for _, n, k in ev]
    for i, (n, k) in enumerate(order):
        if n == "kdown" and i > 0:
            pairs += 1
            if order[i - 1][0] == "kdown":  # previous key still down when this one went down
                overlaps += 1
    rate = overlaps / pairs
    assert abs(rate - P.ROLLOVER_CHANCE) < 0.04, rate
    assert rate > 0.05


def test_never_three_keys_down_and_all_released():
    for seed in range(20):
        page = Fake()
        typed(page, "Rollover keys, Typed FAST; with: Shifted! pairs? (ok) " * 4, rng=random.Random(seed), typos=True)
        worst, left = down_counts(page)
        assert worst <= 2, (seed, worst)
        assert left == 0
        ups = [a[0] for _, n, a in page.calls if n == "kup"]
        downs = [a[0] for _, n, a in page.calls if n == "kdown"]
        assert sorted(ups) == sorted(downs)


def test_rollover_overlap_keeps_next_down_after_prev_down_plus_10ms():
    for seed in range(10):
        page = Fake()
        typed(page, "qwertyuiopasdfghjklzxcvbnm" * 20, rng=random.Random(seed))
        ds = [(t, k) for t, n, k in key_events(page) if n == "kdown"]
        for (t0, _), (t1, _) in zip(ds, ds[1:]):
            assert t1 - t0 >= 10 - 1e-6


def test_typos_off_by_default_has_no_backspace():
    page = Fake()
    typed(page, "abcdefghijklmnopqrstuvwxyz " * 30, rng=random.Random(2))
    assert "Backspace" not in [a[0] for _, n, a in page.calls if n == "kdown"]


def test_typos_final_text_exact_and_backspace_present():
    text = "The Quick brown fox, jumps over 13 lazy dogs! (really)\né and a tab\tend.\n"
    seen_bs = 0
    for seed in range(40):
        page = Fake()
        typed(page, text, rng=random.Random(seed), typos=True)
        assert field_value(page) == text, seed
        seen_bs += page.names("kdown").count(("kdown", "Backspace"))
    assert seen_bs > 20


def test_backspace_is_a_real_key_with_dwell():
    page = Fake()
    typed(page, "abcdefghijklmnopqrstuvwxyz" * 20, rng=random.Random(4), typos=True)
    ev = [(t, n) for t, n, k in key_events(page) if k == "Backspace"]
    assert ev and ev[0][1] == "kdown"
    downs = [t for t, n in ev if n == "kdown"]
    ups = [t for t, n in ev if n == "kup"]
    assert len(downs) == len(ups)
    assert all(u - d >= P.BACKSPACE_DWELL_MIN_MS - 1e-6 for d, u in zip(downs, ups))


def test_typo_waits_the_notice_delay_before_backspace():
    page = Fake()
    typed(page, "abcdefghijklmnopqrstuvwxyz" * 20, rng=random.Random(4), typos=True)
    ev = key_events(page)
    for i, (t, n, k) in enumerate(ev):
        if k == "Backspace" and n == "kdown" and ev[i - 1][2] != "Backspace" and ev[i - 1][1] == "kup":
            assert t - ev[i - 1][0] >= P.TYPO_NOTICE_MIN_MS - 1e-6
            return
    pytest.fail("no first Backspace found")


def test_release_everything_on_error():
    # fail while Shift and a key are down: the sleep after the first shifted keyDown
    for fail_at in range(1, 12):
        page = Fake(fail_at=fail_at)
        with pytest.raises(Boom):
            typed(page, "ABC def GHI", rng=Flat())
        downs = [a[0] for _, n, a in page.calls if n == "kdown"]
        ups = [a[0] for _, n, a in page.calls if n == "kup"]
        assert sorted(ups) == sorted(downs), fail_at


def test_click_press_point_inner_70_percent_settle_and_hold():
    xs, ys = [], []
    for seed in range(200):
        page = Fake()
        human.click(page, "#b", rng=random.Random(seed), sleep=page.sleep)
        moves = [a for _, n, a in page.calls if n == "move"]
        down = [(t, a[0]) for t, n, a in page.calls if n == "down"]
        up = [(t, a[0]) for t, n, a in page.calls if n == "up"]
        assert len(down) == len(up) == 1
        assert down[0][1] == up[0][1] == moves[-1]
        x, y = moves[-1]
        xs.append(x)
        ys.append(y)
        assert BOX["x"] + 0.15 * BOX["width"] - 1e-9 <= x <= BOX["x"] + 0.85 * BOX["width"] + 1e-9
        assert BOX["y"] + 0.15 * BOX["height"] - 1e-9 <= y <= BOX["y"] + 0.85 * BOX["height"] + 1e-9
        t_move = [t for t, n, a in page.calls if n == "move"][-1]
        assert down[0][0] - t_move >= P.SETTLE_MIN_MS - 1e-6
        assert P.CLICK_HOLD_MIN_MS - 1e-6 <= up[0][0] - down[0][0] <= P.CLICK_HOLD_MAX_MS + 1e-6
    assert len(set(round(x, 3) for x in xs)) > 150  # not the centre, not a grid
    assert page.names("scroll")


def test_second_click_makes_no_first_move_seed():
    page = Fake()
    human.click(page, "#b", rng=random.Random(1), sleep=page.sleep)
    n1 = len([1 for _, n, a in page.calls if n == "move"])
    human.click(page, "#b", rng=random.Random(1), sleep=page.sleep)
    n2 = len([1 for _, n, a in page.calls if n == "move"]) - n1
    assert (n1, n2) == (2, 1)


def test_hold_tremor_and_release_at_last_point():
    page = Fake()
    human.hold(page, "#b", 1500, rng=random.Random(9), sleep=page.sleep)
    names = [n for _, n, a in page.calls if n in ("down", "up")]
    assert names == ["down", "up"]
    tdown = [t for t, n, a in page.calls if n == "down"][0]
    tup, pup = [(t, a[0]) for t, n, a in page.calls if n == "up"][0]
    assert tup - tdown == pytest.approx(1500, abs=1e-6)
    held = [(a[0], a[1]) for t, n, a in page.calls if n == "move" and tdown < t < tup]
    assert len(held) >= 3
    px, py = [a[0] for t, n, a in page.calls if n == "down"][0]
    for x, y in held:
        assert abs(x - px) <= P.TREMOR_PX + 1e-9 and abs(y - py) <= P.TREMOR_PX + 1e-9
    assert pup == held[-1]


def test_hold_releases_the_button_on_error():
    page = Fake()
    page.fail_at = None
    seen = {"n": 0}
    real = page.sleep

    def sleeper(s):
        seen["n"] += 1
        if seen["n"] == 3 + 0 and page.names("down"):
            raise Boom("x")
        real(s)

    with pytest.raises(Boom):
        human.hold(page, "#b", 5000, rng=random.Random(9), sleep=sleeper)
    names = [n for _, n, a in page.calls if n in ("down", "up")]
    assert names == ["down", "up"]


def test_async_page_same_trace_as_sync():
    a, b = Fake(), AFake()
    typed(a, "Async? Yes, Same.", rng=random.Random(8), typos=True)

    async def go():
        await human.type(b, "#f", "Async? Yes, Same.", typos=True, rng=random.Random(8), sleep=b.asleep)
    asyncio.run(go())
    assert a.calls == b.calls


def test_async_click_and_hold_and_release_on_cancel():
    b = AFake()

    async def go():
        await human.click(b, "#b", rng=random.Random(1), sleep=b.asleep)
        await human.hold(b, "#b", 400, rng=random.Random(2), sleep=b.asleep)
    asyncio.run(go())
    assert [n for _, n, a in b.calls if n in ("down", "up")] == ["down", "up", "down", "up"]

    c = AFake()

    async def cancelled(seconds):
        if c.names("kdown", "kup") and len(c.calls) > 8:
            raise asyncio.CancelledError()
        Fake.sleep(c, seconds)

    async def go2():
        await human.type(c, "#f", "SHIFTED text", rng=Flat(), sleep=cancelled)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(go2())
    downs = [a[0] for _, n, a in c.calls if n == "kdown"]
    ups = [a[0] for _, n, a in c.calls if n == "kup"]
    assert sorted(downs) == sorted(ups)


def test_package_exports_human():
    import camoucrome
    assert camoucrome.human is human
    assert "human" in camoucrome.__all__

"""SP2d client A (`human_click`) and B (`launch(human_click=True)`): offline
fakes only, so no browser and no driver are needed here."""
import asyncio
import importlib
import pathlib
import sys
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import camoucrome  # noqa: E402
import camoucrome.human_math as human_math  # noqa: E402
import camoucrome.launcher as launcher  # noqa: E402

# `camoucrome` re-exports the *function* `human_click`, which shadows the
# module attribute; the module itself stays reachable through sys.modules.
hc = importlib.import_module("camoucrome.human_click")

class Obj:
    pass


GEO = dict(x=100, y=900, w=120, h=40, n=1, bl=1, bt=1, t=False, vw=1280, vh=720, scroller="document")


class FakeMouse:
    def __init__(self, log): self.log = log
    async def move(self, x, y, **k): self.log.append(("move", round(x), round(y)))
    async def wheel(self, dx, dy): self.log.append(("wheel", dx, dy))


class FakePage:
    def __init__(self, log): self.mouse = FakeMouse(log); self._browser_context = object()


class FakeTarget:
    """Stands in for an impl Locator: evaluate() returns successive geometries;
    click() raises `errors` in order and returns `("result", call number)`."""
    def __init__(self, geos, log, errors=None):
        self.geos, self.log, self.page = list(geos), log, FakePage(log)
        self.errors = list(errors or [])
    async def evaluate(self, js, arg=None, timeout=None, isolatedContext=True):
        assert isolatedContext is True
        return self.geos.pop(0) if len(self.geos) > 1 else self.geos[0]
    async def click(self, **kw):
        self.log.append(("click", kw))
        if self.errors:
            raise self.errors.pop(0)
        return ("result", len(self.log))


def run(coro):
    return asyncio.run(coro)


def test_passthrough_when_caller_positions():
    log = []
    t = FakeTarget([GEO], log)
    run(hc._act(t, t.page, {"position": {"x": 1, "y": 2}}, state=None, rand=lambda: 0.5, sleep=lambda s: asyncio.sleep(0)))
    assert log == [("click", {"position": {"x": 1, "y": 2}})]


def test_scrolls_with_wheel_then_clicks_with_scroll_none():
    log = []
    near = {**GEO, "y": 200}
    t = FakeTarget([GEO, GEO, near], log)
    run(hc._act(t, t.page, {}, state={"scale": 1.0, "windows": True}, rand=lambda: 0.4, sleep=lambda s: asyncio.sleep(0)))
    kinds = [e[0] for e in log]
    assert kinds[0] == "move" and "wheel" in kinds
    clicks = [e for e in log if e[0] == "click"]
    assert len(clicks) == 1
    assert "trial" not in clicks[0][1] and clicks[0][1]["scroll"] == "none"
    assert "position" in clicks[0][1] and "delay" not in clicks[0][1]


def test_null_geometry_falls_back_unchanged():
    log = []
    t = FakeTarget([None], log)
    run(hc._act(t, t.page, {"timeout": 1234}, state=None, rand=lambda: 0.5, sleep=lambda s: asyncio.sleep(0)))
    assert log == [("click", {"timeout": 1234})]


def test_nested_scroller_falls_back():
    log = []
    t = FakeTarget([{**GEO, "scroller": "nested"}], log)
    run(hc._act(t, t.page, {}, state=None, rand=lambda: 0.5, sleep=lambda s: asyncio.sleep(0)))
    assert log == [("click", {})]


def test_no_progress_falls_back_after_two_bursts():
    log = []
    t = FakeTarget([GEO], log)  # never moves
    run(hc._act(t, t.page, {}, state={"scale": 1.0, "windows": True}, rand=lambda: 0.4, sleep=lambda s: asyncio.sleep(0)))
    assert sum(1 for e in log if e[0] == "wheel") == 2 and log[-1] == ("click", {})


class ScrollingMouse(FakeMouse):
    """Each wheel deltaY moves the target up the viewport, like real scrolling."""
    def __init__(self, log, geo): super().__init__(log); self.geo, self.tops = geo, []
    async def wheel(self, dx, dy):
        self.log.append(("wheel", dx, dy))
        self.geo["y"] -= dy
        self.tops.append(self.geo["y"])


class CopyingTarget(FakeTarget):
    """evaluate() returns a fresh dict, like a real isolated-world read."""
    async def evaluate(self, js, arg=None, timeout=None, isolatedContext=True):
        return dict(await super().evaluate(js, arg, timeout, isolatedContext))


def test_wheel_continues_past_first_visibility_to_the_landing_depth():
    """The final top must sit at the landing depth, not near the bottom of the
    viewport, where the target first becomes fully visible."""
    log = []
    geo = {**GEO, "y": 3000, "h": 40}
    t = CopyingTarget([geo], log)
    t.page.mouse = ScrollingMouse(log, geo)
    run(hc._act(t, t.page, {}, state={"scale": 1.0, "windows": True}, rand=lambda: 0.0,
                sleep=lambda s: asyncio.sleep(0)))
    tops = t.page.mouse.tops
    first = next((i for i, y in enumerate(tops) if 0 <= y and y + geo["h"] <= geo["vh"]), None)
    assert first is not None and first < len(tops) - 1, f"stopped at the first fully visible position: {tops}"
    assert abs(geo["y"] - 0.2 * geo["vh"]) < 100, f"final top {geo['y']}"


class PageEndMouse(FakeMouse):
    """Scrolling stops at 380, 300 px above the clamped L=680: the page end."""
    def __init__(self, log, geo): super().__init__(log); self.geo = geo
    async def wheel(self, dx, dy):
        self.log.append(("wheel", dx, dy))
        self.geo["y"] = min(self.geo["y"] - dy, 380)


def _pinned_landing(monkeypatch):
    # The shipped landing knots top out at 0.2891, so a high rand cannot clamp
    # L; pin the knots to the 0.95 the clamped-goal defect needs.
    monkeypatch.setattr(hc.T, "LANDING", [0.95] * 21)


def test_a_clamped_landing_arrives_within_one_notch(monkeypatch):
    """L clamps to vh - h, so a notch cannot put a visible target inside a
    50 px window; it must still arrive, not oscillate to the notch budget."""
    _pinned_landing(monkeypatch)
    log = []
    geo = {**GEO, "y": 1200}
    t = CopyingTarget([geo], log)
    t.page.mouse = ScrollingMouse(log, geo)
    run(hc._act(t, t.page, {}, state={"scale": 1.0, "windows": True}, rand=lambda: 0.5,
                sleep=lambda s: asyncio.sleep(0)))
    goal = min(0.95 * geo["vh"], geo["vh"] - geo["h"])
    assert 0 <= geo["y"] and geo["y"] + geo["h"] <= geo["vh"], f"not visible: {geo['y']}"
    assert abs(geo["y"] - goal) < 100, f"final top {geo['y']}, want within 100 of {goal}"
    notches = sum(abs(e[2]) for e in log if e[0] == "wheel") / 100
    assert notches < 10, f"{notches} notches"
    clicks = [e[1] for e in log if e[0] == "click"]
    assert len(clicks) == 1 and clicks[0]["scroll"] == "none" and "position" in clicks[0], clicks


def test_a_visible_target_at_the_page_end_is_clicked_not_fallen_back(monkeypatch):
    """The target cannot be brought to L=680; held visible at 380, it is
    clicked where the page end left it, not handed to the stock click."""
    _pinned_landing(monkeypatch)
    log = []
    geo = {**GEO, "y": -50}
    t = CopyingTarget([geo], log)
    t.page.mouse = PageEndMouse(log, geo)
    run(hc._act(t, t.page, {}, state={"scale": 1.0, "windows": True}, rand=lambda: 0.5,
                sleep=lambda s: asyncio.sleep(0)))
    assert geo["y"] == 380, f"page end left the target at {geo['y']}"
    clicks = [e[1] for e in log if e[0] == "click"]
    assert len(clicks) == 1 and clicks[0]["scroll"] == "none" and "position" in clicks[0], clicks


def test_launch_refuses_flag_without_humanize():
    for cfg in ({}, {"humanize:enabled": False}):
        with pytest.raises(ValueError, match="humanize:enabled"):
            launcher.launch(None, "/x", config=cfg, human_click=True)


# --- controller rulings -----------------------------------------------------

def test_seed_zero_counts_and_everything_but_a_uint32_int_is_absent():
    for seed, want in ((0, human_math.profile_scale(0, "offset")), (True, 1.0), (-1, 1.0),
                       (2 ** 32, 1.0), ("5", 1.0), (None, 1.0), (1.5, 1.0)):
        ctx = Obj()
        hc.install_state(ctx, {} if seed is None else {"humanize:seed": seed}, None)
        assert hc._state[ctx]["scale"] == want, seed


@pytest.mark.parametrize("caller_timeout", [0, 5000])
def test_the_first_attempt_is_the_real_click_at_the_fixed_timeout(caller_timeout):
    log = []
    t = FakeTarget([{**GEO, "y": 100}], log)
    result = run(hc._act(t, t.page, {"timeout": caller_timeout}, state=None,
                         rand=lambda: 0.5, sleep=lambda s: asyncio.sleep(0)))
    clicks = [e[1] for e in log if e[0] == "click"]
    assert len(clicks) == 1
    assert "trial" not in clicks[0]
    assert clicks[0]["timeout"] == hc.T.TRIAL_TIMEOUT_MS == 2000
    assert clicks[0]["scroll"] == "none" and "position" in clicks[0]
    assert result == ("result", 1)


def test_one_timeout_earns_one_corrective_burst_and_one_retry():
    log = []
    t = FakeTarget([{**GEO, "y": 100}], log, errors=[TimeoutError("Timeout 2000ms exceeded")])
    result = run(hc._act(t, t.page, {}, state=None, rand=lambda: 0.5,
                         sleep=lambda s: asyncio.sleep(0)))
    assert [e[0] for e in log] == ["click", "wheel", "click"]
    clicks = [e[1] for e in log if e[0] == "click"]
    assert [c["timeout"] for c in clicks] == [2000, 2000]
    assert result == ("result", 3)


def test_two_timeouts_fall_back_to_the_stock_click():
    log = []
    t = FakeTarget([{**GEO, "y": 100}], log,
                   errors=[TimeoutError("Timeout 2000ms exceeded")] * 2)
    run(hc._act(t, t.page, {"timeout": 5000}, state=None, rand=lambda: 0.5,
                sleep=lambda s: asyncio.sleep(0)))
    clicks = [e[1] for e in log if e[0] == "click"]
    assert len(clicks) == 3
    assert [c["timeout"] for c in clicks[:2]] == [2000, 2000]
    assert all("trial" not in c for c in clicks[:2])
    assert clicks[2] == {"timeout": 5000}


def test_a_non_timeout_error_is_not_retried_or_fallen_back():
    log = []
    t = FakeTarget([{**GEO, "y": 100}], log, errors=[RuntimeError("Target closed")])
    with pytest.raises(RuntimeError, match="Target closed"):
        run(hc._act(t, t.page, {}, state=None, rand=lambda: 0.5,
                    sleep=lambda s: asyncio.sleep(0)))
    assert [e[0] for e in log] == ["click"]


class LaunchContext:
    def __init__(self):
        self._impl_obj = types.SimpleNamespace()
        self.events = []
    def on(self, event, fn): self.events.append(event)
    def close(self): pass


class LaunchChromium:
    def launch_persistent_context(self, user_data_dir, **kw):
        self.kw = kw
        return LaunchContext()


class LaunchPlaywright:
    def __init__(self): self.chromium = LaunchChromium()


@pytest.fixture(autouse=True)
def temp_dirs_under_tmp_path(tmp_path, monkeypatch):
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))


def test_launch_true_calls_install_despite_the_parameter_name(monkeypatch):
    calls = []
    monkeypatch.setattr(hc, "install", lambda *a: calls.append(("install",) + a))
    monkeypatch.setattr(hc, "install_state", lambda *a: calls.append(("install_state",) + a))
    cfg = {"humanize:enabled": True}
    pw = LaunchPlaywright()
    ctx = launcher.launch(pw, "/x/chrome", config=cfg, human_click=True)
    assert calls == [("install", ctx._impl_obj, cfg, None)]
    ctx.close()


def test_launch_false_only_records_the_profile_state(monkeypatch):
    calls = []
    monkeypatch.setattr(hc, "install", lambda *a: calls.append(("install",) + a))
    monkeypatch.setattr(hc, "install_state", lambda *a: calls.append(("install_state",) + a))
    cfg = {"humanize:enabled": True}
    pw = LaunchPlaywright()
    ctx = launcher.launch(pw, "/x/chrome", config=cfg)
    assert calls == [("install_state", ctx._impl_obj, cfg, None)]
    ctx.close()


def _fake_impl_module():
    """A package whose `_frame.Frame` can be wrapped without patchright."""
    api = types.ModuleType("fakeimpl.api")
    Ctx = type("Ctx", (), {})
    Ctx.__module__ = "fakeimpl.api"
    api.Ctx = Ctx

    frame_mod = types.ModuleType("fakeimpl._frame")
    calls = []

    class Frame:
        def __init__(self, page): self._page = page
        async def _click(self, selector, **kw): calls.append((selector, kw))
        def locator(self, selector):
            assert selector == "button"
            return types.SimpleNamespace(first=self.target)

    frame_mod.Frame = Frame
    sys.modules["fakeimpl"] = types.ModuleType("fakeimpl")
    sys.modules["fakeimpl.api"] = api
    sys.modules["fakeimpl._frame"] = frame_mod
    return api.Ctx, Frame, calls


class BPage:
    def __init__(self, ctx, log):
        self._browser_context = ctx
        self.mouse = FakeMouse(log)


def test_b_wrapper_counts_only_the_human_path():
    Ctx, Frame, calls = _fake_impl_module()
    ctx = Ctx()
    log = []
    frame = Frame(BPage(ctx, log))
    frame.target = FakeTarget([{**GEO, "y": 100}], log)
    hc.install(ctx, {"humanize:enabled": True}, None)
    hc.wrapper_hits = 0

    run(frame._click("button"))
    assert hc.wrapper_hits == 1
    assert len(calls) == 1 and calls[0][1]["scroll"] == "none"
    assert calls[0][1]["timeout"] == hc.T.TRIAL_TIMEOUT_MS

    run(frame._click("button", position={"x": 1, "y": 2}))  # pass-through
    assert hc.wrapper_hits == 1 and calls[-1] == ("button", {"position": {"x": 1, "y": 2}})


def test_b_acts_only_for_contexts_launched_with_the_flag():
    """A launch (install_state only) must not be humanized by a process where
    some other launch used human_click=True (install)."""
    Ctx, Frame, calls = _fake_impl_module()
    b_ctx, a_ctx = Ctx(), Ctx()
    hc.install(b_ctx, {"humanize:enabled": True}, None)
    hc.install_state(a_ctx, {"humanize:enabled": True}, None)
    hc.wrapper_hits = 0

    a_log = []
    a_frame = Frame(BPage(a_ctx, a_log))
    a_frame.target = FakeTarget([{**GEO, "y": 100}], a_log)
    run(a_frame._click("button"))
    assert calls == [("button", {})] and a_log == []   # straight to the stock click
    assert hc.wrapper_hits == 0

    b_log = []
    b_frame = Frame(BPage(b_ctx, b_log))
    b_frame.target = FakeTarget([{**GEO, "y": 100}], b_log)
    run(b_frame._click("button"))
    b_calls = calls[1:]
    assert hc.wrapper_hits == 1 and b_calls[-1][1]["scroll"] == "none"


def _public_locator(module_name, geos=None):
    class Page:
        def __init__(self):
            self._browser_context = Obj()
            self.mouse = FakeMouse([])
    class Locator:
        def __init__(self):
            self._impl_obj = types.SimpleNamespace(
                _frame=types.SimpleNamespace(_page=Page()),
                evaluate=FakeTarget(geos or [{**GEO, "y": 100}], []).evaluate,
                click=self._click)
            self.clicks, self.stock = [], []
        async def _click(self, **kw): self.clicks.append(kw)
        def _sync(self, coro): return asyncio.run(coro)
    Locator.__module__ = module_name
    if module_name.split(".")[1] == "sync_api":
        Locator.click = lambda self, **kw: (self.stock.append(kw), "stock")[1]
    else:
        async def click(self, **kw):
            self.stock.append(kw)
            return "stock"
        Locator.click = click
    return Locator()


def test_human_click_is_a_coroutine_for_the_async_api():
    loc = _public_locator("patchright.async_api._generated")
    coro = hc.human_click(loc, rand=lambda: 0.5)
    assert asyncio.iscoroutine(coro)
    run(coro)
    assert loc.clicks and loc.clicks[-1]["scroll"] == "none"


def test_human_click_runs_and_returns_none_for_the_sync_api():
    loc = _public_locator("patchright.sync_api._generated")
    assert hc.human_click(loc, rand=lambda: 0.5) is None
    assert loc.clicks and loc.clicks[-1]["scroll"] == "none"


def test_a_sync_fallback_calls_the_public_locator_click():
    loc = _public_locator("patchright.sync_api._generated", geos=[None])
    assert hc.human_click(loc, timeout=50, rand=lambda: 0.5) == "stock"
    assert loc.clicks == [] and loc.stock == [{"timeout": 50}]


def test_a_async_fallback_calls_the_public_locator_click():
    loc = _public_locator("patchright.async_api._generated", geos=[None])
    assert run(hc.human_click(loc, timeout=50, rand=lambda: 0.5)) == "stock"
    assert loc.clicks == [] and loc.stock == [{"timeout": 50}]


def _fake_errors_module():
    """A driver-shaped errors module: Error with name/stack, and rewrite_error."""
    mod = types.ModuleType("fakeerrors")

    class Error(Exception):
        def __init__(self, message):
            self._message, self._name, self._stack = message, None, None
            super().__init__(message)
        @property
        def name(self): return self._name
        @property
        def stack(self): return self._stack

    class TimeoutError(Error):
        pass

    def rewrite_error(error, message):
        new = type(error)(message)
        new._name, new._stack = error.name, error.stack
        return new

    TimeoutError.__module__ = "fakeerrors"
    mod.TimeoutError, mod.rewrite_error = TimeoutError, rewrite_error
    sys.modules["fakeerrors"] = mod
    return mod


def _sync_raising(loc, error):
    def _sync(coro):
        coro.close()
        raise error
    loc._sync = _sync
    return loc


def test_a_sync_error_inside_the_act_reads_as_locator_click():
    mod = _fake_errors_module()
    err = mod.TimeoutError("Locator._sync: Timeout 2000ms exceeded.")
    err._name, err._stack = "TimeoutError", "driver stack tail"
    loc = _sync_raising(_public_locator("patchright.sync_api._generated"), err)

    with pytest.raises(mod.TimeoutError) as ei:
        hc.human_click(loc, rand=lambda: 0.5)
    assert str(ei.value) == "Locator.click: Timeout 2000ms exceeded."
    assert type(ei.value) is mod.TimeoutError
    assert ei.value.name == "TimeoutError" and ei.value.stack == "driver stack tail"
    assert ei.value.__cause__ is None


def test_a_sync_error_without_the_prefix_is_reraised_unchanged():
    mod = _fake_errors_module()
    err = mod.TimeoutError("Timeout 2000ms exceeded.")
    loc = _sync_raising(_public_locator("patchright.sync_api._generated"), err)

    with pytest.raises(mod.TimeoutError) as ei:
        hc.human_click(loc, rand=lambda: 0.5)
    assert ei.value is err


def test_a_sync_error_whose_module_lacks_rewrite_error_is_unchanged():
    err = RuntimeError("Locator._sync: Target closed")
    loc = _sync_raising(_public_locator("patchright.sync_api._generated"), err)

    with pytest.raises(RuntimeError) as ei:
        hc.human_click(loc, rand=lambda: 0.5)
    assert ei.value is err


# --- round 2: delivery, corrective notch, tall targets ----------------------

def _driver_timeout(message):
    """A class NAMED TimeoutError, as the driver's is; not the builtin."""
    class TimeoutError(Exception):
        pass
    return TimeoutError(message)


DELIVERED = ("Timeout 2000ms exceeded.\n"
             "  - <header> intercepts pointer events\n"
             "  - retrying click action\n"
             "  - performing click action")
NOT_DELIVERED = ("Timeout 2000ms exceeded.\n"
                 "  - <header> intercepts pointer events\n"
                 "  - retrying click action")
PERFORMING_BEFORE_RETRY = ("Timeout 2000ms exceeded.\n"
                           "  - performing click action\n"
                           "  - <header> intercepts pointer events\n"
                           "  - retrying click action\n"
                           "  - waiting for element to be visible")


def test_a_timeout_after_delivery_started_is_not_retried():
    log = []
    t = FakeTarget([{**GEO, "y": 100}], log, errors=[_driver_timeout(DELIVERED)])
    with pytest.raises(Exception) as ei:
        run(hc._act(t, t.page, {}, state=None, rand=lambda: 0.5, sleep=lambda s: asyncio.sleep(0)))
    assert type(ei.value).__name__ == "TimeoutError"
    assert [e[0] for e in log] == ["click"]


def test_a_timeout_before_delivery_still_retries():
    log = []
    t = FakeTarget([{**GEO, "y": 100}], log, errors=[_driver_timeout(NOT_DELIVERED)])
    result = run(hc._act(t, t.page, {}, state=None, rand=lambda: 0.5,
                         sleep=lambda s: asyncio.sleep(0)))
    assert [e[0] for e in log] == ["click", "wheel", "click"]
    assert result == ("result", 3)


def test_performing_before_the_last_retry_is_not_delivery():
    """An earlier 'performing' line (before the last retry) means the press was
    not dispatched for the attempt that timed out: retry."""
    log = []
    t = FakeTarget([{**GEO, "y": 100}], log, errors=[_driver_timeout(PERFORMING_BEFORE_RETRY)])
    result = run(hc._act(t, t.page, {}, state=None, rand=lambda: 0.5,
                         sleep=lambda s: asyncio.sleep(0)))
    assert [e[0] for e in log] == ["click", "wheel", "click"]
    assert result == ("result", 3)


@pytest.mark.parametrize("y, delta", [(100, -100), (600, 100)])
def test_the_corrective_notch_moves_away_from_the_cover(y, delta):
    log = []
    t = FakeTarget([{**GEO, "y": y}], log, errors=[_driver_timeout(NOT_DELIVERED)])
    run(hc._act(t, t.page, {}, state=None, rand=lambda: 0.5, sleep=lambda s: asyncio.sleep(0)))
    assert [e for e in log if e[0] == "wheel"] == [("wheel", 0, delta)]


@pytest.mark.parametrize("y, direction", [(100, -1), (600, 1)])
def test_the_second_attempt_records_the_point_after_the_corrective_notch(y, direction):
    log = []
    t = FakeTarget([{**GEO, "y": y}], log, errors=[_driver_timeout(NOT_DELIVERED)])
    run(hc._act(t, t.page, {}, state=None, rand=lambda: 0.5, sleep=lambda s: asyncio.sleep(0)))
    pos = [e[1] for e in log if e[0] == "click"][1]["position"]
    assert hc._last[t.page] == (GEO["x"] + GEO["bl"] + pos["x"],
                                y + GEO["bt"] + pos["y"] - 100 * direction)


class BounceTarget(FakeTarget):
    """Geometry alternates between two non-visible tops, as a tall target does
    when each direction lands it just out of view."""
    def __init__(self, ys, log):
        super().__init__([{**GEO, "y": ys[0], "h": 700}], log)
        self.ys, self.i = list(ys), 0
    async def evaluate(self, js, arg=None, timeout=None, isolatedContext=True):
        y = self.ys[self.i % len(self.ys)]
        self.i += 1
        return {**GEO, "y": y, "h": 700}


def test_a_bouncing_tall_target_stops_at_the_stuck_limit():
    log = []
    t = BounceTarget([70, -30], log)
    run(hc._act(t, t.page, {}, state={"scale": 1.0, "windows": True},
                rand=lambda: 0.5, sleep=lambda s: asyncio.sleep(0)))
    wheels = [e for e in log if e[0] == "wheel"]
    assert 0 < len(wheels) <= 4, f"{len(wheels)} wheels"  # two bursts + the corrective notch
    assert log[-1] == ("click", {})  # the stock fallback

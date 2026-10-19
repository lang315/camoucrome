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

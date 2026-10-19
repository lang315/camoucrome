"""SP2d client side (spec §4): wheel the element into view, then click an
off-centre point with scroll="none". The dwell, hold and approach path are the
browser's (humanize:enabled). A never passes `delay`."""
import asyncio
import importlib
import random
import weakref

from . import _click_tables as T
from . import human_math as m

_state = weakref.WeakKeyDictionary()   # impl BrowserContext -> {"scale", "windows"}
_b_contexts = weakref.WeakSet()        # impl BrowserContext launched with human_click=True
_last = weakref.WeakKeyDictionary()    # impl Page -> (x, y) last point this client sent
PASS_THROUGH = ("position", "force", "trial")
wrapper_hits = 0                       # B: human-path invocations, read by later tasks

UINT32_MAX = 2 ** 32 - 1


def _seed(eff):
    """humanize:seed only when it is a real uint32; bool is an int subclass but
    not a seed, and any other shape is treated as absent (scale 1.0)."""
    v = eff.get("humanize:seed")
    return v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= UINT32_MAX else None


async def _geometry(target, timeout):
    try:
        return await target.evaluate(T.GEOMETRY_JS, None, timeout=timeout, isolatedContext=True)
    except Exception:  # noqa: BLE001 - any failure means "fall back to the stock click"
        return None


async def _wheel(page, notches, windows, rand, sleep):
    if windows:
        await page.mouse.wheel(0, notches * 100)  # SP2c splits it into notches
        return
    for _ in range(abs(notches)):
        await page.mouse.wheel(0, 100 if notches > 0 else -100)
        await sleep((18 + 42 * rand()) / 1000)


async def _act(target, page, opts, state, rand, sleep=asyncio.sleep, click=None, fallback=None):
    """`target` is an impl Locator (or the B wrapper's `.first`), `page` its impl
    Page. `click(**kw)` performs the final driver click (A: target.click; B: the
    original Frame._click bound to the selector). `fallback()` is the stock
    click a covered target falls back to (A: the public locator.click, so the
    error keeps the stock API name)."""
    click = click or target.click
    fallback = fallback or (lambda: click(**opts))
    if any(k in opts for k in PASS_THROUGH):
        return await fallback()
    timeout = opts.get("timeout")
    geo = await _geometry(target, timeout)
    if geo is None or geo["scroller"] != "document" or geo["x"] < 0 or geo["x"] + geo["w"] > geo["vw"]:
        return await fallback()
    state = state or {"scale": 1.0, "windows": False}
    if not m.visible(geo):
        pt = (geo["vw"] * (0.1 + 0.8 * rand()), geo["vh"] * (0.1 + 0.8 * rand()))
        await page.mouse.move(*pt)
        _last[page] = pt
        landing = m.sample_knots(T.LANDING, rand())
        sent, stuck = 0, 0
        while True:
            burst = m.next_burst(geo, landing, T.BURST, T.PAUSE, rand, T.MAX_NOTCHES - sent)
            if burst is None:
                break
            if sent >= T.MAX_NOTCHES or stuck >= T.NO_PROGRESS_BURSTS:
                if m.visible(geo):  # the page end: arrived as far as it can
                    break
                return await fallback()
            await _wheel(page, burst[0], state["windows"], rand, sleep)
            sent += abs(burst[0])
            await sleep(burst[1] / 1000)
            before, geo = geo["y"], await _geometry(target, timeout)
            if geo is None:
                return await fallback()
            stuck = stuck + 1 if abs(geo["y"] - before) < 1 else 0
    pos = m.click_position(geo, _last.get(page), T.OFFSET, state["scale"], rand)  # scale = profile_scale(seed, "offset")
    extra = {"scroll": "none"}
    if pos is not None:
        extra["position"] = {"x": pos[0], "y": pos[1]}
    attempt_timeout = T.TRIAL_TIMEOUT_MS  # fixed: the first attempt's timeout, never the caller's
    for attempt in range(2):
        try:
            result = await click(**{**opts, **extra, "timeout": attempt_timeout})
        except Exception as e:  # noqa: BLE001 - only a driver timeout is retried
            if type(e).__name__ != "TimeoutError":
                # the click may already have been delivered: a second one would double-click
                raise
            if attempt == 1:
                return await fallback()
            await _wheel(page, 1, state["windows"], rand, sleep)  # a covered target: one corrective burst
            await sleep(0.2)
        else:
            if pos is not None:
                _last[page] = (geo["x"] + geo["bl"] + pos[0], geo["y"] + geo["bt"] + pos[1])
            return result


_FALLBACK = object()  # A mode: _act returns it instead of calling the stock click


def human_click(locator, *, rand=None, **opts):
    impl = locator._impl_obj
    page = impl._frame._page

    async def stock():
        return _FALLBACK

    act = _act(impl, page, opts, _state.get(page._browser_context), rand or random.random,
               fallback=stock)
    if type(locator).__module__.split(".")[1] == "sync_api":
        result = locator._sync(act)
        return locator.click(**opts) if result is _FALLBACK else result

    async def run():
        result = await act
        # the public click, not the impl one: its error names Locator.click
        return await locator.click(**opts) if result is _FALLBACK else result

    return run()


def install_state(ctx_impl, config, preset):
    """Every launch(): record the profile's offset scale and claimed OS, so A
    sees the seed even without B."""
    from . import launcher  # deferred: launcher imports this module
    eff = launcher.effective_keys(config, preset)
    _state[ctx_impl] = {"scale": m.profile_scale(_seed(eff), "offset"),
                        "windows": launcher.claimed_os(config, preset) == "Windows"}


def install(ctx_impl, config, preset):
    """B: wrap Frame._click once per process; act only for contexts launched
    with human_click=True (A only records state in install_state)."""
    install_state(ctx_impl, config, preset)
    _b_contexts.add(ctx_impl)
    frame_mod = importlib.import_module(type(ctx_impl).__module__.rsplit(".", 1)[0] + "._frame")
    cls = frame_mod.Frame
    if getattr(cls, "_camou_human_click", False):
        return
    orig = cls._click

    async def _click(self, selector, **kw):
        global wrapper_hits
        page = self._page
        bc = page._browser_context if page is not None else None
        st = _state.get(bc) if bc is not None and bc in _b_contexts else None
        if st is None or any(k in kw for k in PASS_THROUGH):
            return await orig(self, selector, **kw)
        wrapper_hits += 1
        first = self.locator(selector).first
        return await _act(first, page, kw, st, random.random,
                          click=lambda **k: orig(self, selector, **k))

    cls._click = _click
    cls._camou_human_click = True

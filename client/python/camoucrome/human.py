"""Human-like input on a patchright Page: click, hold and type.

    from camoucrome import human
    human.click(page, "#buy")
    human.hold(page, "#hold-me", 1200)           # ms
    human.type(page, "#name", "Hello, World!", typos=True)

With the async API, `await human.click(page, ...)`: each function returns a coroutine when the page is async.

The model is the one in client/go/rodclient (human.go, page.go) plus key rollover and typos. Every timing comes from
human_params.py (generated from settings/human_input.json; lognormal, truncated by redrawing, never flat uniform).
Input goes only through page.mouse.move/down/up and page.keyboard.down/up/insert_text: no page JS, no Runtime.enable.
The fork humanizes the mouse path browser-side; the keys are timed here.

How it is built: a plan (a generator) yields the next input, wait or lookup; one small runner per API (sync, async)
performs it and remembers what is down, so an error or a cancel releases every key and the button, the same way in both.
Randomness: one seeded random.Random per page; `rng=` replaces it (tests).
"""
import asyncio
import inspect
import math
import random
import time
import unicodedata
import weakref

from . import human_params as P

POLL_MS = 50
POLL_TRIES = 600  # 30 s, as rodclient's op timeout

# ---------------------------------------------------------------------------------------------------- distributions


def lognormal(rng, median, sigma, lo, hi):
    """median*exp(sigma*N(0,1)) inside [lo, hi] by redrawing."""
    for _ in range(32):
        d = median * math.exp(sigma * rng.gauss(0, 1))
        if lo <= d <= hi:
            return d
    return median


def _dwell(rng):
    return lognormal(rng, P.DWELL_MEDIAN_MS, P.DWELL_SIGMA, P.DWELL_MIN_MS, P.DWELL_MAX_MS)


def _punct(ch):
    return ch.isspace() or unicodedata.category(ch)[0] in "PS"


def flight(rng, prev, nxt):
    """keyDown to keyDown for the pair: the digraph median when the table has it, else the overall one."""
    tok = lambda c: "space" if c == " " else c.lower()  # noqa: E731
    med = P.DIGRAPH_FLIGHT_MS.get(tok(prev) + tok(nxt), P.FLIGHT_MEDIAN_MS)
    d = lognormal(rng, med, P.FLIGHT_SIGMA, P.FLIGHT_MIN_MS, P.FLIGHT_MAX_MS)
    if _punct(prev):
        d *= P.FLIGHT_AFTER_PUNCT
    if _us(nxt) and _us(nxt)[1]:
        d *= P.FLIGHT_BEFORE_SHIFT
    if prev.isspace() and not nxt.isspace() and rng.random() < P.PAUSE_CHANCE:
        d += lognormal(rng, P.PAUSE_MEDIAN_MS, P.PAUSE_SIGMA, P.PAUSE_MIN_MS, P.PAUSE_MAX_MS)
    return d


# ------------------------------------------------------------------------------------------------------ US layout
_SHIFTED = ')!@#$%^&*(' + '_+{}|:"<>?~'
_BASE = '0123456789' + "-=[]\\;',./`"
_SHIFT_TO_BASE = dict(zip(_SHIFTED, _BASE))
_SHIFT_TO_BASE.update({c: c.lower() for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"})
_BASE_TO_SHIFT = {b: s for s, b in _SHIFT_TO_BASE.items()}


def _us(ch):
    """(Playwright key, needs Shift) for a rune on a US layout; None for runes off it."""
    if ch in "\r\n":
        return "Enter", False
    if ch == "\t":
        return "Tab", False
    if len(ch) == 1 and " " <= ch <= "~":
        return ch, ch in _SHIFT_TO_BASE
    return None


def _phys(ch):
    return _SHIFT_TO_BASE.get(ch, ch)


_ROWS = (("`1234567890-=", 0.0), ("qwertyuiop[]\\", 1.5), ("asdfghjkl;'", 1.75), ("zxcvbnm,./", 2.25))


def _build_neighbours():
    pos = {c: (r, off + i) for r, (row, off) in enumerate(_ROWS) for i, c in enumerate(row)}
    out = {}
    for c, (r, x) in pos.items():
        out[c] = [o for o, (r2, x2) in pos.items()
                  if o != c and abs(r2 - r) <= 1 and abs(x2 - x) < (1.01 if r2 == r else 1.0)]
    for c in "vbn":  # the space bar sits under these
        out[c].append(" ")
    out[" "] = list("vbn")
    return out


_NEIGHBOURS = _build_neighbours()


def _neighbour(rng, ch):
    """A US-QWERTY neighbour of ch (same row or adjacent row, same Shift state), or None."""
    shifted = ch in _SHIFT_TO_BASE
    cands = [_BASE_TO_SHIFT.get(n) if shifted else n for n in _NEIGHBOURS.get(_phys(ch), [])]
    cands = [c for c in cands if c and c != ch]
    return cands[int(rng.random() * len(cands))] if cands else None


# --------------------------------------------------------------------------------------------------------- typing
def _plain(ch):
    """A character a typo may touch or sweep into a run: a US key that is not Enter or Tab."""
    k = _us(ch)
    return k is not None and k[0] not in ("Enter", "Tab")


def _strokes(rng, text, typos):
    """The keys to press, in order. A stroke is [char, key|None, shifted, kind, gap]; kind 'key', 'insert' or 'bs';
    gap names a special wait before it ('notice', 'retype'), else None."""
    chars = []
    for c in text:
        if c == "\n" and chars and chars[-1] == "\r":
            continue  # CRLF is one Enter
        chars.append(c)

    def stroke(c, gap=None):
        k = _us(c)
        return [c, k[0] if k else None, bool(k and k[1]), "key" if k else "insert", gap]

    out, i = [], 0
    while i < len(chars):
        c = chars[i]
        if typos and _plain(c) and rng.random() < P.TYPO_RATE:
            wrong = _neighbour(rng, c)
            if wrong:
                r, n = rng.random(), 1
                for p in P.TYPO_RUN_LEN_PROBS[:-1]:
                    if r < p:
                        break
                    r -= p
                    n += 1
                run = [c]
                while len(run) < n and i + len(run) < len(chars) and _plain(chars[i + len(run)]):
                    run.append(chars[i + len(run)])
                out.append(stroke(wrong))
                out += [stroke(x) for x in run[1:]]
                out += [["", "Backspace", False, "bs", "notice" if j == 0 else None] for j in range(len(run))]
                out += [stroke(x, "retype" if j == 0 else None) for j, x in enumerate(run)]
                i += len(run)
                continue
        out.append(stroke(c))
        i += 1
    return out


def plan_type(rng, text, typos=False):
    """The timed keyboard script for text: [(ms, op)] in time order, op = ('kdown'|'kup'|'insert', arg).

    Times are absolute from the first stroke. At most 2 typed keys are down at once (Shift is a modifier, not
    counted); a keyUp is never before its keyDown plus the dwell; rollover sends the next keyDown before the
    previous keyUp (plain keys, no Shift change, never insertText or Backspace, never the same physical key)."""
    ss = _strokes(rng, text, typos)
    ev = []  # (time, prio, seq, op): ups before downs at the same time

    def add(t, op):
        ev.append((t, 0 if op[0] == "kup" else 1, len(ev), op))

    prev = None
    prev_down = prev_up = prev2_up = sh_up = 0.0
    shift = False
    for k, s in enumerate(ss):
        ch, key, shifted, kind, gap = s
        roll = False
        if prev is None:
            t = 0.0
        elif gap == "notice":
            t = prev_up + lognormal(rng, P.TYPO_NOTICE_MEDIAN_MS, P.TYPO_NOTICE_SIGMA, P.TYPO_NOTICE_MIN_MS,
                                    P.TYPO_NOTICE_MAX_MS)
        elif gap == "retype":
            t = prev_up + lognormal(rng, P.TYPO_RETYPE_MEDIAN_MS, P.TYPO_RETYPE_SIGMA, P.TYPO_RETYPE_MIN_MS,
                                    P.TYPO_RETYPE_MAX_MS)
        elif kind == "bs":
            t = prev_down + lognormal(rng, P.BACKSPACE_FLIGHT_MEDIAN_MS, P.BACKSPACE_FLIGHT_SIGMA,
                                      P.BACKSPACE_FLIGHT_MIN_MS, P.BACKSPACE_FLIGHT_MAX_MS)
        else:
            if (kind == "key" and prev[3] == "key" and prev[2] == shifted and _phys(prev[0]) != _phys(ch)
                    and rng.random() < P.ROLLOVER_CHANCE):
                ov = lognormal(rng, P.ROLLOVER_OVERLAP_MEDIAN_MS, P.ROLLOVER_OVERLAP_SIGMA,
                               P.ROLLOVER_OVERLAP_MIN_MS, P.ROLLOVER_OVERLAP_MAX_MS)
                t, roll = max(prev_up - ov, prev_down + 10.0), True
            else:
                t = prev_down + flight(rng, prev[0], ch)
        if not roll and prev is not None:
            t = max(t, prev_up)  # keys do not overlap unless rolled
        t = max(t, prev2_up)  # never a third key down
        if kind == "key" and shifted:
            if not shift:
                lead = lognormal(rng, P.SHIFT_LEAD_MEDIAN_MS, P.SHIFT_LEAD_SIGMA, P.SHIFT_LEAD_MIN_MS,
                                 P.SHIFT_LEAD_MAX_MS)
                t = max(t, max(prev_up, sh_up) + lead)
                add(t - lead, ("kdown", "Shift"))
                shift = True
        else:
            t = max(t, sh_up)
        if kind == "insert":
            add(t, ("insert", ch))
            up = t
        else:
            d = (lognormal(rng, P.BACKSPACE_DWELL_MEDIAN_MS, P.BACKSPACE_DWELL_SIGMA, P.BACKSPACE_DWELL_MIN_MS,
                           P.BACKSPACE_DWELL_MAX_MS) if kind == "bs" else _dwell(rng))
            up = t + d
            add(t, ("kdown", key))
            add(up, ("kup", key))
        if shift and not (k + 1 < len(ss) and ss[k + 1][3] == "key" and ss[k + 1][2]):
            sh_up = max(up, prev_up) + lognormal(rng, P.SHIFT_RELEASE_MEDIAN_MS, P.SHIFT_RELEASE_SIGMA,
                                                 P.SHIFT_RELEASE_MIN_MS, P.SHIFT_RELEASE_MAX_MS)
            add(sh_up, ("kup", "Shift"))
            shift = False
        prev2_up, prev_up, prev_down, prev = prev_up, up, t, s
    ev.sort()
    return [(t, op) for t, _, _, op in ev]


# ---------------------------------------------------------------------------------------------------------- plans
# A plan yields ("sleep", ms) | ("scroll"|"box"|"focus", selector) | ("viewport",) | ("move", x, y) | ("down",) |
# ("up",) | ("kdown"|"kup"|"insert", arg); the runner sends back the lookup's result.


class _State:
    def __init__(self, rng):
        self.rng = rng or random.Random()
        self.moved = False


_states = weakref.WeakKeyDictionary()


def _state(page, rng):
    st = _states.get(page)
    if st is None:
        st = _states[page] = _State(rng)
    elif rng is not None:
        st.rng = rng
    return st


def _axis(rng, lo, hi):
    c, w = (lo + hi) / 2, hi - lo
    if w < P.CLICK_MIN_BOX:
        return c
    for _ in range(32):
        v = c + rng.gauss(0, 1) * w * P.CLICK_SPREAD
        if abs(v - c) <= P.CLICK_INNER * w:
            return v
    return c


def _start_point(rng, vp):
    hx, hy = 300, 200
    if vp:
        if 0 < vp["width"] // 2 < hx:
            hx = vp["width"] // 2
        if 0 < vp["height"] // 2 < hy:
            hy = vp["height"] // 2
    lx, ly = min(50, hx // 2), min(50, hy // 2)
    return float(rng.randint(lx, hx)), float(rng.randint(ly, hy))


def _approach(st, selector):
    """Find, scroll into view, make the first-move seed if needed, move to a press point, settle."""
    yield ("scroll", selector)
    for _ in range(POLL_TRIES):
        box = yield ("box", selector)
        if box and box["width"] > 0 and box["height"] > 0:
            break
        yield ("sleep", POLL_MS)
    else:
        raise TimeoutError(f"camoucrome.human: {selector!r} has no box")
    if not st.moved:
        x0, y0 = _start_point(st.rng, (yield ("viewport",)))
        yield ("move", x0, y0)
        st.moved = True
    x = _axis(st.rng, box["x"], box["x"] + box["width"])
    y = _axis(st.rng, box["y"], box["y"] + box["height"])
    yield ("move", x, y)
    yield ("sleep", lognormal(st.rng, P.SETTLE_MEDIAN_MS, P.SETTLE_SIGMA, P.SETTLE_MIN_MS, P.SETTLE_MAX_MS))
    return x, y


def _click(st, selector):
    yield from _approach(st, selector)
    yield ("down",)
    yield ("sleep", lognormal(st.rng, P.CLICK_HOLD_MEDIAN_MS, P.CLICK_HOLD_SIGMA, P.CLICK_HOLD_MIN_MS,
                              P.CLICK_HOLD_MAX_MS))
    yield ("up",)


def _hold(st, selector, ms):
    x, y = yield from _approach(st, selector)
    yield ("down",)
    left = float(ms)
    while left > 0:
        w = min(left, lognormal(st.rng, P.TREMOR_MEDIAN_MS, P.TREMOR_SIGMA, P.TREMOR_MIN_MS, P.TREMOR_MAX_MS))
        yield ("sleep", w)
        left -= w
        if left > 0:
            dx = max(-P.TREMOR_PX, min(P.TREMOR_PX, st.rng.gauss(0, 1) * P.TREMOR_SIGMA_PX))
            dy = max(-P.TREMOR_PX, min(P.TREMOR_PX, st.rng.gauss(0, 1) * P.TREMOR_SIGMA_PX))
            yield ("move", x + dx, y + dy)
    yield ("up",)  # the mouse is where the last tremor move left it


def _type(st, selector, text, typos):
    yield ("focus", selector)
    now = 0.0
    for t, op in plan_type(st.rng, text, typos):
        if t > now:
            yield ("sleep", t - now)
            now = t
        yield op


# --------------------------------------------------------------------------------------------------------- runners
def _is_async(page):
    return inspect.iscoroutinefunction(page.mouse.move)


def _loc(page, sel):
    return page.locator(sel).first


class _Down:
    """What is held, so a failure can let go of it."""

    def __init__(self):
        self.keys, self.button = [], False

    def seen(self, op):
        n = op[0]
        if n == "kdown":
            self.keys.append(op[1])
        elif n == "kup" and op[1] in self.keys:
            self.keys.remove(op[1])
        elif n == "down":
            self.button = True
        elif n == "up":
            self.button = False


def _call(page, op):
    """The page call for op, as a (function, args) pair; the same for sync and async."""
    n = op[0]
    if n == "move":
        return page.mouse.move, op[1:]
    if n == "down":
        return page.mouse.down, ()
    if n == "up":
        return page.mouse.up, ()
    if n == "kdown":
        return page.keyboard.down, op[1:]
    if n == "kup":
        return page.keyboard.up, op[1:]
    if n == "insert":
        return page.keyboard.insert_text, op[1:]
    if n == "scroll":
        return _loc(page, op[1]).scroll_into_view_if_needed, ()
    if n == "box":
        return _loc(page, op[1]).bounding_box, ()
    if n == "focus":
        return _loc(page, op[1]).focus, ()
    raise ValueError(op)


def _run(page, plan, sleep):
    held = _Down()
    try:
        res = None
        while True:
            try:
                op = plan.send(res)
            except StopIteration:
                return
            res = None
            if op[0] == "sleep":
                sleep(op[1] / 1000.0)
            elif op[0] == "viewport":
                res = page.viewport_size
            else:
                fn, args = _call(page, op)
                res = fn(*args)
                held.seen(op)
    except BaseException:
        for k in reversed(held.keys):
            try:
                page.keyboard.up(k)
            except Exception:
                pass
        if held.button:
            try:
                page.mouse.up()
            except Exception:
                pass
        raise


async def _arun(page, plan, sleep):
    held = _Down()
    try:
        res = None
        while True:
            try:
                op = plan.send(res)
            except StopIteration:
                return
            res = None
            if op[0] == "sleep":
                await sleep(op[1] / 1000.0)
            elif op[0] == "viewport":
                res = page.viewport_size
            else:
                fn, args = _call(page, op)
                res = await fn(*args)
                held.seen(op)
    except BaseException:
        for k in reversed(held.keys):
            try:
                await page.keyboard.up(k)
            except Exception:
                pass
        if held.button:
            try:
                await page.mouse.up()
            except Exception:
                pass
        raise


def _go(page, plan, sleep):
    if _is_async(page):
        return _arun(page, plan, sleep or asyncio.sleep)
    return _run(page, plan, sleep or time.sleep)


def click(page, selector, *, rng=None, sleep=None):
    """Move to a press point in the inner 70% of the element, settle, press, hold tens of ms, release."""
    return _go(page, _click(_state(page, rng), selector), sleep)


def hold(page, selector, ms, *, rng=None, sleep=None):
    """Like click, but keep the button down for ms milliseconds, with a 1-2 px tremor; released at the last point."""
    return _go(page, _hold(_state(page, rng), selector, ms), sleep)


def type(page, selector, text, typos=False, *, rng=None, sleep=None):  # noqa: A001 - the name of the contract
    """Focus the element and type text with dwell, digraph flights, real Shift and key rollover.
    typos=True also makes occasional neighbour-key typos and corrects them with Backspace; the final text is exact."""
    return _go(page, _type(_state(page, rng), selector, text, typos), sleep)

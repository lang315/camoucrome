# SP2c: humanized wheel (notches) — design

SP2c is the first of three sub-projects the owner asked for on 2026-10-17:
"real input instead of node clicks", ported from Camoufox's `humanize`. The
owner chose all four gaps offered and the order **wheel, then click, then
Cursory**:

| # | Sub-project | Layer | This spec |
|---|---|---|---|
| 1 | **SP2c — wheel notches** | browser, `input_handler.cc` | **yes** |
| 2 | human click helper (off-centre point, humanized approach, down→up hold), the replacement for `element.click()` in automation code | `client/` (Python, Go, Node) | no, own spec |
| 3 | Cursory port: recorded human trajectories replace SP2b's Bézier, kept LGPLv3 in its own directory (owner decision 2026-10-17) | browser, `components/camoucfg` | no, own spec |

Making JavaScript's `HTMLElement.click()` itself produce trusted events was
ruled out: stock Chrome reports `isTrusted == false` there, so changing it is
a page-visible deviation (rules 2 and 4). Automation code replaces the call
with sub-project 2's helper instead.

The pin is Chrome `154.0.8037.93`. Line numbers below were read from the
build box checkout (`0aec35868d`) on 2026-10-17.

## Problem

`Input.dispatchMouseEvent` with `type: mouseWheel` is how every driver
scrolls (`page.mouse.wheel`, and patchright's wheel path). The CDP handler
builds one event for the whole delta
(`content/browser/devtools/protocol/input_handler.cc:471-487`):

- `delta_x/y` = the full requested delta, in one event;
- `wheel_ticks_x/y` = ±1 whatever the magnitude;
- `delta_units = kScrollByPrecisePixel` — touchpad-style, which scrolls
  without the smooth-scroll animation a mouse wheel gets;
- a `kPhaseBegan` event, then a zero-delta `kPhaseEnded` follow-up
  (`InjectWheelEvent`, `:709-740`).

Blink derives the page-visible `wheelDelta` from the ticks
(`third_party/blink/renderer/core/events/wheel_event.cc:107-124`,
`ticks * 120`), so `mouse.wheel(0, 300)` yields one `wheel` event with
`deltaY 300` and `wheelDeltaY -120` and an instant jump. A real Windows mouse
turning three notches yields three events of one tick each. Each tick is 3
lines × `100/3` px = 100 px
(`ui/events/blink/web_input_event_builders_win.cc:299-335`), and each one is
animated. Event count, the `wheelDelta`/`deltaY` ratio and the scroll
animation all separate the two.

Camoufox closes this in Juggler (`Page.dispatchWheelEvent`, `humanize` on)
by splitting a scroll into notches 18–60 ms apart. Its per-notch numbers
(`deltaMode 1`, 3 lines, `DOMMouseScroll.detail 3`) are Firefox's encoding
and do not transfer: Chrome reports wheel in pixels. The rule (notch size,
rounding, cadence) transfers; the encoding comes from measuring stock Chrome.

## Goal and success criteria

With `humanize:enabled` set and an effective OS of Windows, a CDP wheel
scroll reaches the page as stock Chrome 154 on Windows delivers the same
number of physical notches. That covers per-event `deltaX/Y`, `deltaMode`,
`wheelDeltaX/Y` and `isTrusted`, the event count, and whether scrolling
animates. Everything else stays byte-identical to stock.

Success is measured by four checks:
- the host oracle (§2) shows the real and CDP arms differ, so the
  measurement has something to measure;
- `verify_sp2c.py` reaches its expected row count on WSL, with its RED rows
  failing on `main` and on the gate mutant;
- `QuantizeWheel` unit tests pass;
- the host-native arm matches the oracle leaf by leaf; this arm needs a
  Windows rebuild, the owner's call.

## Design

### 1. Behaviour (`input_handler.cc`)

**Gate.** Both must hold, read in this order:
1. `camoucfg::GetBool(GlobalScope(), keys::kHumanizeEnabled)` is true;
2. the effective OS is Windows: `camoucfg::ClaimedOs(GlobalScope())`, or,
   when that is `kUnknown` (nothing claimed), the build's own
   `BUILDFLAG(IS_WIN)`. `ClaimedOs`'s own comment says a caller needing the
   real OS asks the platform.

Otherwise the event takes today's path untouched (rule 5). A claimed macOS
or Linux keeps the CDP shape. Those encodings were not measured, and the
owner scoped SP2c to Windows (2026-10-17). Coherence over coverage: no
unmeasured shape is spoofed. SP2b's move hook takes no OS gate because a
path's shape is not OS-encoded; a wheel's is.

**Quantize.** A pure function in `components/camoucfg`, Camoufox's rule
except that both-zero takes stock's path:
per axis `n = sign(d) · max(1, round(|d| / 100))`, and `0` for `d == 0`.
The event count is `max(|nx|, |ny|)`. A wheel with both deltas zero gets
count 0 and takes today's path unchanged, whatever stock does with it. Notch `i` carries `sign(nx)` on X
while `i < |nx|` (Y likewise). `wheel(0, 250)` therefore delivers 3 notches,
not 250 px. That changes the number the caller asked for. It is deliberate
and opt-in, as in Camoufox: a wheel cannot turn 2.5 notches.

**Per-notch event.** Each notch is a fresh `WebMouseWheelEvent` whose
fields (`delta_units`, delta per tick, `wheel_ticks`, `phase`,
`has_precise_scrolling_deltas`, `dispatch_type`) are set to what §2 measures.
The fields are not assumed. The expectation to be confirmed is
`kScrollByPixel`, 100 px at DPR 1, ticks ±1, and no began/ended pair.
Position and modifiers are the caller's.

**Cadence.** The first notch goes at once. Each later notch is a delayed
task, `base::RandInt(18, 60)` ms after the previous one (`<random>` is
banned). The 18–60 ms band is Camoufox's and unmeasured: SendInput sets the
cadence in §2, so the oracle cannot measure a hand's. The CDP response is
sent after the last notch is forwarded, since Playwright awaits it. Delivery
reuses SP2b's pattern: static delayed-task callbacks holding a weak widget
pointer, re-acquiring an injector when they fire, and failing the callback
if the widget is gone. A detached widget must never crash the browser.

The wheel ack path is not a straight copy of the move path. `InjectWheelEvent`
has its own bookkeeping that `InjectMouseEvent` lacks:
- `input_queued_`;
- the `kPhaseEnded` follow-up, gated on `input_queued_`;
- `pending_mouse_callbacks_`, popped by the ack.

The plan must establish how SP2b forwards intermediate events with no
registered callback without an ack popping an empty deque, and mirror that.
It must also decide what becomes of the `kPhaseEnded` branch if §2 measures
no phases.

### 2. Oracle first, RED-first (`scripts/capture_wheel_oracle.py`)

Stock Chrome 154 on the Windows host, headed, launched through
`scripts/windows/run-interactive.ps1` into session 1 and gated by
`scripts/gpu_gate.py`. A non-zero GPU crash count makes the run `UNMEASURED`.
The page records:
- every `wheel` event: `deltaX/Y/Z`, `deltaMode`, `wheelDeltaX/Y`,
  `isTrusted`, `timeStamp`;
- every `scroll` event for 1 s afterwards: `timeStamp`, `scrollY`.

Arms:
- **real**: PowerShell `SetCursorPos` onto the page, then
  `SendInput(MOUSEEVENTF_WHEEL, -120)` once, then three times about 40 ms
  apart. This is the Win32 path a physical wheel takes.
- **CDP control**: the same stock binary, `mouse.wheel(0, 100)` and
  `mouse.wheel(0, 300)` over CDP.

The capture fails unless the arms differ in at least event count,
`wheelDeltaY/deltaY` ratio, and the number of `scroll` events per notch
(animation). If they agree, the probe measures nothing and the slice stops
there. The capture also records the host's "lines to scroll" setting (expected 3),
its Windows scale percentage and `window.devicePixelRatio`.

**DPR must be resolved here, not deferred.** Blink divides
`wheel_ticks * kTickMultiplier` by `window.devicePixelRatio()` in one
`WheelEvent` constructor path (`wheel_event.cc:107-109`). So on a host that
is not at 100 %, `wheelDeltaY` may not be constant, and `deltaY` may or may
not be. One run cannot tell "100 constant", "100 × DPR" and "100 / DPR"
apart. The real arm therefore runs twice: as is, and with
`--force-device-scale-factor=1`. That flag changes the page's DPR but not the
Win32 builder's native scale, so a difference between the two runs is itself
the answer.

If the per-notch values track DPR, the C++ derives them from the spoofed DPR
(SP4 screen geometry). That is a cross-surface tie: `invariants.json` gains a
line, and §3's "no invariant change" no longer holds. The plan settles this
before its C++ task starts.

Output: `baselines/chrome-8037-wheel.json` (recaptured at every re-pin,
never edited), plus
`docs/superpowers/measurements/2026-10-sp2c-wheel.md`, which fixes the
per-notch fields §1 uses.

The oracle needs no build, so it does not take the build lock.

### 3. Files

| File | Change |
|---|---|
| `additions/camoucfg/mouse_trajectories.{h,cc}` | add `QuantizeWheel(dx, dy)` (pure) |
| `additions/camoucfg/mouse_trajectories_unittest.cc` | cases `0`, `50`, `100`, `149`, `150`, `250`, negative, both axes, unequal axes |
| `content/browser/devtools/protocol/input_handler.{cc,h}` | the gate, the notch split, and delayed delivery in the wheel path |
| `patches/sp2c-humanized-wheel.patch`, `patches/series` | exported, after `sp2b-humanized-cursor` |
| `scripts/capture_wheel_oracle.py` | §2 |
| `scripts/verify_sp2c.py` | §4 |
| `.github/workflows/build-verify.yml` | run `verify_sp2c.py` |
| `baselines/chrome-8037-wheel.json`, `measurements/2026-10-sp2c-wheel.md` | §2 output |
| `docs/superpowers/plans/2026-09-02-followon-roadmap.md` | ledger line |

No new config key, so `keys.json` and `keys.h` are untouched.
`invariants.json` is untouched unless §2 finds the notch values track DPR. `BUILD.gn` is untouched: `mouse_trajectories.cc` is already a
source, and `//content/browser` already depends on `//components/camoucfg`.

The patch is cut the project's way: commit on `camoucrome/main` in
`~/chromium/src` with subject `sp2c-humanized-wheel`, then `export.sh`.
`check_checkout_sync.sh` must return `rc=0`.

### 4. Verification (`scripts/verify_sp2c.py`, WSL `content_shell`)

Driven through `lib_shell.session`, so there is no `Runtime.enable` and
Playwright's default argv is not used. The page records wheel and scroll
events into the DOM. Rows, with expected counts:

1. no config: `wheel(0, 300)` → exactly **1** `wheel` event, `deltaY 300`;
   `wheel(0, 0)` → its event count recorded as the control for row 3.
2. `humanize:enabled` + claimed Windows: `wheel(0, 300)` → exactly **3**,
   each with the oracle's per-notch fields, gaps in `[18, 60]` ms with a
   small tolerance for delivery.
3. `humanize:enabled` + claimed Windows: `wheel(0, 0)`, `wheel(0, 40)`,
   `wheel(-250, 0)` → exactly what row 1's no-config run gives for
   `wheel(0, 0)` (the stock path, count recorded, not assumed), **1**, and
   **3** on X.
4. `humanize:enabled` + claimed macOS: same as row 1.
5. `humanize:enabled`, nothing claimed (Linux build): same as row 1.
6. `Object.keys(window)` and `WheelEvent.prototype` accessors unchanged
   against no-config.

RED: row 2 and row 3's non-zero cases fail on `main` (no SP2c). A mutant with the OS gate removed
fails rows 4–5. Each verdict line states its count.

Animation is asserted on the host-native arm only. Whether `content_shell`
on Linux animates `kScrollByPixel` is a property of that platform, so it is
not evidence about Windows.

## Risks and open points

- **Re-pin 156 is due 2026-10-20.** This patch touches `input_handler.cc`
  next to SP2b, so the re-pin has to rebase it. The build lock is held by the
  156 prep build at the time of writing. The oracle (§2) can run before the
  lock is free; the build and verify cannot.
- **DPR** is an open point that §2 resolves, and its answer can add an
  invariant (see §2).
- **Cadence** 18–60 ms is borrowed, not measured (§1).
- **`wheel(0, d)` with `d < 50`** still delivers a full notch (100 px). This
  is Camoufox's choice, kept for parity; a caller wanting a precise
  sub-notch scroll turns humanize off.

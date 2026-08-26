# SP2 — Automation hiding and CDP invisibility

Status: design. Assumes [00-conventions.md](00-conventions.md).

## 1. Goal

Make the fact that the browser is being driven undetectable from page JavaScript. Every
other sub-project spoofs *what the machine looks like*; this one spoofs *that nobody is
driving*. It is the sub-project with the least reusable material from Camoufox, because
Camoufox hides Juggler — Firefox's automation protocol — and Chromium is driven by CDP,
a different protocol with a different and larger leak surface. A perfect fingerprint on
a browser that answers `navigator.webdriver === true`, or whose main world betrays an
attached inspector, is worth nothing. SP2 is therefore the gating risk for the whole
project: if these leaks cannot be closed, the value of SP1/SP3/SP4 is capped.

## 2. Depends on

**SP0** for the config layer, and only lightly — most of SP2 is unconditional behavior
rather than configurable values. The handful of keys it does need (whether to humanize
input, whether to keep a vector open for debugging) follow the standard
`camoucfg::GetBool(ScopeFor(ctx), key)` shape.

SP2 is independent of SP1 and SP3 and may proceed in parallel with them. It has one
coherence tie to SP1 (headless-shaped UA versus automation signals, section 5) that only
matters once both have landed.

## 3. Surfaces

Paths verified against the real checkout at `~/chromium/src` unless marked
*(unverified)*.

| Surface | Config key | Location | Process |
|---|---|---|---|
| `navigator.webdriver` — runtime-feature path | none (always suppressed) | `third_party/blink/renderer/platform/runtime_enabled_features.json5:799` (`AutomationControlled`) | renderer |
| `navigator.webdriver` — probe path | none (always suppressed) | `third_party/blink/renderer/core/frame/navigator.cc:100` → `probe::ApplyAutomationOverride` | renderer |
| Automation script world | `automation:isolatedWorldName` | `third_party/blink/renderer/platform/bindings/dom_wrapper_world.h`, `core/inspector/inspector_page_agent.cc` | renderer |
| `Runtime.enable` console side effects | `automation:hideRuntimeDomain` | `v8/src/inspector/v8-console.cc`, `v8/src/inspector/v8-inspector-impl.cc` | renderer (V8) |
| Inspector attach observability | as above | `core/inspector/main_thread_debugger.cc`, `core/inspector/thread_debugger_common_impl.cc` | renderer |
| Worker inspector attach | as above | `core/inspector/worker_inspector_controller.cc` | worker |
| Synthesized input trust | `automation:trustedInput` | `content/browser/devtools/protocol/input_handler.cc`, `content/browser/renderer_host/render_widget_host_impl.cc` | browser |
| CDP session/target plumbing | — | `content/browser/devtools/devtools_agent_host_impl.cc`, `protocol/page_handler.cc`, `protocol/target_handler.cc` | browser |
| Humanized cursor paths | `humanize`, `humanize:minTime`, `humanize:maxTime`, `showcursor` | new `//components/camoucfg/mouse_trajectories.*` + `input_handler.cc` | browser |
| `cdc_$…` globals | — | not in Chromium; injected by ChromeDriver | n/a |

## 4. Design

### 4.1 `navigator.webdriver` has two paths, not one

The probe of the live checkout settles a question that most public advice gets wrong.
The implementation at `navigator.cc:100` reads:

```cpp
bool Navigator::webdriver() const {
  if (RuntimeEnabledFeatures::AutomationControlledEnabled())
    return true;

  bool automation_enabled = false;
  probe::ApplyAutomationOverride(GetExecutionContext(), automation_enabled);
  return automation_enabled;
}
```

There are two independent sources of truth. The first is the `AutomationControlled`
blink runtime feature, which is what the widely-cited
`--disable-blink-features=AutomationControlled` switch turns off. The second is a
**probe hook** — Blink's instrumentation mechanism, through which an attached inspector
agent answers the question. That path corresponds to the CDP command
`Emulation.setAutomationOverride` *(unverified — the mapping is inferred from the probe
name; confirm against `core/probe/core_probes.pidl` before relying on it)*.

Two consequences follow. First, the popular switch is only half a fix: it silences the
runtime feature and leaves the probe path live, so any driver that sets the override
still flips `webdriver` back to `true`. Second, and more subtly, the probe call itself
means the instrumentation machinery is compiled into the getter regardless — the
value's *provenance* differs from a stock build even when the value matches.

The C++ change is to make `Navigator::webdriver()` return `false` unconditionally,
before either path is consulted, and to do it inside the existing getter so the
descriptor stays native. This is a two-line edit but it must be made in the getter
rather than by flipping the feature flag, precisely because the flag does not cover the
probe path.

The corresponding Camoufox work is `patches/playwright/1-leak-fixes.patch`, which exists
to *undo* leaky parts of the upstream Playwright bootstrap in `dom/base/Navigator.cpp`.
The lesson that ports is architectural: the automation framework's own patches introduce
leaks, and the fork's job includes reverting them. Chromium's equivalent is that CDP is
in-tree, so there is no upstream automation patch to revert — but the same auditing
posture applies to every CDP handler that touches renderer state.

### 4.2 Isolated worlds for automation script

Camoufox's central automation-hiding trick is running the Juggler page agent in a scope
the page cannot see. Chromium already has the mechanism: `DOMWrapperWorld`, with
isolated worlds used by extensions and by DevTools. The CDP surface is
`Page.createIsolatedWorld` to create a named world, `Page.addScriptToEvaluateOnNewDocument`
with a `worldName` to install script into it before page script runs, and
`Runtime.evaluate` with an explicit `contextId` to execute there.

Used correctly this is already strong: a variable defined in an isolated world is not
reachable from the main world, and the isolated world shares the DOM but not the
JavaScript global. The work in SP2 is therefore less about *building* isolation and more
about *auditing* it:

- Confirm no automation state is ever written to the main world. Any driver that calls
  `Runtime.evaluate` without a `contextId` lands in the main world and defeats this.
- Confirm the isolated world's existence is not enumerable from the main world. Execution
  contexts are reported over the protocol, not to page JS, so this should hold, but it
  needs a test rather than an assumption.
- Confirm `document.defaultView`, event listeners registered from the isolated world, and
  any `MutationObserver` the driver installs do not surface attribution to page script.

The honest position is that most of this is a **driver-side discipline**, not a C++
change. That matters for scoping and is picked up in section 7.

### 4.3 The `Runtime.enable` problem

This is the deepest vector and the one that most clearly separates a real fork from a
patched driver.

When the Runtime domain is enabled, the V8 inspector installs console instrumentation
and reports execution contexts. The classic detection exploits the fact that objects
passed to `console.*` are serialized for the protocol, and serialization touches
property getters that would otherwise never run:

```js
let seen = false;
const probe = {};
Object.defineProperty(probe, 'x', { get() { seen = true; return 1; } });
console.debug(probe);
// seen === true implies something is consuming console output
```

Related vectors read stack-trace machinery: `Error.stackTraceLimit`,
`Error.prepareStackTrace`, and the cost of constructing an `Error` all shift when the
inspector is attached, because V8 captures richer stack information for the protocol.
Timing the construction of many `Error` objects is a documented discriminator.

There are three ways to answer this and they are genuinely different in cost:

**(a) Never enable the Runtime domain.** This is what `patchright` does, and it is free.
The driver uses `Page.addScriptToEvaluateOnNewDocument` plus isolated worlds and simply
does not turn on Runtime. It closes the console-serialization and most of the
stack-trace vectors for that driver only.

**(b) Patch V8's inspector so console serialization does not invoke page getters.**
This lives in `v8/src/inspector/v8-console.cc` and would make the leak impossible
regardless of which driver connects. It is the approach most in keeping with the project's
stated constraint, and it is also the riskiest: V8's inspector is intricate, the change
would need to preserve DevTools usability for our own debugging, and it is a large surface
to keep rebasing across Chromium rolls.

**(c) Suppress inspector-visible side effects only for the main world.** Conceptually the
cleanest — the inspector keeps working for isolated worlds, and the main world behaves as
if nothing is attached. Whether V8's inspector draws that boundary cleanly enough to make
this a small change is **unknown and must be established empirically** before committing.

Recommendation is deferred to section 7 because it depends on measurement we have not
made.

### 4.4 Trusted input

Camoufox's `patches/trusted-automation-events.patch` makes synthesized input produce
events with `isTrusted === true` and complete pointer sequences, including the
parent-process `<select>` option event pair that a real mouse commit produces. The
underlying problem is identical on Chromium and the mechanism is different.

CDP's `Input.dispatchMouseEvent` (`content/browser/devtools/protocol/input_handler.cc`,
declared around `input_handler.h:109`) injects events into the browser's input pipeline
via `RenderWidgetHostImpl`. Because injection happens in the browser process and travels
the normal input path, events generally arrive with `isTrusted === true` already — unlike
`dispatchEvent` from page JS. The residual risk is not the flag but the *shape* of the
stream: real hardware produces a dense, jittered series of `mousemove` events with
plausible timing, sub-pixel movement, and correlated `pointerrawupdate`; a naive driver
teleports the cursor and emits a bare down/up pair.

So the C++ question for trusted input is narrower than Camoufox's was. The specific things
worth verifying rather than assuming: whether `Input.dispatchMouseEvent` sets any field a
page can read that differs from hardware input, whether pointer event coalescing produces a
distinguishable pattern, and whether `screenX`/`screenY` on synthesized events remain
consistent with the spoofed screen geometry from SP4.

### 4.5 Humanized cursor paths — placement

Camoufox implements trajectory generation in C++ (`additions/camoucfg/MouseTrajectories.hpp`)
and dispatches from the Juggler `PageHandler` via `ChromeUtils.CamouGetMouseTrajectory`,
controlled by the `humanize` and `showcursor` config keys. The direct Chromium analogue is
a trajectory generator in `//components/camoucfg/` consumed by the CDP input handler.

**Recommendation: keep humanization inside SP2 but as a second phase, after the leak work
lands.** The reasoning is that humanization is a *behavioral* defense against
timing/movement heuristics, while sections 4.1–4.4 close *binary* leaks. A binary leak is
fatal on its own; a robotic mouse path only raises a score. Fixing a fatal leak before an
incremental one is the right order, and phase 1 also settles the input plumbing that phase 2
would build on. Splitting it out entirely into SP6 would be wrong, because it is an
anti-detection concern rather than a packaging concern.

### 4.6 `cdc_$` variables

These are injected by **ChromeDriver**, not by Chromium, and appear as
`window.cdc_asdjflasutopfhvcZLmcfl_*` style globals. They are the single most-cited Selenium
tell and they require no C++ work at all: driving CDP directly, or through Playwright/
patchright, never introduces them. The design consequence is a constraint on the driver
layer (SP6) rather than a patch here: **Camoucrome must not be driven through ChromeDriver.**

## 5. Coherence constraints

| This surface | Must agree with | Invariant |
|---|---|---|
| `navigator.webdriver === false` | SP1 user-agent string | UA must not contain `HeadlessChrome`. A false `webdriver` beside a headless UA is a louder signal than either alone. |
| `navigator.webdriver === false` | Permissions state | The classic headless tell is `Notification.permission === 'denied'` while `navigator.permissions.query({name:'notifications'})` reports `prompt`. These must not disagree. |
| Synthesized pointer coordinates | SP4 screen geometry | `screenX`/`screenY` on synthesized events must fall inside the spoofed screen bounds, not the host display's. |
| Isolated-world script | Worker contexts | Automation state must be invisible from workers too; `worker_inspector_controller.cc` is the parallel attach path and is easy to overlook. |
| Humanized timing (phase 2) | Real event cadence | Inter-event intervals must be plausible for the claimed device class — a touch-capable profile from SP1 that never emits touch events is incoherent. |

## 6. Verification

Each item is independently runnable against `content_shell` built from
`out/Default`, driven over `--remote-debugging-port`.

1. **Runtime feature path.** With no switches, evaluate `navigator.webdriver` in the main
   world. Expected: `false`. Stock Chromium under CDP returns `true`.
2. **Probe path.** Issue `Emulation.setAutomationOverride` with `enabled: true`, then
   re-read `navigator.webdriver`. Expected: still `false`. A stock build returns `true`;
   this is the check that `--disable-blink-features=AutomationControlled` fails.
3. **Descriptor nativeness.** `Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver').get.toString()`
   must contain `[native code]`.
4. **No new globals.** Diff `Object.getOwnPropertyNames(window)` against a stock
   `content_shell` build of the same revision. Expected: empty diff. This is the check that
   catches accidental main-world writes and any `cdc_$`-class leak.
5. **Runtime-domain getter probe.** Run the `Object.defineProperty` + `console.debug`
   snippet from 4.3 with the Runtime domain enabled. Expected: `seen === false`. On stock
   Chromium with `Runtime.enable`, `seen === true`.
6. **Stack-trace timing.** Construct 10,000 `Error` objects and read `.stack`; compare
   median duration with the inspector attached versus detached. Expected: distributions
   overlap. Record the raw numbers — "no difference" is not a result without them.
7. **Isolated-world opacity.** Define a variable in the automation world, then from the main
   world attempt to reach it via `window`, `globalThis`, iterating `document.defaultView`,
   and via a `MutationObserver` on any node the driver touched. Expected: unreachable in all
   four.
8. **Worker parity.** Repeat items 1, 3 and 4 inside a dedicated worker and a shared worker.
   Expected: identical results. This is the conventions rule-3 check and the one Camoufox
   needed `cross-process-storage.patch` to satisfy.
9. **Trusted input.** Dispatch a click via `Input.dispatchMouseEvent` and assert
   `event.isTrusted === true`, that the full sequence
   `pointerdown → mousedown → pointerup → mouseup → click` arrives, and that no field
   differs from a hardware-generated click captured on the same page.
10. **Real detectors.** Run `bot.sannysoft.com`, `CreepJS`, `browserscan.net/bot-detection`,
    and `fingerprint.com`'s bot demo. Record per-check pass/fail into a checked-in baseline
    file so regressions are visible across Chromium rolls. Passing these is necessary, not
    sufficient — they are public and therefore the easiest bar.
11. **Differential against patchright.** Run the same battery against stock Chromium driven
    by patchright. Any vector where patchright already passes and Camoucrome gains nothing is
    a candidate for removal from scope (section 7).

## 7. Open decisions

**D1 — How far to go on `Runtime.enable`.** Options (a) driver-side avoidance, (b) patch
`v8/src/inspector/v8-console.cc`, (c) main-world-only suppression, all described in 4.3. No
recommendation yet, deliberately: the choice depends on measuring how much of the leak
survives option (a), and that measurement (verification items 5, 6 and 11) has not been run.
Committing to a V8 inspector patch before knowing whether a free driver-side fix closes the
same vectors would be the single most expensive mistake available in this sub-project.
Sequence the measurement first.

**D2 — Whether to reimplement what patchright already covers.** patchright is a patched
Playwright that avoids `Runtime.enable` and uses isolated worlds. Where it already passes a
vector, a C++ reimplementation buys protocol-level rather than driver-level robustness — real,
but not free. The proposed rule: implement in C++ only where the leak is observable regardless
of driver behavior. `navigator.webdriver` qualifies (any CDP client can flip it). Console
serialization may not. Verification item 11 produces the evidence for this call.

**D3 — Trusted input: C++ or driver-side.** Section 4.4 argues the `isTrusted` flag is likely
already correct because injection happens in the browser process, leaving only stream *shape*
as the problem — which is driver-side. This is an assumption stated as such. If item 9 finds a
readable field that differs from hardware input, the decision flips and `input_handler.cc`
needs patching.

**D4 — Headless mode.** Whether Camoucrome ships headless at all is unsettled. Chromium's
newer headless mode is much closer to headful than the old one, but differences remain in
GPU, fonts, and permissions. Camoufox's answer is a virtual display rather than true headless.
The equivalent question for Chromium — headless, Xvfb, or both — affects SP4 (screen, fonts)
and needs its own decision.

**D5 — Rebase cost.** Any change inside `v8/src/inspector` will conflict on most Chromium
rolls. If D1 lands on option (b) or (c), the maintenance cost belongs in SP6's planning and
should be estimated before, not after.

**D6 — Empirical limits.** Several claims here cannot be settled by reasoning: whether
execution contexts leak to page JS, whether V8's inspector can cleanly scope side effects per
world, whether coalesced pointer events are distinguishable. Each is written above as a
question, not an answer. None should be closed without a measurement.

## 8. Explicitly out of scope

Fingerprint *values* — user agent, WebGL strings, canvas noise, screen geometry — belong to
SP1, SP3 and SP4. Cross-surface consistency checking belongs to SP5. The driver API and the
prohibition on ChromeDriver belong to SP6, though 4.6 records the constraint here because it
originates in this analysis. TLS/JA3 and HTTP/2 fingerprinting are network-layer concerns
outside every SP in the current map; the Camoufox notes record that TLS is a strength of the
Firefox fork rather than a gap, and the equivalent claim for Chromium is untested.

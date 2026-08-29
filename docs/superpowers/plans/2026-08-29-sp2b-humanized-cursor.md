# SP2b — Humanized cursor trajectories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make CDP-synthesized mouse movement follow a human-like path with human-like timing instead of teleporting, controlled by config, so a detector scoring movement/timing heuristics sees a plausible cursor rather than a robot.

**Architecture:** A trajectory generator in `//components/camoucfg/`, consumed by the CDP input handler at its single injection point. When `humanize` is configured and a mouse move is dispatched, the one teleporting event is replaced by a sequence of intermediate moves along a Bézier curve with jittered inter-event timing. No config → the single event is forwarded unchanged, and stock behaviour (emulation included) survives untouched.

**Tech Stack:** C++20 (Chromium style), GN/Siso, `chrome` + `content_shell`, Python 3 + Playwright over CDP, `components_unittests` for the curve math.

---

## Why SP2b is only the humanized cursor — the measurements collapsed the rest

SP2's spec listed a large surface (sections 4.1–4.7). Three measurements and one recon, run before writing this plan, resolved all of it *except* the humanized cursor to "no C++ needed here". Recording that up front so a reader does not expect the automation-leak work the spec's table implies — it is done, or it is owned elsewhere.

| SP2 item | Status after measurement | Owner |
|---|---|---|
| 4.1 `navigator.webdriver` (both sources) | **shipped** | SP2a |
| `HeadlessChrome` product token | **shipped** | SP2a |
| 4.3 / D1 `Runtime.enable` console getter | **does not reproduce** on this revision (measurement 1) | — |
| 4.3 / D1 `Runtime.enable` stack timing | caused by `Runtime.enable` specifically; closed by *not enabling it* (measurements 2, 3) | **SP6** driver constraint |
| 4.4 / D3 trusted input `isTrusted` | **already `true`** (measurement 4); `WebMouseEvent` has no trust field to patch (recon B) | — |
| 4.2 isolated worlds | driver-side, zero Camoucrome code in the tree (recon C) | **SP6** |
| 4.5 humanized cursor | **this plan** | SP2b |
| 4.7 / D7 `window.chrome` | installers live under `chrome/renderer/`, gated on SP7 branding (recon D) | **deferred**, see below |

The evidence is checked in: `docs/superpowers/measurements/*.json`, `docs/superpowers/measurements/D1-resolution.md`, and `.superpowers/sdd/sp2b-recon.md` (scratch, not committed). D1 and D3 both resolved to driver-layer constraints, which is why SP2b carries **no** `Runtime.enable` or `input_handler` trust patch. The spec's own ordering justifies doing the cursor now: the binary leaks (webdriver, headless) were fatal on their own and are closed; the cursor is the incremental, score-raising defense that comes after, exactly as section 4.5 states.

## Facts established before this plan, so no task re-derives them

All against checkout `70cb99fedc`, from the recon.

- **Injection point, pinned to one line.** `InputHandler::InputInjector::InjectMouseEvent` at `content/browser/devtools/protocol/input_handler.cc:739` does the injection via `widget_host_->ForwardMouseEvent(mouse_event)` at **`input_handler.cc:757`**. The event is built by `CreateWebMouseEvent` (`:426`) and its final `PositionInWidget`/`PositionInScreen` are set in `OnWidgetForDispatchMouseEvent` (`:1631`, coords at `:1639-1642`).
- **BUILD.gn needs no change.** `content/browser/BUILD.gn:150` already lists `"//components/camoucfg"` as a dep of `source_set("browser")` (opens `:101`), and `input_handler.cc`/`.h` are sources of that same target (`:864-865`). A `#include "components/camoucfg/…"` from `input_handler.cc` compiles with no DEPS/BUILD edit — unlike SP0, which had to add the wiring. Confirm once with `gn check` anyway (conventions: a green build does not run it).
- **The algorithm is a port, not a reuse.** `additions/camoucfg/MouseTrajectories.hpp` exists in the **camoufox** repo (Bézier via Bernstein polynomials, `BezierCalculator` + `HumanizeMouseTrajectory`, ~8.6 KB, header-only, reads `MaskConfig.hpp`). It does **not** exist in camoucrome. It must be translated into a `components/camoucfg` `.h/.cc` pair in Chromium style, reading `camoucfg::Config()` through the existing getters, and — critically — **STL random engines are banned in this tree** (SP1a hit this: `GetRandomOrder` in `user_agent_utils.cc` hand-rolls a shuffle for the same reason). The port must use `base/rand_util.h` or a seeded deterministic generator, not `<random>`.
- **The config keys do not exist.** `humanize`, `humanize:minTime`, `humanize:maxTime`, `showcursor` are absent from `additions/camoucfg/keys.h`. They are new.
- **`timestamp` is the stream-shape lever.** CDP's optional `timestamp` param flows into the event's `base::TimeTicks` (`GetEventTimeTicks`, `input_handler.cc:130`). Constant intervals are the robotic tell; the generator sets plausibly-jittered timestamps across the intermediate events.

## Global Constraints

Copied from `docs/superpowers/specs/00-conventions.md` and the SP2 spec. Every task's requirements implicitly include this section.

- **No JavaScript injection into page-visible scopes.** The trajectory is generated in C++ in the browser process and injected through the existing native input path; nothing is added to any page scope.
- **Native-looking accessors** unchanged; `Object.keys(window)` unchanged against a stock build. This plan adds no renderer surface, so this holds by construction — but the browser-level verification asserts it anyway, because "adds no surface" is a claim a test should carry.
- **Worker parity** — not applicable; input injection is a browser-process concern with no worker surface.
- **Coherence over coverage.** Synthesized coordinates must stay inside the spoofed screen bounds (SP2 §5, ties to SP4). Until SP4 lands they must stay inside the *real* bounds; the generator must not produce a point outside the widget.
- **Fall back to the real value when config is absent.** No `humanize` key → the single event is forwarded exactly as today, byte-for-byte. This is the load-bearing safety property: an un-configured Camoucrome must drive identically to stock, emulation included.
- **Apply configuration last, after any probe.** Same rule SP0 established at the `hardwareConcurrency` site — the humanization reads config and must not override a legitimate emulation path when no key is set.
- **A derived value gets no config key.** The intermediate points are derived from start, end, and the timing keys; they get no key of their own.
- **STL random is banned.** Use `base/rand_util.h`. A `<random>` include fails the build.
- **Every `camoucfg` getter takes a scope first.** In the browser process that is `camoucfg::GlobalScope()`.
- **Assert the expected count, or the expected failure.** Every verification step states its number; an exit code of 0 is not evidence anything was examined.
- **The dominant failure mode is a check that reports success while measuring almost nothing.** A humanization test that passes when no extra events were produced measures nothing — assert the intermediate-event *count*, not merely that a move arrived.

## Deferred, with the reason — not omitted

- **`showcursor`** (rendering a visible cursor overlay). Camoufox has it; its anti-detect value is for a human or a screenshot watching the session, which a headless scraper has not. It is cosmetic relative to the timing/path defense that actually defeats movement heuristics. Defined here as a future task, not built now: the `showcursor` key is reserved in `keys.h` (Task 1) so the registry is complete and a later task adds only the overlay, but no overlay code is in this plan. If the user wants it, it is a self-contained follow-up.
- **4.7 `window.chrome`** (SP2 D7). Its installers are under `chrome/renderer/` and what it should present depends on SP7's branding decision (present as Chrome vs Chromium). Planning it now would hard-code an answer SP7 owns. It becomes its own plan once SP7 D1's consequences for the installers are settled.
- **SP6 hand-offs.** D1 (never enable the Runtime domain) and 4.2 (driver uses isolated worlds, never writes automation state to the main world) are driver constraints, recorded in `D1-resolution.md` and to be carried into SP6's spec. No code here.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `additions/camoucfg/keys.h` | Modify | Add `humanize`, `humanize:minTime`, `humanize:maxTime`, `showcursor` constants + registry entries |
| `additions/camoucfg/keys_unittest.cc` | Modify | Extend the two guard tests to the new keys |
| `additions/camoucfg/mouse_trajectories.h` | Create | `BezierPath` / `HumanizeTrajectory` declarations |
| `additions/camoucfg/mouse_trajectories.cc` | Create | The ported curve + timing generator, `base/rand_util.h` not `<random>` |
| `additions/camoucfg/mouse_trajectories_unittest.cc` | Create | Deterministic curve-math tests |
| `additions/camoucfg/BUILD.gn` | Modify | Add the two new source files (both directions, per `check_additions_build.py`) |
| `content/browser/devtools/protocol/input_handler.cc` | Modify (`InjectMouseEvent`, ~`:739`) | When `humanize` set and the event is a move, inject the trajectory sequence instead of one event |
| `settings/invariants.json` + `additions/camoucfg/invariants.h` | Modify (only if a coherence tie is added) | See Task 3 note |
| `scripts/verify_sp2b.py` | Create | Browser-level: a humanized move produces N jittered intermediate events; an un-configured move produces exactly one |
| `patches/sp2b-humanized-cursor.patch` | Create | The `input_handler.cc` edit, extracted last |
| `scripts/apply.sh` | Modify | Apply `sp2b` after `sp2a` |
| `docs/superpowers/specs/00-conventions.md` | Modify | Record the SP2 measurement outcome + SP2b scope |

---

### Task 1: the four config keys

**Files:**
- Modify: `additions/camoucfg/keys.h`
- Modify: `additions/camoucfg/keys_unittest.cc`
- Test: `components_unittests --gtest_filter='CamoucfgKeysTest.*'`

**Interfaces:**
- Produces: `camoucfg::keys::kHumanize`, `kHumanizeMinTime`, `kHumanizeMaxTime`, `kShowCursor` — `constexpr char[]` constants, consumed by Task 2's generator and Task 3's injection hook.

**Background.** `keys.h` holds `constexpr char[]` constants and a `kAllKeys` array that two guard tests police (every constant is in the array; the array has no duplicates). The naming rule (conventions): a **colon** for a synthetic namespace with no JS counterpart. `humanize`, `humanize:minTime`, `humanize:maxTime`, `showcursor` all qualify — none mirrors a JS property path — so `humanize` is a bare synthetic key and the two times are colon-namespaced under it. Follow the existing `ua:*` entries exactly.

- [ ] **Step 1: Write the failing guard-test extension**

In `keys_unittest.cc`, add the four new constants to whatever list the "every key is in `kAllKeys`" test iterates, so the test fails until `keys.h` declares them.

```cpp
// in the expected-keys set the guard test checks:
keys::kHumanize, keys::kHumanizeMinTime, keys::kHumanizeMaxTime,
keys::kShowCursor,
```

- [ ] **Step 2: Run it, expect a compile failure** (the symbols do not exist yet)

Run: `components_unittests --gtest_filter='CamoucfgKeysTest.*'` — expect the build to fail with `no member named 'kHumanize'`. A compile failure IS the red state here; there is nothing to run until it compiles.

- [ ] **Step 3: Add the constants and registry entries**

```cpp
// keys.h — synthetic namespace, colon-separated, per the naming rule.
inline constexpr char kHumanize[] = "humanize";
inline constexpr char kHumanizeMinTime[] = "humanize:minTime";
inline constexpr char kHumanizeMaxTime[] = "humanize:maxTime";
inline constexpr char kShowCursor[] = "showcursor";
```
and add all four to `kAllKeys`.

- [ ] **Step 4: Run the guard tests, expect pass**

Run: `components_unittests --gtest_filter='CamoucfgKeysTest.*'` — expect the existing count + the new keys, all PASS. State the number you see; if a duplicate slipped into `kAllKeys` the uniqueness guard fails and names it.

- [ ] **Step 5: Commit** — `git add additions/camoucfg/keys.h additions/camoucfg/keys_unittest.cc` then commit.

---

### Task 2: the trajectory generator, ported and deterministic

**Files:**
- Create: `additions/camoucfg/mouse_trajectories.h`
- Create: `additions/camoucfg/mouse_trajectories.cc`
- Create: `additions/camoucfg/mouse_trajectories_unittest.cc`
- Modify: `additions/camoucfg/BUILD.gn`
- Test: `components_unittests --gtest_filter='MouseTrajectoriesTest.*'`

**Interfaces:**
- Consumes: nothing from camoucfg config directly in the pure math; the timing keys are read by the caller (Task 3) and passed in, so the generator stays unit-testable without a process-global config.
- Produces:
  ```cpp
  namespace camoucfg {
  struct TrajectoryPoint { double x; double y; base::TimeDelta offset; };
  // Returns `steps`+1 points from `start` to `end` inclusive along a Bézier
  // curve, with monotonically increasing offsets summing to a duration drawn
  // between min_ms and max_ms. Deterministic given `seed`.
  std::vector<TrajectoryPoint> HumanizeTrajectory(
      gfx::PointF start, gfx::PointF end, int steps,
      int min_ms, int max_ms, uint64_t seed);
  }
  ```

**Background — the two things the port must get right.**
1. **No `<random>`.** The camoufox header uses STL engines; this tree bans them (SP1a's `GetRandomOrder` is the precedent, `user_agent_utils.cc`). Use `base::RandGenerator`/`base::RandDouble` from `base/rand_util.h`, or seed a small deterministic PRNG so the unit test is reproducible. The seed argument exists precisely so the test is not flaky — production callers can pass a per-move seed from `base::RandUint64()`.
2. **Endpoints are exact.** A Bézier through jittered control points must still start exactly at `start` and end exactly at `end`, or the click lands in the wrong place. The test asserts this to the ULP.

- [ ] **Step 1: Write the failing curve tests**

```cpp
TEST(MouseTrajectoriesTest, EndpointsAreExact) {
  auto path = camoucfg::HumanizeTrajectory(
      {10, 20}, {300, 400}, /*steps=*/24, /*min_ms=*/40, /*max_ms=*/120,
      /*seed=*/1234);
  ASSERT_GE(path.size(), 2u);
  EXPECT_EQ(path.front().x, 10.0);
  EXPECT_EQ(path.front().y, 20.0);
  EXPECT_EQ(path.back().x, 300.0);
  EXPECT_EQ(path.back().y, 400.0);
}

TEST(MouseTrajectoriesTest, StepCountAndMonotonicTiming) {
  auto path = camoucfg::HumanizeTrajectory(
      {0, 0}, {100, 100}, 24, 40, 120, 1234);
  EXPECT_EQ(path.size(), 25u);  // steps + 1
  for (size_t i = 1; i < path.size(); ++i)
    EXPECT_GT(path[i].offset, path[i - 1].offset);
  EXPECT_GE(path.back().offset, base::Milliseconds(40));
  EXPECT_LE(path.back().offset, base::Milliseconds(120));
}

TEST(MouseTrajectoriesTest, DeterministicGivenSeed) {
  auto a = camoucfg::HumanizeTrajectory({0, 0}, {100, 100}, 24, 40, 120, 7);
  auto b = camoucfg::HumanizeTrajectory({0, 0}, {100, 100}, 24, 40, 120, 7);
  ASSERT_EQ(a.size(), b.size());
  for (size_t i = 0; i < a.size(); ++i) {
    EXPECT_EQ(a[i].x, b[i].x);
    EXPECT_EQ(a[i].y, b[i].y);
    EXPECT_EQ(a[i].offset, b[i].offset);
  }
}

TEST(MouseTrajectoriesTest, PathStaysWithinBoundingBoxSlack) {
  // A human curve bows off the straight line but not wildly. Assert the path
  // stays within a generous bounding box around the segment, so a bug that
  // sends the cursor across the screen is caught.
  auto path = camoucfg::HumanizeTrajectory({0, 0}, {100, 0}, 24, 40, 120, 9);
  for (const auto& p : path) {
    EXPECT_GE(p.x, -50);
    EXPECT_LE(p.x, 150);
    EXPECT_GE(p.y, -80);
    EXPECT_LE(p.y, 80);
  }
}
```

- [ ] **Step 2: Add the sources to `BUILD.gn`, run, expect link/compile red**

Add `mouse_trajectories.h`, `mouse_trajectories.cc`, `mouse_trajectories_unittest.cc` to `additions/camoucfg/BUILD.gn` (both the library sources and the unittest sources — `check_additions_build.py` enforces every file appears). Run the filter; expect it to fail (functions undefined).

- [ ] **Step 3: Port the algorithm**

Translate `BezierCalculator` + `HumanizeMouseTrajectory` from the camoufox `MouseTrajectories.hpp` into `mouse_trajectories.cc`. Keep the Bernstein-polynomial curve. Replace STL random with `base/rand_util.h` seeded via the `seed` argument. Distribute the total duration (drawn in `[min_ms, max_ms]`) across the steps with per-step jitter so intervals are not constant. Exact endpoints: force `path.front() = start` and `path.back() = end` after generating, rather than trusting the curve to hit them.

- [ ] **Step 4: Run the tests, expect all four PASS**

Run: `components_unittests --gtest_filter='MouseTrajectoriesTest.*'` — expect `[  PASSED  ] 4 tests.` Grep for that literal line, not the exit code (a zero-match filter exits 0 printing SUCCESS).

- [ ] **Step 5: Confirm no `<random>` slipped in**

Run: `grep -c '#include <random>' additions/camoucfg/mouse_trajectories.cc` — expect `0`. This is a real gate: the file builds fine with `<random>` locally and only fails in the full tree, so catch it here.

- [ ] **Step 6: `check_additions_build.py` and commit**

Run: `python3 scripts/check_additions_build.py` — expect PASS with the count risen by the two new source files. Then commit.

---

### Task 3: hook the generator into the injection point

**Files:**
- Modify: `content/browser/devtools/protocol/input_handler.cc` (in the checkout, `InjectMouseEvent` ~`:739`)
- Create: `scripts/verify_sp2b.py` (in the repo)
- Test: `scripts/verify_sp2b.py` against `chrome`

**Interfaces:**
- Consumes: `camoucfg::HumanizeTrajectory` (Task 2), `camoucfg::keys::kHumanize`/`kHumanizeMinTime`/`kHumanizeMaxTime` (Task 1), `camoucfg::GetBool`/`GetString`/`GetInt` with `camoucfg::GlobalScope()`.
- Produces: the observable behaviour `verify_sp2b.py` asserts.

**Background — where and how, exactly.** The hook goes in `InputInjector::InjectMouseEvent` (`input_handler.cc:739`), around the `widget_host_->ForwardMouseEvent(mouse_event)` at `:757`. The logic:

- Read `humanize` once. If absent → forward the single event exactly as today. This is the fall-back-to-real safety property, and it must be the first branch so an un-configured build's code path is unchanged.
- If set, and the event is a **move** (`WebInputEvent::Type::kMouseMove`) with a known previous position → generate a trajectory from the previous position to the event's position, and `ForwardMouseEvent` one synthesized move per intermediate point, spacing them by the point offsets. The final forwarded event is the original, so the destination and all its other fields are untouched.
- A down/up/click is **not** humanized — those are discrete, not paths. Only moves get a trajectory. (A future refinement could curve the approach before a click; out of scope here.)

Two hazards from conventions: **apply config last** (this reads config and only acts when the key is present, so stock behaviour including emulation survives when it is absent), and the previous-position tracking must not leak across widgets — reset it when the target widget changes.

- [ ] **Step 1: Write `scripts/verify_sp2b.py`**

Three criteria, against `chrome` (the input path is the same on `content_shell`, but keep one binary for consistency with the other SP2 suites — `chrome` is already built). Drive with Playwright's `page.mouse.move`, which issues `Input.dispatchMouseEvent`.

| # | Criterion | Un-configured | Configured |
|---|---|---|---|
| 1 | a single `page.mouse.move(x, y)` with **no** `humanize` produces exactly **one** `mousemove` | 1 event | — |
| 2 | the same move **with** `humanize` produces **more than one** `mousemove`, ending at (x, y) | — | N > 1, last at (x,y) |
| 3 | inter-event intervals under `humanize` are **not all equal** (the robotic tell the feature exists to remove) | — | variance > 0 |

Criterion 1 is the safety property (un-configured = stock). Criterion 2 is the feature. Criterion 3 is what makes it *human* rather than merely multi-step — assert the intervals are not constant, because a fixed-interval interpolation would pass criterion 2 while still being trivially detectable. Attach a `mousemove` listener that records `event.timeStamp` and coordinates; count and diff.

```python
# configured run sets CAMOU_CONFIG with humanize + the time bounds; the
# un-configured run sets nothing. Same session shape as verify_sp2.py.
HUMANIZE = json.dumps({"humanize": True, "humanize:minTime": 40,
                       "humanize:maxTime": 120})
```

- [ ] **Step 2: Run it against the UNPATCHED tree, record the baseline**

Both criterion 2 and 3 must **FAIL** on the current build (no humanization exists yet): a configured move still produces one event. Expected: criterion 1 PASS, criteria 2 and 3 FAIL. Any other result means the probe is miscounting; stop and find out before writing the hook. (This is the predict-the-failure gate that has caught a plan defect in every SP2 task.)

- [ ] **Step 3: Write the hook** in `InjectMouseEvent` per the background above.

- [ ] **Step 4: Build `chrome`, run the suite, expect 3 PASS**

```bash
~/depot_tools/autoninja -C out/Default chrome content_shell > ~/b.log 2>&1 && echo BUILD_OK || { echo BUILD_FAILED; grep -E "error:" ~/b.log | head; }
~/camoucrome-verify/venv/bin/python3 ~/camoucrome-verify/verify_sp2b.py > ~/v.log 2>&1 && echo ALL_PASS || echo SOME_FAIL
grep -c '^PASS' ~/v.log
```
Expected: `BUILD_OK`, `ALL_PASS`, `3`.

- [ ] **Step 5: The safety mutation — confirm the un-configured path is byte-unchanged**

The one regression that matters: an un-configured Camoucrome must forward exactly one event, as stock does. Criterion 1 asserts it. Additionally, mutate the hook to *always* humanize (drop the `if humanize present` guard), rebuild, and confirm criterion 1 flips to FAIL — proving the guard is what protects the stock path, not luck. Restore, `touch`, rebuild, confirm real work, re-run to 3 PASS.

- [ ] **Step 6: `gn check` the one new cross-component include**

Even though `content/browser/BUILD.gn` already deps `//components/camoucfg`, run it explicitly per conventions — a green build does not:
```bash
~/depot_tools/gn check out/Default "//content/browser:browser"
```
Expected: no error naming the camoucfg include.

- [ ] **Step 7: Commit** the verification script (repo) and the source edit (checkout) separately.

---

### Task 4: extract the patch, wire `apply.sh`, record the SP2 outcome in conventions

**Files:**
- Create: `patches/sp2b-humanized-cursor.patch`
- Modify: `scripts/apply.sh`
- Modify: `docs/superpowers/specs/00-conventions.md`

**Background.** `apply.sh` lists patches explicitly and applies them in extraction order. `sp2b` is extracted from a tree with `sp0`+`sp1a`+`sp5a`+`sp2a` applied, so it goes **last**. Only `input_handler.cc` is patched (the camoucfg additions are copied files, handled by `apply.sh`'s `cp`, not the patch). Extract as a range from the last pre-SP2b commit, not a bare `git diff` — the SP2a episode proved a bare working-tree diff is empty once the edits are committed, and produces a structurally-valid empty patch.

- [ ] **Step 1: Extract**

```bash
git diff <last-pre-sp2b-commit>..HEAD -- content/browser/devtools/protocol/input_handler.cc > ~/sp2b.patch
grep -c '^diff --git' ~/sp2b.patch   # expect 1
grep -c '^[+-][^+-]' ~/sp2b.patch    # expect > 0 — an empty patch also satisfies the header count
```

- [ ] **Step 2: Bring to the repo by base64, sha-compare both sides.** Never `scp`. One file per ssh call.

- [ ] **Step 3: Add `"$ROOT/patches/sp2b-humanized-cursor.patch"` last in `apply.sh`'s `PATCHES` array.**

- [ ] **Step 4: Prove reconstruction** — `git checkout -- input_handler.cc; git apply --3way ~/sp2b.patch; git diff --cached --stat` names exactly that one file.

- [ ] **Step 5: Rebuild from the reconstructed tree, re-run every suite** with its expected count: `verify_sp0` 11, `verify_sp1a` 9, `verify_sp5a` 4, `verify_sp1a_chrome` 34, `verify_sp2` 9, `verify_sp2b` 3, `run_coherence_tests` 6/6, `check_checkout_sync` (rises by the two new additions files), `check_additions_build` (rises by two).

- [ ] **Step 6: Record the SP2 outcome in `00-conventions.md`.** Add to the sub-project map: SP2 is complete across SP2a (binary leaks) and SP2b (humanized cursor); D1 and D3 resolved to SP6 driver constraints by measurement; `window.chrome` (4.7) deferred to post-SP7. Point at `D1-resolution.md`. One paragraph, in the style of the existing SP1/SP5 split notes.

- [ ] **Step 7: Commit** patch + `apply.sh` + conventions together.

---

## Self-review

**Spec coverage.** SP2's sections 4.1–4.4 are shipped (SP2a) or resolved to driver-side by measurement; 4.5 is this plan; 4.7 is deferred with a stated gate (SP7). Every SP2 verification item is either covered by an existing suite (1–8 by `verify_sp2.py`), owned by SP6 (the Runtime and isolated-world items), or by this plan's `verify_sp2b.py` (the humanized-move items). Nothing is silently dropped.

**Placeholders.** None. Every task has its files, its exact injection line (`input_handler.cc:757`), its test code, and its expected counts.

**Type consistency.** `HumanizeTrajectory`'s signature in Task 2 is what Task 3's hook calls; the four key constants named in Task 1 are what Tasks 2 and 3 read. `TrajectoryPoint` carries the `base::TimeDelta offset` the hook uses to space events.

**The one judgment call a reviewer should weigh.** Whether humanization belongs in SP2b at all, given the measurements showed the automation *leaks* need no C++ here. The spec (4.5) explicitly keeps it in SP2 as the phase-two, post-leak behavioral defense, and it is the only remaining C++ surface in the whole sub-project — so landing it as SP2b matches both the spec's ordering and the measured reality. If the user would rather ship SP2 as "leaks closed, cursor deferred", that is a scope decision to raise before Task 1, not a defect in the plan.

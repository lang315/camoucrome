# SP5a registry extension — screen geometry invariant (avail ≤ screen)

**Date:** 2026-09-07
**Slice:** SP5a coherence-registry extension
**Owner:** sp4a-screen (constrains only sp4a's own keys)
**Status:** measurement — approach approved by advisor

## What this adds

Two relational invariants to the SP5a registry, one per axis:

| id | keys[0] (bound, authoritative) | keys[1] (constrained) | fires when |
|----|--------------------------------|-----------------------|------------|
| `screen-avail-width-fits`  | `screen.width`  | `screen.availWidth`  | availWidth  > width  |
| `screen-avail-height-fits` | `screen.height` | `screen.availHeight` | availHeight > height |

A new `Relation::kFitsWithin`: keys[1] must be ≤ keys[0], both read as
`GetUint32` (the exact getter sp4a-screen uses to consume them). keys[0] is the
authoritative bound; the log names keys[1] as the value to lower, suggesting the
bound as its new value. `kRepair` policy, report-only in the same posture as the
UA entry (`ValidateAtStartup` logs, does not write).

## Why this is a REAL invariant (the discipline gate)

The screen's available area is the display minus the OS chrome (taskbar, dock,
menu bar). It is physically a **subset** of the display: `availWidth ≤ width`
and `availHeight ≤ height` hold on every real machine, with equality in the
no-taskbar / fullscreen-kiosk case. A configuration that reports
`availWidth > width` describes a work area larger than the screen containing it
— a state no real device produces, and a contradiction a detector reads for
free by comparing two `screen` properties.

Contrast with **battery-coherence, rejected 2026-09-07**: battery level and
charging state have no cross-surface physical constraint the *config* can
violate — a "coherent battery" invariant would have been manufactured, an
assertion invented to have something to assert. Geometry is the opposite: the
nesting is a hard physical fact that predates the fingerprint, and the config
*can* express its violation. That is the line between an invariant worth
enforcing and busywork. This one is on the right side of it, and the SP5
design §4.3 catalogue names it explicitly ("Window geometry nests:
`inner ≤ outer ≤ avail ≤ screen`").

## Scope — what it catches and what it deliberately does not

**Catches:** both keys present *and* keys[1] > keys[0]. Exactly the
contradiction between two configured values.

**Out of scope, by the boundary the UA entry already drew** (coherence_validator.cc
CheckSameOsFamily, invariants.json `why`):

- **Absent / lone-spoofed key.** availWidth set, width left real: only one value
  is configured, so there is no disagreement to demonstrate. Per the established
  rule an absent partner constrains nothing for a relational entry; the
  one-channel-spoofed incoherence is the startup diagnostic's job, not this
  entry's. **Adjacent gap, noted not filled:** the startup diagnostic
  (browser_main_loop.cc) has a UA-metadata partial-set warning
  (`UaMetadataKeyHasValue`) but **no** screen-cluster equivalent, so
  availWidth-without-width is currently unwarned anywhere. Closing that is a
  separate bespoke-diagnostic task, not a relational invariant; expanding this
  entry to read stock values would change what "constrains nothing" means for
  every entry in the registry.
- **Wrong-type value.** `GetUint32` requires a non-negative JSON integer; a
  string or float returns nullopt, camoucfg falls back to the real value, and
  there is no configured contradiction. An out-of-range single value is SP5b's
  (domain_validator) to reject, not this entry's.

**Deferred, not this slice:**

- **`outer ≤ avail` (window fits work area).** The design's fuller nesting.
  Deferred for three reasons the advisor flagged: (1) the real bound is `avail`,
  not `screen` — `outerHeight ≤ screen.height` would pass a window overlapping
  the taskbar, itself the CreepJS-shaped tell; (2) it must first be confirmed
  that `window.outerWidth` is config-driven *and* page-visible (window-geometry
  may derive it), else the invariant checks a value the operator cannot set;
  (3) it constrains a window-geometry key against sp4a's, so it is
  window-geometry-owned, not sp4a's to add here. `outer ≤ screen` is simply the
  wrong bound and is not added at all.
- **`0 ≤ screenX ≤ screen.width − outerWidth` (window position).** A three-key
  relation. `Invariant.keys` is fixed at 2, and widening it is a deliberate
  flagged moment ("the moment to check that every relation still knows how many
  keys it reads"), not a side effect of this slice.
- **`availLeft + availWidth ≤ width` / `availTop + availHeight ≤ height` (work-area
  offset nesting).** `availWidth ≤ width` is necessary but not sufficient: a
  config `{width:1920, availWidth:1920, availLeft:100}` places the work area
  partly off-screen and this entry does not catch it. `kScreenAvailLeft` /
  `kScreenAvailTop` are real, config-settable, page-visible sp4a keys, so the
  relation is expressible — but it is three keys, the same 2-key-limit class as
  window position above, and deferred for the same reason. `fits-within` is
  therefore the gross-tell bound (work area not larger than the display), not
  full work-area validation.

## RED

`MutationIsCaughtAndNothingElseIs` is driven once per registry mutation, each in
its own process (config latches per process). The new mutations:

```
screen-avail-width-fits   {"screen.width":1920,"screen.availWidth":2560}   -> repaired_key "screen.availWidth"
screen-avail-height-fits  {"screen.height":1080,"screen.availHeight":1440} -> repaired_key "screen.availHeight"
```

Against the current validator (no `kFitsWithin`, invariant not registered),
`Validate()` returns zero violations for these configs → `ASSERT_EQ(size, 1u)`
FAILS. That is the RED. GREEN once the invariant + `CheckFitsWithin` land.
`RegistryMatchesGeneratedHeader` and `MutationsExistForEveryInvariant` are
already generic and cover the new entries with no change.

## Harness cost (advisor: "you're widening the harness too")

`run_coherence_tests.sh` hardcodes a single `MutationIsCaughtAndNothingElseIs`
invocation for `ua-os-family-agrees`. A new mutation defined in `kMutations` but
not driven by the runner is "documentation, not enforcement" — the exact failure
the mutation harness exists to prevent. The runner is restructured to drive the
case once per registry mutation, plus a drift guard asserting the runner's
mutation set covers every invariant id in `invariants.json` (same shape as its
existing `--gtest_list_tests` count guard).

## No existing consumer breaks on the new relation

`grep` across scripts/ and pythonlib/ found no consumer that parses
`invariants.json` and switches on the `relation` string. The two references
(`check_additions_build.py`, `check_checkout_sync.sh`) treat it as data to copy
and sync-check, not to interpret. The `$comment`'s "fingerprint generator
self-check" is SP6a-future and does not exist yet. So adding the `fits-within`
relation string breaks no shipped consumer. `apply.sh:23` copies
`settings/invariants.json` → `components/camoucfg/invariants.json`, so
`RegistryMatchesGeneratedHeader` resolves it on a clean worktree.

## Verify — RESULT (all green on the box, 2026-09-07)

1. `run_coherence_tests.sh` — **6/6**, all three mutations driven and reported
   per-id (`MutationIsCaughtAndNothingElseIs[screen-avail-width-fits]` etc.).
   `CleanConfigProducesNoViolations` now sets an equal screen cluster
   (availWidth == width) and asserts the four screen keys resolved, exercising
   the equality boundary the `<=` check depends on.
2. **RED run empirically** (not just reasoned): flipping `CheckFitsWithin`'s
   `<=` to `>=` and rebuilding (8 steps) turned exactly the two `screen-avail-*`
   mutations red (`ASSERT_EQ size 1u`), ua and every guard case still green —
   5/6, exit 1. Restored and rebuilt → 6/6. (A first attempt with an early
   `return {}` failed `-Werror` on unreachable code, so the runner ran the stale
   binary and falsely printed 6/6 — caught by checking the build reported
   `Build Succeeded: N steps`, not by the runner.)
3. `verify_sp5a.py` — extended to **6/6**. New C5 matches the full geometry log
   line `...'screen.availWidth' is '2560', which disagrees with 'screen.width'.
   It should be '1920'.`, pinning `base::NumberToString`'s integer formatting
   end-to-end (the unit test checks the repaired key, not the message). New C6
   confirms a geometry violation exits 13 under `CAMOU_CONFIG_STRICT` through the
   invariant-agnostic refusal. C1–C4 unchanged and green → no UA regression.

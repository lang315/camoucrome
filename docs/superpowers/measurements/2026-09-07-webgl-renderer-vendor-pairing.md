# webGl renderer ↔ vendor all-or-nothing (SP5 pairing, reject-under-strict)

**Date:** 2026-09-07
**Slice:** `webGl:renderer` ↔ `webGl:vendor` (and the webGl2 pair) bound
all-or-nothing, enforced at browser-process startup
**Owner:** SP3 exposes the knobs (sp3b-i), SP5 enforces the pairing — the
deferred obligation logged at `sp3-webgl-canvas-design.md` §253 item 1 and the
invariant table row §283.

## The leak

`webGl:renderer` and `webGl:vendor` are independent config keys. The consumer
(`webgl_rendering_context_base.cc`, sp3b patch :281-311) resolves each on its
own: `getParameter(UNMASKED_RENDERER_WEBGL)` returns the configured renderer if
set **else the real driver string** `ContextGL()->GetString(GL_RENDERER)`, and
`getParameter(UNMASKED_VENDOR_WEBGL)` does the same with `GL_VENDOR`. There is
no cross-check.

So a half-configured profile — `{"webGl:renderer":"NVIDIA GeForce RTX 4090"}`
with no `webGl:vendor` — makes a page read the spoofed renderer beside **this
machine's real GL vendor**. The two are read together through one extension
(`WEBGL_debug_renderer_info`); a vendor that does not match its renderer is a
textbook GPU tell, and it fires by default on the exact operator mistake of
setting one knob and forgetting its pair. Design §283: "A renderer string
without its matching vendor is invalid config and must be rejected at parse
time, not silently half-applied."

## Why this is a startup check, not a registry invariant

The coherence machinery has two mechanisms with an explicit, already-documented
division of labour (`coherence_validator.cc:37-48`, and the diagnostic block
patched into `browser_main_loop.cc` by
`patches/sp5a-coherence-validator.patch:139-143`):

- **The invariant registry** (`kAllInvariants` / `Validate`) owns relations
  between keys that are **both present** — value contradictions, with a
  repair target. Its own comment states an absent key "constrains nothing FOR
  THIS RELATIONAL ENTRY".
- **The startup diagnostic** owns **presence/absence** incoherence — one
  channel configured, its partner left to leak the real value.

renderer ↔ vendor is a presence relation, so it does **not** belong in the
registry (no new `Relation`, no `invariants.json` entry, no mutation-harness
entry). Design §256-257 places it precisely: "SP3b-i exposes the knobs; **the
validator** enforces the pairing." That is `coherence_validator.cc`, alongside
`ValidateDomains`, not the ua: half-config warn block in `browser_main_loop.cc`
— because the validator already owns `strict`, is unit-testable in
`components_unittests`, and feeds the existing refusal path.

**Severity differs from the shipped ua: half-config, and the difference is
worth stating honestly.** The ua:osInfo/ua:platform half-config (the diagnostic
block, `patches/sp5a-coherence-validator.patch:139-177`) is `LOG(WARNING)`-only
and never refuses. SP1 actually asked for the SAME all-or-nothing rejection
there — `sp1-navigator-identity-design.md:419-423`: "a partial config is
rejected rather than producing a half-spoofed identity … Validating it is SP5's
job; declaring it is SP1's." So sp5a's warn-only ua: block under-delivers on
that SP1 obligation; it is a pre-existing gap, not one this slice introduces or
touches. This slice implements design line 283's "must be rejected" faithfully:
a webGl pairing violation is `LOG(ERROR)` on the strict-refusal path, exactly
like a registry or domain violation. Aligning the ua: block to reject (per SP1
:419-423) is that block's business — flagged here as a deferred item, left out
of scope so this slice stays surgical.

## The fix

Two functions in `coherence_validator.{h,cc}`:

- **`CheckPairing(renderer_resolves, vendor_resolves, renderer_key, vendor_key)`**
  — pure, no config access. Returns a `PairingViolation{present_key,
  absent_key}` when exactly one side resolves, `nullopt` when both or neither
  do. Factored out for the same reason `CheckDomain` is (domain_validator.h
  :26-34): the logic is a security branch (`==` vs `!=` silently disables or
  over-fires the check) and must be testable with literals, not only through a
  per-process config load.
- **`ValidatePairing(scope)`** — reads config and calls `CheckPairing` once per
  API (webGl, webGl2). "Resolves" mirrors the consumer's **full** resolution:
  the dedicated key (`GLRenderer`/`GLVendor`) **or** a string entry in the
  parameters table at the pname (`GLParam(0x9246 / 0x9245)`), the exact two
  steps sp3b :281-311 uses. A check reading only the dedicated key would
  false-refuse `{"webGl:renderer":"…","webGl:parameters":{"37445":"…"}}` — a
  config the page actually sees whole — and under strict that refuses a valid
  fingerprint.

`ValidateAtStartup` collects `ValidatePairing` alongside `Validate` and
`ValidateDomains` before its early return, logs each with its own `LOG(ERROR)`,
and the existing `return !strict` refuses startup under `CAMOU_CONFIG_STRICT`.
`GLParam` reads `ParsedConfig()` and ignores `scope`, which is correct at browser
startup with `GlobalScope()`.

Log line (presence, no value substitution — an empty "should be ''" would be
the misleading-message anti-pattern this project forbids):

```
camoucfg: '<present_key>' is set but its pair '<absent_key>' is not. A page
reads both through WEBGL_debug_renderer_info, so the configured value sits
beside this machine's real one -- an incoherent pair. Set both, or neither, or
set CAMOU_CONFIG_STRICT=1 to refuse startup.
```

## What this does NOT do

This slice does **not** change what a page sees. Under non-strict, a half-config
still leaks the host vendor after this ships — the design says *reject*, not
*repair*, and repairing would mean inventing a vendor the operator did not
choose (the same reasoning that keeps the ua: half-config warn-only). The
deliverable is: today the half-config produces **no** log line and strict
startup **succeeds**; after, it produces a `LOG(ERROR)` and strict startup
**exits 13**. The content_shell read of spoofed-renderer-beside-host-vendor is
the *motivation* row — it proves the leak is real — not a row this slice turns
green.

## RED / GREEN

**Unit (`components_unittests`, pure, one process):** `PairingTest` over
`CheckPairing` with literals — renderer-only → names vendor absent; vendor-only
→ names renderer absent; both → none; neither → none. RED is that the symbol
does not exist (link failure) until implemented; the test locks the branch.

**Box e2e (`verify_webgl_pairing.py`, content_shell startup stderr + exit
code, modelled on `verify_sp5a.py`):**

| case | config | RED (before) | GREEN (after) |
|------|--------|--------------|---------------|
| WP-MOTIVATION | `{"webGl:renderer":"NVIDIA GeForce RTX 4090"}` | page reads spoofed renderer + **host** vendor | unchanged (still leaks — reject-not-repair); the differ-guaranteed proof the leak exists |
| WP-HALF-LOG | same | no `camoucfg:` line | `LOG(ERROR)` naming `webGl:vendor` absent |
| WP-HALF-STRICT | same, `CAMOU_CONFIG_STRICT=1` | starts (DevTools opens) | exits 13, refusal message |
| WP-VENDOR-ONLY | `{"webGl:vendor":"Google Inc. (NVIDIA)"}` | no line | `LOG(ERROR)` naming `webGl:renderer` absent |
| WP-BOTH | `{"webGl:renderer":"…","webGl:vendor":"…"}` | no line | no line, starts (both resolve) |
| WP-PARAMS-GUARD-VENDOR | `{"webGl:renderer":"…","webGl:parameters":{"37445":"Google Inc. (NVIDIA)"}}` | no line | **no** line, starts — vendor resolves via the parameters table; the false-refusal guard (vendor arm) |
| WP-PARAMS-GUARD-RENDERER | `{"webGl:vendor":"…","webGl:parameters":{"37446":"NVIDIA GeForce RTX 4090"}}` | no line | **no** line, starts — renderer resolves via the parameters table; the mirror, and the ONLY test of `GLStringResolves`'s renderer arm (un-unit-testable: config singleton) |
| WP-CROSS | `{"webGl:renderer":"…","webGl2:vendor":"…"}` | no line | two `LOG(ERROR)` lines (webGl vendor absent, webGl2 renderer absent) — the two APIs are independent |
| WP-NONE | none | no line | no line, starts |

WP-MOTIVATION is the row where the reference is guaranteed to differ (host GL
vendor ≠ the spoofed NVIDIA renderer's implied vendor, CLAUDE.md #4). WP-PARAMS-
GUARD-VENDOR and WP-PARAMS-GUARD-RENDERER are the two that would false-refuse a
valid config if "resolves" read only the dedicated key — one per arm of
`GLStringResolves`'s pname ternary, since the config singleton makes that helper
un-unit-testable and this script is its only regression surface (a pname swap in
either arm ships silent otherwise). WP-CROSS proves webGl and webGl2 are checked
independently, not collapsed.

## Verify — RESULT (box, 2026-09-07)

- **`PairingTest.*` 4/4** (`components_unittests`, build "Build Succeeded: 10
  steps" — a real rebuild of `coherence_validator.o` + unittest + relink, not a
  stale-binary no-op): renderer-only names vendor absent, vendor-only names
  renderer absent, both/neither silent.
- **`verify_webgl_pairing.py`: RED baseline** (current binary, before the
  change) — WP-HALF-LOG / WP-HALF-STRICT / WP-VENDOR-ONLY / WP-CROSS **FAIL**
  (no `camoucfg:` line, strict started); the four silent-line cases PASS
  vacuously (no pairing line exists yet). **After: GREEN 9/9.** WP-HALF-LOG logs
  `webGl:vendor` absent, WP-VENDOR-ONLY logs `webGl:renderer` absent, WP-CROSS
  logs both `webGl:vendor` and `webGl2:renderer` absent (the two APIs
  independent), WP-HALF-STRICT exits 13 with the refusal message, WP-PARAMS-
  GUARD-VENDOR and WP-PARAMS-GUARD-RENDERER both stay silent (each arm of
  `GLStringResolves`'s pname ternary resolves via the parameters table — the
  false-refusal guard holds on both), WP-BOTH/WP-NONE silent. The renderer-arm
  guard was added in review: the vendor arm alone left a pname-swap regression
  in the renderer arm shippable-silent, since the config singleton makes
  `GLStringResolves` un-unit-testable and this script is its only surface.
- **WP-MOTIVATION, before AND after (unchanged, as designed):** host =
  `('ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) …), SwiftShader
  driver)', 'Google Inc. (Google)')`; renderer-only session =
  `('NVIDIA GeForce RTX 4090', 'Google Inc. (Google)')`. The spoofed NVIDIA
  renderer sits beside the leaked host vendor `Google Inc. (Google)` both before
  and after — the leak the check warns about is real (host renderer is
  SwiftShader, ≠ NVIDIA, so the differ-guarantee holds), and this slice rejects
  rather than repairs it, exactly as the doc states.
- **Regression:** `verify_sp5a.py` 6/6 (the `ValidateAtStartup` change is
  transparent to non-webgl configs — `ValidatePairing` returns empty, so the ua
  and geometry startup diagnostics are untouched); `run_coherence_tests.sh` 6/6
  (registry suite unaffected — `PairingTest` is a separate suite, the
  `CoherenceValidatorTest.*` count and the `invariants.json` drift guard are
  unchanged).

## Patch re-extraction

Clean, and this is the reason to prefer the validator over a
`browser_main_loop.cc` edit: `coherence_validator.{h,cc}` and
`coherence_validator_unittest.cc` are `additions/camoucfg/` whole-file copies
(apply.sh `cp additions/camoucfg/*`), not patch hunks. No `patches/*.patch`
changes, no `invariants.h` / `invariants.json` / schema changes, no
`AllPoliciesAreRepair` static_assert touch, and the registry's documented
"absent key constrains nothing" boundary stays exactly where its comment drew
it. The `verify_webgl_pairing.py` script is a new untracked file staged
explicitly in the commit.

## renderer → OS field-invariant — REJECTED (2026-09-07)

The sibling relation considered at the same checkpoint — `webGl:renderer`
implies an OS (an Apple GPU under a claimed Windows UA is incoherent, design
§287) — was **rejected without writing code**, the way battery-ii §6 and
webrtc-ii were. Reasons, fatal one first:

1. **The fork's own default renderer format defeats the classifier.** The
   in-repo WebGL strings are bare marketing names (`verify_sp3b.py:70` —
   `"NVIDIA GeForce RTX 4090"`, `"AMD Radeon RX 7900 XTX"`), which carry no OS
   token. A renderer→OS classifier returns kUnknown for exactly the shape the
   fork ships, so the entry would fire on almost nothing — it reads as
   protection and provides none, the precise failure
   `EveryInvariantKeyIsDeclaredInTheRegistry` exists to prevent, one level up.
2. **The backend tokens are not a closed set.** The tokens that *do* imply an
   OS (`Direct3D11` ⟹ Windows) sit beside tokens that imply nothing: Mesa runs
   on Windows and macOS, `OpenGL` appears everywhere, ANGLE's Metal/Vulkan/GL
   backends cross OSes. Only D3D is near-definitional, so any map would be a
   hand-built guess encoding ANGLE's format from memory — CLAUDE.md #1/#6, the
   pattern this project keeps paying for.
3. **The design already assigns it elsewhere.** §287: "SP3 cannot enforce this
   alone; it is SP5's cross-surface job. SP3's obligation is to expose the
   strings as config so SP5 *can* enforce it." §7.1 makes that enforcement
   whole-profile — shipping captured GPU profiles, never hand-edited fields —
   so a field-level renderer→OS invariant is the wrong mechanism by design, not
   merely hard.
4. **Not a derive either.** Unlike navigator.platform (one frozen reduced
   literal per OS), there is no single canonical renderer for an OS to derive
   toward — every OS runs many GPUs — so the derive route that fit
   navigator.platform does not fit here.

**Residual owner:** the whole-profile coherence of §7.1 / the profile generator
(renderer must match the captured vendor, parameters, and extensions together),
and — for the *absence* case a profile cannot cover — the renderer-absent
startup diagnostic already deferred. Not this slice, and not on bare in-repo
strings.

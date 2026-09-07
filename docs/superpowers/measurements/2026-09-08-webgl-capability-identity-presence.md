# A WebGL capability profile without its identity strings (SP5 presence, reject-under-strict)

**Date:** 2026-09-08
**Slice:** any spoofed WebGL capability field (`webGl:parameters`,
`webGl:supportedExtensions`, `webGl:shaderPrecisionFormats`,
`webGl:contextAttributes`, and the webGl2 mirrors) set while **neither**
`webGl:renderer` nor `webGl:vendor` resolves is reported at startup and refuses
under `CAMOU_CONFIG_STRICT`.
**Owner:** SP3 exposes the knobs; SP5 enforces coherence (design §7.1 makes the
unit of configuration a whole captured profile, not editable fields).

## The measured leak

`{"webGl:parameters":{"3379":16384}}` alone (3379 = MAX_TEXTURE_SIZE), on the box
under SwiftShader:

| config (alone) | spoofed surface reads | UNMASKED_RENDERER reads |
|---|---|---|
| baseline (none) | maxTex 8192, ext 36, precision 23, preserveDrawingBuffer false | SwiftShader |
| `webGl:parameters` | **maxTex 16384** | SwiftShader (host) |
| `webGl:shaderPrecisionFormats` | **precision 20** (host 23) | SwiftShader (host) |
| `webGl:contextAttributes` | **preserveDrawingBuffer true** (host false) | SwiftShader (host) |
| `webGl:supportedExtensions` (incl. debug ext) | **ext count 2** (host 36) | SwiftShader (host) |
| reverse: `webGl:renderer`+`webGl:vendor` | identity NVIDIA | host maxTex 8192, ext 36 |

The extensions row was measured with `{"webGl:supportedExtensions":
["WEBGL_debug_renderer_info","OES_element_index_uint"]}` — a realistic capture
keeps the debug extension, so the renderer stays readable (host SwiftShader)
beside the shrunk ext count. The check itself fires on any non-empty list; the
verify script's `CP-EXT-LOG` row omits the debug ext deliberately to prove the
presence gate does not depend on it.

The first four rows are the leak: a spoofed GPU **capability** beside the
machine's real GPU **identity**. A detector reading "MAX_TEXTURE_SIZE 16384
(high-end) but renderer SwiftShader (software rasterizer)" catches it with one
comparison. §7.1(c) named this exact failure — "operators supply raw values …
guarantees incoherent configurations in practice."

## One-directional: capability ⟹ identity, not the reverse

The reverse row (identity set, capabilities host) also disagrees — a spoofed
NVIDIA renderer beside the host's maxTex 8192 — but that is **out of scope**, for
a concrete reason: identity-strings-only is the fork's own supported simple
spoof (`verify_sp3b.py` V2 sets exactly `webGl:renderer`+`webGl:vendor`), and
design §284 assigns the "do the numeric limits match the claimed GPU" question to
whole-profile shipping (the SP5 profile database, which does not exist yet).
Requiring capabilities whenever identity is set would refuse every simple spoof.
So the check is strictly one-directional, and this doc records the reverse as a
real-but-owned-elsewhere disagreement.

## Gated on identity FULLY absent (no double-report with the pairing check)

The renderer↔vendor pairing check (`db71830`) already fires when exactly one of
`webGl:renderer`/`webGl:vendor` resolves, naming the missing one. So this check
gates on **both** absent (neither renderer nor vendor resolves): that is the case
the pairing check calls coherent, and the unique contribution here. When exactly
one identity string is set, the pairing check owns it and this check stays silent
— proven by a test row, not assumed.

"Resolves" reuses `GLStringResolves` (the pairing check's helper), which already
mirrors the consumer's full resolution: the dedicated key OR a string in the
parameters table at the pname.

## Presence semantics: empty = absent, uniformly (read from the consumers)

"Capability configured" must be type-aware and match each consumer, or a config
that spoofs nothing false-refuses under strict. Reading the four consumers
(`mask_config_internal.cc`, sp3b patch) settles it — and it is NOT what analogy
suggests:

- **parameters / shaderPrecisionFormats:** `cfg.FindDict(key)`; an absent key or a
  present-but-empty dict makes every pname resolve to nullopt → the host value.
  So **empty dict = absent**.
- **contextAttributes:** `GLContextAttrs` returns the dict; the hook reads
  individual fields off it, so an empty dict leaves every field real. **Empty
  dict = absent.**
- **supportedExtensions:** the hook (`sp3b:124-137`) reads
  `GetStringList(...)` then `if (!camou_list.empty())` — an **empty list falls
  through to the real extension set**, identical to absent. So **empty list =
  absent too**, the *opposite* of the "empty list advertises nothing" guess. Read
  the consumer; do not reason by analogy (CLAUDE.md #2).

`FindDict` returns null for a non-dict value and `GetStringList` returns empty for
a non-list, so `{"webGl:parameters":"oops"}` is correctly "not configured" — the
type-blindness the ua: slice fixed, avoided here by construction and proven by a
mutation test.

So the uniform predicate per field is **present AND non-empty**, exposed as
`GLParamsConfigured` / `GLShaderPrecisionConfigured` / `GLContextAttrsConfigured`
/ `GLExtensionsConfigured` in `gl_params.{h,cc}`.

## The check

`coherence_validator.cc`: a pure `CapabilityLeaksIdentity(cap_configured,
renderer_resolves, vendor_resolves)` returns true iff `cap_configured &&
!renderer_resolves && !vendor_resolves` (testable with literals like
`CheckPairing`). `ValidateCapabilityIdentity(scope)` loops the two APIs × the four
capability fields; when identity is fully absent it emits one `CapabilityViolation`
per configured field. Collected in `ValidateAtStartup` before the early return,
its own `LOG(ERROR)` (not `PairingViolation`'s — that message names
WEBGL_debug_renderer_info, wrong here), feeding the existing `return !strict`.

Message: `'webGl:parameters' is set but neither 'webGl:renderer' nor
'webGl:vendor' is. A page reads the configured GPU capability beside this
machine's real GPU identity — an incoherent profile. Set the identity strings
from the same capture, or set CAMOU_CONFIG_STRICT=1 to refuse startup.`

## RED / GREEN

**Box e2e (`verify_webgl_capability_identity.py`):**

| case | config | RED (before) | GREEN (after) |
|------|--------|--------------|---------------|
| CP-MOTIVATION | `{"webGl:parameters":{"3379":16384}}` | maxTex 16384 beside SwiftShader | unchanged (report-not-repair) |
| CP-PARAMS-LOG | same | no line | `LOG(ERROR)` naming webGl:parameters |
| CP-PARAMS-STRICT | same, strict | starts | exits 13 |
| CP-EXT-LOG / CP-SHADERPREC-LOG / CP-CTXATTRS-LOG | each field alone | no line | line naming that field |
| CP-WITH-IDENTITY | params + renderer + vendor | no line | no line (identity present) |
| CP-PARTIAL-IDENTITY | params + renderer only | no line | pairing line present, capability line **absent** (both-absent gate) |
| CP-IDENTITY-ONLY | renderer + vendor, no capability | no line | no line (one-directional) |
| CP-WEBGL2 | `webGl2:parameters` alone | no line | webGl2 line; webGl silent |
| CP-EMPTY-DICT | `{"webGl:parameters":{}}` | no line | **no** line (empty = absent) |
| CP-EMPTY-LIST | `{"webGl:supportedExtensions":[]}` | no line | **no** line (empty list falls through to real) |
| CP-WRONG-TYPE | `{"webGl:parameters":"oops"}` | no line | **no** line (FindDict null) — mutation-proven |

CP-EMPTY-DICT / CP-EMPTY-LIST / CP-WRONG-TYPE are the rows proving the presence
semantics were read from the consumer, not assumed. CP-PARTIAL-IDENTITY proves
the both-absent gate (no double-report with the pairing check). CP-WRONG-TYPE is
mutation-proven: flipping the presence getter to a type-blind `HasKey` must turn
it red.

## What this does NOT do

Report, not repair — the capability still applies under non-strict, beside the
leaked host identity (repairing would mean inventing renderer/vendor strings the
operator did not choose). CP-MOTIVATION reads identically before and after. It is
a **presence** guard: it does not check that the numeric values match the claimed
GPU (§284's value coherence), which needs the SP5 profile database and is the
residual owner. A presence guard catches hand-edits; it cannot catch a wrong
capture.

Two known edges, both erring toward over-report (safe: they never miss a real
leak, they can only over-refuse under strict):

- A **non-empty map of only unrecognized entries** — `{"webGl:parameters":{"99999":5}}`
  — reads as "configured" though the consumer spoofs nothing (that pname is never
  read). Distinguishing it would mean validating pname/value shapes here, which
  is the value-coherence job the SP5 profile database owns; a presence check
  stays a presence check.
- A **bare `...:blockIfNotDefined` flag** with no capability map is deliberately
  NOT "configured" (it spoofs no value), so it does not fire — noted in
  `gl_params.h`'s comment. Whether a bare block flag beside real identity should
  itself be a coherence concern is a separate question for the design owner.

## Verify — RESULT (box, 2026-09-08)

- **Build "Build Succeeded: 18 steps"** — real recompile of `gl_params.o` +
  `coherence_validator.o` + unittest, relink of both targets.
- **`CapabilityIdentityTest.*` + `PairingTest.*` 8/8** (pure literals): a
  configured capability with both identity strings absent leaks; partial identity
  (either one resolving) does not (the pairing check's); full identity is
  coherent; no capability never leaks.
- **`verify_webgl_capability_identity.py`: RED baseline** (current binary) — the
  six capability rows (CP-PARAMS-LOG/STRICT, CP-EXT-LOG, CP-SHADERPREC-LOG,
  CP-CTXATTRS-LOG, CP-WEBGL2) **FAIL** (no line, strict started); the other seven
  PASS. **After: GREEN 13/13.** Each capability alone logs naming itself and
  strict exits 13; full identity / identity-only / partial-identity are silent of
  the capability line (CP-PARTIAL-IDENTITY shows the pairing line instead, proving
  the both-absent gate — no double-report); webGl2 is independent; empty dict,
  empty list, and a non-dict value are all silent (empty = absent, uniformly).
- **Presence semantics proven by mutation, for both structurally-distinct
  getters:** flipping the **dict** getter `GLParamsConfigured` to a type-blind
  `HasKey(...)` and rebuilding turned exactly CP-EMPTY-DICT and CP-WRONG-TYPE red
  (both depend on its present-AND-non-empty, type-aware logic); separately
  flipping the **list** getter `GLExtensionsConfigured` to `HasKey(...)` turned
  exactly CP-EMPTY-LIST red (the empty-list-falls-through-to-real semantics is
  the one most at risk of being wrong-by-analogy, so it is observed, not
  reasoned); each time the other rows stayed green and restoring returned 13/13.
  `GLShaderPrecisionConfigured` and `GLContextAttrsConfigured` share the dict
  getter's `FindDict`+non-empty structure already mutation-covered.
- **An undiagnosed low-rate flake, disclosed:** three per-field webGl2 rows
  (extensions, shaderPrec, contextAttrs) were trialed to widen webGl2 coverage.
  Adding them surfaced an intermittent (~1-in-6 full runs) content_shell startup
  miss on **one** row only — `webGl2:shaderPrecisionFormats`, three of three
  identified misses. Cause not diagnosed. The check path is deterministic by
  construction (config → `FindDict` → violation → `LOG`), so the miss is upstream
  of the check, but where is unknown; the single affected row is weak evidence for
  a harness-general flake and equally consistent with something about that one
  config. The three rows were dropped rather than ship intermittent green: the
  webGl/webGl2 mixup they guard against is structurally impossible (the `Cap[]`
  loop keys all four fields off one `is_webgl2` and sets the identity keys once per
  iteration), and CP-WEBGL2 already exercises the `is_webgl2=true` wiring. The
  retained 13 rows ran clean across ~6 repeats — which does not rule out a low-rate
  flake reaching them, only that none was observed. If a future run shows a lone
  12/13 or 13/14, this is the prior.
- **CP-MOTIVATION, before AND after (unchanged):** maxTex 16384 beside the host
  SwiftShader renderer — the leak is real and this slice reports rather than
  repairs it.
- **Regression:** `verify_webgl_pairing.py` 9/9 (the pairing check is untouched
  and the both-absent gate keeps the two from double-reporting);
  `run_coherence_tests.sh` 6/6 (registry suite unaffected — this check is
  collected in `ValidateAtStartup`, not the registry). Because the new capability
  vector is ANDed into `ValidateAtStartup`'s early return, the other startup
  diagnostics were re-run against the same binary: `verify_sp5a.py` 6/6,
  `verify_navplatform_bucket.py` 7/7, `verify_ua_halfconfig_reject.py` 6/6 — no-GL
  configs are untouched.

## Patch re-extraction

None: `gl_params.{h,cc}`, `coherence_validator.{h,cc}`, `coherence_validator_unittest.cc`
are `additions/camoucfg/` whole-file copies. No `patches/*.patch` change (confirmed
by grep — the capability reads and the check are all in additions).

# navigator.platform ↔ claimed OS — the same-platform-bucket invariant

**Date:** 2026-09-08
**Slice:** a registry invariant catching an EXPLICIT `navigator.platform` that
disagrees with the OS claimed in the UA (`ua:osInfo`)
**Owner:** SP1b navigator leaves ↔ SP5a coherence — the complement the
navigator.platform derive deferred (`2026-09-07-navigator-platform-derive.md`
lines 164-167: "kSamePlatformBucket … would additionally catch an EXPLICIT
navigator.platform that disagrees with the claimed UA — the case this derive,
being a fallback below the explicit key, intentionally leaves to the operator").

## The leak

The navigator.platform derive (shipped `a6e0045`) fills navigator.platform from
the claimed OS **only when the key is absent** — an explicitly configured value
wins (its RP-EXPLICIT case proves the derive never overrides). So an operator
who claims Windows in the UA *and* explicitly sets
`navigator.platform = "MacIntel"` ships an incoherent pair the derive leaves
alone: `navigator.userAgent` says Windows, `navigator.platform` says a Mac. A
page reads both without effort; the derive cannot catch it because the value is
present and the derive is a fallback.

This is a relation between two keys that are **both present** — a value
contradiction — so unlike the renderer↔vendor pairing (a presence relation,
shipped `db71830`) it belongs in the invariant **registry**, beside
`ua-os-family-agrees` and the screen `fits-within` entries.

## Why a new relation (`kSamePlatformBucket`)

It cannot reuse `kSameOsFamily`, and not only because of the static_assert that
pins that relation to the ua:osInfo/ua:platform pair (invariants.h:161-166).
`CheckSameOsFamily` repairs keys[1] via `CanonicalUaChPlatformFor`, so it would
log "should be 'Windows'" — the UA-CH token — when the right repair target is
`"Win32"`, the navigator.platform literal. And a family-level compare
false-fires the bucket: reverse-mapping the platform `"Linux x86_64"` back to an
OS family lands on Linux, yet a ChromeOS claim is coherent with `"Linux x86_64"`
(that is the reduced platform ChromeOS reports). The correct primitive is a
**canonical navigator.platform string compare**, which collapses Linux and
ChromeOS into one bucket by construction — hence the name.

The check: `CheckSamePlatformBucket` reads the OS family of keys[0] (`ua:osInfo`)
with `OsFamilyOfKey` — the same helper `CheckSameOsFamily` uses, so keys[0] stays
literally authoritative and the log is honest. If that family is known, and
`navigator.platform` is configured, and its value ≠
`CanonicalNavigatorPlatformFor(family)`, it reports a violation naming
navigator.platform as the key to change and the canonical value as its repair
target — exactly the value the derive would have produced had the key been
absent.

## Disjoint from the derive, by design

- **Derive** (navigator_base.cc): fires when navigator.platform is **absent**,
  computing the OS via `ClaimedOs(scope)` (which reads `ua:osInfo` first, then
  falls back to `ua:platform`).
- **This invariant** (coherence_validator.cc): fires when navigator.platform is
  **present**, anchored on `ua:osInfo` (keys[0]) via `OsFamilyOfKey`.

They never both fire on the same config (one needs the key absent, the other
present). The invariant deliberately anchors on `ua:osInfo` rather than the
derive's `ClaimedOs`: keys[0] is the authoritative key by the registry's
contract (invariants.h:41-43), and using `ClaimedOs`'s osInfo→platform fallback
would let the log say "disagrees with 'ua:osInfo'" for a config where only
`ua:platform` is set — naming a key that is not there. The cost is that a
`ua:platform`-only OS claim is out of this entry's reach, the same boundary
`ua-os-family-agrees` already has, and the sp5a half-config diagnostic already
warns on `ua:platform` set without `ua:osInfo`.

## RED / GREEN

**Unit (`components_unittests`):** a `kSamePlatformBucket` mutation
(`{"ua:osInfo":"Windows NT 10.0; Win64; x64","navigator.platform":"MacIntel"}`)
drives `MutationIsCaughtAndNothingElseIs` — exactly one violation, `repaired_key
== navigator.platform`. `ua:platform` is absent so `ua-os-family-agrees` stays
silent, geometry is absent, and the pairing check lives in a different vector.
`CleanConfigProducesNoViolations` gains a `navigator.platform` assertion so the
clean side exercises this relation instead of passing vacuously.

**Box e2e (`verify_navplatform_bucket.py`, startup stderr + exit code, modelled
on `verify_sp5a.py`):**

| case | config | RED (before) | GREEN (after) |
|------|--------|--------------|---------------|
| NB-MOTIVATION | `{"ua:osInfo":"Windows…","navigator.platform":"MacIntel"}` | page reads `navigator.platform === "MacIntel"` under a Windows UA | unchanged (explicit wins — report-not-repair); the incoherence is real |
| NB-MISMATCH-LOG | same | no `camoucfg:` line | `LOG(ERROR)` naming navigator.platform, should be `Win32` |
| NB-MISMATCH-STRICT | same, `CAMOU_CONFIG_STRICT=1` | starts | exits 13, refusal message |
| NB-BUCKET-CROS | `{"ua:osInfo":"X11; CrOS x86_64 14541.0.0","navigator.platform":"Linux x86_64"}` | no line | **no** line, starts — ChromeOS accepts `Linux x86_64` (the bucket) |
| NB-BUCKET-LINUX | `{"ua:osInfo":"X11; Linux x86_64","navigator.platform":"Linux x86_64"}` | no line | **no** line — the other bucket member accepts the same value |
| NB-COHERENT | `{"ua:osInfo":"Windows…","navigator.platform":"Win32"}` | no line | no line, starts |
| NB-EXPLICIT-NO-UA | `{"navigator.platform":"FreeBSD amd64"}` | no line | **no** line — no OS claimed (keys[0] unknown), nothing to disagree with |

NB-BUCKET-CROS and NB-BUCKET-LINUX are what justify "bucket" over "family": both
OSes accept `Linux x86_64`. NB-EXPLICIT-NO-UA proves the entry fires only when an
OS is actually claimed (it is not a domain check on navigator.platform).
NB-MOTIVATION is the differ-guaranteed read (a Windows UA beside `MacIntel`).

## What this does NOT do

Report, not repair. Under non-strict, `navigator.platform === "MacIntel"` under a
Windows UA is logged but still served. The read is preserved by **two**
independent layers, and it is worth naming which: the SP1b **derive** honours
an explicitly configured navigator.platform (it fills the key from the claimed
OS only when absent), *and* the validator here is report-only (it logs at
browser startup and never writes back into the config store). Either alone would
keep `MacIntel` on the page — so a future change adding a repair write-path must
change the validator, not the derive. NB-MOTIVATION reads identically before and
after. The rows that flip RED→GREEN are the `LOG(ERROR)` and the strict exit 13.

## Verify — RESULT (box, 2026-09-08)

- **Build "Build Succeeded: 10 steps"** — a real recompile of
  `coherence_validator.o` (with the new relation + switch case) and relink of
  both `components_unittests` and `content_shell`. The two new static_asserts in
  `invariants.h` (`AllPoliciesAreRepair` still holds; the new
  `EverySamePlatformBucketEntryUsesTheNavigatorPlatformPair`) compiled, so they
  pass.
- **`run_coherence_tests.sh` 6/6**, now driving **four** mutations
  (`navigator-platform-matches-os` added): `MutationIsCaughtAndNothingElseIs`
  passes for it (exactly one violation, `repaired_key == navigator.platform`);
  `RegistryMatchesGeneratedHeader` passes with the JSON's fourth entry and the
  new `"same-platform-bucket"` relation branch; `CleanConfigProducesNoViolations`
  passes with the coherent config now setting `navigator.platform:"Win32"`; the
  drift guard (`REGISTRY_COUNT == ${#MUTATIONS[@]}`) holds at 4.
- **`verify_navplatform_bucket.py`: RED baseline** (current binary, before) —
  NB-MISMATCH-LOG and NB-MISMATCH-STRICT **FAIL** (no `camoucfg:` invariant line,
  strict started); the five silent/coherent rows PASS. **After: GREEN 7/7.**
  NB-MISMATCH-LOG logs `navigator.platform` "should be 'Win32'";
  NB-MISMATCH-STRICT exits 13 with the refusal; NB-BUCKET-CROS and NB-BUCKET-
  LINUX both stay silent (ChromeOS and Linux both accept `Linux x86_64` — the
  bucket, the case that justifies a string compare over a family one).
  NB-BUCKET-CROS is load-bearing on a fact outside this diff: `derive.cc`'s
  `kForms` tests the `"CrOS"` marker before `"Linux"` (an X11/CrOS os_info also
  contains no `"Linux"`, but the ordering is asserted by `DeriveTest`), so a
  future reorder that made a ChromeOS os_info resolve to the Linux family would
  still pass here only because both canonicalize to `Linux x86_64` — the string
  compare, not the family, is what keeps this green. NB-COHERENT and
  NB-EXPLICIT-NO-UA silent; NB-MOTIVATION reads
  `navigator.platform === "MacIntel"` under a Windows UA before AND after
  (explicit wins — report-not-repair).
  - Observed while reading RED stderr: the MISMATCH config
    (`ua:osInfo` set, no `ua:platform`) also trips the pre-existing sp5a ua:
    half-config WARNING. Orthogonal and expected; the bucket/coherent rows
    assert absence of the `navigator-platform-matches-os` id specifically, not
    absence of all `camoucfg:` lines, so the coexisting warning does not
    interfere.
- **Regression:** `verify_navplatform_derive.py` 7/7 — the derive still fills an
  ABSENT navigator.platform from the claimed OS, confirming the invariant (which
  fires only on a PRESENT one) is disjoint from it, not a double-hook.

## Patch re-extraction

Clean: `invariants.h`, `coherence_validator.{cc}`, `coherence_validator_unittest.cc`
are `additions/camoucfg/` whole-file copies; `settings/invariants.json` is copied
to `components/camoucfg/invariants.json` by apply.sh; `scripts/run_coherence_tests.sh`
and `scripts/verify_navplatform_bucket.py` are scripts. No `patches/*.patch` change.

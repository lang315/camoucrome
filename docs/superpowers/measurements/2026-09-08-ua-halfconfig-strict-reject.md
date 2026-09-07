# A ua: half-config refuses startup under CAMOU_CONFIG_STRICT

**Date:** 2026-09-08
**Slice:** make the ua:osInfo/ua:platform half-config feed the strict refusal at
browser startup (it was warn-only)
**Owner:** SP1 ↔ SP5a — SP1 declared the all-or-nothing rule, SP5 enforces it.

## The broken contract

`CAMOU_CONFIG_STRICT` is specified to refuse an incoherent fingerprint rather
than launch one (a launched-but-detectable browser is worse than one that
refuses to start). A `ua:osInfo`-only config — a Windows UA string with no
`ua:platform`, so `navigator.userAgentData.platform` and `Sec-CH-UA-Platform`
keep reporting this machine's real OS — is exactly that incoherence, and
`sp1-navigator-identity-design.md:419-423` named it: "a partial config is
rejected rather than producing a half-spoofed identity … Validating it is SP5's
job; declaring it is SP1's." But the sp5a diagnostic block only `LOG(WARNING)`s
it; `strict` started anyway. Strict was a broken contract on the ua: surface.

Two prior slices in this run — the webGl renderer/vendor pairing (`db71830`) and
the navigator.platform bucket invariant (`f9d4314`) — both refuse under strict.
The ua: half-config warn-only was the odd one out, *and* the one the spec most
explicitly asked to reject.

**Camoufox-port concern, resolved not dismissed:** a Camoufox profile carries no
`ua:` keys at all (they do not exist there), so porting one produces
`ua:osInfo`-alone only if the porter *added* that key by hand — a hand-porting
mistake, which is precisely what strict exists to catch. Under non-strict nothing
changes: still a warning.

## Why in-place, not relocated into the validator

The natural instinct is to move the two ua: branches into `coherence_validator.cc`
as a pairing check beside `ValidatePairing`, so the validator (which owns
`strict`) enforces it and the patch edit becomes a deletion. Rejected after
reading the block: the two branches carry **distinct, channel-specific messages**
(osInfo-absent explains the UA-string leak; platform-absent explains the UA-CH
leak) that the WebGL-shaped `PairingViolation` log cannot express without
generalizing the struct, and the block's comments record bugs that were actually
hit (`HasKey` type-blindness at the `UaMetadataKeyHasValue` helper, the
`any_metadata_configured`-vs-`ua_platform_configured` gating). Moving working
code with those comments is regression surface for no user-visible gain; the
detection logic is two booleans, so e2e coverage is proportionate.

## The fix (in-place, `browser_main_loop.cc`)

The two warn branches already detect the two half-config directions. Add a
`bool ua_half_configured`, set true in each branch, and extend the refusal at the
bottom of the block:

```cpp
const bool strict =
    base::Environment::Create()->GetVar("CAMOU_CONFIG_STRICT").has_value();
if (!coherent || (ua_half_configured && strict)) {
```

`coherent` already encodes strict for the registry/domain/pairing checks
(`ValidateAtStartup` returns `!strict` when it finds a violation); the ua:
half-config is detected here rather than there, so its strict read is local. This
adds one `CAMOU_CONFIG_STRICT` read on every startup (a second only when a
registry/domain/pairing violation is also present, since `ValidateAtStartup`
early-returns without reading the env when it finds none) — one startup lookup,
not worth plumbing to avoid. The
refusal message ("configuration is incoherent and CAMOU_CONFIG_STRICT is set")
is correct for both causes, unchanged. `base/environment.h` is added to the
include block (it was not previously included). The "Warned, not repaired"
comment gains a sentence naming the strict refusal so it does not contradict the
code two screens down.

## What this does NOT change

Non-strict behavior is identical: the same `LOG(WARNING)` in each direction, and
the browser starts. Only under `CAMOU_CONFIG_STRICT` does a half-config now
refuse. No key is repaired or invented — refusing is the enforcement, not
guessing the missing value.

**Scope of the strict refusal (a consequence worth naming).** Branch 1 fires on
`ua:osInfo` absent while *any* of the seven `ua:` metadata keys
(`kUaMetadataKeys`: platform, platformVersion, architecture, bitness, model,
mobile, wow64) carries a readable value — so `{"ua:architecture":"x86"}` alone, or
`{"ua:model":"Pixel 7"}` alone, now refuses under strict where it previously only
warned. That is intended: sp1-navigator-identity-design.md:419-423 extends the
all-or-nothing group to the UA-CH fields, so any UA-CH field set without its
`ua:osInfo` anchor is the half-spoofed identity strict is meant to reject. The
trigger logic is unchanged from the pre-existing warning; only the consequence of
a hit (refuse vs warn) changed, and only under strict.

## RED / GREEN

**Box e2e (`verify_ua_halfconfig_reject.py`, startup stderr + exit code,
modelled on `verify_sp5a.py`):**

| case | config | strict? | RED (before) | GREEN (after) |
|------|--------|---------|--------------|---------------|
| UH-OSINFO-STRICT | `{"ua:osInfo":"Windows…"}` | yes | starts | exits 13, refusal |
| UH-PLATFORM-STRICT | `{"ua:platform":"Windows"}` | yes | starts | exits 13, refusal |
| UH-OSINFO-WARN | `{"ua:osInfo":"Windows…"}` | no | warns, starts | warns, starts (unchanged) |
| UH-PLATFORM-WARN | `{"ua:platform":"Windows"}` | no | warns, starts | warns, starts (unchanged) |
| UH-FULL-COHERENT | `{"ua:osInfo":"Windows…","ua:platform":"Windows"}` | yes | starts | starts (no half-config) |
| UH-TYPE-BLIND-GUARD | `{"ua:mobile":"yes"}` | yes | starts | starts |

UH-OSINFO-STRICT and UH-PLATFORM-STRICT are the two rows that flip. UH-*-WARN are
regression guards: the warnings must be byte-unchanged under non-strict.
UH-TYPE-BLIND-GUARD is a real type-blindness discriminator: a lone `ua:mobile:"yes"`
— a bool key given a string, and nothing else configured — makes the type-aware
`UaMetadataKeyHasValue` return false, so `any_metadata_configured` is false,
branch 1 does not fire, nothing is spoofed, and it starts under strict. This RED
was observed, not reasoned: flipping `UaMetadataKeyHasValue`'s body to a
type-blind `camoucfg::HasKey(...)` and rebuilding turned exactly this row red
(the mutant makes `any_metadata_configured` true, fires branch 1, and refuses
under strict) while the other five stayed green; restoring the type-aware body
returned 6/6. (An earlier draft set `ua:osInfo`+`ua:platform` validly alongside
the wrong-typed key, so neither branch depended on it at all — a false control,
caught in review.)

**Regression:** the two strict verify scripts from earlier this run
(`verify_navplatform_bucket.py`, `verify_webgl_pairing.py`) — their
`ua:osInfo`-only / no-ua configs are unchanged under non-strict; `NB-MISMATCH-
STRICT` still exits 13, now for two reasons (the bucket violation AND the ua:
half-config, since its config sets `ua:osInfo` without `ua:platform`). Re-run
both to confirm, do not assume.

## Verify — RESULT (box, 2026-09-08)

- **Build "Build Succeeded: 2 steps"** — recompiled `browser_main_loop.o` and
  relinked `content_shell` (non-zero; the `base/environment.h` include and the
  new `base::Environment` use compiled).
- **`verify_ua_halfconfig_reject.py`: RED baseline** (current binary, before) —
  UH-OSINFO-STRICT and UH-PLATFORM-STRICT **FAIL** (started under strict); the
  four other rows PASS. **After: GREEN 6/6.** Both strict rows exit 13 with the
  refusal message; UH-OSINFO-WARN and UH-PLATFORM-WARN still warn and start under
  non-strict (byte-unchanged); UH-FULL-COHERENT and UH-TYPE-BLIND-GUARD start
  under strict. UH-TYPE-BLIND-GUARD (a lone `ua:mobile:"yes"`, revised in review
  from a false control) is the real type-blindness discriminator, **proven by
  mutation**: with `UaMetadataKeyHasValue` flipped to a type-blind
  `camoucfg::HasKey(...)` and rebuilt, this row went red (refused under strict)
  while the other five stayed green; the type-aware body returns false for the
  wrong-typed bool key, so no branch fires and it starts — 6/6 restored.
- **Regression:** `verify_sp5a.py` 6/6 (the coherent/incoherent-value/geometry
  startup cases are unaffected — none is a half-config); `verify_navplatform_
  bucket.py` 7/7 (NB-MISMATCH-STRICT still exits 13, now for two reasons — the
  bucket violation AND the ua: half-config, since its config sets `ua:osInfo`
  without `ua:platform`); `verify_webgl_pairing.py` 9/9.
- **Patch re-extraction:** the sp5a section regenerated as `git diff` against
  base blob `ca073899e4` (b-blob now `9ac1d3d021`), spliced programmatically.
  **Strict round-trip OK** — `git apply -p1` (no `--recount`, matching apply.sh's
  `git apply --3way`) of the regenerated patch onto the base blob reproduces the
  tested-GREEN live file byte-for-byte (`cmp` clean). No downstream co-owner
  (only sp0/sp1a/sp5a touch `browser_main_loop.cc`, sp5a terminal), so full
  reconstruction was not needed.

## Patch re-extraction

`browser_main_loop.cc` is owned by three patches (sp0 → sp1a → sp5a in apply.sh
order); sp5a is the terminal owner (no later patch touches the file, grep-proven),
so a single-file round-trip suffices. The sp5a section is regenerated as
`git diff` against its true base — the blob `ca073899e4` (`git cat-file -t`
confirmed a blob), which is the sp1a-applied state — and spliced back
programmatically (never the Edit tool, which mangles blank context-line leading
spaces). Round-trip: applying the regenerated section to the base blob reproduces
the tested-GREEN live file byte-for-byte (`git hash-object`). Full reconstruction
not needed: no downstream co-owner exists to have its context shifted.

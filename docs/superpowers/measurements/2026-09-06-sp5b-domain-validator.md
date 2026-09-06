# SP5b — config-domain validator (single-key numeric ranges)

Date: 2026-09-06. Owner slice: SP5b (single-key domain checks).

## The gap

SP5a's `CoherenceValidator` catches **relational** incoherence — a spoofed value
that contradicts another spoofed value (e.g. a UA claiming Windows next to a
UA-CH platform of macOS). It deliberately does **not** catch a single value that
is simply out of range. Its own comment says so:

> An unrecognised value is a per-key type question rather than a relational one
> — SP5b's to reject, not this entry's to guess about.

So today a mistyped `geolocation:latitude` of `91` sails past every check. The
consumer then silently rejects it and the geo spoof never applies — the author
sees a stock timeout and no diagnostic. The footgun is: **a bad number silently
disables the spoof instead of telling you the number is bad.**

## What a domain entry mirrors (the earning rule)

The point is to catch *at startup* exactly what a downstream Chromium consumer
rejects *later*. So a domain entry is not general plausibility — it mirrors, byte
for byte, a real downstream rejection that would otherwise fail silently. A key
earns a domain entry only when such a rejection exists.

Geolocation is the one that exists so far.
`services/device/public/cpp/geolocation/geoposition.cc`:

```cpp
bool ValidateGeoposition(const mojom::Geoposition& position) {
  return position.latitude >= -90. && position.latitude <= 90. &&
         position.longitude >= -180. && position.longitude <= 180. &&
         position.accuracy >= 0. && !position.timestamp.is_null();
}
```

Domain table (both ends inclusive on all three, matching `>=`/`<=`):

| key | domain |
|---|---|
| `geolocation:latitude`  | `[-90, 90]` |
| `geolocation:longitude` | `[-180, 180]` |
| `geolocation:accuracy`  | `[0, +inf)` |

`timestamp` is synthesized by the fork, never configured — no key, no entry.

"Generalized validator, geo-only table" is the correct first cut: the mechanism
is extensible under the earning rule, not a guess at 82 domains. Adding a bound
for `hardwareConcurrency`/`deviceMemory`/screen without a consumer-side rejection
to mirror would be manufacturing a domain, so those wait for a real rejection.

## Scope decisions (stated, not implicit)

- **Range only this slice.** `HasKey && !GetDouble` (a wrong *type*, e.g.
  `"latitude":"91"`) is already logged for free: `GetDoubleFrom` calls
  `WarnWrongType` and returns `nullopt` when a domain key is read at startup.
  Making strict-mode *refuse* on a type mismatch changes strict semantics for
  every key (type mismatch is warning-only under strict today) — that is a
  separate decision, not shipped inside a geo slice.
- **Non-strict is log-only.** Same report-don't-repair posture as SP5a: the
  spoof still no-ops and looks stock; only `CAMOU_CONFIG_STRICT=1` changes
  behavior (refuse startup). This does not "fix" the footgun for a non-strict
  run — it makes it loud.
- **Not an invariant.** Separate table in a separate file
  (`domain_validator.{h,cc}`); `invariants.json` / `invariants.h` are untouched,
  so `MutationsExistForEveryInvariant` / `RegistryMatchesGeneratedHeader` stay
  green.
- **Integer configs are covered.** The motivating case is `latitude: 91` — a
  JSON *int*, not `91.0`. `GetDoubleFrom` widens an int to double by design
  ("Widening it is what a configuration author expects"), so `ValidateDomains`
  sees `91.0` and reports it. The D8 browser check drives an integer end to end.

## Design

- `std::optional<DomainViolation> CheckDomain(key, value)` — **pure**: table
  lookup + compare, no config access. Exhaustively testable with literals (this
  is why it is factored out — `ScopeFor` is process-global, so anything reading
  config is one-process-per-config).
- `std::vector<DomainViolation> ValidateDomains(scope)` — thin loop: for each
  table entry, `GetDouble` → `CheckDomain`. Absent key or wrong type → skipped
  (not this check's concern; the getter already warned on wrong type).
- Wired into `ValidateAtStartup`: collect relational **and** domain violations,
  return true only when **both** are empty (the pre-existing
  `if (violations.empty()) return true;` would have skipped the domain check on a
  clean relational config — restructured), log each domain violation loudly,
  `return !strict`. No `browser_main_loop.cc` change — it already calls
  `ValidateAtStartup`.

Pure `additions/camoucfg/` change: no Blink patch, no patch round-trip.

## Verify (RED-first)

Unit (`domain_validator_unittest.cc`, `components_unittests`, filter
`DomainValidatorTest.*`) — boundary coverage of the pure `CheckDomain`,
literals only, no env, all six in one process (6/6 PASS):

- latitude: `-90` / `90` ok (inclusive), `-90.0001` / `90.0001` violation, the
  motivating `91` violation.
- longitude: `-180` / `180` ok, `-180.0001` / `180.0001` violation.
- accuracy: `0` ok, large positive ok, `-1e-9` violation (lower bound only).
- a NaN latitude is a violation — locks the `domain_validator.cc` comment's
  claim (NaN fails `>=` on both sides, mirroring `ValidateGeoposition`) and is
  the only place the branch is exercised, since `base::JSONReader` rejects NaN
  literals so a NaN never arrives through `CAMOU_CONFIG`.
- the report names key, value (`"91"`), and a non-empty range reason.
- a key with no registered domain → `nullopt`, whatever the value.

Browser (`scripts/verify_sp5b_domain.py`, mirrors `verify_sp5a.py`) — the
**behavioral RED**. Against the pre-change binary D-STRICT + D-WARN FAIL (the
shell starts with `latitude:91` under strict, no domain line); against the
patched binary all four PASS. Same config, opposite result across the two
binaries (4/4):

- D-STRICT: `CAMOU_CONFIG_STRICT=1` + `{"geolocation:latitude":91}` → **exits
  13** (`chrome::RESULT_CODE_UNSUPPORTED_PARAM`, same code SP5a's refusal uses)
  and stderr carries the domain line. Integer `91` exercises the `GetDouble`
  int path end to end.
- D-WARN: same config, non-strict → shell **starts**, stderr contains
  `camoucfg:` + `geolocation:latitude` + `out of range` + `[-90, 90]`.
- D-TYPE: `CAMOU_CONFIG_STRICT=1` + `{"geolocation:latitude":"91"}` (a
  **string**) → shell **starts** and stderr says `is not a number`, not `out of
  range`. This is the guard for the range-only scope decision above: a type
  mismatch must never become a domain refusal, even under strict.
- D-CLEAN: `{"geolocation:latitude":45,"geolocation:longitude":10}` → no domain
  line, shell starts (regression: a valid config is untouched).

Regression for the `ValidateAtStartup` edit: `run_coherence_tests.sh` 6/6 (the
relational path, each case one process).

A missing symbol failing the build is **not** a RED result — the RED is
D-STRICT flipping start→refuse on the same config across the two binaries.

## Residual

The refusal message on exit is emitted by the caller,
`content/browser/browser_main_loop.cc`, and still reads "configuration is
incoherent" — wording inherited from SP5a's relational-only origin, imprecise
for a domain-only violation. It is left unpatched deliberately: the per-value
`LOG(ERROR)` line printed just above it (`'geolocation:latitude' is '91', out
of range: ...`) carries the precision, and widening the caller's message is a
`content/` patch (round-trip) not worth it for one word. Noted so a future
reader does not mistake the generic line for the whole diagnostic.

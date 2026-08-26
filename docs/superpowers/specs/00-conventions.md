# Shared conventions for all Camoucrome specs

Every SP spec in this directory assumes the decisions below. Do not re-litigate them
inside an individual spec; reference this file instead.

## Project

Camoucrome is an anti-detect fork of Chromium. It is the Chromium counterpart to
Camoufox (`lang315/camoufox`, a Firefox fork). The defining constraint, carried over
from Camoufox, is that **spoofing is implemented in C++ at the Blink/browser level,
never by injecting JavaScript into the page**. A page must not be able to observe
that any value was substituted.

Camoufox is the reference design, not a codebase to copy. Firefox and Chromium share
no code. What ports is the *architecture*: a C++ config layer that patched call sites
consult.

## Decided architecture

**Config component.** `//components/camoucfg/` — one GN target usable from the
browser, renderer, and GPU processes. Blink reaches it through **per-header** entries
in `third_party/blink/renderer/DEPS`, one line per header a Blink file actually
includes — `"+components/camoucfg/mask_config.h",` and
`"+components/camoucfg/blink_scope.h",` — not a directory-wide
`"+components/camoucfg",` grant.

Per-header is what that file already does for other components, and it keeps the grant
to least privilege: a later SP that includes a third camoucfg header has to add a line
and, in doing so, has to think about whether Blink should see it. `gn check` is enabled
for blink core, so a missing entry is a hard build failure rather than a warning.

**Config transport.** Environment variables `CAMOU_CONFIG_1`, `CAMOU_CONFIG_2`, …
concatenated in order, falling back to a single `CAMOU_CONFIG`. Chunking exists
because Windows caps a single environment variable near 32KB. This is deliberately
byte-compatible with Camoufox's transport so that Camoufox's Python fingerprint
generator can eventually drive both forks.

**Config format.** A flat JSON object whose keys are dotted or colon-separated
strings (`"navigator.userAgent"`, `"webGl:parameters"`). Parsed once per process into
a **`base::DictValue`** held by a `base::NoDestructor`, via
`base::JSONReader::ReadDict(raw, base::JSON_PARSE_RFC)`. No third-party JSON library
is vendored.

Three API details that cost SP0 a build cycle each, recorded so no later SP repeats
them. `base::Value::Dict` does **not** exist in this Chromium revision — the type is
`base::DictValue`, and `components/` contains 4520 uses of the latter and none of the
former. `JSONReader::Read` and `ReadDict` take a **required** `int options` argument
with no default. And `base::NoDestructor` static_asserts against a trivially
destructible `T`, so it suits the dictionary but not an empty tag type like
`ConfigScope`, which uses a plain function-local static instead.

**API shape.** Every getter takes a `ConfigScope` as its first argument:

```cpp
camoucfg::GetUint32(ScopeFor(execution_context), "navigator.hardwareConcurrency")
```

In SP0 every scope resolves to the same process-global config. The scope parameter
exists so that a later per-context backing store can be introduced by changing
`ScopeFor` alone, without touching a single call site. Never write a getter that
omits the scope.

**Failure behavior.** Missing config is normal and silent — every surface falls back
to its real value. Malformed JSON logs an error once per process; if
`CAMOU_CONFIG_STRICT=1` is set it aborts startup instead. A type mismatch logs a
warning naming the key and returns `nullopt`. Bad config must never crash a renderer:
a crash is itself a fingerprint.

## Non-negotiable rules for every SP

1. **No JavaScript injection into page-visible scopes.** If a surface can only be
   reached from JS, say so explicitly and treat it as an open problem rather than
   quietly injecting.
2. **Native-looking accessors.** After any change,
   `Object.getOwnPropertyDescriptor(...).get.toString()` must still report
   `[native code]`, and `Object.keys(window)` must be unchanged against a stock build.
3. **Worker parity.** Any surface exposed to both a window and a worker must report
   identical values in both. Camoufox needed `cross-process-storage.patch` for exactly
   this class of bug; a worker disagreeing with its window is a tell.

   Today this holds for free: the config arrives by environment variable and child
   processes inherit the environment, so every context in the process parses the same
   bytes. **That guarantee expires the moment a per-context override channel lands.**
   Whichever SP introduces that channel owns re-establishing worker parity explicitly,
   and must say so in its spec.
4. **Coherence over coverage.** A spoofed value that contradicts another spoofed value
   is worse than not spoofing at all. Where a surface must agree with another, name the
   surface and the invariant.
5. **Fall back to the real value** whenever config is absent, never to a hardcoded
   placeholder.

   One scoped exception is allowed, and only where a spec argues it explicitly: a
   surface may fail *closed* — refusing to answer rather than answering honestly — when
   a partially spoofed profile would be more detectable than a blocked one. Camoufox's
   `blockIfNotDefined` mode for WebGL parameters is the precedent: a GL profile with
   some values spoofed and the rest real is a stronger signal than a context that
   declines to report. Do not generalise this to surfaces where a real value is merely
   inconvenient.

## The config layer does not reach every process

`ScopeFor()` resolves a `blink::ExecutionContext`, so it is available anywhere Blink
runs, and `//components/camoucfg` itself is reachable from the browser and GPU
processes. It is **not** available in services that run outside all three — the device
service, which owns geolocation, is the known case. A surface living there needs its
own path to the config and cannot assume the Blink-shaped API. Say so in the spec
rather than discovering it during implementation.

## Repository layout

```
additions/     whole new files, copied into the Chromium tree verbatim
patches/       diffs against files that already exist in Chromium
settings/      the spoofable-key registry
scripts/       apply / extract / build helpers
docs/superpowers/specs/   these documents
```

This mirrors Camoufox's split, which has held up across ~64 patches: new files are
copied, edits to existing files are diffs. The Chromium checkout is a git repository,
so `git format-patch` produces `patches/` content directly.

## Build environment

Chromium builds on the user's Windows PC inside WSL2 (Ubuntu 24.04), as the non-root
user `lang`, at `~/chromium/src`. depot_tools refuses to run as root. Build config is
`out/Default` with `is_component_build=true` and `symbol_level=0`, so an incremental
rebuild after touching one Blink source file is one to three minutes. The primary
build target for verification is `content_shell`, not `chrome` — it is far smaller and
still exposes the DevTools protocol.

**`content_shell` is not a complete browser, and the gap is load-bearing.** Anything
implemented under `//chrome` is absent from it. `window.chrome` is the known case: every
installer lives in `chrome/renderer/` and `content/shell/BUILD.gn` links none of them, so
`content_shell` has no `window.chrome` at all. A surface in that position needs a `chrome`
build to verify, which is a much slower loop. Check which target owns a surface before
planning its verification, and say so in the spec rather than discovering it mid-task.

## Spec format

Each spec uses these sections, in order:

1. **Goal** — one paragraph. What this SP makes possible that was not possible before.
2. **Depends on** — which SPs must land first, and why.
3. **Surfaces** — a table of every value this SP controls, its config key, its Chromium
   source location (file path, verified against a real checkout where possible), and the
   process it lives in.
4. **Design** — how it works. Scale the length to the difficulty.
5. **Coherence constraints** — which other surfaces this one must agree with, and the
   invariant in each case.
6. **Verification** — numbered, each item independently runnable and falsifiable. State
   the command and the expected output, not "it works".
7. **Open decisions** — anything not yet settled, with the options and a recommendation.
   Never invent a decision the user has not made; list it here instead.
8. **Explicitly out of scope** — what a reader might expect here but will find elsewhere.

Write in prose with tables where they genuinely compress. No code blocks longer than
about fifteen lines; describe the change instead of transcribing it.

## Sub-project map

| SP | Scope | Depends on |
|----|-------|-----------|
| SP0 | Config layer + tracer-bullet surface | — |
| SP6a | Patch management and the key registry | SP0 |
| SP5a | Invariant registry, reader, and load-time validator | SP0 |
| SP1 | Navigator identity and UA / UA-CH coherence | SP0, SP6a, SP5a |
| SP2 | Automation hiding and CDP invisibility | SP0 |
| SP3 | WebGL and canvas fingerprints | SP0 |
| SP4 | Audio, fonts, screen, media devices, battery, WebRTC | SP1, SP3, SP5a |
| SP5b | Invariant catalogue and fingerprint presets | SP1, SP3, SP4 |
| SP6b | Packaging and driver API | SP1–SP5 |
| SP7 | Phone-home removal and build-level hardening | — |

SP5 and SP6 are each split, because both specs argue in their own dependency sections
that half their content is needed far earlier than the other half. SP6's patch
management is needed immediately after SP0's first commit — a branch in the Chromium
tree is at risk from the next `gclient sync` — and its key registry must exist before
SP1 adds twenty keys as string literals. SP5's registry and validator can land as soon
as SP0 does, and SP5 warns that deferring them is precisely the failure mode Camoufox
exhibits. Deferring either to the end is the mistake this split prevents.

SP2 and SP3 are independent of each other and of SP1. SP7 is GN arguments and build
configuration, so it depends on nothing and can start at any time.

## Config key naming

A key uses a **dot** when it mirrors a JavaScript property path exactly
(`navigator.userAgent`, `screen.width`, `window.outerHeight`) and a **colon** when it
names a synthetic namespace with no direct JS counterpart (`webGl:renderer`,
`canvas:seed`, `locale:region`). Camoufox follows this rule in practice without ever
stating it; stating it matters here because SP6a generates C++ constants from the key
registry, which makes a later rename a breaking change.

A value that is *derived* from another gets no key at all. If `screen.orientation` is
always computable from the spoofed dimensions, an independent override key creates the
opportunity for incoherence rather than removing it.

## Ownership decisions

These resolve gaps found while cross-checking the spec set, and override any
contradicting statement left in an individual spec.

**Claimed-OS derivation belongs to SP5a.** The single function answering "what OS are
we claiming" lives in `additions/camoucfg/derive.{h,cc}`, alongside the other derived
values. SP1 populates the inputs it derives from; SP4 and SP7 consume it. No spec
re-derives the OS from a user-agent string locally.

**`window.chrome` belongs to SP2.** Its `runtime`, `loadTimes` and `csi` members are a
page-observable discriminator, and the historically important failure — headless Chrome
lacking the object entirely — is an automation tell rather than a branding one. SP7
owns the build-identity discriminators (Widevine, proprietary codecs); SP2 owns this
one, and the two cross-reference.

**Proprietary codecs and Widevine belong to SP7,** not SP6. SP7 did not exist when SP5
assigned them.

## Out of roadmap: TLS and HTTP/2 fingerprinting

JA3, JA4 and HTTP/2 frame-ordering fingerprints are deliberately **not** an SP, and this
is a decision rather than an oversight. Camoucrome is a real Chromium build using
BoringSSL and Chromium's own network stack, so its TLS and HTTP/2 fingerprints are
already those of Chrome — the same reason this was a strength rather than a gap in
Camoufox. The exposure is not the browser but what sits in front of it: a driver, proxy,
or interception layer that re-terminates TLS will substitute its own fingerprint and
undo this for free. Treat it as a deployment constraint to verify, not a surface to
build. Revisit only if measurement shows the built binary's fingerprint diverging from
stock Chrome of the same milestone.

## Cross-cutting findings

Recorded here because each was discovered while writing one spec but constrains
several. Each is stated in full in its owning spec.

**One producer feeds all three UA channels.** `navigator.userAgentData` and the
`Sec-CH-UA*` request headers both derive from a single `blink::UserAgentMetadata`
struct built by `embedder_support::GetUserAgentMetadata()` in the browser process. SP1
therefore patches two producer functions rather than roughly twenty renderer-side leaf
accessors, and workers inherit the result. This is a place Chromium is *easier* than
Firefox, where Camoufox must patch `Navigator`, `WorkerNavigator`, and `nsHttpHandler`
independently.

**`navigator.webdriver` has two independent sources.** The `AutomationControlled`
runtime feature and a `probe::ApplyAutomationOverride` instrumentation hook both feed
the same getter, so the widely cited `--disable-blink-features=AutomationControlled`
switch closes only one of them. Owned by SP2.

**Assume a `probe::Apply*Override` hook already sits on the surface you are about to
spoof, and check before writing.** This is not confined to `webdriver`. SP0's tracer
surface turned out to have one too: `NavigatorBase::hardwareConcurrency()` already
calls `probe::ApplyHardwareConcurrencyOverride`, the instrumentation behind CDP's
`Emulation.setHardwareConcurrencyOverride`. Chromium exposes a large emulation surface
through DevTools, and much of it lands on exactly the accessors a fingerprint spoof
targets.

Two rules follow. **Never delete a probe call** to resolve a conflict — it silently
breaks DevTools emulation, and removing it is the obvious-looking fix when a
duplicate-definition error appears. And **apply configuration last, after the probe**,
so the configured value wins: the fingerprint is the identity the browser is
presenting, and a driver's emulation override must not be able to contradict it. When
no key is set the lookup is a no-op and the stock behaviour, emulation included,
survives untouched.

The same collision is why SP1 and SP2 are coupled through
`Emulation.setUserAgentOverride`. Expect to find more of these; each one is a
precedence decision, and the answer is the same every time.

**SP1 and SP2 are coupled through CDP.** A pre-existing `platform_override` in
`navigator.cc`, driven by CDP's `Emulation.setUserAgentOverride`, flows through the
same channels SP1 patches. Neutralising it is SP2 work that SP1 depends on.

**Do not spoof the browser version.** SP5's analysis: a claimed version that
contradicts actual feature availability is a contradiction no value substitution
repairs, and feature availability cannot practically be made to match an arbitrary
version. Spoof hardware, locale, and rendering dimensions; let the version be the real
one. This scopes SP1 — it spoofs identity, not version.

**Spoofing an answer the build cannot honour is a contradiction.** Stock Chromium ships
without proprietary codecs, so `canPlayType` for H.264 and AAC answers differently than
real Chrome. SP4 spoofs the API answer; SP7 must make the build actually match via
`proprietary_codecs` and `ffmpeg_branding`. Doing only the first leaves a page able to
ask for the media and watch it fail.

**Two registries, two purposes.** `settings/keys.json` (SP6) is the registry of
spoofable keys and their types, from which both the C++ constants and the client's
validation table are generated. `settings/invariants.json` (SP5) is the registry of
cross-surface invariants, consumed by the browser-process validator, the generator's
self-check, and a generated mutation-test suite. They are different files and neither
subsumes the other.

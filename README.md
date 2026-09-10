# Camoucrome

An anti-detect fork of Chromium. The Chromium counterpart to
[Camoufox](https://github.com/lang315/camoufox), which does the same job for Firefox.

**Status: the SP0–SP7 spoofing arc plus its follow-on residual-closing slices have
landed on `main`** — 26 patches in `patches/` (applied in the order of
`patches/series`, which `scripts/export.sh` regenerates from the checkout's
`camoucrome/main` branch) plus the proprietary-codec GN args in `settings/build-args.gn`.
Apply the whole set to a pristine Chromium checkout with
`scripts/apply.sh <chromium-src>`. The specs in `docs/superpowers/specs/` define the
design; `docs/superpowers/measurements/` records the per-surface measurement each
slice was built from.

Shipped: the config layer and load-time coherence validator (SP0, SP5a); the
browser-process UA / UA-CH producer and Blink-side navigator leaves (SP1a, SP1b);
automation hiding and the humanized cursor (SP2a, SP2b); canvas and WebGL
fingerprints (SP3a, SP3b); the SP4 device-faking arc — screen, fonts, audio, media
devices, timezone/locale, WebRTC IP, voices, geolocation, battery; the proprietary
codec build (SP7 D2); and the follow-on slices that close residual tells the SP4
measurements deferred — window geometry, canvas metric jitter, media-device
getSettings/id coherence, phantom-webcam error coherence, render-thread audio input
masking, and SpeechSynthesis boundary/jitter/generation fixes. SP5b adds a
single-key config-domain validator (a generalized mechanism, populated with the
geolocation range-checks) so an out-of-range value is refused loudly at startup
instead of being dropped silently downstream. SP7 also compiles the field-trial
testing config out of the build (`disable_fieldtrial_testing_config`), so feature
state is the build's compiled defaults rather than the public per-milestone
testing set that an unbranded Chromium applies, and `sp7-phone-home.patch`
stops the component updater, GCM check-in, the startup `ListAccounts`, network
time, the omnibox AI-mode eligibility fetch and the spellcheck dictionary
download — a fresh headless `chrome` now issues zero outbound requests in 75 s
(`scripts/verify_sp7_phonehome.py`). fonts-ii extends the sp4-fonts
allowlist to the `@font-face { src: local() }` path, closing the direct-vs-local()
cross-method inconsistency (a listed font still resolves; an unlisted one no
longer leaks) — the codepoint-fallback and native-host completeness parts remain
open, gated on a real Windows/macOS harness.

**Verification is per-slice and RED-first.** Each slice ships a `scripts/verify_*.py`
that drives a real `content_shell` over CDP, is confirmed to go red against the
pre-change binary, and is re-run after a full revert-and-reapply round-trip
(`gn check` + rebuild) so the committed patches — not just the working tree — are
what passed. Unit coverage backs the config layer and the invariant validator.

**What `content_shell` cannot reach is stated, not hidden.** Some surfaces need a
`chrome` build or a backend this headless host lacks, and so cannot be exercised here
— the `Sec-CH-UA*` header and `userAgentData` channels (SP1a Task 8), `AudioWorklet`
input (its worklet thread never starts headless), and the backend-present
SpeechSynthesis paths. These are documented as residuals in the owning slice's
measurement doc rather than claimed as verified. Coherence across channels is the
project's thesis (see below), and the rows that remain unproven are named where they
live.

Remaining work is the follow-on roadmap's low-value residuals (geo-ii, battery-ii)
and its two high-risk, infrastructure-gated items (fonts-ii, which needs real
Windows/macOS testing; webrtc-ii, browser-process/libwebrtc surgery). See
[`docs/superpowers/plans/2026-09-02-followon-roadmap.md`](docs/superpowers/plans/2026-09-02-followon-roadmap.md).

The change set is generated against Chromium **`507c6ee3e2`, the Chrome stable
tag `153.0.8010.36`** (full SHA and tag in `upstream.env`; `scripts/apply.sh`
refuses any other HEAD). The pin is the current stable tag so the fork reports
a version real users run; it moves to the newest stable tag each milestone.

## The defining constraint

Fingerprint spoofing is implemented in **C++ at the Blink and browser level, never by
injecting JavaScript into the page**. A page must not be able to observe that a value
was substituted — accessors keep reporting `[native code]`, and no property appears on
`window` that is not on a stock build.

This is inherited from Camoufox and is the whole reason the project exists. Anything
achievable by injecting a script into the page can already be done with an existing
tool; the hard, durable part is doing it below the point where page JavaScript can look.

## Relationship to Camoufox

Camoufox is the reference design, not a codebase to copy. Firefox and Chromium share no
code. What ports is the architecture: a C++ config layer that patched call sites
consult, fed by an out-of-process fingerprint generator.

Two things deliberately carry over byte-for-byte so tooling can be shared:

- the `CAMOU_CONFIG_1..N` environment-variable transport, chunked to survive the
  Windows environment-variable size cap
- the flat JSON config format with dotted and colon-separated keys

Two things explicitly do **not** port:

- Camoufox hides Juggler, Firefox's automation protocol. Chromium uses CDP, a different
  model with different leaks. That work is new (SP2).
- Camoufox cross-compiles Windows and macOS binaries from Linux. Chromium cannot — a
  Windows build needs Windows and Visual Studio, a macOS build needs macOS and Xcode
  (SP6).

## Layout

| Path | Contents |
|---|---|
| `docs/superpowers/specs/` | design specs, one per sub-project |
| `docs/superpowers/plans/` | implementation plans, one per slice |
| `docs/superpowers/measurements/` | per-surface measurements each slice was built from |
| `additions/` | whole new files, copied into the Chromium tree verbatim |
| `patches/` | diffs against files that already exist in Chromium |
| `settings/` | the invariant registry (`invariants.json`), the key registry (`keys.json`), captured device presets (`presets/`) and canonical GN args (`build-args.gn`) |
| `scripts/` | apply, and per-slice `verify_*.py` browser verifications |

New files go in `additions/` and edits to existing files go in `patches/`. This split
held up across Camoufox's ~64 patches and keeps rebase conflicts confined to the small
diffs.

`CLAUDE.md` at the repo root is the operational guide for agents working here; it
distills the apply/verify loop, the config-layer API, and the patch-extraction traps.

## Sub-projects

Read [`00-conventions.md`](docs/superpowers/specs/00-conventions.md) first — every spec
assumes the architecture decisions recorded there.

| SP | Scope | Depends on |
|----|-------|-----------|
| SP0 | Config layer plus a tracer-bullet surface | — |
| SP6a | Patch management and the key registry | SP0 |
| SP5a | Invariant registry, reader, load-time validator | SP0 |
| SP1a | Browser-process UA producer: `navigator.userAgent`, `userAgentData`, `Sec-CH-UA*` headers | SP0 |
| SP1b | Blink-side leaf accessors and languages | SP1a, SP6a, SP5a |
| SP2 | Automation hiding and CDP invisibility | SP0 |
| SP3 | WebGL and canvas fingerprints | SP0 |
| SP4 | Audio, fonts, screen, media devices, battery, WebRTC | SP1a, SP1b, SP3, SP5a |
| SP5b | Invariant catalogue and fingerprint presets | SP1a, SP1b, SP3, SP4 |
| SP6b | Packaging and driver API | SP1a–SP5b |
| SP7 | Phone-home removal and build-level hardening | — |

SP5 and SP6 are each split. Both specs argue that half their content is needed far
earlier than the other half: a branch in the Chromium tree is at risk from the next
`gclient sync` the moment SP0's first commit exists, and a key registry that arrives
after twenty keys have been added as string literals has already failed. Deferring
either to the end is the mistake the split prevents.

SP2 and SP3 are independent of each other and of SP1. SP7 is GN arguments and build
configuration, so it depends on nothing and can start at any time.

TLS, JA3 and HTTP/2 fingerprinting are deliberately not a sub-project. Camoucrome is a
real Chromium build on BoringSSL and Chromium's own network stack, so those
fingerprints are already Chrome's. The exposure is a proxy or driver in front that
re-terminates TLS — a deployment constraint to verify, not a surface to build.

## Why coherence matters more than coverage

A spoofed value that contradicts another spoofed value is a stronger detection signal
than not spoofing at all. A user agent claiming Windows alongside a WebGL renderer
string naming a Mac GPU is worse than an honest Linux fingerprint. Camoufox learned
this the expensive way and ended up enforcing coherence in three uncoordinated places
— C++ patches, an all-or-nothing schema, and Python fixup functions. SP5 exists so
Camoucrome does not repeat that.

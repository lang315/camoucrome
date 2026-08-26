# Camoucrome

An anti-detect fork of Chromium. The Chromium counterpart to
[Camoufox](https://github.com/lang315/camoufox), which does the same job for Firefox.

**Status: design phase.** No code yet. The specs in
`docs/superpowers/specs/` define the work.

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
| `additions/` | whole new files, copied into the Chromium tree verbatim |
| `patches/` | diffs against files that already exist in Chromium |
| `settings/` | the registry of spoofable keys and their types |
| `scripts/` | apply, extract, and build helpers |

New files go in `additions/` and edits to existing files go in `patches/`. This split
held up across Camoufox's ~64 patches and keeps rebase conflicts confined to the small
diffs.

## Sub-projects

Read [`00-conventions.md`](docs/superpowers/specs/00-conventions.md) first — every spec
assumes the architecture decisions recorded there.

| SP | Scope | Depends on |
|----|-------|-----------|
| SP0 | Config layer plus a tracer-bullet surface | — |
| SP1 | Navigator identity and UA / UA-CH coherence | SP0 |
| SP2 | Automation hiding and CDP invisibility | SP0 |
| SP3 | WebGL and canvas fingerprints | SP0 |
| SP4 | Audio, fonts, screen, media devices, battery, WebRTC | SP0 |
| SP5 | Coherence engine and real fingerprint presets | SP1, SP3, SP4 |
| SP6 | Build system, packaging, driver API | all |
| SP7 | Phone-home removal and build-level hardening | — |

SP2 and SP3 are independent of each other. SP7 is GN arguments and build
configuration, so it depends on nothing and can start at any time.

## Why coherence matters more than coverage

A spoofed value that contradicts another spoofed value is a stronger detection signal
than not spoofing at all. A user agent claiming Windows alongside a WebGL renderer
string naming a Mac GPU is worse than an honest Linux fingerprint. Camoufox learned
this the expensive way and ended up enforcing coherence in three uncoordinated places
— C++ patches, an all-or-nothing schema, and Python fixup functions. SP5 exists so
Camoucrome does not repeat that.

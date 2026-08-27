# Camoucrome

An anti-detect fork of Chromium. The Chromium counterpart to
[Camoufox](https://github.com/lang315/camoufox), which does the same job for Firefox.

**Status: SP0 landed; SP1a landed, partially verified.** Apply both to a Chromium checkout
with `scripts/apply.sh <chromium-src>`. The specs in `docs/superpowers/specs/` define the
work.

The configuration layer exists and drives `navigator.hardwareConcurrency`. The
browser-process UA producer in `user_agent_utils.cc` is patched so that one site feeds
`navigator.userAgent`, `navigator.userAgentData` and the `Sec-CH-UA*` request headers. What
is *verified* is narrower than what is patched, and the difference matters:

| Channel | Evidence today |
|---|---|
| `navigator.userAgent` | **Verified end to end** in a running browser — spoofed, unconfigured, malformed-config and refused-key cases, all diffed against a pre-patch baseline. |
| `navigator.userAgentData` | **Unit tests only.** `GetUserAgentMetadata()` is called directly, with no browser. |
| `Sec-CH-UA*` headers | **Not yet verified at all.** |
| the three agreeing with each other | **Not yet verified.** |

The gap is not neglect, it is the test binary. `content_shell` reimplements
`GetUserAgentMetadata()` in shell code — hardcoding `platform = "Unknown"` — and never calls
the patched function, and its `ClientHintsControllerDelegate` is `nullptr`, so it emits no
high-entropy `Sec-CH-UA*` headers under any configuration. Closing all three rows needs a
`chrome` build, which is SP1a's Task 8.

Cross-channel coherence is the whole thesis of this sub-project, so it is worth stating
plainly that it is the row still open.

The change set is generated against Chromium revision
`0e8d4a9268118d323f62ca207b40514df39dcaa9`. Rebasing onto a newer revision is SP6a's job.

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

# Derive navigator.platform from the claimed OS (SP5 coherence, derive policy)

**Date:** 2026-09-07
**Slice:** navigator.platform ← ClaimedOs (SP1b patch, coherence derive)
**Owner:** SP1b navigator leaves ↔ SP5 coherence (the coherence obligation SP1 §410/§411 deferred to SP5)

## The leak

`navigator.platform` is a direct config key (SP1b), and when the operator does
not set it, it falls to the host's reduced platform — `GetReducedNavigatorPlatform()`
on the window/worker path, the uname-derived `#if` value on the legacy path.
That host value is computed from the machine the browser runs on, NOT from the
claimed fingerprint. So an operator who spoofs the UA to Windows and leaves
`navigator.platform` unset ships an incoherence by default: a Windows user-agent
beside `navigator.platform === "Linux x86_64"` (the Linux build host). A page
reads both without effort; the pair is a textbook OS tell.

This is not caught by a relational coherence *invariant*: the invariant compares
two configured values, and here `navigator.platform` is absent (its value is the
host default, invisible to the config layer). SP1b chose "unset → plausible real
value" deliberately and named SP5 as the owner of the coherence
(`sp1-navigator-identity-design.md` §410: "The OS token in the UA string must
map to the platform string a real Chrome on that OS reports — `Win32`,
`MacIntel`, `Linux x86_64`"; §411/§416 defer to SP5). This slice is that SP5
work, implemented as a **derive**: `derive.h`'s own philosophy is that a value
which is a function of another should be derived, because an independent default
that can disagree is exactly an incoherence.

## The fix

When `navigator.platform` is not explicitly configured, derive it from
`ClaimedOs(scope)` (which reads `ua:osInfo` first, then `ua:platform`) instead of
returning the host default:

| ClaimedOs | derived navigator.platform | source |
|-----------|----------------------------|--------|
| kWindows           | `"Win32"`         | `GetReducedNavigatorPlatform()` `IS_WIN` literal |
| kMac               | `"MacIntel"`      | its `IS_MAC` literal |
| kLinux / kChromeOs | `"Linux x86_64"`  | its `IS_LINUX \|\| IS_CHROMEOS` literal |
| kAndroid           | `"Linux armv81"`  | its `IS_ANDROID` literal |
| kUnknown           | *(empty → keep host)* | no OS is claimed |

`CanonicalNavigatorPlatformFor(OsFamily)` returns these — the FROZEN per-OS
literals `GetReducedNavigatorPlatform()` (navigator_base.cc) returns under the
reduced User-Agent, which is the live path `NavigatorBase::platform()` serves and
the default in a modern Chrome. UA reduction freezes them independent of the
host's real architecture, so `"Linux x86_64"` is byte-identical to what a real
reduced Chrome reports on ANY Linux, any arch — there is a single correct value
for the Linux family after all, and deriving it keeps the discipline
`CanonicalOsInfoFor`/`CanonicalUaChPlatformFor` hold: byte-identical to what a
real Chrome on that OS emits, never invented. (The non-reduced `navigator_id.cc`
`#else` builds `"Linux <arch>"` from uname, but that branch is compiled out on
every desktop target and is not the path that runs — an earlier draft of this
doc wrongly cited it as the reason to leave the Linux family underived.) Only
kUnknown yields empty: with no OS claimed the caller keeps the host's own value.

## Placement — below the DevTools override, above the host default

`Navigator::platform()` (window) resolves: configured key > DevTools
`Emulation.setUserAgentOverride` platform > `NavigatorBase::platform()`. The
derive goes **inside `NavigatorBase::platform()`**, where the host default is
produced (`GetReducedNavigatorPlatform()`), so it sits below the DevTools
override (an explicit automation choice still wins) and above the host fallback.
`WorkerNavigator` reaches `NavigatorBase::platform()` directly (no window,
no DevTools override), so the worker gets the same derive — coherent with the
window, which is why the hook lives on the shared path.

`NavigatorID::platform()` (the `#if IS_ANDROID`-guarded legacy/non-reduced path)
is NOT changed: on a non-Android build that `#if` block is compiled out, so the
path is dead on the box (camoucrome's only targets are linux/windows/macos), and
adding untestable derive code for a non-target platform is speculative. Its
existing config hook stays. If camoucrome ever targets Android, mirror the
`NavigatorBase` derive there. The verify below proves the live path goes through
`NavigatorBase` (navigator.platform becomes `Win32`), so this omission leaves no
gap on the target surface.

## RED

content_shell, reading `navigator.platform`:

| case | config | before (RED) | after (GREEN) |
|------|--------|--------------|---------------|
| RP-DERIVE | `{"ua:osInfo":"Windows NT 10.0; Win64; x64"}` | `"Linux x86_64"` (host) | `"Win32"` |
| RP-MAC | `{"ua:osInfo":"...Macintosh; Intel Mac OS X 10_15_7..."}` | `"Linux x86_64"` | `"MacIntel"` |
| RP-WORKER | RP-DERIVE config, read inside a Worker | `"Linux x86_64"` | `"Win32"` |
| RP-ANDROID | `{"ua:osInfo":"Linux; Android 10; K"}` | `"Linux x86_64"` (host) | `"Linux armv81"` |
| RP-EXPLICIT (invariant) | `{"navigator.platform":"FreeBSD amd64"}` | `"FreeBSD amd64"` | `"FreeBSD amd64"` (explicit wins; derive must not override) |
| RP-NONE (invariant) | none | host | host (unchanged) |
| RP-LINUX | `{"ua:osInfo":"X11; Linux x86_64"}` | `"Linux x86_64"` | `"Linux x86_64"` (derive coincides with the Linux host; RP-ANDROID is the control that differs) |

RP-DERIVE, RP-MAC and RP-ANDROID are the strong controls: the claimed OS differs
from the Linux host, so a green that reads Win32/MacIntel/`Linux armv81` could not
have come from the host value (CLAUDE.md #4 — the reference is guaranteed to
differ). RP-ANDROID specifically proves the Linux-family derive fires
byte-correctly, which RP-LINUX cannot on a Linux host. RP-EXPLICIT proves the
derive is strictly a fallback. RP-WORKER proves the shared-path placement reaches
workers.

## Verify — RESULT (box, 2026-09-07)

- `DeriveTest.*` 8/8, including `CanonicalNavigatorPlatformMatchesReducedLiterals`
  (Win32/MacIntel/Linux x86_64/Linux armv81; only kUnknown empty).
- `verify_navplatform_derive.py`: **RED baseline** (navigator_base.cc unchanged)
  read `'Linux x86_64'` for RP-DERIVE/RP-MAC/RP-WORKER/RP-ANDROID — the host leak —
  while the invariant cases passed; after the derive, **GREEN 7/7** (windows→`Win32`,
  mac→`MacIntel`, worker→`Win32`, android→`Linux armv81`, explicit→`FreeBSD amd64`,
  none→host, linux→`Linux x86_64`). RP-ANDROID (`Linux armv81` ≠ the host's
  `Linux x86_64`) is the differ-guaranteed control that proves the Linux-family
  derive fires byte-correctly — the change made in review after the first draft
  wrongly left the Linux family underived. The RP-DERIVE window path reading
  `Win32` also proves the live window+worker paths reach `NavigatorBase::platform()`,
  so `NavigatorID::platform()` is genuinely dead on the desktop target —
  reachability confirmed, not assumed.
- **DEPS/checkdeps:** `#include "components/camoucfg/derive.h"` in navigator_base.cc
  is a blink include not previously allow-listed. `buildtools/checkdeps/checkdeps.py`
  on `core/execution_context` was **RED** ("Illegal include ... no rule applying"),
  **GREEN** after adding `+components/camoucfg/derive.h` to
  `third_party/blink/renderer/DEPS`. autoninja does not run checkdeps, so the green
  build alone would not have caught this.
- **DevTools-override ordering:** code-verified, not exercised. The derive sits
  inside `NavigatorBase::platform()`, below `Navigator::platform()`'s
  `GetNavigatorPlatformOverride()` check, so `Emulation.setUserAgentOverride`'s
  platform still wins. RP-EXPLICIT tests the config key, not the CDP override; no
  CDP case was built for it.

## Patch re-extraction

navigator_base.cc is edited by SP0 (camoucfg includes + hardwareConcurrency) and
sp1b (platform); the DEPS allow-list is SP0's. So the change split across two
patches: `sp0-config-layer.patch` gains one DEPS line (`+components/camoucfg/derive.h`);
`sp1b-navigator-leaves.patch`'s navigator_base.cc section gains the derive.h include
hunk and the platform-derive hunk. Each section was regenerated as a git diff
against its true base (SP0's DEPS `a`-blob `d5142fdb5a` = pristine; sp1b's navbase
`a`-blob `c9332e1fdf` = SP0-applied, unchanged since I did not touch SP0's navbase
hunks) so the derive.h `#include` lands in sp1b (the consumer) with correct
post-SP0 context.

**Round-trip:** single-file — applying each regenerated section to its base
reproduced the tested-GREEN live file byte-for-byte (new navbase b-blob
`2c6f62c794…` = `git hash-object` of the built file). The full-stack
reconstruction (worktree-at-pristine + apply.sh) was **not** run: its unique catch
is baseline drift into a downstream co-owner patch, and grep proves no such patch
exists — only sp0 touches `blink/renderer/DEPS`, only sp0+sp1b touch
navigator_base.cc — so no other patch's context can shift. The b-blob change is
intentional and matches the live GREEN truth (per the re-extraction-direction
hazard: verified `git hash-object` of the live file, not a co-tenant's
contamination).

## Residual (documented limit)

All claimed OS families now derive (Windows, Mac, Linux, ChromeOS, Android) from
`GetReducedNavigatorPlatform()`'s frozen literals, so a spoofed UA on any host no
longer leaks the host's navigator.platform. Two cases remain, both correct or
pre-existing:

- **No OS claimed** (`kUnknown`): the derive is a strict fallback, so with no
  `ua:osInfo`/`ua:platform` the host value stands — correct, nothing is spoofed.
- **`ua:platform` set without `ua:osInfo`** (a half-configured profile):
  `ClaimedOs` still resolves so navigator.platform derives, but the UA STRING may
  still show the host OS. This is the pre-existing half-config hazard documented
  at keys.h:416-423, owned by the profile generator (which sets `ua:osInfo` and
  `ua:platform` together), not introduced here.

The complementary relational invariant (kSamePlatformBucket, deferred to SP5a)
would additionally catch an EXPLICIT `navigator.platform` that disagrees with the
claimed UA — the case this derive, being a fallback below the explicit key,
intentionally leaves to the operator.

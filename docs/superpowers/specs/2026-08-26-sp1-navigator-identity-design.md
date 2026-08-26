# SP1 — Navigator identity and UA / UA-CH coherence

Status: draft, not yet approved
Assumes: [00-conventions.md](00-conventions.md)

## 1. Goal

SP1 makes the browser able to claim a different *device* identity than the one it is
running on — a different operating system, architecture, and locale — consistently
across every channel that reveals it. After SP1, a config that says "Windows 11 x64,
en-US" produces a `navigator.userAgent` string, a `navigator.userAgentData` object, a
set of `Sec-CH-UA*` request headers, an `Accept-Language` header, and a dozen
`navigator.*` scalars that all agree with each other and with what a real Chrome of
*this build's own version* running on Windows 11 emits.

The browser version is deliberately not part of what SP1 spoofs. Conventions settles
this: a claimed version that contradicts the feature set actually compiled into the
binary is a contradiction no value substitution repairs, and feature availability cannot
be made to track an arbitrary version number. Every UA channel therefore reports the
build's real Chromium milestone, and SP1's work is to change the OS, hardware, and
locale dimensions around it. That is a narrowing of what an earlier draft of this spec
assumed, and it removes a class of failure rather than adding one.

This is the single highest-value surface in the project: it is what nearly every
detector reads first, and it is also where Chromium differs most sharply from Firefox,
so almost none of Camoufox's implementation experience transfers.

## 2. Depends on

**SP0** — every value here is read through `camoucfg::Get*(ScopeFor(...), key)`. SP1 is
also the first real consumer of the browser-process config path. SP0 only smoke-tests
that path with a startup log line; SP1 depends on it working for real, because the UA
producer lives in the browser process. If SP0's browser-process probe fails, SP1 is
blocked until it is fixed.

**SP6a** — the key registry. SP1 introduces roughly twenty keys at once, which is the
point past which string literals at call sites stop being acceptable. `settings/keys.json`
must exist first, so SP1's keys are generated constants from the start rather than being
retrofitted afterwards.

**SP5a** — the invariant registry and the derivation helpers in
`additions/camoucfg/derive.{h,cc}`. SP1 does not itself answer the question "what OS are
we claiming"; see section 4.

SP1 does not depend on SP3 or SP4. It is coupled to **SP2** in one direction: Chromium's
existing CDP emulation override flows through the same channels SP1 patches, and
neutralising it is SP2 work. See open decision D1.

## 3. Surfaces

Paths were verified against the real checkout at `~/chromium/src` unless marked
*(unverified)*. Line numbers are from that checkout and will drift.

| Value | Config key | Location | Process |
|---|---|---|---|
| `userAgent` | `navigator.userAgent` | `components/embedder_support/user_agent_utils.cc` (producer) | browser |
| UA-CH brands, platform, platformVersion, architecture, bitness, model, fullVersionList, wow64 | `navigator.uaData:*` | `components/embedder_support/user_agent_utils.cc` → `blink::UserAgentMetadata` (`third_party/blink/public/common/user_agent/user_agent_metadata.h:46`) | browser |
| `navigator.userAgentData` | *(derived)* | `third_party/blink/renderer/core/frame/navigator_ua_data.cc`, `navigator_ua.cc` | renderer |
| `Sec-CH-UA*` request headers | *(derived)* | `services/network/public/cpp/client_hints.cc` | network service |
| `appCodeName` | `navigator.appCodeName` | `core/frame/navigator_id.cc:47` | renderer |
| `appName` | `navigator.appName` | `core/frame/navigator_id.cc:51` | renderer |
| `appVersion` | `navigator.appVersion` | `core/frame/navigator_id.cc:55` | renderer |
| `platform` | `navigator.platform` | `core/frame/navigator_id.cc:61`, overridden in `core/frame/navigator.cc:58-66` | renderer |
| `product` | `navigator.product` | `core/frame/navigator_id.cc:86` | renderer |
| `productSub` | `navigator.productSub` | `core/frame/navigator.cc:42` | renderer |
| `vendor` | `navigator.vendor` | `core/frame/navigator.cc:46` | renderer |
| `vendorSub` | `navigator.vendorSub` | `core/frame/navigator.cc:54` | renderer |
| `language`, `languages` | `navigator.language`, `navigator.languages` | `core/frame/navigator_language.cc` | renderer |
| `Accept-Language` header | `headers.Accept-Language` | `core/frame/navigator.cc:109` (`GetAcceptLanguages`), `services/network/network_context.cc`, `content/browser/renderer_host/navigation_request.cc` | renderer + network + browser |
| `hardwareConcurrency` | `navigator.hardwareConcurrency` | `core/frame/navigator_concurrent_hardware.cc` | renderer |
| `deviceMemory` | `navigator.deviceMemory` | `core/frame/navigator_device_memory.cc` (+ `.idl`) | renderer |
| `maxTouchPoints` | `navigator.maxTouchPoints` | declared in `core/events/navigator_events.idl`; implementation *(unverified)* | renderer |
| `doNotTrack` | `navigator.doNotTrack` | `core/frame/navigator.cc` *(unverified line)* | renderer |
| `cookieEnabled` | `navigator.cookieEnabled` | `core/frame/navigator.cc` *(unverified line)* | renderer |
| `onLine` | `navigator.onLine` | `NavigatorOnLine` *(unverified path)* | renderer |
| `pdfViewerEnabled` | `navigator.pdfViewerEnabled` | `core/frame/navigator.cc` *(unverified line)* | renderer |

`hardwareConcurrency` is listed for completeness; SP0 already implements it as its
tracer bullet. SP1 inherits it unchanged and only adds it to the coherence checks.

Two structural facts discovered while probing, both of which shape the design:

**`NavigatorBase` exists.** `navigator.cc:63` and `:66` call `NavigatorBase::platform()`.
The class is not at `core/frame/navigator_base.{h,cc}` — those paths do not exist in this
checkout — so its real location is *(unverified)*, most likely under
`core/execution_context/`. It matters because `Navigator` (window) and `WorkerNavigator`
both derive from it, which makes it the natural single place to satisfy the worker-parity
rule.

**A platform override already exists.** `Navigator::platform()` at `navigator.cc:58-66`
consults a `platform_override` and falls back to `NavigatorBase::platform()` only when
that override is empty. This is Chromium's existing device-emulation plumbing, driven by
the CDP `Emulation.setUserAgentOverride` command. Its existence is both an opportunity
and a hazard; see Open decisions.

## 4. Design

### Patch high, not wide

The naive approach patches every leaf accessor in Blink — twenty small edits, each
reading config independently. That approach produces incoherence by construction,
because nothing forces the UA string patch and the UA-CH patch to agree, and it
duplicates work for workers.

Chromium's own architecture offers a much better chokepoint. Both
`navigator.userAgentData` and the `Sec-CH-UA*` headers are populated from a single
`blink::UserAgentMetadata` struct, and that struct plus the UA string are produced in
the browser process by `embedder_support::GetUserAgent()` and
`embedder_support::GetUserAgentMetadata()` in `user_agent_utils.cc`. The browser then
ships both to the renderer (where they become `navigator.userAgent` and
`navigator.userAgentData`) and to the network service (where the metadata becomes
`Sec-CH-UA*` headers).

So the primary design is: **patch the two producer functions in `user_agent_utils.cc` to
consult config, and let Chromium's existing distribution machinery carry the spoofed
values to all three channels.** One patch site, three coherent channels, and workers
inherit it because worker global scopes receive the same metadata through
`core/workers/global_scope_creation_params.cc`.

This is a real architectural divergence from Camoufox. Camoufox's
`navigator-spoofing.patch` must touch `Navigator` and `WorkerNavigator` separately, and
`network-patches.patch` must separately rewrite the on-the-wire `User-Agent` header in
`nsHttpHandler`, because Firefox has no equivalent single producer. Chromium's client
hints design accidentally gives us a better seam. We should use it.

### What the producer patch cannot cover

A second, smaller group of values is not derived from the UA string or metadata and
must be patched in Blink individually:

- The near-constants: `appCodeName`, `appName`, `product`, `productSub`, `vendor`,
  `vendorSub`. In real Chrome these are fixed strings (`Mozilla`, `Netscape`, `Gecko`,
  `20030107`, `Google Inc.`, empty). They must default to those exact values and only
  change if the config is impersonating something that is not Chrome. Spoofing them to
  anything else while claiming to be Chrome is an instant tell, so config for these
  should be treated as an expert override, not a normal knob.
- `appVersion` and `platform`, which are UA-adjacent but computed separately in
  `navigator_id.cc`.
- The device scalars: `deviceMemory`, `maxTouchPoints`, and (from SP0)
  `hardwareConcurrency`.
- The state flags: `doNotTrack`, `cookieEnabled`, `onLine`, `pdfViewerEnabled`.
- Languages, which have their own two-channel problem described below.

For each of these, the patch reads config and falls back to the real computed value
when the key is absent, per conventions rule 5.

### SP1 populates the OS inputs; it does not derive the OS

Several later sub-projects need to know which operating system the current config is
claiming. SP4 resolves system fonts, CSS system-font keywords and codec answers from
it; SP7 reasons about platform-specific update machinery from it. That question has
exactly one answer function, and conventions places it in SP5a's
`additions/camoucfg/derive.{h,cc}` alongside the other derived values.

SP1's relationship to it runs one way. SP1 populates the inputs the derivation reads —
the UA-CH `platform` field, `navigator.platform`, and the OS token inside the UA string
— and then consumes the derived answer like every other sub-project. **SP1 must not
parse a user-agent string locally to work out the OS.** Two independent parsers of the
same string is exactly how surfaces drift apart, and avoiding it is why Camoufox keeps
`utils.py::determine_ua_os` as the only such function in its codebase.

### Worker parity

Rule 3 requires a worker to report the same values as its window. The design satisfies
this in two different ways depending on the value.

For UA and UA-CH, parity is automatic: the browser produces one metadata struct and
both the document and the worker global scope receive it.

For the Blink-side scalars, parity requires patching at `NavigatorBase` rather than at
`Navigator`, since `WorkerNavigator` shares that base. Where a value is implemented on
`Navigator` only (`productSub`, `vendor`, `vendorSub` at `navigator.cc:42-54`), check
whether `WorkerNavigator` exposes it at all; several of these are window-only in the
IDL, in which case there is no parity obligation. The implementation must confirm this
per value rather than assume it, and the verification step below tests it empirically
rather than by reading the IDL.

Camoufox needed a dedicated `cross-process-storage.patch` to keep values identical
between content and worker processes. Chromium's worker global scopes are created from
browser-supplied parameters, so the equivalent problem largely does not arise — but
that is a claim the verification step must actually check, not assume.

### Languages and Accept-Language

`navigator.languages` and the `Accept-Language` request header are separate channels
that a detector can trivially cross-check. `Navigator::GetAcceptLanguages()` at
`navigator.cc:109` feeds the renderer side; `services/network/network_context.cc` and
`content/browser/renderer_host/navigation_request.cc` feed the wire side.

Both must be derived from one config value. The config exposes `navigator.languages` as
the source of truth (an ordered array), and `headers.Accept-Language` as an optional
explicit override for cases where the q-value formatting must be controlled precisely.
When only `navigator.languages` is set, the `Accept-Language` header is generated from
it using Chromium's normal formatting, so the two cannot disagree.

**The boundary with SP4's `locale:*` keys.** `navigator.language` and
`navigator.languages` are the page-visible values and keep their `navigator.` names,
per the key-naming rule in conventions: they mirror a JavaScript property path exactly.
SP4's `locale:*` keys are a **separate, non-overlapping namespace** covering what ICU
consumes — collation order, date and number formatting, the default calendar — none of
which is readable as a `navigator` property. Neither namespace is an alias for the
other. The mapping between them is stated once, in the key registry: an unset `locale:*`
value defaults from `navigator.languages[0]`, and setting both to values that disagree
is an invariant violation for SP5a's validator to reject, not something SP1 silently
reconciles.

One deliberate exception to the naming rule: `headers.Accept-Language` keeps its dot
even though `headers` is not a JavaScript property path. Camoufox uses that exact
spelling, and conventions commits to a transport its generator can drive unchanged.
Renaming it would buy internal consistency at the cost of the compatibility the
transport exists for.

### Reduced User-Agent

Modern Chromium ships a *reduced* User-Agent string by default: the minor version is
frozen and platform detail is coarsened. Whether a build emits the reduced or the full
form depends on its version and feature state.

Because SP1 no longer spoofs the version, most of this resolves itself. The build emits
whichever form its own milestone emits, and that is by definition the correct form for
the version being reported — the mismatch an earlier draft worried about cannot arise
if the version is never substituted.

What remains is narrower and still real: the OS token inside the string has to be
substituted, and the reduced form coarsens platform detail in a way the full form does
not, so the substitution differs between the two. The producer patch must therefore read
which form the build is emitting and rewrite the OS token within it, rather than
assembling a UA string from scratch. Assembling from scratch is the thing that would let
the two forms get mixed.

## 5. Coherence constraints

| This surface | Must agree with | Invariant |
|---|---|---|
| every UA channel | the binary itself | The Chromium version reported in the UA string, in `userAgentData.brands`, in `fullVersionList`, and in the `Sec-CH-UA` header must all equal the version this build was compiled from. Config cannot override it. This is SP1's primary invariant; verification item 1 asserts it. |
| `navigator.userAgent` | `navigator.userAgentData.brands`, `fullVersionList` | The major version in the UA string must equal the Chromium brand's version in the brands list. |
| `navigator.userAgent` | `Sec-CH-UA` header | Same brand list, same versions, same order and GREASE placement. |
| `navigator.userAgent` | `navigator.platform`, `navigator.appVersion` | The OS token in the UA string must map to the platform string a real Chrome on that OS reports (`Win32`, `MacIntel`, `Linux x86_64`). |
| `navigator.userAgentData.platform` | `navigator.platform` | Both must name the same OS family. |
| `navigator.userAgentData.architecture`, `bitness` | `navigator.userAgent` | `x86`/`64` must match the architecture token in the UA string. |
| `navigator.languages` | `Accept-Language` header | Same list, same order. |
| `navigator.languages[0]` | `navigator.language` | Must be identical. |
| `navigator.maxTouchPoints` | claimed OS and form factor | A desktop Windows profile reporting a nonzero touch-point count is unusual; a mobile profile reporting zero is impossible. |
| `navigator.platform` | SP3's WebGL renderer string, SP4's font list | Deferred to SP5, but named here so SP5 has the list. |
| `navigator.hardwareConcurrency`, `deviceMemory` | each other | Real devices cluster; 2 cores with 64GB is not a real machine. Enforcement belongs to SP5. |

Camoufox encodes the first group as an all-or-nothing `$__UA` group in
`camoucfg.jvv`, binding `userAgent` + `appVersion` + `platform` + `oscpu` so a partial
config is rejected rather than producing a half-spoofed identity. Camoucrome should
adopt the same all-or-nothing rule, extended to cover the UA-CH fields, in the
`settings/` key registry. Validating it is SP5's job; declaring it is SP1's.

## 6. Verification

Each item is runnable against a `content_shell` build with `--remote-debugging-port`.
`CFG` below stands for a `CAMOU_CONFIG` value describing **Windows 11 x64, en-US**,
while the host is Linux x86_64. `CFG` carries no version field of any kind: the reported
Chromium version is always this build's own.

1. **The version is never spoofed; everything else in the UA string is.** Launch with
   `CFG` and evaluate `navigator.userAgent`: expect a Windows-shaped OS token and a
   version segment byte-identical to stock. Then extract the Chromium version from four
   places — the UA string, `navigator.userAgentData.brands`, the `fullVersionList`
   high-entropy hint, and the `Sec-CH-UA` request header — and confirm all four equal the
   version this binary was built from, read independently from `chrome://version` or
   `chrome/VERSION`. Then relaunch with a `CFG` that attempts to set a version: the
   attempt must be rejected or ignored, and all four channels must still report the build
   version. Finally launch with no config at all and expect the stock Linux UA,
   byte-identical. This item is what stops the spoofed identity from contradicting the
   binary underneath it, and it is the one to run first after any change to the producer.
2. **UA-CH object.** Evaluate `navigator.userAgentData.platform`. Expect `"Windows"`.
   Evaluate `navigator.userAgentData.brands` and confirm the Chromium entry's version
   equals the major version in the UA string from item 1.
3. **High-entropy hints.** Await
   `navigator.userAgentData.getHighEntropyValues(["architecture","bitness","platformVersion","model","fullVersionList"])`.
   Expect `architecture: "x86"`, `bitness: "64"`, a Windows-shaped `platformVersion`, and
   a `fullVersionList` whose Chromium version matches items 1 and 2.
4. **Request headers.** Point the shell at a local listener that echoes request headers.
   Expect `Sec-CH-UA`, `Sec-CH-UA-Platform: "Windows"`, `Sec-CH-UA-Mobile: ?0`, and — after
   the listener advertises `Accept-CH` — `Sec-CH-UA-Arch: "x86"` and
   `Sec-CH-UA-Bitness: "64"`. Every value must match items 1–3. This is the item that
   fails if the producer patch is bypassed anywhere.
5. **Accept-Language.** With `navigator.languages` set to `["en-US","en"]`, the same
   listener must observe `Accept-Language: en-US,en;q=0.9`, and
   `navigator.languages` must evaluate to `["en-US","en"]` with
   `navigator.language === "en-US"`.
6. **Worker parity.** In a dedicated worker, evaluate `navigator.userAgent`,
   `navigator.platform`, `navigator.hardwareConcurrency`, `navigator.deviceMemory`, and
   `navigator.languages`, and compare each against the window value. All must be equal.
   Repeat in a shared worker and a service worker. Any disagreement is a blocking defect.
7. **Native accessors.** For every patched property,
   `Object.getOwnPropertyDescriptor(Navigator.prototype, prop).get.toString()` must
   contain `[native code]`. `Object.keys(window)` and `Object.keys(navigator)` must be
   byte-identical to a stock `content_shell` of the same revision, captured before the
   patch.
8. **No-config regression.** With no `CAMOU_CONFIG` set, every value in the surfaces
   table must equal what stock `content_shell` reports. Diff the full set
   programmatically rather than spot-checking.
9. **Chrome constants.** With a config that sets only `navigator.userAgent`, confirm
   `productSub === "20030107"`, `vendor === "Google Inc."`, `appCodeName === "Mozilla"`,
   `appName === "Netscape"`, `product === "Gecko"`. These must not drift when the UA
   changes.
10. **Emulation interaction.** Issue a CDP `Emulation.setUserAgentOverride` and confirm
    the resulting state is still self-consistent across items 1–4, or that the command is
    neutralized. See Open decisions.

## 7. Open decisions

**D1 — What to do about the existing CDP emulation override.** `Navigator::platform()`
already honours a `platform_override`, and `Emulation.setUserAgentOverride` sets a UA
plus metadata override that flows through the same channels we intend to patch. Three
options: (a) ignore it, and accept that a page which can reach DevTools emulation could
observe a second, different identity; (b) neutralize it, making the emulation override a
no-op when config is present, which is simple but changes CDP behaviour that the
automation driver may itself rely on; (c) reuse it as the delivery mechanism instead of
patching the producer, which is less code but means our spoofing rides the exact
automation channel SP2 exists to hide. Recommendation: (b), neutralize, and revisit in
SP2 once the CDP hiding design is settled — but this genuinely couples SP1 and SP2 and
the user should decide.

**D2 — Explicit UA-CH keys versus deriving them from the UA string.** The UA-CH fields
are structured (brands array, platformVersion, architecture, bitness, model,
fullVersionList, wow64) while the UA string is flat text. Either the config carries all
of them explicitly, or the producer parses the UA string to derive them.
Recommendation: explicit keys. Parsing is lossy, and derivation is precisely where
incoherence appears — the parser's idea of "Windows 11" and the real Chrome's differ in
the platformVersion encoding. The cost is roughly eight more config keys, which SP5's
preset generator fills from real captured fingerprints rather than a human typing them.

The version-bearing fields are excluded from this decision entirely. The brand versions
and `fullVersionList` are not config keys under either option, because the version is
not spoofed; the producer fills them from the build's own version regardless of what
config says.

**D3 — Whether the Chrome constants are configurable at all.** `productSub`, `vendor`,
`appCodeName`, `appName`, `product` are fixed in real Chrome. Exposing them as config
keys invites a user to set them to something that instantly reveals the fork.
Recommendation: implement them as config-readable but leave them out of the documented
key registry, and have SP5's validator reject any value that disagrees with the claimed
brand. Alternative: hardcode them and do not read config at all.

**D4 — `NavigatorBase`'s real location.** Confirmed to exist but not located. The
implementation plan's first task must find it, because whether the Blink-side scalars can
be patched once or must be patched twice depends on it.

**D5 — Which values belong to SP1 versus SP4.** `onLine`, `cookieEnabled`, and
`pdfViewerEnabled` are navigator properties but are not identity in any real sense. They
could reasonably move to SP4's long tail. Recommendation: keep them here, because they
live in the same files and moving them means touching `navigator.cc` twice.

## 8. Explicitly out of scope

`navigator.webdriver` and everything about hiding automation belongs to **SP2**, even
though `webdriver` is a navigator property living in `navigator.cc:100`. It is
deliberately excluded so that SP1 and SP2 do not both edit that file's identity logic.

`navigator.plugins` and `navigator.mimeTypes` are not in SP1. WebGL vendor and renderer
strings are **SP3**. Screen geometry, fonts, media devices, and battery are **SP4**.

Cross-surface validation — deciding whether a given combination of UA, platform, WebGL
renderer, and font list describes a machine that could actually exist — is **SP5**. SP1
declares the invariants in section 5 but does not enforce them. A config that sets a
Windows UA and a macOS platform will produce exactly that incoherent result in SP1, by
design; catching it is SP5's job. Concretely: SP5a supplies the validator and the
derivation helpers SP1 depends on, and SP5b supplies the catalogue of invariants that
validator enforces.

Generating realistic values is also **SP5b**. SP1 consumes whatever config it is given.

# SP5 — Coherence engine and fingerprint presets

Assumes everything in [00-conventions.md](00-conventions.md).

This spec covers two phases that land at very different times, and the sub-project map
names them separately. **SP5a** — the invariant registry file, its C++ reader, the
browser-process validator, the derivation helpers and the generated test harness —
depends only on SP0 and should land immediately after it. **SP5b** — the invariant
catalogue itself and the preset path — depends on SP1, SP3 and SP4, because an
invariant over a key that nothing reads is untestable. Each section below is marked
with the phase it belongs to.

## 1. Goal

SP1 through SP4 each give an operator independent control over a set of surfaces. Used
naively that produces a browser capable of asserting a hundred individually plausible
facts that, taken together, describe a machine that has never existed — a macOS GPU
under a Windows user agent, a window taller than the screen containing it, a worker
whose canvas seed disagrees with its own page. Every one of those is a stronger
detection signal than not spoofing at all, because real browsers are noisy about
*values* and perfectly consistent about *relationships*.

SP5 makes the set of assertions internally consistent. It does this with one
machine-readable registry of invariants that is the single source of truth, a
browser-process validator that enforces the registry before any renderer starts, and a
preset path that replays identity dimensions observed on real devices instead of
synthesising them. After SP5, a config that would produce an impossible machine is
rejected or repaired at launch rather than discovered by a detector.

## 2. Depends on

**SP5a depends on SP0 alone.** The registry file, its C++ reader, the validator, the
derivation helpers in `derive.{h,cc}` and the generated test harness need nothing but a
parsed config to exist. They should land immediately after SP0 and before SP1, because
SP1 is the first sub-project that both adds many keys and needs the claimed-OS helper
that lives here.

**SP5b depends on SP1, SP3 and SP4.** An invariant over a key that nothing reads is
untestable, so the catalogue fills in as those sub-projects land. The preset path
additionally depends on SP1 for user-agent and client-hint plumbing, since a Chrome
preset is mostly an identity claim and identity is SP1's surface.

Splitting the two is not bookkeeping. Treating the whole of SP5 as a late phase imposes
a process cost on the earlier sub-projects that is easy to leave implicit and should
not be: **an SP is not complete until its invariants are in the registry with a passing
mutation test.** That discipline is only available if the registry already exists when
SP1 starts. If it slips, SP5 degenerates into a late audit of work already shipped,
which is precisely the failure mode Camoufox exhibits today.

## 3. What this sub-project owns

SP5 controls no page-visible value directly. It owns the relationships between values,
plus the machinery that enforces them.

| Phase | Artifact | Location | Process |
|---|---|---|---|
| SP5a | Invariant registry file (schema and mechanism) | `settings/invariants.json` | data, consumed by C++ and by the generator |
| SP5a | Registry reader and validator | `additions/camoucfg/coherence_validator.{h,cc}` | browser |
| SP5a | Validator invocation at startup | patch to Chromium browser startup, after config parse, before any renderer launch | browser |
| SP5a | Derived-value helpers, including the claimed-OS function | `additions/camoucfg/derive.{h,cc}` | shared |
| SP5a | Property and mutation test harness | `additions/camoucfg/coherence_validator_unittest.cc` | test |
| SP5b | The invariant catalogue itself (§4.3 contents) | `settings/invariants.json` | data |
| SP5b | Preset store | `settings/presets/chromium-<milestone>.json` | data |
| SP5b | Preset loader and expander | `additions/camoucfg/preset_loader.{h,cc}` | browser |

The registry *file and its mechanism* are SP5a; the *entries in it* are SP5b, filled in
by SP1, SP3 and SP4 as each lands. That division is what lets the discipline in §2 —
no SP is done until its invariants have a passing mutation test — apply from SP1
onward.

The exact Chromium startup file to patch is left to implementation; the requirement is
that validation runs after the config is parsed and before the first renderer process
is spawned, so that a rejection can still prevent launch.

## 4. Design

### 4.1 Where coherence belongs (SP5a)

Camoufox enforces coherence in three uncoordinated places: C++ patches that derive one
value from another at read time, all-or-nothing `$group` declarations in the
`camoucfg.jvv` schema, and a large family of fixup functions in the Python generator.
Nothing reconciles the three. The registry drift already found in that codebase is the
predictable result — `cssMedia:*`, `screen:orientation*` and `mediaCapabilities:*` are
read by C++ but declared nowhere in `settings/`, and the `voiceURI` versus `voiceUri`
casing split means a config that satisfies the schema is rejected by the C++ reader.
Those are not sloppiness; they are what happens when the same rule has three homes.

Camoucrome uses **one registry, three consumers**. `settings/invariants.json` states
each invariant once. It is read by the browser-process validator at config-load time,
by the external fingerprint generator as a post-generation self-check, and by the test
suite, which generates configs and asserts the registry cannot be violated. Adding an
invariant is a one-file change that all three pick up.

Enforcement happens at **config-load time in the browser process**, not at read time in
the renderer. Read-time enforcement was considered and rejected for three reasons: it
requires every getter to know about every related key, which recreates in C++ exactly
the fragmentation being fixed; it makes each renderer repeat work the browser could do
once; and a renderer cannot cheaply see the whole config, so it cannot check a global
invariant at all. Load time is also the only point at which the fork can still refuse
to start, which the conventions' fail-closed model requires.

Two mechanisms sit alongside load-time validation and are deliberately not folded into
it:

**Derivation (SP5a).** Some values are strictly a function of another spoofed value and
have no independent config key — `screen.orientation.type` and its angle follow from
whether the spoofed screen is wider than it is tall; the CSS `system-ui` generic family
and the CSS2 system-font keywords follow from the spoofed platform. These are computed
at read time from a shared helper in `derive.{h,cc}`. That is not fragmentation,
because the value has exactly one definition. The conventions state the general rule
under *Config key naming*: a derived value gets no key at all, because an independent
override key creates the opportunity for incoherence rather than removing it.

`derive.{h,cc}` also holds **the single function that answers "what operating system
are we claiming"**, and the conventions assign that ownership to SP5a explicitly. SP1
populates the inputs it derives from; SP4 and SP7 consume it. No sub-project re-derives
the target OS from a user-agent string locally, because two derivations of the same
fact are two chances to disagree — and every OS-dependent surface in §4.3 hangs off
this one answer.

**Propagation.** Seeds and identity values that must be byte-identical in the window,
in every worker, and in the GPU process are not a validation problem but a transport
problem. SP0's environment-variable transport already solves it for the process-global
case, since every child process inherits the environment. It is unsolved for the
per-context case and is listed as an open decision below. Camoufox needed a dedicated
`cross-process-storage.patch` precisely because Firefox had no equivalent inheritance.

### 4.2 Registry format and repair policy (SP5a)

Each entry names the keys it constrains, the relation, and what to do on violation.
Three policies:

| Policy | Behavior |
|---|---|
| `reject` | Refuse to launch. Reserved for violations no repair can make plausible. |
| `repair` | Fix deterministically, log the key, the old value and the new one. |
| `derive` | The dependent key has no independent value; it is always computed. |

The default for a repairable violation is `repair` with a loud log; under
`CAMOU_CONFIG_STRICT=1` every violation becomes `reject`. This matches SP0's failure
model and preserves its central property: the operator is never left believing a
fingerprint is active when it silently is not.

A repair must be deterministic and idempotent. Running the validator on its own output
must produce no further changes, and the test suite asserts this.

### 4.3 The invariant catalogue (SP5b)

What follows is the initial catalogue. It is not exhaustive, and it is SP5b work: each
entry can only be enforced once the sub-project owning its keys has landed, so the
catalogue fills in alongside SP1, SP3 and SP4 rather than being written up front.

**Geometry.** `screen.availWidth ≤ screen.width` and `screen.availHeight ≤
screen.height`, with the availHeight comparison strict on desktop platforms — CreepJS
raises a `noTaskbar` flag when a claimed desktop reports no reserved screen space, and
Camoufox carries `fix_screen_no_taskbar` for exactly this. Window geometry nests:
`inner ≤ outer ≤ avail ≤ screen` on both axes, and `0 ≤ screenX ≤ screen.width −
outerWidth` likewise for Y. `document.body.clientWidth ≤ window.innerWidth`.
`colorDepth` equals `pixelDepth`, and both are 24 — real Chrome reports nothing else,
so any other value is a tell rather than a variation.

**Device pixel ratio.** Screen and window dimensions are expressed in CSS pixels at a
particular device pixel ratio. A preset captured on a display running at 1.25 and
replayed with `devicePixelRatio` of 1 describes a machine that does not exist. Camoufox
resolves this by resampling to a known real DPR-1 display; Camoucrome needs the
equivalent, and the invariant is that the geometry cluster and the reported DPR must
originate from the same capture.

**Operating system.** The target OS is derived once, by the single helper in
`derive.{h,cc}` described in §4.1, and is then the sole authority for every
OS-dependent surface: `navigator.platform`, the UA-CH
`platform` and `platformVersion`, `navigator.userAgentData.platform`, the
`Sec-CH-UA-Platform` request header, the font list, the voice list, plausibility of the
WebGL vendor and renderer pair, CSS system-font resolution and the `system-ui` family,
`AudioContext.sampleRate`, and `navigator.maxTouchPoints`, which is 0 on desktop.

One fixed-value rule deserves its own line because getting it wrong is instantly fatal
and the intuitive answer is the wrong one: **Chrome on 64-bit Windows reports
`navigator.platform` as `Win32`**, not `Win64`. Architecture is expressed through
`Sec-CH-UA-Arch` and `Sec-CH-UA-Bitness`, not through `platform`. Camoufox's
`fix_navigator_arch` has a Firefox-shaped equivalent of this rule; the Chromium rule is
different and must not be ported by analogy.

**Locale and time.** `navigator.language` equals `navigator.languages[0]`. The first
entry of the `Accept-Language` request header equals `navigator.language`.
`Intl.DateTimeFormat().resolvedOptions().timeZone` equals the configured timezone, and
its `locale` is consistent with `navigator.language`. `Date.prototype.getTimezoneOffset`
must return the offset that the configured zone actually has *at the instant it is
called*, which means daylight-saving transitions must be honoured — a fixed offset
substituted for a zone is detectable by sampling two dates six months apart. Where
geolocation is configured, the timezone must be plausible for the coordinates.

**Graphics.** The WebGL `UNMASKED_VENDOR_WEBGL` and `UNMASKED_RENDERER_WEBGL` strings
must be a pair observed together on a real device and must be plausible for the target
OS; an Apple GPU string under a Windows user agent ends the session. The WebGL
parameter table — maximum texture size, maximum renderbuffer size, the various limits —
must match what the claimed renderer really reports, which is why Camoufox samples
these from a bundled database rather than generating them. WebGL2 parameters must be
consistent with the WebGL1 ones. Canvas noise seeds must be identical between the
window and every worker, and between the 2D readback path and the WebGL readback path.

**Audio and media.** The audio seed obeys the same cross-process rule as the canvas
seed. `AudioContext.sampleRate` must be plausible for the claimed OS.
`mediaDevices.enumerateDevices()` counts must be consistent with the claimed hardware,
and device identifiers must be stable per origin for the lifetime of a session.

**Network.** The three user-agent channels must agree with each other, which is
important enough to have its own section below. WebRTC ICE candidates must not
contradict the claimed public address.

### 4.4 Chromium-specific traps with no Camoufox counterpart (SP5b)

**Three user-agent channels rather than one.** Firefox exposes browser identity through
the user-agent string and little else. Chromium exposes it three times: the UA string,
the `navigator.userAgentData` object, and the `Sec-CH-UA` family of request headers.
All three must derive from one config source, which is SP1's responsibility; the
invariant that they agree lives here. There is a fourth, subtler channel: which hints a
browser sends is itself a pattern. High-entropy hints are only sent after a server
opts in through `Accept-CH`, so a fork that always sends everything, or never sends the
low-entropy set, is distinguishable from real Chrome without any value being wrong.

**GREASE brands.** Chrome's brand list contains a deliberately varying entry generated
deterministically from the major version. A preset that stores a brand list captured
from a different milestone will carry a GREASE entry that milestone would never
produce. The mitigation is architectural rather than a validation rule: presets store
the milestone and let the fork regenerate the brand list with Chromium's own function,
so the output is correct by construction.

**Claimed version versus actual behavior.** A detector can compare the version a
browser claims against the web platform features it actually implements. Claiming
Chrome 120 while supporting an API that first shipped in 126 is a contradiction no
amount of value spoofing repairs, because the evidence is the engine itself. The
recommendation that follows is narrower than Camoufox's ambition and should be stated
plainly: **do not spoof the browser version.** Claim the fork's real Chromium
milestone and spoof only the identity dimensions that genuinely vary between real users
— operating system, GPU, screen, fonts, locale, timezone. A fork that lags upstream by
a milestone or two looks like a user who has not restarted their browser, which is an
enormous and unremarkable population. A fork that claims a version it does not
implement looks like a fork. The consequence is a maintenance obligation — the fork
must track upstream reasonably closely — which belongs to SP6b.

**Proprietary codecs.** Stock Chromium is built without proprietary codec support,
while Chrome ships with it. A build claiming to be Chrome that answers
`canPlayType('video/mp4; codecs="avc1.42E01E"')` with the empty string instead of
`probably` is trivially detectable, and no C++ spoofing of the answer will make the
media pipeline actually decode the stream if a detector tests playback rather than the
advertisement. This is a build-configuration invariant, not a runtime one: the fork
must be built with proprietary codecs and Chrome ffmpeg branding enabled. **SP7 owns
the flags** — it did not exist when this spec was first written and the obligation was
provisionally assigned to SP6 — and SP7 additionally identifies Widevine as a second
discriminator of the same shape, reached through `requestMediaKeySystemAccess`. SP5
owns the assertion that the codec and key-system answer matrix matches the claimed
browser.

**GPU process versus renderer.** The renderer reports WebGL strings, but the GPU
process holds `gpu::GPUInfo`, which is also surfaced through `chrome://gpu`, through
crash and telemetry paths, and through the WebGPU adapter. Spoofing at the renderer
alone leaves the GPU process telling a different story. SP3 decides where the
substitution happens; SP5 asserts that whatever the two report cannot disagree.

**WebGPU.** Chromium ships WebGPU, so `GPUAdapter.info` exposes vendor, architecture,
device and description as a second, independent graphics identity. It must agree with
the WebGL strings and with the claimed OS. Firefox's limited WebGPU exposure means
Camoufox has nothing to port here; this surface is new and unguarded.

**The `window.chrome` object.** Real Chrome exposes a `chrome` object with `runtime`,
`loadTimes` and `csi` members whose presence and shape vary between Chrome, plain
Chromium, and headless. Its absence or wrong shape is a classic check. The conventions
assign construction of that object to **SP2** — the historically important failure,
headless Chrome lacking the object entirely, is an automation tell rather than a
branding one — and the invariant that its shape matches the claimed browser lives here.

### 4.5 The preset path (SP5b)

Camoufox ships `fingerprint-presets-v150.json`, a set of real captured fingerprints
version-matched to its Firefox build, and can replay one instead of synthesising a
profile. Camoucrome needs the equivalent, but a flat replay is the wrong shape for
Chromium because so much of a Chrome identity is derivable and version-bound.

A Camoucrome preset stores the **minimum identifying set** and nothing that can be
computed from it: the capture's Chromium milestone, the operating system and its
version, the GPU vendor and renderer pair together with the parameter table observed
with it, the screen geometry with the DPR it was captured at, the font list, the locale
and timezone, and the audio sample rate. Everything else — the UA string, the brand
list including GREASE, `fullVersionList`, the `Sec-CH-UA` header set,
`navigator.platform`, the orientation, the system font resolution — is expanded at load
time by `preset_loader` using the same derivation helpers the validator uses. This
makes presets robust against milestone drift in a way a flat capture is not, and it
removes an entire category of preset staleness bugs by construction.

On load the preset's milestone is compared against the fork's own. Three policies were
considered: refuse on mismatch, rewrite the version-bearing fields to the fork's
milestone, or accept with a warning. The recommendation is **rewrite**, for the same
reason version spoofing is rejected above — the fork's observable behavior is that of
its own milestone, so that is the only version it can claim without contradiction. A
preset is a claim about hardware and locale, not about browser version.

When the fork's Chromium version advances past every shipped preset, nothing breaks:
the hardware and locale dimensions remain valid indefinitely, and the version-bearing
fields were already being regenerated. What does degrade over time is the *population
realism* of the hardware distribution — a GPU that was common two years ago is less
common now — which is a refresh cadence question rather than a correctness one.

## 5. Coherence constraints

SP5 is the coherence constraints, so this section instead records what SP5 itself must
stay consistent with.

The invariant registry must stay consistent with the **key** registry,
`settings/keys.json`, which **SP6a** introduces. These are two different files with two
different jobs and neither subsumes the other: `settings/keys.json` declares which keys
exist and what type each holds, while `settings/invariants.json` declares which
relationships between those keys must hold. The conventions record both.

An invariant naming a key that does not exist in `settings/keys.json`, or a key with no
invariant in a cluster where its siblings have one, is itself a defect and the test
suite checks for both. This is the specific failure Camoufox exhibits — keys read by
C++ but declared nowhere, and a casing split between schema and reader — and catching
it mechanically is the only reliable defence. It is also why SP6a must land before SP1
rather than at the end.

The derivation helpers must be the same code the surfaces use. If `derive.cc` computes
an orientation from screen dimensions and the screen surface computes its own, they
will diverge. Surfaces call the helper; they do not reimplement it.

Repairs must not fight the operator. If a repair changes a value the operator set
explicitly, that must be visible in the log rather than silent, because an operator who
believes they configured a 1440-tall screen and got a repaired 1080 will misread every
subsequent test result.

## 6. Verification

1. **Mutation test per invariant.** For each entry in the registry, start from a known
   good config, corrupt exactly the keys that entry constrains, and assert the validator
   reports that entry and no other. A registry entry with no passing mutation test is
   documentation, not enforcement. This test is generated from the registry, so adding
   an invariant without a test is not possible.

2. **Repair idempotence.** For every mutation above whose policy is `repair`, run the
   validator on its own output and assert zero further changes and a byte-identical
   config.

3. **Generated configs are clean.** Generate at least 1000 configs from the fingerprint
   generator across all supported target platforms and assert the validator reports zero
   violations on every one. A failure here means the generator and the registry disagree,
   which is the exact drift SP5 exists to prevent.

4. **Shipped presets are clean.** Load every preset in `settings/presets/`, expand it,
   and assert zero violations. Run this in CI so a preset added later cannot regress.

5. **Cross-process identity.** With one config, read each seed and each identity value
   from the window, a dedicated worker, a shared worker and a service worker, and assert
   all four are identical. Expected output is four equal values per key; any difference
   is a failure. This is the class of bug Camoufox needed `cross-process-storage.patch`
   for and the one most likely to be missed by page-level testing.

6. **A/A and A/B determinism.** Two launches with the same config must produce
   byte-identical fingerprints across every surface. Two launches with configs differing
   in a dimension must differ in that dimension and only that dimension. The first half
   catches non-determinism; the second half catches a spoof that silently did nothing,
   which is the failure Camoufox issue #58 was about.

7. **Timezone across a DST boundary.** With a configured zone that observes daylight
   saving, assert `getTimezoneOffset` differs between a January date and a July date and
   that both match the zone's real offsets. A fixed-offset implementation passes a naive
   check and fails this one.

8. **Real detectors, as canaries.** Record results against CreepJS (capturing the
   specific lie-detection flags raised, not just a score), BrowserScan, fingerprint.com,
   and a Cloudflare and a DataDome challenge page. These are regression canaries, not
   proof. Passing them today says nothing about next month, and optimising against a
   detector's score rather than against the invariants leads to overfitting a single
   adversary — the invariant suite is the success criterion, and detector results are
   evidence that the invariant suite is not missing something obvious.

## 7. Open decisions

**Registry format.** JSON consumed by both the C++ validator and the Python generator
is the recommendation, because a shared data file is the whole point and JSON is the
one format both sides already parse. A small expression DSL would express relational
constraints more naturally than nested JSON, at the cost of writing an evaluator on
both sides. Not yet decided.

**Where the generator lives.** The config transport is byte-compatible with Camoufox by
design, so extending Camoufox's `pythonlib` is tempting. But the fingerprint *content*
diverges substantially — client hints, GREASE, WebGPU, a different OS-to-platform
mapping — so a shared package with a per-engine module is likely cleaner than a fork of
the existing generator. Not yet decided, and it interacts with SP6b.

**Preset sourcing.** Presets must come from real devices to be worth having. Whether
they are captured by the operator, drawn from an existing dataset, or contributed,
raises practical and licensing questions this spec does not resolve.

**Per-context validation.** When the per-context config store arrives, validation must
run per context rather than once at startup, and a context that fails validation must
fail to create rather than silently falling back to the global config. Where that check
runs, and whether a failing context is an error to the automation driver or a hard
launch failure, is undecided.

**Strictness default.** The conventions make `CAMOU_CONFIG_STRICT` opt-in. An argument
exists for inverting that once the registry is mature, since the population most likely
to run this fork would rather fail loudly than be quietly identified. Revisit after
SP1 through SP4 land.

## 8. Explicitly out of scope

The surfaces themselves belong to SP1, SP3 and SP4; this spec constrains their
relationships and does not describe how any individual value is substituted. The
`window.chrome` object and every other automation-hiding concern belongs to SP2, which
this spec references only where an invariant crosses into it. The build flags that make
the codec matrix match a real Chrome — proprietary codecs, ffmpeg branding and Widevine
— belong to **SP7**. The key registry `settings/keys.json` belongs to SP6a. The
obligation to track upstream milestones closely enough that claiming the real version
stays credible belongs to SP6b, as does the implementation of the fingerprint
generator; SP5 defines the contract that generator must satisfy, not how it satisfies
it.

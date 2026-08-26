# SP7 — Phone-home removal and build-level hardening

Assumes the decisions in [00-conventions.md](00-conventions.md).

## 1. Goal

Stop Chromium from making outbound requests that would deanonymise or correlate the
identities the rest of Camoucrome works to separate, and fix the build-configuration
differences that make a stock Chromium build falsifiable as Chrome regardless of what
any spoofed value claims.

The goal is deliberately **not** "make no network requests". Real Chrome contacts
Google constantly, and a browser presenting as Chrome that never does is anomalous to
anyone watching the network. The requests worth eliminating are the ones that fail one
of three tests:

**Does it carry a stable per-install identifier?** This is the primary threat and the
reason SP7 exists at all. Camoucrome's use case runs one identity per proxy. Metrics
carries a persistent client GUID, the component updater carries an install ID, and
variations carries the `X-Client-Data` header encoding active trial IDs. Any of these,
emitted from two sessions that are meant to be unrelated, links them — regardless of
how perfect the fingerprint is. A correlation leak defeats every other sub-project at
once, which makes SP7 higher-stakes than its "build hygiene" appearance suggests.

**Does it leak the real machine?** A Crashpad upload carries the module list, the
memory layout, and file paths that typically include the real username. That is a
richer disclosure than any fingerprint surface SP1 through SP4 protects.

**Does it reveal this is not stock Chrome?** Fewer callouts qualify here than one might
expect, because a page cannot observe the browser's traffic to third parties. This test
matters mostly for the *absence* of expected behaviour and for build-configuration
differences that surface in JavaScript — proprietary codecs and Widevine especially.

A fourth concern is narrower but sharp: any request that **bypasses the configured
proxy** leaks the real egress IP. Chromium's updater on Windows runs partly outside the
browser process and does not necessarily honour the browser's proxy settings.

## 2. Depends on

Nothing blocks SP7. It is almost entirely GN arguments and build configuration, so it
can start the moment the tree builds, and it is the cheapest sub-project to land.

Two later sub-projects depend on decisions made here. SP4 spoofs the codec query APIs
and must not claim support the build cannot honour (§5). SP5's presets encode a claimed
Chrome milestone whose expected feature set depends on the branding decision left open
in §7.

## 3. Surfaces

SP7 controls build configuration rather than config-keyed values, so this table
deviates from the conventions' shape: it lists each subsystem, the lever, where that
lever lives, and whether the effect is observable from a page. Paths were verified
against the live checkout at `~/chromium/src` except where marked.

| Subsystem | Lever | Location | Page-observable |
|---|---|---|---|
| Variations / Finch seed fetch | source patch + runtime | `components/variations/service/variations_service.cc` | indirectly, via feature availability |
| Field-trial testing config | GN arg / switch | `testing/variations/fieldtrial_testing_config.json` | indirectly, via feature availability |
| `X-Client-Data` header | falls out of variations removal | `components/variations/` | no (network-visible only) |
| Crash reporting upload | GN arg `enable_crash_reporter` *(location unverified)* | `components/crash`, `third_party/crashpad` | no |
| Metrics / UMA | GN arg `enable_reporting` *(location unverified)* | `components/metrics` | no |
| Component Updater | source patch | `components/component_updater` | partly — see CRLSet and Origin Trials below |
| Auto-update (Omaha / Keystone) | GN arg + omit target | `chrome/updater` | no |
| Safe Browsing | GN arg `safe_browsing_mode = 0` | `components/safe_browsing/buildflags.gni:23,25,27` | no |
| Domain Reliability | source patch or runtime pref | `components/domain_reliability` | no |
| Network Time | source patch or runtime pref | `components/network_time` | no |
| Google API keys | GN args `use_official_google_api_keys`, `google_api_key` | `google_apis/config.gni:21`, `google_apis/BUILD.gn:25,40,48` | no |
| Proprietary codecs | GN args `proprietary_codecs`, `ffmpeg_branding` | `build/config/features.gni:31`; ffmpeg options *(unverified)* | **yes** |
| Widevine CDM | GN arg `enable_widevine` + CDM availability | `build/config/` *(declaration site unverified)* | **yes** |
| Branding | GN arg `is_chrome_branded` | `build/config/chrome_build.gni:12` | indirectly |

The two rows in bold are the only ones a website can test directly. Everything else is
a correlation or disclosure risk rather than a fingerprint mismatch, which is why §1
frames the goal the way it does rather than as "look more like Chrome".

## 4. Design

### 4.1 Prefer compiling out

Where a GN argument exists, use it rather than a runtime pref or a command-line
switch. Three reasons, in order of weight.

A compiled-out subsystem cannot be re-enabled by a policy file, an enterprise
configuration, a stray command-line flag, or a future rebase that changes a default.
Runtime disabling leaves the code and its endpoint strings in the binary, so a mistake
anywhere in the launch path silently restores the callout. Second, compiling out is
verifiable by inspection: §6.7 checks that the endpoint hostnames are absent from the
binary, which distinguishes "compiled out" from "disabled by a flag someone might
forget". Third, it matches the project's C++-first constraint and Camoufox's own
precedent — `librewolf/disable-data-reporting-at-compile-time.patch` exists because
LibreWolf reached the same conclusion about Firefox's telemetry.

Where no GN argument exists, prefer a source patch over a runtime pref, but keep the
patch to the smallest possible edit at the service's construction site so it survives
rebases. Per the conventions' repository layout, an edit that can be expressed as "do
not construct this service" is a one-line diff; an edit that rewrites the service is a
recurring merge conflict.

### 4.2 Variations and Finch — the subtle one

This deserves more care than the rest combined, because both the obvious options are
wrong and the correct answer is not yet decided.

Chromium fetches a variations seed at startup. The seed activates field trials, field
trials gate features, and some features gate the existence of JavaScript APIs. So the
seed is, at one remove, page-observable: two browsers of the same milestone with
different seeds expose different API surfaces. It also produces the `X-Client-Data`
header sent to Google properties, which encodes the active variation IDs and is a
well-studied correlation vector.

The obvious move — disable the fetch — leaves the browser at pure compiled-in defaults.
Real Chrome installs are distributed across a space of seed-dependent feature states;
a browser sitting exactly at defaults occupies one specific, consistent point in that
space that few real installs occupy. Whether any detector currently checks this is
unknown, but the vector is real and the position is stable across every Camoucrome
instance, which is precisely the property that makes a fingerprint useful to a
detector.

The less obvious problem is worse and applies today. **A developer build is not at
Chrome's defaults either.** Chromium applies `testing/variations/fieldtrial_testing_config.json`
by default in non-branded builds, which real Chrome does not. So an unmodified
Camoucrome build currently sits at a third point — matching neither seeded Chrome nor
default Chrome — and this is true before anyone touches variations at all. Disabling
that config with `--disable-field-trial-config` is the minimum correct action and is
independent of everything else in this section.

SP7 therefore does two things now and leaves one open. It disables the seed fetch, so
nothing phones home and no `X-Client-Data` is emitted. It disables the testing config,
so the build is not sitting at a state no real browser occupies. What it does not
settle is whether Camoucrome should later **ship a captured seed** matching the claimed
milestone, so feature state resembles a plausible real install rather than the defaults.
That is genuinely novel work with no Camoufox precedent and it is recorded in §7.

### 4.3 Crash reporting

Compile out with `enable_crash_reporter` *(GN argument name confident, declaration site
unverified)*. Uploads carry the module list, memory layout, and paths that usually
embed the real username.

One detail survives disabling uploads: Crashpad may still write dumps to disk inside
the user data directory. A profile template that is copied between identities would
carry them. SP7 must confirm no dump directory is created, not merely that nothing is
uploaded — §6.4 tests this by inducing a crash rather than by reading configuration.

### 4.4 Metrics, updater, Safe Browsing, and the rest

**Metrics/UMA** — `enable_reporting` *(name confident, declaration site unverified)*.
The persistent client GUID it maintains is the clearest instance of the correlation
threat in §1.

**Component Updater and auto-update** — compile out the updater target and patch out
the component updater's construction. `chrome/updater/` exists in the tree (verified).
This one has a real cost that must be stated: the component updater delivers CRLSet
revocation data and the Origin Trials public keys, among others. A build that never
updates them has stale certificate revocation information and may reject Origin Trial
tokens that a real Chrome accepts — the latter is page-observable in principle. The
recommendation is still to remove it, because a per-install update ID that may bypass
the proxy is a worse problem than stale CRLSets, but SP7 should bundle a
milestone-matched CRLSet and Origin Trials key set at build time rather than shipping
empty ones.

**Safe Browsing** — `safe_browsing_mode = 0`, verified declared at
`components/safe_browsing/buildflags.gni:23`. This is high priority and often
overlooked: in its normal modes Safe Browsing sends URL hash prefixes for navigations,
which discloses browsing activity to a third party on a channel that has nothing to do
with the identity's proxy. For a scraping browser this is both a correlation vector and
a straightforward leak of what is being scraped.

**Domain Reliability and Network Time** — both directories verified present. Neither
has an obvious dedicated GN argument, so both are construction-site patches. Network
Time carries a second consideration: SP4 spoofs the timezone, and a browser that
silently corrects its clock against a Google time server introduces a second source of
truth about time. Removing it is the coherent choice as well as the private one.

**Google API keys** — leave `google_api_key` empty and set `use_official_google_api_keys`
to false. `google_api_key = ""` is the declared default at `google_apis/BUILD.gn:25`,
and `use_official_google_api_keys` is a tri-state declared as `""` at
`google_apis/config.gni:21` and resolved at `BUILD.gn:40,48`. Nothing important breaks,
because the features that need keys — sync, translate, full Safe Browsing — are being
removed anyway. The one visible consequence is Chromium's "Google API keys are missing"
warning; `google_api_keys.cc:70` defines `kAPIKeysDevelopersHowToURL`, confirming that
warning path exists. It appears in the browser UI, not to a page, and not at all in
headless operation, so it is cosmetic here — but it should be suppressed so a
screenshot of a headful session does not advertise the build.

### 4.5 Proprietary codecs

`build/config/features.gni:31` declares
`proprietary_codecs = is_chrome_branded || is_castos || is_cast_android || …`, and
`build/config/chrome_build.gni:12` declares `is_chrome_branded = false`. Both verified.
A stock developer build therefore ships **without** H.264 and AAC, so
`canPlayType('video/mp4; codecs="avc1.42E01E"')` returns the empty string where real
Chrome returns `"probably"`. This is a one-line detection that no amount of value
substitution elsewhere repairs, and SP5 identified it as such.

The levers are `proprietary_codecs = true` and `ffmpeg_branding = "Chrome"`
*(the ffmpeg option file was not in the probed set; unverified)*.

The licensing position should be stated plainly rather than buried. H.264 and AAC are
covered by patent pools — Via LA, formerly MPEG-LA. Google holds licences that cover
distribution of Chrome. A third-party build that enables these codecs is not covered by
those licences, and the obligations attach to distribution, not to building for
personal use. This is a decision for the project owner, not a technicality to wave
through: building locally with the flag on is a materially different act from
distributing binaries with it on. It is recorded again in §7 for that reason.

### 4.6 Widevine

A page can call `navigator.requestMediaKeySystemAccess('com.widevine.alpha', …)`.
Real Chrome resolves it; a typical Chromium build rejects it, because the CDM is a
proprietary binary Chromium does not bundle. This is as direct a Chrome-versus-Chromium
discriminator as the codec check and is page-observable, yet it is easy to miss because
it lives behind an async API rather than a synchronous property.

`enable_widevine` appeared during the probe only in Fuchsia cast argument files, so its
primary declaration site is *(unverified)*. Enabling the flag is not sufficient on its
own — the CDM binary must also be present, and its normal delivery mechanism is the
component updater that §4.4 removes. If the branding decision in §7 is "present as
Chrome", the CDM must be bundled at build time and this becomes a real piece of work
rather than a flag flip.

### 4.7 Directory and service naming

Camoufox needed `librewolf/mozilla_dirs.patch` and `dbus_name.patch` to relocate the
profile directory and rename the DBus service. The Chromium equivalents matter much
less. The user data directory is set per-launch by the driver through `--user-data-dir`,
which every automation setup already does, so no patch is needed. On Linux there is a
DBus service name and a `.desktop` identifier; neither is page-observable and neither
affects correlation. Low priority, listed for completeness, not scheduled.

## 5. Coherence constraints

**SP7 and SP4 — codecs.** SP4 spoofs the answers from `canPlayType`, `decodingInfo`,
and `MediaSource.isTypeSupported`. SP7 determines what the build can actually decode.
The invariant is that **SP4 must never claim codec support the build does not have**.
If it does, a page that asks and then attempts playback gets a contradiction: the API
promised `"probably"` and the video fails. That two-stage check is stronger evidence
than the original mismatch, so an incorrect spoof here is worse than no spoof. This is
the clearest instance in the project of the conventions' rule 4.

**SP7 and SP1 — the Chrome claim.** SP1 makes the browser assert a Chrome identity
through the UA string and UA-CH brands. Every build-level difference SP7 leaves
unfixed is a way to falsify that assertion without touching a single spoofed value.
Codecs and Widevine are the two that a page can reach today.

**SP7 and SP5 — presets and milestone.** SP5's presets encode a claimed milestone. The
feature state that milestone implies depends on the variations decision in §4.2 and on
the branding decision in §7. A preset claiming a milestone whose features the build
does not expose is the same class of contradiction as the codec case.

**SP7 and SP4 — time.** Removing Network Time (§4.4) leaves the system clock and SP4's
spoofed timezone as the only sources of truth about time, which is the coherent state.
Leaving it in creates a third.

## 6. Verification

Each item is independently runnable against a build in `out/Default`. Items 1, 4, 5 and
7 are the ones that would catch a regression introduced by a rebase.

1. **Network silence under idle.** Launch with a proxy capturing all traffic, open
   `about:blank`, idle for 120 seconds, then assert zero requests to
   `clientservices.googleapis.com`, `clients2.google.com`, `clients4.google.com`,
   `safebrowsing.googleapis.com`, `update.googleapis.com`, and `*.gvt1.com`. Expected:
   an empty capture. Run the same test against a stock `content_shell` from the same
   revision to confirm the capture setup actually observes traffic — a silent capture
   that was never wired up passes this test vacuously.

2. **Proxy containment.** With the proxy configured for all traffic and the host's
   direct route to the internet blocked at the firewall, launch, browse for 120
   seconds, and assert the browser neither errors on nor attempts any direct
   connection. Expected: no egress outside the proxy. This is the test for the
   real-IP leak in §1, and it must be run on Windows specifically, because that is
   where the updater has its own process.

3. **Codec matrix.** Evaluate `canPlayType` for `video/mp4; codecs="avc1.42E01E"`,
   `audio/mp4; codecs="mp4a.40.2"`, `video/webm; codecs="vp9"`, and
   `audio/ogg; codecs="opus"`. Expected: identical answers to a real Chrome of the
   claimed milestone on the same OS. Record that real Chrome's answers were captured,
   not assumed.

4. **No crash artefacts.** Induce a renderer crash with `chrome://crash`, then assert
   that no upload was attempted (item 1's capture) **and** that no dump file appeared
   under the user data directory. Expected: neither. Testing by inducing a crash rather
   than by reading configuration is the point — a disabled uploader that still writes
   dumps passes a configuration review and fails this.

5. **No `X-Client-Data`.** With the capture from item 1, assert the header appears on no
   request to any host. Expected: absent.

6. **Widevine consistency.** Call `navigator.requestMediaKeySystemAccess('com.widevine.alpha', …)`.
   Expected: the outcome that matches the §7 branding decision — resolving if presenting
   as Chrome, and if presenting as Chromium, then SP1 must not be claiming Chrome.
   Either result is acceptable; the pair being inconsistent is not.

7. **Endpoint strings absent from the binary.** Run `strings` over the built binary and
   its component libraries and grep for the hostnames from item 1. Expected: absent.
   This is what separates compiled-out from runtime-disabled, and it is the check that
   fails first when a rebase restores a default.

8. **Field-trial state.** Dump the active field trials and compare against a real Chrome
   of the claimed milestone. Expected, for the scope SP7 commits to: no trials from
   `fieldtrial_testing_config.json` are active. The stronger expectation — that the set
   resembles a real install — is out of scope pending the §7 decision.

## 7. Open decisions

**D1 — Branding: present as Chrome or as Chromium?** This is the decision that
determines several levers above and it is genuinely unmade. Presenting as Chrome means
SP1 claims Chrome in the UA and UA-CH brands, which obliges SP7 to enable proprietary
codecs, bundle Widevine, and match Chrome's feature state — real work with a licensing
question attached. Presenting as Chromium means claiming Chromium honestly, which
costs nothing to build but narrows the disguise, because Chromium is a far rarer
browser and therefore a more distinctive fingerprint on its own. Recommendation:
present as Chrome, because the entire premise of an anti-detect browser is blending
into the common case, and Chromium's rarity defeats that — but this is contingent on
D2 and the user should decide both together.

**D2 — Proprietary codecs and distribution.** Building with `proprietary_codecs = true`
for local use is a different act from distributing such binaries. If Camoucrome is only
ever built and run by its author, the question is narrow. If binaries are distributed,
the patent-pool licences are a real obligation that Google's Chrome licence does not
extend to third-party builds. Recommendation: enable for local builds now, and settle
the distribution question before SP6 produces anything shippable. No recommendation is
offered on the licensing itself — that is not a technical call.

**D3 — Ship a captured variations seed?** §4.2 leaves the browser at compiled-in
defaults, which is a stable and therefore fingerprintable position. The alternative is
capturing a real seed for the claimed milestone and baking it in, so feature state
resembles a plausible install. The costs are that seeds expire and are milestone-bound,
which is the same treadmill SP5 designs its presets to avoid, and that a *shared*
captured seed would make every Camoucrome instance identical to every other — trading a
"defaults" fingerprint for a "same seed" fingerprint, which may be worse. Recommendation:
defer, and revisit only if a detector is observed checking feature state. Measure before
building.

**D4 — Unverified GN argument sites.** `enable_reporting`, `enable_crash_reporter`,
`enable_widevine`, and `ffmpeg_branding` were not located by the single probe this spec
was allowed. All four are well-established argument names, but their declaration sites
and exact semantics in this Chromium revision must be confirmed during implementation
before being written into a build configuration.

**D5 — CRLSet and Origin Trials keys.** §4.4 recommends bundling milestone-matched data
at build time to replace what the removed component updater would have delivered. The
mechanism is unspecified and the refresh story — what happens when the bundled CRLSet
ages — is unaddressed. Small, but it becomes a real question at SP6 packaging time.

## 8. Explicitly out of scope

The UA string and UA-CH brands that *claim* a browser identity belong to SP1; SP7 only
makes the build capable of honouring the claim. The codec query APIs themselves belong
to SP4; SP7 sets what the build can actually decode. Preset construction and milestone
matching belong to SP5. Packaging, installers, and the question of which GN arguments
land in a shipped build configuration belong to SP6 — SP7 specifies the arguments and
their justification, not the build driver that applies them.

Chromium's UI-level privacy hardening — the new-tab page, the default search engine,
onboarding, the sign-in promo — is not covered. Camoufox needed roughly fourteen patches
in this territory, but almost all of them address surfaces that only exist in headful,
interactive use. Camoucrome is driven by automation, so they are noise rather than
threat. If a headful mode becomes a supported configuration, this becomes its own
sub-project.

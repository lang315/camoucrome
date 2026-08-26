# SP4 — Remaining fingerprint surfaces

Status: draft, not yet approved.
Assumes everything in [00-conventions.md](00-conventions.md).

## 1. Goal

SP0 proves one surface can be driven from config. SP1 and SP3 establish the two hard
patterns: an identity block whose members must agree with each other, and a seeded-noise
surface whose seed must stay stable. SP4 applies those two patterns to everything left —
screen geometry, fonts, audio, media devices, codec support, battery, WebRTC addresses,
timezone and locale, and speech voices.

Individually these are small. Collectively they are where an anti-detect browser is
actually won or lost, because they are the surfaces a real device leaks through when
only the headline values (user agent, WebGL renderer) have been spoofed. Camoufox needed
roughly eighteen patches to cover this ground, and four of its nine hardest bugs live
here. The point of doing them as one SP is that they share a single question — does this
value agree with the OS we claim to be? — and answering it once per surface is cheaper
than answering it eighteen times across eighteen SPs.

After SP4 the browser can present a complete, self-consistent device identity. It cannot
yet *generate* one; that is SP5.

## 2. Depends on

**SP0** for the config component and the `ConfigScope`-shaped API. Every surface here is
a config read.

**SP1** for the platform-derivation helper. Several surfaces here (CSS2 system fonts, the
`system-ui` generic family, the codec matrix, speech voice URIs) must resolve from the
*claimed* OS rather than the host OS. SP1 owns the single function that answers "what OS
are we claiming"; SP4 consumes it and must not re-derive it from the user-agent string
independently. Two independent derivations that disagree is precisely the failure this
project exists to avoid.

**SP3** for the seeded-noise helper. Audio and font-metric jitter use the same
seed-derivation and stability rules as canvas. SP3 writes that helper; SP4 reuses it
rather than growing a second one.

SP4 does not depend on SP2 and may run alongside it.

## 3. Surfaces

Paths were checked against the real checkout at `~/chromium/src`
(HEAD `0e8d4a9268`) unless marked *(unverified)*.

### 3.1 Screen and viewport

| Value | Config key | Location | Process |
|---|---|---|---|
| `screen.width` / `.height` | `screen.width`, `screen.height` | `core/frame/screen.cc` | renderer |
| `screen.availWidth` / `.availHeight` / `.availTop` / `.availLeft` | `screen.avail*` | `core/frame/screen.cc` | renderer |
| `screen.colorDepth` / `.pixelDepth` | `screen.colorDepth`, `screen.pixelDepth` | `core/frame/screen.cc` | renderer |
| `window.outerWidth` / `.outerHeight` | `window.outer*` | `core/frame/local_dom_window.cc` | renderer |
| `window.innerWidth` / `.innerHeight` | `window.inner*` | `core/frame/local_dom_window.cc` | renderer |
| `window.screenX` / `.screenY` | `window.screenX`, `window.screenY` | `core/frame/local_dom_window.cc` | renderer |
| `devicePixelRatio` | `window.devicePixelRatio` | `core/frame/local_dom_window.cc` | renderer |
| `history.length` | `window.history.length` | `core/frame/history.cc` | renderer |
| `document.body.clientWidth` / `.clientHeight` | `document.body.client*` | `core/dom/element.cc` *(unverified)* | renderer |
| scroll min/max, `pageXOffset` / `pageYOffset` | `window.scroll*`, `window.pageX/YOffset` | `core/frame/local_dom_window.cc` | renderer |
| CSS `device-width` / `device-height` | *derived from `screen.*`* | `core/css/media_values.cc`, `media_values.h` | renderer |
| `screen.orientation.type` / `.angle` | `screen:orientation`, `screen:orientationAngle` | `modules/screen_orientation/screen_orientation.cc` | renderer |

`core/css/media_values.cc` is the Chromium counterpart to Firefox's `nsMediaFeatures`.
`core/css/media_feature_names.json5` confirms `device-width`, `min-device-width` and
`max-device-width` are registered feature names, and `core/css/media_query_evaluator.cc`
is where they are compared.

### 3.2 Fonts

| Value | Config key | Location | Process |
|---|---|---|---|
| Available font list | `fonts` (array of strings) | `platform/fonts/font_cache.cc` | renderer |
| `document.fonts.load()` resolution | `fonts` | `css/font_face_set_document.cc` *(unverified)* | renderer |
| Local Font Access API enumeration | `fonts` | `modules/font_access/` | renderer |
| Text metric jitter | `fonts:spacing_seed` | `core/html/canvas/text_metrics.cc` | renderer |
| CSS2 system-font keywords | *derived from claimed OS* | `core/css/` resolution path *(unverified)* | renderer |
| `system-ui` generic family | *derived from claimed OS* | `platform/fonts/font_family_names.json5` | renderer |

The Local Font Access API is present in this Chromium (`modules/font_access/`) and is
gated by the `FontAccess` runtime-enabled feature at
`platform/runtime_enabled_features.json5:3187`. Firefox has no equivalent, so Camoufox
never needed to handle it. It is a permission-gated enumeration of every installed font
and is therefore the single highest-yield font-fingerprinting surface Chromium offers.
It must be driven from the same `fonts` list as everything else, or disabled outright.

### 3.3 Audio

| Value | Config key | Location | Process |
|---|---|---|---|
| AnalyserNode FFT readback noise | `audio:seed` | `modules/webaudio/realtime_analyser.cc` | renderer |
| AudioBuffer channel-data readback noise | `audio:seed` | `modules/webaudio/audio_buffer.cc` | renderer |
| `AudioContext.sampleRate` | `AudioContext:sampleRate` | `modules/webaudio/audio_context.cc` | renderer |
| `AudioContext.outputLatency` | `AudioContext:outputLatency` | `modules/webaudio/audio_context.cc` | renderer |
| `destination.maxChannelCount` | `AudioContext:maxChannelCount` | `modules/webaudio/audio_context.cc` | renderer |

### 3.4 Media devices

| Value | Config key | Location | Process |
|---|---|---|---|
| `enumerateDevices()` microphone count | `mediaDevices:micros` | `modules/mediastream/media_devices.cc` | renderer |
| webcam count | `mediaDevices:webcams` | same | renderer |
| speaker count | `mediaDevices:speakers` | same | renderer |
| whether the API reports anything | `mediaDevices:enabled` | same | renderer |

### 3.5 Media codecs

| Value | Config key | Location | Process |
|---|---|---|---|
| `HTMLMediaElement.canPlayType()` | `mediaCapabilities:canPlayType` | `core/html/media/html_media_element.cc:1060` | renderer |
| `MediaCapabilities.decodingInfo()` | `mediaCapabilities:decodingInfo` | `modules/media_capabilities/media_capabilities.cc` | renderer |
| `MediaSource.isTypeSupported()` | `mediaCapabilities:canPlayType` | `modules/mediasource/media_source.cc` | renderer |

Camoufox's `MaskConfig::GetMediaCanPlayType` returns `"probably"`, `"maybe"`, `""`, or
`nullopt` to fall through to the real decoder, matching on a case-insensitive substring
of the MIME type with first-match-wins. That contract is worth keeping verbatim: it is
the only sane way to express a codec matrix without enumerating hundreds of MIME strings.

### 3.6 Battery

| Value | Config key | Location | Process |
|---|---|---|---|
| `charging`, `chargingTime`, `dischargingTime`, `level` | `battery:*` | `modules/battery/battery_manager.cc` | renderer (data from device service) |

`modules/battery/battery_manager.cc` exists. A grep of
`platform/runtime_enabled_features.json5` for a `Battery` feature name returned nothing,
so the API is not gated by a runtime flag under that name — but Chromium restricts the
Battery Status API more aggressively than Firefox did, and on some platforms it reports
constants rather than real hardware state. **Before writing any code, confirm what a stock
`content_shell` on this machine actually returns for `navigator.getBattery()`.** If it
already reports constant values, spoofing it is wasted work and the correct answer is a
note in the registry saying so. This is the SP4 item most likely to be deleted rather
than implemented.

### 3.7 WebRTC addresses

| Value | Config key | Location | Process |
|---|---|---|---|
| Public IPv4 in ICE candidates | `webrtc:ipv4` | `third_party/webrtc/p2p/base/port.cc` | renderer |
| Public IPv6 | `webrtc:ipv6` | same | renderer |
| Local IPv4 | `webrtc:localipv4` | same | renderer |
| Local IPv6 | `webrtc:localipv6` | same | renderer |
| SDP rewriting | all of the above | `third_party/webrtc/pc/peer_connection.cc` | renderer |
| Blink-side factory | — | `modules/peerconnection/peer_connection_dependency_factory.cc` | renderer |

The Blink-level `rtc_peer_connection.cc` is a thin wrapper; the addresses are minted deep
inside the vendored `//third_party/webrtc` library. Patching a vendored third-party
library is a maintenance burden every Chromium roll will re-open, which makes this the
most expensive surface in SP4 per unit of value.

Chromium ships `--force-webrtc-ip-handling-policy` and the
`WebRTCIPHandlingPolicy` preference, which can restrict candidates to the default public
interface without any patch. That does not *substitute* an address, but it does prevent
the real local address from leaking, which is the majority of the practical risk. See
Open decisions.

### 3.8 Timezone, locale, geolocation

| Value | Config key | Location | Process |
|---|---|---|---|
| `Date` timezone offset and name | `timezone` | `v8/src/date/date.cc` | renderer (V8) |
| `Intl.DateTimeFormat().resolvedOptions().timeZone` | `timezone` | `v8/src/objects/js-date-time-format.cc` | renderer (V8) |
| Process default timezone | `timezone` | `base/i18n/timezone.cc`, `base/i18n/icu_util.cc` | all |
| `navigator.language` / `.languages` | `locale:language`, `locale:all` | SP1 owns these | renderer |
| `Accept-Language` header | `headers.Accept-Language` | SP1 owns this | browser |
| `Intl` collation, number and date formatting | `locale:*` | ICU default locale | renderer |
| Geolocation position | `geolocation:latitude`, `:longitude`, `:accuracy` | `services/device/geolocation/geolocation_impl.cc` | **device service, not renderer** |

Geolocation is the one surface in SP4 that does not live in Blink at all. It is served by
the device service over Mojo, which means the config read happens outside the renderer and
`ScopeFor(execution_context)` is not available there. Until the per-context store exists,
geolocation can only be a process-global value. Flag this rather than pretending otherwise.

### 3.9 Speech voices

| Value | Config key | Location | Process |
|---|---|---|---|
| `speechSynthesis.getVoices()` | `voices` | `modules/speech/speech_synthesis.cc` | renderer |
| Block when unconfigured | `voices:blockIfNotDefined` | same | renderer |
| Fake utterance completion | `voices:fakeCompletion`, `:charsPerSecond` | same | renderer |

## 4. Design

Every surface follows the SP0 pattern: at the point where Chromium computes the real
value, consult config first and fall back to the real value when config is absent. The
design work in SP4 is not in the individual reads — those are mechanical — but in the
five places where the naive read is wrong.

**Screen geometry must be spoofed in two places at once.** `screen.width` is read by
`Screen::width()` in `core/frame/screen.cc`, and independently by
`MediaValues::DeviceWidth()` in `core/css/media_values.cc` when a stylesheet asks
`@media (device-width: …)`. Patching only the first leaves a CSS media query that
contradicts the JS-visible value, which is trivially detectable and is exactly the bug
Camoufox's `screen-spoofing.patch` exists to close on the Firefox side. Both call sites
must read the same config key through the same helper. The same applies to
`screen.orientation`, whose type and angle are derived quantities: a spoofed 1920×1080
screen reporting `portrait-primary` is a contradiction. Derive orientation from the
spoofed dimensions by default and treat the explicit config keys as an override.

**Font work splits into three problems of very different difficulty.** Enumeration —
making `font_cache.cc` report only the configured list — is straightforward. Blocking
probes is medium: a page can detect an unlisted font by measuring text width with it
requested versus a fallback, so `document.fonts.load()` must resolve only for listed
fonts and the CSS font-matching path must never silently fall back to a real font that
is not on the list. Metric jitter is hard: Camoufox needed 55KB of patch across
`measureText`, layout, `OffscreenCanvas` and the graphics layer, because the same glyph
advance leaks through many independent paths. SP4 should implement enumeration and probe
blocking, and deliberately scope metric jitter as its own follow-on rather than pretending
it is a line item — see Open decisions.

The Local Font Access API has no Firefox counterpart and therefore no Camoufox precedent.
It is permission-gated, so a page cannot silently enumerate, but a page that obtains
permission gets the complete real font list in one call. It must read the same `fonts`
list, or the `FontAccess` runtime feature must be disabled in the build. Disabling is the
cheaper correct answer and should be the default.

**Timezone must be enforced inside V8, not at the DOM boundary.** `Date` reads its offset
from V8's date cache, which is populated from the ICU default timezone;
`Intl.DateTimeFormat().resolvedOptions().timeZone` reads ICU directly through
`js-date-time-format.cc`. A DOM-level override would leave `Intl` reporting the host zone
while `Date` reported the spoofed one — a two-line detection. Camoufox solved this by
patching SpiderMonkey's `js/src/DateTime.cpp` directly.

Chromium already contains a working mechanism for this: the CDP command
`Emulation.setTimezoneOverride`, implemented by the inspector's emulation agent, which
sets the isolate's timezone and issues V8's date-configuration-change notification so the
cache is invalidated. SP4 should call the same underlying machinery from config at
document initialisation rather than re-implementing it, and rather than requiring a CDP
round-trip. Driving it from config means it works with no debugger attached, which is the
whole point.

**This is where Camoufox issue #57 came from, and why SP0's API shape matters.** In
Camoufox, timezone could only be set through the launch-time environment variable. There
was no path for a value to reach the C++ layer per browser context, so Playwright's
per-context `timezone_id` had nowhere to go, and launch-level timezone behaved
inconsistently because nothing re-applied it per document. In Camoucrome every read is
already written as `camoucfg::GetString(ScopeFor(execution_context), "timezone")`. When
the per-context backing store lands, the correct per-context timezone arrives at every
existing call site with no edit. The bug class is designed out rather than patched later.

One caveat, and it is a real one: contexts that share a renderer process share a V8
isolate, and the ICU default timezone is isolate-wide. Whether Chromium's process model
guarantees separate renderers per browser context in all the cases that matter needs
verification before per-context timezone can be promised. Recorded in Open decisions.

**Codec answers must be internally consistent and OS-plausible.** `canPlayType()`,
`MediaSource.isTypeSupported()` and `MediaCapabilities.decodingInfo()` are three views of
one underlying question. A profile claiming macOS that reports no HEVC hardware decode, or
a profile claiming Linux that reports full PlayReady support, is incoherent. All three
must be answered from one config-backed table, and `decodingInfo`'s `supported`, `smooth`
and `powerEfficient` triple must be derivable from the same entry that answers
`canPlayType`. This is Camoufox issue #6 restated for Chromium.

**Speech voices carry a lesson rather than a difficulty.** Camoufox's schema file
`settings/camoucfg.jvv:291` declares the field as `voiceURI` while `MaskConfig.hpp` and
the Python generator both read `voiceUri`. A configuration that validates against the
published schema is silently rejected by the C++ that consumes it. SP4 adopts one
spelling — `voiceUri`, matching the JavaScript-visible attribute name minus the
capitalisation trap — and validates it in exactly one place: the key registry in
`settings/`, which both the C++ reader and any generator consume. No second spelling
exists anywhere in the tree.

## 5. Coherence constraints

| This surface | Must agree with | Invariant |
|---|---|---|
| CSS `device-width` / `device-height` | `screen.width` / `.height` | Identical values, from the same config read |
| `screen.orientation.type` / `.angle` | `screen.width` / `.height` | Landscape iff width > height; angle consistent with type |
| `screen.availHeight` | `screen.height` | Strictly less, or CreepJS's `noTaskbar` heuristic fires |
| `window.inner*` | `window.outer*` | inner ≤ outer, both axes |
| `window.outer*` | `screen.avail*` | outer ≤ avail, both axes |
| `window.screenX` / `.screenY` | `screen.*`, `window.outer*` | 0 ≤ position ≤ screen − outer |
| `devicePixelRatio` | `screen.*`, `window.inner*` | Geometry must be expressed in the CSS pixels that ratio implies |
| CSS2 system fonts, `system-ui` | claimed OS (SP1) | Resolved from the claimed platform, never the host |
| `fonts` list | claimed OS (SP1) | Every listed font plausible for that OS; marker fonts present |
| Local Font Access enumeration | `fonts` list | Identical set, or the API is disabled |
| `decodingInfo()` | `canPlayType()` | Same underlying table; no MIME type answered differently |
| Codec matrix | claimed OS (SP1) | Hardware-decode claims plausible for that OS and GPU (SP3) |
| Speech voice URIs and names | claimed OS (SP1) | OS-shaped URIs; a macOS profile must not list Microsoft voices |
| `timezone` | `geolocation:*` and proxy egress (SP5) | Zone consistent with the coordinates and the exit IP |
| `Intl` timezone | `Date` timezone | Byte-identical zone identifier |
| `locale:*` | `navigator.languages`, `Accept-Language` (SP1) | One source; SP1 owns the value, SP4 owns ICU application |
| `audio:seed` in a worker | same seed in its window | Identical; a worker disagreeing is a tell |
| `webrtc:*` addresses | proxy egress IP (SP5) | Candidate address must match the address the site sees |

The last one deserves emphasis. Spoofing a WebRTC address to a value that differs from
the IP the HTTP request arrived from is worse than leaving WebRTC alone: it converts a
passive leak into an active contradiction. The address must come from the same source
that knows the egress IP, which is SP5's job.

## 6. Verification

Each item is run against `content_shell` built at `out/Default`, launched with an
explicit `CAMOU_CONFIG` and inspected over the DevTools protocol.

1. **Screen JS/CSS agreement.** With `screen.width` set to 1920 on a host whose real
   width differs, a page evaluating `screen.width` and
   `matchMedia('(device-width: 1920px)').matches` must report `1920` and `true`. Run the
   same check with a deliberately wrong media query width and require `false`.
2. **Orientation derivation.** With a 1920×1080 config and no explicit orientation keys,
   `screen.orientation.type` must be `landscape-primary` and `.angle` must be `0`.
   With 1080×1920, `portrait-primary`.
3. **Geometry invariants.** For twenty randomly generated screen configs, assert
   `inner ≤ outer ≤ avail ≤ screen` on both axes and `availHeight < height` in every case.
   This is a unit test over the clamping helper, not a browser launch.
4. **Font enumeration.** With `fonts` set to a five-name list, a page that measures text
   width for each of those five plus five known-absent names must find exactly five
   distinct widths and five identical fallback widths. `document.fonts.check()` must
   return `true` for the five and `false` for the others.
5. **Local Font Access.** Either `navigator.fonts.query()` returns exactly the configured
   list, or `navigator.fonts` is `undefined` because the runtime feature is disabled.
   Any third outcome is a failure.
6. **Audio seed stability.** The same `audio:seed` across two page loads must produce a
   byte-identical `AnalyserNode.getFloatFrequencyData()` result; two different seeds must
   differ. A worker computing the same readback must match its window.
7. **Audio context values.** `new AudioContext().sampleRate` returns the configured value;
   `outputLatency` and `destination.maxChannelCount` likewise.
8. **Media device counts.** `navigator.mediaDevices.enumerateDevices()` returns exactly
   the configured number of entries of each kind, with plausible `deviceId` and
   `groupId` shapes.
9. **Codec consistency.** For every MIME type in a fixed test list, assert
   `canPlayType(t)`, `MediaSource.isTypeSupported(t)` and
   `MediaCapabilities.decodingInfo({type:t,…})` give mutually consistent answers, and that
   the answers match the configured table.
10. **Battery baseline first.** Record what stock `content_shell` returns from
    `navigator.getBattery()` on this machine before implementing anything. Only if it
    reports real host state does the spoof get built; the expected result is then that
    configured values are returned verbatim.
11. **WebRTC candidates.** With `webrtc:ipv4` configured, every `candidate` line produced
    by a data-channel-only `RTCPeerConnection` must contain the configured address and
    must not contain any real host address. Assert against the full SDP text, not the
    first candidate.
12. **Timezone across Date and Intl.** With `timezone` set to `Europe/London` on a host in
    `Asia/Ho_Chi_Minh`: `Intl.DateTimeFormat().resolvedOptions().timeZone` is
    `Europe/London`, `new Date().getTimezoneOffset()` matches London for that date, and
    `new Date().toString()` contains a London zone abbreviation. All three, or it fails.
13. **Timezone in a worker.** The same three assertions inside a `Worker`.
14. **Timezone across a DST boundary.** Two `Date` objects either side of the configured
    zone's DST transition must show the correct differing offsets — a hardcoded constant
    offset passes item 12 and fails here.
15. **Speech voices.** `speechSynthesis.getVoices()` returns exactly the configured
    entries with the `voiceUri` spelling honoured end to end, from registry through C++ to
    the JS-visible `voiceURI` attribute.
16. **No new observable surface.** Against every item above, `Object.keys(window)` and
    `Object.keys(navigator)` must be byte-identical to a stock `content_shell`, and every
    touched accessor must still report `[native code]`.
17. **Stock fallback.** With no `CAMOU_CONFIG` set at all, every value in this spec must
    equal what stock `content_shell` reports. Run the full suite twice, once configured
    and once bare.

## 7. Open decisions

**Font metric jitter: in SP4 or its own SP?** Camoufox spent 55KB of patch on this across
`measureText`, layout, `OffscreenCanvas` and the graphics layer, because glyph advances
leak through many independent code paths and each must be jittered consistently or the
jitter itself becomes the signal. Bundling it into SP4 makes SP4 unshippable for weeks.
*Recommendation: SP4 covers font enumeration and probe blocking; metric jitter becomes
SP4b with its own spec.* Enumeration alone closes the common case, and a partial,
inconsistent jitter is worse than none.

**WebRTC: patch the vendored library or use the existing policy?** Patching
`//third_party/webrtc` gives true address substitution but re-opens on every Chromium roll.
`--force-webrtc-ip-handling-policy=default_public_interface_only` needs no patch and stops
the real local address leaking, but cannot present a chosen address.
*Recommendation: ship the policy flag in SP4, and defer address substitution until SP5
knows the egress IP* — a substituted address that disagrees with the egress IP is worse
than no substitution, so the substitution has no correct value to use until SP5 exists.

**Battery: implement or delete?** Depends entirely on verification item 10. If stock
Chromium already reports constants, the correct output is a registry note, not code.

**Per-context timezone and the V8 isolate.** ICU's default timezone is isolate-wide, and
contexts sharing a renderer process share an isolate. Whether Chromium's process model
guarantees a distinct renderer per browser context in every case that matters is not yet
verified. If it does not, per-context timezone needs either a forced process-per-context
mode or per-context date-cache manipulation. *Recommendation: verify before promising
per-context timezone in any user-facing documentation.* Launch-level timezone is
unaffected and can ship regardless.

**Geolocation lives outside the renderer.** It is served by the device service, where
`ScopeFor(execution_context)` does not exist. Until the per-context store lands,
geolocation is process-global. *Recommendation: accept the limitation and document it;
revisit when the per-context store is designed.*

**`document.body.clientWidth` path unverified.** Camoufox spoofs it; the Chromium call
site was not confirmed in this pass. Confirm before including it in the surface list.

**Do speech voices matter enough to build?** `speechSynthesis.getVoices()` is a real
fingerprinting surface, but a considerably rarer one than fonts or canvas.
*Recommendation: implement enumeration, skip `voices:fakeCompletion` timing until there
is evidence a real detector uses it.*

## 8. Explicitly out of scope

Navigator identity, user-agent string, UA Client Hints, `navigator.languages` and the
`Accept-Language` header are **SP1**. SP4 consumes SP1's claimed-OS helper but never
derives the OS itself.

Automation hiding, `navigator.webdriver`, and CDP invisibility are **SP2**.

WebGL parameters, the canvas noise implementation, and the shared seed helper are **SP3**.
SP4 reuses SP3's helper.

Generating a coherent fingerprint, real device presets, proxy-to-geolocation-to-timezone
consistency, and cross-surface validation are **SP5**. SP4 enforces invariants it is given;
it does not choose values.

Build integration, packaging, and the driver API are **SP6**.

Font metric jitter is deferred to SP4b pending the decision in section 7.

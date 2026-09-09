# SP7 D5: what the silenced component updater no longer delivers (2026-09-09)

`patches/sp7-phone-home.patch` leaves `ConfiguratorImpl::UpdateUrl()` empty, so
no component is ever fetched (`2026-09-09-sp7-phone-home.md` §3). The roadmap
called the fallout "CRLSet + origin-trial keys" and asked for a bundle. Neither
of those is something a page can observe. This measurement lists every
registrant and separates the ones a page *can* see, measures those on the
built `chrome` against a real Chrome, and records the decision.

## 1. The registrants (`chrome/browser/component_updater/registration.cc`, `RegisterComponentsForUpdate`)

Linux desktop build; rows behind a `#if` this build does not take are marked.

| component | page-observable? | note |
|---|---|---|
| RecoveryImproved | no | `IS_WIN || IS_MAC` only |
| WidevineCdm | **yes** — but not via D5 | `ENABLE_WIDEVINE_CDM_COMPONENT` is off here: `enable_widevine = false` (unbranded, `third_party/widevine/cdm/widevine.gni:14-20`). Restoring the updater would not deliver it. A5 packaging + licensing item |
| SubresourceFilter | **yes**, on flagged sites | ad-blocking ruleset; a page on a "better ads" violator sees requests blocked in real Chrome, not here |
| OnDeviceHeadSuggest | no | omnibox |
| OptimizationHints | no | `optimization_guide` hints; affects prefetch/preload heuristics, not page state |
| TrustTokenKeyCommitments | edge | Private State Tokens key commitments; `document.hasPrivateToken` on issuers only |
| PrivateVerificationTokens | edge | same family |
| FirstPartySets | edge | Related Website Sets; changes `requestStorageAccess` outcomes for listed sets only |
| PrivacySandboxAttestations | edge | gates Topics / Protected Audience calls for unattested sites |
| ActorSafetyLists | no | |
| HistorySearchStrings | no | |
| SSLErrorAssistant | no | interstitial copy |
| Indigo | no | |
| FileTypePolicies | no | download UI (`safe_browsing_mode = 1` here) |
| CRLSet | no | revocation state is not observable from a page |
| OriginTrials | edge | revoked-token list; only matters for a token Google has since revoked |
| MediaEngagementPreload | **yes**, on listed sites | autoplay-with-sound allowed on high-engagement origins in real Chrome; `play()` rejects here |
| PKIMetadata | no | CT log list + Chrome Root Store update |
| SafetyTips, CrowdDeny | no | UI |
| SmartDim, AppProvisioning, chrome-app allowlist | no | ChromeOS only |
| **Hyphenation** | **yes**, everywhere | `USE_MINIKIN_HYPHENATION` is `!is_apple` (`third_party/blink/public/public_features.gni:13`): Linux and Windows get `hyphens: auto` dictionaries *only* from the `hyphen-data` component. Measured below |
| DictationConnector, IwaKeyDistribution, ZxcvbnData | no | |
| RealTimeUrlChecksAllowlist | no | Android only |
| CommerceHeuristics | no | |
| TranslateKit + language packs | no | on-device translation (`enable_on_device_translation = true`) — UI-triggered |
| AmountExtractionHeuristicRegexes | no | autofill |
| WasmTtsEngine | edge | `speechSynthesis.getVoices()` on platforms with no native voices; sp4-voices already owns that surface |
| CaptchaProvider, PlatformRuntime | no | |

**Baseline caveat.** A real Chrome fresh profile also has none of these until
its first update check, which the phone-home RED table put at 0.0–0.7 s after
launch with CRX downloads following. So the tell is against a Chrome that has
been up for seconds, i.e. every real Chrome a site meets.

## 2. Measured (`scripts/measure_sp7_components.py`)

Both probes run on a loopback page (EME is `[SecureContext]`; headless
chrome's initial `about:blank` has `requestMediaKeySystemAccess` undefined).

| probe | this `chrome` (Linux, updater silenced) | Google Chrome 151.0.7922.138 macOS, headless, same page |
|---|---|---|
| `hyphens:auto` vs `manual` — `scrollWidth` of a 60 px box holding "extraordinarily supercalifragilistic" | auto **152**, manual 152 → no hyphenation | auto **60**, manual 119 → hyphenated |
| `requestMediaKeySystemAccess('com.widevine.alpha')` | `NotSupportedError` | `granted` |
| `'org.w3.clearkey'` (control, built in) | `granted` | `granted` |

The macOS Chrome hyphenates through CoreText, not the component, so its row
proves what a page expects of "Chrome", not that the component path works; a
Windows/Linux real-Chrome capture is the B2-style follow-up. The hyphenation
row is the D5 tell: any page can put a long word in a narrow `hyphens:auto`
box and read `scrollWidth`.

## 3. Decision

- **The updater stays off.** Every registrant reaches the network through the
  one choke (`UpdateUrl()`, and `PingUrl()` returns `UpdateUrl()` so pings are
  covered too).
- **Bundling mechanism** (A5, packaging): restore `RegisterComponentsForUpdate()`
  (the `chrome_browser_main.cc` hunk is not load-bearing — phone-home §3),
  keep the choke, and pre-seed payloads into the profile's component
  directory so each installer's `ComponentReady` fires from disk with every
  update check failing `MISSING_URLS` before a socket. Not done today: with no
  payload to load, flipping registration is a rebuild plus a 75 s verify that
  measures nothing.
- **Payloads worth seeding, by page visibility:** `hyphen-data` first
  (layout tell on every page), then MediaEngagementPreload and
  SubresourceFilter (site-specific). Widevine is not a seeding candidate on
  this build (GN off; licensing).
- **CRLSet / PKIMetadata / OriginTrials** are security hygiene, not tells;
  seed them in the same pass because the mechanism is the same, refresh them
  per milestone alongside the pin.

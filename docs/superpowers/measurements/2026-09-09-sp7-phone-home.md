# SP7 phone-home measurement (2026-09-09)

Checkout HEAD `a727b57805`, `out/Default` `chrome` (component build, rebuilt
this morning with `disable_fieldtrial_testing_config = true`). This is SP7 §3's
correlation-leak half — the callouts that carry a per-install identifier or
otherwise link two sessions meant to be unrelated — measured rather than
assumed, then closed with the smallest lever per caller.

---

## 1. Method: netlog, not a proxy

`chrome --headless --user-data-dir=<fresh> --log-net-log=<file>
--net-log-capture-mode=Default about:blank` for 75 s, then parse the netlog's
`REQUEST_ALIVE` events (each carries the URL and the traffic-annotation hash).
A netlog records *intent to connect* regardless of DNS or TLS outcome, so a
box with no route still reports the attempt; and the annotation hash maps each
request to the code that issued it, which is what turns a host list into a
lever list. `scripts/verify_sp7_phonehome.py` automates exactly this.

## 2. RED — what a fresh headless `chrome` does in 75 s on `about:blank`

| t | host | path | annotation | caller (read from the tree) |
|---|---|---|---|---|
| 0.0 s | `clients2.google.com` | `/time/1/current` | 46188932 | `NetworkTimeTracker` (`kNetworkTimeServiceQuerying`, ENABLED on desktop, `network_time_tracker.cc:65`) |
| 0.0 s | `redirector.gvt1.com` → `r6---sn-….gvt1.com` | `/edgedl/chrome/dict/en-us-10-2.bdic` | 117649486 | `SpellcheckHunspellDictionary::InitializeDictionaryLocationComplete` → `DownloadDictionary` (`spellcheck_hunspell_dictionary.cc:425-428`) |
| 0.0 s, 2.0 s, then every ~1.5 s from 59.8 s | `update.googleapis.com` | `/service/update2/json` (×12) | 54845618 | component updater, registered by `ChromeBrowserMainParts` (`chrome_browser_main.cc:1946-1949`, gated only on `--disable-component-update`) |
| 0.7 s, 60–72 s | `edgedl.me.gvt1.com` | `/edgedl/release2/chrome_component/…` and `/edgedl/diffgen-puffin/…` (×10) | 54845618 | the same updater downloading CRXs (sslErrorAssistant among them) |
| 0.0 s | `accounts.google.com` | `/ListAccounts?…source=ChromiumBrowser` | 35565745 | `BtmBrowserSigninDetector` (`btm_browser_signin_detector.cc:39`) → `IdentityManager::GetAccountsInCookieJar()` → `GaiaCookieManagerService::ListAccounts()` on the stale fresh-profile jar (`kAvoidAutoTriggerListAccountsOnStale` DISABLED, `signin_switches.cc:90`). First attributed from the annotation to `AccountReconcilor::StartReconcile` under DICE; the round-1 rebuild with DICE off still showed the host, which is what forced the re-read (§5) |
| 0.0 s | `www.google.com` | `/async/folae?…client_locale=en-US&client_country=ZZ` | 109231476 | omnibox `AimEligibilityService` (`kAimEnabled` + `kAimServerRequestOnStartupEnabled`, both ENABLED, `aim_eligibility_service_features.cc:11,35`) |
| 1.9 s | `android.clients.google.com` | `/checkin` | 65957842 | GCM `GCMClientImpl` checkin — carries the persistent android id |
| 2.4 s ×3, 23.7 s, 30.2 s, 67.8 s | `android.clients.google.com` | `/c2dm/register3` (×6) | 61656965 | GCM app registrations following the checkin (`GCMDriverDesktop::EnsureStarted`, `gcm_driver_desktop.cc:1188`) |

**Absent, and why (read from the tree, not assumed):**

- **UMA / crash upload.** `ChromeCrashReporterClient::GetCollectStatsConsent()`
  (`chrome_crash_reporter_client.cc:173-201`) returns false whenever
  `GOOGLE_CHROME_BRANDING` is off; `ChromeMetricsServiceAccessor::
  IsMetricsAndCrashReportingEnabled` reads `kMetricsReportingEnabled`, default
  false. Crashpad still *writes* dumps locally (`crashpad.cc:250-262`: dumping
  unconditional, upload consent-gated). No lever needed; the spec's D4 names
  `enable_crash_reporter` / `enable_reporting` as unverified GN args — the
  first does not exist upstream and the second (`net/features.gni:36`) is the
  W3C Reporting API, **page-observable, do not touch**.
- **Variations seed.** Off unbranded (`2026-09-09-sp7-fieldtrial-config.md` §4).
- **Safe Browsing, Domain Reliability, policy fetch, DoH probes.** Nothing in
  75 s on `about:blank`. Not disproven for longer windows or real navigation;
  each gets its own measurement before a lever (rule: measure first).

## 3. Levers — one per caller, smallest that holds without driver discipline

All nine are source edits (no GN arg exists for any of them); together they
form `patches/sp7-phone-home.patch`. Six were found from the RED table; the
last three only appeared once the first six were built and the verify re-run —
the measurement's own "measure, then measure again" discipline. Each prefers a *default* the tree already
knows how to be in (policy-disabled, feature-off, offline) over a new code
path, so the resulting state is one real Chrome installs also occupy.

| caller | lever | file |
|---|---|---|
| component updater | never call `RegisterComponentsForUpdate()`; `ShouldInstallSodaDuringPostProfileInit` → false. **Not load-bearing** once the `UpdateUrl()` choke below is in (the choke alone stops every check); kept for the "nothing registered at all" intent. A rebaser who loses this hunk loses no measured behaviour | `chrome/browser/chrome_browser_main.cc` |
| GCM | `GCMDriverDesktop::EnsureStarted` returns `GCM_DISABLED` while `gcm_started_` is false (which it now always is) — the result policy-disabled GCM already produces | `components/gcm_driver/gcm_driver_desktop.cc` |
| ListAccounts | `ComputeAccountConsistencyMethod` returns `kDisabled` instead of `kDice` — the `BrowserSignin=Disabled` state | `chrome/browser/signin/account_consistency_mode_manager.cc` |
| network time | `kNetworkTimeServiceQuerying` default → DISABLED | `components/network_time/network_time_tracker.cc` |
| AIM eligibility | `kAimEnabled` default → DISABLED (`:326` gates every request) | `components/omnibox/browser/aim_eligibility_service_features.cc` |
| spellcheck dictionary | drop the `DownloadDictionary` branch in `InitializeDictionaryLocationComplete`; `RetryDownloadDictionary` (a user action) untouched | `chrome/browser/spellchecker/spellcheck_hunspell_dictionary.cc` |
| component updater, the shared choke | `ConfiguratorImpl::UpdateUrl()` returns `{}` unless `--component-updater=url-source` is set; `update_client` then fails every check with `ProtocolError::MISSING_URLS` (`update_checker.cc:171`) before a socket opens; `PingUrl()` returns `UpdateUrl()` (`configurator_impl.cc:100-103`), so pings share the choke. Found by the first GREEN attempt: with registration removed, on-demand registrants (IWA key distribution, optimization guide, on-device translation — `iwa_key_distribution_component_installer.cc:47-51` even documents ignoring the switch in tests) still produced 3 `update2/json` checks and 1 CRX download | `components/component_updater/configurator_impl.cc` |
| ListAccounts, the second trigger | `IdentityManager::OnNetworkInitialized` fetches `ListAccounts` as soon as the network is up when `kAvoidAutoTriggerListAccountsOnStale` is on (`identity_manager.cc:458-467`). Removed; the cookie-change trigger stays | `components/signin/public/identity_manager/identity_manager.cc` |
| ListAccounts, the trigger that actually fired | `kAvoidAutoTriggerListAccountsOnStale` is DISABLED by default (`signin_switches.cc:90`), so `IdentityManager::GetAccountsInCookieJar()` calls `GaiaCookieManagerService::ListAccounts()` on a stale jar and fetches; `BtmBrowserSigninDetector` does that at profile start (`btm_browser_signin_detector.cc:39`). The edit above sat under the same feature and never ran — the third GREEN attempt still showed `{accounts.google.com: 1}`. Flipped the feature to ENABLED: the jar is read from cache and only an explicit trigger fetches | `components/signin/public/base/signin_switches.cc` |

**Consequences recorded, not hidden:**

- With no component updater, **CRLSet, sslErrorAssistant, origin-trial keys
  and the other component payloads are never delivered.** SP7 D5 (bundle
  milestone-matched data at build time) is now the open item it always was,
  with the concrete list of what the updater fetched in §2 as its input.
- No Hunspell dictionary means spellcheck is inactive for the UI language in
  the fork until SP6b bundles `.bdic` files. Not page-observable.
- DICE off also means no `X-Chrome-Connected` / Dice request headers on
  Google properties — the same as an enterprise profile with sign-in
  disabled. Network-visible to Google only.

## 4. Verification (`scripts/verify_sp7_phonehome.py`)

| # | assertion | RED (measured) | GREEN |
|---|---|---|---|
| P1 | external host set in 75 s is `{}` | 7 hosts (the `r6---…gvt1.com` redirect target is a second run's variance) | `{}` |
| P2 | the netlog holds ≥ 1 loopback request — the page is navigated to a local echo server right after launch so chrome itself issues one (the DevTools `/json/version` poll is inbound and never appears; the first draft assumed it would and P2 went FAIL on the RED run, which is exactly what a presence guard is for) | 3 | ≥ 1 |
| P3 | control: `navigator.hardwareConcurrency` override still works on this `chrome` | 8 | 8 |

## 5. Result (applied + verified 2026-09-09)

Four RED→GREEN rounds on the `chrome` target, each a rebuild of a handful of
steps (82, 12, 2) because the levers are leaf `.cc` edits in a component build:

| round | levers in the binary | P1 external hosts in 75 s |
|---|---|---|
| RED | none | `accounts.google.com 1, android.clients.google.com 7, clients2.google.com 1, edgedl.me.gvt1.com 15, redirector.gvt1.com 1, update.googleapis.com 17, www.google.com 1` |
| 1 | six from the RED table | `accounts.google.com 1, edgedl.me.gvt1.com 1, update.googleapis.com 3` |
| 2 | + updater URL choke, + `OnNetworkInitialized` | `accounts.google.com 1` |
| 3 | + `kAvoidAutoTriggerListAccountsOnStale` on | **`{}`** — P1 PASS, P2 PASS (3 loopback), P3 PASS |

Rounds 1 and 2 are the measurement earning its keep: the annotation table
named six callers, the tree had three more behind them (an on-demand updater
path with no `RegisterComponentsForUpdate` in it, and two ListAccounts
triggers, one of which was dead under a feature the other lived under). A
verify that had asserted "the six hosts are gone" instead of "the set is
empty" would have passed after round 1 and shipped a leak.

`patches/sp7-phone-home.patch`: 9 files, all `//chrome` and `//components`,
none owned by an earlier patch; applied last in `scripts/apply.sh`.
Round-trip (revert the nine, `git apply --3way`, diff md5 identical) and the
chrome-dependent regressions (`verify_sp7_fieldtrial`, `verify_sp1a_chrome`,
`verify_sp2`, `verify_sp2b`) are recorded in the plan's Task 5 and the
ledger.

**Still open, named:** SP7 D5 — measured and decided in
`2026-09-09-sp7-components.md` (the page-visible loss is `hyphen-data`, not
CRLSet; pre-seeding is an A5 item); longer windows and real navigation (Safe Browsing
lookups, DoH probes, `google.com` cookie-change ListAccounts are all
un-measured beyond 75 s on `about:blank`); the `X-Client-Data` header (no
seed, no ids — but assert it on a navigation to a Google host under B1);
`content_shell` is not covered by this patch (it links none of these
subsystems) and needs no lever.

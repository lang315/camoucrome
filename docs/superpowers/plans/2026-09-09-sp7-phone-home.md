# SP7 phone-home Implementation Plan (executed 2026-09-09)

> **For agentic workers:** this plan was executed inline the same day it was written, RED-first, with the measurement doc as the brief. It is kept as the record of the task sequence and the deviations; a re-run on a new pin follows the same steps.

**Goal:** A fresh headless `chrome` on `about:blank` makes zero outbound requests to non-loopback hosts in 75 s.

**Architecture:** One netlog-based verify (`scripts/verify_sp7_phonehome.py`) is the RED/GREEN instrument; each caller it exposes gets the smallest source-level lever that puts the tree in a state it already knows (feature off, policy-disabled, offline), never a driver switch. The levers form one patch, `patches/sp7-phone-home.patch`, applied last in `scripts/apply.sh`.

**Tech Stack:** `--log-net-log` parsing, `scripts/lib_shell.py`, `scripts/echo_server.py`, the WSL box (`runwsl`, siso).

**Measurement basis:** `docs/superpowers/measurements/2026-09-09-sp7-phone-home.md`.

## Global Constraints

- No page-visible change: every lever is browser-process behaviour. `enable_reporting` (W3C Reporting API) is page-observable and stays untouched.
- RED-first: the verify goes red on the pre-change `chrome` (7 hosts) before any edit; every rebuild is followed by a re-run, and a residual host is a new lever, not a waived row.
- Assert presence before absence: P2 (a loopback request the verify itself provokes) guards P1's empty set.
- Patch round-trip before commit; secret-scan; commits local, push on the user's word.

---

### Task 1: RED — the instrument

- [x] Write `scripts/verify_sp7_phonehome.py` (P1 external host set, P2 loopback presence, P3 config-layer control), push, run on the current `chrome`.
  - First draft's P2 assumed the DevTools `/json/version` poll would appear in the netlog. It is inbound; it does not. Fixed by navigating the page to `echo_server` after launch. RED run: P1 FAIL (7 hosts), P2 PASS (3), P3 PASS.

### Task 2: first six levers (from the RED table's annotation → caller mapping)

- [x] `chrome_browser_main.cc`: never `RegisterComponentsForUpdate()`; SODA install false.
- [x] `gcm_driver_desktop.cc`: `EnsureStarted` → `GCM_DISABLED` while `gcm_started_` is false.
- [x] `account_consistency_mode_manager.cc`: `kDice` → `kDisabled`.
- [x] `network_time_tracker.cc`: `kNetworkTimeServiceQuerying` → DISABLED.
- [x] `aim_eligibility_service_features.cc`: `kAimEnabled` → DISABLED.
- [x] `spellcheck_hunspell_dictionary.cc`: no `DownloadDictionary` on init.
- [x] Rebuild `chrome` (82 steps), re-run: residual `{accounts.google.com: 1, update.googleapis.com: 3, edgedl.me.gvt1.com: 1}`.

### Task 3: the two callers the first six missed

- [x] `configurator_impl.cc`: `UpdateUrl()` returns `{}` unless a `url-source` override is set — the choke every registrant shares (on-demand registrants bypass `RegisterComponentsForUpdate`).
- [x] `identity_manager.cc`: drop the `OnNetworkInitialized` `ListAccounts()`.
- [x] Rebuild (12 steps), re-run: residual `{accounts.google.com: 1}`.

### Task 4: the ListAccounts trigger that actually fired

- [x] Read: `kAvoidAutoTriggerListAccountsOnStale` is DISABLED by default (`signin_switches.cc:90`), so `IdentityManager::GetAccountsInCookieJar()` calls `ListAccounts()` on a stale jar, and `BtmBrowserSigninDetector` does that at profile start (`btm_browser_signin_detector.cc:39`). The Task 3 `identity_manager.cc` edit sat under the same feature and never ran.
- [x] `signin_switches.cc`: `kAvoidAutoTriggerListAccountsOnStale` → ENABLED (keeps the Task 3 edit meaningful: with the feature on, upstream would fetch in `OnNetworkInitialized`).
- [x] Rebuild (2 steps), re-run: `{}` — P1/P2/P3 PASS.

### Task 5: extract, round-trip, regress, record

- [x] `git diff` the nine files → `patches/sp7-phone-home.patch`; append to `scripts/apply.sh` PATCHES (last).
- [x] Round-trip (APPLY_RC=0, diff md5 identical before/after, rebuild 87 steps, phone-home 3/3): `git checkout HEAD -- <nine files>`, `git apply --3way patches/sp7-phone-home.patch`, `git diff` byte-identical to the pre-revert state, rebuild reports 0 or a relink, verify still GREEN.
- [x] Regression on the rebuilt `chrome` (all PASS, rc=0): `verify_sp1a_chrome.py`, `verify_sp2.py`, `verify_sp2b.py`, `verify_sp7_fieldtrial.py`.
- [x] Measurement §5, completion roadmap A1 #3/#4, README, ledger; commit; push on the user's word.

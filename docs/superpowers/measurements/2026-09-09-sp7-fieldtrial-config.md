# SP7 field-trial testing config measurement (2026-09-09)

Target: checkout HEAD `a727b57805`, `out/Default` (content_shell,
`is_component_build`). Source facts below were first read from Chromium `main`
(chrome/VERSION 155.0.8049.0) over gitiles while the build box was offline,
then **confirmed at the pin on 2026-09-09 (plan Task 0): every cited line
number is identical at `a727b57805`.** Three Gate 0 findings beyond the line
check:

- `content_shell` links `content/test/setup_field_trials.cc` for real:
  `content/shell/BUILD.gn:359` depends on `//content/test:test_support`, whose
  `public_deps` (`content/test/BUILD.gn:522`) carry `:setup_field_trials`
  (`content/test/BUILD.gn:54-60`). Not just a header include.
- `content/shell` contains no `VariationsService(` construction (only
  `RegisterPrefs`), so §4's "never constructs one" holds.
- `VariationsServiceClient::ExitWithMessage`
  (`components/variations/service/variations_service_client.cc:97-100`) is
  `puts(message); exit(1);` — the message goes to **stdout**, which
  `lib_shell.launch()` sends to `DEVNULL`. F2 therefore asserts the exit
  (`launch()` raising `exited during startup, code 1`), not the text.
- `out/Default/args.gn` had no `disable_fieldtrial_testing_config` line
  (the `false` shown by `gn args --list` was the default); the arg is appended.

This is the field-trial half of **SP7** — the item the SP7 spec calls "the
highest-priority item in this section despite being the least discussed"
(D3, RESOLVED 2026-08-27). Like the codec slice it is a build-configuration
change, not a Blink patch, and it re-opens no decision.

---

## 1. The tell being closed (SP7 §4.2, D3)

An unbranded Chromium build applies `testing/variations/fieldtrial_testing_config.json`
at startup. Real Chrome does not (it applies a fetched seed instead). The fork's
feature state therefore sits at a **third position** matching neither seeded
Chrome nor default Chrome — page-observable indirectly through feature
availability, and made worse by the fact that the testing config is a public,
per-milestone file: a detector can know exactly which feature set a
"Chromium-with-testing-config" build exposes.

The testing config on `main` holds 1,119 studies, 573 of them with a `linux`
platform entry, toggling 718 distinct features on Linux. None carries a
`google_web_experiment_id`, so it does not produce an `X-Client-Data` header
by itself — the tell is feature state, not a header.

## 2. The lever — compile it out (SP7 §4.1 "prefer compiling out")

`components/variations/service/BUILD.gn:8-32` (main):

```gn
declare_args() {
  # Set to true make a build that disables activation of field trial tests
  # specified in testing/variations/fieldtrial_testing_config.json.
  disable_fieldtrial_testing_config = false
  force_enable_fieldtrial_testing_config = false
}
fieldtrial_testing_enabled =
    force_enable_fieldtrial_testing_config ||
    (!disable_fieldtrial_testing_config && !(is_android && is_chrome_branded))
buildflag_header("buildflags") {
  flags = [ "FIELDTRIAL_TESTING_ENABLED=$fieldtrial_testing_enabled" ]
}
```

`components/variations/service/variations_field_trial_creator.cc` (main):

- `:132-156` — `ShouldUseFieldTrialTestingConfig()` exists only under
  `#if BUILDFLAG(FIELDTRIAL_TESTING_ENABLED)`. In a non-Chrome-branded build it
  returns true unless `--disable-field-trial-config` or
  `--variations-server-url` is passed (`:151-153`).
- `:328-342` — `SetUpFieldTrials()`: under the buildflag, applies the config
  when `ShouldUse…` is true; **without** the buildflag, passing
  `--enable-field-trial-config` calls `client_->ExitWithMessage("--%s was
  passed, but the field trial testing config was excluded from the build.")`.
- `:609-616` — `ApplyFieldTrialTestingConfig()` logs
  `VLOG(1) << "Applying FieldTrialTestingConfig";` then associates the config.
  This line is the RED/GREEN signal: it is emitted on every startup of the
  current build (with `--vmodule=variations_field_trial_creator=1`) and cannot
  exist in a build with the flag set, because the function is compiled out.

**GN arg, not the switch.** `--disable-field-trial-config` achieves the same
runtime state but is driver discipline: every launcher that forgets it (stock
Playwright forgets it) silently reverts to the third position. The GN arg makes
the position a property of the binary. This is the same reasoning the codec
slice used for `proprietary_codecs`, and it persists in `settings/build-args.gn`
alongside it.

## 3. `content_shell` DOES apply the testing config — measurable here

The roadmap assumed most of SP7 needs the `chrome` target. Not this item:

- `content/shell/app/shell_main_delegate.cc:442` →
  `browser_client_->CreateFeatureListAndFieldTrials()`
- `content/shell/browser/shell_content_browser_client.cc:901-904` →
  `SetupFieldTrials()` (from `content/public/test/setup_field_trials.h`)
- `content/test/setup_field_trials.cc:75-160` builds a
  `variations::VariationsFieldTrialCreator` and calls `SetUpFieldTrials()` on
  it; line 100 says it in so many words: *"Needed so that content_shell can use
  fieldtrial_testing_config."*

So the same `SetUpFieldTrials` → `ShouldUseFieldTrialTestingConfig` →
`ApplyFieldTrialTestingConfig` chain runs in `content_shell` as in `chrome`
(`ChromeFeatureListCreator` → same creator class), and one GN arg closes both.
Confirming the VLOG line appears on the current `content_shell` is the RED.

## 4. The seed fetch — already off; verify, do not patch

`components/variations/service/variations_service.cc:269-288` (main):

```cpp
// Variations seed fetching is only enabled in official Chrome builds, if a URL
// is specified on the command line, and for testing.
bool IsFetchingEnabled() {
#if BUILDFLAG(GOOGLE_CHROME_BRANDING)
  ...
#else
  if (!HasSwitch(switches::kVariationsServerURL) && !g_should_fetch_for_testing)
    return false;
#endif
  return true;
}
```

The fork is not `is_chrome_branded` (conventions: it "is not the mechanism"), so
no seed is fetched unless a driver passes `--variations-server-url`. Two
consequences recorded rather than patched:

- **Driver constraint (SP6b):** never pass `--variations-server-url`. It would
  both start seed fetches AND (via `ShouldUse…:153`) change the testing-config
  answer.
- `content_shell` never constructs a `VariationsService` at all
  (`setup_field_trials.cc` builds only the creator with a null URL loader
  factory, `:53-55`), so the fetch path is unreachable there. The `chrome`
  target's `IsFetchingEnabled()==false` is verified under B1 of the completion
  roadmap, together with the rest of SP7.

## 5. Verification plan (`scripts/verify_sp7_fieldtrial.py`)

All rows read the per-launch stderr capture (`lib_shell.STDERR_LOG`, O_APPEND
since `806ac5f`) or the launch exit path. Flags are passed as `extra_flags`
(which REPLACES `SHELL_FLAGS`, so `--ozone-platform=headless` must be repeated).

| # | Launch | RED (current build) | GREEN (flag set) |
|---|---|---|---|
| F1 | `--ozone-platform=headless --enable-logging=stderr --v=0 --vmodule=variations_field_trial_creator=1` | stderr contains `Applying FieldTrialTestingConfig` (expected COUNT 1) | count 0 |
| F2 | same + `--enable-field-trial-config` | starts normally (DevTools port answers) | `launch()` raises `exited during startup, code 1`. The exclusion message (`was passed, but the field trial testing config was excluded from the build`) is printed by `ExitWithMessage` via `puts()` to stdout, which the harness discards, so the exit code is the observable (Gate 0 finding above) |
| F3 | control: `CAMOU_CONFIG={"navigator.hardwareConcurrency":8}` with SHELL_FLAGS | `navigator.hardwareConcurrency === 8` | same — proves the binary under test is the fork and the rebuild changed nothing else |
| F4 | probe capability: F1's launch also asserts a known-present line (`DevTools listening on`) | present | present — assert presence before absence (conventions table: "absence-asserting criteria pass when the surface disappears") |

F1 is the count assertion; F2 is the expected-failure assertion. A page-visible
spot check (a feature the pin's testing config flips on Linux, e.g. an API
gated by a `base::Feature` with `FEATURE_DISABLED_BY_DEFAULT`) is worth adding
only if Gate 0 finds one whose default differs from its testing-config value at
the pin; it is not required for the slice to be measured.

## 6. Persistence

`settings/build-args.gn` gains an SP7 field-trial section:

```gn
# --- SP7: field-trial testing config (SP7 §4.2 / D3, resolved 2026-08-27) ---
# An unbranded build applies testing/variations/fieldtrial_testing_config.json at
# startup; real Chrome does not. That puts the fork's feature state at a third
# position matching neither seeded nor default Chrome, and the testing config is
# a public per-milestone file. Compile it out (FIELDTRIAL_TESTING_ENABLED=0) so
# the position is a property of the binary, not of whether a driver remembered
# --disable-field-trial-config. Verified by scripts/verify_sp7_fieldtrial.py.
disable_fieldtrial_testing_config = true
```

No `patches/` change. No `additions/` change. No key.

## 7. Scope summary

- In: the GN arg, the verify, the persisted args, the docs.
- Out (own items in the completion roadmap A1): crash reporting, metrics,
  component updater, Safe Browsing, API keys, CRLSet — `//chrome`-only,
  B1-gated. The seed fetch is recorded as measured-off (§4), not patched.
- Rebuild cost: `components/variations/service` + `content/test` + dependents
  of `buildflags.h` — expect a few hundred steps, not the 43-minute ffmpeg
  rebuild the codec slice paid.

## 8. Result (applied + verified 2026-09-09)

**Lever applied.** `disable_fieldtrial_testing_config = true` appended to
`out/Default/args.gn`; `gn gen` regenerated
`gen/components/variations/service/buildflags.h` to
`FIELDTRIAL_TESTING_ENABLED() (0)` (it read `(1)` before). `content_shell`
rebuilt (102 steps in the first pass, `variations_field_trial_creator.o`
recompiled 06:32:21, binary relinked). Persisted in `settings/build-args.gn`.

**RED (pre-change binary, 2026-09-07 build):**
```
note: F1: 'Applying FieldTrialTestingConfig' count = 1 (expect 0; RED build 1)
note: F2: browser started normally with --enable-field-trial-config (RED build behaviour)
note: F3: hardwareConcurrency = 8 (expect 8)
F1: FAIL   F2: FAIL   F3: PASS   F4: PASS   EXIT=1
```

**GREEN (rebuilt content_shell):**
```
note: F1: 'Applying FieldTrialTestingConfig' count = 0 (expect 0; RED build 1)
note: F2: content_shell exited during startup, code 1
note: F3: hardwareConcurrency = 8 (expect 8)
F1: PASS   F2: PASS   F3: PASS   F4: PASS
```

**Control by mutation.** Flipping the arg back to `false` and rebuilding
(14 steps) restored the RED shape exactly (F1 count 1, F2 starts); flipping
to `true` and rebuilding restored GREEN. The final binary is the `true` one
(`content_shell` 06:47:43).

**Regression sweep — every `verify_*.py` on the rebuilt binary** (35 scripts,
`verify_webrtc_ii_fakeip.py` excluded as a rejected-slice RED record):
34 exit 0, **1 exit 1: `verify_sp1a.py` criterion 7** ("no property was added
to navigator or window"). Investigated, not waved through:

| delta vs the 2026-08-27 baseline | cause | attribution |
|---|---|---|
| `window.queryLocalFonts` gone | upstream: `runtime_enabled_features.json5` `FontAccess` status `{default: "stable"}` at `0e8d4a9268` → `{default: ""}` at `a727b57805` | present with the arg `false` AND `true` → the rebase, not this slice. The baseline had been latent-stale since the rebase; nobody had re-run `verify_sp1a.py` on `a727b57805` |
| `Navigator.prototype` gains 13 Protected Audience members (`joinAdInterestGroup`, `runAdAuction`, `protectedAudience`, …) | the testing config's `ProtectedAudienceDeprecation` study disables `Fledge` + `AdInterestGroupAPI` on every platform; compiled defaults (json5 `status: "stable"`) expose them | absent with the arg `false`, present with `true` → this slice |

Everything else in the baseline (UA string, brands, high-entropy values,
request headers, `navigator_keys`) is byte-identical. The baseline
`baselines/content_shell-sp0-stock-ua.json` was recaptured from the final
binary with a `recaptured_2026-09-09` provenance block naming both deltas;
`verify_sp1a.py` is 9/9 on it.

**Rule-2 evidence this produced, stated precisely.** The old baseline came
from an sp0-only binary at `0e8d4a9268`; the new one from the full 25-patch
stack at `a727b57805`. The diff between them is exactly 14 names, every one
attributed to upstream or to the testing config. So across the rebase and 24
further patches, `Object.keys(window)`, `Object.keys(navigator)` and
`Object.getOwnPropertyNames(Navigator.prototype)` gained nothing from the
fork — the strongest rule-2 evidence recorded so far, bounded to those three
lists (it says nothing about `Screen.prototype`, worker scopes, or other
prototypes; B2's stock-build diff stays open for those).

**Which binary ran what.** The full 35-script sweep ran on the first `true`
build (`content_shell` 06:34:39). The control flip rebuilt the same inputs
into the final binary (06:47:43); `verify_sp7_fieldtrial.py`, `verify_sp1a.py`
and the three chrome-dependent verifies ran on that one, the other 31 did
not.

**What the Protected Audience delta means (SP5b finding, not fixed here).**
The compiled default is the "defaults" position SP7 D3 accepted. Whether real
Chrome stable *today* exposes these members depends on the live Finch seed —
the study's name says Google is winding Protected Audience down, so seeded
Chrome may have them off while this build has them on. That is the exact
"defaults ≠ seeded" gap D3 named, and it needs a capture from real Chrome
stable to settle (a `Object.getOwnPropertyNames(Navigator.prototype)` from a
stock Chrome on the claimed OS). Recorded in the completion roadmap as a
measurement item for the feature-state work; no key, no patch invented for it.

**`chrome` target.** Same buildflag, same creator class. The pre-existing
`out/Default/chrome` (built 2026-08-30, before the arg) shows the RED shape
(C1 count 1, C2 starts). After rebuilding `chrome` with the arg (2,915 steps
over three resumed `autoninja` runs; binary 07:16:46) the full script is 7/7:
```
note: C1: 'Applying FieldTrialTestingConfig' count = 0 (expect 0; RED build 1)
note: C2: chrome exited during startup, code 1
F1: PASS  F2: PASS  F3: PASS  F4: PASS  C1: PASS  C2: PASS  C4: PASS   EXIT=0
```
So the arg is verified on both binaries the project ships, and B1 of the
completion roadmap now has a `chrome` built at the pin with the arg in place.

**Seed fetch.** Not exercised here (§4): `content_shell` builds no
`VariationsService`; the `chrome` target's `IsFetchingEnabled()` returns
false unbranded without `--variations-server-url`. Driver constraint recorded
in `settings/build-args.gn`.

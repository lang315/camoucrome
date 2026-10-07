# Tracking observer — follow-ups

Items deliberately left out of phase 1
(`docs/superpowers/specs/2026-10-06-tracking-observer-design.md`). Each gets its
own spec when picked up.

## Out of scope for phase 1

- **V8/Intl hooks (phase 2).** `Intl.DateTimeFormat.prototype.resolvedOptions`,
  the `*.supportedLocalesOf` family and the `Intl.DateTimeFormat` constructor are
  C++ `BUILTIN`s in `v8/src/builtins/builtins-intl.cc` and can carry a trace
  event. `v8/` is a separate git repo, and `apply.sh`, `export.sh`,
  `check_checkout_sync.sh`, `rebuild_branch.sh`, `repin.py` and `upstream.env`
  know only one repo, so phase 2 first extends the change-set tooling to a
  second repo. `Date.prototype.getTimezoneOffset` is a CSA builtin (`TFJ`) and
  stays a blind spot.
- **No new spoofs.** A leak the recon finds opens its own slice; the observer
  only reports.
- **No decoding of the Falco `/ajax/bz` `e` payload.**
- **No automated loops against facebook.com.** Recon on live Meta sites is
  manual, by the owner, in their own account.

## Merge preconditions (before the PR merges)

CI (`build-verify`) builds `~/chromium/src/out/Default` from box branch
`camoucrome/main` and starts with the sync gate, so merging first turns CI red
(sync gate) or runs into its 180-min timeout (every binding regenerates). In
this order:

1. In `~/chromium/src` on the build box, cherry-pick the `observe` commit onto
   `camoucrome/main` (append, subject `observe`), in a window agreed with any
   other session using the box.
2. Rebuild `out/Default` by hand under the build lock (the bindings
   regenerate; a multi-hour build). Confirm a non-zero step count.
3. `scripts/check_checkout_sync.sh` gives `rc=0`.
4. Merge the PR.

`verify_observe.py` stays a visible SKIP in CI until the owner decides to set
`camou_observe = true` in the CI out dir (one more full bindings rebuild there).

## Open

- **V8 fast API calls are not counted.** About 100 canvas-2D/WebGL methods and
  setters on allow-listed interfaces have `[NoAllocDirectCall]` fast paths
  (`make_no_alloc_direct_call_callback_def` and
  `make_attribute_set_nadc_callback_def` in `interface.py`) that skip the
  hooked callback once V8 optimizes a call site; draw and state counts are
  lower bounds. Fix: do not register the fast paths under
  `BUILDFLAG(CAMOU_OBSERVE)`, or hook the fast callbacks too. Prove it with a
  hot-loop verify row (for example `fillRect` 100 000 times, exact count) that
  is RED on the current code.
- **Phase 1b: the live dashboard `chrome://camou-observe`.** Designed in the
  spec, not built; the recon used the report.
- **`d-pointer-touch.patch` lacks a `//components/camoucfg` dep in
  `third_party/blink/renderer/core/exported/BUILD.gn`.** It includes camoucfg
  headers from `web_view_impl.cc`, so `gn check` on that directory fails (3
  errors, also on `camoucrome/main`). Pre-existing, found while checking the
  observe slice; a separate fix.

## After the facebook recon (2026-10-07)

- Instagram/Threads recon pending (arm 1 ran for both; arms 2-4 not yet); the phone-home finding (`passwordsleakcheck-pa.googleapis.com` at login, `content-autofill.googleapis.com` in every arm) goes to SP7; per-script attribution is done (phase 1c). Details: `docs/superpowers/measurements/2026-10-07-fb-observe.md`.

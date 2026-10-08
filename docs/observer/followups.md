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

## Landing order for a slice that changes the bindings

CI (`build-verify`) builds `~/chromium/src/out/Default` from box branch
`camoucrome/main` and starts with the sync gate, so a bindings change lands on
the box first: amend or append the commit in `~/chromium/src` (in a window
agreed with any other session using the box), rebuild `out/Default` by hand
under the build lock, get `scripts/check_checkout_sync.sh` `rc=0`, then merge.
Since 2026-10-08 CI's out dir sets `camou_observe = true` and runs
`verify_observe.py`.

## Open

- **The `Emit` comment in the observe patch is inaccurate.** It says the V8
  heap "must not change" inside fast API calls; V8 allows allocation there
  (`Utf8LengthV2`/`WriteUtf8V2` may flatten). Reword it at the next amend of
  the `observe` commit.
- **Add a hot row from a cross-origin iframe running an external script**, to
  prove fast-call script/origin attribution across realms.
- **Re-run `verify_observe.py --timing` 3-5 times** on the observer build and
  publish a range in the README.
- **Phase 1b: the live dashboard `chrome://camou-observe`.** Designed in the
  spec, not built; the recon used the report.
- **`d-pointer-touch.patch` lacks a `//components/camoucfg` dep in
  `third_party/blink/renderer/core/exported/BUILD.gn`.** It includes camoucfg
  headers from `web_view_impl.cc`, so `gn check` on that directory fails (3
  errors, also on `camoucrome/main`). Pre-existing, found while checking the
  observe slice; a separate fix.

## After the facebook recon (2026-10-07)

- Instagram/Threads recon pending (arm 1 ran for both; arms 2-4 not yet); the phone-home finding (`passwordsleakcheck-pa.googleapis.com` at login, `content-autofill.googleapis.com` in every arm) goes to SP7; per-script attribution is done (phase 1c). Details: `docs/superpowers/measurements/2026-10-07-fb-observe.md`.
- Counts of canvas-2D/WebGL draw and state calls in that recon are lower bounds (V8 fast API calls were not counted before 2026-10-08); re-run arms to get exact counts.

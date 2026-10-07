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

## After the facebook recon (2026-10-07)

- Instagram/Threads recon pending (arm 1 ran for both; arms 2-4 not yet); the phone-home finding (`passwordsleakcheck-pa.googleapis.com` at login, `content-autofill.googleapis.com` in every arm) goes to SP7; per-script attribution is done (phase 1c). Details: `docs/superpowers/measurements/2026-10-07-fb-observe.md`.

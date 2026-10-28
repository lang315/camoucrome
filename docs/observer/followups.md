# Tracking observer — follow-ups

Items deliberately left out of phase 1
(`docs/superpowers/specs/2026-10-06-tracking-observer-design.md`). Each gets its
own spec when picked up.

## Out of scope for phase 1

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
- **Phase 1b: the live dashboard `chrome://camou-observe`.** Designed in the
  spec, not built; the recon used the report. A read-only spike (2026-10-12,
  PR #34) found the page can export a cloned session through its own
  `TraceProcessorStorage` and `json::ExportJson`, the exporter behind phase
  1's `trace.json`.

## After the facebook recon (2026-10-07)

- Instagram/Threads recon dropped by the owner (2026-10-17); facebook re-run with exact counts and Intl in `docs/superpowers/measurements/2026-10-17-fb-observe-intl.md`; unattended re-runs via `observe-auto.ps1`. The phone-home finding (`passwordsleakcheck-pa.googleapis.com` at login, `content-autofill.googleapis.com` in every arm) goes to SP7; per-script attribution is done (phase 1c). Details: `docs/superpowers/measurements/2026-10-07-fb-observe.md`.
- Counts of canvas-2D/WebGL draw and state calls in that recon are lower bounds (V8 fast API calls were not counted before 2026-10-08); the exact counts are in `docs/superpowers/measurements/2026-10-17-fb-observe-intl.md`.

## What the observer cannot say about behaviour (2026-10-28)

An inventory of facebook's behaviour-adjacent reads, from the arm 1 and arm 3 loads of the 156.0.8078.48
recalibration (no input sent, no extra load):

- **Seen** (calls per load, arm 1 / arm 3): `Window.innerWidth` 19 / about 220, `innerHeight` 17 / about 260,
  `Window.matchMedia` 26 / about 120, `Element.getBoundingClientRect` 26 / about 700, `HTMLElement.offsetHeight`
  0 / about 1200, `Navigator.maxTouchPoints` 5 / 1, `Navigator.webdriver` 4 / 1, network state
  (`connection`, `rtt`, `downlink`, `effectiveType`, `onLine`) read in both arms, and `Navigator.deviceMemory`
  about 820 times from one bundle in arm 3. The reading scripts are a handful of content-hashed bundles.
- **Not seen, by construction:** `addEventListener` registrations (by type or at all), `performance.now`,
  `requestAnimationFrame`, timers, clipboard, device motion and orientation, visibility, focus, scroll offsets,
  and the pointer, key, wheel and touch event property reads. They are not on the allow-list, and `v8.callFunction`
  slices carry no listener type. The trace cannot say whether facebook listens to wheel, pointer or keys.
- **Follow-ups (each needs a bindings change, so a box-first landing and an `out\Observe` rebuild):**
  1. count `EventTarget` listener registrations by type and script;
  2. add `Performance.now`, `requestAnimationFrame` and timer rates;
  3. add `Document.visibilityState`/`hidden`/`hasFocus`, `Window.scrollX/scrollY`, `Selection`, `Clipboard`,
     the motion and orientation interfaces, `IntersectionObserver`/`ResizeObserver` constructors;
  4. record the `matchMedia` query string;
  5. field names (not values) of the `/ajax/bz` batch.
- An input arm against facebook is not allowed (2026-10-17 rules), so a listener inventory would answer
  "registered", never "reacts to".

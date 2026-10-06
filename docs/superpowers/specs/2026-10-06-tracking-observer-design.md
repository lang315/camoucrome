# Tracking observer (phase 1) — design

Approved in brainstorming on 2026-10-06. Port of camoufox's Tracking Observer
(`camoufox/docs/observer/README.md`,
`camoufox/docs/superpowers/specs/2026-07-10-tracking-observer-design.md`) to
this fork, followed by a facebook.com / instagram.com / threads recon with it.
Out-of-scope items are tracked in `docs/observer/followups.md`. A live dashboard, `chrome://camou-observe`, is
phase 1b of this spec.

## Goal

An opt-in audit tool that records, per site, **which fingerprint surfaces a
page reads** (API name, real call count, reading origin, top-level site) and
**what it sends back** (requests, cookie names), then a measured answer to
"what do facebook.com / instagram.com / threads actually collect on this
build". Observe-only: nothing is blocked or altered.

## What camoufox shipped, and what carries over

Camoufox puts a C++ `Record()` call in each spoof hook (7 surfaces), pushes into
a mutex-guarded buffer, drains it from a JSWindowActor every 500 ms, collects in
the parent, and renders a `chrome://camoufox` panel; network comes from a
read-only `http-on-modify-request` observer. Its own docs name the gaps:

- **Un-spoofed surfaces are invisible** (deviceMemory, plugins, userAgentData,
  enumerateDevices, battery, connection) — no hook exists where nothing is
  spoofed, and that is exactly where a real value leaks.
- **Workers and OffscreenCanvas are invisible** — the hooks need an owning
  document.
- **Counts are not read counts** — dedup per drain window makes a count
  "windows the surface was active in".
- Rejected there, and still rejected here: a single config-getter chokepoint
  (no origin; `camoucfg::ScopeFor()` ignores its context the same way,
  `additions/camoucfg/blink_scope.h`), a per-read `stderr` write (a timing
  tell), and any page-side JS shim (detectable, poisons the data — and banned by
  this repo's rule 1).

What carries over: observe-only, off by default, attribution by site, a fixed
"not observable" list so silence is never read as safety, memory and disk
hygiene for captured data, a local-first and manual-only stance toward
facebook.com.

## Why Chromium's own tracing, not a port

Chromium 154 already generates a trace event at the entry of every Web IDL
getter, setter and operation: `make_bindings_trace_event` in
`third_party/blink/renderer/bindings/scripts/bind_gen/interface.py:839`, called
from six callback generators, expanding to `BLINK_BINDINGS_TRACE_EVENT`
(`platform/bindings/runtime_call_stats.h:178`) behind the GN arg
`enable_blink_bindings_tracing` (`platform/BUILD.gn`, default
`extended_tracing_enabled = false`). Chromium's tracing service already does
the buffering, the cross-process collection out of sandboxed renderers, and the
file output (`--trace-startup*`, `components/tracing/common/tracing_switches.cc`).
The net stack already logs every request with its initiator and
`site_for_cookies` (`--log-net-log`).

Bindings run in windows and workers alike and do not care whether a surface is
spoofed, so hooking there closes both camoufox blind spots with one patch.

Turning the stock arg on is not enough: it traces every DOM call, millions on a
facebook.com load, and the fingerprinting burst at load is what a ring buffer
evicts or a fill-once buffer truncates after. The stock event also carries no
origin. Hence an allow-listed event of our own, with the origin attached.

Dactyloscoper / the identifiability study (the obvious earlier candidate) is
gone from this tree.

## Architecture

```
page or worker calls an allow-listed Web IDL member
  -> generated binding callback
     -> CAMOU_OBSERVE_TRACE("Navigator.deviceMemory.get", ctx)
        category disabled: one static check, return
        category enabled : instant event {origin, site}  -> Perfetto buffer
browser: --trace-startup ... -> trace.json at exit
browser: --log-net-log=net.json -> every URL_REQUEST_START_JOB
after the session: Cookies sqlite (names only)
scripts/observe_report.py trace.json net.json [--cookies DB] -> per-site markdown
```

### Components

1. **Build gate.** GN arg `camou_observe` (default `false`), declared next to
   `enable_blink_bindings_tracing` in `third_party/blink/renderer/platform/BUILD.gn`
   and exported as `CAMOU_OBSERVE` in the existing `bindings_buildflags` header.
   It is **not** added to `settings/build-args.gn`, because `release-args.gn`
   copies that file verbatim. A dev or observe out dir sets it in its own
   `args.gn`. `scripts/package.py` refuses an out dir whose `args.gn` sets
   `camou_observe = true`, so a release binary never contains the observer.
2. **Trace category.** `disabled-by-default-camou.observe`, registered in
   `base/trace_event/builtin_categories.h`. Disabled-by-default means no
   ordinary trace (DevTools Performance included) ever enables it.
3. **Macro.** `CAMOU_OBSERVE_TRACE(name, execution_context)` in
   `runtime_call_stats.h`, beside `BLINK_BINDINGS_TRACE_EVENT`, which generated
   code already includes. With the flag on it emits a `TRACE_EVENT_INSTANT` with
   two arguments: `origin` (the calling context's security origin) and `site`
   (the top-level site from the context's `StorageKey`). Arguments are computed
   only when the category is enabled; the plan verifies this in the macro
   expansion, not by assumption. With the flag off it compiles to nothing.
4. **Allow-list in the generator.** `interface.py` emits `CAMOU_OBSERVE_TRACE`
   in the same six places as `make_bindings_trace_event`, but only for members
   on the list, each tagged with a group the report uses:

   | Group | Whole interfaces / members |
   |---|---|
   | navigator | Navigator, WorkerNavigator, NavigatorUAData, PluginArray, MimeTypeArray, NetworkInformation, BatteryManager, Permissions, StorageManager, Keyboard, MediaCapabilities |
   | screen | Screen, ScreenOrientation |
   | canvas | HTMLCanvasElement, OffscreenCanvas, CanvasRenderingContext2D, OffscreenCanvasRenderingContext2D |
   | webgl | WebGLRenderingContext, WebGL2RenderingContext |
   | webgpu | GPU, GPUAdapter |
   | audio | BaseAudioContext, AudioContext, OfflineAudioContext, AnalyserNode, AudioBuffer |
   | media | MediaDevices, SpeechSynthesis |
   | webrtc | RTCPeerConnection |
   | fonts | FontFaceSet |
   | layout-probe | `Window.matchMedia`, `Window.devicePixelRatio`, `Window.outer*/inner*/screen*`, `HTMLElement.offsetWidth/offsetHeight`, `Element.getBoundingClientRect/getClientRects` |
   | storage | `Document.cookie`, `Storage.*` |

   Mixin and partial-interface members (`navigator.deviceMemory`,
   `navigator.userAgentData`) are emitted under their host interface's name;
   the plan confirms the generated identifier for each before relying on it.
   The list lives in the patch as one literal; adding an interface is one line.
5. **Network.** `--log-net-log=<file>` in the default capture mode, which drops
   cookies and credentials. The report reads `URL_REQUEST_START_JOB` (url,
   method, initiator, site_for_cookies).
6. **Cookies.** After the session the report reads the profile's `Cookies`
   sqlite: `host_key, name, expires_utc, is_httponly` only. It never selects
   `value` or `encrypted_value`.
7. **Report.** `scripts/observe_report.py trace.json net.json [--cookies DB]`
   prints markdown per top-level site:
   - surface group → API name → call count, split by reading origin (an
     embedded facebook.com frame on another site shows as "facebook.com read
     X on site Y");
   - requests per host, host and path only (query strings carry tokens);
   - cookie names per host;
   - the fixed "Not observable" section (below).

   Raw traces open in ui.perfetto.dev. The live view is phase 1b (below).
8. **Slice.** One new patch, `observe.patch`, last in `patches/series`,
   produced by the usual loop: commit on `camoucrome/main` in the build tree,
   then `scripts/export.sh`.

### Running it

```
chrome --user-data-dir=<fresh profile> \
  --trace-startup=disabled-by-default-camou.observe \
  --trace-startup-format=json --trace-startup-file=<trace.json> \
  --trace-startup-duration=<seconds or the value that means until exit> \
  --log-net-log=<net.json>
```

No new environment variable. The plan confirms the duration semantics and the
buffer size flag against `tracing_switches.cc`.

## Not observable (printed in every report)

- V8 built-ins: `Intl.*` (`resolvedOptions().timeZone`, `supportedLocalesOf`),
  `Date.prototype.getTimezoneOffset`, `Math`. Intl is phase 2
  (`docs/observer/followups.md`); `getTimezoneOffset` is a CSA builtin
  (`TFJ` in `v8/src/builtins/builtins-definitions.h`) and stays blind.
- CSS `@media` rules in stylesheets (only `matchMedia` is seen).
- Font enumeration by layout measurement beyond the listed layout members.
- TLS/JA3, HTTP/2 framing, anything computed server-side.
- Allow-list members are counted, not values: the report says *that* a page
  read `deviceMemory`, not what it got.

## Verification (RED-first)

`scripts/verify_observe.py`, run on `content_shell` (the bindings are shared
with `chrome`; the patched generator is the code under test, and both targets
call it):

- A probe page calls a fixed list exactly K times each: `navigator.userAgent`,
  `navigator.deviceMemory` (un-spoofed), `screen.width`, `canvas.toDataURL`,
  `gl.getParameter`, `matchMedia`, `document.cookie`; a dedicated Worker reads
  `navigator.hardwareConcurrency` K times; `document.title`, which is **not**
  on the list, is read K times.
- Assert, per name, **exactly** K events with `origin` and `site` equal to the
  probe's; the worker events present; `Document.title` absent.
- A cross-site iframe reading `navigator.userAgent`: its events carry the
  iframe's `origin` and the parent's `site`.
- RED first: the same run with a deliberately wrong expectation (K+1) must
  report FAIL before a GREEN run is trusted.
- Off arm: the same probe without `--trace-startup` writes no trace file.
- Build gates: the rebuild reports a non-zero step count; `gn check` and
  `checkdeps.py` pass; `check_additions_build.py` and
  `check_checkout_sync.sh` pass.
- No regression: `build-verify` CI green on a build with `camou_observe = true`
  and tracing off.
- Overhead: `toDataURL` and one navigator getter timed with the category off and
  on, reported in the measurement doc as numbers, not a gate. The observer is
  an audit tool, not a stealth mode, and the README says so.
- `scripts/test_observe_report.py`: the report on a small hand-made
  trace/netlog/cookies fixture, asserting grouping, counts, query stripping and
  that no cookie value column is read.

## Recon: facebook.com, instagram.com, threads

- Vehicle: native `chrome` on the Windows host (D:/camou-win), built from
  `release-args.gn` plus `camou_observe = true` in its own out dir. Launched
  headed with the flags above and nothing else attached: no CDP, no driver.
  The launch is the one a real user makes.
- One fresh profile per site (camoufox measured cookie misattribution when
  profiles were shared).
- Four arms per site: logged-out landing; fresh login; established session,
  about two minutes of feed browsing; a third-party page embedding the Meta
  Pixel or a social plugin, if a public one is found.
- The owner logs in by hand. Tooling never handles credentials.
- Every `/ajax/bz` count is reported with the session's total request count as
  its denominator (camoufox's lesson: a bare zero proves nothing).
- Compared with camoufox's results (`recon_fb_live.json`, `REPORT.md`): what
  the Chromium build sees that the Firefox one could not, un-spoofed surfaces
  and worker reads in particular.
- Output: `docs/superpowers/measurements/2026-10-<dd>-fb-ig-observe.md`, plus an
  operator guide `docs/observer/README.md` (enable, run, read, the
  not-observable list, "silence is not safety", detectability caveat).

## Data handling

- Traces, netlogs and profiles stay on the Windows host or the build box. They
  are never committed or copied into the repo.
- What is committed: API names and counts, request hosts and query-stripped
  paths, cookie names. Never cookie values, account ids, or beacon payloads.

## Phase 1b: live dashboard `chrome://camou-observe`

Approved 2026-10-06 as a separate slice of this spec, built after the phase 1
logger and report verify GREEN. The recon uses the dashboard if it is ready in
time and the report otherwise; it does not wait for it.

### What the spike established (read-only, 2026-10-06)

- Perfetto's `TracingSession::CloneTrace`
  (`third_party/perfetto/include/perfetto/tracing/tracing.h:388`) snapshots a
  **running** session read-only: no stop, no lost events, the source buffer is
  not drained.
- Chromium already uses it: `chrome://traces-internals` has "Clone trace
  session" (`content/browser/tracing/traces_internals/traces_internals_handler.cc:224`,
  `traces_internals.mojom:117`). That WebUI is registered at the **content**
  layer (`content/browser/webui/content_web_ui_configs.cc:51`), so the same
  shape exists in `chrome` and `content_shell`.
- The tracing service links a proto→JSON exporter
  (`services/tracing/perfetto/consumer_host.cc`,
  `//third_party/perfetto/include/perfetto/ext/trace_processor:export_json`).
- **Not established:** whether a cloned session can be read back as JSON
  through that exporter. The first plan task is a throwaway probe that
  settles it. If it cannot, the page decodes the small protobuf subset it
  needs (TrackEvent, interned names, debug annotations) itself.

### Design

- A content-layer WebUI at `chrome://camou-observe`, compiled only with
  `camou_observe = true`. Web content cannot navigate to `chrome://` URLs, so
  pages cannot see it.
- Switch `--camou-observe` makes the browser open its own tracing session for
  `disabled-by-default-camou.observe` at startup, so no page load is missed.
  This replaces the `--trace-startup*` flags of phase 1; the report keeps
  working on the files the dashboard saves.
- Every few seconds the handler clones the session, aggregates, and the page
  renders: top-level site → surface group → API → call count, split by
  reading origin.
- Network is live through a read-only `NetLog` observer (as
  `chrome://net-export` attaches one). Cookie names come from the
  `CookieManager`, never values.
- A "Save" button writes the trace and netlog to files that
  `observe_report.py` reads.
- The page renders only through `textContent` under a strict CSP: an XSS in a
  `chrome://` page is full compromise (camoufox's panel rule). A test feeds
  markup-laden hostnames and asserts they render inert.
- Verification: the phase 1 probe page, read through the dashboard, shows the
  same exact counts the report shows.

### Cost

A new WebUI (C++ handler, mojom, TS/HTML, grd, registration) patched into
`content/`, roughly 600–1000 lines, and one more full build on each box.

## Non-goals (phase 1)

Tracked in `docs/observer/followups.md`: V8/Intl hooks, new spoofs for any leak
the recon finds, decoding Falco `e` payloads, automated loops against
facebook.com. Also not built: value capture (real vs spoofed), response
bodies.

## Risks

- **Generator patch at re-pin.** `interface.py` is upstream Python that moves;
  the patch is small and the verify catches a silent no-op (zero events).
- **Rebuild cost.** Regenerating every binding is a multi-hour build on the
  only box and again on the Windows host; the 156 re-pin is due 2026-10-20.
  Schedule builds so they do not collide with the re-pin.
- **Trace volume.** Even allow-listed, a canvas-heavy page can emit many
  events. The plan sets the trace buffer size explicitly and the report states
  whether the buffer filled.
- **Login walls.** Logged-out Instagram/Threads serve a wall; camoufox noted the
  data may describe the wall's code. The logged-in arms are the ones that count.

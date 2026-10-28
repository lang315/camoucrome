# Tracking observer — operator guide

An audit build that records, per site, which fingerprint surfaces a page reads
(Web IDL member, real call count, reading origin, top-level site) and what it
sends back (requests, cookie names). Observe-only. Design:
`docs/superpowers/specs/2026-10-06-tracking-observer-design.md`.

## Build

Add to the out dir's `args.gn` (never to `settings/build-args.gn`):

    camou_observe = true
    v8_enable_runtime_call_stats = true

The second arg compiles in V8's runtime call stats, which the Intl recipe below
reads; it rebuilds V8, not Blink (box, 2026-10-13: 1634 steps, 22 min).

`scripts/package.py` refuses such an out dir: an observer build is never a
release. With the arg off, the generated calls compile to nothing.

## Run

    chrome --user-data-dir=<fresh profile> \
      --trace-startup=-*,disabled-by-default-camou.observe \
      --trace-startup-format=json --trace-startup-file=<trace.json> \
      --trace-startup-duration=0 \
      --trace-startup-record-mode=record-as-much-as-possible \
      --log-net-log=<net.json>

Browse, then close the browser normally. The trace is written at shutdown; a
killed browser leaves no trace file. Use one fresh profile per site.

The `-*,` prefix matters: a filter listing only disabled-by-default categories
still enables every default category, which made traces tens to hundreds of MB
and carried unrelated browsing data.

**Intl recipe.** To also count Intl built-ins (`new Intl.DateTimeFormat`,
`resolvedOptions`, the `supportedLocalesOf` family, `toLocale*`), record with

    --trace-startup=-*,disabled-by-default-camou.observe,v8,disabled-by-default-v8.runtime_stats

The report's "V8 built-ins (Intl)" section then lists calls per site, entry
script and built-in. The entry script is the Blink `v8.run` script around the
V8 slice, else the one script of the observer events inside that slice, else
`(unknown)`: event handlers, timers, promise callbacks and module bodies have
no entry script of their own. Without the recipe, or on a build without the
arg, the section says `Intl: blind`, never zero. The recipe is opt-in because
`v8` is a busy default category and the call stats time every built-in call
(see Detectability). On Windows: `observe-recon.ps1 ... -Intl`.

On the Windows host the recon used `scripts/windows/observe-recon.ps1` (one
owner-driven arm: launch with the flags above, wait for the browser to close,
copy the cookie database, run the report) and `scripts/windows/observe-arm1.ps1`
(the tooling-launched logged-out arm, closed by one CDP `Browser.close`). They
are byte-exact copies of `D:\camou-win\observe\recon.ps1` and `arm1.ps1` and
hardcode that host's layout (`D:\camou-win\chromium\src\out\Observe\chrome.exe`,
`observe_report.py` in `D:\camou-win\observe`). `observe-recon.ps1` gained
`-Intl` on 2026-10-13; the host copy is updated with the `out\Observe`
rebuild.

`--trace-startup-duration=0` (record until exit) is the documented setting for
`chrome` sessions closed normally. `scripts/verify_observe.py` instead uses
`--trace-startup-duration=20` on `content_shell`, because content_shell's
SIGTERM path wrote no trace; the duration timer flushes it.

`verify_observe.py` has 25 rows, including a hot loop of 100 000 `fillRect`
calls and `lineWidth` sets that V8 runs on its fast API path, three Intl
built-ins counted on the page and in its worker, and two arms that must report
Intl blind.

## Read

    cp <profile>/Default/Cookies /tmp/cookies.db
    python3 scripts/observe_report.py <trace.json> <net.json> --cookies /tmp/cookies.db

Per top-level site: surface group, API, reading origin, script, call count,
then a "Top scripts" table (each script's total calls and its three most-read
APIs); requests per host (query strings dropped); cookie names (values are
never read). The raw trace opens in https://ui.perfetto.dev.

The report's first line says whether the trace buffer (200 MB under
`record-as-much-as-possible`) discarded chunks. A full buffer stops the whole
trace while the browser keeps running, so the counts then cover only the start
of the session and are lower bounds; the netlog's requests are still complete.

Sections named `chrome://...` (the omnibox popup, the new-tab page) are
Chrome's own internal pages, not web content. Dedicated-worker reads carry no
site, so they land in a section named after the worker's origin (its
creator's), not under the page's top-level site.

`script` is the script at the top of the JavaScript stack when the API was
called, shown as host and path (query and fragment dropped). It separates a
page's own code from third-party scripts it includes as first-party code (for
example `connect.facebook.net/en_US/fbevents.js` under the page's origin). An
inline `<script>` reports its document's URL; code with no script (or `eval`
without a `sourceURL`) shows `(no script)`. A `blob:` or `data:` script shows as
`blob:` or `data:` alone (the rest is an object id or the code itself).

An event fires at the entry of the binding, before argument and receiver
checks, so a call that throws (for example a brand-check probe) still counts
as a read.

## Behaviour signals

Since the `observe-behaviour` patch the observer also reports (design:
`docs/superpowers/specs/2026-10-28-observer-behaviour-signals-design.md`):

- **Listener registrations by event type**, from every `addEventListener`
  overload and `on*` setter (`EventTarget.addEventListener[<type>] target=<interface>
  opts=<passive,capture,once>`), with the registering origin, site and script. A
  type is printed only if it is in the report's known set; any other type is
  counted under `[other]` and its name is never printed (a page can register any
  string).
- **Timing:** `Performance.now`, `requestAnimationFrame`, `setTimeout` and
  `setInterval`, with a calls-per-second figure per script.
- **Focus and visibility:** `Document.visibilityState`, `hidden`, the `webkit`
  forms and `hasFocus`.
- **Clipboard:** the `Clipboard` and `ClipboardItem` interfaces and
  `Document.execCommand`.
- **Motion and orientation:** the `DeviceMotionEvent` and `DeviceOrientationEvent`
  classes and the Generic Sensor classes.

A registration is counted, not how often the listener fires or what it does. A
duplicate registration still counts (the page asked), and an `on*` handler
re-assigned after its first assignment does not. With the category on, each
call adds about 2 to 4 microseconds, which `performance.now` timings include:
do not use the timing rows to judge timing detectability. Report groups:
`input-events`, `focus-visibility`, `clipboard`, `motion`, `timing`,
`listeners-other`.

## What it cannot see (silence is not safety)

- V8 built-ins `Date.prototype.getTimezoneOffset` (a CSA builtin) and `Math`;
  Intl only with the Intl recipe.
- CSS `@media` rules in stylesheets (only `matchMedia` is seen).
- Font enumeration through layout beyond the listed layout members.
- TLS/JA3, HTTP/2 framing, server-side computation.
- Values: a row says a page read `deviceMemory`, not what it got.
- Named and indexed access (`localStorage.foo`, `navigator.plugins[0]`) goes
  through interceptors and is not observed.
- Dispatch: how often a listener fires and what its handler does.
- `Date.now`, `performance.timeOrigin`, `PerformanceObserver`, `queueMicrotask`,
  `requestIdleCallback`, scroll offsets, `document.execCommand`'s command.

## Detectability

The observer is an audit tool, not a stealth mode. With the category off, each
allow-listed call costs one category check. With it on, each call writes a
trace event. Measured with only the observer category enabled (`-*,` filter),
content_shell on the build box, 200 000 `navigator.userAgent` reads and 300
`toDataURL` calls. This is a worst-case microbenchmark, not a page-load cost.
The numbers come from `scripts/verify_observe.py --timing`; its "off" row ran
with `blink,loading` tracing on and the observer category off, so it is not a
no-tracing baseline:

| category | `ua_200k_ms` | `todataurl_300_ms` |
|---|---|---|
| off | 88.5 | 29.6 |
| on | 512.1 | 30.6 |

A single run on 2026-10-08 (after the fast-call hook) measured off 75.6 /
29.5 ms and on 788.9 / 30.9 ms. The on-arm `navigator.userAgent` rise is
more than 10x what the hook's extra `HandleScope` and script-name copy cost,
and the off arm moved 15% the other way in the same session, so it is not
attributed to the hook; it needs repeated runs before replacing the numbers
above.

Three runs on 2026-10-13, on the build with `v8_enable_runtime_call_stats =
true`. `intl` is the Intl recipe. `trace_bytes` is the `timing.html` trace.

| recipe | `ua_200k_ms` | `todataurl_300_ms` | `trace_bytes` |
|---|---|---|---|
| off (`blink,loading`) | 92.9-94.7 | 29.1-30.3 | 244 830-247 911 |
| on | 854-884 | 32.9-33.6 | 52 533 915-52 535 207 |
| intl | 944-1006 | 31.8-34.1 | 52 548 451-52 550 560 |

The Intl recipe adds 8-14% to the on-arm getter loop. Its call stats time
every built-in and runtime call. It adds about 15 KB of `v8` events to this
page's trace. With the stats category off, the compiled-in counters cost one
flag check per C++ built-in: CI's browser verifies on this build matched
main's (2026-10-13).

Browse a site normally, on a release build, when staying hidden matters.

## Data handling

Traces, netlogs and profiles hold the operator's real browsing. Keep them on
the machine that made them. Commit only names, counts, hosts and
query-stripped paths. Ids inside a path (account ids, pixel ids, as in
`signals/config/<pixel-id>`) are redacted in committed data; the report prints
paths as they are, so redact before committing.

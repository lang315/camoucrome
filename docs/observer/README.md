# Tracking observer — operator guide

An audit build that records, per site, which fingerprint surfaces a page reads
(Web IDL member, real call count, reading origin, top-level site) and what it
sends back (requests, cookie names). Observe-only. Design:
`docs/superpowers/specs/2026-10-06-tracking-observer-design.md`.

## Build

Add to the out dir's `args.gn` (never to `settings/build-args.gn`):

    camou_observe = true

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

On the Windows host the recon used `scripts/windows/observe-recon.ps1` (one
owner-driven arm: launch with the flags above, wait for the browser to close,
copy the cookie database, run the report) and `scripts/windows/observe-arm1.ps1`
(the tooling-launched logged-out arm, closed by one CDP `Browser.close`). They
are byte-exact copies of `D:\camou-win\observe\recon.ps1` and `arm1.ps1` and
hardcode that host's layout (`D:\camou-win\chromium\src\out\Observe\chrome.exe`,
`observe_report.py` in `D:\camou-win\observe`).

`--trace-startup-duration=0` (record until exit) is the documented setting for
`chrome` sessions closed normally. `scripts/verify_observe.py` instead uses
`--trace-startup-duration=20` on `content_shell`, because content_shell's
SIGTERM path wrote no trace; the duration timer flushes it.

`verify_observe.py` has 17 rows, including a hot loop of 100 000 `fillRect`
calls and `lineWidth` sets that V8 runs on its fast API path.

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

## What it cannot see (silence is not safety)

- V8 built-ins: `Intl.*`, `Date.prototype.getTimezoneOffset`, `Math`.
- CSS `@media` rules in stylesheets (only `matchMedia` is seen).
- Font enumeration through layout beyond the listed layout members.
- TLS/JA3, HTTP/2 framing, server-side computation.
- Values: a row says a page read `deviceMemory`, not what it got.
- Named and indexed access (`localStorage.foo`, `navigator.plugins[0]`) goes
  through interceptors and is not observed.

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

A single run on 2026-10-08 (after the fast-call hook) measured off 75.6 / 29.5 ms and on 788.9 / 30.9 ms; the on-arm `navigator.userAgent` figure is not attributed to the hook (that getter has no fast path) and needs repeated runs before replacing the numbers above.

Browse a site normally, on a release build, when staying hidden matters.

## Data handling

Traces, netlogs and profiles hold the operator's real browsing. Keep them on
the machine that made them. Commit only names, counts, hosts and
query-stripped paths. Ids inside a path (account ids, pixel ids, as in
`signals/config/<pixel-id>`) are redacted in committed data; the report prints
paths as they are, so redact before committing.

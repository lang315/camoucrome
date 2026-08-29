# SP2 D1 — resolved by measurement: driver-side (option a), no V8 patch

**Decision:** SP2 open decision D1 asked how far to go on the `Runtime.enable`
vector, between (a) never enabling the Runtime domain, driver-side and free;
(b) patching `v8/src/inspector/v8-console.cc`, the riskiest and most
rebase-expensive; and (c) main-world-only suppression, of unknown
feasibility. **The measurements resolve it to (a). Option (b) is not
warranted by either sub-vector.**

The spec was explicit that this had to be measured first: *"Committing to a V8
inspector patch before knowing whether a free driver-side fix closes the same
vectors would be the single most expensive mistake available in this
sub-project. Sequence the measurement first."* Three measurements were run
against the shipping build at checkout `70cb99fedc`.

## The two sub-vectors D1 covers

**Console-serialization getter** (measurement 1,
`2026-08-28-sp2b-1-console-getter.json`). The classic vector — `defineProperty`
a getter, pass the object to `console.debug`, watch the getter fire because
protocol serialization read it — **does not reproduce on this Chromium
revision**, on `content_shell` or `chrome`, with both controls confirming the
probe was capable and the Runtime domain was live. There is no defect here for
any option to fix.

**Stack-trace timing** (measurements 2 and 3). Timing 10,000 `new Error().stack`
constructions:

| state | median | vs baseline |
|---|---|---|
| no debugging port | 24.6-25.8 ms | — |
| port open, no client | 24.3-25.1 ms | none |
| raw CDP attach, Page domain only, **no Runtime** | 24.4 ms (n=9) | **none** |
| raw CDP attach, **`Runtime.enable`** | 29.5 ms (n=9) | **+21%, zero overlap** |
| Playwright (Runtime + page agent) | 30.6-31.4 ms | +21% and a little more |

`Runtime.enable` is the specific cause. A bare attach costs nothing; not
enabling Runtime returns the timing to baseline. The vector is closed by a
driver that does not enable the Runtime domain — which is option (a), and
which is where a well-built CDP driver (patchright, or SP6's own) already
sits.

`Error.stackTraceLimit` (10) and `Error.prepareStackTrace` (undefined) are
invariant across every state, so the properties a page reads directly never
move; only a self-timing differs, and only while Runtime is enabled.

## Why not (b) or (c)

Option (b), the V8 inspector patch, is the one the spec flagged as the most
expensive available mistake. Neither sub-vector needs it: the console getter
does not reproduce, and the timing vector is closed for free by (a). Patching
`v8/src/inspector` to fix a leak that a driver-side setting already closes
would be pure rebase cost against every Chromium roll (SP2 D5), for nothing.
Option (c) is moot for the same reason — there is no residual the free option
leaves behind that (c) would need to catch.

## What this constrains, and what it hands to SP6

D1's resolution is a **driver-layer constraint, not a C++ change**: Camoucrome
must not be driven through a CDP client that enables the Runtime domain. That
is the same shape as SP2 section 4.6's ChromeDriver prohibition, and it lands
in SP6 (the driver API) rather than in an SP2 patch. SP2b therefore has **no
V8 work** on account of D1.

Two honest limits on the evidence, recorded so they are not over-read:

- The timing signal is a self-measurement with no device-independent
  reference (~2500ns unattached vs ~3100ns with Runtime), so on its own it is
  a score-raising heuristic rather than a binary tell. Option (a) removes even
  that, for free, so there is no reason not to take it — but it was never the
  fatal class of leak `navigator.webdriver` was.
- Measurement 1's console result is for the default configuration and for a
  page-triggered getter. A DevTools frontend rendering object previews, or an
  explicit `Runtime.getProperties` with `generatePreview`, is a client action
  a page cannot trigger, and was not measured. If SP6 ever ships a driver that
  requests previews, that is a new measurement, not a settled one.

## Downstream

- SP2b has no `Runtime.enable` C++ task. D1 is a driver constraint for SP6.
- D5 (rebase cost of a V8 inspector patch) is moot: no such patch.
- Still open in SP2b, untouched by these measurements: D3 (trusted input),
  the isolated-world audit (4.2), humanized cursor (4.5), and `window.chrome`
  (4.7 / D7, also gated on SP7 branding).

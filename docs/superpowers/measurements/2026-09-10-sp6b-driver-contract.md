# SP6b driver contract and the two clients (A4 #1, A4 #3 flags) — 2026-09-10

Roadmap A4 #1: adopt, not write, a CDP driver that honours the measured
constraints (SP2 D1: never `Runtime.enable`; isolated worlds; no main-world
init script), then actually run the isolated-world items. This is the
contract, the measurement, and the two launchers (Python, Go) that ship on
it. SP6's threat model stays visible below: each item says whether the
browser or the driver closes it.

## 1. Where the anti-detect property lives

Playwright is a thin binding (Python, Go, Node) talking JSON-RPC to one
**Node driver** (`playwright-core`); the driver is what sends CDP. patchright
patches the driver; its Python package is the stock binding over the patched
driver. `playwright-go` runs the same kind of driver from a directory it is
pointed at, so pointing it at `patchright-core` gives Go the whole patch set
with no Go code involved. The Go binding therefore needs no port, and Rod /
chromedp (which `Runtime.enable` themselves) were not considered further.

Pins (`settings/launcher.json`): patchright 1.62.3 (Python);
`playwright-go v0.6201.1`, which checks the driver's `--version` against
`1.62.1`, with `patchright-core@1.62.1` unpacked as `<dir>/package` and
`<dir>/node` from the patchright wheel (Node 24 — the box's Node 18 is
refused by the driver). Gotcha: the Go module declares its path as
`github.com/mxschmitt/playwright-go`; the `playwright-community` path fails
to resolve. `PLAYWRIGHT_NODEJS_PATH` skips playwright-go's own Node download.

## 2. Two things measured before the launcher existed

**patchright evaluates in an isolated world.** A global set through
`page.evaluate` was invisible to a script the page itself injected into the
main world (`document.title = typeof window.__camou_marker` → `undefined`),
and playwright-go cannot pass a per-call world flag. So nothing in the
contract is read through `evaluate`: the probe page's own script (main
world, synchronous, so a `--dump-dom` run captures it too) writes its report
into `<pre id="o">`, and every client reads that text through the DOM, which
all worlds share.

**Playwright's default argv moves feature state.** The browser's real argv
(`/proc/<pid>/cmdline`; Chromium rewrites it into one space-joined string)
under patchright's defaults carried `--disable-features=` with 18 features,
`--enable-features=CDPScreenshotNewSurface`,
`--blink-settings=primaryHoverType=2,availableHoverTypes=2,primaryPointerType=4,availablePointerTypes=4`,
`--hide-scrollbars`, `--mute-audio`, `--force-color-profile=srgb`,
`--disable-blink-features=AutomationControlled`, `--disable-field-trial-config`,
`--password-store=basic`, `--use-mock-keychain` and more. Each moves a
page-visible surface off the compiled-defaults position SP7 D3 accepted (the
feature list literally so). Both launchers pass `ignore_default_args` and
exactly `settings/launcher.json`'s list — which then has to include the two
Playwright defaults the flag also drops: without `--remote-debugging-pipe`
the driver waits forever on `Browser.getVersion`; without `--user-data-dir`
Chrome ran `--incognito` in a scoped dir. Chrome's own `--headless=new`
relaunch appends `--noerrdialogs --ozone-platform=headless
--ozone-override-screen-size=800,600 --use-angle=swiftshader-webgl`; those
appear identically with no driver at all, so the contract lists them as
Chrome's, not the driver's.

Also measured on the way: `CAMOU_CONFIG` reaches the browser both through
Playwright's `env=` and by inheritance (`screen.width` 1234 either way);
`navigator.userAgent` in a config is *unsupported by design* (the registry
says so; the UA comes from `ua:*`), which is why the first smoke test showed
the real UA. content_shell is not launchable through Playwright
(`Target.createBrowserContext` fails, persistent context finds no page), so
the contract runs on `chrome`.

## 3. The contract (`scripts/verify_sp6b_driver.py`, `settings/launcher.json`)

One verify, one probe page, four drivers through one CLI shape
(`python -m camoucrome.probe`, `camoucrome-probe`): the stock rows are the
RED rows and must fail, the patchright rows must pass. Stock is the *same
version* as patchright on each side (`playwright==1.62.0` in a second venv,
`playwright-core@1.62.1` in a second driver dir), so the only variable is
the patch set.

| item | closed by | how it is observed |
|---|---|---|
| C1 no `Runtime.enable`, and ≥ 20 protocol sends so a silenced logger cannot pass vacuously | driver | `DEBUG=pw:protocol` on the driver process |
| C2 `Object.keys(window)` == no-driver baseline | browser (SP2) + driver (no binding/init-script global) | probe page vs `--dump-dom` run |
| C3 `navigator.webdriver` false | browser | probe page |
| C4 browser argv **equals** the contract's set (+ profile dir, + the probe's `--no-sandbox`) | launcher | `/proc` cmdline; equality, not just absence of the four forbidden flags, so a new default cannot slip in |
| C5 7×10000 `new Error().stack` median within 15% of the baseline (median of 3 no-driver launches) | driver | probe page; D1's +21% signal |

| driver | C1 | C2 | C3 | C4 | C5 | row |
|---|---|---|---|---|---|---|
| python-stock | `Runtime.enable=1`, 383 sends | ok | ok | ok | +20% / +27% | RED as expected |
| python-patchright | 0 / 404 | ok | ok | ok | −1% / −1% | PASS |
| go-stock | 1 / 383 | ok | ok | ok | +22% / +21% | RED as expected |
| go-patchright | 0 / 410 | ok | ok | ok | +3% / +2% | PASS |

Two consecutive runs, both `ALL_PASS`; the C5 pairs are the two runs.
Baseline: 235 window keys, `webdriver=false`, stack median 19.6 / 19.3 ms.
Before the three-run baseline one run wobbled to 17.8 ms and put patchright
at +11% against a 10% tolerance — the reason for both the median-of-three and
the 15%. C2 passing on the stock rows means the SP2 browser-level closures
hold against stock Playwright too (bindings and init scripts leave no
enumerable window key), which is exactly SP6's threat model; C1 and C5 are
what only the driver closes.

## 4. The clients

`client/python/camoucrome` (`launch(playwright, executable_path, config=,
preset=, strict=, user_data_dir=, window=, dpr=, headless=, args=)`) and
`client/go` (`camoucrome.Launch(pw, Options{...})`) do the same four
things: drop every parent `CAMOU_*` and set `CAMOU_CONFIG` / `CAMOU_PRESET`
/ `CAMOU_CONFIG_STRICT`; build the argv above plus the launcher-layer flags
the C++ left to them (`--window-size`, `--force-device-scale-factor`, one
`--user-data-dir` per identity — A4 #3); `ignore_default_args`; a persistent
context with `no_viewport` (Playwright otherwise emulates 1280×720 through
`Emulation.setDeviceMetricsOverride`, fighting `screen.*`). Python refuses
the contract's forbidden options (`locale`, `timezone_id`, `user_agent`,
`viewport`, `screen`, `device_scale_factor`, `geolocation`, `color_scheme`,
`extra_http_headers` — each duplicates a config key); Go has no such field,
and a test pins that none appears. Each client has one test that builds its
args and compares them with `settings/launcher.json`, so the two cannot
drift apart silently.

Box layout: `~/camoucrome-verify/venv` (patchright + `pip install -e
client/python`), `venv-stock` (playwright 1.62.0, `--no-deps`),
`~/camoucrome-driver` and `~/camoucrome-driver-stock`, the Go probe at
`~/camoucrome-go/camoucrome-probe`; the verify takes these as `CAMOU_*` /
`PLAYWRIGHT_NODEJS_PATH` environment overrides.

## 5. Not done, named

- Headed launches: the contract ran headless only (`--headless=new`). A
  headed run drops Chrome's four self-added flags and needs a display;
  the verify's C4 handles the absence, nothing measured it.
- `--load-extension` (uBO) and a custom CA for MITM proxies: not in either
  launcher yet.
- Generator (A4 #2): the Go client takes a preset + per-instance seeds
  today; the statistical generator stays Python, to be exposed as a CLI the
  Go client can exec. Not started.
- The Node front-end is nearly free (patchright ships one) and was not
  built.

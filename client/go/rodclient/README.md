# rodclient

Launch the fork exactly as `camoucrome.Launch` does (same env, same argv) and
drive it with [go-rod](https://github.com/go-rod/rod) over
`--remote-debugging-pipe`. rod's own launcher is never used, and rod's page API
is unreachable: callers get a small vetted `Page`.

## When to use it

- Use the playwright-go launcher (`client/go`, `camoucrome.Launch`) by default:
  it has the full Playwright API, proxy auth, frames and the patched
  `patchright-core` driver.
- Use rodclient when you want no Node driver process and can live with the
  small API below. Its CDP traffic is the measured contract of
  `scripts/verify_sp6b_driver.py` (row `go-rodclient`).

## API

`Launch(ctx, camoucrome.Options, ...Option) (*Browser, error)`, then
`Browser`: `Argv()`, `OnSend(func([]byte))`, `NewPage(ctx)`, `Close()`.

To audit CDP traffic, pass `WithSendObserver(f)` to `Launch`: it sees every
message sent, in wire order, from the first one, including what is sent while
connecting (`Target.setDiscoverTargets`). `OnSend` only sees messages sent
after Launch returns, so it cannot prove that a connect-time message was
absent.

`Page` (exactly these 13 methods, pinned by `surface_test.go`):
`Goto(ctx, url, WaitLoad|WaitNetworkIdle)`, `WaitForSelector`, `Click`, `Hold`,
`Type`, `TypeWith`, `Text`, `Attribute`, `Screenshot`, `Cookies`, `Eval`, `AddInitScript`,
`Close`.

Input is human-like, client-side (`human.go`; the fork humanizes the mouse path
and wheel browser-side):
- `Click` moves to a press point drawn inside the inner 70 % of the element's
  content box (not the centre), settles, then presses, holds tens of ms and
  releases. `Hold(ctx, selector, d)` is the same approach, then keeps the button
  down for `d` with sparse 1-2 px `mouseMoved` events (buttons=1).
- `Type` gives every key a dwell and a right-skewed gap to the next key (longer
  after a space or punctuation and before a shifted key, with a rare pause at a
  word boundary). A shifted US-layout character is bracketed by real `ShiftLeft`
  key events; consecutive shifted characters share one press. Runes off the
  layout still go through `Input.insertText`. The gap for a frequent English
  letter pair (`th`, `er`, `e` then space, ...) is that pair's calibrated
  median; other pairs use the overall one. With the calibrated probability
  (about 18 %) the next key goes down before the previous one is up (key
  rollover), by a lognormal overlap; never more than two keys are down at once
  (Shift apart), and on any error or cancel every key still down is released.
- `TypeWith(ctx, selector, text, TypeOptions{Typos: true})` adds typos, off in
  `Type`: now and then a neighbouring US-QWERTY key is typed instead (same Shift
  state), 1 to 3 characters pass, then after a notice delay Backspace is pressed
  (real key events) once per character and they are retyped. The field's final
  value is always `text`. Enter, Tab and runes off the layout get no typos.
- Every timing is a named constant in `human.go`, drawn from `Page`'s seeded
  `rand` (lognormal, truncated; no flat uniform). The values come from
  published keystroke and pointing studies; they are not calibrated on a
  person.

Every op is bounded by the ctx deadline, or 30 s without one. `Goto` and
`Text` run in an isolated world; only `Eval` and `AddInitScript` touch the main
world.

`Launch`'s ctx bounds Launch only: the browser is started with
`context.WithoutCancel(ctx)`, so `WithTimeout` + `defer cancel` does not kill
it; it lives until `Close`. A ctx cancelled before Launch returns (also during
the connect) aborts with nothing left running or on disk. `Close` asks the
browser to quit (up to 3 s), then waits up to 5 s for it to exit (so a
persistent profile is fully written; skipped when the quit request failed),
then kills the process group. A failed `Launch` kills at once. `OnSend` replaces the observer
set by `WithSendObserver`; observers run under the send lock and must not call
back into `Browser`. Errors from `Launch` and `NewPage` carry a `rodclient:`
prefix and wrap their cause.
`AddInitScript` is the counterpart of playwright's `add_init_script`: it runs
in the MAIN world, by design, so anything it defines is visible to the page.

## What it does not expose, and why

- rod's `Page`, `Element`, `Browser`: no embedding, accessor or exported field.
  rod helpers enable domains (`Runtime.enable`, `Page.enable`, `Network.enable`,
  `DOM.enable`) or emulate (`Emulation.*`, user agent) behind the caller's back.
  `page_unix_test.go` asserts that no `Page` op sends any of them.
- The one exception is `Page.enable`, sent once by `NewPage` (rod's page setup;
  playwright and patchright send it too, and the box C5 +0 % includes it).
  `TestNewPageExactMethods` pins `NewPage`'s exact method set. "No `DOM.enable`"
  is about messages sent: `DOM.getDocument` still activates Chromium's DOM
  agent implicitly.
- Launch applies rod's `NoDefaultDevice()`: rod's implicit laptop emulation
  would fight the fork's `screen.*`.
- No frame or event APIs: rod's event machinery works through domain enables.

## Known limits (v1)

- No proxy: `Launch` rejects `Options.Proxy` (proxy auth is not implemented).
- No frames or OOPIF; elements are found in the top document only.
- Input timing is parametric, not recorded from a person: a detector that
  fits individual typists or pointing trajectories can still tell. `Type` has
  no typos or Backspace corrections (`TypeWith` adds them), and
  no layouts other than US; runes off it are inserted as text, with no key
  events.
- `Goto` polls document state from an isolated world; a same-document
  navigation (hash change) times out.

## Contract probe

    cd client/go/rodclient && go build -o ~/camoucrome-go/camoucrome-probe-rodclient ./cmd/camoucrome-probe-rodclient

The box's Go (1.22.2) is enough; no toolchain change. On the box, with
`out/Default` built:

    ~/camoucrome-verify/venv/bin/python3 scripts/verify_sp6b_driver.py

or override the binary path with `CAMOU_RODCLIENT_PROBE` (default `~/camoucrome-go/camoucrome-probe-rodclient`, next to the playwright-go probe). The probe takes the same
flags as `camoucrome-probe` (`--proxy*` exits 2), registers
`window.__camou_init = 1`, and logs one raw JSON line per sent CDP message to
stderr.

Tests: `GOTOOLCHAIN=local go test -race -count=1 ./... && go vet ./...`

## Smoke

`cmd/camoucrome-smoke` drives a loopback page that records every input event
(`window.__ev`: type, isTrusted, timeStamp, button(s), key, code, location, shiftKey, x, y) with
`Click` twice, `Type` (into `#in` and, for the key-rollover row, `#in2`),
`TypeWith{Typos}` (into `#in3`, in chunks until one typo was seen), `Hold`, `Text`, `Screenshot` and `Cookies`, then judges the
page's own log, not the client's return values. It prints one JSON report
(`checks`, `events`, `cdp_sends`, `argv`) and exits 1 if any check is RED.
`--humanize` adds `{"humanize:enabled": true}` to the config and checks the
humanized second click (>= 4 mousemoves, median gap 12.5-20.8 ms: the 60 Hz
recording period +-25%). The CDP row allows the one `Page.enable` that `NewPage` sends.

    cd client/go/rodclient && go build -o ~/camoucrome-go/camoucrome-smoke ./cmd/camoucrome-smoke
    ~/camoucrome-go/camoucrome-smoke --executable ~/chromium/src/out/Default/chrome --humanize

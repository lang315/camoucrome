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

`Page` (exactly these 11 methods, pinned by `surface_test.go`):
`Goto(ctx, url, WaitLoad|WaitNetworkIdle)`, `WaitForSelector`, `Click`, `Type`,
`Text`, `Attribute`, `Screenshot`, `Cookies`, `Eval`, `AddInitScript`, `Close`.

Every op is bounded by the ctx deadline, or 30 s without one.
`AddInitScript` is the counterpart of playwright's `add_init_script`: it runs
in the MAIN world, by design, so anything it defines is visible to the page.

## What it does not expose, and why

- rod's `Page`, `Element`, `Browser`: no embedding, accessor or exported field.
  rod helpers enable domains (`Runtime.enable`, `Page.enable`, `Network.enable`,
  `DOM.enable`) or emulate (`Emulation.*`, user agent) behind the caller's back.
  `page_unix_test.go` asserts that no op sends any of them.
- Launch applies rod's `NoDefaultDevice()`: rod's implicit laptop emulation
  would fight the fork's `screen.*`.
- No frame or event APIs: rod's event machinery works through domain enables.

## Known limits (v1)

- No proxy: `Launch` rejects `Options.Proxy` (proxy auth is not implemented).
- No frames or OOPIF; elements are found in the top document only.
- `Type` timing is client-side: uniform 40-120 ms per key (the fork humanizes
  mouse and wheel events only).
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

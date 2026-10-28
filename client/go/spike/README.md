# G0 spike: Go drivers (go-rod, chromedp)

THROWAWAY. This module answers one question (can a pure-Go CDP driver pass the
SP6b driver contract?). Delete `client/go/spike/` if the owner chooses G3.

Two probes, both launching the browser themselves over our pipe, so the browser
argv equals the contract:

- `cmd/camoucrome-probe-rod`: go-rod. GREEN candidate. `--no-default-device`
  turns off rod's default device emulation.
- `cmd/camoucrome-probe-chromedp`: chromedp with default settings. RED control:
  it must fail C1, or the harness measures nothing.

Both take `--executable --url --config --preset --headed --strict --sandbox
--label --driver-dir` (ignored), print `{"driver","report","argv"}` on stdout and
one raw JSON line per SENT CDP message on stderr (the C1 log).

## Build

Needs Go >= 1.25 (chromedp v0.21.0). The box's Go version is unknown: run
`go version` first.

    cd client/go/spike && go build -o bin/camoucrome-probe-rod ./cmd/camoucrome-probe-rod && go build -o bin/camoucrome-probe-chromedp ./cmd/camoucrome-probe-chromedp

`bin/` is git-ignored. Paths can be overridden with `CAMOU_ROD_PROBE` and
`CAMOU_CHROMEDP_PROBE`. A missing binary is a FAIL row.

## Run on the box

    env -i HOME PATH PYTHONPATH CAMOU_CLIENT CAMOU_FONTS_DIR ~/camoucrome-verify/venv/bin/python3 scripts/verify_sp6b_driver.py

There is no row filter: the six older rows (Python, Go, Node) run too, and need
their usual drivers under `~/camoucrome-driver*`. Read the two rows named
`go-rod-own-launcher` and `go-chromedp-control`.

## Reading the result

- rod PASS (C1-C6 all ok): G1 is viable.
- rod fails C1 or C5: G3.
- chromedp must FAIL C1 (Runtime.enable sent). If it passes, the row is
  measuring nothing.
- C1 for rod uses a floor of 10 sends (`min_methods`), not 20: the Go probes
  log sent messages only.

## By hand: rod's library defaults

Rod's default device emulation is a finding, not a row (verify knows only
GREEN/RED). Run once by hand without `--no-default-device`, with the same
`--executable` and `--url`, and record which of C1-C6 move in the measurement
doc.

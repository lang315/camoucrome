"""Measurement 0 (cursory spec): how steady is a 60 Hz mouse path sent as
individual Input.dispatchMouseEvent calls from a client, as seen by the page?

Stock content_shell, no humanize, no fork changes. For each driver (patchright
page.mouse.move per sample, raw websocket; the Go client has no mouse-move
entry point), send N=120 samples along a straight 600 px line at a 16.7 ms
target period, record the page-visible mousemove.timeStamp, print gap_stats
per driver as JSON.

Run on the build box:
  env -i HOME="$HOME" PATH="$PATH" PYTHONPATH="$PYTHONPATH" \
    CAMOU_CLIENT="$CAMOU_CLIENT" CAMOU_FONTS_DIR="$CAMOU_FONTS_DIR" \
    ~/camoucrome-verify/venv/bin/python3 scripts/measure_cdp_timing.py
It launches the binary lib_shell.layout() resolves (out/Default/content_shell).
"""
import json
import statistics
import sys
import time

TARGET_PERIOD_MS = 1000 / 60
N = 120
LINE_PX = 600
X0, Y = 20, 200

PAGE = ("data:text/html,<body style='margin:0'>"
        "<script>window.__m=[];addEventListener('mousemove',"
        "e=>__m.push(e.timeStamp))</script></body>")


def gap_stats(stamps_ms):
    gaps = [b - a for a, b in zip(stamps_ms, stamps_ms[1:])]
    if not gaps:
        return {"n": 0}
    sd = statistics.pstdev(gaps)
    return {
        "n": len(gaps),
        "median": statistics.median(gaps),
        "p95": sorted(gaps)[int(0.95 * (len(gaps) - 1))],
        "max": max(gaps),
        "stdev": sd,
        "jitter": sd,
    }


def _xs():
    return [X0 + LINE_PX * i / (N - 1) for i in range(N)]


def _paced(send):
    """Calls send(x) per sample, sleeping to absolute deadlines so the
    client's own loop does not add drift to what is being measured."""
    t0 = time.monotonic()
    for i, x in enumerate(_xs()):
        send(x)
        wait = t0 + (i + 1) * TARGET_PERIOD_MS / 1000 - time.monotonic()
        if wait > 0:
            time.sleep(wait)


def _read_and_reset(page):
    got = page.evaluate("(()=>{const m=__m;window.__m=[];return m})()")
    return got


def main():
    import urllib.request
    import lib_shell
    import websocket  # websocket-client, as measure_sp2b_attach.py
    from playwright.sync_api import sync_playwright

    # --remote-allow-origins=*: Chrome 141+ rejects websocket-client's Origin.
    proc = lib_shell.launch({}, extra_flags=[*lib_shell.SHELL_FLAGS,
                                                  "--remote-allow-origins=*"])
    out = {}
    try:
        base = f"http://127.0.0.1:{proc.cdp_port}"
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(base)
            ctx = browser.contexts[0]
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(PAGE, wait_until="load")
            page.mouse.move(X0, Y)  # warm the input path; discarded
            _read_and_reset(page)

            _paced(lambda x: page.mouse.move(x, Y))
            out["patchright_page_mouse_move"] = gap_stats(_read_and_reset(page))

            targets = json.loads(urllib.request.urlopen(base + "/json").read())
            url = next(t["webSocketDebuggerUrl"] for t in targets
                       if t.get("type") == "page")
            ws = websocket.create_connection(url, timeout=15, suppress_origin=True)
            ids = iter(range(1, 10 ** 6))

            def raw(x):
                ws.send(json.dumps({"id": next(ids),
                                    "method": "Input.dispatchMouseEvent",
                                    "params": {"type": "mouseMoved", "x": x, "y": Y}}))
                ws.recv()  # reply; events need no domain enable, so none arrive

            try:
                _paced(raw)
            finally:
                ws.close()
            out["raw_websocket"] = gap_stats(_read_and_reset(page))
            browser.close()
    finally:
        lib_shell.shutdown(proc)
    # client/go/cmd has only camoucrome-probe, no mouse-move entry point.
    out["go"] = "not available"
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

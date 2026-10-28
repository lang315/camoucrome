"""Measurement 0 (cursory spec): how steady is a 60 Hz mouse path sent as
individual Input.dispatchMouseEvent calls from a client, as seen by the page?

Stock content_shell, no humanize, no fork changes. For each driver (patchright
page.mouse.move per sample, raw websocket; the Go client has no mouse-move
entry point), send N=120 samples along a straight 600 px line at a 16.7 ms
target period, record the page-visible mousemove.timeStamp, print gap_stats
per driver as JSON.

Isolation: each driver gets its own freshly launched browser, killed before
the next starts; the raw-websocket driver runs with nothing else attached, and
stamps are read over HTTP /json (document.title), never over CDP. The
patchright driver may have Runtime.enable active (a property of that driver),
so its figure is a patchright figure, not a clean-CDP figure.

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

# Stamps leave the page through document.title, set once when the last
# sample (plus one discarded warm-up move) has arrived, and are read from the
# HTTP /json target list: no CDP command, no domain, nothing for the driver
# under test to share a session with.
PAGE = ("data:text/html,<title>wait</title><body style='margin:0'><script>"
        "var m=[];addEventListener('mousemove',e=>{m.push(e.timeStamp);"
        f"if(m.length=={N + 1})document.title=JSON.stringify(m)}})</script></body>")


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


def _stamps(base, wait_s=5):
    import urllib.request
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        for t in json.loads(urllib.request.urlopen(base + "/json").read()):
            if t.get("type") == "page" and t.get("title", "").startswith("["):
                return json.loads(t["title"])[1:]  # drop the warm-up move
        time.sleep(0.1)
    raise RuntimeError("page never recorded all samples")


def _launch():
    import lib_shell
    # --remote-allow-origins=*: Chrome 141+ rejects websocket-client's Origin.
    return lib_shell.launch({}, extra_flags=[*lib_shell.SHELL_FLAGS,
                                             "--remote-allow-origins=*"])


def drive_patchright(base):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(base)
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(PAGE, wait_until="load")
        page.mouse.move(X0, Y)  # warm-up
        _paced(lambda x: page.mouse.move(x, Y))
        browser.close()


def drive_raw(base):
    import urllib.request
    import websocket  # websocket-client, as measure_sp2b_attach.py
    targets = json.loads(urllib.request.urlopen(base + "/json").read())
    url = next(t["webSocketDebuggerUrl"] for t in targets if t.get("type") == "page")
    ws = websocket.create_connection(url, timeout=15, suppress_origin=True)
    ids = iter(range(1, 10 ** 6))

    def call(method, params):
        i = next(ids)
        ws.send(json.dumps({"id": i, "method": method, "params": params}))
        while json.loads(ws.recv()).get("id") != i:
            pass  # no domain enabled, so only the reply arrives

    try:
        call("Page.navigate", {"url": PAGE})
        time.sleep(1)
        move = lambda x: call("Input.dispatchMouseEvent",
                              {"type": "mouseMoved", "x": x, "y": Y})
        move(X0)  # warm-up
        _paced(move)
    finally:
        ws.close()


def main():
    import lib_shell
    out = {}
    for name, drive in (("patchright_page_mouse_move", drive_patchright),
                        ("raw_websocket", drive_raw)):
        proc = _launch()  # a fresh browser per driver, killed before the next
        try:
            base = f"http://127.0.0.1:{proc.cdp_port}"
            drive(base)
            out[name] = gap_stats(_stamps(base))
        finally:
            lib_shell.shutdown(proc)
    # client/go/cmd has only camoucrome-probe, no mouse-move entry point.
    out["go"] = "not available"
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

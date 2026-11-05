#!/usr/bin/env python3
"""End to end for chrome://observer on the box: hooks -> trace -> sandboxed decoder -> page.

Runs `chrome` (out/Default) under a synthetic config, records a local test tab from the
observer page and asserts the tables. One line per row: PASS / FAIL / UNMEASURED, then
`RESULT passed/expected`. Exit 1 on any FAIL or when the rows printed differ from EXPECTED
(a verify that lost a row measured less), 3 when a row is UNMEASURED.

Run: ~/camoucrome-verify/venv/bin/python3 verify_observer_page.py
OBSERVER_HEADED=1 (with CAMOU_VERIFY_KEEP_DISPLAY=1 and a DISPLAY) drops --headless.
Streaming ReadableStream uploads need HTTP/2 and are not in this loopback run.

Driving: a raw CDP client over the stdlib, Runtime.evaluate only. Nothing sends
Runtime.enable, which would change the recorded tab's stack timing.
"""
import base64
import hashlib
import json
import os
import socket
import struct
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell  # noqa: E402
import lib_ws_server  # noqa: E402

WIDTH_COUNT = 8  # Screen.width reads on the test page: 1 + 7
HWC_COUNT = 5  # Navigator.hardwareConcurrency: 1 + 4
EXPECTED = 33
CONFIG = {"screen.width": 1517, "screen.height": 853, "navigator.hardwareConcurrency": 12,
          "navigator.deviceMemory": 16, "timezone:id": "Pacific/Chatham",
          "navigator.languages": ["en-US", "en"]}
# The golden `sjd-ok` body (additions/camoucfg/observe_golden.json).
SJD_BODY = ('{"asid":"0123456789abcdefghijklmnopqrstuvwxyz","sjd":"jZe/OrIO2d74uiRZ8ZuWGnal6DU'
            'zGLgY7D8BrOwkSxEjbbaxDacBGIU29Hf/O52O"}')
HTTP_PATHS = ["/s/fetch-string", "/s/fetch-gzip", "/s/fetch-blob", "/s/fetch-formdata", "/s/fetch-usp",
              "/s/xhr-b64", "/s/beacon-blob", "/s/beacon-formdata", "/s/keepalive", "/r307", "/s/sjd"]

PAGE = r"""<!doctype html><meta charset=utf-8><title>observer e2e</title><script>
const WSP = __WSP__, SJD = __SJD__;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const post = (u, body, o) => fetch(u, Object.assign({method: 'POST', body}, o || {}));
const gz = async (s, f) => new Response(new Blob([s]).stream().pipeThrough(new CompressionStream(f))).arrayBuffer();
(async () => {
  post('/pre/fetch-string', '{"pre":1}');
  while ((await (await fetch('/go')).text()) !== '1') await sleep(200);
  const W = screen.width, H = screen.height, TZ = Intl.DateTimeFormat().resolvedOptions().timeZone,
        UA = navigator.userAgent, HC = navigator.hardwareConcurrency, DM = navigator.deviceMemory,
        LG = navigator.languages;
  for (let i = 0; i < 7; i++) void screen.width;
  for (let i = 0; i < 4; i++) void navigator.hardwareConcurrency;
  const jw = JSON.stringify({w: W});
  await post('/s/fetch-string', JSON.stringify({w: W, tz: TZ}));
  await post('/s/fetch-gzip', await gz(jw, 'gzip'));
  await post('/s/fetch-blob', new Blob([`res=${W}x${H}`], {type: 'application/x-www-form-urlencoded'}));
  const fd = new FormData();
  fd.append('a', jw);
  fd.append('z', new File([await gz(jw, 'deflate')], ''));
  await post('/s/fetch-formdata', fd);
  await post('/s/fetch-usp', new URLSearchParams({tz: TZ}));
  await new Promise(r => { const x = new XMLHttpRequest(); x.open('POST', '/s/xhr-b64');
    x.onloadend = r; x.send(btoa(jw)); });
  navigator.sendBeacon('/s/beacon-blob', new Blob([JSON.stringify({d: jw})], {type: 'application/json'}));
  const bf = new FormData(); bf.append('langs', LG.join(','));
  navigator.sendBeacon('/s/beacon-formdata', bf);
  await post('/s/keepalive', new Blob([JSON.stringify({ua: UA})], {type: 'application/json'}), {keepalive: true});
  await post('/r307', jw);
  await post('/s/sjd', SJD, {headers: {'Content-Type': 'application/json'}});
  const ws = new WebSocket(`ws://127.0.0.1:${WSP}/ws`);
  await new Promise(r => ws.onopen = r);
  const enc = new TextEncoder(), t = enc.encode('/t/x'), p = enc.encode(jw);
  const mq = new Uint8Array(4 + t.length + p.length);
  mq.set([0x30, 2 + t.length + p.length, 0, t.length]); mq.set(t, 4); mq.set(p, 4 + t.length);
  const n = 2 + p.length, ch = new Uint8Array(8 + p.length);
  ch.set([0x0d, 0, 0, n & 255, (n >> 8) & 255, 0, 0, 0]); ch.set(p, 8);
  ws.send(jw); ws.send(mq.buffer); ws.send(new Blob([ch]));
  const ok = new Promise(r => ws.onmessage = e => e.data === 'ok' && r());
  ws.send('done'); await ok;
  let gl = null;
  try { const c = document.createElement('canvas').getContext('webgl'); const e = c.getExtension('WEBGL_debug_renderer_info');
    gl = e ? c.getParameter(e.UNMASKED_RENDERER_WEBGL) : null; } catch (_) {}
  await post('/done', JSON.stringify({w: W, h: H, hc: HC, dm: DM, tz: TZ, langs: [...LG], gl: gl || null}));
})();
</script>"""
POST_PAGE = "<!doctype html><meta charset=utf-8><title>observer e2e post</title><script>fetch('/post/fetch-string',{method:'POST',body:'{\"p\":1}'})</script>"

# ---------------------------------------------------------------------------- rows
ROWS = []  # (verdict, name)


def row(name, ok, why="", unmeasured=False, info=""):
    verdict = "UNMEASURED" if unmeasured else ("PASS" if ok else "FAIL")
    ROWS.append((verdict, name))
    detail = info if verdict == "PASS" else why
    print(f"{verdict} {name}" + (f": {detail}" if detail else ""), flush=True)


def finish():
    passed = sum(v == "PASS" for v, _ in ROWS)
    print(f"RESULT {passed}/{EXPECTED}", flush=True)
    if len(ROWS) != EXPECTED:
        print(f"FAIL rows: printed {len(ROWS)}, expected {EXPECTED}", flush=True)
    if any(v == "FAIL" for v, _ in ROWS) or len(ROWS) != EXPECTED:
        return 1
    return 3 if any(v == "UNMEASURED" for v, _ in ROWS) else 0


# ---------------------------------------------------------------------------- http + ws servers
class Site:
    def __init__(self, ws_port):
        self.go = False
        self.reqs = []
        self.done = None
        self.lock = threading.Lock()
        site = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _serve(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                path = urllib.parse.urlsplit(self.path).path
                code, ctype, out, extra = 200, "text/plain", b"ok", {}
                if path == "/page.html":
                    ctype, out = "text/html", PAGE.replace("__WSP__", str(ws_port)).replace(
                        "__SJD__", json.dumps(SJD_BODY)).encode()
                elif path == "/post.html":
                    ctype, out = "text/html", POST_PAGE.encode()
                elif path == "/go":
                    out = b"1" if site.go else b"0"
                elif path == "/r307":
                    code, extra = 307, {"Location": "/s/redirected"}
                elif path == "/done":
                    site.done = json.loads(body)
                if path not in ("/go", "/page.html", "/post.html", "/favicon.ico"):
                    with site.lock:
                        site.reqs.append(path)
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(out)))
                for k, v in extra.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(out)

            do_GET = do_POST = _serve

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def seen(self, path):
        with self.lock:
            return path in self.reqs


# ---------------------------------------------------------------------------- raw CDP
class Cdp:
    def __init__(self, ws_url):
        u = urllib.parse.urlsplit(ws_url)
        self.s = socket.create_connection((u.hostname, u.port), timeout=60)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\n"
                        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            head += self.s.recv(1)
        assert b" 101 " in head.split(b"\r\n")[0], head
        self.n = 0

    def _read(self, n):
        out = b""
        while len(out) < n:
            c = self.s.recv(n - len(out))
            if not c:
                raise EOFError("cdp closed")
            out += c
        return out

    def _recv(self):
        msg = b""
        while True:
            b0, b1 = self._read(2)
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            msg += self._read(n)
            if b0 & 0x80:
                return json.loads(msg)

    def call(self, method, params=None):
        self.n += 1
        data = json.dumps({"id": self.n, "method": method, "params": params or {}}).encode()
        mask = os.urandom(4)
        hdr = bytes([0x81])
        if len(data) < 126:
            hdr += bytes([0x80 | len(data)])
        elif len(data) < 65536:
            hdr += bytes([0x80 | 126]) + struct.pack(">H", len(data))
        else:
            hdr += bytes([0x80 | 127]) + struct.pack(">Q", len(data))
        self.s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
        while True:
            m = self._recv()
            if m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m["result"]

    def ev(self, expr):
        r = self.call("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True})
        if "exceptionDetails" in r:
            raise RuntimeError(f"eval: {r['exceptionDetails'].get('exception', r['exceptionDetails'])}")
        return r["result"].get("value")

    def close(self):
        self.s.close()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def until(fn, timeout, what):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.2)
    raise TimeoutError(what)


class Browser:
    def __init__(self, filter_env=None):
        self.base = None
        flags = list(lib_shell.CHROME_FLAGS)
        if os.environ.get("OBSERVER_HEADED") == "1":
            flags.remove("--headless")
        if filter_env is None:
            os.environ.pop("OBSERVER_PAGE_FILTER", None)
        else:
            os.environ["OBSERVER_PAGE_FILTER"] = filter_env
        self.proc = lib_shell.launch(json.dumps(CONFIG), shell=lib_shell.CHROME, extra_flags=flags,
                                     debug_port=free_port())
        self.base = f"http://127.0.0.1:{self.proc.cdp_port}"

    def open(self, url):
        req = urllib.request.Request(f"{self.base}/json/new?{url}", method="PUT")
        info = json.load(urllib.request.urlopen(req, timeout=10))
        return info["id"], Cdp(info["webSocketDebuggerUrl"])

    def close_tab(self, tid):
        urllib.request.urlopen(f"{self.base}/json/close/{tid}", timeout=10).read()

    def alive(self):
        return self.proc.poll() is None

    def stop(self):
        lib_shell.shutdown(self.proc)


class Observer:
    """The chrome://observer tab."""

    def __init__(self, browser):
        self.browser = browser
        self.tid, self.c = browser.open("chrome://observer")
        until(lambda: self.c.ev("!!document.getElementById('tab') && !!document.getElementById('raw')"),
              30, "observer page did not render")
        # Counts how many times a refresh wrote #raw.
        self.c.ev("window.__n = 0; new MutationObserver(() => window.__n++).observe("
                  "document.getElementById('raw'), {childList: true, characterData: true, subtree: true});")

    def status(self):
        return self.c.ev("document.getElementById('status').textContent")

    def refreshes(self):
        return self.c.ev("window.__n")

    def wait_refreshes(self, k, timeout=40):
        n0 = self.refreshes()
        until(lambda: self.refreshes() >= n0 + k, timeout, f"{k} refresh(es)")

    def pick(self, needle):
        self.c.ev("document.getElementById('tab').dispatchEvent(new Event('focus'))")  # reload the tab list

        def sel():
            return self.c.ev("(() => { const s = document.getElementById('tab'); const o = [...s.options]"
                             f".find(o => o.textContent.includes({json.dumps(needle)}));"
                             " if (!o) return false; s.value = o.value; return true; })()")
        until(sel, 15, f"tab {needle} not listed")

    def record(self):
        self.c.ev("document.getElementById('record').click()")
        until(lambda: self.status().startswith("recording"), 40, "status never reached recording: " + self.status())

    def stop(self):
        self.c.ev("document.getElementById('stop').click()")
        until(lambda: self.status().startswith("off") and self.c.ev("document.getElementById('stop').disabled"),
              15, "stop: " + self.status())

    def raw(self):
        t = self.c.ev("document.getElementById('raw').textContent")
        return json.loads(t) if t else None

    def close(self):
        self.browser.close_tab(self.tid)
        self.c.close()


# ---------------------------------------------------------------------------- assertions
def http_rows(tables, path):
    return [r for r in tables["sends"] if r["via"] == "http" and r["endpoint"].split("?")[0].endswith(path)]


def strong(r, fpath, surface):
    """The encoding of the strong hit for `surface` on field `fpath`, or None."""
    for f in r["fields"]:
        if f["path"] == fpath:
            for h in f["strong"]:
                if h["surface"] == surface:
                    return h["encoding"]
    return None


def check_send(name, rows, kind, fpath, surface, by_ok=("frame",)):
    """kind None: not asserted. ws rows have no kinds."""
    if len(rows) != 1:
        row(name, False, f"{len(rows)} rows: {[(r['endpoint'], r['topic'], r['by'], r['count']) for r in rows]}")
        return
    r = rows[0]
    problems = []
    if r["count"] != 1:
        problems.append(f"count {r['count']}")
    if kind and r["kinds"] != {kind: 1}:
        problems.append(f"kinds {r['kinds']}")
    enc = strong(r, fpath, surface)
    if enc is None:
        problems.append(f"no strong {surface} hit on field {fpath}; fields "
                        f"{[(f['path'], f['strong']) for f in r['fields']]}")
    note = ""
    if r["by"] not in by_ok:
        problems.append(f"by {r['by']}")
    elif r["by"] != "frame":
        note = f" (by {r['by']}, the survey expects frame)"
    row(name, not problems, "; ".join(problems), info=f"{surface} {enc}{note}")


def read_count(tables, member):
    rows = [r for r in tables["reads"] if r["site"] == "http://127.0.0.1" and r["member"] == member]
    return rows, sum(r["count"] for r in rows)


def main_run(browser, site, frames):
    # Step 2-3: test page, then the observer. The page sends /pre/fetch-string at once.
    page_tid, page_c = browser.open(f"http://127.0.0.1:{site.port}/page.html")
    until(lambda: site.seen("/pre/fetch-string"), 30, "page never sent /pre/fetch-string")
    obs = Observer(browser)
    # Step 4
    obs.pick(f"127.0.0.1:{site.port}/page.html")
    obs.record()
    site.go = True
    # Step 5-6
    want = HTTP_PATHS + ["/s/redirected", "/done"]
    until(lambda: all(site.seen(p) for p in want) and len(frames) >= 3 and site.done, 60,
          f"page traffic incomplete: reqs {site.reqs}, frames {len(frames)}")
    obs.wait_refreshes(2)
    t = obs.raw()
    if t is None:
        raise RuntimeError("pre#raw empty after two refreshes: " + obs.status())

    # rows: pre-record
    pre = [r for r in t["sends"] if "/pre/" in r["endpoint"]]
    row("pre-record", not pre, f"{len(pre)} /pre/ rows")

    check_send("/s/fetch-string", http_rows(t, "/s/fetch-string"), "json", "w", "screen.width")
    check_send("/s/fetch-gzip", http_rows(t, "/s/fetch-gzip"), "json", "w", "screen.width")
    check_send("/s/fetch-blob", http_rows(t, "/s/fetch-blob"), "form", "res", "screen")
    check_send("/s/fetch-formdata", http_rows(t, "/s/fetch-formdata"), "multipart", "a.w", "screen.width")
    # the second field of the same row
    fr = http_rows(t, "/s/fetch-formdata")
    row("/s/fetch-formdata z", len(fr) == 1 and strong(fr[0], "z.w", "screen.width") is not None,
        "no strong screen.width on z.w")
    check_send("/s/fetch-usp", http_rows(t, "/s/fetch-usp"), "form", "tz", "timezone")
    check_send("/s/xhr-b64", http_rows(t, "/s/xhr-b64"), "json", "w", "screen.width")
    check_send("/s/beacon-blob", http_rows(t, "/s/beacon-blob"), "json", "d.w", "screen.width")
    check_send("/s/beacon-formdata", http_rows(t, "/s/beacon-formdata"), "multipart", "langs", "navigator.languages")
    check_send("/s/keepalive", http_rows(t, "/s/keepalive"), "json", "ua", "navigator.userAgent",
               by_ok=("frame", "site"))
    check_send("/r307", http_rows(t, "/r307"), None, "w", "screen.width")
    row("/r307 no /s/redirected row", not http_rows(t, "/s/redirected"), "a /s/redirected row exists")
    sj = http_rows(t, "/s/sjd")
    ok = len(sj) == 1 and sj[0]["sjd"] == [1, 0] and any(f["path"].startswith("sjd.") for f in sj[0]["fields"])
    row("/s/sjd", ok, f"rows {[(r['sjd'], [f['path'] for f in r['fields']]) for r in sj]}")
    ws = [r for r in t["sends"] if r["via"] == "ws" and r["endpoint"].endswith("/ws")]
    for name, topic in (("ws text", "(text)"), ("ws binary", "/t/x"), ("ws blob", "0d/(json)")):
        check_send(name, [r for r in ws if r["topic"] == topic], None, "w", "screen.width", by_ok=("frame", "site"))

    # reads, status, truth
    rows_w, nw = read_count(t, "Screen.width.get")
    row("reads Screen.width", nw == WIDTH_COUNT and all(r["by"] == "site" for r in rows_w),
        f"count {nw} (want {WIDTH_COUNT}), by {[r['by'] for r in rows_w]}")
    rows_h, nh = read_count(t, "Navigator.hardwareConcurrency.get")
    row("reads Navigator.hardwareConcurrency", nh == HWC_COUNT and all(r["by"] == "site" for r in rows_h),
        f"count {nh} (want {HWC_COUNT}), by {[r['by'] for r in rows_h]}")
    st = t["status"]
    row("status.lost == 0", st["lost"] == 0, f"lost {st['lost']}")
    row("status.self_reads > 0", st["self_reads"] > 0, f"self_reads {st['self_reads']}")
    row("status.truth_ok", st["truth_ok"] is True, f"truth_ok {st['truth_ok']}")
    d, tr = site.done, t["truth"]
    for name, key, val in (("screen.width", "screen.width", d["w"]), ("screen.height", "screen.height", d["h"]),
                           ("navigator.hardwareConcurrency", "navigator.hardwareConcurrency", d["hc"]),
                           ("navigator.deviceMemory", "navigator.deviceMemory", d["dm"]),
                           ("timezone", "timezone", d["tz"]), ("navigator.languages", "navigator.languages", d["langs"])):
        row(f"truth {name}", tr.get(key) == val, f"tables.truth {tr.get(key)!r} vs page {val!r}", info=repr(val))
    g, pg = tr.get("webgl.renderer"), d["gl"]
    row("truth webgl.renderer", g == pg, f"tables.truth {g!r} vs page {pg!r}")
    print(f"note webgl.renderer: {'both null' if g is None and pg is None else 'equal' if g == pg else 'differ'}")

    # Step 7: close the recorded tab; the recording survives (Review Focus 1)
    browser.close_tab(page_tid)
    page_c.close()
    obs.wait_refreshes(1)
    s7 = obs.status()
    row("review-focus tab-close keeps recording", s7.startswith("recording"), f"status {s7!r}")

    # Step 8: stop clears, nothing captured while off
    obs.stop()
    post_tid, post_c = browser.open(f"http://127.0.0.1:{site.port}/post.html")
    until(lambda: site.seen("/post/fetch-string"), 30, "post page never sent")
    obs.pick(f"127.0.0.1:{site.port}/post.html")
    obs.record()
    obs.wait_refreshes(1)
    t2 = obs.raw()
    bad = [r["endpoint"] for r in (t2 or {"sends": []})["sends"] if "/s/" in r["endpoint"] or "/post/" in r["endpoint"]]
    row("stop-clears", t2 is not None and not bad, f"raw {'empty' if t2 is None else 'rows ' + str(bad)}")

    # Step 9: close the observer right around a refresh; the browser survives (Review Focus 2)
    obs.wait_refreshes(1)
    time.sleep(4.8)  # the next refresh is due at 5 s
    obs.close()
    time.sleep(1)
    survived = browser.alive()
    obs2 = Observer(browser)
    try:
        obs2.pick(f"127.0.0.1:{site.port}/post.html")
        obs2.record()
        row("review-focus observer-close survives", survived and browser.alive(), "browser died")
    except Exception as e:  # noqa: BLE001
        row("review-focus observer-close survives", False, f"{type(e).__name__}: {e}")
    obs2.close()
    post_c.close()


def blind_run(site):
    browser = Browser(filter_env="-*,camou.none")
    try:
        _, pc = browser.open(f"http://127.0.0.1:{site.port}/post.html")
        until(lambda: site.seen("/post/fetch-string"), 30, "post page never sent")
        obs = Observer(browser)
        obs.pick(f"127.0.0.1:{site.port}/post.html")
        obs.c.ev("document.getElementById('record').click()")
        until(lambda: obs.status().startswith(("recording", "blind")), 40, "blind: " + obs.status())
        until(lambda: obs.status().startswith("blind"), 40, "never blind: " + obs.status())
        t = obs.raw()
        row("blind", t is not None and t["reads"] == [] and t["sends"] == [],
            f"reads {len((t or {}).get('reads', []))} sends {len((t or {}).get('sends', []))}")
    finally:
        browser.stop()


def main():
    server, ws_port, frames = lib_ws_server.start()
    site = Site(ws_port)
    browser = None
    try:
        browser = Browser()
        main_run(browser, site, frames)
    except Exception:  # noqa: BLE001 - rows not reached stay missing, which finish() fails
        traceback.print_exc()
    finally:
        if browser:
            browser.stop()
    try:
        blind_run(site)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    return finish()


if __name__ == "__main__":
    sys.exit(main())

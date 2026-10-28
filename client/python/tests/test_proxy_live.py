"""A real browser through a real local proxy. Skipped unless CAMOU_TEST_CHROME names a Chrome executable.

launch(proxy=...) once did nothing at all: the launcher drops Playwright's default argv, and --proxy-server is one
of its defaults, so a user's traffic went out on their real address. The fixture counts what reaches it."""
import http.server
import os
import pathlib
import sys
import threading

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import camoucrome  # noqa: E402

EXE = os.environ.get("CAMOU_TEST_CHROME")
pytestmark = pytest.mark.skipif(not EXE, reason="set CAMOU_TEST_CHROME to a Chrome executable")


class CountingProxy(http.server.ThreadingHTTPServer):
    """407 until Proxy-Authorization arrives; then 200 for a GET and 502 for a CONNECT (no tunnel is needed:
    the count is the point). `seen` is [(method, authenticated)]."""

    def __init__(self):
        proxy = self
        self.seen = []

        class H(http.server.BaseHTTPRequestHandler):
            def handle_any(self):
                authed = bool(self.headers.get("Proxy-Authorization"))
                if "example.test" in (self.path or ""):
                    proxy.seen.append((self.command, authed))
                if not authed:
                    self.send_response(407)
                    self.send_header("Proxy-Authenticate", 'Basic realm="t"')
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                body = b"<title>via-proxy</title>ok" if self.command == "GET" else b""
                self.send_response(200 if self.command == "GET" else 502)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_CONNECT = handle_any

            def log_message(self, *a):
                pass

        super().__init__(("127.0.0.1", 0), H)
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_port}"


@pytest.fixture
def proxy():
    p = CountingProxy()
    yield p
    p.shutdown()


@pytest.fixture
def pw():
    from patchright.sync_api import sync_playwright
    with sync_playwright() as p:
        yield p


def visit(pw, url, **kw):
    ctx = camoucrome.launch(pw, EXE, headless=True, **kw)
    try:
        page = ctx.new_page()
        try:
            page.goto(url, timeout=15000)
            return page.title()
        except Exception as e:  # noqa: BLE001 - the proxy's count is the assertion
            return f"ERR {str(e).splitlines()[0]}"
    finally:
        ctx.close()


def test_the_proxy_option_reaches_the_proxy_and_authenticates(pw, proxy):
    title = visit(pw, "http://example.test/", proxy={"server": proxy.url, "username": "u", "password": "p"})
    assert title == "via-proxy"
    assert ("GET", False) in proxy.seen and ("GET", True) in proxy.seen  # the 407, then the authenticated retry


def test_https_goes_through_connect(pw, proxy):
    visit(pw, "https://example.test/", proxy={"server": proxy.url, "username": "u", "password": "p"})
    assert ("CONNECT", True) in proxy.seen


def test_without_the_option_nothing_reaches_the_proxy(pw, proxy):
    assert visit(pw, "http://example.test/").startswith("ERR")
    assert proxy.seen == []

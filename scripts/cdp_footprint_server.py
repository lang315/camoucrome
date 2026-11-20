"""Loopback server of the CDP footprint harness: serves the probe page, receives its result."""
import http.server
import pathlib
import re
import threading
import time
import urllib.parse

HERE = pathlib.Path(__file__).parent
_NAME = re.compile(r"[A-Za-z0-9_-]+")
_FILE = re.compile(r"[A-Za-z0-9._-]+")


def serve(out_dir, delay_ms=50):
    out_dir = pathlib.Path(out_dir)

    class H(http.server.BaseHTTPRequestHandler):
        def _send(self, code, body=b"", ctype="text/plain"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _target(self, q):
            arm, run = q.get("arm", [""])[0], q.get("run", [""])[0]
            if _NAME.fullmatch(arm) and _NAME.fullmatch(run):
                return out_dir / f"{arm}-{run}.json"

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if u.path == "/probe.html":
                self._send(200, (HERE / "cdp_footprint" / "probe.html").read_bytes(), "text/html; charset=utf-8")
            elif u.path == "/delay":
                time.sleep(delay_ms / 1000)
                self._send(200, b"ok")
            elif u.path == "/done":
                f = self._target(q)
                self._send(200 if f and f.exists() else 404)
            elif u.path.startswith("/creepjs/"):
                name = urllib.parse.unquote(u.path[len("/creepjs/"):])
                f = HERE / "third_party" / "creepjs" / name
                if _FILE.fullmatch(name) and f.is_file():
                    ctype = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}.get(f.suffix, "application/octet-stream")
                    self._send(200, f.read_bytes(), ctype)
                else:
                    self._send(404)
            else:
                self._send(404)

        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            f = self._target(urllib.parse.parse_qs(u.query))
            if u.path != "/result" or f is None:
                return self._send(400)
            f.write_bytes(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            self._send(200)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_port

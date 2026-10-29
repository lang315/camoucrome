"""Local page for the dry runs of observe_drive.py (verify_observe_drive.py): http.server only, 127.0.0.1.

  /            40 000 px tall; on load a form POST to /ajax/bz, a sendBeacon to /ajax/bnzai, a sendBeacon with a Blob body to
               /ajax/qm/ (the body CDP does not carry) and a multipart POST to /ajax/mp, all carrying the value canary CANARY-7f3a9c; wheel events are counted into document.title as "wheels=<n>"
  /second      the same page with a comment of its own (so its bytes, and its file in resources/html, differ)
  /checkpoint/ a plain page, to trip the driver's checkpoint exit
  /app.js      the script `/` and `/second` include
Every POST answers 204.  --port 0 prints the chosen port as PORT=<n>.
"""
import argparse
import http.server
import threading

CANARY = "CANARY-7f3a9c"

APP_JS = f"""
fetch('/ajax/bz', {{method: 'POST', body: '__a=1&q=' + encodeURIComponent(JSON.stringify([{{name: '{CANARY}',
  dm: navigator.deviceMemory, tz: Intl.DateTimeFormat().resolvedOptions().timeZone}}]))}});
navigator.sendBeacon('/ajax/bnzai', JSON.stringify({{u: '{CANARY}-u'}}));
navigator.sendBeacon('/ajax/qm/', new Blob([JSON.stringify({{bl: '{CANARY}-blob', k: 7}})], {{type: 'text/plain'}}));
const fd = new FormData();
fd.append('__a', '1');
fd.append('q', JSON.stringify([{{name: '{CANARY}-mp', tz: Intl.DateTimeFormat().resolvedOptions().timeZone}}]));
fd.append('upload', new Blob([new Uint8Array(40)]), 'blob.bin');
fetch('/ajax/mp', {{method: 'POST', body: fd}});
let wheels = 0;
document.title = 'wheels=0';
addEventListener('wheel', () => {{ wheels += 1; document.title = 'wheels=' + wheels; }}, {{passive: true}});
"""


def page(tag):
    return (f"<!doctype html><title>wheels=0</title><!-- {tag} --><script src=\"/app.js\"></script>"
            "<div style=\"height:40000px\">tall</div>").encode()


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self._send(page("first"), "text/html")
        elif path == "/second":
            self._send(page("second"), "text/html")
        elif path.startswith("/checkpoint"):
            self._send(b"<!doctype html><title>checkpoint</title>checkpoint", "text/html")
        elif path == "/app.js":
            self._send(APP_JS.encode(), "text/javascript")
        else:
            self.send_error(404)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *a):
        pass


def serve(port=0):
    """(server, port): serving in a daemon thread."""
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_port


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    srv, port = serve(ap.parse_args().port)
    print(f"PORT={port}", flush=True)
    threading.Event().wait()

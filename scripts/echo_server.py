"""A local listener that records request headers, for UA-CH verification.

High-entropy client hints are not sent until the origin has advertised
Accept-CH, and then only from the next request onward. So the root document
both advertises the hints and references a same-origin subresource; the
headers worth asserting on are the subresource's, not the document's.
"""

import http.server
import threading


def start(accept_ch):
    records = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            records.append((self.path, dict(self.headers)))
            body = (b"<!doctype html><title>ua</title>"
                    b"<script src='/probe.js'></script>")
            self.send_response(200)
            self.send_header("Accept-CH", ", ".join(accept_ch))
            if self.path == "/probe.js":
                self.send_header("Content-Type", "application/javascript")
                body = b"/* probe */"
            else:
                self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass  # the test's own output is the only output that matters

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def headers_for(path):
        """Returns the LAST recorded headers for path, or None."""
        for recorded_path, headers in reversed(records):
            if recorded_path == path:
                return headers
        return None

    def stop():
        server.shutdown()
        server.server_close()

    return f"http://127.0.0.1:{server.server_port}/", headers_for, stop

"""Raw HTTP/1.1 loopback server of the driver probes: serves the probe pages and logs, for every request, the exact bytes
of the request line and headers (http.server parses them away, so it cannot be used)."""
import os
import pathlib
import re
import socket
import threading
import urllib.parse

PAGES = pathlib.Path(__file__).parent / "cdp_footprint"
_NAME = re.compile(r"[A-Za-z0-9_-]+")


def serve(out_dir):
    """Returns (listening socket, port, log); log gets (path with query, raw head bytes) per request, in arrival order."""
    out_dir = pathlib.Path(out_dir)
    log, lock = [], threading.Lock()

    def reply(c, code, body=b"", ctype="text/plain"):
        c.sendall(f"HTTP/1.1 {code} X\r\nContent-Type: {ctype}\r\nContent-Length: {len(body)}\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n".encode() + body)

    def handle(c):
        try:
            buf = b""
            while b"\r\n\r\n" not in buf:
                d = c.recv(65536)
                if not d:
                    return
                buf += d
            head, rest = buf.split(b"\r\n\r\n", 1)
            line = head.split(b"\r\n")[0].decode("latin-1")
            method, target, _ = line.split(" ", 2)
            u = urllib.parse.urlparse(target)
            with lock:
                log.append((target, head + b"\r\n\r\n"))
            m = re.search(rb"(?i)\r\ncontent-length:\s*(\d+)", head)
            n = int(m.group(1)) if m else 0
            while len(rest) < n:
                rest += c.recv(65536)
            q = urllib.parse.parse_qs(u.query)
            if method == "POST" and u.path == "/result":
                arm, run = q.get("arm", [""])[0], q.get("run", [""])[0]
                if not (_NAME.fullmatch(arm) and _NAME.fullmatch(run)):
                    return reply(c, 400)
                f = out_dir / f"{arm}-{run}.json"
                tmp = f.with_name(f.name + ".tmp")
                tmp.write_bytes(rest[:n])
                os.replace(tmp, f)
                reply(c, 200)
            elif u.path in ("/l9.html", "/h.html"):
                reply(c, 200, (PAGES / u.path[1:]).read_bytes(), "text/html; charset=utf-8")
            elif u.path == "/hdr":
                reply(c, 200, b"ok")
            else:
                reply(c, 404)
        except OSError:
            pass
        finally:
            c.close()

    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", 0))
    s.listen(64)

    def loop():
        while True:
            try:
                c, _ = s.accept()
            except OSError:
                return
            threading.Thread(target=handle, args=(c,), daemon=True).start()

    threading.Thread(target=loop, daemon=True).start()
    return s, s.getsockname()[1], log

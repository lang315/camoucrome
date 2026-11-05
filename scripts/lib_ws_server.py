#!/usr/bin/env python3
"""A stdlib RFC 6455 server on 127.0.0.1 for verifications.

start() -> (server, port, frames). `frames` collects (opcode, payload) of every
unmasked data frame (text/binary) the clients send, in arrival order. A text
frame `done` is not recorded; it is answered with a text frame `ok`, so a page
can wait for the server to have everything before it moves on.
shortcut: no fragmentation, no ping replies, payloads < 2**32; upgrade if a
verification sends continuation frames.
"""
import base64
import hashlib
import socketserver
import struct
import threading

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _read(rfile, n):
    data = rfile.read(n)
    if len(data) != n:
        raise EOFError
    return data


class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        key = None
        while True:
            line = self.rfile.readline()
            if line in (b"\r\n", b""):
                break
            if line.lower().startswith(b"sec-websocket-key:"):
                key = line.split(b":", 1)[1].strip().decode()
        if key is None:
            return
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        self.wfile.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                          f"Connection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n").encode())
        try:
            while True:
                b0, b1 = _read(self.rfile, 2)
                opcode, n = b0 & 0x0F, b1 & 0x7F
                if n == 126:
                    n = struct.unpack(">H", _read(self.rfile, 2))[0]
                elif n == 127:
                    n = struct.unpack(">Q", _read(self.rfile, 8))[0]
                mask = _read(self.rfile, 4) if b1 & 0x80 else b"\0\0\0\0"
                data = bytes(c ^ mask[i % 4] for i, c in enumerate(_read(self.rfile, n)))
                if opcode == 8:
                    self.wfile.write(b"\x88\x00")
                    return
                if opcode == 1 and data == b"done":
                    self.wfile.write(b"\x81\x02ok")
                elif opcode in (1, 2):
                    self.server.frames.append((opcode, data))
        except (EOFError, ConnectionError):
            return


class _Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def start():
    server = _Server(("127.0.0.1", 0), _Handler)
    server.frames = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1], server.frames

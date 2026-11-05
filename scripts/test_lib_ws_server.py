#!/usr/bin/env python3
"""lib_ws_server: a stdlib client handshakes, sends a masked text frame, a
masked binary frame and `done`; the server records the first two and answers ok."""
import base64
import hashlib
import os
import socket
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_ws_server  # noqa: E402

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def client_frame(opcode, payload):
    mask = b"\x01\x02\x03\x04"
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return bytes([0x80 | opcode, 0x80 | len(payload)]) + mask + masked


def read_exact(s, n):
    out = b""
    while len(out) < n:
        chunk = s.recv(n - len(out))
        assert chunk, "server closed"
        out += chunk
    return out


def test_roundtrip():
    server, port, frames = lib_ws_server.start()
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=5)
        key = base64.b64encode(os.urandom(16)).decode()
        s.sendall((f"GET /ws HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\n"
                   f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                   "Sec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            head += s.recv(1)
        want = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        assert b"101" in head.split(b"\r\n")[0]
        assert f"Sec-WebSocket-Accept: {want}".encode() in head
        s.sendall(client_frame(1, b"x") + client_frame(2, b"\x00\x01") + client_frame(1, b"done"))
        h = read_exact(s, 2)
        assert h[0] == 0x81 and h[1] == 2 and read_exact(s, 2) == b"ok"
        assert frames == [(1, b"x"), (2, b"\x00\x01")], frames
        s.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    test_roundtrip()
    print("ok")

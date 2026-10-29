"""x_server_answers: a headed launch needs an X server that ANSWERS, not just a socket that accepts."""
import os
import pathlib
import socket
import struct
import sys
import tempfile
import threading
import types

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
if "playwright.sync_api" not in sys.modules:  # as test_lib_shell_env: only session()/evaluate() need it
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        pkg, api = types.ModuleType("playwright"), types.ModuleType("playwright.sync_api")
        api.sync_playwright = None
        pkg.sync_api = api
        sys.modules.update({"playwright": pkg, "playwright.sync_api": api})
import lib_shell  # noqa: E402


@pytest.fixture
def xdir():
    # AF_UNIX paths are short: pytest's tmp_path can exceed the limit on macOS
    with tempfile.TemporaryDirectory(prefix="x") as d:
        yield d


def fake_x(xdir, n, reply):
    """A server on <xdir>/X<n> that reads the 12-byte setup request, then sends `reply` (None: never answers)."""
    srv = socket.socket(socket.AF_UNIX)
    srv.bind(os.path.join(xdir, f"X{n}"))
    srv.listen(4)
    held = []

    def serve():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            held.append(c)
            c.recv(12)
            if reply is not None:
                c.sendall(reply)
    threading.Thread(target=serve, daemon=True).start()
    return srv, held


def test_a_server_that_answers_the_setup_request_is_live(xdir):
    srv, _ = fake_x(xdir, 7, struct.pack("<BxHHHI", 1, 11, 0, 0, 0))
    try:
        assert lib_shell.x_server_answers(":7", timeout=2, sock_dir=xdir) is True
        assert lib_shell.x_server_answers(":7.0", timeout=2, sock_dir=xdir) is True  # screen suffix
    finally:
        srv.close()


def test_a_refusal_is_still_an_answer(xdir):
    srv, _ = fake_x(xdir, 8, struct.pack("<BBHHHH", 0, 0, 11, 0, 0, 0))  # status Failed: auth refused, but a server
    try:
        assert lib_shell.x_server_answers(":8", timeout=2, sock_dir=xdir) is True
    finally:
        srv.close()


def test_a_socket_that_accepts_and_never_answers_is_not_live(xdir):
    # the box on 2026-10-29: the WSLg X0 socket accepted connections and nothing behind it spoke; chrome waited 30 s and died
    srv, held = fake_x(xdir, 9, None)
    try:
        assert lib_shell.x_server_answers(":9", timeout=0.5, sock_dir=xdir) is False
    finally:
        srv.close()


@pytest.mark.parametrize("display", [None, "", "nonsense", ":", "host:0", ":99"])
def test_no_display_a_foreign_display_or_a_missing_socket_is_not_live(xdir, display):
    assert lib_shell.x_server_answers(display, timeout=0.5, sock_dir=xdir) is False

"""Fail UNMEASURED when `camoucrome` was imported from somewhere other than the intended client dir.

sys.path.insert(0, CLIENT/...) loses to a new-style editable install (a meta-path finder), so a stale
editable of an old checkout in the host venv shadows CAMOU_CLIENT and the verify measures the wrong client
(release -8: verify_webgpu_blocked row 4 read FAIL from it).
"""
import os
import pathlib
import sys

UNMEASURED = 3


def check(module, client):
    """None when module.__file__ is under client/client/python, else the message naming both paths."""
    want = pathlib.Path(os.path.realpath(pathlib.Path(client) / "client" / "python"))
    got = pathlib.Path(os.path.realpath(getattr(module, "__file__", None) or ""))
    if want in got.parents:
        return None
    return f"UNMEASURED: camoucrome imported from {got}, expected under {want}"


def require(module, client):
    """Exit UNMEASURED (3) with the message when check() fails."""
    problem = check(module, client)
    if problem:
        print(problem, file=sys.stderr)
        sys.exit(UNMEASURED)

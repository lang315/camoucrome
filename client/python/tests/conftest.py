import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camoucrome import gen  # noqa: E402


@pytest.fixture(autouse=True)
def _no_host_cpu_vendor(monkeypatch):
    """The suite's expectations do not depend on the machine's CPU: tests that need a vendor pass one.
    (scripts/conftest.py does the same: CI runs the two directories apart, so no shared conftest is collected.)"""
    monkeypatch.setattr(gen, "host_cpu_vendor", lambda: None)

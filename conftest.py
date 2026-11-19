import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "client" / "python"))
from camoucrome import gen  # noqa: E402


@pytest.fixture(autouse=True)
def _no_host_cpu_vendor(monkeypatch):
    """Every suite's expectations (client/python/tests and scripts/ alike) do not depend on the machine's CPU: tests that need a vendor pass one."""
    monkeypatch.setattr(gen, "host_cpu_vendor", lambda: None)

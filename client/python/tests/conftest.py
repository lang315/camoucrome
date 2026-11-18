import pytest

from camoucrome import gen


@pytest.fixture(autouse=True)
def _no_host_cpu_vendor(monkeypatch):
    """The suite's expectations do not depend on the machine's CPU: tests that need a vendor pass one."""
    monkeypatch.setattr(gen, "host_cpu_vendor", lambda: None)

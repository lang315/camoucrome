"""probe.host_renderer: hermetic cases use a fake launch; the live one needs a real browser."""
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camoucrome import probe  # noqa: E402


class FakePage:
    def __init__(self, value, boom):
        self.value, self.boom = value, boom

    def goto(self, url, **kw):
        if self.boom:
            raise RuntimeError("goto failed")

    def evaluate(self, js):
        return self.value


class FakeCtx:
    def __init__(self, value, boom=False):
        self.pages = [FakePage(value, boom)]
        self.closed = 0

    def close(self):
        self.closed += 1


def fake_pw(monkeypatch, ctx):
    class PW:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import patchright.sync_api as sa
    monkeypatch.setattr(sa, "sync_playwright", lambda: PW())
    monkeypatch.setattr(probe, "launch", lambda pw, exe, **kw: ctx)


def test_host_renderer_none_on_probe_failure(tmp_path):
    assert probe.host_renderer(str(tmp_path / "no-such-browser")) is None


@pytest.mark.parametrize("value", [None, "", 5, ["x"]])
def test_host_renderer_none_on_bad_result(monkeypatch, value):
    ctx = FakeCtx(value)
    fake_pw(monkeypatch, ctx)
    assert probe.host_renderer("x") is None
    assert ctx.closed == 1


def test_host_renderer_returns_string_and_closes(monkeypatch):
    ctx = FakeCtx("ANGLE (fake)")
    fake_pw(monkeypatch, ctx)
    assert probe.host_renderer("x") == "ANGLE (fake)"
    assert ctx.closed == 1


def test_host_renderer_closes_on_exception(monkeypatch):
    ctx = FakeCtx("ANGLE (fake)", boom=True)
    fake_pw(monkeypatch, ctx)
    assert probe.host_renderer("x") is None
    assert ctx.closed == 1


@pytest.mark.skipif(not os.environ.get("CAMOU_TEST_CHROME"), reason="needs a real browser")
def test_host_renderer_reads_a_real_string():
    r = probe.host_renderer(os.environ["CAMOU_TEST_CHROME"])
    assert r and r.startswith("ANGLE (")

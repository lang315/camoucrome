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
    def __init__(self, value, boom=False, close_boom=False):
        self.pages = [FakePage(value, boom)]
        self.closed = 0
        self.close_boom = close_boom

    def close(self):
        self.closed += 1
        if self.close_boom:
            raise RuntimeError("close failed")


def fake_pw(monkeypatch, ctx):
    class PW:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import patchright.sync_api as sa
    monkeypatch.setattr(sa, "sync_playwright", lambda: PW())
    calls = []

    def launch(pw, exe, **kw):
        calls.append(kw)
        if isinstance(ctx, Exception):
            raise ctx
        return ctx
    monkeypatch.setattr(probe, "launch", launch)
    return calls


def test_host_renderer_none_when_launch_raises(monkeypatch):
    fake_pw(monkeypatch, RuntimeError("no browser"))
    assert probe.host_renderer("x") is None


def test_host_renderer_none_for_missing_executable(tmp_path):
    pytest.importorskip("patchright")
    assert probe.host_renderer(str(tmp_path / "no-such-browser")) is None


@pytest.mark.parametrize("value", [
    "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)",
    "llvmpipe (LLVM 15.0.7, 256 bits)",
    "Google SwiftShader",
    "Mesa Software Rasterizer",
    "ANGLE (Microsoft, Microsoft Basic Render Driver (0x0000008C) Direct3D11 vs_5_0 ps_5_0, D3D11)",
])
def test_host_renderer_none_for_software_renderer(monkeypatch, value):
    ctx = FakeCtx(value)
    fake_pw(monkeypatch, ctx)
    assert probe.host_renderer("x") is None
    assert ctx.closed == 1


def test_host_renderer_keeps_hardware_string(monkeypatch):
    s = "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00009BC5) Direct3D11 vs_5_0 ps_5_0, D3D11)"
    fake_pw(monkeypatch, FakeCtx(s))
    assert probe.host_renderer("x") == s


def test_host_renderer_launches_headless_without_config(monkeypatch):
    calls = fake_pw(monkeypatch, FakeCtx("ANGLE (fake)"))
    probe.host_renderer("x")
    assert calls[0]["headless"] is True and "config" not in calls[0]


def test_host_renderer_survives_close_error(monkeypatch):
    ctx = FakeCtx("ANGLE (fake)", close_boom=True)
    fake_pw(monkeypatch, ctx)
    assert probe.host_renderer("x") == "ANGLE (fake)"
    assert ctx.closed == 1


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

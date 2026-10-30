"""host_screen (host-fit): a draw is acceptable only if its claimed work area, in physical px, fits the host's."""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camoucrome import gen, probe  # noqa: E402

KW = {"timezone": "UTC", "locale": "en-US"}
HOST = {"availWidth": 1366, "availHeight": 728}


def _gen(seed, **kw):
    return gen.generate("windows", seed=seed, **KW, **kw)


def _fits(g, host=HOST):
    c, dpr = g["config"], g["launch"]["dpr"]
    return c["screen.availWidth"] * dpr <= host["availWidth"] and c["screen.availHeight"] * dpr <= host["availHeight"]


def _seed(pred):
    return next(s for s in range(1, 300) if pred(_gen(s)))


def test_host_screen_makes_a_non_fitting_seed_fit():
    s = _seed(lambda g: not _fits(g))
    assert _fits(_gen(s, host_screen=HOST))


def test_no_host_screen_is_byte_identical():
    for s in (_seed(_fits), _seed(lambda g: not _fits(g))):
        assert _gen(s, host_screen=None) == _gen(s)


def test_light_and_host_screen_together():
    s = _seed(lambda g: not _fits(g) or g["launch"]["dpr"] != 1)
    g = _gen(s, light=True, host_screen=HOST)
    assert g["launch"]["dpr"] == 1 and _fits(g)


def test_cli_host_screen(capsys):
    s = _seed(lambda g: not _fits(g))
    gen.main(["--os", "windows", "--seed", str(s), "--timezone", "UTC", "--locale", "en-US", "--host-screen", json.dumps(HOST)])
    assert _fits(json.loads(capsys.readouterr().out))


@pytest.mark.parametrize("bad", ['{"availWidth":0,"availHeight":700}', '{"availWidth":"x","availHeight":700}',
                                 '{"availWidth":1366}', '[1366,728]', '{"availWidth":true,"availHeight":700}'])
def test_cli_rejects_a_malformed_host_screen(bad):
    with pytest.raises(SystemExit) as e:
        gen.main(["--os", "windows", "--seed", "1", "--host-screen", bad])
    assert "host-screen" in str(e.value)


def test_probe_host_screen_is_none_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert probe.host_screen() is None


@pytest.mark.skipif(sys.platform != "win32", reason="reads the Windows work area")
def test_probe_host_screen_on_windows():
    r = probe.host_screen()
    assert r and r["availWidth"] > 0 and r["availHeight"] > 0


def test_host_draw_carries_host_screen_and_drops_none(monkeypatch):
    for n in ("host_renderer", "host_display", "host_platform_version"):
        monkeypatch.setattr(probe, n, lambda exe: None)
    from camoucrome import hostfonts
    monkeypatch.setattr(hostfonts, "families", lambda: None)
    monkeypatch.setattr(probe, "host_screen", lambda: HOST)
    assert probe.host_draw("x")["host_screen"] == HOST
    monkeypatch.setattr(probe, "host_screen", lambda: None)
    assert "host_screen" not in probe.host_draw("x")

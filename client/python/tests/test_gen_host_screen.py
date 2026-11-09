"""host_screen (window fit): the claimed screen and DPR stay the pool's; the window is made to fit the host work area."""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camoucrome import gen, probe  # noqa: E402

KW = {"timezone": "UTC", "locale": "en-US"}
SMALL = {"availWidth": 1366, "availHeight": 728}
BIG = {"availWidth": 1920, "availHeight": 1032}


def _gen(seed, **kw):
    return gen.generate("windows", seed=seed, **KW, **kw)


def _inside(g, host):
    """The window, in physical px, lies inside the host work area: size and far edge, from the claimed work-area origin."""
    c, dpr = g["config"], g["launch"]["dpr"]
    ox, oy = c.get("screen.availLeft", 0), c.get("screen.availTop", 0)
    ow, oh = c["window.outerWidth"], c["window.outerHeight"]
    return (ow * dpr <= host["availWidth"] and oh * dpr <= host["availHeight"]
            and (c["window.screenX"] - ox + ow) * dpr <= host["availWidth"]
            and (c["window.screenY"] - oy + oh) * dpr <= host["availHeight"])


def _capped(seed, host):
    return _gen(seed)["config"]["window.outerHeight"] * _gen(seed)["launch"]["dpr"] > host["availHeight"]


def test_every_window_fits_the_host_and_none_raises():
    for s in range(1, 51):
        assert _inside(_gen(s, host_screen=SMALL), SMALL), s


def test_the_claimed_screen_and_dpr_stay_the_pools():
    for s in range(1, 51):
        a, b = _gen(s), _gen(s, host_screen=BIG)
        if a["launch"]["dpr"] > 2:  # 1032 / 2.5 is below MIN_WINDOW: that draw is rejected, not fitted
            continue
        assert (a["config"]["screen.width"], a["config"]["screen.height"], a["launch"]["dpr"]) == \
               (b["config"]["screen.width"], b["config"]["screen.height"], b["launch"]["dpr"])


def test_dpr_diversity_is_kept(capsys):
    share = lambda **kw: sum(_gen(s, **kw)["launch"]["dpr"] > 1 for s in range(1, 201)) / 200  # noqa: E731
    plain, fitted = share(), share(host_screen=BIG)
    print(f"dpr>1 share: plain {plain:.3f}, host_screen {fitted:.3f}")
    assert fitted > 0 and abs(fitted - plain) < 0.05


def test_capped_windows_differ_in_height():
    seeds = [s for s in range(1, 200) if _capped(s, SMALL)][:3]
    assert len(seeds) == 3
    assert len({_gen(s, host_screen=SMALL)["config"]["window.outerHeight"] for s in seeds}) >= 2


def test_no_host_screen_is_byte_identical():
    for s in (1, 2, 3, 4):
        assert _gen(s, host_screen=None) == _gen(s)


def test_light_and_host_screen_together():
    for s in range(1, 21):
        g = _gen(s, light=True, host_screen=SMALL)
        assert g["launch"]["dpr"] == 1 and _inside(g, SMALL)


def test_a_host_too_small_for_a_minimum_window_rejects_the_draw():
    tiny = {"availWidth": 700, "availHeight": 400}  # below MIN_WINDOW even at DPR 1
    with pytest.raises(RuntimeError):
        _gen(1, host_screen=tiny)


def test_cli_host_screen(capsys):
    s = next(s for s in range(1, 200) if _capped(s, SMALL))
    gen.main(["--os", "windows", "--seed", str(s), "--timezone", "UTC", "--locale", "en-US", "--host-screen", json.dumps(SMALL)])
    assert _inside(json.loads(capsys.readouterr().out), SMALL)


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
    monkeypatch.setattr(probe, "host_screen", lambda: SMALL)
    assert probe.host_draw("x")["host_screen"] == SMALL
    monkeypatch.setattr(probe, "host_screen", lambda: None)
    assert "host_screen" not in probe.host_draw("x")

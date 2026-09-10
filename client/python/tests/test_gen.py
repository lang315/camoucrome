"""Generator: literal pool samples in, coherent configs out. No browser."""
import json
import pathlib
import random
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camoucrome import gen  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[3]
KEYS = {k["key"] for k in json.loads((ROOT / "settings" / "keys.json").read_text())["keys"]}

POOL = {
    "navigator": {
        "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ... Chrome/147.0.0.0 Safari/537.36",
        "userAgentData": {"brands": [{"brand": "Google Chrome", "version": "147"}],
                          "mobile": False, "platform": "Windows", "architecture": "x86",
                          "bitness": "64", "model": "", "platformVersion": "10.0.0"},
        "language": "en-US", "languages": ["en-US", "en"], "platform": "Win32",
        "deviceMemory": 16, "hardwareConcurrency": 4, "maxTouchPoints": 0,
        "vendor": "Google Inc.", "appVersion": "5.0 (...)",
    },
    "screen": {"width": 1536, "height": 864, "availWidth": 1536, "availHeight": 864,
               "availLeft": 1920, "availTop": 30, "colorDepth": 32,
               "outerWidth": 1600, "outerHeight": 900, "screenX": 500, "screenY": 200,
               "devicePixelRatio": 1.25},
    "battery": {"charging": True, "chargingTime": 600, "dischargingTime": None, "level": 0.99},
    "multimediaDevices": {"speakers": [{}], "micros": [{}], "webcams": []},
    "videoCard": {"renderer": "ANGLE (AMD, ...)", "vendor": "Google Inc. (AMD)"},
    "fonts": ["Calibri"],
}


def test_every_emitted_key_is_a_registered_key():
    out = gen.from_pool(POOL, "Europe/Paris", rng=random.Random(1))
    assert set(out["config"]) <= KEYS, set(out["config"]) - KEYS


def test_never_taken_fields_stay_out():
    cfg = gen.from_pool(POOL, "UTC", rng=random.Random(1))["config"]
    for k in ("navigator.userAgent", "navigator.platform", "navigator.vendor",
              "navigator.appVersion", "screen.colorDepth", "screen.availLeft",
              "screen.availTop", "webGl:renderer", "webGl:vendor", "fonts:list"):
        assert k not in cfg, k


def test_geometry_is_coherent_after_the_helpers():
    cfg = gen.from_pool(POOL, "UTC", rng=random.Random(1))["config"]
    # avail == screen in the pool -> taskbar applied; outer 1600x900 clamped.
    assert cfg["screen.availHeight"] == 864 - 40 and cfg["screen.availWidth"] == 1536
    assert cfg["window.outerWidth"] == 1536 and cfg["window.outerHeight"] == 824  # 824 % 4 == 0
    assert cfg["window.screenX"] == 0 and cfg["window.screenY"] == 40
    out = gen.from_pool(POOL, "UTC", rng=random.Random(1))
    assert out["launch"] == {"window": [1534, 822], "dpr": 1.25}


def test_locale_and_timezone():
    cfg = gen.from_pool(POOL, "America/New_York", rng=random.Random(1))["config"]
    assert (cfg["locale:tag"], cfg["navigator.language"], cfg["navigator.languages"],
            cfg["timezone:id"]) == ("en-US", "en-US", ["en-US", "en"], "America/New_York")
    cfg = gen.from_pool(POOL, "Europe/Paris", locale="fr-FR", rng=random.Random(1))["config"]
    assert cfg["navigator.languages"] == ["fr-FR", "fr"] and cfg["locale:tag"] == "fr-FR"


def test_ua_battery_media_and_seeds():
    cfg = gen.from_pool(POOL, "UTC", rng=random.Random(1))["config"]
    assert cfg["ua:osInfo"] == "Windows NT 10.0; Win64; x64" and cfg["ua:platform"] == "Windows"
    assert cfg["ua:platformVersion"] == "10.0.0" and cfg["ua:mobile"] is False
    assert cfg["battery:charging"] is True and cfg["battery:chargingTime"] == 600.0
    assert "battery:dischargingTime" not in cfg
    assert cfg["mediaDevices:enabled"] is True and cfg["mediaDevices:webcams"] == 0
    assert all(1 <= cfg[k] <= 0xFFFFFFFF for k in ("canvas:seed", "audio:seed", "mediaDevices:seed"))


def test_os_forms_match_derive_cc():
    src = (ROOT / "additions" / "camoucfg" / "derive.cc").read_text()
    rows = re.findall(r'\{OsFamily::k\w+, "([^"]+)", "([^"]+)", "[^"]+"\}', src)
    cpp = {plat: (info, plat) for plat, info in rows if plat in gen.OS_FORMS}
    assert cpp == gen.OS_FORMS


def test_filter_redraws_brave_edge_mobile_and_unknown_platform():
    ok = json.loads(json.dumps(POOL))
    assert gen.acceptable(ok)
    for mutate in (lambda f: f["navigator"]["userAgentData"]["brands"].append({"brand": "Brave", "version": "147"}),
                   lambda f: f["navigator"]["userAgentData"].update(mobile=True),
                   lambda f: f["navigator"]["userAgentData"].update(platform="")):
        bad = json.loads(json.dumps(POOL))
        mutate(bad)
        assert not gen.acceptable(bad)


def test_timezone_is_required():
    with pytest.raises(ValueError, match="timezone"):
        gen.generate(os="windows")


def test_generate_from_the_real_pool_is_registered_and_deterministic():
    pytest.importorskip("browserforge")
    a = gen.generate(os="windows", timezone="UTC", seed=3)
    b = gen.generate(os="windows", timezone="UTC", seed=3)
    assert a == b and set(a["config"]) <= KEYS
    assert a["config"]["ua:platform"] == "Windows" and a["launch"]["window"][0] > 0


def test_launch_window_carries_the_measured_dpr_offset():
    pool = json.loads(json.dumps(POOL))
    pool["screen"].update(outerWidth=1530, outerHeight=901, width=2000, height=1200,
                          availWidth=2000, availHeight=1160)
    out = gen.from_pool(pool, "UTC", rng=random.Random(1))
    assert out["config"]["window.outerWidth"] == 1530 and out["config"]["window.outerHeight"] == 901
    assert out["launch"] == {"window": [1528, 899], "dpr": 1.25}
    pool["screen"]["devicePixelRatio"] = 2
    assert gen.from_pool(pool, "UTC", rng=random.Random(1))["launch"] == {"window": [1530, 901], "dpr": 2}
    odd = json.loads(json.dumps(POOL))
    odd["screen"]["devicePixelRatio"] = 1.2145832777023315
    assert not gen.acceptable(odd)

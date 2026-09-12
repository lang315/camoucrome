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
              "screen.availTop"):
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
    assert cfg["navigator.deviceMemory"] == 8  # the sample says 16, Chrome caps at 8
    assert gen.chrome_device_memory(32) == 8 and gen.chrome_device_memory(3) == 2 and gen.chrome_device_memory(0.1) == 0.25
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


def test_timezone_is_required_only_for_a_locale_outside_the_table():
    with pytest.raises(ValueError, match="timezone"):
        gen.from_pool(POOL, None, "xx-ZZ", rng=random.Random(1))


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


def test_pool_wide_properties_hold_over_unseeded_draws():
    """The fixed-seed oracle cannot see pool oddities; 200 unseeded draws can."""
    pytest.importorskip("browserforge")
    for i in range(200):
        out = gen.generate(timezone="UTC")
        cfg, launch = out["config"], out["launch"]
        assert cfg["navigator.deviceMemory"] in gen.DEVICE_MEMORY, cfg["navigator.deviceMemory"]
        assert cfg["navigator.hardwareConcurrency"] >= 1
        assert launch["dpr"] in gen.WINDOW_OFFSET
        for axis in ("Width", "Height"):
            assert cfg[f"window.outer{axis}"] <= cfg[f"screen.avail{axis}"] <= cfg[f"screen.{axis.lower()}"], (i, cfg)
        assert cfg["navigator.languages"][0] == cfg["navigator.language"] == cfg["locale:tag"]
        assert 0 <= cfg["window.screenX"] <= cfg["screen.width"] - cfg["window.outerWidth"]
        assert set(cfg) <= KEYS


def test_webgl_profile_keys_follow_the_claimed_os():
    profiles = gen.load_profiles()
    assert "windows-intel-uhd-630-d3d11" in profiles
    keys = gen.webgl_keys(profiles["windows-intel-uhd-630-d3d11"])
    assert set(keys) == {"webGl:vendor", "webGl:renderer", "webGl2:vendor", "webGl2:renderer",
                         "webGl:parameters", "webGl2:parameters", "webGl:supportedExtensions", "webGl2:supportedExtensions",
                         "webGl:shaderPrecisionFormats", "webGl2:shaderPrecisionFormats"}
    assert keys["webGl:shaderPrecisionFormats"]["35633:36338"] == [127, 127, 23]  # VERTEX_SHADER, HIGH_FLOAT
    assert set(keys) <= KEYS
    assert "Direct3D11" in keys["webGl:renderer"] and keys["webGl2:renderer"] == keys["webGl:renderer"]
    assert all(k.isdigit() for k in keys["webGl:parameters"])


def test_from_pool_picks_the_os_profile_and_gpu_overrides():
    out = gen.from_pool(POOL, "America/New_York", rng=random.Random(1))
    assert "Direct3D11" in out["config"]["webGl:renderer"]
    mac = gen.from_pool(POOL, "America/New_York", rng=random.Random(1), gpu="macos-apple-m1-pro-metal")
    assert "Metal" in mac["config"]["webGl:renderer"]
    with pytest.raises(KeyError):
        gen.from_pool(POOL, "America/New_York", rng=random.Random(1), gpu="no-such-profile")


def test_zone_table_is_valid_iana_and_tags_parse():
    import zoneinfo
    table = json.loads((ROOT / "settings" / "locale_zones.json").read_text())["zones"]
    assert len(table) >= 40
    avail = zoneinfo.available_timezones()
    for tag, zones in table.items():
        assert re.fullmatch(r"[a-z]{2,3}-[A-Z]{2}", tag), tag
        assert zones and all(z in avail for z in zones), tag


def test_timezone_defaults_from_the_locale_table():
    out = gen.from_pool(POOL, None, "fr-FR", rng=random.Random(3))
    assert out["config"]["timezone:id"] == "Europe/Paris"
    a = gen.from_pool(POOL, None, None, rng=random.Random(5))["config"]["timezone:id"]
    b = gen.from_pool(POOL, None, None, rng=random.Random(5))["config"]["timezone:id"]
    assert a == b and a in {"America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles"}
    with pytest.raises(ValueError, match="no locale->zone"):
        gen.from_pool(POOL, None, "xx-ZZ", rng=random.Random(1))


def test_fonts_keys_carry_unique_names_and_the_platform_version_follows_the_list():
    k = gen.fonts_keys("Windows")
    assert "SegoeUI" not in k["fonts:list"] and k["fonts:aliasLocal"]["SegoeUI"] == "Selawik" and "SegoeUI" not in k["fonts:alias"]
    assert k["fonts:aliasLocal"]["Georgia"] == "Gelasio Regular" and k["fonts:alias"]["Georgia"] == "Gelasio"
    assert k["fonts:alias"]["Segoe UI"] == "Selawik" and k["ua:platformVersion"] == "10.0.0"
    assert gen.fonts_keys("macOS")["ua:platformVersion"] == gen.json.loads(
        (gen.ROOT / "settings" / "fonts.json").read_text(encoding="utf-8"))["families"]["macOS"]["platform_version"]
    m = gen.fonts_keys("macOS")  # stock macOS resolves PostScript names as CSS families; Windows does not
    assert "HelveticaNeue-Bold" in m["fonts:list"] and m["fonts:alias"]["HelveticaNeue-Bold"] == "Inter Variable"
    assert m["fonts:aliasLocal"]["HelveticaNeue-Bold"] == "Inter Variable" and "HelveticaNeue-Bold" not in k["fonts:alias"]
    assert gen.fonts_keys("Linux") == {}


def test_brand_voices_and_local_faces_follow_the_windows_claim():
    cfg = gen.from_pool(POOL, "UTC", rng=random.Random(1))["config"]
    assert cfg["ua:brand"] == "Google Chrome"
    assert [v["name"] for v in cfg["voices:list"]] == ["Microsoft David - English (United States)", "Microsoft Mark - English (United States)", "Microsoft Zira - English (United States)"]
    assert cfg["voices:list"][0]["default"] is True and cfg["voices:list"][0]["voiceURI"] == cfg["voices:list"][0]["name"]
    faces = cfg["fonts:local"]
    assert len(faces) > 150 and all(len(f.split("\t")) == 4 for f in faces) and "SegoeUI\tSegoe UI\tSegoe UI\tRegular" in faces
    assert faces == sorted(faces)  # stock returns them sorted by PostScript name
    assert not any(f.startswith("Selawik") for f in faces)
    assert gen.voices_keys("Linux") == {}


def test_local_faces_exist_for_every_os_with_a_list_and_are_never_empty():
    for os_name in ("Windows", "macOS"):
        faces = gen.fonts_keys(os_name)["fonts:local"]
        assert len(faces) > 150 and faces == sorted(faces), os_name


def test_voices_follow_the_locale_and_share_cancel_is_human_paced():
    fr = gen.from_pool(POOL, "Europe/Paris", locale="fr-FR", rng=random.Random(1))["config"]
    assert [v["name"] for v in fr["voices:list"]] == ["Microsoft Hortense - French (France)", "Microsoft Julie - French (France)", "Microsoft Paul - French (France)"]
    assert all(v["lang"] == "fr-FR" for v in fr["voices:list"]) and fr["voices:list"][0]["default"] is True
    assert gen.voices_keys("Windows", "en-NZ")["voices:list"][0]["lang"] == "en-AU"   # same language, first row
    assert gen.voices_keys("Windows", "uk-UA")["voices:list"][0]["lang"] == "en-US"   # no Ukrainian pack: en-US
    assert 900 <= fr["share:cancelMs"] <= 2600
    assert "share:cancelMs" not in gen.from_pool(dict(POOL, navigator=dict(POOL["navigator"], userAgentData=dict(POOL["navigator"]["userAgentData"], platform="Linux"))), "UTC", rng=random.Random(1))["config"]


def test_mac_voices_are_the_measured_list_and_sample_rate_follows_the_claim():
    win = gen.from_pool(POOL, "UTC", rng=random.Random(1))["config"]
    assert win["audio:sampleRate"] == 48000
    assert gen.voices_keys("macOS", "fr-FR")["voices:list"] == gen.voices_keys("macOS")["voices:list"]
    assert len(gen.voices_keys("macOS")["voices:list"]) > 100 and gen.audio_keys("macOS") == {"audio:sampleRate": 48000}
    assert gen.audio_keys("Linux") == {}

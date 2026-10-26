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


def test_a_pool_position_inside_the_work_area_is_kept():
    pool = json.loads(json.dumps(POOL))
    pool["screen"].update(outerWidth=1400, outerHeight=700, screenX=30, screenY=20)
    cfg = gen.from_pool(pool, "UTC", rng=random.Random(1))["config"]
    assert (cfg["window.screenX"], cfg["window.screenY"], cfg["window.outerWidth"], cfg["window.outerHeight"]) == (30, 20, 1400, 700)


def test_geometry_is_coherent_after_the_helpers():
    cfg = gen.from_pool(POOL, "UTC", rng=random.Random(1))["config"]
    # avail == screen in the pool -> taskbar applied; outer 1600x900 clamped.
    assert cfg["screen.availHeight"] == 864 - 40 and cfg["screen.availWidth"] == 1536
    # pool window 1536x824 at (0, 0): gen.window_position draws the offset (66, 75) for this rng (a pinned draw,
    # not a pool value) and the window shrinks by it, so it ends at the work-area corner: 66+1470, 75+749
    assert (cfg["window.screenX"], cfg["window.screenY"]) == (66, 75)
    assert (cfg["window.outerWidth"], cfg["window.outerHeight"]) == (1470, 749)
    assert 66 + 1470 == 1536 and 75 + 749 == 824
    out = gen.from_pool(POOL, "UTC", rng=random.Random(1))
    assert out["launch"] == {"window": [1468, 747], "dpr": 1.25, "args": [],
                             "position": [cfg["window.screenX"], cfg["window.screenY"]]}


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
    assert {k: out["launch"][k] for k in ("window", "dpr")} == {"window": [1528, 899], "dpr": 1.25}
    pool["screen"]["devicePixelRatio"] = 2
    two = gen.from_pool(pool, "UTC", rng=random.Random(1))["launch"]
    assert {k: two[k] for k in ("window", "dpr")} == {"window": [1530, 901], "dpr": 2}
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
    if not avail:  # Windows ships no IANA database; zoneinfo reads the tzdata package
        pytest.skip("no IANA time zone database: pip install tzdata")
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
    assert [v["name"] for v in cfg["voices:list"][:3]] == ["Microsoft David - English (United States)", "Microsoft Mark - English (United States)", "Microsoft Zira - English (United States)"]
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
    assert [v["name"] for v in fr["voices:list"][:3]] == ["Microsoft Hortense - French (France)", "Microsoft Julie - French (France)", "Microsoft Paul - French (France)"]
    assert all(v["lang"] == "fr-FR" for v in fr["voices:list"][:3]) and fr["voices:list"][0]["default"] is True
    assert gen.voices_keys("Windows", "en-NZ")["voices:list"][0]["lang"] == "en-AU"   # same language, first row
    assert gen.voices_keys("Windows", "uk-UA")["voices:list"][0]["lang"] == "en-US"   # no Ukrainian pack: en-US
    assert 900 <= fr["share:cancelMs"] <= 2600
    assert "share:cancelMs" not in gen.from_pool(dict(POOL, navigator=dict(POOL["navigator"], userAgentData=dict(POOL["navigator"]["userAgentData"], platform="Linux"))), "UTC", rng=random.Random(1))["config"]


def test_mac_voices_are_the_measured_list_and_sample_rate_follows_the_claim():
    win = gen.from_pool(POOL, "UTC", rng=random.Random(1))["config"]
    assert win["audio:sampleRate"] == 44100
    assert gen.voices_keys("macOS", "fr-FR")["voices:list"] == gen.voices_keys("macOS")["voices:list"]
    assert len(gen.voices_keys("macOS")["voices:list"]) > 100 and gen.audio_keys("macOS")["audio:sampleRate"] == 48000
    assert gen.audio_keys("Linux") == {}


def test_buffer_frames_follow_the_rate_and_linux_keeps_its_real_platform_version():
    win = gen.from_pool(POOL, "UTC", rng=random.Random(1))["config"]
    assert win["audio:bufferFrames"] == 441 and win["audio:bufferFrames"] / win["audio:sampleRate"] == 0.01
    assert gen.audio_keys("macOS")["audio:bufferFrames"] == 256
    lin = json.loads(json.dumps(POOL)); lin["navigator"]["userAgentData"]["platform"] = "Linux"; lin["navigator"]["userAgentData"]["platformVersion"] = ""
    cfg = gen.from_pool(lin, "UTC", rng=random.Random(1))["config"]
    assert "ua:platformVersion" not in cfg and cfg["ua:platform"] == "Linux"


def test_remote_google_voices_follow_the_local_row():
    # The table copied from the 154.0.8037.93 host oracle; stock 156 on the host lists no Google voices (2026-10-21).
    remote = [[v["name"], v["lang"]] for v in json.loads((ROOT / "settings" / "voices.json").read_text(encoding="utf-8"))["remote"]]
    assert len(remote) == 19
    for plat, loc, n_local in [("Windows", "en-US", 3), ("Windows", "fr-FR", 3), ("Windows", "uk-UA", 3), ("macOS", "en-US", 191)]:
        vl = gen.voices_keys(plat, loc)["voices:list"]
        assert len(vl) == n_local + 19
        assert all(v["localService"] for v in vl[:n_local])
        assert [[v["name"], v["lang"]] for v in vl[n_local:]] == remote
        assert all(v["localService"] is False and v["default"] is False and v["voiceURI"] == v["name"] for v in vl[n_local:])
        assert [v["default"] for v in vl].count(True) == 1 and vl[0]["default"] is True
    assert gen.voices_keys("Linux") == {}


def test_quickstart_seeds_keep_a_profile_and_tell_two_apart():
    pytest.importorskip("browserforge")
    one, again, two = (gen.generate(os="windows", seed=s) for s in (1, 1, 2))
    assert one == again and one != two


def test_load_profiles_ignores_the_gpu_pool_file():
    assert not any(stem.endswith("-pool") for stem in gen.load_profiles())


HOST = "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00009BC5) Direct3D11 vs_5_0 ps_5_0, D3D11)"


def test_gen9_host_swaps_only_name_and_device_id():
    base = gen.profile_for("Windows")
    prof, warn = gen.gpu_for("Windows", HOST, random.Random(3))
    assert warn is None
    assert gen.gen9_device_id(prof["renderer"]) is not None
    assert prof["webgl"] == base["webgl"] and prof["webgl2"] == base["webgl2"]
    assert prof["vendor"] == base["vendor"] == "Google Inc. (Intel)"


def test_gpu_draw_is_seed_stable_and_varies_across_seeds():
    draws = {gen.gpu_for("Windows", HOST, random.Random(s))[0]["renderer"] for s in range(40)}
    assert gen.gpu_for("Windows", HOST, random.Random(7))[0] == gen.gpu_for("Windows", HOST, random.Random(7))[0]
    assert len(draws) >= 3


def test_gpu_draw_does_not_advance_the_rng():
    rng = random.Random(5)
    state = rng.getstate()
    gen.gpu_for("Windows", HOST, rng)
    assert rng.getstate() == state


def test_non_gen9_host_keeps_real_gpu_and_warns():
    nv = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002504) Direct3D11 vs_5_0 ps_5_0, D3D11)"
    prof, warn = gen.gpu_for("Windows", nv, random.Random(1))
    assert prof is None and "shared" in warn


@pytest.mark.parametrize("host", [
    "ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)",
    "ANGLE (Intel, Mesa Intel(R) UHD Graphics 630 (CFL GT2), OpenGL 4.6)"])
def test_non_windows_host_renderer_keeps_the_default_profile_and_warns(host):
    prof, warn = gen.gpu_for("Windows", host, random.Random(1))
    assert prof == gen.profile_for("Windows") and "not a Windows D3D11" in warn


def test_warning_does_not_call_other_intel_parts_non_gen9():
    odd = "ANGLE (Intel, Intel(R) HD Graphics 530 (0x00001912) Direct3D11 vs_5_0 ps_5_0, D3D11)"
    assert "not in the supported Intel Gen9 set" in gen.gpu_for("Windows", odd, random.Random(1))[1]


def test_gen9_regex_equals_the_pool_scripts():
    sys.path.insert(0, str(ROOT / "scripts"))
    import gen_gpu_pool
    assert gen.GEN9_RE.pattern == gen_gpu_pool.RENDERER_RE.pattern


def test_gen9_name_with_unknown_device_id_keeps_real_gpu():
    odd = "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x0000FFFF) Direct3D11 vs_5_0 ps_5_0, D3D11)"
    prof, warn = gen.gpu_for("Windows", odd, random.Random(1))
    assert prof is None and warn


def test_no_host_renderer_keeps_todays_behaviour_and_warns():
    prof, warn = gen.gpu_for("Windows", None, random.Random(1))
    assert prof == gen.profile_for("Windows") and warn


def test_pool_file_declares_its_weights_are_an_assumption():
    assert gen.gen9_pool()["weights_how"].startswith("assumption:")


def test_non_gen9_host_emits_no_webgl_keys():
    nv = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002504) Direct3D11 vs_5_0 ps_5_0, D3D11)"
    r = gen.generate("windows", "Europe/Paris", None, 1, host_renderer=nv)
    assert not [k for k in r["config"] if k.startswith(("webGl:", "webGl2:"))]
    assert r["warnings"] and "shared" in r["warnings"][0]


def test_generate_with_host_renderer_draws_a_gen9_identity():
    r = gen.generate("windows", "Europe/Paris", None, 1, host_renderer=HOST)
    assert gen.gen9_device_id(r["config"]["webGl:renderer"]) is not None
    assert r["config"]["webGl2:renderer"] == r["config"]["webGl:renderer"]
    assert r["warnings"] == []


# Pinned from the code before the GPU draw and the font plumbing (seeds 1..3, windows, Europe/Paris).
# seed 1 "rest" recomputed on the pre-final-review code without window.screenX/Y, window.outerWidth/Height,
# launch.window and launch.position: those five are pinned in test_gen_linkability; the pin covers every other key.
PRE_CHANGE = {
    1: {"share:cancelMs": 2543, "canvas:seed": 577090038, "audio:seed": 2444712011, "mediaDevices:seed": 3639700192,
        "rest": "cfc63531725c99cb"},
    2: {"share:cancelMs": 1015, "canvas:seed": 4106135924, "audio:seed": 3707026330, "mediaDevices:seed": 4070888060},
    3: {"share:cancelMs": 1167, "canvas:seed": 1022050302, "audio:seed": 2545373331, "mediaDevices:seed": 2337446731},
}


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_seeded_keys_do_not_move(seed):
    cfg = gen.generate("windows", "Europe/Paris", None, seed)["config"]
    assert {k: cfg[k] for k in ("share:cancelMs", "canvas:seed", "audio:seed", "mediaDevices:seed")} == \
        {k: v for k, v in PRE_CHANGE[seed].items() if k != "rest"}


def test_default_args_output_is_unchanged_outside_the_font_subset():
    """Passing rng to fonts_keys draws a font subset (Task 7's intent), so fonts:* is
    excluded; every other key and launch must be byte-identical to the pre-change run."""
    import hashlib
    r = gen.generate("windows", "Europe/Paris", None, 1)
    # the window position is drawn since Task 6 (test_gen_linkability pins it), so it is excluded too
    rest = {k: v for k, v in r["config"].items()
            if not k.startswith("fonts:") and k not in ("window.screenX", "window.screenY",
                                                                  "window.outerWidth", "window.outerHeight")}
    launch = {k: v for k, v in r["launch"].items() if k not in ("position", "args", "window")}
    assert hashlib.sha256(json.dumps([rest, launch], sort_keys=True).encode()).hexdigest()[:16] == PRE_CHANGE[1]["rest"]


def test_host_families_limit_fonts_list_and_alias_local():
    fam = json.loads((ROOT / "settings" / "fonts.json").read_text(encoding="utf-8"))["families"]["Windows"]
    gone = next(f for f in fam["base"] if any(v["family"] == f for v in fam["unique_names"].values()))
    host = set(fam["base"]) - {gone}
    base = gen.generate("windows", "Europe/Paris", None, 1)["config"]
    r = gen.generate("windows", "Europe/Paris", None, 1, host_families=host)["config"]
    assert gone in base["fonts:list"] and gone not in r["fonts:list"]
    names = {n for n, v in fam["unique_names"].items() if v["family"] == gone}
    assert names & set(base["fonts:aliasLocal"]) and not names & set(r["fonts:aliasLocal"])

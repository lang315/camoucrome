"""Fingerprint generator, v1: a coherent CAMOU_CONFIG from BrowserForge's
Chrome pool plus the launcher options that go with it.

    python -m camoucrome.gen --os windows --timezone Europe/Paris [--locale fr-FR] [--seed N]
    -> {"config": {...}, "launch": {"window": [w, h], "dpr": x}}

Pool field -> config key (mirrors the preset loader's table style):

  userAgentData.platform          -> ua:osInfo, ua:platform (canonical forms, OS_FORMS)
  userAgentData.platformVersion/architecture/bitness/model/mobile
                                  -> ua:platformVersion, ua:architecture, ua:bitness,
                                     ua:model, ua:mobile; ua:wow64 false
  navigator.hardwareConcurrency, maxTouchPoints -> same-named keys
  navigator.deviceMemory           -> snapped to Chrome's set {0.25..8} (DEVICE_MEMORY);
                                     the pool says 16/32 in half its samples
  screen.width/height/availWidth/availHeight -> screen.*
  screen.outerWidth/outerHeight/screenX/screenY -> window.*, and launch.window
  screen.devicePixelRatio          -> launch.dpr (a launcher flag; DPR has no key);
                                     launch.window = outer minus WINDOW_OFFSET[dpr]
  navigator.language / languages   -> locale:tag, navigator.language, navigator.languages
                                     (--locale replaces all three; the head always equals
                                     navigator.language)
  --timezone (required)            -> timezone:id  (no locale->zone table exists; an
                                     unset zone beside locale:tag trips
                                     timezone-set-with-locale at startup)
  battery.*                        -> battery:charging, battery:level, and the two
                                     times when the pool has them
  multimediaDevices                -> mediaDevices:enabled + the three counts
  per_instance_config()            -> canvas:seed, audio:seed, mediaDevices:seed

Never taken, and why:
  navigator.userAgent, appVersion, brands, fullVersionList, headers
                                   version-bearing; the fork's own milestone produces them
  navigator.platform, vendor, product*, appName, appCodeName
                                   derived or constant in the fork already
  screen.colorDepth / pixelDepth   the pool says 32 where real Chrome reports 24/30; the
                                   real value is coherent by construction
  screen.availLeft / availTop      multi-monitor offsets from the pool; the real 0 is fine
  videoCard (webGl:*)              the pool's strings are not taken; webGl:* comes from
                                   settings/webgl/ instead -- real-GPU captures whose
                                   parameter table matches the identity (A3 #2); --gpu
                                   picks one, default the first profile for the claimed OS
  fonts                            fonts:list is the captured family list of the claimed OS
                                   (settings/fonts.json), which the bundled fontconfig
                                   layer makes resolvable; Linux claims get none
  voices, geolocation              Chrome voice names and GeoIP are their own catalogues;
                                   timezone:id without --timezone comes from
                                   settings/locale_zones.json by locale

Samples whose brands name Brave (font enumeration is farbled there) or Edge,
that are mobile, or that carry no UA-CH platform are redrawn.

Three helpers are copied from camoufox/pythonlib/camoufox/fingerprints.py
(lang315/camoufox aa67f7b, 2026-09-10), reduced to the keys this fork has:
fix_screen_no_taskbar, clamp_window_dimensions, clamp_window_position. SP6
4.5 asked for a shared core rather than a copy; three functions of ~60 lines
are copied instead, revisit when a second target appears or they diverge.
"""
import argparse
import json
import pathlib
import random
import sys
from dataclasses import asdict

from .identity import per_instance_config

# derive.cc's kForms: UA-CH platform -> (ua:osInfo, ua:platform). The test
# asserts this equals the C++ table so the generator and the validator agree.
OS_FORMS = {
    "Windows": ("Windows NT 10.0; Win64; x64", "Windows"),
    "macOS": ("Macintosh; Intel Mac OS X 10_15_7", "macOS"),
    "Linux": ("X11; Linux x86_64", "Linux"),
}
OS_ARG = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}
TASKBAR = {"Windows": 40, "macOS": 25, "Linux": 27}
MAX_DRAWS = 50
# Measured 2026-09-10 (headless chrome, --window-size WxH, --force-device-
# scale-factor D, sizes 1528/1600/2048): at D = 1.25 and 1.75 the window
# comes back exactly 2 px larger on both axes (1528 -> 1530, 2048 -> 2050),
# at 1, 1.5, 2, 2.5 and 3 it comes back exact. Not rounding -- the offset is
# constant across sizes. So launch.window is the configured outer minus the
# offset, and the real innerWidth then never exceeds window.outerWidth.
# DPRs outside the measured set are redrawn.
WINDOW_OFFSET = {1: 0, 1.25: 2, 1.5: 0, 1.75: 2, 2: 0, 2.5: 0, 3: 0}


def dpr_of(fp):
    return fp["screen"].get("devicePixelRatio") or 1


# Chrome clamps navigator.deviceMemory to a power of two in [0.25, 8]; the
# pool carries 16 and 32 in over half of its samples (200 draws: 8 x76,
# 16 x76, 32 x33, 4 x15), values no real Chrome reports. Largest allowed
# value <= the pool's. The C++ domain validator has no rule for this key
# (only the geolocation axes), so the strict oracle cannot catch it.
DEVICE_MEMORY = (0.25, 0.5, 1, 2, 4, 8)
ROOT = pathlib.Path(__file__).resolve().parents[3]


def load_profiles():
    """settings/webgl/*.json by id: real-GPU captures (scripts/capture_webgl_profile.py)."""
    return {p.stem: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((ROOT / "settings" / "webgl").glob("*.json")) if not p.name.startswith("._")}


GL_ENUM = {"VERTEX_SHADER": 35633, "FRAGMENT_SHADER": 35632, "LOW_FLOAT": 36336, "MEDIUM_FLOAT": 36337,
           "HIGH_FLOAT": 36338, "LOW_INT": 36339, "MEDIUM_INT": 36340, "HIGH_INT": 36341}


def precision_keys(spf):
    """Profile cells "VERTEX_SHADER/HIGH_FLOAT" -> the key's "<shadertype>:<precisiontype>" decimal form."""
    return {f"{GL_ENUM[s]}:{GL_ENUM[p]}": v for (s, p), v in ((k.split("/"), v) for k, v in spf.items())}


def webgl_keys(profile):
    """The profile's identity, numeric table, extension list and precision formats
    on both contexts (measured 2026-09-11: the SwiftShader host's precision
    cells differ from a real GPU's in 8 of 12, so they must be emitted too;
    contextAttributes agreed in all and stay unemitted)."""
    return {"webGl:vendor": profile["vendor"], "webGl:renderer": profile["renderer"],
            "webGl2:vendor": profile["vendor"], "webGl2:renderer": profile["renderer"],
            "webGl:parameters": profile["webgl"]["parameters"],
            "webGl2:parameters": profile["webgl2"]["parameters"],
            "webGl:supportedExtensions": profile["webgl"]["supportedExtensions"],
            "webGl2:supportedExtensions": profile["webgl2"]["supportedExtensions"],
            "webGl:shaderPrecisionFormats": precision_keys(profile["webgl"]["shaderPrecisionFormats"]),
            "webGl2:shaderPrecisionFormats": precision_keys(profile["webgl2"]["shaderPrecisionFormats"])}


def profile_for(platform, gpu=None):
    profiles = load_profiles()
    if gpu:
        return profiles[gpu]
    return next((p for p in profiles.values() if p["os"] == platform), None)


def zone_for(locale, rng):
    table = json.loads((ROOT / "settings" / "locale_zones.json").read_text(encoding="utf-8"))["zones"]
    if locale not in table:
        raise ValueError(f"--timezone is required for {locale}: no locale->zone table row, and "
                         "locale:tag without timezone:id trips timezone-set-with-locale")
    return rng.choice(table[locale])


def fonts_keys(platform):
    """fonts:list (the claimed OS's captured family list) and fonts:alias (each
    family's bundled target, generated by scripts/gen_fontconfig.py); {} for Linux."""
    fonts = json.loads((ROOT / "settings" / "fonts.json").read_text(encoding="utf-8"))
    if platform not in fonts["alias_map"]:
        return {}
    fam = fonts["families"][platform]
    return {"fonts:list": fam["list"] + fonts["extra_allowed"][platform] + sorted(fam.get("unique_names", {})),
            "fonts:alias": {**fonts["alias_map"][platform], **fonts.get("unique_map", {}).get(platform, {})},
            # The list was captured on one OS version; the UA-CH claim follows it (rule 4).
            "ua:platformVersion": fam["platform_version"]}


def chrome_device_memory(value):
    return max((m for m in DEVICE_MEMORY if m <= value), default=DEVICE_MEMORY[0])


def acceptable(fp):
    ud = fp["navigator"].get("userAgentData") or {}
    brands = " ".join(b.get("brand", "") for b in ud.get("brands", []))
    return (ud.get("platform") in OS_FORMS and not ud.get("mobile")
            and "Brave" not in brands and "Edge" not in brands
            and dpr_of(fp) in WINDOW_OFFSET)


def fix_screen_no_taskbar(config, platform):
    """screen.avail == screen on both axes is the headless tell CreepJS
    flags; give the OS its bar and keep the window inside it."""
    sw, sh = config.get("screen.width"), config.get("screen.height")
    if not (sw and sh and config.get("screen.availWidth") == sw
            and config.get("screen.availHeight") == sh):
        return
    config["screen.availHeight"] = sh - TASKBAR[platform]
    if config.get("window.outerHeight", 0) > config["screen.availHeight"]:
        config["window.outerHeight"] = config["screen.availHeight"]


def clamp_window_dimensions(config):
    """outer <= avail <= screen on both axes."""
    for axis in ("Width", "Height"):
        screen = config.get(f"screen.{axis.lower()}")
        avail = config.get(f"screen.avail{axis}")
        if screen and avail and avail > screen:
            config[f"screen.avail{axis}"] = avail = screen
        cap = avail or screen
        if cap and config.get(f"window.outer{axis}", 0) > cap:
            config[f"window.outer{axis}"] = cap


def clamp_window_position(config):
    """0 <= screenX/Y <= screen - outer."""
    for axis, key in (("Width", "window.screenX"), ("Height", "window.screenY")):
        screen, outer, pos = (config.get(f"screen.{axis.lower()}"),
                              config.get(f"window.outer{axis}"), config.get(key))
        if pos is not None and screen and outer:
            config[key] = max(0, min(pos, screen - outer))


def from_pool(fp, timezone=None, locale=None, rng=None, gpu=None):
    """Pure: one BrowserForge fingerprint dict -> {"config", "launch"}."""
    nav, ud, scr = fp["navigator"], fp["navigator"]["userAgentData"], fp["screen"]
    platform = ud["platform"]
    os_info, ua_platform = OS_FORMS[platform]
    rng = rng or random.Random()
    if locale:
        tag = locale
        languages = [tag] if "-" not in tag else [tag, tag.split("-")[0]]
    else:
        tag = nav["language"]
        languages = [tag] + [l for l in nav.get("languages", []) if l != tag]
    config = {
        "ua:osInfo": os_info, "ua:platform": ua_platform,
        "ua:platformVersion": ud.get("platformVersion", ""),
        "ua:architecture": ud.get("architecture", ""),
        "ua:bitness": ud.get("bitness", ""),
        "ua:model": ud.get("model", ""),
        "ua:mobile": False, "ua:wow64": False,
        "navigator.hardwareConcurrency": nav["hardwareConcurrency"],
        "navigator.deviceMemory": chrome_device_memory(nav["deviceMemory"]),
        "navigator.maxTouchPoints": nav["maxTouchPoints"],
        "screen.width": scr["width"], "screen.height": scr["height"],
        "screen.availWidth": scr["availWidth"], "screen.availHeight": scr["availHeight"],
        "window.outerWidth": scr["outerWidth"], "window.outerHeight": scr["outerHeight"],
        "window.screenX": scr["screenX"], "window.screenY": scr.get("screenY", 0),
        "timezone:id": timezone or zone_for(tag, rng),
    }
    config.update({"locale:tag": tag, "navigator.language": tag,
                   "navigator.languages": languages})
    bat = fp.get("battery") or {}
    if "charging" in bat:
        config["battery:charging"] = bool(bat["charging"])
        config["battery:level"] = float(bat.get("level", 1))
        for k in ("chargingTime", "dischargingTime"):
            if bat.get(k) is not None:
                config[f"battery:{k}"] = float(bat[k])
    mm = fp.get("multimediaDevices") or {}
    counts = {k: len(mm.get(k) or []) for k in ("micros", "webcams", "speakers")}
    config["mediaDevices:enabled"] = any(counts.values())
    for k, n in counts.items():
        config[f"mediaDevices:{k}"] = n
    config.update(per_instance_config(rng))
    profile = profile_for(platform, gpu)
    if profile:
        config.update(webgl_keys(profile))
    config.update(fonts_keys(platform))

    fix_screen_no_taskbar(config, platform)
    clamp_window_dimensions(config)
    clamp_window_position(config)
    dpr, off = dpr_of(fp), WINDOW_OFFSET[dpr_of(fp)]
    launch = {"window": [config["window.outerWidth"] - off, config["window.outerHeight"] - off],
              "dpr": dpr}
    return {"config": config, "launch": launch}


def generate(os=None, timezone=None, locale=None, seed=None, gpu=None):
    from browserforge.fingerprints import FingerprintGenerator
    rng = random.Random(seed)
    if seed is not None:
        random.seed(seed)  # BrowserForge draws from the global RNG
    # browserforge 1.2.4 raises TypeError on every draw when os=None is
    # passed explicitly; the keyword must be absent for "any OS".
    gen = FingerprintGenerator(browser="chrome", **({"os": os} if os else {}))
    for _ in range(MAX_DRAWS):
        fp = asdict(gen.generate())
        if acceptable(fp):
            return from_pool(fp, timezone, locale, rng, gpu)
    raise RuntimeError(f"no acceptable Chrome sample in {MAX_DRAWS} draws for os={os}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--os", choices=sorted(OS_ARG))
    ap.add_argument("--timezone", help="IANA zone; default from settings/locale_zones.json by locale")
    ap.add_argument("--locale")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--gpu", help="a settings/webgl profile id; default: the first profile for the claimed OS")
    a = ap.parse_args()
    json.dump(generate(a.os, a.timezone, a.locale, a.seed, a.gpu), sys.stdout)


if __name__ == "__main__":
    main()

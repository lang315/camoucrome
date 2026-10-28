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
import os
import pathlib
import random
import re
import sys
from dataclasses import asdict

from . import hostfonts
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
# at 1, 1.5, 2, 2.5 and 3 it comes back exact. Those sizes were all multiples
# of 4. Measured again 2026-10-28 over L = 1180..1191, 1480..1491 and
# 660..671, 714..725: the offset is not constant. At 1.25 and 1.75 L % 4 == 2
# comes back +1 (not +2), at 1.5 an odd L comes back +1, and at 1.25 an L with
# L % 4 == 3 comes back +2 with innerWidth 1 px ABOVE the outer width (G4 of
# verify_sp6b_generator). So launch.window is the largest L <= outer - offset
# whose residue is in WINDOW_SAFE[dpr]: there the browser returns L + offset
# exactly with innerWidth not above it, and the claimed outer is set to that
# (at most 2 px smaller). The residues are from the same measurement:
# 1.25: L % 4 in {0, 1}; 1.75: L % 4 in {0, 1, 3}; 1.5: L even.
# DPRs outside the measured set are redrawn.
WINDOW_OFFSET = {1: 0, 1.25: 2, 1.5: 0, 1.75: 2, 2: 0, 2.5: 0, 3: 0}
WINDOW_SAFE = {1.25: (4, (0, 1)), 1.5: (2, (0,)), 1.75: (4, (0, 1, 3))}


def snap_window(dpr, outer):
    """(launch size, outer the browser then reports) along one axis, for a claimed outer size."""
    off = WINDOW_OFFSET[dpr]
    mod, ok = WINDOW_SAFE.get(dpr, (1, (0,)))
    length = outer - off
    while length % mod not in ok:
        length -= 1
    return length, length + off


def dpr_of(fp):
    return fp["screen"].get("devicePixelRatio") or 1


# Chrome clamps navigator.deviceMemory to a power of two in [0.25, 8]; the
# pool carries 16 and 32 in over half of its samples (200 draws: 8 x76,
# 16 x76, 32 x33, 4 x15), values no real Chrome reports. Largest allowed
# value <= the pool's. The C++ domain validator has no rule for this key
# (only the geolocation axes), so the strict oracle cannot catch it.
DEVICE_MEMORY = (0.25, 0.5, 1, 2, 4, 8)
# The repository (or an archive/client copy with the same layout), else the
# copy a wheel build puts in the package (client/python/setup.py).
_PACKAGED = pathlib.Path(__file__).resolve().parent / "_settings"
ROOT = pathlib.Path(os.environ.get("CAMOUCROME_ROOT") or pathlib.Path(__file__).resolve().parents[3])
if not (ROOT / "settings" / "webgl").is_dir():
    ROOT = _PACKAGED
if not (ROOT / "settings" / "webgl").is_dir():
    raise ImportError(f"camoucrome.gen needs settings/ and found none at {ROOT}: "
                      "set CAMOUCROME_ROOT to the repository (or client copy) root")


def load_profiles():
    """settings/webgl/*.json by id: real-GPU captures (scripts/capture_webgl_profile.py)."""
    return {p.stem: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((ROOT / "settings" / "webgl").glob("*.json")) if not p.name.startswith("._") and not p.stem.endswith(("-pool", "-thread-caps"))}


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


GEN9_RE = re.compile(r"^ANGLE \(Intel, Intel\(R\) (U?HD Graphics( 6\d\d)?) \((0x[0-9A-F]{8})\) "
                     r"Direct3D11 vs_5_0 ps_5_0, D3D11\)$")
SHARED_GPU = "the GPU is shared by every profile on this host"


# assumption: the thread counts Intel parts typically ship with, not a measured distribution
THREAD_STEPS = (2, 4, 6, 8, 12, 16, 20)


def gen9_pool():
    return json.loads((ROOT / "settings" / "webgl" / "intel-gen9-pool.json").read_text(encoding="utf-8"))


def gen9_thread_cap(renderer):
    """Most threads any CPU shipping this Gen9 GPU has (Intel ARK, settings/webgl/intel-gen9-thread-caps.json);
    None for a non-Gen9 renderer or one with no sourced cap."""
    return _thread_caps().get(gen9_device_id(renderer))


def _thread_caps():
    rows = json.loads((ROOT / "settings" / "webgl" / "intel-gen9-thread-caps.json").read_text(encoding="utf-8"))["rows"]
    return {int(r["device_id"], 16): r["max_threads"] for r in rows if r["max_threads"] is not None}


def gen9_device_id(renderer, ids=None):
    m = GEN9_RE.match(renderer or "")
    if not m:
        return None
    dev = int(m.group(3), 16)
    return dev if dev in set(ids if ids is not None else gen9_pool()["device_ids"]) else None


def gpu_for(platform, host_renderer, rng, gpu=None):
    """(profile, warning). A host that is unknown, not a D3D11 renderer or not Intel Gen9 claims no GPU (None: the real
    GPU is kept). An Intel Gen9 host draws one Gen9 identity per profile seed: name and DeviceId
    change, every parameter stays the host generation's. The draw uses its own generator seeded from rng's
    state (as fonts_keys does), so rng is not advanced and later seeded keys do not move.
    Only renderers with a sourced thread cap (gen9_thread_cap) are drawn; from_pool then holds
    navigator.hardwareConcurrency to that cap."""
    base = profile_for(platform, gpu)
    if gpu or platform != "Windows" or base is None:
        return base, None
    # Fail closed: a host this code cannot identify may not back an Intel claim (an RTX or Arc host shows its own adapter in
    # WebGPU and AV1 hardware decode under an Intel WebGL string), so it claims no GPU. `--gpu` is the deliberate opt-in.
    if host_renderer is None:
        return None, f"host GPU unknown: {SHARED_GPU}; the real GPU is kept"
    if not host_renderer.endswith(", D3D11)"):
        return None, f"host renderer is not a Windows D3D11 renderer: {SHARED_GPU}; the real GPU is kept"
    if gen9_device_id(host_renderer) is None:
        return None, f"host GPU is not in the supported Intel Gen9 set: {SHARED_GPU}; the real GPU is kept"
    caps = _thread_caps()
    pool = [r for r in gen9_pool()["renderers"] if r["device_id"] in caps]  # no sourced cap: never drawn
    pick = random.Random(repr(rng.getstate()) + "gpu").choices(pool, weights=[r["weight"] for r in pool])[0]
    return {**base, "renderer": pick["renderer"]}, None


def zone_for(locale, rng):
    table = json.loads((ROOT / "settings" / "locale_zones.json").read_text(encoding="utf-8"))["zones"]
    if locale not in table:
        raise ValueError(f"--timezone is required for {locale}: no locale->zone table row, and "
                         "locale:tag without timezone:id trips timezone-set-with-locale")
    return rng.choice(table[locale])


def fonts_keys(platform, rng=None, host_families=None):
    """fonts:list (the claimed OS's captured family list) and fonts:alias (each
    family's bundled target, generated by scripts/gen_fontconfig.py); {} for Linux.
    With rng, fonts:list is a subset: the base set plus each optional group drawn at its p
    (groups in name order, so a seed is stable). host_families (what hostfonts.families()
    returns: registry labels) limits the list on both paths, for a Windows claim only (ignored for
    any other platform: a Windows registry says nothing about a macOS claim's fonts); empty or unmappable means
    "host unknown" and limits nothing. fonts:local, fonts:alias and fonts:aliasLocal drop
    every entry of a hidden family, so no local() name outlives the list.
    The draw uses its own generator seeded from rng's state, so rng is not advanced: Task 4
    passes the generation rng and other seeded keys (share:cancelMs ...) must not move.
    Without rng it is the whole captured list, as before."""
    fonts = json.loads((ROOT / "settings" / "fonts.json").read_text(encoding="utf-8"))
    if platform not in fonts["alias_map"]:
        return {}
    fam = fonts["families"][platform]
    chosen = set(fam["list"])
    if rng is not None and "base" in fam:
        draw = random.Random(repr(rng.getstate()))
        chosen = set(fam["base"])
        for name in sorted(fam["groups"]):
            if draw.random() < fam["groups"][name]["p"]:
                chosen |= set(fam["groups"][name]["families"])
    # the registry set means something only for a Windows claim (the one with a base set)
    on_host = hostfonts.host_families_from_labels(host_families, fam) if host_families and "base" in fam else set()
    if on_host and chosen & on_host:
        chosen &= on_host
    families = [f for f in fam["list"] if f in chosen]
    hidden = set(fam["list"]) - chosen
    alias = {k: v for k, v in fonts["alias_map"][platform].items() if k not in hidden}
    allowed = families + fonts["extra_allowed"][platform]
    if fam["ps_names_are_css_families"]:
        # macOS Chrome resolves a PostScript/full name as a CSS family (font_matcher_mac.mm falls
        # back to it; measured on stock); Windows does not. Same map keys, family targets.
        for name, v in fam["unique_names"].items():
            target = alias.get(v["family"], v["family"])
            if target != name:
                alias[name] = target
        allowed = allowed + sorted(fam["unique_names"])
    return {"fonts:list": allowed,
            # queryLocalFonts() lists the captured host's faces (tab-joined ps, full, family, style), never the bundle's
            **({"fonts:local": ["\t".join(f) for f in fam["faces"] if f[2] in families]} if fam.get("faces") else {}),  # no captured faces: real enumeration (rule 5), never an empty list
            "fonts:alias": alias,
            # src:local() names (the local() gate allows this map's keys) land on a face's full name (F-PSNAME)
            "fonts:aliasLocal": {k: v for k, v in fonts["unique_map"][platform].items()
                                 if fam["unique_names"].get(k, {}).get("family") not in hidden},
            # The list was captured on one OS version; the UA-CH claim follows it (rule 4).
            "ua:platformVersion": fam["platform_version"]}


def voices_keys(platform, locale="en-US"):
    """voices:list for the claimed OS and locale from settings/voices.json: the locale's language-pack row, else the same
    language's first row, else en-US (only en-US is measured; the rest are quoted), then Chrome's Google network voices
    ("remote", the same 19 on every OS). {} when the OS has no table."""
    voices = json.loads((ROOT / "settings" / "voices.json").read_text(encoding="utf-8"))
    if platform not in voices:
        return {}
    table = voices[platform]
    if isinstance(table, list):  # macOS ships every language's voices at once (measured: 191 on a 15.7.4 Mac)
        row = table
    else:
        lang = locale.split("-")[0]
        row = table.get(locale) or next((v for t, v in table.items() if t.split("-")[0] == lang), table["en-US"])
    return {"voices:list": row + voices["remote"]}


def audio_keys(platform):
    """audio:sampleRate for the claimed OS from settings/audio.json (measured on stock); {} when the OS has no row."""
    audio = json.loads((ROOT / "settings" / "audio.json").read_text(encoding="utf-8"))
    if platform not in audio:
        return {}
    return {"audio:sampleRate": audio[platform]["sampleRate"], "audio:bufferFrames": audio[platform]["bufferFrames"]}


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


MIN_WINDOW = (800, 500)  # assumption: a person's window is never narrower or shorter than this


def window_position(rng, avail, outer):
    """How far a person dragged the window off the work-area corner: (dx, dy), each 0..120 px (assumption), and
    never so far that the window would be narrower or shorter than MIN_WINDOW. from_pool moves the window by
    (dx, dy) and shrinks it by the same amount, so its far edge stays where it was inside the work area."""
    r = random.Random(repr(rng.getstate()) + "window-position")  # own generator: rng and later keys stay put
    lim = [max(0, min(120, min(a, o) - m)) for a, o, m in zip(avail, outer, MIN_WINDOW)]
    return r.randint(0, lim[0]), r.randint(0, lim[1])


def valid_display(d):
    """True for a {"gamut": srgb|p3|rec2020, "colorBits": 8|10, "hdr": bool} dict; probe and the CLI share it."""
    return (isinstance(d, dict) and d.get("gamut") in ("srgb", "p3", "rec2020") and d.get("colorBits") in (8, 10)
            and isinstance(d.get("hdr"), bool))


def display_flags(host_display):
    """--force-color-profile=srgb for a wide-gamut host. 10-bit and HDR have no known launch lever: a warning, not a claim."""
    if not host_display:
        return [], "display unknown: gamut, bit depth and HDR keep the host's values"
    flags = ["--force-color-profile=srgb"] if host_display["gamut"] != "srgb" else []
    left = [n for n, on in (("10-bit", host_display["colorBits"] != 8), ("hdr", host_display["hdr"])) if on]
    warn = f"host display is {', '.join(left)}: no lever hides it, every profile shows it" if left else None
    return flags, warn


def from_pool(fp, timezone=None, locale=None, rng=None, gpu=None, host_renderer=None, host_families=None,
              host_platform_version=None, host_display=None):
    """Pure: one BrowserForge fingerprint dict -> {"config", "launch", "warnings"}.
    When a host_renderer swaps in a drawn Gen9 GPU, navigator.hardwareConcurrency above that GPU's thread
    cap (gen9_thread_cap) is redrawn from THREAD_STEPS within it, so a mobile part never claims 16 threads;
    a value already within the cap stays as BrowserForge drew it."""
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
        # The pool's Linux rows carry no platformVersion; an empty override would replace the real kernel version
        # (stock Linux Chrome reports it), so the key is left out and rule 5 keeps the real value.
        **({"ua:platformVersion": ud["platformVersion"]} if ud.get("platformVersion") else {}),
        "ua:architecture": ud.get("architecture", ""),
        "ua:bitness": ud.get("bitness", ""),
        "ua:model": ud.get("model", ""),
        "ua:mobile": False, "ua:wow64": False,
        "ua:brand": "Google Chrome",  # the pool's brands carry it; a Chromium build would ship two brands where Chrome ships three
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
    profile, warn = gpu_for(platform, host_renderer, rng, gpu)
    if profile:
        config.update(webgl_keys(profile))
        cap = gen9_thread_cap(profile["renderer"]) if host_renderer and not gpu else None
        if cap is not None and config["navigator.hardwareConcurrency"] > cap:
            # own generator: rng stays where it was, so the other seeded keys do not move
            config["navigator.hardwareConcurrency"] = random.Random(repr(rng.getstate()) + "gpu-threads").choice(
                [t for t in THREAD_STEPS if t <= cap])
    config.update(fonts_keys(platform, rng, host_families))
    pv_warn = None
    if host_platform_version and platform == "Windows":  # the host is Windows; a macOS or Linux claim keeps its own
        if re.fullmatch(r"\d+\.\d+\.\d+", host_platform_version):  # the host's real OS wins over the pool's and the font capture's claim
            config["ua:platformVersion"] = host_platform_version
        else:
            pv_warn = f"host platform version {host_platform_version!r} is not N.N.N: ignored"
    config.update(voices_keys(platform, tag))
    config.update(audio_keys(platform))
    if platform in ("Windows", "macOS"):
        config["share:cancelMs"] = rng.randint(900, 2600)  # a dismissed share sheet takes a human seconds, never 0 ms

    fix_screen_no_taskbar(config, platform)
    clamp_window_dimensions(config)
    clamp_window_position(config)
    # Position: a pool position that is not (0, 0) and lies inside the work area is a real sample and stays. Any
    # other (the pool puts 36 of 40 windows at 0,0) is drawn, and the window shrinks by the offset so it never
    # reaches under the taskbar the identity claims: screenX + outerWidth <= availLeft + availWidth, same for Y.
    pos = (config["window.screenX"], config["window.screenY"])
    avail = (config["screen.availWidth"], config["screen.availHeight"])
    outer = [config["window.outerWidth"], config["window.outerHeight"]]
    origin = (config.get("screen.availLeft", 0), config.get("screen.availTop", 0))
    inside = all(origin[i] <= pos[i] and pos[i] + outer[i] <= origin[i] + avail[i] for i in (0, 1))
    if pos == (0, 0) or not inside:
        d = window_position(rng, avail, outer)
        config["window.screenX"], config["window.screenY"] = origin[0] + d[0], origin[1] + d[1]
        config["window.outerWidth"], config["window.outerHeight"] = outer[0] - d[0], outer[1] - d[1]
    dpr = dpr_of(fp)
    (lw, config["window.outerWidth"]), (lh, config["window.outerHeight"]) = (
        snap_window(dpr, config["window.outerWidth"]), snap_window(dpr, config["window.outerHeight"]))
    launch = {"window": [lw, lh], "dpr": dpr, "position": [config["window.screenX"], config["window.screenY"]]}
    # None = not probed (no claim); a failed probe is the caller's to turn into display_flags(None)
    if host_display is not None and not valid_display(host_display):
        host_display, bad_display = None, "host display is malformed: ignored"
    else:
        bad_display = None
    launch["args"], dw = display_flags(host_display) if host_display is not None else ([], None)
    return {"config": config, "launch": launch, "warnings": [w for w in (warn, pv_warn, bad_display, dw) if w]}


def generate(os=None, timezone=None, locale=None, seed=None, gpu=None, exit_ip=None, geoip_db=None, host_renderer=None,
             host_families=None, host_platform_version=None, host_display=None):
    """exit_ip (item 13): the zone and locale come from where the address is, unless given explicitly. When it cannot
    be resolved the draw proceeds as without it and a GeoIPWarning says so."""
    if exit_ip:
        timezone, locale = _from_exit_ip(exit_ip, geoip_db, timezone, locale)
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
            return from_pool(fp, timezone, locale, rng, gpu, host_renderer, host_families, host_platform_version,
                             host_display)
    raise RuntimeError(f"no acceptable Chrome sample in {MAX_DRAWS} draws for os={os}")


def _from_exit_ip(exit_ip, geoip_db, timezone, locale):
    from . import geoip
    try:
        found = geoip.lookup(exit_ip, geoip_db)
    except geoip.GeoIPError as e:
        geoip.warn_all([f"the exit IP {exit_ip} was not resolved ({e}): timezone and locale are not derived from it"])
        return timezone, locale
    if found["locale"] is None:
        geoip.warn_all([f"no locale for country {found['country']}: the identity keeps its drawn locale beside {found['timezone']}"])
    return timezone or found["timezone"], locale or found["locale"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--os", choices=sorted(OS_ARG))
    ap.add_argument("--timezone", help="IANA zone; default from settings/locale_zones.json by locale")
    ap.add_argument("--locale")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--gpu", help="a settings/webgl profile id, claimed whatever the host is (a deliberate opt-in, e.g. a test box with no GPU); "
                                  "default: a Windows claim draws a Gen9 GPU on a Gen9 host and claims none on any other")
    ap.add_argument("--exit-ip", help="the proxy's exit address: timezone and locale follow where it is (needs --geoip-db or CAMOU_GEOIP_DB)")
    ap.add_argument("--geoip-db", help="a DB-IP Lite or GeoLite2-layout .mmdb")
    ap.add_argument("--host-renderer", help="the host's WebGL renderer string (probe.host_renderer): an Intel Gen9 host draws a Gen9 identity per seed")
    ap.add_argument("--probe-executable", help="a Chrome binary: launch it once to read the host's WebGL renderer when --host-renderer is not given (a failed probe claims no GPU)")
    ap.add_argument("--host-fonts", action="store_true", help="limit a Windows claim's fonts to the families this host has (Windows only; elsewhere unknown)")
    ap.add_argument("--host-platform-version", help="the host's UA-CH platformVersion (probe.host_platform_version): wins over the pool's")
    ap.add_argument("--host-display", type=json.loads, help='the host display as JSON (probe.host_display): {"gamut","colorBits","hdr"}; a wide-gamut host gets --force-color-profile=srgb in launch.args')
    a = ap.parse_args(argv)
    if a.host_renderer is None and a.probe_executable:
        from . import probe
        a.host_renderer = probe.host_renderer(a.probe_executable)
    if a.host_display is not None and not valid_display(a.host_display):
        sys.exit('gen: --host-display must be {"gamut": "srgb"|"p3"|"rec2020", "colorBits": 8|10, "hdr": true|false}')
    families = hostfonts.families() if a.host_fonts else None
    json.dump(generate(a.os, a.timezone, a.locale, a.seed, a.gpu, a.exit_ip, a.geoip_db, a.host_renderer, families, a.host_platform_version, a.host_display), sys.stdout)


if __name__ == "__main__":
    main()

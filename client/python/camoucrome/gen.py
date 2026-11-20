"""Fingerprint generator, v1: a coherent CAMOU_CONFIG from BrowserForge's
Chrome pool plus the launcher options that go with it.

    python -m camoucrome.gen --os windows --timezone Europe/Paris [--locale fr-FR] [--seed N]
    -> {"config": {...}, "launch": {"window": [w, h], "dpr": x}}

Pool field -> config key (mirrors the preset loader's table style):

  userAgentData.platform          -> ua:osInfo, ua:platform (canonical forms, OS_FORMS)
  userAgentData.platformVersion/architecture/bitness/model/mobile
                                  -> ua:platformVersion, ua:architecture, ua:bitness,
                                     ua:model, ua:mobile; ua:wow64 false
  navigator.hardwareConcurrency, maxTouchPoints -> same-named keys; a claim above the host's cores
                                     (host_cores, default os.cpu_count()) snaps to the largest THREAD_STEPS
                                     value within them (or to host_cores when none fits): timing on the host
                                     shows the real count
  navigator.deviceMemory           -> the pool's value in [8, 32] (DEVICE_MEMORY): the real
                                     jsHeapSizeLimit of an 8 GB+ host rules out a smaller claim
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
  per_instance_config()            -> canvas:seed, mediaDevices:seed

Never taken, and why:
  navigator.userAgent, appVersion, brands, fullVersionList, headers
                                   version-bearing; the fork's own milestone produces them
  navigator.platform, vendor, product*, appName, appCodeName
                                   derived or constant in the fork already
  screen.colorDepth / pixelDepth   the pool says 32 where real Chrome reports 24/30; the
                                   real value is coherent by construction
  screen.availLeft / availTop      multi-monitor offsets from the pool; the real 0 is fine
  videoCard (webGl:*)              taken when gpu_class accepts it (NVIDIA, AMD RX/Pro, Intel Arc A-series,
                                   an Intel or AMD iGPU with a sourced thread cap), else the sample is redrawn.
                                   With a host renderer of known Dawn architecture (gpu_architecture) the claim
                                   must share its vendor and architecture; with none in MAX_DRAWS there is no claim
                                   and the host's GPU shows. Only the four strings and webGpu:blocked are emitted;
                                   tables stay the host's.
                                   --gpu names a captured profile's strings instead
  fonts                            fonts:list is the captured family list of the claimed OS
                                   (settings/fonts.json), drawn per seed and limited to the
                                   host's families, plus the Windows 11 families on a Windows 11
                                   host (win11_families); the bundled fontconfig layer makes
                                   it resolvable off the claimed OS; Linux claims get none
  voices, geolocation              Chrome voice names and GeoIP are their own catalogues;
                                   with an exit IP, geolocation:latitude/longitude are the
                                   database's point for it plus a seeded offset within 2 km;
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
import math
import os
import os as _os  # generate() has an `os` parameter
import pathlib
import random
import re
import sys
from dataclasses import asdict

from . import hostfonts, pin
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
# 200: a draw that succeeds within 50 never reaches the extra ones, so no seed moves; the rest absorb the gpu_class and floor rejects (35.8% of 20,000 raw samples: 22.7% class, 13.1% floor, measured 2026-11-18).
MAX_DRAWS = 200
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


def valid_screen(s):
    """{"availWidth": int > 0, "availHeight": int > 0}: the host's work area in physical px (probe.host_screen)."""
    return (isinstance(s, dict) and set(s) == {"availWidth", "availHeight"}
            and all(type(v) is int and v > 0 for v in s.values()))


def dpr_of(fp):
    return fp["screen"].get("devicePixelRatio") or 1


# navigator.deviceMemory is the pool's value clamped to [8, 32]. The fork leaves
# performance.memory.jsHeapSizeLimit real, and V8 sizes the heap from physical
# memory (old generation = RAM / 2, capped at 4 GB on 64-bit), so a host with
# 8 GB or more shows the capped heap (3760000000 on Chrome 156, Windows and
# Linux, measured 2026-11-04), which no real 0.25..4 GB device shows; facebook
# sends both (measurements/2026-11-04-fb-tracking-map.md). 8, 16 and 32 all sit
# beside that heap. Chrome 156 desktop clamps the API to [2, 32]
# (approximated_device_memory.cc), and so does domain_validator.cc. The pool
# draws 8 x76, 16 x76, 32 x33, 4 x15 in 200 samples.
# shortcut: a host under 8 GB RAM shows a smaller heap beside this claim; derive the claim from host RAM then.
DEVICE_MEMORY = (8, 32)
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
            for p in sorted((ROOT / "settings" / "webgl").glob("*.json")) if not p.name.startswith("._") and not p.stem.endswith(("-pool", "-thread-caps", "-architectures"))}


GPU_CLAIM_KEYS = ("webGl:vendor", "webGl:renderer", "webGl2:vendor", "webGl2:renderer", "webGpu:blocked")


def gpu_keys(vendor, renderer, host_renderer):
    """The claim's four strings, plus webGpu:blocked: true unless the claim and the host share vendor and Dawn architecture
    (adapter.info reports only those two, so WebGPU then agrees with the claim, as on a real machine), or the claim is the
    host's own renderer string. An unknown host (None) is never the same. Parameters, extensions and precision formats are
    the host's and are not emitted."""
    same = renderer == host_renderer or same_architecture(renderer, host_renderer)
    return {"webGl:vendor": vendor, "webGl:renderer": renderer, "webGl2:vendor": vendor, "webGl2:renderer": renderer,
            "webGpu:blocked": not same}


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


ANGLE_D3D11_RE = re.compile(r"^ANGLE \((NVIDIA|AMD|Intel), (.+) \(0x([0-9A-Fa-f]{8})\) Direct3D11 vs_5_0 ps_5_0, D3D11\)$")


def _igpu_caps():
    """{(vendor, device id): max threads} from settings/webgl/igpu-thread-caps.json; a row with no max_threads is unsourced
    and left out (an unsourced id is never drawn)."""
    rows = json.loads((ROOT / "settings" / "webgl" / "igpu-thread-caps.json").read_text(encoding="utf-8"))["rows"]
    return {(r["vendor"], int(r["device_id"], 16)): r["max_threads"] for r in rows if r["max_threads"] is not None}


def _igpu_floors():
    """{(vendor, device id): min threads} for the rows that carry a sourced min_threads: the smallest Total Threads of any
    SKU read that lists the id. An iGPU fixes the CPU family, so a claim with fewer threads is a tell."""
    rows = json.loads((ROOT / "settings" / "webgl" / "igpu-thread-caps.json").read_text(encoding="utf-8"))["rows"]
    return {(r["vendor"], int(r["device_id"], 16)): r["min_threads"] for r in rows
            if r["max_threads"] is not None and r.get("min_threads") is not None}


def _gen9_floors():
    """{device id: min threads} for the Gen9 rows of intel-gen9-thread-caps.json that carry a sourced min_threads."""
    rows = json.loads((ROOT / "settings" / "webgl" / "intel-gen9-thread-caps.json").read_text(encoding="utf-8"))["rows"]
    return {int(r["device_id"], 16): r["min_threads"] for r in rows
            if r["max_threads"] is not None and r.get("min_threads") is not None}


def igpu_thread_floor(renderer):
    """Fewest threads any CPU shipping this iGPU has (min_threads in intel-gen9-thread-caps.json for Gen9, else
    igpu-thread-caps.json); None when the renderer is not such an iGPU or its row has no sourced floor."""
    dev = gen9_device_id(renderer)
    if dev is not None:
        return _gen9_floors().get(dev)
    m = ANGLE_D3D11_RE.match(renderer or "")
    return _igpu_floors().get((m.group(1), int(m.group(3), 16))) if m else None


def igpu_thread_cap(renderer):
    """Most threads any CPU/APU shipping this non-Gen9 iGPU has (settings/webgl/igpu-thread-caps.json); None when the
    renderer is not an ANGLE D3D11 Intel or AMD string, or its id has no sourced cap."""
    m = ANGLE_D3D11_RE.match(renderer or "")
    return _igpu_caps().get((m.group(1), int(m.group(3), 16))) if m else None


def thread_cap(renderer):
    """The cap of any claimed iGPU (Gen9 or other), else None."""
    cls = gpu_class(renderer)
    return gen9_thread_cap(renderer) if cls == "igpu-gen9" else igpu_thread_cap(renderer) if cls == "igpu" else None


def gpu_class(renderer):
    """"dgpu", "igpu-gen9", "igpu" or None (not drawable: an iGPU with no sourced thread cap, a software renderer, or a
    string that is not an ANGLE D3D11 renderer)."""
    m = ANGLE_D3D11_RE.match(renderer or "")
    if not m or re.search(r"\(\d+GB\)", renderer):  # an Arc name's memory label (16GB) can contradict navigator.deviceMemory
        return None
    vendor, name = m.group(1), m.group(2)
    if vendor == "NVIDIA":
        return "dgpu"
    if vendor == "AMD":
        if ("RX" in name and "Vega" not in name) or "Radeon Pro" in name:  # "RX Vega 8/11" are APUs
            return "dgpu"
        return "igpu" if igpu_thread_cap(renderer) is not None else None
    dev = gen9_device_id(renderer)
    if dev is not None:
        return "igpu-gen9" if dev in _thread_caps() else None  # no sourced cap (0x5921): any thread count would be unbacked
    if re.search(r"Arc\(TM\) A\d{3}", name):
        return "dgpu"
    return "igpu" if igpu_thread_cap(renderer) is not None else None


def _arch_table():
    """settings/webgl/gpu-architectures.json: Dawn's device-id -> architecture table at the pin (scripts/gen_gpu_architectures.py)."""
    global _ARCH
    if _ARCH is None:
        _ARCH = json.loads((ROOT / "settings" / "webgl" / "gpu-architectures.json").read_text(encoding="utf-8"))
    return _ARCH


_ARCH = None


def gpu_architecture(renderer):
    """(vendor, Dawn architecture) of an ANGLE D3D11 renderer string, e.g. ("intel", "gen-9"); None for no renderer, a
    software or non-D3D11 string, or a device id the table does not hold. adapter.info reports exactly these two."""
    m = ANGLE_D3D11_RE.match(renderer or "")
    if not m:
        return None
    vendor = m.group(1).lower()
    v = _arch_table()["vendors"].get(vendor)
    dev = int(m.group(3), 16)
    for s in v["sets"] if v else ():
        a = s["ids"].get(f"0x{dev & int(s['mask'], 16):0{len(s['mask']) - 2}X}")
        if a:
            return vendor, a
    return None


def same_architecture(claim, host):
    a = gpu_architecture(claim)
    return a is not None and a == gpu_architecture(host)


INTEL_CPU, AMD_CPU = "GenuineIntel", "AuthenticAMD"


def igpu_vendor(renderer):
    """The CPU vendor a claimed iGPU implies (AMD APUs ship only with AMD CPUs, Intel iGPUs only with Intel CPUs), as the
    CPUID vendor string; None for a dGPU, an undrawable renderer or no renderer."""
    if gpu_class(renderer) not in ("igpu", "igpu-gen9"):
        return None
    return INTEL_CPU if ANGLE_D3D11_RE.match(renderer).group(1) == "Intel" else AMD_CPU


def cpu_vendor_of(text):
    """GenuineIntel / AuthenticAMD found in /proc/cpuinfo or PROCESSOR_IDENTIFIER text, else None."""
    for v in (INTEL_CPU, AMD_CPU):
        if v in text:
            return v
    return None


def cpu_vendor_from(path, env):
    """The vendor in the file at path (/proc/cpuinfo), else in env (PROCESSOR_IDENTIFIER); None when neither says."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return cpu_vendor_of(f.read(4096))
    except OSError:
        return cpu_vendor_of(env)


def host_cpu_vendor():
    """This machine's CPU vendor (/proc/cpuinfo on Linux, PROCESSOR_IDENTIFIER on Windows), None when unreadable."""
    return cpu_vendor_from("/proc/cpuinfo", _os.environ.get("PROCESSOR_IDENTIFIER", ""))


def vendor_fits(renderer, host_vendor):
    """False only when the claimed iGPU implies a CPU vendor and the host is known to have the other. Skia's reciprocal
    estimates (RCPPS/RSQRTPS) differ between Intel and AMD, so a CPU-rastered readback shows the host's vendor."""
    want = igpu_vendor(renderer)
    return want is None or host_vendor not in (INTEL_CPU, AMD_CPU) or want == host_vendor


def gpu_for(platform, host_renderer, rng, gpu=None, fp=None):
    """(profile, warning): {"vendor", "renderer"} or None. Windows without --gpu claims the fingerprint's own videoCard when
    gpu_class accepts it (the draw is BrowserForge's, joint with cores, memory and screen), else None so generate redraws.
    --gpu names a captured profile. A macOS claim keeps its Apple profile only on a host that reports exactly that renderer."""
    if gpu:
        return profile_for(platform, gpu), None
    if platform == "Windows":
        vc = (fp or {}).get("videoCard") or {}
        if gpu_class(vc.get("renderer")) is None:
            return None, "the sampled GPU is not a drawable class"
        return {"vendor": vc["vendor"], "renderer": vc["renderer"]}, None
    base = profile_for(platform)
    if base is None or platform != "macOS":
        return base, None
    # Only a host that already reports the claimed part backs the Apple claim: on any other host the Apple WebGL string would
    # sit over a different GPU's pixels, WebGPU adapter and decoders.
    if host_renderer is None:
        return None, f"host GPU unknown: {SHARED_GPU}; the real GPU is kept"
    if host_renderer != base["renderer"]:
        return None, f"host GPU is not the claimed Apple part: {SHARED_GPU}; the real GPU is kept"
    return base, None


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


def win11_families(platform_version):
    """The Windows 11 families (settings/fonts.json families.Windows.win11) for a host whose UA-CH platformVersion is
    Windows 11, else []: the identity carries the host's version, and fonts date Windows (CreepJS)."""
    w = json.loads((ROOT / "settings" / "fonts.json").read_text(encoding="utf-8"))["families"]["Windows"]["win11"]
    return list(w["families"]) if int(platform_version.split(".")[0]) >= w["min_platform_major"] else []


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


def holds_min_window(host_screen, dpr):
    return host_screen["availWidth"] / dpr >= MIN_WINDOW[0] and host_screen["availHeight"] / dpr >= MIN_WINDOW[1]


def fit_window(rng, host_screen, dpr, avail, origin, pos, outer):
    """(pos, outer) with the window inside the host's work area as well as the claimed one, on each axis. A window
    larger than the host is drawn again from 60-100 % of what fits (own generator: other seeded keys stay put);
    a position that would put its far edge past the host's is drawn again too. A real window off the host's monitor
    could be treated as occluded and throttled, so the launch position must be inside."""
    host = (host_screen["availWidth"], host_screen["availHeight"])
    cap = [min(avail[i], int(host[i] // dpr)) for i in (0, 1)]
    pos, outer = list(pos), list(outer)
    r = random.Random(repr(rng.getstate()) + "window-fit")
    for i in (0, 1):
        if outer[i] > cap[i]:
            outer[i] = r.randint(max(MIN_WINDOW[i], round(0.6 * cap[i])), cap[i])
    bad = [i for i in (0, 1) if pos[i] + outer[i] > origin[i] + cap[i]]
    if bad:
        d = window_position(rng, cap, outer)
        for i in bad:
            pos[i] = origin[i] + d[i]
            outer[i] = min(outer[i], cap[i] - d[i])
    return pos, outer


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
              host_platform_version=None, host_display=None, host_screen=None, host_cores=None, host_cpu_vendor=None, claim_gpu=True):
    """Pure: one BrowserForge fingerprint dict -> {"config", "launch", "warnings"}.
    When the claimed GPU is an iGPU (Gen9 or any other sourced class), navigator.hardwareConcurrency above that GPU's thread
    cap (thread_cap) is redrawn from THREAD_STEPS within it, so a mobile part never claims 16 threads;
    a value already within the cap stays as BrowserForge drew it.
    host_cores: a claim above it snaps to the largest THREAD_STEPS value within it (deterministic, nothing drawn);
    None leaves the claim alone."""
    nav, ud, scr = fp["navigator"], fp["navigator"]["userAgentData"], fp["screen"]
    platform = ud["platform"]
    os_info, ua_platform = OS_FORMS[platform]
    rng = rng or random.Random()
    # Stock Chrome lists the primary subtag after a regional tag (["en-US", "en"]); the pool's rows often omit it.
    tag = locale or nav["language"]
    languages = [tag] if "-" not in tag else [tag, tag.split("-")[0]]
    if not locale:
        languages += [l for l in nav.get("languages", []) if l not in languages]
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
        "navigator.deviceMemory": min(max(nav["deviceMemory"], DEVICE_MEMORY[0]), DEVICE_MEMORY[1]),
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
    profile, warn = gpu_for(platform, host_renderer, rng, gpu, fp) if claim_gpu else (None, None)
    if profile:
        keys = gpu_keys(profile["vendor"], profile["renderer"], host_renderer)
        if platform != "Windows" and not gpu:
            del keys["webGpu:blocked"]  # the Apple claim without --gpu is only ever made on its own host; --gpu is the opt-in
        config.update(keys)
        cap = thread_cap(profile["renderer"])
        if cap is not None and config["navigator.hardwareConcurrency"] > cap:
            # own generator: rng stays where it was, so the other seeded keys do not move. Within [floor, cap]; no step
            # there (a 24-thread part) means the cap itself, a real SKU's count.
            floor = igpu_thread_floor(profile["renderer"]) or 0
            config["navigator.hardwareConcurrency"] = random.Random(repr(rng.getstate()) + "gpu-threads").choice(
                [t for t in THREAD_STEPS if floor <= t <= cap] or [cap])
    config["navigator.hardwareConcurrency"] = snap_threads(config["navigator.hardwareConcurrency"], host_cores)
    floor = igpu_thread_floor(profile["renderer"]) if profile else None
    floor_warn = None
    if floor and config["navigator.hardwareConcurrency"] < floor:
        # the host's cores fell below what the claimed iGPU's CPU family ships with: the real GPU then matches the real CPU
        for k in GPU_CLAIM_KEYS:
            config.pop(k, None)
        floor_warn = (f"host cores snap to {config['navigator.hardwareConcurrency']}, below the {floor} threads of the "
                      f"claimed GPU's CPU family: the GPU claim is dropped and the host's real GPU is kept")
    vendor_warn = None
    if profile and not gpu and "webGl:renderer" in config and not vendor_fits(profile["renderer"], host_cpu_vendor):
        # an iGPU claim beside the other vendor's CPU: the real GPU then matches the real CPU
        for k in GPU_CLAIM_KEYS:
            config.pop(k, None)
        vendor_warn = ("the claimed iGPU ships only with the other CPU vendor than this host's: the GPU claim is dropped "
                       "and the host's real GPU is kept")
    config.update(fonts_keys(platform, rng, host_families))
    pv_warn = None
    if host_platform_version and platform == "Windows":  # the host is Windows; a macOS or Linux claim keeps its own
        if re.fullmatch(r"\d+\.\d+\.\d+", host_platform_version):  # the host's real OS wins over the pool's and the font capture's claim
            config["ua:platformVersion"] = host_platform_version
            # Not limited by host_families (fonts_keys limits the captured list): fonts:list only allows, so a Windows 11
            # family the host lacks stays unresolved and a page cannot tell; Go core has no host font list and matches this.
            config["fonts:list"] = config["fonts:list"] + [f for f in win11_families(host_platform_version)
                                                           if f not in config["fonts:list"]]
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
    if host_screen is not None:
        p, o = fit_window(rng, host_screen, dpr, avail, origin, (config["window.screenX"], config["window.screenY"]),
                          (config["window.outerWidth"], config["window.outerHeight"]))
        config["window.screenX"], config["window.screenY"] = p
        config["window.outerWidth"], config["window.outerHeight"] = o
    (lw, config["window.outerWidth"]), (lh, config["window.outerHeight"]) = (
        snap_window(dpr, config["window.outerWidth"]), snap_window(dpr, config["window.outerHeight"]))
    launch = {"window": [lw, lh], "dpr": dpr, "position": [config["window.screenX"], config["window.screenY"]]}
    # None = not probed (no claim); a failed probe is the caller's to turn into display_flags(None)
    if host_display is not None and not valid_display(host_display):
        host_display, bad_display = None, "host display is malformed: ignored"
    else:
        bad_display = None
    launch["args"], dw = display_flags(host_display) if host_display is not None else ([], None)
    return {"config": config, "launch": launch, "warnings": [w for w in (warn, floor_warn, vendor_warn, pv_warn, bad_display, dw) if w]}


def allowed_cpus():
    """The CPUs this process may use (the mask the launch pin compares with), else all of them."""
    mask = pin.get_mask(_os.getpid())
    return len(mask) if mask else _os.cpu_count()


def snap_threads(n, host_cores):
    """A thread claim above host_cores snaps to the largest THREAD_STEPS value within them (host_cores itself when none fits);
    None host_cores leaves it."""
    if host_cores is not None and n > host_cores:
        return max([t for t in THREAD_STEPS if t <= host_cores], default=host_cores)
    return n


def gpu_ok(fp, profile, host_vendor=None, host_arch=None):
    """A Windows sample with no drawable GPU is rejected, as is an Apple one beside an x86 claim, and one whose thread
    count is below the claimed iGPU's floor."""
    if profile is None and fp["navigator"]["userAgentData"]["platform"] == "Windows":
        return False
    floor = igpu_thread_floor(profile["renderer"]) if profile else None
    if floor and fp["navigator"]["hardwareConcurrency"] < floor:
        return False
    if profile and not vendor_fits(profile["renderer"], host_vendor):
        return False
    if (host_arch and profile and fp["navigator"]["userAgentData"]["platform"] == "Windows"
            and gpu_architecture(profile["renderer"]) != host_arch):
        return False  # same-architecture mode: a drawn claim needs the host's vendor and architecture
    return arch_fits(fp, profile)


def arch_fits(fp, profile):
    """False only for an Apple GPU profile beside a UA-CH architecture that is not arm."""
    return (profile is None or "Apple" not in profile["renderer"]
            or fp["navigator"]["userAgentData"].get("architecture") == "arm")


def generate(os=None, timezone=None, locale=None, seed=None, gpu=None, exit_ip=None, geoip_db=None, host_renderer=None,
             host_families=None, host_platform_version=None, host_display=None, light=False,
             host_screen=None, host_cores=None, host_cpu_vendor="probe"):
    """host_cpu_vendor: GenuineIntel / AuthenticAMD; a draw whose iGPU claim needs the other is rejected, and from_pool
    drops such a claim. Default probes this machine; None applies no rule. host_cores: the CPUs of the machine the browser will run on (default allowed_cpus(), since identities are
    generated on the host); see from_pool. exit_ip (item 13): the zone and locale come from where the address is, unless given explicitly. When it cannot
    be resolved the draw proceeds as without it and a GeoIPWarning says so. light (part 3, L1): only samples with
    DPR 1 are acceptable; a first draw that already has DPR 1 is unchanged.
    host_screen (window fit): the claimed screen and DPR stay the pool's; only the window is made to fit the host's
    work area (fit_window), and a draw is rejected when the host cannot hold MIN_WINDOW at its DPR. None changes nothing."""
    if host_cores is None:
        host_cores = allowed_cpus()
    if host_cpu_vendor == "probe":
        host_cpu_vendor = globals()["host_cpu_vendor"]()  # the parameter shadows the probe
    point = None
    if exit_ip:
        timezone, locale, point = _from_exit_ip(exit_ip, geoip_db, timezone, locale)
    from browserforge.fingerprints import FingerprintGenerator
    rng = random.Random(seed)
    if seed is not None:
        random.seed(seed)  # BrowserForge draws from the global RNG
    # browserforge 1.2.4 raises TypeError on every draw when os=None is
    # passed explicitly; the keyword must be absent for "any OS".
    gen = FingerprintGenerator(browser="chrome", **({"os": os} if os else {}))
    # Same-architecture mode: a drawn Windows claim needs the host's vendor and Dawn architecture. Without one in the budget the
    # first sample that passed every other rule is kept with no GPU claim, so the host's real GPU shows. An unknown host
    # architecture (or no host renderer: None) keeps the draw as it was.
    host_arch = None if gpu else gpu_architecture(host_renderer)
    spare = None
    for _ in range(MAX_DRAWS):
        fp = asdict(gen.generate())
        # an Apple GPU string over an x86 claim is a cross-surface lie
        if not (acceptable(fp) and (not light or dpr_of(fp) == 1)):
            continue
        profile = gpu_for(fp["navigator"]["userAgentData"]["platform"], host_renderer, rng, gpu, fp)[0]
        vendor = None if gpu else host_cpu_vendor
        if gpu_ok(fp, profile, vendor) and (host_screen is None or holds_min_window(host_screen, dpr_of(fp))):
            if host_arch and not gpu_ok(fp, profile, vendor, host_arch):
                # the real iGPU shows once the claim is gone: its thread count must not sit below the host iGPU's floor
                if spare is None and snap_threads(fp["navigator"]["hardwareConcurrency"], host_cores) >= (igpu_thread_floor(host_renderer) or 0):
                    spare = fp
                continue
            out = from_pool(fp, timezone, locale, rng, gpu, host_renderer, host_families, host_platform_version,
                            host_display, host_screen, host_cores, host_cpu_vendor)
            if point:  # drawn after the pool, so an identity without an exit IP is unchanged
                out["config"].update(geolocation_keys(point, rng))
            return _arch_warning(out, host_renderer, host_arch, gpu)
    if spare is not None:
        out = from_pool(spare, timezone, locale, rng, gpu, host_renderer, host_families, host_platform_version,
                        host_display, host_screen, host_cores, host_cpu_vendor, claim_gpu=False)
        if point:
            out["config"].update(geolocation_keys(point, rng))
        out["warnings"].append(f"no pool draw in {MAX_DRAWS} shares the host GPU's vendor and architecture {'/'.join(host_arch)}: "
                               "no GPU claim, the host's real GPU shows")
        return out
    raise RuntimeError(f"no acceptable Chrome sample in {MAX_DRAWS} draws for os={os}")


def _arch_warning(out, host_renderer, host_arch, gpu):
    """One warning when a host renderer was given but its architecture is unknown (a software or non-D3D11 renderer, or an id
    missing from Dawn's table): the draw keeps choice B, a claim from the whole pool with WebGPU blocked. A claim with no
    webGpu:blocked key (a macOS claim on its own Apple host) is the host's own and needs no warning."""
    if host_renderer and host_arch is None and not gpu and "webGpu:blocked" in out["config"]:
        out["warnings"].append("the host GPU's architecture is unknown (no ANGLE D3D11 renderer, or an id Dawn's table lacks): "
                               "the GPU claim is drawn from the whole pool and WebGPU stays blocked")
    return out


GEO_RADIUS_KM = 2


def geolocation_keys(point, rng):
    """The record's (lat, lng) moved to a uniform random spot within GEO_RADIUS_KM, so the identity does not sit on
    the database's own point. accuracy is left to the browser's default."""
    lat, lng = point
    r, theta = GEO_RADIUS_KM * math.sqrt(rng.random()), rng.random() * 2 * math.pi
    return {"geolocation:latitude": round(lat + r * math.cos(theta) / 111.32, 6),
            "geolocation:longitude": round(lng + r * math.sin(theta) / (111.32 * math.cos(math.radians(lat))), 6)}


def _from_exit_ip(exit_ip, geoip_db, timezone, locale):
    from . import geoip
    try:
        found = geoip.lookup(exit_ip, geoip_db)
    except geoip.GeoIPError as e:
        geoip.warn_all([f"the exit IP {exit_ip} was not resolved ({e}): timezone and locale are not derived from it"])
        return timezone, locale, None
    if found["locale"] is None:
        geoip.warn_all([f"no locale for country {found['country']}: the identity keeps its drawn locale beside {found['timezone']}"])
    point = None if None in (found["latitude"], found["longitude"]) else (found["latitude"], found["longitude"])
    return timezone or found["timezone"], locale or found["locale"], point


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
    ap.add_argument("--host-renderer", help="the host's WebGL renderer string (probe.host_renderer): a host of a known Dawn architecture draws only claims of that architecture (or none)")
    ap.add_argument("--probe-executable", help="a Chrome binary: launch it once to read the host's WebGL renderer when --host-renderer is not given (a failed probe claims no GPU)")
    ap.add_argument("--host-fonts", action="store_true", help="limit a Windows claim's fonts to the families this host has (Windows only; elsewhere unknown)")
    ap.add_argument("--host-platform-version", help="the host's UA-CH platformVersion (probe.host_platform_version): wins over the pool's")
    ap.add_argument("--host-display", type=json.loads, help='the host display as JSON (probe.host_display): {"gamut","colorBits","hdr"}; a wide-gamut host gets --force-color-profile=srgb in launch.args')
    ap.add_argument("--host-screen", type=json.loads, help='the host work area as JSON (probe.host_screen): {"availWidth","availHeight"} in physical px; draws that do not fit are rejected')
    ap.add_argument("--host-cpu-vendor", choices=[INTEL_CPU, AMD_CPU, "none"], help="the host's CPU vendor (default: probed): a claimed iGPU of the other vendor is not drawn; none applies no rule")
    ap.add_argument("--host-cores", type=int, help="the host's CPU count (default: os.cpu_count()): a navigator.hardwareConcurrency claim above it snaps down")
    ap.add_argument("--light", action="store_true", help="light mode (part 3): draw only pool samples with DPR 1")
    a = ap.parse_args(argv)
    if a.host_renderer is None and a.probe_executable:
        from . import probe
        a.host_renderer = probe.host_renderer(a.probe_executable)
    if a.host_display is not None and not valid_display(a.host_display):
        sys.exit('gen: --host-display must be {"gamut": "srgb"|"p3"|"rec2020", "colorBits": 8|10, "hdr": true|false}')
    if a.host_screen is not None and not valid_screen(a.host_screen):
        sys.exit('gen: --host-screen must be {"availWidth": <positive int>, "availHeight": <positive int>}')
    families = hostfonts.families() if a.host_fonts else None
    json.dump(generate(a.os, a.timezone, a.locale, a.seed, a.gpu, a.exit_ip, a.geoip_db, a.host_renderer, families, a.host_platform_version, a.host_display, light=a.light, host_screen=a.host_screen, host_cores=a.host_cores,
                       **({"host_cpu_vendor": None if a.host_cpu_vendor == "none" else a.host_cpu_vendor} if a.host_cpu_vendor else {})), sys.stdout)


if __name__ == "__main__":
    main()

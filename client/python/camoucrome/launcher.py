"""The launcher. Pure helpers (build_env, build_args) plus launch()."""
import inspect
import json
import os
import shutil
import tempfile

# Mirrors settings/launcher.json "forbidden_context_options"; tests/test_launcher.py
# asserts the two agree. Each of these duplicates a CAMOU_CONFIG key: a second
# emulation of the same surface either fails (timezone -> kAlreadyInEffect) or
# silently overrides the fork's value.
FORBIDDEN_OPTIONS = frozenset({
    "locale", "timezone_id", "user_agent", "viewport", "screen",
    "device_scale_factor", "geolocation", "color_scheme", "extra_http_headers",
    "has_touch", "is_mobile",
})

BASE_ARGS = ["--no-first-run", "--no-default-browser-check"]


def _as_json(value):
    return value if isinstance(value, str) else json.dumps(value)


FONTCONFIG_ENV = "FONTCONFIG_FILE"
FONTCONFIG_FILES = {"Windows": "settings/fontconfig/windows.conf", "macOS": "settings/fontconfig/macos.conf"}


def _as_dict(v):
    d = json.loads(v) if isinstance(v, str) else (v or {})
    if not isinstance(d, dict):
        raise ValueError(f"config and preset must be JSON objects, got {type(d).__name__}")
    return d


# derive.cc kForms: (ua:osInfo marker, UA-CH platform), in its match order --
# Android and CrOS before Linux, whose marker their osInfo also contains.
OS_INFO_MARKERS = (("Android", "Android"), ("CrOS", "Chrome OS"), ("Windows NT", "Windows"),
                   ("Macintosh", "macOS"), ("Linux", "Linux"))


def effective_keys(config=None, preset=None):
    """The keys the browser ends up with for what the launcher reads: the
    preset's os and locale expanded as preset_loader.cc does, under the
    explicit config (explicit wins). Raises ValueError on a shape the browser
    would ignore, rather than launching with a silently dropped value."""
    p, c, out = _as_dict(preset), _as_dict(config), {}
    markers = {plat: m for m, plat in OS_INFO_MARKERS}

    def set_os(plat):
        out.update({"ua:osInfo": markers[plat], "ua:platform": plat})

    def set_locale(tag):
        primary = tag.split("-")[0]
        out.update({"locale:tag": tag, "navigator.language": tag,
                    "navigator.languages": [tag] + ([primary] if primary != tag else [])})

    if p.get("os") in markers:
        set_os(p["os"])
    if isinstance(p.get("locale"), str):
        set_locale(p["locale"])
    # preset_loader.cc OverridePresetGroups: an explicit member of the preset's
    # OS pair or locale triple re-derives the whole group from it.
    info, plat = c.get("ua:osInfo"), c.get("ua:platform")
    fam = next((pl for m, pl in OS_INFO_MARKERS if isinstance(info, str) and m in info), None)
    if fam is None and plat in markers:
        fam = plat
    if fam and "ua:osInfo" in out:
        set_os(fam)
    langs = c.get("navigator.languages")
    head = (langs[0] if isinstance(langs, list) and langs and isinstance(langs[0], str)
            else next((c[k] for k in ("navigator.language", "locale:tag") if isinstance(c.get(k), str)), None))
    if head and "locale:tag" in out:
        set_locale(head)
    out.update(c)
    langs = out.get("navigator.languages")
    if langs is not None and not (isinstance(langs, list) and all(isinstance(l, str) for l in langs)):
        raise ValueError(f"navigator.languages must be a list of strings, got {langs!r}")
    return out


def claimed_os(config=None, preset=None):
    """derive.cc ClaimedOs over the effective keys: a recognised ua:osInfo,
    else ua:platform, else None."""
    keys = effective_keys(config, preset)
    info = keys.get("ua:osInfo")
    for marker, plat in OS_INFO_MARKERS:
        if isinstance(info, str) and marker in info:
            return plat
    return keys.get("ua:platform")


def fontconfig_for(config=None, preset=None, fonts_dir=None, executable_path=None):
    """The FONTCONFIG_FILE for the claimed OS (contract launch.fontconfig): the
    generated conf beside the bundled fonts dir, which lives beside the
    executable in an archive. Linux claim or no fonts dir: None. A fonts dir
    without its conf raises: host fonts under a Windows claim are a tell."""
    os_name = claimed_os(config, preset)
    if os_name not in FONTCONFIG_FILES:
        return None
    if fonts_dir is None and executable_path is not None:
        cand = os.path.join(os.path.dirname(os.path.abspath(str(executable_path))), "fonts")
        fonts_dir = cand if os.path.isdir(cand) else None
    if fonts_dir is None:
        return None
    conf = os.path.abspath(os.path.join(str(fonts_dir), os.pardir, FONTCONFIG_FILES[os_name]))
    if not os.path.isfile(conf):
        raise FileNotFoundError(f"fonts dir {fonts_dir} has no {FONTCONFIG_FILES[os_name]} beside it: {conf}")
    return conf


CONFIG_CHUNK_CHARS = 30000  # Linux caps one environment string at 128 KiB; a macOS identity (191 voices, 409 faces) is ~140 KB


def config_env(raw, name="CAMOU_CONFIG"):
    """`name` when it fits in one environment string, else name_1..N in order (the reader concatenates)."""
    if len(raw) <= CONFIG_CHUNK_CHARS:
        return {name: raw}
    chunks = [raw[i:i + CONFIG_CHUNK_CHARS] for i in range(0, len(raw), CONFIG_CHUNK_CHARS)]
    return {f"{name}_{n}": c for n, c in enumerate(chunks, 1)}


def build_env(config=None, preset=None, strict=False, base=None, fontconfig=None):
    """The child environment: every CAMOU_* of the parent dropped, then the
    given config/preset set. Dropping first is deliberate -- a stale
    CAMOU_CONFIG_1 in the shell would otherwise win over `config`.
    `fontconfig` (from fontconfig_for) sets FONTCONFIG_FILE; the parent's
    is never inherited (a host conf under a Windows claim is a tell)."""
    effective_keys(config, preset)  # raises on a shape the browser would drop
    env = {k: v for k, v in (os.environ if base is None else base).items()
           if not k.startswith("CAMOU_") and k != FONTCONFIG_ENV}
    if config is not None:
        env.update(config_env(_as_json(config)))
    if preset is not None:
        env.update(config_env(_as_json(preset), "CAMOU_PRESET"))
    if strict:
        env["CAMOU_CONFIG_STRICT"] = "1"
    if fontconfig:
        env[FONTCONFIG_ENV] = fontconfig
    return env


def accept_lang_of(config, preset=None):
    """The --accept-lang value the config implies: navigator.languages joined,
    else locale:tag, else None -- over the effective keys, so a preset's
    locale counts. Measured 2026-09-10: without the flag a French config
    still sends Accept-Language: en-US,en;q=0.9; with it Chrome sends
    fr-FR,fr;q=0.9, adding the q-values itself."""
    keys = effective_keys(config, preset)
    languages = keys.get("navigator.languages") or (
        [keys["locale:tag"]] if keys.get("locale:tag") else [])
    return ",".join(languages) or None


def build_args(window=None, dpr=None, extra=(), headless=True, user_data_dir=None,
               accept_lang=None, extensions=(), spki_list=()):
    """Launch flags the C++ deliberately left to the launcher: window size so
    inner/outer/client widths cohere with screen.*, and the device scale
    factor. Timezone, locale and UA are NOT flags: they come through config.

    This is the WHOLE argv besides what the driver must add (the debugging
    pipe, the profile dir): launch() passes ignore_default_args, because
    Playwright's defaults carry --disable-features=<18 features>,
    --blink-settings=primaryHoverType=..., --hide-scrollbars, --mute-audio,
    --force-color-profile=srgb and more, each moving a page-visible surface
    off the compiled defaults (settings/launcher.json, "why_ignore_default_args")."""
    args = list(BASE_ARGS)
    if headless:
        args.append("--headless=new")
    # Both are Playwright defaults too, so ignore_default_args drops them:
    # without the pipe the driver waits forever on Browser.getVersion, and
    # without the profile dir Chrome runs --incognito in a scoped dir
    # (measured 2026-09-10).
    args.append("--remote-debugging-pipe")
    if user_data_dir is not None:
        args.append(f"--user-data-dir={user_data_dir}")
    if window is not None:
        args.append(f"--window-size={window[0]},{window[1]}")
    if dpr is not None:
        args.append(f"--force-device-scale-factor={dpr}")
    if accept_lang:
        args.append(f"--accept-lang={accept_lang}")
    if extensions:
        paths = ",".join(str(e) for e in extensions)
        args += [f"--disable-extensions-except={paths}", f"--load-extension={paths}"]
    if spki_list:
        args.append("--ignore-certificate-errors-spki-list=" + ",".join(spki_list))
    args.extend(extra)
    return args


def launch(playwright, executable_path, *, config=None, preset=None,
           strict=False, user_data_dir=None, window=None, dpr=None,
           headless=True, args=(), extensions=(), spki_list=(), fonts_dir=None, **options):
    """Launches a persistent context (one profile per identity) and returns it.

    Never add_init_script anything a page could enumerate: both patchright
    and stock run a user's init script in the MAIN world (measured
    2026-09-10). patchright's evaluate runs in an isolated world; use that.

    `playwright` is the object from patchright.sync_api.sync_playwright() (or
    the async one); passing stock playwright's works too but loses the
    Runtime.enable guarantee -- scripts/verify_sp6b_driver.py measures the
    difference. Any option in FORBIDDEN_OPTIONS raises: those surfaces are
    configured through CAMOU_CONFIG only. `extensions` are unpacked
    extension directories (--load-extension); `spki_list` are base64
    SHA-256 SPKI hashes whose certificate errors are ignored (a MITM proxy's
    CA). The Accept-Language header follows the config's (else the preset's)
    languages. A temp profile (no `user_data_dir`) is removed on close or on a
    failed launch.
    `fonts_dir` is the bundled font directory (default: `fonts` beside the
    executable when present); FONTCONFIG_FILE then names the conf of the
    claimed OS so its families resolve.
    """
    bad = FORBIDDEN_OPTIONS.intersection(options)
    if bad:
        raise ValueError(
            f"{sorted(bad)} must come through CAMOU_CONFIG, not the driver: "
            "a second emulation of the same surface fights the fork's value")
    temp = user_data_dir is None
    if temp:
        user_data_dir = tempfile.mkdtemp(prefix="camoucrome-")
    try:
        ctx = playwright.chromium.launch_persistent_context(
            user_data_dir,
            executable_path=str(executable_path),
            headless=headless,
            ignore_default_args=True,
            env=build_env(config, preset, strict,
                          fontconfig=fontconfig_for(config, preset, fonts_dir, executable_path)),
            args=build_args(window, dpr, args, headless, user_data_dir,
                            accept_lang_of(config, preset), extensions, spki_list),
            # Playwright otherwise emulates a 1280x720 viewport through
            # Emulation.setDeviceMetricsOverride, which fights screen.* and the
            # window size above.
            no_viewport=True,
            **options)
    except BaseException:
        if temp:
            shutil.rmtree(user_data_dir, ignore_errors=True)
        raise
    if not temp:
        return ctx
    # A temp profile lives as long as the context, including a failed async launch.
    remove = lambda *_: shutil.rmtree(user_data_dir, ignore_errors=True)  # noqa: E731
    if inspect.isawaitable(ctx):
        async def started():
            try:
                c = await ctx
            except BaseException:
                remove()
                raise
            c.on("close", remove)
            return c
        return started()
    ctx.on("close", remove)
    return ctx

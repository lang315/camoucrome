"""The launcher. Pure helpers (build_env, build_args) plus launch()."""
import json
import os
import tempfile

# Mirrors settings/launcher.json "forbidden_context_options"; tests/test_launcher.py
# asserts the two agree. Each of these duplicates a CAMOU_CONFIG key: a second
# emulation of the same surface either fails (timezone -> kAlreadyInEffect) or
# silently overrides the fork's value.
FORBIDDEN_OPTIONS = frozenset({
    "locale", "timezone_id", "user_agent", "viewport", "screen",
    "device_scale_factor", "geolocation", "color_scheme", "extra_http_headers",
})

BASE_ARGS = ["--no-first-run", "--no-default-browser-check"]


def _as_json(value):
    return value if isinstance(value, str) else json.dumps(value)


def build_env(config=None, preset=None, strict=False, base=None):
    """The child environment: every CAMOU_* of the parent dropped, then the
    given config/preset set. Dropping first is deliberate -- a stale
    CAMOU_CONFIG_1 in the shell would otherwise win over `config`."""
    env = {k: v for k, v in (os.environ if base is None else base).items()
           if not k.startswith("CAMOU_")}
    if config is not None:
        env["CAMOU_CONFIG"] = _as_json(config)
    if preset is not None:
        env["CAMOU_PRESET"] = _as_json(preset)
    if strict:
        env["CAMOU_CONFIG_STRICT"] = "1"
    return env


def build_args(window=None, dpr=None, extra=(), headless=True, user_data_dir=None):
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
    args.extend(extra)
    return args


def launch(playwright, executable_path, *, config=None, preset=None,
           strict=False, user_data_dir=None, window=None, dpr=None,
           headless=True, args=(), **options):
    """Launches a persistent context (one profile per identity) and returns it.

    Never add_init_script anything a page could enumerate: both patchright
    and stock run a user's init script in the MAIN world (measured
    2026-09-10). patchright's evaluate runs in an isolated world; use that.

    `playwright` is the object from patchright.sync_api.sync_playwright() (or
    the async one); passing stock playwright's works too but loses the
    Runtime.enable guarantee -- scripts/verify_sp6b_driver.py measures the
    difference. Any option in FORBIDDEN_OPTIONS raises: those surfaces are
    configured through CAMOU_CONFIG only.
    """
    bad = FORBIDDEN_OPTIONS.intersection(options)
    if bad:
        raise ValueError(
            f"{sorted(bad)} must come through CAMOU_CONFIG, not the driver: "
            "a second emulation of the same surface fights the fork's value")
    if user_data_dir is None:
        user_data_dir = tempfile.mkdtemp(prefix="camoucrome-")
    return playwright.chromium.launch_persistent_context(
        user_data_dir,
        executable_path=str(executable_path),
        headless=headless,
        ignore_default_args=True,
        env=build_env(config, preset, strict),
        args=build_args(window, dpr, args, headless, user_data_dir),
        # Playwright otherwise emulates a 1280x720 viewport through
        # Emulation.setDeviceMetricsOverride, which fights screen.* and the
        # window size above.
        no_viewport=True,
        **options)

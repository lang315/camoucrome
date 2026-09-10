"""Camoucrome Python client: launch the patched browser with a fingerprint.

    from patchright.sync_api import sync_playwright
    import camoucrome

    with sync_playwright() as pw:
        ctx = camoucrome.launch(pw, "/path/to/chrome", preset=preset_json,
                                config=camoucrome.per_instance_config(),
                                window=(1920, 1040))
        page = ctx.pages[0]

Everything anti-detect lives in the browser and in the driver (patchright's
Node driver never sends Runtime.enable); this package only carries the
configuration into the process and refuses the options that would fight it.
The contract it implements is settings/launcher.json in the repository.
"""
from .identity import SEED_KEYS, per_instance_config
from .launcher import FORBIDDEN_OPTIONS, accept_lang_of, build_args, build_env, launch

__all__ = ["FORBIDDEN_OPTIONS", "SEED_KEYS", "accept_lang_of", "build_args", "build_env", "launch",
           "per_instance_config"]

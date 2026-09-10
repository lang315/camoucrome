"""Camoucrome Python client: launch the patched browser with a fingerprint.

    from patchright.sync_api import sync_playwright
    import camoucrome

    with sync_playwright() as pw:
        ctx = camoucrome.launch(pw, "/path/to/chrome", config={...}, window=(1920, 1040))
        page = ctx.pages[0]

Everything anti-detect lives in the browser and in the driver (patchright's
Node driver never sends Runtime.enable); this package only carries the
configuration into the process and refuses the options that would fight it.
The contract it implements is settings/launcher.json in the repository.
"""
from .launcher import FORBIDDEN_OPTIONS, build_args, build_env, launch

__all__ = ["FORBIDDEN_OPTIONS", "build_args", "build_env", "launch"]

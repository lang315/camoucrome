"""Verifies chrome://credits lists Cursory under its LGPL (LGPL-3.0 section 4(c)).

Needs `chrome` (content_shell has no chrome://credits) built with
generate_about_credits = true (settings/release-args.gn) and the licenses.py
ADDITIONAL_PATHS entry for components/camoucfg_lgpl. Three rows, each states
its expected count; RED (absent) before those two changes, GREEN after.

Page-visible surfaces: none change. The credits page is a browser-internal
WebUI document built at compile time from README.chromium files; no page of
any origin can load chrome://credits, no Blink code, config key or runtime
path is touched. So Object.keys(window) on a normal page cannot move; no
stock window-keys baseline JSON exists in baselines/ (the other verifies
compare configured against unconfigured runs), so that check is skipped here.

Run on the box like the other verify_*.py (clean env, venv python).
"""
import sys

from playwright.sync_api import sync_playwright

import lib_shell

R1 = "1 chrome://credits has a Cursory entry"
R2 = "2 chrome://credits carries the LGPL text (GNU LESSER GENERAL PUBLIC LICENSE)"
R3 = "3 the Cursory entry links its upstream URL"
CHECKS = ((R1, "Cursory"), (R2, "GNU LESSER GENERAL PUBLIC LICENSE"),
          (R3, "github.com/Vinyzu/cursory"))


def credits_text():
    proc = None
    try:
        proc = lib_shell.launch(None, shell=lib_shell.CHROME, extra_flags=lib_shell.CHROME_FLAGS)
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{proc.cdp_port}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("chrome://credits", wait_until="load")
            return page.evaluate("document.documentElement.innerHTML"), None
    except Exception as exc:  # noqa: BLE001
        return None, exc
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)


def main():
    text, err = credits_text()
    out = {}
    for name, needle in CHECKS:
        out[name] = "UNMEASURED" if err else ("PASS" if needle in text else "FAIL")
    for name in sorted(out):
        print(f"{out[name]:10} {name}")
    if err:
        print(f"      {err!r}")
    elif "Cursory" not in text:
        print(f"      page is {len(text)} chars; 'Chromium' present: {'Chromium' in text} "
              "(a placeholder page means generate_about_credits is off)")
    return 0 if len(out) == len(CHECKS) and all(v == "PASS" for v in out.values()) else 1


if __name__ == "__main__":
    sys.exit(main())

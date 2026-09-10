"""Probe command for scripts/verify_sp6b_driver.py: launch through this
package with the chosen driver, load a URL, print the page's own report
(the text of #o, written by the page's main-world script) and the browser
process's argv as JSON. The caller sets DEBUG=pw:protocol and reads the
driver's protocol log from stderr.

    python -m camoucrome.probe --driver patchright|stock --executable EXE --url URL
"""
import argparse
import importlib
import json
import os
import sys

from . import launch


def browser_argv(executable):
    """argv of the browser (not renderer/gpu) process running `executable`,
    read from /proc. Linux only; empty elsewhere."""
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                argv = f.read().split(b"\0")[:-1]
        except OSError:
            continue
        # Chromium rewrites its own cmdline into one space-joined string
        # (process title), so a single element is split on spaces.
        if len(argv) == 1:
            argv = argv[0].split(b" ")
        if argv and argv[0].decode(errors="replace") == executable and \
                not any(a.startswith(b"--type=") for a in argv):
            return [a.decode(errors="replace") for a in argv]
    return []


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--driver", choices=["patchright", "stock"], required=True)
    ap.add_argument("--executable", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--config")
    ap.add_argument("--preset")
    a = ap.parse_args()
    module = "patchright" if a.driver == "patchright" else "playwright"
    sync_playwright = importlib.import_module(f"{module}.sync_api").sync_playwright
    with sync_playwright() as pw:
        ctx = launch(pw, a.executable, config=a.config, preset=a.preset,
                     args=["--no-sandbox"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        # SP2 4.2: a driver's init script must not be observable from the
        # main world. The probe page reports typeof window.__camou_init.
        page.add_init_script("window.__camou_init = 1")
        page.goto(a.url, wait_until="load")
        report = page.locator("#o").text_content()
        argv = browser_argv(a.executable)
        ctx.close()
    json.dump({"driver": f"python-{a.driver}", "module": module,
               "report": json.loads(report), "argv": argv}, sys.stdout)


if __name__ == "__main__":
    main()

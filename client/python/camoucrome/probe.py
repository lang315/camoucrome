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
import pathlib
import os
import subprocess
import sys
import tempfile

from . import human_click, launch


def windows_argv(executable):
    """browser_argv on Windows: Win32_Process has each process's command line
    as one string; CommandLineToArgvW splits it the way the process itself
    did. ConvertTo-Json gives a bare object for one match, a list for more."""
    import ctypes
    query = (f"Get-CimInstance Win32_Process -Filter \"Name='{os.path.basename(executable)}'\""
             " | Select-Object ExecutablePath,CommandLine | ConvertTo-Json -Compress")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", query],
                         capture_output=True, text=True).stdout.strip()
    procs = json.loads(out) if out else []
    split = ctypes.windll.shell32.CommandLineToArgvW
    split.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    split.restype = ctypes.POINTER(ctypes.c_wchar_p)
    ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    for p in procs if isinstance(procs, list) else [procs]:
        # A null CommandLine (access denied) must not reach CommandLineToArgvW,
        # which would return this process's own argv.
        if not p["CommandLine"] or os.path.normcase(p["ExecutablePath"] or "") != \
                os.path.normcase(os.path.abspath(executable)):
            continue
        n = ctypes.c_int()
        ptr = split(p["CommandLine"], ctypes.byref(n))
        argv = [ptr[i] for i in range(n.value)]
        ctypes.windll.kernel32.LocalFree(ctypes.cast(ptr, ctypes.c_void_p))
        if not any(a.startswith("--type=") for a in argv):
            return argv
    return []


def browser_argv(executable):
    """argv of the browser (not renderer/gpu) process running `executable`,
    read from /proc on Linux and Win32_Process on Windows; empty elsewhere."""
    if os.name == "nt":
        return windows_argv(executable)
    if not os.path.isdir("/proc"):
        return []
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


def run_scenario(pw, a):
    """scripts/verify_human_click_clients.py row `a.scenario` -> (page log, extra).
    The log is the page's own #o; `extra` carries what the page cannot see
    (error messages, a second context's log)."""
    n, url, exe = a.scenario, a.url, a.executable
    kw = dict(headless=not a.headed, args=["--no-sandbox"])
    if n == "B4":  # launch must refuse human_click without humanize, before any browser
        extra = {}
        for key, cfg in (("nohumanize", None), ("false", json.dumps({"humanize:enabled": False}))):
            try:
                launch(pw, exe, config=cfg, human_click=True, **kw).close()
                extra[key] = None
            except Exception as e:  # noqa: BLE001 - the message is the datum
                extra[key] = str(e)
        return {}, extra
    if n not in ("A1", "A2", "A3", "A4", "A5", "A6", "A7", "stock-missing", "B1", "B2", "B3"):
        raise ValueError(f"unknown scenario {n}")

    def log_of(page):
        page.wait_for_timeout(500)  # the page's 100 ms sync catches the last scroll
        return json.loads(page.locator("#o").text_content())

    def open_page(ctx):
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, wait_until="load")
        return page

    def err(fn):
        try:
            fn()
            return None
        except Exception as e:  # noqa: BLE001
            return str(e)

    def wrapper_hits():
        return sys.modules["camoucrome.human_click"].wrapper_hits

    ctx = launch(pw, exe, config=a.config, human_click=n.startswith("B"), **kw)
    extra, others = None, []
    try:
        page = open_page(ctx)
        loc = page.locator("#t")
        if n in ("A1", "A7"):
            for _ in range(20 if n == "A1" else 5):
                human_click(loc)
        elif n in ("A2", "A3", "A4", "A5"):
            human_click(loc)
        elif n == "A6":
            human_click(page.locator("#late"))
            extra = {"missing": err(lambda: human_click(page.locator("#nope"), timeout=500)),
                     "strict": err(lambda: human_click(page.locator(".dup"), timeout=500)),
                     "hidden": err(lambda: human_click(page.locator("#hid"), timeout=500))}
        elif n == "stock-missing":
            extra = {"missing": err(lambda: page.locator("#nope").click(timeout=500)),
                     "strict": err(lambda: page.locator(".dup").click(timeout=500)),
                     "hidden": err(lambda: page.locator("#hid").click(timeout=500))}
        elif n == "B1":
            for _ in range(10):
                loc.click()
                page.click("#t")
        elif n == "B3":
            page.click("#t", position={"x": 5, "y": 5})
            hits = [wrapper_hits()]
            page.click("#t", force=True)
            hits.append(wrapper_hits())
            loc.click(trial=True)
            hits.append(wrapper_hits())
            extra = {"hits_after": hits}
        elif n == "B2":  # contexts launch() did not flag: a direct one, and a launch() without the flag
            tmp = tempfile.mkdtemp(prefix="camoucrome-b2-")
            direct = pw.chromium.launch_persistent_context(tmp, executable_path=exe, **kw)
            others.append(direct)
            plain = launch(pw, exe, config=a.config, human_click=False, **kw)
            others.append(plain)
            extra = {}
            for key, c in (("direct", direct), ("plain", plain)):
                p = open_page(c)
                for _ in range(3):
                    p.click("#t")
                extra[key] = log_of(p)
        log = log_of(page)
    finally:
        for c in [ctx, *others]:
            c.close()
    return log, extra


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--driver", choices=["patchright", "stock"], required=True)
    ap.add_argument("--executable", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--config", help="JSON object, or @path to a file holding it (a macOS identity is ~140 KB, past Linux's 128 KiB single-argument limit)")
    ap.add_argument("--preset")
    ap.add_argument("--window", help="W,H -> --window-size")
    ap.add_argument("--dpr", type=float)
    ap.add_argument("--strict", action="store_true", help="CAMOU_CONFIG_STRICT=1")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--extension", action="append", default=[])
    ap.add_argument("--spki", action="append", default=[])
    ap.add_argument("--arg", action="append", default=[], help="extra browser argv, verbatim")
    ap.add_argument("--scenario", help="verify_human_click_clients row: load --url, act, print the page log")
    ap.add_argument("--fonts-dir", help="bundled font dir (FONTCONFIG_FILE follows the claimed OS)")
    a = ap.parse_args()
    window = tuple(int(v) for v in a.window.split(",")) if a.window else None
    module = "patchright" if a.driver == "patchright" else "playwright"
    sync_playwright = importlib.import_module(f"{module}.sync_api").sync_playwright
    with sync_playwright() as pw:
        if a.config and a.config.startswith("@"):
            a.config = pathlib.Path(a.config[1:]).read_text(encoding="utf-8")
        if a.scenario:
            try:
                log, extra = run_scenario(pw, a)
                error = None
            except Exception as e:  # noqa: BLE001 - surfaced in the JSON; the verify prints it
                log, extra, error = None, None, str(e)
            hits = sys.modules["camoucrome.human_click"].wrapper_hits
            json.dump({"log": log, "error": error, "wrapper_hits": hits, "extra": extra}, sys.stdout)
            return
        # B (launch(human_click=True)) needs humanize:enabled in the config.
        humanize = bool(a.config) and json.loads(a.config).get("humanize:enabled") is True
        ctx = launch(pw, a.executable, config=a.config, preset=a.preset,
                     strict=a.strict, window=window, dpr=a.dpr, headless=not a.headed,
                     extensions=a.extension, spki_list=a.spki, args=["--no-sandbox", *a.arg],
                     fonts_dir=a.fonts_dir, human_click=humanize)
        try:  # a failed goto must still close: the temp profile goes on close
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            # SP2 4.2: a driver's init script must not be observable from the
            # main world. The probe page reports typeof window.__camou_init.
            page.add_init_script("window.__camou_init = 1")
            page.goto(a.url, wait_until="load")
            # A page that reports from a worker writes #o after load; wait for it.
            page.wait_for_function("document.getElementById('o').textContent !== ''", timeout=30000)
            # SP2d: exercise A (the helper) and B (page.click) before reporting.
            if humanize:
                if not page.locator("#camou-click").count():
                    raise RuntimeError("humanize on but the page has no #camou-click")
                human_click(page.locator("#camou-click"))
                page.click("#camou-click")
            report = page.locator("#o").text_content()
            argv = browser_argv(a.executable)
        finally:
            ctx.close()
    json.dump({"driver": f"python-{a.driver}", "module": module,
               "report": json.loads(report), "argv": argv}, sys.stdout)


if __name__ == "__main__":
    main()

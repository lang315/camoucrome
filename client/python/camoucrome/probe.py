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

from . import launch
from .gen import valid_display, valid_screen


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


def proc_candidates(proc_root, executable):
    """argv of every browser (not renderer/gpu) process running `executable` in a /proc-style directory. More than one
    means a stray earlier run is still alive: the caller must not trust which one it reads (2026-10-29: a stray headless
    chrome made all three patchright rows of verify_sp6b_driver compare a stock-style argv)."""
    if not os.path.isdir(proc_root):
        return []
    found = []
    for pid in sorted((p for p in os.listdir(proc_root) if p.isdigit()), key=int):
        try:
            with open(os.path.join(proc_root, pid, "cmdline"), "rb") as f:
                argv = f.read().split(b"\0")[:-1]
        except OSError:
            continue
        # Chromium rewrites its own cmdline into one space-joined string
        # (process title), so a single element is split on spaces.
        if len(argv) == 1:
            argv = argv[0].split(b" ")
        if argv and argv[0].decode(errors="replace") == executable and \
                not any(a.startswith(b"--type=") for a in argv):
            found.append([a.decode(errors="replace") for a in argv])
    return found


def browser_candidates(executable):
    """proc_candidates over /proc on Linux; on Windows Win32_Process, the first match only (one candidate)."""
    if os.name == "nt":
        argv = windows_argv(executable)
        return [argv] if argv else []
    return proc_candidates("/proc", executable)


def browser_argv(executable):
    """The first candidate's argv, [] when there is none."""
    found = browser_candidates(executable)
    return found[0] if found else []


HOST_GL_JS = """() => { const g = document.createElement('canvas').getContext('webgl');
  const e = g && g.getExtension('WEBGL_debug_renderer_info');
  return e ? g.getParameter(e.UNMASKED_RENDERER_WEBGL) : null; }"""


SOFTWARE_MARKERS = ("swiftshader", "llvmpipe", "software", "basic render")


def _probe(executable, js, timeout_s):
    """One headless launch through the package launcher with no config; the page's evaluate() result, None on any failure."""
    try:
        from patchright.sync_api import sync_playwright
        with sync_playwright() as pw:
            ctx = launch(pw, executable, headless=True, timeout=timeout_s * 1000)
            try:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto("about:blank", timeout=timeout_s * 1000)
                # shortcut: no wall-clock bound on evaluate, upgrade if a hung GPU process is seen
                return page.evaluate(js)
            finally:
                try:
                    ctx.close()
                except Exception:
                    pass
    except Exception:
        return None


def host_renderer(executable, timeout_s=30):
    """The host's real WebGL renderer, read once at identity generation.

    None on any failure, and when the browser reports a software renderer
    (no usable GPU): pinning that into an identity is a bot tell.
    Launches through the package launcher with no config, so the argv is the
    contract's; Playwright's default --use-angle=swiftshader-webgl would
    report SwiftShader.
    """
    r = _probe(executable, HOST_GL_JS, timeout_s)
    if not isinstance(r, str) or not r or any(m in r.lower() for m in SOFTWARE_MARKERS):
        return None
    return r


HOST_PV_JS = "() => navigator.userAgentData.getHighEntropyValues(['platformVersion']).then(v => v.platformVersion)"


def host_platform_version(executable, timeout_s=30):
    """The host's real UA-CH platformVersion (Windows 10 reports 10.0.0, Windows 11 13.0.0 or later); None on any failure."""
    r = _probe(executable, HOST_PV_JS, timeout_s)
    return r if isinstance(r, str) and r else None


HOST_DISPLAY_JS = """() => ({gamut: matchMedia('(color-gamut: rec2020)').matches ? 'rec2020' : matchMedia('(color-gamut: p3)').matches ? 'p3' : 'srgb', colorBits: matchMedia('(color: 10)').matches ? 10 : 8, hdr: matchMedia('(dynamic-range: high)').matches})"""


def host_display(executable, timeout_s=30):
    """The host display's {"gamut": srgb|p3|rec2020, "colorBits": 8|10, "hdr": bool}; None on any failure or odd shape.
    Reads in HEADLESS mode: a headless read may not see a wide-gamut display (unverified, Task 3 Step 5)."""
    r = _probe(executable, HOST_DISPLAY_JS, timeout_s)
    return r if valid_display(r) else None


HOST_ZONE_JS = "() => ({timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, locale: navigator.language})"


def host_zone(executable, timeout_s=30):
    """The host's real IANA time zone and navigator.language, read with no config (rule 5); None on any failure."""
    r = _probe(executable, HOST_ZONE_JS, timeout_s)
    if isinstance(r, dict) and all(isinstance(r.get(k), str) and r[k] for k in ("timezone", "locale")):
        return {"timezone": r["timezone"], "locale": r["locale"]}
    return None


def host_screen():
    """The primary monitor's work area in PHYSICAL px, {"availWidth", "availHeight"}; None off Windows or on any failure.
    The process is made DPI-aware first, so the rectangle is not scaled."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        ctypes.windll.user32.SetProcessDPIAware()
        r = wintypes.RECT()
        if not ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0):  # SPI_GETWORKAREA
            return None
        out = {"availWidth": r.right - r.left, "availHeight": r.bottom - r.top}
        return out if valid_screen(out) else None
    except Exception:
        return None


def host_draw(executable):
    """The host facts gen.generate() takes; a probe that returns None is left out (no claim, rule 5),
    except host_renderer and host_families, which generate() reads as "unknown host"."""
    from . import hostfonts
    d = dict(host_renderer=host_renderer(executable), host_families=hostfonts.families(),
             host_display=host_display(executable), host_platform_version=host_platform_version(executable),
             host_screen=host_screen())
    return {k: v for k, v in d.items() if v is not None or k in ("host_renderer", "host_families")}


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
    ap.add_argument("--fonts-dir", help="bundled font dir (FONTCONFIG_FILE follows the claimed OS)")
    ap.add_argument("--proxy", help="proxy server URL (verify_sp6b_driver's proxy mode: C1 must hold with one set)")
    ap.add_argument("--proxy-bypass")
    ap.add_argument("--proxy-user")
    ap.add_argument("--proxy-pass")
    a = ap.parse_args()
    window = tuple(int(v) for v in a.window.split(",")) if a.window else None
    module = "patchright" if a.driver == "patchright" else "playwright"
    sync_playwright = importlib.import_module(f"{module}.sync_api").sync_playwright
    with sync_playwright() as pw:
        if a.config and a.config.startswith("@"):
            a.config = pathlib.Path(a.config[1:]).read_text(encoding="utf-8")
        ctx = launch(pw, a.executable, config=a.config, preset=a.preset,
                     strict=a.strict, window=window, dpr=a.dpr, headless=not a.headed,
                     extensions=a.extension, spki_list=a.spki, args=["--no-sandbox", *a.arg],
                     fonts_dir=a.fonts_dir,
                     proxy={"server": a.proxy, "bypass": a.proxy_bypass, "username": a.proxy_user,
                            "password": a.proxy_pass} if a.proxy else None)
        try:  # a failed goto must still close: the temp profile goes on close
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            # SP2 4.2: a driver's init script must not be observable from the
            # main world. The probe page reports typeof window.__camou_init.
            page.add_init_script("window.__camou_init = 1")
            page.goto(a.url, wait_until="load")
            # A page that reports from a worker writes #o after load; wait for it.
            page.wait_for_function("document.getElementById('o').textContent !== ''", timeout=30000)
            report = page.locator("#o").text_content()
            candidates = browser_candidates(a.executable)
            argv = candidates[0] if candidates else []
        finally:
            ctx.close()
    json.dump({"driver": f"python-{a.driver}", "module": module,
               "report": json.loads(report), "argv": argv,
               "strays": max(len(candidates) - 1, 0)}, sys.stdout)


if __name__ == "__main__":
    main()

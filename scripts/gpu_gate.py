"""The GPU-process crash gate for browser runs on the Windows host.

S4 (docs/superpowers/measurements/2026-10-12-s4-gpu-session0.md): in Windows
session 0, where anything started through sshd, sshgate or Win32_Process runs,
the GPU process crashes once per launch, stock included. A renderer that
queried it in that window latches empty answers for its life: HEVC
["", false], sometimes a null WebGPU adapter and WebGL. A launch whose
chrome://gpu reports a crash measured nothing GPU-backed, so its rows are
UNMEASURED, never PASS or FAIL. Off Windows every entry point is a no-op.

  python gpu_gate.py PORT   prints the crash count of the browser on that DevTools port
"""
import os
import re
import subprocess
import sys
import time

# chrome://gpu nests shadow roots; every li/tr's text, one per line (S4's s4probe.gpu_page).
GPU_JS = ("(()=>{const o=[];const w=r=>{for(const e of r.querySelectorAll('*')){if(e.tagName==='LI'||e.tagName==='TR')"
          "o.push(e.textContent.replace(/\\s+/g,' ').trim());if(e.shadowRoot)w(e.shadowRoot)}};w(document);return o.join('\\n')})()")
# 2026-10-13 on the host: "GPU process crash count :1" in session 0, ":0" in session 1.
CRASH = re.compile(r"^GPU process crash count\s*:\s*(\d+)\s*$", re.M)


class Unmeasured(Exception):
    """A run that measured nothing; its rows are neither PASS nor FAIL."""


class GpuCrashed(Unmeasured):
    def __init__(self, n):
        self.n = n
        super().__init__(f"UNMEASURED gpu-crash={'unknown' if n is None else n}")


def crash_count(text):
    """The count from a chrome://gpu text, or None when the line is missing (never 0)."""
    m = CRASH.search(text or "")
    return int(m.group(1)) if m else None


def check(n):
    """None (the page had no count) is as unmeasured as a crash."""
    if n != 0:
        raise GpuCrashed(n)


def read_page(page, tries=20):
    page.goto("chrome://gpu", wait_until="load", timeout=15000)
    text = ""
    for _ in range(tries):
        text = page.evaluate(GPU_JS)
        if CRASH.search(text):
            break
        time.sleep(0.25)
    return crash_count(text)


def read_ctx(ctx):
    """The crash count of the browser behind a Playwright/patchright context, from a page of its own.
    A read that fails is None (unmeasured), never an exception that voids the caller's other rows."""
    try:
        page = ctx.new_page()
        try:
            return read_page(page)
        finally:
            page.close()
    except Exception:  # noqa: BLE001 - an unreadable count is unmeasured, never 0
        return None


def read_port(port, timeout=60):
    """The crash count of the browser on a DevTools port. The read runs in a child
    process, because the caller may be inside a sync Playwright block already."""
    try:
        p = subprocess.run([sys.executable, os.path.abspath(__file__), str(port)],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    tail = (p.stdout.strip().splitlines() or ["None"])[-1]
    return int(tail) if tail.isdigit() else None


def session_id():
    """This process's Windows session id (0 = services), or None off Windows."""
    if os.name != "nt":
        return None
    import ctypes
    sid = ctypes.c_ulong()
    ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(sid))
    return sid.value


def session_problem(sid):
    if sid == 0:
        return ("UNMEASURED session=0: start this through scripts/windows/run-interactive.ps1 "
                "(in session 0 the GPU process crashes once per launch)")
    return None


def require_interactive():
    """Exit 3 in session 0. CAMOU_ALLOW_SESSION0=1 lets a RED run through, so the
    per-launch crash gates behind this can be seen to trip."""
    why = session_problem(session_id())
    if not why:
        return
    if os.environ.get("CAMOU_ALLOW_SESSION0") == "1":
        print("NOTE: CAMOU_ALLOW_SESSION0=1: session 0 allowed (a RED run)", flush=True)
        return
    print(why, flush=True)
    sys.exit(3)


if __name__ == "__main__":
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{sys.argv[1]}")
        print(read_ctx(browser.contexts[0]))

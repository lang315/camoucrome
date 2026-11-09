#!/usr/bin/env python3
"""Live recon through chrome://observer: names and matches out, never a value.

Starts a chrome.exe (no identity config, the launcher's flags) on the profile dir the caller gives
(--profile, used as is: a fresh empty dir is logged out, a warm copy made by
observe-auto.ps1 -KeepWarm is logged in; this script never copies or reads a profile),
opens https://www.facebook.com/ and chrome://observer, presses Record on the facebook tab,
with --reload then reloads that tab (on -7 the reloaded document is not recorded),
waits --seconds, reads pre#raw and writes {"status", "tables": names_only(..)} to --out.
The only inputs are the Record click on chrome://observer and, with --reload, that one reload.

Driving: no Playwright; the pages are read over a raw CDP client that
sends Runtime.evaluate and, with --reload, one Page.reload (never Runtime.enable or Page.enable).
Run it through scripts/windows/run-interactive.ps1 (session 1), detached.
Exit: 0 MEASURED, 3 UNMEASURED.
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FB = "https://www.facebook.com/"


def names_only(tables):
    """Field, endpoint and surface names, value classes and counts; no sample, truth, query string or value."""
    sends = [{"endpoint": r["endpoint"].split("?")[0], "topic": r["topic"],
              "fields": [{"path": f["path"], "classes": f["classes"],
                          "strong": sorted({h["surface"] for h in f["strong"]}),
                          "weak": sorted({h["surface"] for h in f["weak"]})} for f in r["fields"]]}
             for r in tables.get("sends", [])]
    reads = [{"member": r["member"], "count": r["count"]} for r in tables.get("reads", [])]
    return {"sends": sends, "reads": reads, "lost": tables.get("status", {}).get("lost")}


class _Tabs:
    """The two members Observer needs from a browser: open(url) and close_tab(id)."""

    def __init__(self, port, cdp_cls):
        self.base, self.cdp_cls = f"http://127.0.0.1:{port}", cdp_cls

    def open(self, url):
        req = urllib.request.Request(f"{self.base}/json/new?{urllib.parse.quote(url, safe=':/?=&')}", method="PUT")
        info = json.load(urllib.request.urlopen(req, timeout=10))
        return info["id"], self.cdp_cls(info["webSocketDebuggerUrl"])

    def close_tab(self, tid):
        urllib.request.urlopen(f"{self.base}/json/close/{tid}", timeout=10).read()


def _measure(a):
    """(raw tables or None, reason or None)."""
    import gpu_gate
    import verify_observer_page as vop

    port = vop.free_port()
    tables, why = None, None
    # chrome.exe directly, as recon.ps1 arm 2 starts the login: patchright's auto-attach sends
    # Network.setCacheDisabled into the session facebook's reload closes, and its driver dies.
    # These are the flags the camoucrome launcher adds with no config; no CAMOU_CONFIG is set.
    proc = subprocess.Popen([a.exe, f"--user-data-dir={a.profile}", "--no-first-run", "--no-default-browser-check",
                             f"--remote-debugging-port={port}", "about:blank"])
    try:
        vop.until(lambda: _json(port, "version"), 30, "DevTools port never answered")
        tabs = _Tabs(port, vop.Cdp)
        _, fb_cdp = tabs.open(FB)
        obs = vop.Observer(tabs)
        obs.pick("facebook.com")
        obs.record()
        if a.reload:  # 2026-11-06: the reloaded document is not recorded (0 reads, 0 sends on -7)
            fb_cdp.call("Page.reload", {})
        fb_cdp.close()
        time.sleep(a.seconds)
        obs.wait_refreshes(1)
        tables = obs.raw()
        crashes = gpu_gate.read_port(port)
        if tables is None:
            why = "pre#raw empty: " + obs.status()
        elif crashes != 0:
            why = f"GPU crash count {crashes}"
    finally:
        try:
            vop.Cdp(_json(port, "version")["webSocketDebuggerUrl"]).call("Browser.close")
            proc.wait(30)
        except Exception:  # noqa: BLE001 - a browser that will not close is killed, never left running
            proc.kill()
    return tables, why


def _json(port, what):
    try:
        return json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/{what}", timeout=5))
    except OSError:
        return None


def run(a):
    try:
        tables, why = _measure(a)
    except Exception as e:  # noqa: BLE001 - a detached run must always leave --out
        tables, why = None, f"{type(e).__name__}: {e}"
    status = "MEASURED" if why is None else "UNMEASURED"
    out = {"status": status, "tables": names_only(tables) if tables and why is None else {}}
    if why:
        out["why"] = why
    pathlib.Path(a.out).write_text(json.dumps(out), encoding="utf-8")
    print(status, why or "", flush=True)
    return 0 if why is None else 3


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--exe", required=True, help="chrome.exe of the build under test")
    ap.add_argument("--profile", required=True, help="user-data-dir, used as is")
    ap.add_argument("--out", required=True, help="the names-only JSON file")
    ap.add_argument("--seconds", type=int, default=60)
    ap.add_argument("--reload", action="store_true", help="reload the facebook tab after Record")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())

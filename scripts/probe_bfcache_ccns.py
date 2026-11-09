"""Finch gap B3: is BackForwardCacheCCNSIgnoreUnchangedCookies observable from a page?

Stock 156.0.8078.80 has the feature on in 3/3 seeded profiles (measurements/2026-11-07-finch-feature-gap.md, "maybe"
table). With it, a `Cache-Control: no-store` page stays back/forward-cache eligible while no cookie changed;
`pageshow.persisted` is the page-visible result. One launch per browser (a seeded stock profile is good for 4 killed
launches), all arms in that launch, on a loopback page A -> same-origin page B -> history.back().

Arms (each on its own path, so no arm sees another's cookie or cache entry):
  0 cacheable      plain page, no no-store. POSITIVE CONTROL: must be persisted=true, else bfcache itself does not
                   work in this launch and the no-store arms measured nothing (UNMEASURED, exit 2).
  1 nostore-same   A is no-store, B changes no cookie. The feature's case.
  1b nostore-same  the same again (repeat, to see a flaky answer).
  2 nostore-cookie A is no-store, B sets a cookie. Expected persisted=false in both browsers: the control that proves
                   the probe can see a difference between "kept" and "not kept".

Per arm it also records Page.backForwardCacheNotUsed (CDP, experimental) reasons.
The same launch checks 'joinAdInterestGroup' in navigator: present means a stock profile without its variations seed
(compiled defaults), so the arm is UNMEASURED too.

Run: CAMOU_SHELL=chrome CAMOU_EXE=<chrome.exe> [CAMOU_FINCH_PROFILE=<seeded stock profile>] python probe_bfcache_ccns.py
Prints one line per arm and `RESULT <json>`; exit 0 measured, 2 UNMEASURED."""
import http.server
import json
import os
import sys
import threading
import time
import urllib.parse

import lib_shell

PROFILE = os.environ.get("CAMOU_FINCH_PROFILE") or None
ARMS = [("0", "cacheable", "cacheable"), ("1", "nostore-same", "nostore"), ("1b", "nostore-same", "nostore"),
        ("2", "nostore-cookie", "nostore")]


def page_a(arm):
    return ("<!doctype html><title>A</title><script>"
            f"addEventListener('pageshow', e => navigator.sendBeacon('/log?arm={arm}&persisted=' + e.persisted"
            "));</script>").encode()


def serve():
    log = []  # (arm, persisted) from pageshow beacons
    hits = []  # (arm, 'A'|'B') document requests

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            parts = u.path.split("/")
            if len(parts) != 3:  # /favicon.ico
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            arm, kind = parts[1], parts[2]
            body = page_a(arm) if kind == "A" else b"<!doctype html><title>B</title>"
            hits.append((arm, kind))
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            if self.server.modes.get(arm) == "nostore":
                self.send_header("Cache-Control", "no-store")
            if kind == "A":
                self.send_header("Set-Cookie", f"k{arm}=init; Path=/")
            elif self.server.modes.get(arm) == "nostore" and arm == "2":
                self.send_header("Set-Cookie", f"k{arm}=changed; Path=/")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            log.append((q["arm"][0], q["persisted"][0]))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.modes = {a: m for a, _, m in ARMS}
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}", log, hits, server


def wait_for(cond, seconds=6):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def run_arms(proc, base, log, hits):
    from playwright.sync_api import sync_playwright

    out = {}
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{proc.cdp_port}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        cdp = context.new_cdp_session(page)
        not_used = []
        cdp.on("Page.backForwardCacheNotUsed", lambda ev: not_used.append(
            [(r.get("type"), r.get("reason")) for r in ev.get("notRestoredExplanations", [])]))
        cdp.send("Page.enable")
        page.goto(base + "/seedcheck/A", wait_until="load")
        out["unseeded_marker"] = page.evaluate("'joinAdInterestGroup' in navigator")
        for arm, _label, _mode in ARMS:
            n_log = len(log)
            n_not_used = len(not_used)
            page.goto(f"{base}/{arm}/A", wait_until="load")
            wait_for(lambda: len(log) > n_log)  # the first pageshow (persisted=false)
            page.goto(f"{base}/{arm}/B", wait_until="load")
            n_after_visit = len(log)
            page.evaluate("history.back()")
            got = wait_for(lambda: len(log) > n_after_visit)
            time.sleep(0.3)
            back = [pers for a, pers in log[n_after_visit:] if a == arm]
            out[arm] = {
                "persisted": back[0] if back else None,
                "pageshow_seen": got,
                "doc_requests": [k for a, k in hits if a == arm],
                "not_used": not_used[n_not_used:],
            }
    return out


def main():
    base, log, hits, server = serve()
    proc = None
    try:
        proc = lib_shell.launch("{}", shell=lib_shell.CHROME, extra_flags=lib_shell.CHROME_FLAGS, user_data_dir=PROFILE)
        res = run_arms(proc, base, log, hits)
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)
        server.shutdown()
        server.server_close()
    for arm, label, _ in ARMS:
        print(f"arm {arm} {label}: {res[arm]}")
    print("RESULT " + json.dumps(res))
    reasons = []
    if res["unseeded_marker"]:
        reasons.append("joinAdInterestGroup is on Navigator: no variations seed, not a stock result")
    if res["0"]["persisted"] != "true":
        reasons.append(f"positive control arm 0 persisted={res['0']['persisted']!r}: bfcache does not work here")
    if res["2"]["persisted"] != "false":
        reasons.append(f"negative control arm 2 persisted={res['2']['persisted']!r}: the probe cannot see a difference")
    for a in ("0", "1", "1b", "2"):
        if res[a]["persisted"] is None:
            reasons.append(f"arm {a}: no pageshow after history.back()")
    if reasons:
        print("UNMEASURED: " + "; ".join(reasons))
        return 2
    print(f"MEASURED nostore-same persisted: {res['1']['persisted']}, {res['1b']['persisted']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

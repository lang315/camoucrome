import http.server, json, os, sys, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell

PROBE = r"""(() => ({outerWidth:outerWidth, outerHeight:outerHeight,
  screenX:screenX, screenY:screenY, screenLeft:screenLeft, screenTop:screenTop,
  innerWidth:innerWidth}))()"""

def run(config):
    v,e = lib_shell.session(config, [PROBE], navigate_to="about:blank")
    if e: raise e
    return v[0]

def cfg(d): return json.dumps(d)

# Popup/iframe geometry (plan 2026-11-21-popup-geometry). Runs in the main page: opens a popup with explicit features,
# a no-feature window.open and an iframe, and reads each window's own outer/inner/screen values, before and after
# resizeTo/moveTo. about:blank is same-origin with its opener, so the handle is readable.
POPUP = r"""(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const read = w => ({ow:w.outerWidth, oh:w.outerHeight, iw:w.innerWidth, ih:w.innerHeight,
                      sx:w.screenX, sy:w.screenY,
                      mb:w.menubar.visible, tb:w.toolbar.visible});
  const out = {top: read(window)};
  const p = window.open('about:blank', '', 'popup=yes,width=400,height=300,left=50,top=60');
  await sleep(1000);
  out.popup = p ? read(p) : null;
  if (p) { p.resizeTo(500, 400); p.moveTo(70, 90); await sleep(1000); out.popup_after = read(p); p.close(); }
  const t = window.open('about:blank');
  await sleep(1000);
  out.tab = t ? read(t) : null;
  if (t) t.close();
  const f = document.createElement('iframe'); document.body.appendChild(f);
  out.iframe = read(f.contentWindow);
  return out;
})()"""

def popup_run(config):
    v,e = lib_shell.session(config, [POPUP], navigate_to="about:blank", extra_flags=lib_shell.SHELL_FLAGS + ["--disable-popup-blocking"])
    if e: raise e
    return v[0]

# Popups that leave the opener's renderer process (noopener, cross-site, a cross-site iframe in a popup) cannot be
# read through a window handle. Each target page reads its own geometry and POSTs it to this server, which also serves
# the pages on two hosts: 127.0.0.1 and localhost are different sites (the same host on another port is same-site).
GEO_JS = """
const g = () => ({ow:outerWidth, oh:outerHeight, iw:innerWidth, ih:innerHeight, sx:screenX, sy:screenY,
  mb:menubar.visible, tb:toolbar.visible});
const label = new URLSearchParams(location.search).get('label');
const send = () => navigator.sendBeacon('http://127.0.0.1:__P__/report', JSON.stringify({label, geo:g()}));
setTimeout(send, 400); setTimeout(send, 1500);
"""
PAGES = {
    "/main": "<html><body>main</body></html>",
    "/geo.html": "<html><body>geo<script>" + GEO_JS + "</script></body></html>",
    "/frame.html": "<html><body>frame<script>" + GEO_JS + "</script>"
                   "<iframe src='http://localhost:__P__/geo.html?label=xframe-child'></iframe></body></html>",
}
SITES = r"""(async () => {
  const P = location.port, F = 'popup=yes,width=400,height=300,left=50,top=60';
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  window.open('/geo.html?label=same', '', F);
  window.open('/geo.html?label=noopener', '', F + ',noopener');
  window.open('http://localhost:' + P + '/geo.html?label=xsite', '', F);
  window.open('/frame.html?label=xframe', '', F);
  await sleep(4000);
  return 1;
})()"""
SITE_LABELS = ("same", "noopener", "xsite", "xframe", "xframe-child")

def site_run(config):
    reports = {}
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            path = self.path.split("?")[0]
            body = PAGES.get(path)
            if body is None:
                self.send_response(404); self.end_headers(); return
            data = body.replace("__P__", str(self.server.server_port)).encode()
            self.send_response(200); self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                m = json.loads(raw); reports[m["label"]] = m["geo"]
            except Exception: pass
            self.send_response(204); self.end_headers()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        v, e = lib_shell.session(config, [SITES], navigate_to=f"http://127.0.0.1:{srv.server_port}/main",
                                 extra_flags=lib_shell.SHELL_FLAGS + ["--disable-popup-blocking"])
        if e: raise e
    finally:
        srv.shutdown()
    return reports

# A chrome frame of a real popup is a few dozen px; the leak makes it 1000+. The bound makes the row discriminate.
def chrome_ok(w): return 0 <= w["ow"]-w["iw"] <= 200 and 0 <= w["oh"]-w["ih"] <= 300

def popup_rows(r, ctl, label):
    """r = fork with window.* config, ctl = fork without config (the control). The popup must read what the control's
    popup reads (its own real geometry), never the main window's claimed one."""
    rows = {}
    for k in ("popup", "popup_after"):  # tab: headless opens it as its own window; judged headed only (INFO below)
        w, c = r.get(k), ctl.get(k)
        ok = w is not None and c is not None
        rows[f"{label}-{k}-outer"] = ok and (w["ow"], w["oh"]) == (c["ow"], c["oh"])
        rows[f"{label}-{k}-screen"] = ok and (w["sx"], w["sy"]) == (c["sx"], c["sy"])
        rows[f"{label}-{k}-coherent"] = ok and chrome_ok(w)
        # BarProp must stay exactly as stock in every process: the popup bit is separate from the window features
        rows[f"{label}-{k}-bars"] = ok and (w["mb"], w["tb"]) == (c["mb"], c["tb"])
        rows[f"{label}-{k}-chrome"] = ok and (w["ow"]-w["iw"], w["oh"]-w["ih"]) == (c["ow"]-c["iw"], c["oh"]-c["ih"])
    return rows

def site_rows(r, ctl):
    rows = {}
    for k in SITE_LABELS:
        w, c = r.get(k), ctl.get(k)
        ok = w is not None and c is not None
        rows[f"S-{k}-outer"] = ok and (w["ow"], w["oh"]) == (c["ow"], c["oh"])
        rows[f"S-{k}-screen"] = ok and (w["sx"], w["sy"]) == (c["sx"], c["sy"])
        rows[f"S-{k}-bars"] = ok and (w["mb"], w["tb"]) == (c["mb"], c["tb"])
        if k in ("same", "noopener", "xsite"):  # the popup windows themselves; xframe-child is an iframe
            rows[f"S-{k}-coherent"] = ok and chrome_ok(w)
    return rows

def unmeasured(ctl, sites_ctl):
    """The control must itself be a measured popup: iw 400 (500 after resizeTo) and a non-empty outer. A 0x0 or
    missing control popup would make every equality row pass against nothing."""
    bad = []
    def need(name, cond):
        if not cond: bad.append(name)
    p, pa = ctl.get("popup"), ctl.get("popup_after")
    need("control popup iw==400", bool(p) and p["iw"] == 400)
    need("control popup_after iw~500", bool(pa) and abs(pa["iw"] - 500) <= 20)
    for k in SITE_LABELS:
        s = sites_ctl.get(k)
        need(f"control site {k} measured", bool(s) and s["ow"] > 0 and s["oh"] > 0)
    for k in ("same", "noopener", "xsite"):
        s = sites_ctl.get(k)
        need(f"control site {k} iw==400", bool(s) and s["iw"] == 400)
    return bad

def main():
    r = {}
    a = run(cfg({"window.outerWidth":1440}));   r["W1"] = a["outerWidth"]==1440
    b = run(cfg({"window.outerHeight":900}));   r["W2"] = b["outerHeight"]==900
    c = run(cfg({"window.screenX":120,"window.screenY":80}))
    r["W3"] = c["screenX"]==120
    r["W4"] = c["screenY"]==80
    r["W5"] = c["screenLeft"]==120 and c["screenTop"]==80
    s = run(cfg({}))
    chrome = os.environ.get("CAMOU_SHELL") == "chrome"
    if not chrome:  # content_shell's fixed 812x680 / 800 window; chrome's headless window differs
        r["W6"] = (s["outerWidth"]==812 and s["outerHeight"]==680
                   and s["screenX"]==0 and s["screenY"]==0)
        r["W7"] = a["innerWidth"]==800
    if not chrome:  # content_shell's browser process crashes on window.open under headless ozone (measured 2026-11-21)
        return finish(r, 7)
    CFG = {"window.outerWidth":1440,"window.outerHeight":900,"window.screenX":120,"window.screenY":80}
    ctl, got = popup_run(cfg({})), popup_run(cfg(CFG))
    sctl, sgot = site_run(cfg({})), site_run(cfg(CFG))
    for name, d in (("control", ctl), ("config", got), ("control-site", sctl), ("config-site", sgot)):
        for k, w in d.items(): print(f"  {name:12} {k:12} {w}")
    bad = unmeasured(ctl, sctl)
    if bad:
        for b in bad: print(f"UNMEASURED: {b}")
        print("UNMEASURED: the control is not a measured popup; no row can be PASS or FAIL")
        sys.exit(3)
    r["P0-top-claimed"] = got["top"]["ow"]==1440 and got["top"]["oh"]==900
    r.update(popup_rows(got, ctl, "P"))
    r.update(site_rows(sgot, sctl))
    # INFO, not counted: headless opens a no-feature window.open as its own window, and stock's iframe reads
    # the top's inner size (unexplained); both are judged on headed chrome on the host.
    for k in ("tab", "iframe"): print(f"INFO {k}: control {ctl[k]} config {got[k]}")
    # 5 W + P0 + 2 windows x 5 + 5 site labels x 3 + 3 site popups x coherent; literals, not len(r)
    finish(r, 5 + 1 + 10 + 15 + 3)

def finish(r, expected):
    for k in r: print(f"{k}: {'PASS' if r[k] else 'FAIL'}")
    n=sum(r.values()); print(f"{n}/{expected} " + ("ALL_PASS" if n==expected and len(r)==expected else "FAIL"))
    sys.exit(0 if n==expected and len(r)==expected else 1)

if __name__=="__main__": main()

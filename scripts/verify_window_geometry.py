import json, os, sys
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
                      sx:w.screenX, sy:w.screenY});
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

def popup_rows(r, ctl, label):
    """r = fork with window.* config, ctl = fork without config (the control). The popup must read what the control's
    popup reads (its own real geometry), never the main window's claimed one, and must stay coherent."""
    rows = {}
    for k in ("popup", "popup_after"):  # tab: headless opens it as its own window; judged headed only (INFO below)
        w, c = r.get(k), ctl.get(k)
        ok = w is not None and c is not None
        rows[f"{label}-{k}-outer"] = ok and (w["ow"], w["oh"]) == (c["ow"], c["oh"])
        rows[f"{label}-{k}-screen"] = ok and (w["sx"], w["sy"]) == (c["sx"], c["sy"])
        rows[f"{label}-{k}-coherent"] = ok and w["ow"] >= w["iw"] and w["oh"] >= w["ih"]
        rows[f"{label}-{k}-chrome"] = ok and (w["ow"]-w["iw"], w["oh"]-w["ih"]) == (c["ow"]-c["iw"], c["oh"]-c["ih"])
    return rows

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
    for name, d in (("control", ctl), ("config", got)):
        for k, w in d.items(): print(f"  {name:8} {k:12} {w}")
    r["P0-top-claimed"] = got["top"]["ow"]==1440 and got["top"]["oh"]==900
    r.update(popup_rows(got, ctl, "P"))
    # INFO, not counted: headless opens a no-feature window.open as its own window, and stock's iframe reads
    # the top's inner size (unexplained); both are judged on headed chrome on the host.
    for k in ("tab", "iframe"): print(f"INFO {k}: control {ctl[k]} config {got[k]}")
    finish(r, 14)  # 5 W + P0 + 2 windows x 4; literals, not len(r)

def finish(r, expected):
    for k in r: print(f"{k}: {'PASS' if r[k] else 'FAIL'}")
    n=sum(r.values()); print(f"{n}/{expected} " + ("ALL_PASS" if n==expected and len(r)==expected else "FAIL"))
    sys.exit(0 if n==expected and len(r)==expected else 1)

if __name__=="__main__": main()

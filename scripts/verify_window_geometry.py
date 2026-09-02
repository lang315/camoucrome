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

def main():
    r = {}
    a = run(cfg({"window.outerWidth":1440}));   r["W1"] = a["outerWidth"]==1440
    b = run(cfg({"window.outerHeight":900}));   r["W2"] = b["outerHeight"]==900
    c = run(cfg({"window.screenX":120,"window.screenY":80}))
    r["W3"] = c["screenX"]==120
    r["W4"] = c["screenY"]==80
    r["W5"] = c["screenLeft"]==120 and c["screenTop"]==80
    s = run(cfg({}))
    r["W6"] = (s["outerWidth"]==812 and s["outerHeight"]==680
               and s["screenX"]==0 and s["screenY"]==0)
    r["W7"] = a["innerWidth"]==800
    EXPECTED=7
    for k in ("W1","W2","W3","W4","W5","W6","W7"): print(f"{k}: {'PASS' if r[k] else 'FAIL'}")
    n=sum(r.values()); print(f"{n}/{EXPECTED} " + ("ALL_PASS" if n==EXPECTED else "FAIL"))
    sys.exit(0 if n==EXPECTED else 1)

if __name__=="__main__": main()

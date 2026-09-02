import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell, echo_server

GET = r"""(async () => {
  return await new Promise((res) => {
    navigator.geolocation.getCurrentPosition(
      (p)=>res({ok:true, lat:p.coords.latitude, lon:p.coords.longitude, acc:p.coords.accuracy}),
      (e)=>res({ok:false, code:e.code}), {timeout:4000});
    setTimeout(()=>res({ok:false, timeout:true}), 5000);
  });
})()"""

WATCH = r"""(async () => {
  return await new Promise((res) => {
    const id = navigator.geolocation.watchPosition(
      (p)=>{ navigator.geolocation.clearWatch(id); res({ok:true, lat:p.coords.latitude}); },
      (e)=>res({ok:false, code:e.code}), {timeout:4000});
    setTimeout(()=>res({ok:false, timeout:true}), 5000);
  });
})()"""

# G5: register watchPosition WITHOUT clearing it, count how many times the
# success callback fires over ~1200ms. A stationary config position must
# fire once and then stay quiet (no busy-loop re-synthesis on the
# OnPositionUpdated -> UpdateGeolocationState re-arm).
STANDING_WATCH = r"""(async () => {
  return await new Promise((res) => {
    let count = 0;
    let lastLat = null;
    navigator.geolocation.watchPosition(
      (p)=>{ count++; lastLat = p.coords.latitude; },
      (e)=>{ /* ignore errors, just keep counting successes */ },
      {timeout:4000});
    setTimeout(()=>res({count, lastLat}), 1200);
  });
})()"""

def run(config, expr):
    url, _, stop = echo_server.start([])
    try:
        v, e = lib_shell.session(config, [expr], navigate_to=url)
        if e: raise e
        return v[0]
    finally:
        stop()

def cfg(d): return json.dumps(d)

def main():
    r = {}
    a = run(cfg({"geolocation:latitude":48.8566,"geolocation:longitude":2.3522,"geolocation:accuracy":25}), GET)
    r["G1"] = a.get("ok") and a["lat"]==48.8566 and a["lon"]==2.3522 and a["acc"]==25
    b = run(cfg({}), GET)
    r["G2"] = (not b.get("ok")) and b.get("code")==3
    c = run(cfg({"geolocation:latitude":10.0,"geolocation:longitude":20.0}), GET)
    r["G3"] = c.get("ok") and c["acc"]==100
    d = run(cfg({"geolocation:latitude":48.8566,"geolocation:longitude":2.3522,"geolocation:accuracy":25}), WATCH)
    r["G4"] = d.get("ok") and d["lat"]==48.8566
    e5 = run(cfg({"geolocation:latitude":48.8566,"geolocation:longitude":2.3522,"geolocation:accuracy":25}), STANDING_WATCH)
    r["G5"] = e5.get("lastLat")==48.8566 and 1 <= e5.get("count", 0) <= 3
    EXPECTED=5
    for k in ("G1","G2","G3","G4","G5"): print(f"{k}: {'PASS' if r[k] else 'FAIL'}")
    if "count" in e5:
        print(f"  (G5 detail: count={e5.get('count')}, lastLat={e5.get('lastLat')})")
    n=sum(r.values()); print(f"{n}/{EXPECTED} " + ("ALL_PASS" if n==EXPECTED else "FAIL"))
    sys.exit(0 if n==EXPECTED else 1)

if __name__=="__main__": main()

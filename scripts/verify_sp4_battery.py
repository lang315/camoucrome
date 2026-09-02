import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell, echo_server

PROBE = r"""(async () => {
  const b = await navigator.getBattery();
  return { charging:b.charging, level:b.level, chargingTime:b.chargingTime,
           dischargingTime: (b.dischargingTime===Infinity ? "Infinity" : b.dischargingTime) };
})()"""

def run(config):
    url,_,stop = echo_server.start([])
    try:
        v,e = lib_shell.session(config, [PROBE], navigate_to=url)
        if e: raise e
        return v[0]
    finally:
        stop()

def cfg(d): return json.dumps(d)

def main():
    r = {}
    r["B1"] = run(cfg({"battery:charging":False})).get("charging") is False
    r["B2"] = run(cfg({"battery:level":0.42})).get("level") == 0.42
    r["B3"] = run(cfg({"battery:chargingTime":1800})).get("chargingTime") == 1800
    r["B4"] = run(cfg({"battery:dischargingTime":9000})).get("dischargingTime") == 9000
    s = run(cfg({}))
    r["B5"] = (s.get("charging") is True and s.get("level") == 1
               and s.get("chargingTime") == 0 and s.get("dischargingTime") == "Infinity")
    EXPECTED=5
    for k in ("B1","B2","B3","B4","B5"): print(f"{k}: {'PASS' if r[k] else 'FAIL'}")
    n=sum(r.values()); print(f"{n}/{EXPECTED} " + ("ALL_PASS" if n==EXPECTED else "FAIL"))
    sys.exit(0 if n==EXPECTED else 1)

if __name__=="__main__": main()

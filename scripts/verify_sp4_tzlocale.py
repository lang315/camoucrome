import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell

MAIN = r"""(() => ({
  tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
  offset: new Date().getTimezoneOffset(),
  locale: Intl.DateTimeFormat().resolvedOptions().locale,
  num: new Intl.NumberFormat().format(1234567.89),
}))()"""

WORKER = r"""(async () => {
  try {
    const src = `postMessage({tz: Intl.DateTimeFormat().resolvedOptions().timeZone, locale: Intl.DateTimeFormat().resolvedOptions().locale});`;
    const w = new Worker(URL.createObjectURL(new Blob([src], {type:'application/javascript'})));
    return await new Promise((res) => { w.onmessage = (e)=>res(e.data); setTimeout(()=>res({error:'timeout'}),3000); });
  } catch(e) { return {error:String(e)}; }
})()"""

BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sp4_tzlocale_baseline.json")

def run(config):
    vals, err = lib_shell.session(config, [MAIN, WORKER], navigate_to="about:blank")
    if err: raise err
    return {"main": vals[0], "worker": vals[1]}

def cfg(d): return json.dumps(d)

def main():
    if "--capture-baseline" in sys.argv:
        b = run(None)
        with open(BASELINE,"w") as f: json.dump(b,f)
        print("baseline:", json.dumps(b)); return
    r = {}
    a = run(cfg({"timezone:id":"America/New_York"}))
    r["T1"] = a["main"]["tz"]=="America/New_York" and a["main"]["offset"] in (240,300)
    r["T2"] = a["worker"].get("tz")=="America/New_York"
    b = run(cfg({"locale:tag":"fr-FR"}))
    r["T3"] = b["main"]["locale"]=="fr-FR" and b["main"]["num"]!="1,234,567.89"
    r["T4"] = b["worker"].get("locale")=="fr-FR"
    c = run(cfg({"navigator.language":"fr-FR"}))
    r["T5"] = c["main"]["locale"]=="fr-FR"
    d = run(cfg({}))
    with open(BASELINE) as f: base=json.load(f)
    r["T6"] = d["main"]["tz"]==base["main"]["tz"] and d["main"]["locale"]==base["main"]["locale"]
    EXPECTED=6
    for k in ("T1","T2","T3","T4","T5","T6"): print(f"{k}: {'PASS' if r[k] else 'FAIL'}")
    n=sum(r.values()); print(f"{n}/{EXPECTED} " + ("ALL_PASS" if n==EXPECTED else "FAIL"))
    sys.exit(0 if n==EXPECTED else 1)

if __name__=="__main__": main()

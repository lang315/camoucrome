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
        print("baseline captured (not printed: host values)"); return
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
    # Fail closed (2026-11-17): a present-but-invalid key never shows the host value.
    e = run(cfg({"timezone:id":"Not/AZone"}))
    r["T7"] = e["main"]["tz"]=="UTC" and e["main"]["offset"]==0
    r["T8"] = e["worker"].get("tz")=="UTC"
    f2 = run(cfg({"locale:tag":"xx-INVALID!!"}))
    r["T9"] = f2["main"]["locale"]=="en-US" and f2["main"]["num"]=="1,234,567.89"
    r["T10"] = f2["worker"].get("locale")=="en-US"
    # Candidate order: a rejected locale:tag falls to navigator.language, not en-US.
    g = run(cfg({"locale:tag":"xx-INVALID!!","navigator.language":"de-DE"}))
    r["T11"] = g["main"]["locale"]=="de-DE"
    r["T12"] = g["worker"].get("locale")=="de-DE"
    # T7-T12 measure nothing when the process already runs as UTC / en-US. Run with e.g.
    # TZ=Etc/GMT-5 LANGUAGE=de (and capture the baseline under the same env).
    if base["main"]["tz"]=="UTC" or base["main"]["locale"]=="en-US":
        print("UNMEASURED: baseline is UTC or en-US, so T7-T12 cannot go RED; set TZ and LANGUAGE to other values")
        sys.exit(2)
    EXPECTED=12
    for k in ("T1","T2","T3","T4","T5","T6","T7","T8","T9","T10","T11","T12"): print(f"{k}: {'PASS' if r[k] else 'FAIL'}")
    n=sum(r.values()); print(f"{n}/{EXPECTED} " + ("ALL_PASS" if n==EXPECTED else "FAIL"))
    sys.exit(0 if n==EXPECTED else 1)

if __name__=="__main__": main()

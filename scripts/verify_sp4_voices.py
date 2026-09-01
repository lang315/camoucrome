import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell

PROBE = r"""(async () => {
  const get = () => speechSynthesis.getVoices().map(v => ({name:v.name, lang:v.lang, voiceURI:v.voiceURI, localService:v.localService, default:v.default}));
  let voices = get();
  if (voices.length === 0) { await new Promise(r => { speechSynthesis.onvoiceschanged = r; setTimeout(r, 1500); }); voices = get(); }
  return { count: voices.length, voices };
})()"""

def run(config):
    v, e = lib_shell.session(config, [PROBE], navigate_to="about:blank")
    if e: raise e
    return v[0]

def cfg(d): return json.dumps(d)

def main():
    r = {}
    a = run(cfg({"voices:list":[{"name":"Camou EN","lang":"en-US","voiceURI":"urn:camou:en","localService":True,"default":True}]}))
    r["V1"] = (a["count"]==1 and a["voices"]==[{"name":"Camou EN","lang":"en-US","voiceURI":"urn:camou:en","localService":True,"default":True}])
    b = run(cfg({}))
    r["V2"] = (b["count"]==0)
    EXPECTED=2
    for k in ("V1","V2"): print(f"{k}: {'PASS' if r[k] else 'FAIL'}")
    n=sum(r.values()); print(f"{n}/{EXPECTED} " + ("ALL_PASS" if n==EXPECTED else "FAIL"))
    sys.exit(0 if n==EXPECTED else 1)

if __name__=="__main__": main()

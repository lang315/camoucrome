import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell

PROBE = r"""(async () => {
  const get = () => speechSynthesis.getVoices().map(v => ({name:v.name, lang:v.lang, voiceURI:v.voiceURI, localService:v.localService, default:v.default}));
  let voices = get();
  if (voices.length === 0) { await new Promise(r => { speechSynthesis.onvoiceschanged = r; setTimeout(r, 1500); }); voices = get(); }
  return { count: voices.length, voices };
})()"""

SPEAK = r"""(async () => {
  speechSynthesis.getVoices();
  await new Promise(r => setTimeout(r, 300));
  const voices = speechSynthesis.getVoices();
  if (!voices.length) return {error:'no injected voice'};
  const u = new SpeechSynthesisUtterance('hello world');
  u.voice = voices[0]; u.rate = 1.0;
  const events = [];
  const t0 = performance.now();
  return await new Promise((res) => {
    u.onstart = () => events.push('start');
    u.onend = () => { events.push('end'); res({events, ms: performance.now()-t0}); };
    u.onerror = (e) => { events.push('error:'+e.error); res({events, ms: performance.now()-t0}); };
    speechSynthesis.speak(u);
    setTimeout(() => res({events, ms: performance.now()-t0, timeout:true}), 4000);
  });
})()"""

def run(config):
    v, e = lib_shell.session(config, [PROBE], navigate_to="about:blank")
    if e: raise e
    return v[0]

def run2(config, expr):
    v, e = lib_shell.session(config, [expr], navigate_to="about:blank")
    if e: raise e
    return v[0]

def cfg(d): return json.dumps(d)

ONE_VOICE = {"voices:list": [{"name": "Camou EN", "lang": "en-US",
                              "voiceURI": "urn:camou:en",
                              "localService": True, "default": True}]}

def main():
    r = {}
    a = run(cfg({"voices:list":[{"name":"Camou EN","lang":"en-US","voiceURI":"urn:camou:en","localService":True,"default":True}]}))
    r["V1"] = (a["count"]==1 and a["voices"]==[{"name":"Camou EN","lang":"en-US","voiceURI":"urn:camou:en","localService":True,"default":True}])
    b = run(cfg({}))
    r["V2"] = (b["count"]==0)

    # V3: fakeCompletion default (absent -> true) -> start then end, no error,
    # and the delay reflects "hello world" (11 chars) / (12.5 cps * 1.0 rate)
    # ~= 0.88s, so ms must exceed 400ms (well below the fake delay, well above
    # an immediate synchronous resolution).
    c = run2(cfg(ONE_VOICE), SPEAK)
    r["V3"] = (c.get("events") == ["start", "end"] and c.get("ms", 0) > 400)

    # V4: fakeCompletion explicitly false -> deterministic error, no end.
    d_cfg = dict(ONE_VOICE)
    d_cfg["voices:fakeCompletion"] = False
    d = run2(cfg(d_cfg), SPEAK)
    events = d.get("events", [])
    r["V4"] = (any(ev.startswith("error:") for ev in events) and "end" not in events)

    EXPECTED=4
    for k in ("V1","V2","V3","V4"): print(f"{k}: {'PASS' if r[k] else 'FAIL'}")
    n=sum(r.values()); print(f"{n}/{EXPECTED} " + ("ALL_PASS" if n==EXPECTED else "FAIL"))
    sys.exit(0 if n==EXPECTED else 1)

if __name__=="__main__": main()

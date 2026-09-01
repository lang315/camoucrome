import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell

FLAGS = ["--ozone-platform=headless",
         "--use-fake-device-for-media-stream",
         "--use-fake-ui-for-media-stream"]

PROBE = r"""(async () => {
  try {
    const pc = new RTCPeerConnection({iceServers: []});
    pc.createDataChannel("x");
    const cands = [];
    pc.onicecandidate = (e) => { if (e.candidate) cands.push(e.candidate.candidate); };
    await pc.setLocalDescription(await pc.createOffer());
    await new Promise((res)=>{ if(pc.iceGatheringState==='complete')return res();
      pc.onicegatheringstatechange=()=>{if(pc.iceGatheringState==='complete')res()}; setTimeout(res,4000); });
    const addrs = cands.map(c => c.split(' ')[4]);
    pc.close();
    return { addrs };
  } catch(e){ return {error:String(e)}; }
})()"""

PRIV = re.compile(r"\b(10\.\d+\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)")
BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sp4_webrtc_baseline.json")

def run(config):
    vals, err = lib_shell.session(config, [PROBE], navigate_to="about:blank", extra_flags=FLAGS)
    if err: raise err
    return vals[0]

def cfg(d): return json.dumps(d)

def main():
    if "--capture-baseline" in sys.argv:
        b = run(cfg({}))
        with open(BASELINE,"w") as f: json.dump(b,f)
        print("baseline:", json.dumps(b)); return
    r = {}
    a = run(cfg({"webrtc:ipHandlingPolicy":"default_public_interface_only"}))
    addrs = a.get("addrs", ["1.2.3.4"])  # sentinel non-empty so a probe error can't vacuously pass
    r["W1"] = "error" not in a and not any(PRIV.search(x or "") for x in addrs)
    b = run(cfg({}))
    with open(BASELINE) as f: base=json.load(f)
    r["W2"] = sorted(b.get("addrs",[])) == sorted(base.get("addrs",[]))
    EXPECTED=2
    for k in ("W1","W2"): print(f"{k}: {'PASS' if r[k] else 'FAIL'}")
    n=sum(r.values()); print(f"{n}/{EXPECTED} " + ("ALL_PASS" if n==EXPECTED else "FAIL"))
    sys.exit(0 if n==EXPECTED else 1)

if __name__=="__main__": main()

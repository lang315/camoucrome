import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell, echo_server

PROBE = r"""(async () => {
  try {
    if (!navigator.mediaDevices) return {error: "mediaDevices undefined"};
    const d = await navigator.mediaDevices.enumerateDevices();
    const byKind = {};
    for (const x of d) byKind[x.kind] = (byKind[x.kind]||0)+1;
    return { count: d.length, byKind, secure: window.isSecureContext,
             fields: d.map(x => ({kind:x.kind, label:x.label, deviceId:x.deviceId, groupId:x.groupId})) };
  } catch(e) { return { error: String(e) }; }
})()"""

def run(config):
    url, _, stop = echo_server.start([])
    try:
        vals, err = lib_shell.session(config, [PROBE], navigate_to=url)
        if err: raise err
        return vals[0]
    finally:
        stop()

def cfg(d): return json.dumps(d)

BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sp4_media_baseline.json")

def main():
    if "--capture-baseline" in sys.argv:
        base = run(None)
        with open(BASELINE, "w") as f: json.dump(base, f)
        print("baseline captured:", json.dumps(base)); return
    results = {}
    m1 = run(cfg({"mediaDevices:enabled": True, "mediaDevices:micros": 2,
                  "mediaDevices:webcams": 3, "mediaDevices:speakers": 4}))
    # Pre-grant, stock lists at most ONE blank entry per kind
    # (content/browser/media/media_devices_util.cc TranslateMediaDeviceInfoArray
    # stops after the first blank one), so counts above 1 collapse to 1.
    results["M1"] = (m1.get("byKind") == {"audioinput":1,"videoinput":1,"audiooutput":1}
                     and m1.get("count") == 3)
    results["M2"] = all(x["label"]=="" and x["deviceId"]=="" and x["groupId"]==""
                        for x in m1.get("fields", [{"label":"x","deviceId":"x","groupId":"x"}]))
    m3 = run(cfg({"mediaDevices:enabled": True}))
    results["M3"] = m3.get("byKind") == {"audioinput":1,"videoinput":1,"audiooutput":1}
    m4 = run(cfg({}))
    with open(BASELINE) as f: base = json.load(f)
    results["M4"] = (m4.get("byKind") == base.get("byKind")
                     and m4.get("secure") is True)
    EXPECTED = 4
    for k in ("M1","M2","M3","M4"):
        print(f"{k}: {'PASS' if results[k] else 'FAIL'}")
    npass = sum(results.values())
    print(f"{npass}/{EXPECTED} " + ("ALL_PASS" if npass==EXPECTED else "FAIL"))
    sys.exit(0 if npass==EXPECTED else 1)

if __name__ == "__main__":
    main()

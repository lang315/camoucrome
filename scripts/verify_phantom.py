import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell, echo_server

# media-ii Slice 2 (phantom-webcam): a configured-but-unbacked device must reject
# getUserMedia with NotReadableError (present, unstartable), not NotFoundError
# (absent) which contradicts the spoofed enumerate. Camera/mic-less box, NO
# --use-fake-device (the real hardware-absent path). P5 uses --use-fake-device as
# a real-device stand-in (success path must not be remapped).
BASE = ["--ozone-platform=headless"]
FAKE = ["--ozone-platform=headless", "--use-fake-device-for-media-stream",
        "--use-fake-ui-for-media-stream"]

def gum_probe(constraints):
    return (r"""(async () => {
      const gum = navigator.mediaDevices.getUserMedia(%s)
        .then(s => { s.getTracks().forEach(t => t.stop()); return 'ok'; })
        .catch(e => e.name || String(e));
      const to = new Promise(r => setTimeout(() => r('TIMEOUT(hang)'), 3000));
      return await Promise.race([gum, to]);
    })()""" % constraints)

def cfg(**kw):
    d = {"mediaDevices:enabled": True, "mediaDevices:seed": 12345}
    d.update(kw)
    return json.dumps(d)

def run(config, constraints, flags):
    url, _, stop = echo_server.start([])
    try:
        vals, err = lib_shell.session(config, [gum_probe(constraints)],
                                      navigate_to=url, extra_flags=flags)
        return f"SESSION_ERR:{err}" if err else vals[0]
    finally:
        stop()

def main():
    r = {}
    # P1 stock, camera-less -> NotFoundError (RED baseline)
    p1 = run(None, "{video:true}", BASE);                          r["P1"] = (p1 == "NotFoundError", p1)
    # P2 spoof webcams=1, camera-less -> NotReadableError
    p2 = run(cfg(**{"mediaDevices:webcams": 1}), "{video:true}", BASE)
    r["P2"] = (p2 == "NotReadableError", p2)
    # P3 spoof webcams=0 (micros=1) -> video still NotFoundError (no video phantom)
    p3 = run(cfg(**{"mediaDevices:webcams": 0, "mediaDevices:micros": 1}), "{video:true}", BASE)
    r["P3"] = (p3 == "NotFoundError", p3)
    # P4 config {} -> stock exact (== P1)
    p4 = run(json.dumps({}), "{video:true}", BASE);                r["P4"] = (p4 == "NotFoundError", p4)
    # P5 real device present (fake-device stand-in) -> succeeds, NOT remapped
    p5 = run(cfg(**{"mediaDevices:webcams": 1}), "{video:true}", FAKE)
    r["P5"] = (p5 == "ok", p5)
    # P6 no-regression: audio on this headless box hits a DIFFERENT path
    # (NotSupportedError -- no audio subsystem, never reaches NO_HARDWARE), so the
    # remap must leave it untouched. (The code's audio gate is correct-if-reached
    # but unexercised here; audio is low-priority per sp4-media §1.5b.)
    p6 = run(cfg(**{"mediaDevices:micros": 1}), "{audio:true}", BASE)
    r["P6"] = (p6 == "NotSupportedError", p6)

    order = ["P1", "P2", "P3", "P4", "P5", "P6"]
    for k in order:
        ok, val = r[k]
        print(f"{k}: {'PASS' if ok else 'FAIL'}  -- got {val!r}")
    n = sum(1 for k in order if r[k][0])
    print(f"{n}/6 " + ("ALL_PASS" if n == 6 else "FAIL"))
    sys.exit(0 if n == 6 else 1)

if __name__ == "__main__": main()

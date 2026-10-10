"""S3b mutant rows: a phantom speaker on a host with no output device.

Run ONLY against the W13 mutant build (raw audiooutput snapshot emptied).
Every real host here has a speaker, so this is the only way to reach the
phantom-output path. The stock arm is the liveness check: on the mutant it
must list no audiooutput at all, or the script exits 2 without counting.

S3-M1: setSinkId(<phantom speaker id>) resolves, as stock setSinkId("")
resolves on a host with no output device.
S3-M2: new AudioContext({sinkId: <phantom id>}) reaches 'running' with that
sinkId and no error event within 3 s. A devicechange cannot be triggered on
WSL, so the NotifyDeviceChange half of the fix is not measured here.
"""

import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell, echo_server

EXPECTED = 2
FLAGS = ["--ozone-platform=headless", "--use-fake-ui-for-media-stream",
         "--autoplay-policy=no-user-gesture-required"]
CONFIG = json.dumps({"mediaDevices:enabled": True, "mediaDevices:seed": 424242,
                     "mediaDevices:micros": 1, "mediaDevices:webcams": 1,
                     "mediaDevices:speakers": 1})
PROBE = r"""(async () => {
  try {
    const real = d => !['', 'default', 'communications'].includes(d.deviceId);
    const ds = await navigator.mediaDevices.enumerateDevices();
    const outs = ds.filter(d => d.kind === 'audiooutput');
    const out = outs.find(real);
    const r = {outs: outs.length, hasOut: !!out};
    if (!out) return r;
    const a = new Audio();
    try { await a.setSinkId(out.deviceId); r.sink = a.sinkId === out.deviceId ? 'ok' : 'mismatch'; }
    catch (e) { r.sink = e.name; }
    let errored = false;
    const ac = new AudioContext({sinkId: out.deviceId});
    ac.onerror = () => { errored = true; };
    const t0 = Date.now();
    while (ac.state !== 'running' && Date.now() - t0 < 3000) await new Promise(f => setTimeout(f, 100));
    await new Promise(f => setTimeout(f, 500));
    r.ac = (ac.state === 'running' && ac.sinkId === out.deviceId && !errored) ? 'ok'
         : `state=${ac.state} sinkMatch=${ac.sinkId === out.deviceId} error=${errored}`;
    await ac.close();
    return r;
  } catch (e) { return {error: String(e)}; }
})()"""


def run(url, config):
    vals, err = lib_shell.session(config, [PROBE], navigate_to=url, extra_flags=FLAGS)
    return {"error": str(err)} if err else vals[0]


def main():
    url, _, stop = echo_server.start([])
    try:
        stock = run(url, None)
        fork = run(url, CONFIG)
    finally:
        stop()
    if not isinstance(stock, dict) or "error" in stock or stock.get("outs") != 0:
        print(f"not the W13 mutant build (stock lists audiooutput): {stock.get('outs') if isinstance(stock, dict) else stock}")
        sys.exit(2)
    ok = isinstance(fork, dict) and "error" not in fork and fork.get("hasOut")
    rows = {"S3-M1": (bool(ok) and fork.get("sink") == "ok", f"sink={fork.get('sink') if ok else fork}"),
            "S3-M2": (bool(ok) and fork.get("ac") == "ok", f"ac={fork.get('ac') if ok else fork}")}
    assert len(rows) == EXPECTED
    for k, (good, note) in rows.items():
        print(f"{k}: {'PASS' if good else 'FAIL'}  -- {note}")
    n = sum(1 for good, _ in rows.values() if good)
    print(f"{n}/{EXPECTED} " + ("ALL_PASS" if n == EXPECTED else "FAIL"))
    sys.exit(0 if n == EXPECTED else 1)


if __name__ == "__main__":
    main()

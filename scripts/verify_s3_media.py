"""S3 verify: enumerateDevices() after a grant, on a host without the claimed devices.

Backlog S3 (specs/2026-10-10-s3-media-device-ids-design.md). With camera and
microphone granted, stock Chrome lists real ids, while the fork listed every
claimed device with id "" because no real input existed. This script never
passes --use-fake-device-for-media-stream: fake devices would make every kind
real and hide the bug. --use-fake-ui-for-media-stream alone grants all three
types to enumerateDevices without a getUserMedia call
(media_devices_permission_checker.cc:154-160, 218-223).

REAL_KINDS is measured, not assumed: the kinds stock content_shell lists
under the grant (WSLg may expose a PulseAudio source and sink). Phantom
expectations apply to the claimed kinds outside REAL_KINDS.
"""

import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell, echo_server

EXPECTED = 8
BASE = ["--ozone-platform=headless"]
GRANT = BASE + ["--use-fake-ui-for-media-stream"]
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SENTINELS = ("default", "communications")
KINDS = ("audioinput", "videoinput", "audiooutput")
CONFIG = json.dumps({"mediaDevices:enabled": True, "mediaDevices:seed": 424242,
                     "mediaDevices:micros": 1, "mediaDevices:webcams": 1,
                     "mediaDevices:speakers": 1,
                     "mediaDevices:cameraLabel": "Camo Cam",
                     "mediaDevices:microphoneLabel": "Camo Mic",
                     "mediaDevices:speakerLabel": "Camo Speaker"})

# Main document, then a same-origin iframe (a second document: its own frame
# salt, so its own groupIds), then getCapabilities() per entry.
PROBE = r"""(async () => {
  try {
    const pick = ds => ds.map(d => ({kind: d.kind, deviceId: d.deviceId,
                                     groupId: d.groupId, label: d.label}));
    const devs = await navigator.mediaDevices.enumerateDevices();
    const f = document.createElement('iframe');
    f.src = location.href;
    await new Promise(r => { f.onload = r; document.body.appendChild(f); });
    const frame = pick(await f.contentWindow.navigator.mediaDevices.enumerateDevices());
    const caps = devs.filter(d => typeof d.getCapabilities === 'function').map(d => {
      const c = d.getCapabilities();
      return {kind: d.kind, deviceId: d.deviceId,
              sampleRate: c.sampleRate || null, channelCount: c.channelCount || null,
              width: c.width || null, height: c.height || null};
    });
    return {secure: window.isSecureContext, main: pick(devs), frame, caps};
  } catch (e) { return {error: String(e)}; }
})()"""


def run(url, config, flags):
    vals, err = lib_shell.session(config, [PROBE], navigate_to=url, extra_flags=flags)
    if err:
        return {"error": str(err)}
    return vals[0]


def bad(r):
    return not isinstance(r, dict) or "error" in r


def kinds(lst):
    return sorted({d["kind"] for d in lst})


def devices(lst):
    """Entries that stand for a device: not the default/communications sentinels."""
    return [d for d in lst if d["deviceId"] not in SENTINELS]


def shape(lst):
    return sorted((d["kind"], d["deviceId"] == "", d["groupId"] == "", d["label"] == "") for d in lst)


def main():
    res = {}
    a_url, _, a_stop = echo_server.start([])
    b_url, _, b_stop = echo_server.start([])
    try:
        stock = run(a_url, None, GRANT)
        unconf = run(a_url, json.dumps({}), GRANT)
        pre = run(a_url, CONFIG, BASE)
        post = run(a_url, CONFIG, GRANT)
        other = run(b_url, CONFIG, GRANT)
    finally:
        a_stop()
        b_stop()

    if bad(stock):
        print(f"stock run failed: {stock}")
        sys.exit(2)
    real_kinds = set(kinds(stock["main"]))
    phantom_kinds = set(KINDS) - real_kinds
    print(f"REAL_KINDS={sorted(real_kinds)} PHANTOM_KINDS={sorted(phantom_kinds)}")
    if not phantom_kinds:
        print("every kind is real on this host: it cannot show S3")
        sys.exit(2)

    # Rows S3-1, 2, 6 and the phantom half of S3-7 look only at PHANTOM kinds: a
    # real kind already has ids on main, so including it would let a row pass
    # without the fix. S3-5 compares the fork with stock on every kind, and the
    # real-input half of S3-7 checks the REAL kinds.
    def ph(lst):
        return [d for d in lst if d["kind"] in phantom_kinds]

    if bad(post):
        for k in ("S3-1", "S3-2", "S3-5", "S3-7"):
            res[k] = (False, f"error {post}")
    else:
        m = post["main"]
        res["S3-1"] = (set(kinds(m)) == set(KINDS) and len(devices(ph(m))) > 0 and
                       all(HEX64.match(d["deviceId"]) for d in devices(ph(m))),
                       f"kinds={kinds(m)} phantom ids={[d['deviceId'][:8] for d in ph(m)]}")
        res["S3-2"] = (len(ph(m)) > 0 and all(HEX64.match(d["groupId"]) for d in ph(m)),
                       f"phantom groups={[d['groupId'][:8] for d in ph(m)]}")
        fr = post["frame"]
        # Stock content_shell has no persistent deviceId salt, so a same-origin
        # iframe gets other deviceIds than its main frame. The fork must do what
        # stock does per kind: persistent per-profile stability is measured on
        # the Windows host (Task 5), not here. groupIds differ per document in
        # the fork, as they do in Chrome.
        def eq_by_kind(lst_a, lst_b):
            return {k: sorted(d["deviceId"] for d in devices(lst_a) if d["kind"] == k) ==
                       sorted(d["deviceId"] for d in devices(lst_b) if d["kind"] == k)
                    for k in KINDS if any(d["kind"] == k for d in devices(lst_a))}
        fork_eq = eq_by_kind(m, fr)
        stock_eq = eq_by_kind(stock["main"], stock["frame"])
        common = set(fork_eq) & set(stock_eq)
        mg = {d["groupId"] for d in devices(m)}
        fg = {d["groupId"] for d in devices(fr)}
        res["S3-5"] = (len(common) > 0 and all(fork_eq[k] == stock_eq[k] for k in common) and
                       mg.isdisjoint(fg) and "" not in mg | fg,
                       f"deviceId equal across documents (fork/stock): "
                       f"{ {k: (fork_eq[k], stock_eq[k]) for k in sorted(common)} }, "
                       f"groups disjoint={mg.isdisjoint(fg)}")
        caps = {d["kind"]: d for d in post["caps"]
                if d["deviceId"] not in SENTINELS and d["kind"] in phantom_kinds}
        real_caps = {d["kind"]: d for d in post["caps"]
                     if d["deviceId"] not in SENTINELS and d["kind"] in real_kinds}
        checks = []
        # The seeded transform must keep the REAL input's capabilities too.
        if "audioinput" in real_kinds:
            mic = real_caps.get("audioinput", {})
            checks.append(bool(mic.get("sampleRate")) and bool(mic.get("channelCount")))
        if "videoinput" in real_kinds:
            cam = real_caps.get("videoinput", {})
            checks.append(bool(cam.get("width")) and bool(cam.get("height")))
        if "audioinput" in phantom_kinds:
            mic = caps.get("audioinput", {})
            checks.append(bool(mic.get("sampleRate")) and bool(mic.get("channelCount")))
        if "videoinput" in phantom_kinds:
            cam = caps.get("videoinput", {})
            checks.append(bool(cam.get("width")) and bool(cam.get("height")))
        res["S3-7"] = (len(checks) > 0 and all(checks),
                       f"input caps phantom={caps} real={real_caps}" if checks else "no phantom input kind on this host: not measurable")

    if bad(pre):
        res["S3-3"] = (False, f"error {pre}")
    else:
        m = pre["main"]
        counts = {k: sum(1 for d in m if d["kind"] == k) for k in KINDS}
        res["S3-3"] = (counts == {k: 1 for k in KINDS} and
                       all(d["deviceId"] == d["groupId"] == d["label"] == "" for d in m),
                       f"guard: counts={counts}")

    if bad(pre) or bad(post):
        res["S3-4"] = (False, "error")
    else:
        res["S3-4"] = (kinds(pre["main"]) == kinds(post["main"]),
                       f"kinds equal across the grant: pre={kinds(pre['main'])} post={kinds(post['main'])}")

    if bad(post) or bad(other):
        res["S3-6"] = (False, "error")
    else:
        ia = {d["deviceId"] for d in devices(post["main"]) if d["kind"] in phantom_kinds}
        ib = {d["deviceId"] for d in devices(other["main"]) if d["kind"] in phantom_kinds}
        res["S3-6"] = (len(ia) > 0 and "" not in ia and ia.isdisjoint(ib),
                       f"origin A {len(ia)} ids, origin B {len(ib)} ids, disjoint={ia.isdisjoint(ib)}")

    if bad(unconf):
        res["S3-8"] = (False, f"error {unconf}")
    else:
        res["S3-8"] = (shape(unconf["main"]) == shape(stock["main"]),
                       f"guard rule 5: {{}}={shape(unconf['main'])} stock={shape(stock['main'])}")

    order = [f"S3-{i}" for i in range(1, EXPECTED + 1)]
    for k in order:
        ok, note = res.get(k, (False, "MISSING"))
        print(f"{k}: {'PASS' if ok else 'FAIL'}  -- {note}")
    n = sum(1 for k in order if res.get(k, (False,))[0])
    print(f"{n}/{EXPECTED} " + ("ALL_PASS" if n == EXPECTED else "FAIL"))
    sys.exit(0 if n == EXPECTED else 1)


if __name__ == "__main__":
    main()

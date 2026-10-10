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

Only the SINK sessions (S3-9..S3-11) pass --use-fake-device-for-media-stream:
they test the round trip of a listed real-device id, which must not depend on
WSLg/RDP audio being present. Every other session stays without it.
"""

import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell, echo_server

EXPECTED = 12
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
NOSEED = json.dumps({k: v for k, v in json.loads(CONFIG).items() if k != "mediaDevices:seed"})
SINKFLAGS = GRANT + ["--use-fake-device-for-media-stream", "--autoplay-policy=no-user-gesture-required"]

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
      return {kind: d.kind, deviceId: d.deviceId, groupId: d.groupId,
              capDeviceId: c.deviceId, capGroupId: c.groupId,
              sampleRate: c.sampleRate || null, channelCount: c.channelCount || null,
              width: c.width || null, height: c.height || null};
    });
    return {secure: window.isSecureContext, main: pick(devs), frame, caps};
  } catch (e) { return {error: String(e)}; }
})()"""

SINK = r"""(async () => {
  try {
    const real = d => !['', 'default', 'communications'].includes(d.deviceId);
    const ds = await navigator.mediaDevices.enumerateDevices();
    const out = ds.find(d => d.kind === 'audiooutput' && real(d));
    const mic = ds.find(d => d.kind === 'audioinput' && real(d));
    const r = {hasOut: !!out, hasMic: !!mic};
    if (out) {
      const a = new Audio();
      try { await a.setSinkId(out.deviceId); r.sink = a.sinkId === out.deviceId ? 'ok' : 'mismatch'; }
      catch (e) { r.sink = e.name; }
      const ac = new AudioContext();
      // AudioContext fills its sink id set from its own enumerate after
      // construction; let that land before setSinkId.
      await navigator.mediaDevices.enumerateDevices();
      await new Promise(f => setTimeout(f, 500));
      try { await ac.setSinkId(out.deviceId); r.acSink = ac.sinkId === out.deviceId ? 'ok' : 'mismatch'; }
      catch (e) { r.acSink = e.name; }
      await ac.close();
    }
    if (mic) {
      try {
        const s = await navigator.mediaDevices.getUserMedia({audio: {deviceId: {exact: mic.deviceId}}});
        const st = s.getAudioTracks()[0].getSettings();
        r.gum = (st.deviceId === mic.deviceId && st.groupId === mic.groupId) ? 'ok' : 'mismatch';
        s.getTracks().forEach(t => t.stop());
      } catch (e) { r.gum = e.name; }
    }
    return r;
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


def by_value(r):
    """(kind, label, which-fields-empty) per entry, plus capability key sets per input entry."""
    lst = sorted((d["kind"], d["label"], d["deviceId"] == "", d["groupId"] == "") for d in r["main"])
    caps = sorted((c["kind"], tuple(k for k in ("sampleRate", "channelCount", "width", "height") if c[k]))
                  for c in r["caps"])
    return lst, caps


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
        noseed = run(a_url, NOSEED, GRANT)
        sink_stock = lib_shell.session(None, [SINK], navigate_to=a_url, extra_flags=SINKFLAGS)
        sink_fork = lib_shell.session(CONFIG, [SINK], navigate_to=a_url, extra_flags=SINKFLAGS)
    finally:
        a_stop()
        b_stop()

    def sink(v):
        vals, err = v
        return {"error": str(err)} if err else vals[0]
    sink_stock, sink_fork = sink(sink_stock), sink(sink_fork)

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
                       f"kinds={kinds(m)} phantom ids n={len(ph(m))} hex64={all(HEX64.match(d['deviceId']) for d in ph(m))}")
        res["S3-2"] = (len(ph(m)) > 0 and all(HEX64.match(d["groupId"]) for d in ph(m)),
                       f"phantom groups n={len(ph(m))} hex64={all(HEX64.match(d['groupId']) for d in ph(m))}")
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
        mg = {d["groupId"] for d in devices(m)}
        fg = {d["groupId"] for d in devices(fr)}
        # Guard row (its RED was never seen): every kind stock lists must be in
        # the fork, every phantom kind must be in BOTH fork documents with a
        # non-empty deviceId, and every fork groupId differs between documents.
        present = lambda lst, k: [d for d in devices(lst) if d["kind"] == k]
        phantoms_ok = all(present(lst, k) and all(d["deviceId"] for d in present(lst, k))
                          for k in phantom_kinds for lst in (m, fr))
        kinds_ok = set(stock_eq) <= set(fork_eq)
        eq_ok = kinds_ok and all(fork_eq[k] == stock_eq[k] for k in stock_eq)
        groups_ok = len(mg) > 0 and mg.isdisjoint(fg) and "" not in mg | fg
        res["S3-5"] = (kinds_ok and eq_ok and phantoms_ok and groups_ok,
                       f"guard: deviceId equal across documents (fork/stock): "
                       f"{ {k: (fork_eq.get(k), stock_eq[k]) for k in sorted(stock_eq)} }, "
                       f"stock kinds in fork={kinds_ok}, phantom kinds in both docs={phantoms_ok}, "
                       f"groups disjoint={groups_ok}")
        inputs = [d for d in post["caps"] if d["deviceId"] not in SENTINELS]
        ids_ok = all(d["capDeviceId"] == d["deviceId"] and d["capGroupId"] == d["groupId"]
                     for d in inputs)
        # Ranges, not truthiness: a camera's width/height start at >= 1 and reach
        # the format maximum; a mic's sampleRate is a positive min <= max range.
        def cam_ok(d):
            w, h = d["width"] or {}, d["height"] or {}
            return (w.get("min", 0) >= 1 and w.get("max", 0) >= 1920 and
                    h.get("min", 0) >= 1 and h.get("max", 0) >= 1080)
        def mic_ok(d):
            s, c = d["sampleRate"] or {}, d["channelCount"] or {}
            return 0 < s.get("min", 0) <= s.get("max", -1) and c.get("max", 0) >= 1
        checks = [ids_ok] if inputs else []
        for d in inputs:
            if d["kind"] == "audioinput":
                checks.append(mic_ok(d))
            if d["kind"] == "videoinput" and d["kind"] in phantom_kinds:
                checks.append(cam_ok(d))
            if d["kind"] == "videoinput" and d["kind"] in real_kinds:
                checks.append(bool(d["width"]) and bool(d["height"]))
        res["S3-7"] = (len(checks) > 1 and all(checks),
                       f"{len(inputs)} input entries, capability ids equal own ids={ids_ok}, "
                       f"range checks={checks[1:]}" if checks else "no input kind on this host: not measurable")

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
        same = by_value(unconf) == by_value(stock)
        res["S3-8"] = (same, f"guard rule 5: config {{}} equals stock by label and capability keys: {same}")

    # S3-9..11: an id the fork lists must work when passed back, as on stock.
    # The stock run is the control: a row is only measurable when stock passes.
    if bad(sink_stock) or bad(sink_fork):
        for k in ("S3-9", "S3-10", "S3-11"):
            res[k] = (False, f"error stock={sink_stock} fork={sink_fork}")
    else:
        for k, key, need in (("S3-9", "sink", "hasOut"), ("S3-10", "gum", "hasMic"),
                             ("S3-11", "acSink", "hasOut")):
            ctl = sink_stock.get(key) == "ok"
            got = sink_fork.get(key)
            res[k] = (bool(sink_fork.get(need) and ctl and got == "ok"),
                      f"{key}: fork={got} stock={sink_stock.get(key)}"
                      + ("" if ctl else " (stock control failed: not measurable)"))
    # S3-12 (M1): enabled without a seed is inactive, so the list equals stock.
    if bad(noseed):
        res["S3-12"] = (False, f"error {noseed}")
    else:
        same = by_value(noseed) == by_value(stock)
        res["S3-12"] = (same, f"enabled, no seed equals stock by label and capability keys: {same}")

    order = [f"S3-{i}" for i in range(1, EXPECTED + 1)]
    for k in order:
        ok, note = res.get(k, (False, "MISSING"))
        print(f"{k}: {'PASS' if ok else 'FAIL'}  -- {note}")
    n = sum(1 for k in order if res.get(k, (False,))[0])
    print(f"{n}/{EXPECTED} " + ("ALL_PASS" if n == EXPECTED else "FAIL"))
    sys.exit(0 if n == EXPECTED else 1)


if __name__ == "__main__":
    main()

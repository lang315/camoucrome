"""media-ii verify: grant-aware id/label coherence (M1-M11).

Slice 1 of media-ii. sp4-media spoofs enumerateDevices() to configured counts
of empty-field devices, but a granted MediaStreamTrack still reports the REAL
device id/group/label -- a value that is NOT among the (empty) enumerated ids
and, on real hardware, is the camera/mic model. This makes the granted track
coherent with the spoofed enumerate:

  - Pre-grant (no getUserMedia): enumerate = the sp4 empty-count spoof.
  - Post-grant: enumerate transforms each REAL device to an origin-salted
    synthetic deviceId/groupId (camoucfg::SyntheticDeviceId) + a configured
    generic per-kind label, keeping the real count; and the track getters
    (getSettings/getCapabilities/label) apply the SAME helper to the SAME real
    id -> coherent by construction.

Grant is the axis. echo_server binds 127.0.0.1 which is a secure context (so
getUserMedia is allowed) but a RANDOM port -- so M6 reuses ONE server url
across two launches to hold origin fixed, and M8 uses TWO servers (two ports =
two origins).

MEASURED FACT (rotation_probe.py / shared_profile_probe.py): the fake-device
video deviceId ROTATES per launch even with a shared --user-data-dir
(content_shell has no persistent media-device salt). Since SyntheticDeviceId
folds real_id, the synthetic video id necessarily rotates per launch too. So:
  - M6 asserts §2's real requirement -- the synthetic id ROTATES like stock
    (a stable id would be the cross-origin supercookie §2 forbids), NOT that
    it is byte-identical across launches (that is impossible here).
  - M7/M8 still pass but are CONFOUNDED: rotation alone makes two launches
    differ. The non-vacuous seed/origin-sensitivity coverage lives in
    additions/camoucfg/device_ids_unittest.cc (Deterministic,
    DifferentSeedsDiffer, DifferentOriginsDiffer).
The evidence the transform actually fired: M11 GREEN => the enabled&&seed!=0
guard was true => both sites call SyntheticDeviceId(seed!=0, non-empty id) =>
the unit tests prove that path hashes => M3 proves both sites agree.
"""

import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell, echo_server

BASE = ["--ozone-platform=headless", "--use-fake-device-for-media-stream"]
GRANT = BASE + ["--use-fake-ui-for-media-stream"]
HEX64 = re.compile(r"^[0-9a-f]{64}$")

SEED, SEED2 = 424242, 999983
LABELS = {"mediaDevices:cameraLabel": "Camo Cam",
          "mediaDevices:microphoneLabel": "Camo Mic",
          "mediaDevices:speakerLabel": "Camo Speaker"}


def spoof(seed, counts=None):
    d = {"mediaDevices:enabled": True, "mediaDevices:seed": seed}
    d.update(LABELS)
    if counts:
        d.update(counts)
    return json.dumps(d)


ENUM = r"""(async () => {
  try {
    const devs = await navigator.mediaDevices.enumerateDevices();
    return {secure: window.isSecureContext,
            enumerate: devs.map(d => ({kind:d.kind, deviceId:d.deviceId,
                                       groupId:d.groupId, label:d.label}))};
  } catch(e) { return {error: String(e)}; }
})()"""

# gUM grant, then read each track's getSettings/getCapabilities/label AND
# re-enumerate -- both surfaces in one shot so coherence is checked in-launch.
GRANT_PROBE = r"""(async () => {
  try {
    const s = await navigator.mediaDevices.getUserMedia({video:true, audio:true});
    const tracks = s.getTracks().map(t => ({
      kind: t.kind,
      settingsDeviceId: t.getSettings().deviceId,
      settingsGroupId: t.getSettings().groupId,
      capsDeviceId: t.getCapabilities().deviceId,
      label: t.label}));
    const devs = await navigator.mediaDevices.enumerateDevices();
    s.getTracks().forEach(t => t.stop());
    // Post-stop: label()/getSettings() must stay masked (a stopped track that
    // reverts to the real device name/id is a fingerprinter's exact pattern).
    const postStop = s.getTracks().map(t => ({
      kind: t.kind, label: t.label,
      settingsDeviceId: t.getSettings().deviceId}));
    return {secure: window.isSecureContext, tracks, postStop,
            enumerate: devs.map(d => ({kind:d.kind, deviceId:d.deviceId,
                                       groupId:d.groupId, label:d.label}))};
  } catch(e) { return {error: String(e)}; }
})()"""


def run(url, config, probe, flags):
    vals, err = lib_shell.session(config, [probe], navigate_to=url,
                                  extra_flags=flags)
    if err:
        return {"error": str(err)}
    return vals[0]


def is_err(r):
    return not isinstance(r, dict) or "error" in r


def by_kind_counts(enum):
    c = {}
    for d in enum:
        c[d["kind"]] = c.get(d["kind"], 0) + 1
    return c


def ids_by_kind(enum):
    m = {}
    for d in enum:
        m.setdefault(d["kind"], set()).add(d["deviceId"])
    return m


ENUMK = {"audio": "audioinput", "video": "videoinput"}


def video_track_id(res):
    for t in res.get("tracks", []):
        if t["kind"] == "video":
            return t["settingsDeviceId"]
    return None


def audio_track_id(res):
    for t in res.get("tracks", []):
        if t["kind"] == "audio":
            return t["settingsDeviceId"]
    return None


def main():
    results = {}   # name -> (bool, note)

    srvA_url, _, srvA_stop = echo_server.start([])
    srvB_url, _, srvB_stop = echo_server.start([])
    try:
        # --- pre-grant arms (BASE flags, no gUM) ---
        m1 = run(srvA_url, spoof(SEED, counts={"mediaDevices:micros": 2,
                                               "mediaDevices:webcams": 2,
                                               "mediaDevices:speakers": 2}),
                 ENUM, BASE)
        stock_pre = run(srvA_url, None, ENUM, BASE)
        empty_pre = run(srvA_url, json.dumps({}), ENUM, BASE)

        # --- post-grant arms (GRANT flags, gUM) ---
        spoofA1 = run(srvA_url, spoof(SEED), GRANT_PROBE, GRANT)
        spoofA2 = run(srvA_url, spoof(SEED), GRANT_PROBE, GRANT)   # same origin+seed
        spoofA_seed2 = run(srvA_url, spoof(SEED2), GRANT_PROBE, GRANT)  # M7
        spoofB1 = run(srvB_url, spoof(SEED), GRANT_PROBE, GRANT)   # M8 (other origin)
        stock1 = run(srvA_url, None, GRANT_PROBE, GRANT)
        stock2 = run(srvA_url, None, GRANT_PROBE, GRANT)
        empty_post = run(srvA_url, json.dumps({}), GRANT_PROBE, GRANT)

        # M5: same session, two evaluations.
        m5vals, m5err = lib_shell.session(spoof(SEED), [GRANT_PROBE, GRANT_PROBE],
                                          navigate_to=srvA_url, extra_flags=GRANT)
    finally:
        srvA_stop()
        srvB_stop()

    # ---------------- M1: pre-grant enumerate = sp4 empties -----------------
    if is_err(m1):
        results["M1"] = (False, f"error {m1}")
    else:
        allempty = all(d["deviceId"] == "" and d["groupId"] == "" and d["label"] == ""
                       for d in m1["enumerate"])
        # Configured 2/2/2, but pre-grant stock lists one blank entry per
        # kind at most (media_devices_util.cc TranslateMediaDeviceInfoArray).
        results["M1"] = (by_kind_counts(m1["enumerate"]) ==
                         {"audioinput": 1, "videoinput": 1, "audiooutput": 1}
                         and allempty and m1["secure"] is True,
                         "pre-grant empties, one per kind")

    # ---------------- M2: post-grant enumerate shaped, real count -----------
    if is_err(spoofA1) or is_err(stock1):
        results["M2"] = (False, f"error spoof={spoofA1} stock={stock1}")
    else:
        se = spoofA1["enumerate"]
        inp = [d for d in se if d["kind"] in ("audioinput", "videoinput")]
        ok = (by_kind_counts(se) == by_kind_counts(stock1["enumerate"])
              and len(inp) > 0
              and all(d["deviceId"] != "" for d in inp)
              and all(d["deviceId"] == "default" or HEX64.match(d["deviceId"])
                      for d in inp))
        results["M2"] = (ok, f"count={by_kind_counts(se)} vs stock "
                             f"{by_kind_counts(stock1['enumerate'])}")

    # ---------------- M3: coherence gate -- track id in enumerate -----------
    if is_err(spoofA1):
        results["M3"] = (False, f"error {spoofA1}")
    else:
        ibk = ids_by_kind(spoofA1["enumerate"])
        ok = len(spoofA1["tracks"]) > 0 and all(
            t["settingsDeviceId"] in ibk.get(ENUMK[t["kind"]], set())
            for t in spoofA1["tracks"])
        results["M3"] = (ok, "track getSettings().deviceId in enumerate ids")

    # ---------------- M4: caps==settings + label==enumerate label -----------
    if is_err(spoofA1):
        results["M4"] = (False, f"error {spoofA1}")
    else:
        lab = {(d["kind"], d["deviceId"]): d["label"] for d in spoofA1["enumerate"]}
        ok = all(t["capsDeviceId"] == t["settingsDeviceId"] and
                 lab.get((ENUMK[t["kind"]], t["settingsDeviceId"])) == t["label"]
                 for t in spoofA1["tracks"])
        results["M4"] = (ok, "getCapabilities.deviceId==getSettings.deviceId; "
                             "track.label==enumerate label")

    # ---------------- M5: same session x2 identical -------------------------
    if m5err:
        results["M5"] = (False, f"error {m5err}")
    else:
        def tmap(r):
            return {t["kind"]: (t["settingsDeviceId"], t["label"]) for t in r["tracks"]}
        results["M5"] = (tmap(m5vals[0]) == tmap(m5vals[1]),
                         "two reads in one session identical")

    # ---------------- M6: rotation preserved (NOT stable supercookie) -------
    # §2 requires the synthetic id to rotate per launch exactly as stock does;
    # a stable id would be the cross-origin supercookie the design forbids.
    if any(is_err(x) for x in (spoofA1, spoofA2, stock1, stock2)):
        results["M6"] = (False, "error in a launch")
    else:
        sv1, sv2 = video_track_id(spoofA1), video_track_id(spoofA2)
        kv1, kv2 = video_track_id(stock1), video_track_id(stock2)
        spoof_rotates = (bool(HEX64.match(sv1 or "")) and bool(HEX64.match(sv2 or ""))
                         and sv1 != sv2)
        stock_rotates = (kv1 or "") != (kv2 or "")
        audio_stable = (audio_track_id(spoofA1) == audio_track_id(spoofA2) == "default")
        results["M6"] = (spoof_rotates and stock_rotates and audio_stable,
                         "REFORMULATED: synthetic video id rotates per launch "
                         "like stock (audio 'default' stable)")

    # ---------------- M7: different seed -> different (CONFOUNDED) -----------
    if is_err(spoofA1) or is_err(spoofA_seed2):
        results["M7"] = (False, "error")
    else:
        a, b = video_track_id(spoofA1), video_track_id(spoofA_seed2)
        ok = bool(HEX64.match(a or "")) and bool(HEX64.match(b or "")) and a != b
        results["M7"] = (ok, "seed differs -> id differs (CONFOUNDED: rotation "
                             "alone suffices -- see device_ids_unittest "
                             "DifferentSeedsDiffer)")

    # ---------------- M8: different origin -> different (CONFOUNDED) ---------
    if is_err(spoofA1) or is_err(spoofB1):
        results["M8"] = (False, "error")
    else:
        a, b = video_track_id(spoofA1), video_track_id(spoofB1)
        ok = bool(HEX64.match(a or "")) and bool(HEX64.match(b or "")) and a != b
        results["M8"] = (ok, "origin differs -> id differs (CONFOUNDED: rotation "
                             "alone suffices -- see device_ids_unittest "
                             "DifferentOriginsDiffer)")

    # ---------------- M9: {} == stock, pre AND post; stock is coherent ------
    if any(is_err(x) for x in (stock_pre, empty_pre, stock1, empty_post)):
        results["M9"] = (False, "error in a launch")
    else:
        pre_ok = by_kind_counts(empty_pre["enumerate"]) == by_kind_counts(stock_pre["enumerate"])
        post_ok = by_kind_counts(empty_post["enumerate"]) == by_kind_counts(stock1["enumerate"])
        secure_ok = empty_post["secure"] is True and stock1["secure"] is True
        # Validate the M3 invariant is NOT vacuous: it holds on stock too.
        sbk = ids_by_kind(stock1["enumerate"])
        stock_coherent = len(stock1["tracks"]) > 0 and all(
            t["settingsDeviceId"] in sbk.get(ENUMK[t["kind"]], set())
            for t in stock1["tracks"])
        results["M9"] = (pre_ok and post_ok and secure_ok and stock_coherent,
                         "{} matches stock pre+post; stock satisfies the M3 "
                         "invariant (non-vacuous)")

    # ---------------- M10: audio "default" sentinel preserved ---------------
    if is_err(spoofA1):
        results["M10"] = (False, f"error {spoofA1}")
    else:
        ibk = ids_by_kind(spoofA1["enumerate"])
        results["M10"] = ("default" in ibk.get("audioinput", set())
                          and audio_track_id(spoofA1) == "default",
                          "audio 'default' preserved in enumerate + track")

    # ---------------- M11: label == configured generic ----------------------
    if is_err(spoofA1):
        results["M11"] = (False, f"error {spoofA1}")
    else:
        tl = {t["kind"]: t["label"] for t in spoofA1["tracks"]}
        el = {d["kind"]: d["label"] for d in spoofA1["enumerate"]}
        ok = (tl.get("video") == "Camo Cam" and tl.get("audio") == "Camo Mic"
              and tl.get("video") != "fake_device_0"
              and el.get("videoinput") == "Camo Cam"
              and el.get("audioinput") == "Camo Mic"
              and el.get("audiooutput") == "Camo Speaker")
        results["M11"] = (ok, "track+enumerate labels == configured generic")

    # ---------------- M12: groupId coherence (track in enumerate) -----------
    if is_err(spoofA1):
        results["M12"] = (False, f"error {spoofA1}")
    else:
        gbk = {}
        for d in spoofA1["enumerate"]:
            gbk.setdefault(d["kind"], set()).add(d["groupId"])
        ok = len(spoofA1["tracks"]) > 0 and all(
            t["settingsGroupId"] in gbk.get(ENUMK[t["kind"]], set())
            for t in spoofA1["tracks"])
        results["M12"] = (ok, "track getSettings().groupId in enumerate groupIds "
                              "(by kind) -- the groupId leg of coherence")

    # ---------------- M13: post-stop label stays masked ---------------------
    if is_err(spoofA1):
        results["M13"] = (False, f"error {spoofA1}")
    else:
        pre = {t["kind"]: t["label"] for t in spoofA1["tracks"]}
        ps = spoofA1.get("postStop", [])
        ok = len(ps) > 0 and all(
            p["label"] != "fake_device_0"
            and p["label"] == pre.get(p["kind"]) for p in ps)
        results["M13"] = (ok, "post-stop track.label stays the generic mask "
                              "(no revert to real source name)")

    order = [f"M{i}" for i in range(1, 14)]
    for k in order:
        ok, note = results.get(k, (False, "MISSING"))
        print(f"{k}: {'PASS' if ok else 'FAIL'}  -- {note}")
    npass = sum(1 for k in order if results.get(k, (False,))[0])
    print(f"{npass}/13 " + ("ALL_PASS" if npass == 13 else "FAIL"))
    sys.exit(0 if npass == 13 else 1)


if __name__ == "__main__":
    main()

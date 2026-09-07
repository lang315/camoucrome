"""Verifies webrtc-ii fake-local-IP (webrtc:localipv4).

Under a media-permission (bypass) context (--use-fake-device flags), stock leaks
the raw LAN IP (172.22.x) in host candidates. With webrtc:localipv4 set, every
host candidate must show the configured fake IP -- coherently across
onicecandidate, pc.localDescription.sdp, and getStats() -- and zero raw / zero
.local. The substitution must NOT fire in the common no-permission path
(RI-NOPERM), which keeps .local.

RED (pre-hook): RI-FAKE/RI-SDP/RI-STATS FAIL (fake absent, raw 172.22.x present);
RI-STOCK/RI-NOPERM/RI-HIDE already PASS. GREEN: all pass.
"""
import json
import re
import sys

import lib_shell

FAKE = "192.168.1.37"
PRIV = re.compile(r"\b(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.)")
FLAGS = ["--ozone-platform=headless",
         "--use-fake-device-for-media-stream",
         "--use-fake-ui-for-media-stream"]
NOPERM_FLAGS = ["--ozone-platform=headless"]

GATHER = r"""(async () => {
  const pc = new RTCPeerConnection({iceServers: []});
  const cands = [];
  pc.onicecandidate = (e) => { if (e.candidate) cands.push(e.candidate.candidate); };
  pc.createDataChannel("x");
  await pc.setLocalDescription(await pc.createOffer());
  await new Promise((res) => {
    if (pc.iceGatheringState === "complete") return res();
    pc.addEventListener("icegatheringstatechange",
      () => { if (pc.iceGatheringState === "complete") res(); });
    setTimeout(res, 8000);
  });
  const stats = [];
  (await pc.getStats()).forEach((r) => {
    if (r.type === "local-candidate") stats.push(r.address || r.ip || "");
  });
  return {cands, sdp: pc.localDescription.sdp, stats};
})()"""

results = {}
notes = []


def run(cfg, flags):
    config = json.dumps(cfg) if cfg is not None else None
    v, e = lib_shell.session(config, [GATHER], extra_flags=flags)
    return (None, e) if e else (v[0], None)


def host_ips(cands):
    out = []
    for c in cands:
        m = re.search(r"candidate:\S+ \d+ \S+ \d+ (\S+) \d+ typ host", c)
        if m:
            out.append(m.group(1))
    return out


# --- bypass path (fake-device flags) ---
w, e = run({"webrtc:localipv4": FAKE}, FLAGS)
if e or not isinstance(w, dict):
    for k in ("RI-FAKE onicecandidate host IPs all == fake, no raw, no .local",
              "RI-SDP localDescription has fake, not raw, not .local",
              "RI-STATS getStats local-candidate address == fake, no raw"):
        results[k] = False
    notes.append(f"fake session error: {e or w}")
else:
    ips = host_ips(w["cands"])
    notes.append(f"fake host IPs: {ips}; stats: {w['stats']}")
    results["RI-FAKE onicecandidate host IPs all == fake, no raw, no .local"] = (
        len(ips) >= 1 and all(ip == FAKE for ip in ips)
        and not any(".local" in c for c in w["cands"]))
    results["RI-SDP localDescription has fake, not raw, not .local"] = (
        FAKE in w["sdp"] and not PRIV.search(w["sdp"].replace(FAKE, ""))
        and ".local" not in w["sdp"])
    results["RI-STATS getStats local-candidate address == fake, no raw"] = (
        any(s == FAKE for s in w["stats"])
        and not any(PRIV.search(s) and s != FAKE for s in w["stats"]))

# --- rule 5: no key -> raw leak untouched ---
w2, e2 = run(None, FLAGS)
if e2 or not isinstance(w2, dict):
    results["RI-STOCK no key -> raw private IP present"] = False
    notes.append(f"stock session error: {e2 or w2}")
else:
    ips2 = host_ips(w2["cands"])
    results["RI-STOCK no key -> raw private IP present"] = any(
        PRIV.search(ip) for ip in ips2)
    notes.append(f"stock host IPs: {ips2}")

# --- anti-tell: no permission -> substitution must NOT fire, keeps .local ---
w3, e3 = run({"webrtc:localipv4": FAKE}, NOPERM_FLAGS)
if e3 or not isinstance(w3, dict):
    results["RI-NOPERM no-perm keeps .local, no fake, no raw"] = False
    notes.append(f"noperm session error: {e3 or w3}")
else:
    results["RI-NOPERM no-perm keeps .local, no fake, no raw"] = (
        any(".local" in c for c in w3["cands"])
        and FAKE not in w3["sdp"]
        and not any(PRIV.search(ip) for ip in host_ips(w3["cands"])))
    notes.append(f"noperm cands: {w3['cands']}")

# --- regression: force-mDNS (webrtc-ii R-LEAK) still holds ---
w4, e4 = run({"webrtc:hideLocalIps": True}, FLAGS)
if e4 or not isinstance(w4, dict):
    results["RI-HIDE hideLocalIps still -> .local, no raw"] = False
    notes.append(f"hide session error: {e4 or w4}")
else:
    results["RI-HIDE hideLocalIps still -> .local, no raw"] = (
        any(".local" in c for c in w4["cands"])
        and not any(PRIV.search(ip) for ip in host_ips(w4["cands"])))

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for n in notes:
    print(f"      {n}")

sys.exit(0 if results and all(results.values()) else 1)

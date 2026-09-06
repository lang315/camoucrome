"""Verifies webrtc-ii force-mDNS (key webrtc:hideLocalIps) in FilteringNetworkManager.

The residual local-IP leak from sp4-webrtc-ip: a page holding camera/mic
permission bypasses mDNS (enumeration_permission()==ENUMERATION_ALLOWED) and
sees the raw LAN IP in ICE host candidates. webrtc:hideLocalIps forces the mDNS
responder on unconditionally in GetMdnsResponder(), so host candidates emit as
<uuid>.local even under permission (and even when an enterprise policy set
allow_mdns_obfuscation=false).

Three cases, each its own content_shell session (media permission is simulated
with --use-fake-{device,ui}-for-media-stream, which replace the base flags so
--ozone-platform=headless must be included):

- R-LEAK  (the fix): fake-device + {"webrtc:hideLocalIps":true}
            -> 0 raw private IP AND >=1 .local. RED pre-fix: 2 raw, 0 .local.
- R-STOCK (rule 5) : fake-device, no key -> >=1 raw private IP (leak untouched).
- R-NOPERM(no new tell): no fake-device + {"webrtc:hideLocalIps":true}
            -> 0 raw AND >=1 .local (force is a no-op where mDNS was already on).

The .local-present half of R-LEAK is what distinguishes this fix from sp4's
policy lever, which empties the candidate set. Assert .local by substring; two
.local names are random per session, never compare across sessions.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell

PROBE = r"""(async () => {
  const pc = new RTCPeerConnection({iceServers: []});
  pc.createDataChannel('x');
  const cands = [];
  pc.onicecandidate = (e) => { if (e.candidate) cands.push(e.candidate.candidate); };
  await pc.setLocalDescription(await pc.createOffer());
  await new Promise(r => setTimeout(r, 2500));
  pc.close();
  return cands;
})()"""

HEADLESS = "--ozone-platform=headless"
FAKE = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
        HEADLESS]

PRIV = re.compile(r"\b(10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|"
                  r"192\.168\.\d+\.\d+)\b")


def gather(config, flags):
    """Run the probe once; return (candidates, raw_priv_list, mdns_list, error)."""
    v, e = lib_shell.session(config, [PROBE], extra_flags=flags)
    if e:
        return None, None, None, f"{type(e).__name__}: {e}"
    cands = v[0]
    if not isinstance(cands, list):
        return None, None, None, f"probe returned non-list: {cands!r}"
    raw = [c for c in cands if PRIV.search(c)]
    mdns = [c for c in cands if ".local" in c]
    return cands, raw, mdns, None


results = {}
notes = []

# R-STOCK: media permission, no key -> the raw leak is present (rule 5).
cands, raw, mdns, err = gather(None, FAKE)
if err:
    results["R-STOCK leak present without the key (rule 5)"] = False
    notes.append(f"R-STOCK error: {err}")
else:
    results["R-STOCK leak present without the key (rule 5)"] = len(raw) >= 1
    notes.append(f"R-STOCK: {len(cands)} cands, {len(raw)} raw-private, "
                 f"{len(mdns)} .local; IPs="
                 f"{sorted({PRIV.search(c).group(0) for c in raw})}")

# R-LEAK: media permission + hideLocalIps -> no raw IP, mDNS present.
cands, raw, mdns, err = gather(json.dumps({"webrtc:hideLocalIps": True}), FAKE)
if err:
    results["R-LEAK hideLocalIps closes the permission leak, emits .local"] = False
    notes.append(f"R-LEAK error: {err}")
else:
    results["R-LEAK hideLocalIps closes the permission leak, emits .local"] = (
        len(raw) == 0 and len(mdns) >= 1)
    notes.append(f"R-LEAK: {len(cands)} cands, {len(raw)} raw-private, "
                 f"{len(mdns)} .local")

# R-NOPERM: no permission + hideLocalIps -> force is a no-op (mDNS already on).
cands, raw, mdns, err = gather(json.dumps({"webrtc:hideLocalIps": True}),
                               [HEADLESS])
if err:
    results["R-NOPERM force is a no-op where mDNS was already on"] = False
    notes.append(f"R-NOPERM error: {err}")
else:
    results["R-NOPERM force is a no-op where mDNS was already on"] = (
        len(raw) == 0 and len(mdns) >= 1)
    notes.append(f"R-NOPERM: {len(cands)} cands, {len(raw)} raw-private, "
                 f"{len(mdns)} .local")

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for note in notes:
    print(f"      {note}")

sys.exit(0 if results and all(results.values()) else 1)

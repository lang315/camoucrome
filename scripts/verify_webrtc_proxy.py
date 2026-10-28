"""WebRTC must not leak the host's public address while a proxy is set (backlog 4d).

Measured 2026-10-24 on the box's chrome, no proxy needed to see the lever:
  default                                         host + srflx (UDP)
  --force-webrtc-ip-handling-policy=disable_non_proxied_udp   host + srflx  (the switch is read only by
                                                  content_shell and headless; //chrome ignores it)
  Preferences webrtc.ip_handling_policy = disable_non_proxied_udp          no candidates
  CAMOU_CONFIG webrtc:ipHandlingPolicy = disable_non_proxied_udp           no candidates
So a client passing the switch protected nothing, in stock and in the fork, and with a proxy set the
page's STUN candidate (srflx, UDP, a proxy cannot carry it) holds the host's real public address.

  W0 probe capability: no proxy, default policy: the page gets a srflx candidate (STUN reaches out).
     Without it the other rows measure nothing.
  W1 proxy set, nothing else: no srflx/relay/prflx candidate and no host candidate with a raw IP.
  W2 proxy + --force-webrtc-ip-handling-policy=disable_non_proxied_udp: the same (the switch is read).
  W3 no proxy + that switch: the same (the switch is read without a proxy too).
  W4 precedence, one row each (S = srflx present, N = no candidate beyond mDNS host):
       camoucfg key > explicit pref > switch > proxy default > Chrome's default
     P1 pref=default explicit + proxy                         S  (the user's choice beats the proxy default)
     P2 pref=default explicit + switch disable, no proxy      S  (pref beats switch)
     P3 switch=default + proxy                                S  (switch beats the proxy default)
     P4 pref=default + camoucfg key disable_non_proxied_udp   N  (key beats pref)
     P5 pref=disable + camoucfg key default                   S  (key beats pref, the other way)
     P6 proxy in the Preferences file (fixed_servers), no switch   N  (proxy by pref, not only by switch)

The proxy is a dead local port: STUN is UDP and the page is a data: URL, so what is measured is the
policy the renderer receives, which is what a real proxy changes. The real-proxy check, comparing the
candidates to the host's real address, is run on the Windows host (measure_layer3 harness).
"""
import json
import os
import shutil
import sys
import tempfile

import lib_shell

PAGE = """async () => {
  const pc = new RTCPeerConnection({iceServers: [{urls: 'stun:stun.l.google.com:19302'}]});
  const got = [];
  pc.onicecandidate = e => { if (e.candidate) got.push(e.candidate.candidate); };
  pc.createDataChannel('x');
  await pc.setLocalDescription(await pc.createOffer());
  await new Promise(r => setTimeout(r, 6000));
  pc.close();
  return got;
}"""
PROXY = "--proxy-server=http://127.0.0.1:9"
FORCE = "--force-webrtc-ip-handling-policy="
D = "disable_non_proxied_udp"


def candidates(flags=(), pref=None, config=None, prefs_extra=None):
    prof = tempfile.mkdtemp(prefix="camou-rtc-")
    prefs = dict(prefs_extra or {})
    if pref:
        prefs["webrtc"] = {"ip_handling_policy": pref}
    if prefs:
        os.makedirs(os.path.join(prof, "Default"))
        with open(os.path.join(prof, "Default", "Preferences"), "w") as f:
            json.dump(prefs, f)
    proc = None
    try:
        proc = lib_shell.launch(json.dumps(config) if config else None, shell=lib_shell.CHROME, user_data_dir=prof,
                                extra_flags=[*lib_shell.CHROME_FLAGS, *flags])
        return lib_shell.evaluate(proc, [PAGE], navigate_to="data:text/html,<title>x</title>")[0], None
    except Exception as exc:  # noqa: BLE001 - any fault becomes a FAIL
        return None, f"{type(exc).__name__}: {exc}"
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)
        shutil.rmtree(prof, ignore_errors=True)


def kinds(cands):
    """(type, protocol) of each candidate, and whether a host candidate carries a raw IP."""
    out, raw_ip = [], False
    for c in cands:
        p = c.split(" ")
        typ = p[p.index("typ") + 1] if "typ" in p else "?"
        out.append((typ, p[2].lower()))
        if typ == "host" and not p[4].endswith(".local"):
            raw_ip = True
    return sorted(out), raw_ip


def verdict(**kw):
    """('S' srflx present | 'N' nothing beyond an mDNS host | 'L' other leak | 'E' error, detail)."""
    cands, err = candidates(**kw)
    if err:
        return "E", err
    k, raw = kinds(cands)
    types = {t for t, _ in k}
    if "srflx" in types:
        return "S", k
    if types - {"host"} or raw:
        return "L", f"{k} raw_host_ip={raw}"
    return "N", k


CASES = [
    # name, kwargs, expected
    ("W0 probe capability: no proxy, default policy: srflx appears (rule 5: unchanged without a proxy)", {}, "S"),
    ("W1 proxy set, nothing else: no candidate beyond mDNS host", dict(flags=[PROXY]), "N"),
    ("W2 proxy + the disable switch: none", dict(flags=[PROXY, FORCE + D]), "N"),
    ("W3 no proxy + the disable switch: none (the switch is read)", dict(flags=[FORCE + D]), "N"),
    ("P1 pref=default explicit + proxy: srflx (user's choice beats the proxy default)",
     dict(flags=[PROXY], pref="default"), "S"),
    ("P2 pref=default explicit + switch disable, no proxy: srflx (pref beats switch)",
     dict(flags=[FORCE + D], pref="default"), "S"),
    ("P3 switch=default + proxy: srflx (switch beats the proxy default)", dict(flags=[PROXY, FORCE + "default"]), "S"),
    ("P4 pref=default + camoucfg key disable: none (key beats pref)",
     dict(pref="default", config={"webrtc:ipHandlingPolicy": D}), "N"),
    ("P5 pref=disable + camoucfg key default: srflx (key beats pref)",
     dict(pref=D, config={"webrtc:ipHandlingPolicy": "default"}), "S"),
    ("P6 proxy only in the Preferences file (fixed_servers), no switch: none",
     dict(prefs_extra={"proxy": {"mode": "fixed_servers", "server": "127.0.0.1:9"}}), "N"),
]


def main():
    results, notes = {}, []
    for name, kw, want in CASES:
        got, detail = verdict(**kw)
        results[name] = got == want
        notes.append(f"{name.split(':')[0].split(' ')[0]} want {want} got {got} {detail}")
    for name, passed in sorted(results.items()):
        print(f"{'PASS' if passed else 'FAIL'}  {name}")
    for n in notes:
        print(f"      {n}")
    if len(results) == len(CASES) and all(results.values()):
        print("ALL_PASS")
        return 0
    print("FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())

"""WebRTC behind a REAL proxy leaks nothing but the exit (backlog 4d). Run on the Windows host, headed, in
session 1 (scripts/windows/run-interactive.ps1), with the proxy file of measure_layer3.

The page's candidates are compared, inside this process, to (a) the address the proxy exits from, read by the
page through the proxy, and (b) the host's own public address, read directly. Nothing but a verdict is
printed: an address, a proxy field or a username never reaches the output.

  R1 probe capability: the page read an exit address through the proxy, the host read its own, and they differ
     (otherwise a leak and the exit cannot be told apart), and the page collected at least one candidate OR the
     policy is the reason it collected none (stated as 'none collected', not as a pass of R1).
  R2 no candidate holds the host's public address.
  R3 no candidate holds an address other than the exit (an mDNS host name is fine).

  --arm fork|stock   fork is CAMOU_FORK_EXE; stock is the installed Chrome (the control: expected to LEAK before
                     the fork's default and, with no policy, also after: the fix is the fork's).
No policy argument is passed: the browser must protect by default.
"""
import argparse
import json
import os
import pathlib
import sys
import urllib.request

ECHO = "https://api.ipify.org"
RTC = """async () => {
  const out = [];
  const pc = new RTCPeerConnection({iceServers: [{urls: 'stun:stun.l.google.com:19302'}]});
  pc.createDataChannel('x');
  pc.onicecandidate = e => { if (e.candidate) out.push(e.candidate.candidate); };
  await pc.setLocalDescription(await pc.createOffer());
  await new Promise(r => setTimeout(r, 6000));
  pc.close();
  return out;
}"""


def classify(cands, exit_ip, real_ip):
    """Pure: returns (leaked_channels, n). Channels are 'type/proto', never addresses."""
    leaks = []
    for c in cands:
        p = c.split(" ")
        addr, typ, proto = p[4], p[p.index("typ") + 1], p[2].lower()
        if addr.endswith(".local"):
            continue
        if addr == real_ip or addr != exit_ip:
            leaks.append(f"{typ}/{proto}" + ("(host public address)" if addr == real_ip else ""))
    return sorted(set(leaks)), len(cands)


def load_proxy(path):
    cfg = json.loads(pathlib.Path(os.path.expanduser(path)).read_text(encoding="utf-8"))
    for k in ("server", "username_template", "password"):
        if not cfg.get(k):
            sys.exit("proxy file lacks a field")
    return {"server": cfg["server"], "username": cfg["username_template"].format(session="webrtc-check"),
            "password": cfg["password"]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=("fork", "stock"), default="fork")
    ap.add_argument("--proxy", default=os.path.expanduser("~/.config/camoucrome/layer3-proxy.json"))
    a = ap.parse_args(argv)
    from patchright.sync_api import sync_playwright
    from camoucrome import launch
    real = urllib.request.urlopen(ECHO, timeout=30).read().decode().strip()
    exe = os.environ["CAMOU_FORK_EXE"] if a.arm == "fork" else os.path.join(
        os.environ.get("CAMOU_STOCK_APP", r"C:\Program Files\Google\Chrome\Application"), "chrome.exe")
    with sync_playwright() as pw:
        ctx = launch(pw, exe, headless=False, args=[], proxy=load_proxy(a.proxy))
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("about:blank")
            exit_ip = page.evaluate(f"fetch('{ECHO}').then(r => r.text())").strip()
            cands = page.evaluate(RTC)
        finally:
            ctx.close()
    leaks, n = classify(cands, exit_ip, real)
    ok_probe = bool(exit_ip) and exit_ip != real
    print(f"R1 probe capability (exit read through the proxy, differs from the host's own): {'PASS' if ok_probe else 'FAIL'}")
    print(f"      candidates collected: {n}" + ("  (none collected: the policy is why)" if n == 0 else ""))
    print(f"R2 no candidate holds the host's public address: "
          f"{'PASS' if ok_probe and not any('host public' in l for l in leaks) else 'FAIL'}")
    print(f"R3 no candidate holds an address other than the exit: {'PASS' if ok_probe and not leaks else 'FAIL'}")
    print("leak: none" if ok_probe and not leaks else "leak: " + (", ".join(leaks) or "probe failed"))
    return 0 if ok_probe and not leaks else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - an error text can carry the proxy server: print the type only
        print(f"R-ERROR {type(exc).__name__} (message withheld)")
        sys.exit(2)

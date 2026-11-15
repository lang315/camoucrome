#!/usr/bin/env python3
"""UVPA on the Windows host: does the fork read what stock reads?

`PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable()` (and `getClientCapabilities()` where it
exists) answers from the host's authenticators (Windows Hello), so stock on this host is the oracle. One host run,
through run-interactive.ps1 in session 1, launches three arms from a loopback page (a secure context):

  stock  the frozen stock chrome (CAMOU_STOCK_APP), a seeded profile
  F0     the fork (CAMOU_OUT or CAMOU_EXE), no config
  F      the fork under a generated Windows identity (seed 1000)

  U1 fork without config reads stock's UVPA and client capabilities
  U2 fork under a generated identity reads stock's UVPA and client capabilities

PASS when the fork arm equals stock. A host without Windows Hello reads false in every arm: that is a PASS and the
note line says which case it was. UNMEASURED (exit 3) when PublicKeyCredential is undefined in any arm, or the
page never reported. --plant flips the fork's UVPA in the comparison (the RED: a comparison that cannot fail
measures nothing). Windows only; no Linux identity is generated, so there is nothing to compare there.
"""
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

PAGE_TIMEOUT_S = 90
IDENTITY_SEED = 1000

PAGE = """<!doctype html><meta charset=utf-8><title>uvpa</title><body><script>
(async () => {
  const r = { pkc: typeof PublicKeyCredential, uvpa: null, caps: null, errors: [] };
  try {
    if (r.pkc !== 'undefined') {
      r.uvpa = await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
      if (typeof PublicKeyCredential.getClientCapabilities === 'function')
        r.caps = await PublicKeyCredential.getClientCapabilities();
    }
  } catch (e) { r.errors.push(String(e)); }
  await fetch('/result', { method: 'POST', body: JSON.stringify(r) });
})();
</script></body>"""


def compare(stock, fork):
    """True when the fork's reading equals stock's: the UVPA boolean and the client capabilities, key for key."""
    return stock.get("uvpa") == fork.get("uvpa") and stock.get("caps") == fork.get("caps")


def rows(readings, plant=False):
    """[(row name, verdict)] from {'stock', 'F0', 'F'} readings; verdict True/False, or None (UNMEASURED) with a reason
    in the second slot of the returned pair list (name, verdict, why)."""
    out = []
    names = {"F0": "U1 fork without config reads stock's UVPA and client capabilities",
             "F": "U2 fork under a generated identity reads stock's UVPA and client capabilities"}
    for arm, name in names.items():
        bad = [a for a in ("stock", arm) if readings.get(a) is None or readings[a].get("pkc") == "undefined"
               or readings[a].get("errors")]
        if bad:
            out.append((name, None, f"{bad[0]}: no reading (PublicKeyCredential undefined, a page error, or no report)"))
            continue
        fork = dict(readings[arm])
        if plant:
            fork["uvpa"] = not fork["uvpa"]
        out.append((name, compare(readings["stock"], fork), None))
    return out


def stock_note(readings):
    """A note line when stock reads UVPA false: the host has no Windows Hello, so a PASS means the arms are equal, not
    that the fork exposes a platform authenticator."""
    st = readings.get("stock")
    if st and st.get("pkc") != "undefined" and st.get("uvpa") is False:
        return ("      NOTE stock reads isUserVerifyingPlatformAuthenticatorAvailable() false: this host has no platform "
                "authenticator, so PASS means the arms are equal, not that one is exposed")
    return None


class _Server(http.server.ThreadingHTTPServer):
    results = None


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.server.results.append(json.loads(self.rfile.read(n) or b"{}"))
        self.send_response(204)
        self.end_headers()


def main(argv):
    plant = "--plant" in argv[1:]
    import gpu_gate
    import lib_shell
    import measure_step2 as m2
    from camoucrome import launcher
    from measure_timing_parity import _kill_tree

    gpu_gate.require_interactive()
    stock_exe = os.path.join(os.environ.get("CAMOU_STOCK_APP") or m2.STOCK_APP, "chrome.exe")
    fork_exe = lib_shell.CHROME
    for exe in (stock_exe, fork_exe):
        if not os.path.isfile(exe):
            print(f"UNMEASURED: no browser at {exe}")
            return 3
    server = _Server(("127.0.0.1", 0), _Handler)
    server.results = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    ident = m2.identity(IDENTITY_SEED)

    def launch(arm):
        server.results = []
        if arm == "stock":
            udd = m2.SEED.fresh_copy()
            argv_ = [stock_exe, *launcher.BASE_ARGS, f"--user-data-dir={udd}"]
            env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}
        else:
            udd = tempfile.mkdtemp(prefix="uvpa-")
            if arm == "F0":
                argv_ = [fork_exe, *launcher.BASE_ARGS, f"--user-data-dir={udd}"]
                env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}
            else:
                cfg, lo = ident["config"], ident["launch"]
                args = launcher.build_args(tuple(lo["window"]) if lo.get("window") else None, lo.get("dpr"),
                                           lo.get("args", []), False, udd, launcher.accept_lang_of(cfg),
                                           position=tuple(lo["position"]) if lo.get("position") else None)
                argv_ = [fork_exe] + [x for x in args if x != "--remote-debugging-pipe"]
                env = launcher.build_env(cfg, fontconfig=launcher.fontconfig_for(cfg, None, None, fork_exe))
        proc = subprocess.Popen(argv_ + [url], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + PAGE_TIMEOUT_S
            while not server.results and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.5)
            return server.results[0] if server.results else None
        finally:
            _kill_tree(proc.pid)
            time.sleep(1.0)
            if arm != "stock":
                launcher.remove_dir(udd)
            else:
                m2.SEED.drop(udd)

    readings = {}
    with m2.seeded_control(stock_exe):
        for arm in ("stock", "F0", "F"):
            readings[arm] = launch(arm)
            print(f"      {arm}: {json.dumps(readings[arm], sort_keys=True)}", flush=True)
    verdicts = rows(readings, plant)
    note = stock_note(readings)
    if note:
        print(note)
    unm = False
    for name, ok, why in verdicts:
        if ok is None:
            unm = True
            print(f"UNMEASURED  {name}: {why}")
        else:
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if any(ok is False for _, ok, _ in verdicts):
        return 1
    return 3 if unm else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

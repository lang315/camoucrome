"""SP6b generator (A4 #2): every config `python -m camoucrome.gen` emits
starts the fork under CAMOU_CONFIG_STRICT with zero invariant and zero
wrong-type lines, and the page sees the emitted values -- the fork's own
coherence validator is the oracle. RED first: one emitted config with
ua:platform flipped to Linux under its Windows ua:osInfo must be refused
(exit 13, the verify_sp5a shape) and the log must name ua-os-family-agrees.

Per OS (windows, macos, linux) N configs, each launched through
python -m camoucrome.probe (patchright, --strict, --window, --dpr, the
driver's browser log via DEBUG=pw:browser):
  G1 browser starts, probe exits 0
  G2 log has no camoucfg: line at all (invariant, domain, wrong-type)
  G3 page sees screen.width/height, navigator.language, languages[0],
     timezone, devicePixelRatio == emitted; window.outerWidth == emitted
  G4 innerWidth <= outerWidth (headless honours --window-size; measured, not
     assumed -- headless pins an 800x600 ozone screen)
Zero generated configs is a failure.
"""
import html as html_mod
import http.server
import json
import os
import subprocess
import sys
import threading

HOME = os.path.expanduser("~")
EXE = os.environ.get("CAMOU_EXE", f"{HOME}/chromium/src/out/Default/chrome")
PY = os.environ.get("CAMOU_VENV", f"{HOME}/camoucrome-verify/venv") + "/bin/python3"
NODE = os.environ.get("PLAYWRIGHT_NODEJS_PATH", f"{HOME}/camoucrome-driver/node")
N = int(os.environ.get("CAMOU_GEN_N", "10"))
OSES = ["windows", "macos", "linux"]
TZ = {"windows": "Europe/Paris", "macos": "America/New_York", "linux": "Asia/Tokyo"}

PAGE = b"""<!doctype html><title>gen</title><pre id="o"></pre><script>
document.getElementById('o').textContent = JSON.stringify({
  width: screen.width, height: screen.height, availHeight: screen.availHeight,
  language: navigator.language, languages: navigator.languages,
  tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
  dpr: window.devicePixelRatio, outerWidth: window.outerWidth,
  innerWidth: window.innerWidth, ua: navigator.userAgent,
});
</script>"""


def serve():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_port}/", srv


def generate(os_name, seed):
    p = subprocess.run([PY, "-m", "camoucrome.gen", "--os", os_name, "--timezone", TZ[os_name],
                        "--seed", str(seed)], capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-400:])
    return json.loads(p.stdout)


def probe(url, config, launch):
    env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}
    env.update(DEBUG="pw:browser", PLAYWRIGHT_NODEJS_PATH=NODE)
    cmd = [PY, "-m", "camoucrome.probe", "--driver", "patchright", "--executable", EXE,
           "--url", url, "--strict", "--config", json.dumps(config),
           "--window", f"{launch['window'][0]},{launch['window'][1]}", "--dpr", str(launch["dpr"])]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env)
    report = json.loads(p.stdout)["report"] if p.returncode == 0 and p.stdout else None
    return p.returncode, report, p.stderr


def main():
    url, srv = serve()
    results, notes = {}, []
    total = 0
    for os_name in OSES:
        for i in range(N):
            gen = generate(os_name, seed=1000 + i)
            cfg, launch = gen["config"], gen["launch"]
            total += 1
            rc, rep, log = probe(url, cfg, launch)
            label = f"{os_name}#{i}"
            bad = []
            if rc != 0 or rep is None:
                bad.append(f"G1 probe rc={rc}: {log[-300:]}")
            else:
                # Every camoucfg: line -- invariant, domain ('<key>' is '<v>'),
                # wrong-type -- a clean config produces none.
                inv = [l for l in log.splitlines() if "camoucfg:" in l]
                if inv:
                    bad.append("G2 " + inv[0][-160:])
                exp = {"width": cfg["screen.width"], "height": cfg["screen.height"],
                       "language": cfg["navigator.language"], "tz": cfg["timezone:id"],
                       "dpr": launch["dpr"], "outerWidth": cfg["window.outerWidth"]}
                for k, v in exp.items():
                    if rep[k] != v:
                        bad.append(f"G3 {k}={rep[k]!r} expected {v!r}")
                if rep["languages"][0] != cfg["navigator.languages"][0]:
                    bad.append(f"G3 languages[0]={rep['languages'][0]}")
                if rep["innerWidth"] > rep["outerWidth"]:
                    bad.append(f"G4 innerWidth {rep['innerWidth']} > outerWidth {rep['outerWidth']}")
            results[label] = not bad
            if bad:
                notes.append(f"{label}: " + "; ".join(bad))
    # RED: a mutated config must be refused under strict.
    gen = generate("windows", seed=1)
    mutated = dict(gen["config"], **{"ua:platform": "Linux"})
    rc, rep, log = probe(url, mutated, gen["launch"])
    red = rc != 0 and rep is None and "invariant 'ua-os-family-agrees'" in log
    results["RED windows config with ua:platform=Linux is refused under strict"] = red
    if not red:
        notes.append(f"RED: rc={rc} rep={rep is not None} log has invariant line={'ua-os-family-agrees' in log}")
    srv.shutdown()
    n_ok = sum(results.values())
    for name, ok in results.items():
        if not ok or name.startswith("RED"):
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
    for n in notes:
        print("  " + n)
    print(f"{n_ok}/{len(results)} PASS ({total} generated configs across {len(OSES)} OSes)")
    ok = total == N * len(OSES) and all(results.values())
    print("ALL_PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

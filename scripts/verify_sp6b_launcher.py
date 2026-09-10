"""SP6b launcher-layer duties (A4 #3) and the deviceMemory domain entry,
measured on chrome through python -m camoucrome.probe (patchright).

L1 Accept-Language follows the config: a fr-FR,fr config sends
   "fr-FR,fr;q=0.9" (RED, measured 2026-09-10 before the launcher derived
   --accept-lang: the same config sent en-US,en;q=0.9).
L2 --load-extension on --headless=new: an MV3 extension written here (a
   document_start content script stamps documentElement.dataset.ext) is
   seen by the page; RED: same page without the extension sees nothing.
L3 --ignore-certificate-errors-spki-list: a self-signed HTTPS server here;
   with the cert's SPKI hash the page loads, RED: without it the probe fails.
L4 headed launch (WSLg DISPLAY on the box): starts, argv equals the
   contract's set minus --headless=new and Chrome's headless-only flags.
L5 domain: navigator.deviceMemory 16 (what the fingerprint pool says, what
   Chrome never reports) is refused under strict and the log names it;
   non-strict starts and logs it.
"""
import base64
import http.server
import json
import os
import ssl
import subprocess
import sys
import tempfile
import threading

HOME = os.path.expanduser("~")
EXE = os.environ.get("CAMOU_EXE", f"{HOME}/chromium/src/out/Default/chrome")
PY = os.environ.get("CAMOU_VENV", f"{HOME}/camoucrome-verify/venv") + "/bin/python3"
NODE = os.environ.get("PLAYWRIGHT_NODEJS_PATH", f"{HOME}/camoucrome-driver/node")
CONTRACT = json.loads(open(next(p for p in [
    os.environ.get("CAMOU_CONTRACT", ""),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "settings", "launcher.json"),
    f"{HOME}/camoucrome-client/settings/launcher.json"] if p and os.path.exists(p))).read())

PAGE = b"""<!doctype html><title>launcher</title><pre id="o"></pre><script>
document.getElementById('o').textContent = JSON.stringify({
  ext: document.documentElement.dataset.ext || null,
  language: navigator.language, proto: location.protocol,
});
</script>"""

FR = {"locale:tag": "fr-FR", "navigator.language": "fr-FR",
      "navigator.languages": ["fr-FR", "fr"], "timezone:id": "Europe/Paris"}


class Handler(http.server.BaseHTTPRequestHandler):
    records = []

    def do_GET(self):
        Handler.records.append((self.path, dict(self.headers)))
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *a):
        pass


def serve(tls=None):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    if tls:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(tls[0], tls[1])
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    scheme = "https" if tls else "http"
    return f"{scheme}://127.0.0.1:{srv.server_port}/", srv


def probe(url, config=None, extra=(), strict=False, headed=False):
    env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}
    env.update(DEBUG="pw:browser", PLAYWRIGHT_NODEJS_PATH=NODE)
    cmd = [PY, "-m", "camoucrome.probe", "--driver", "patchright", "--executable", EXE, "--url", url]
    if config is not None:
        cmd += ["--config", json.dumps(config)]
    if strict:
        cmd.append("--strict")
    if headed:
        cmd.append("--headed")
    cmd += list(extra)
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env)
    out = json.loads(p.stdout) if p.returncode == 0 and p.stdout else None
    return out, p.stderr


def make_extension(d):
    os.makedirs(d, exist_ok=True)
    json.dump({"manifest_version": 3, "name": "camou-probe", "version": "1",
               "content_scripts": [{"matches": ["<all_urls>"], "js": ["cs.js"],
                                    "run_at": "document_start"}]},
              open(os.path.join(d, "manifest.json"), "w"))
    open(os.path.join(d, "cs.js"), "w").write('document.documentElement.dataset.ext = "camou-ext";')


def make_cert(d):
    crt, key = os.path.join(d, "crt.pem"), os.path.join(d, "key.pem")
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key,
                    "-out", crt, "-days", "2", "-subj", "/CN=127.0.0.1",
                    "-addext", "subjectAltName=IP:127.0.0.1"], check=True, capture_output=True)
    pub = subprocess.run(["openssl", "x509", "-in", crt, "-pubkey", "-noout"], check=True,
                         capture_output=True).stdout
    der = subprocess.run(["openssl", "pkey", "-pubin", "-outform", "der"], input=pub, check=True,
                         capture_output=True).stdout
    import hashlib
    return crt, key, base64.b64encode(hashlib.sha256(der).digest()).decode()


def main():
    results, notes = {}, []
    url, srv = serve()
    work = tempfile.mkdtemp(prefix="camoucrome-launcher-")

    Handler.records.clear()
    out, log = probe(url, FR)
    al = next((h.get("Accept-Language") for _, h in Handler.records), None)
    L1 = "L1 Accept-Language follows the config (fr-FR,fr;q=0.9)"
    results[L1] = out is not None and al == "fr-FR,fr;q=0.9" and out["report"]["language"] == "fr-FR"
    if not results[L1]:
        notes.append(f"L1: header={al!r} out={out is not None} {log[-200:] if out is None else ''}")

    ext = os.path.join(work, "ext")
    make_extension(ext)
    out_red, _ = probe(url)
    out, log = probe(url, extra=["--extension", ext])
    L2 = "L2 --load-extension on headless=new: content script stamps the page (RED without: nothing)"
    results[L2] = (out_red is not None and out_red["report"]["ext"] is None
                   and out is not None and out["report"]["ext"] == "camou-ext")
    if not results[L2]:
        notes.append(f"L2: without={out_red and out_red['report']['ext']!r} with={out and out['report']['ext']!r} {log[-200:] if out is None else ''}")

    crt, key, spki = make_cert(work)
    surl, ssrv = serve((crt, key))
    out_red, _ = probe(surl)
    out, log = probe(surl, extra=["--spki", spki])
    L3 = "L3 SPKI allow-list: self-signed HTTPS loads with the hash (RED without: fails)"
    results[L3] = out_red is None and out is not None and out["report"]["proto"] == "https:"
    if not results[L3]:
        notes.append(f"L3: without={out_red is not None} with={out is not None} {log[-200:] if out is None else ''}")
    ssrv.shutdown()

    out, log = probe(url, headed=True)
    L4 = "L4 headed launch starts; argv == contract set minus the headless flags"
    if out is None:
        results[L4] = False
        notes.append(f"L4: {log[-300:]}")
    else:
        got = {a for a in out["argv"][1:] if not a.startswith("--user-data-dir=") and a != "--no-sandbox"}
        expected = set(CONTRACT["browser_argv_expected"]["args"]) - {"--headless=new"}
        results[L4] = got == expected
        if not results[L4]:
            notes.append(f"L4: unexpected={sorted(got - expected)} absent={sorted(expected - got)}")

    dm = dict(FR, **{"navigator.deviceMemory": 16})
    out_s, log_s = probe(url, dm, strict=True)
    out_w, log_w = probe(url, dm)
    named = "'navigator.deviceMemory' is '16'"
    L5 = "L5 deviceMemory 16: refused under strict, logged non-strict (domain entry)"
    results[L5] = (out_s is None and named in log_s and "[0.25, 8]" in log_s
                   and out_w is not None and named in log_w)
    if not results[L5]:
        notes.append(f"L5: strict_started={out_s is not None} strict_named={named in log_s} "
                     f"warn_started={out_w is not None} warn_named={named in log_w}")
    srv.shutdown()

    for name, ok in results.items():
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    for n in notes:
        print("  " + n)
    ok = all(results.values())
    print(f"{sum(results.values())} PASS {len(results) - sum(results.values())} FAIL")
    print("ALL_PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

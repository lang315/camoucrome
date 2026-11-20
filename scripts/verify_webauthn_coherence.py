"""WebAuthn coherence guard.

Chromium derives the `passkeyPlatformAuthenticator` client capability from the others:
`passkeyPlatformAuthenticator == isUVPAA || hybridTransport`
(content/browser/webauth/authenticator_common_impl.cc, InsertIsPPAACapability). The fork spoofs NONE of these; it
reports the host's real values, which are coherent by construction. This guard locks that in: if a future slice ever
spoofs a WebAuthn capability (the tempting cross-OS "a Mac has Touch ID, claim isUVPAA" fix), it must move the whole
set together, or this fails. ShardBrowser's engine gets exactly this wrong (isUVPAA true, ppaa false); the survey
`measurements/2026-11-20-engine-parity-survey.md` has the comparison.

RED-first: a mutant arm overrides getClientCapabilities to return the incoherent ShardX shape and must be flagged; a
CTRL arm with a no-op init script must stay clean. A GREEN run on the three claimed OSes carries meaning only because
the mutant proves the check can fail.

Box-only: needs patchright and the fork build (lib_shell layout, out/Default chrome -- content_shell has no
//chrome WebAuthn path).
"""
import http.server
import json
import os
import subprocess
import sys
import threading

OSES = ("windows", "macos", "linux")
# The incoherent shape ShardX returns: uvpa true while ppaa false (ppaa must be uvpa||hybrid). Injected in the main
# world for the RED arm only, to prove the check notices an incoherent report.
MUTANT_JS = ("(()=>{const r={userVerifyingPlatformAuthenticator:true,passkeyPlatformAuthenticator:false,"
             "hybridTransport:false,relatedOrigins:true};"
             "PublicKeyCredential.getClientCapabilities=()=>Promise.resolve(r);"
             "PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable=()=>Promise.resolve(true)})()")
CTRL_JS = "void 0"

PAGE = (b"<!doctype html><title>w</title><pre id=o></pre><script>(async()=>{const o={};"
        b"try{o.isUVPAA=await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();"
        b"const c=await PublicKeyCredential.getClientCapabilities();"
        b"o.uvpa=c.userVerifyingPlatformAuthenticator;o.ppaa=c.passkeyPlatformAuthenticator;o.hybrid=c.hybridTransport;}"
        b"catch(e){o.error=String(e)}document.getElementById('o').textContent=JSON.stringify(o)})()</script>")


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *a):
        pass


def read(pw, chrome, cfg, fonts_dir, url, init_js):
    """One launch's WebAuthn report under an optional init script. A launch or page failure is an error report."""
    from camoucrome.launcher import launch
    try:
        ctx = launch(pw, chrome, config=cfg, headless=True,
                     args=["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader"], fonts_dir=fonts_dir)
        try:
            if init_js is not None:
                ctx.add_init_script(init_js)
            page = ctx.new_page()
            page.goto(url)
            page.wait_for_function("document.getElementById('o').textContent !== ''", timeout=60000)
            return json.loads(page.locator("#o").text_content())
        finally:
            ctx.close()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def coherence_problems(rep):
    """The two relations a page can read in one getClientCapabilities() call. Absent/error is itself a failure."""
    if "error" in rep:
        return [f"report error: {rep['error']}"]
    missing = [k for k in ("isUVPAA", "uvpa", "ppaa", "hybrid") if k not in rep]
    if missing:
        return [f"missing {m}" for m in missing]
    out = []
    if rep["ppaa"] != (rep["uvpa"] or rep["hybrid"]):
        out.append(f"ppaa {rep['ppaa']} != uvpa({rep['uvpa']})||hybrid({rep['hybrid']})")
    if rep["isUVPAA"] != rep["uvpa"]:
        out.append(f"isUVPAA {rep['isUVPAA']} != caps.uvpa {rep['uvpa']}")
    return out


def main() -> int:
    from lib_shell import CHROME, layout
    _home, py, node, CLIENT, fonts_dir = layout()
    sys.path.insert(0, str(CLIENT / "scripts"))
    sys.path.insert(0, str(CLIENT / "client" / "python"))
    import camoucrome
    import client_guard
    client_guard.require(camoucrome, CLIENT)
    from patchright.sync_api import sync_playwright
    os.environ["PLAYWRIGHT_NODEJS_PATH"] = node
    seed = os.environ.get("CAMOU_SEED", "1")

    configs = {}
    for osname in OSES:
        g = subprocess.run([py, "-m", "camoucrome.gen", "--os", osname, "--seed", seed],
                           capture_output=True, text=True, timeout=120)
        if g.returncode != 0:
            print(f"gen {osname} failed: {g.stderr[-300:]}")
            return 2
        configs[osname] = json.loads(g.stdout)["config"]

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"

    rows = {}  # label -> (ok, detail)
    with sync_playwright() as pw:
        for osname in OSES:
            rep = read(pw, CHROME, configs[osname], fonts_dir, url, None)
            probs = coherence_problems(rep)
            rows[osname] = (not probs, probs or rep)
        # CTRL: a no-op init script must not disturb the windows report
        ctrl = coherence_problems(read(pw, CHROME, configs["windows"], fonts_dir, url, CTRL_JS))
        rows["CTRL"] = (not ctrl, ctrl)
        # MUTANT: the incoherent ShardX shape must be flagged
        mut = coherence_problems(read(pw, CHROME, configs["windows"], fonts_dir, url, MUTANT_JS))
        rows["MUTANT"] = (bool(mut), mut or "not flagged -- the check measured nothing")
    srv.shutdown()

    n = 0
    for label, (ok, detail) in rows.items():
        n += ok
        print("PASS " if ok else "FAIL ", label, "" if ok else json.dumps(detail)[:300])
    expected = len(OSES) + 2  # 3 OS + CTRL + MUTANT
    print(f"{n} PASS {len(rows) - n} FAIL (expected {expected})")
    return 0 if n == expected else 1


if __name__ == "__main__":
    sys.exit(main())

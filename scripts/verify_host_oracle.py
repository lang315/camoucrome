#!/usr/bin/env python3
"""The fork under a generated Windows identity vs stock Chrome 153 on the
Windows host (baselines/chrome-8010-stock-oracle-windows.json): the same
page (capture_host_oracle.page), every difference printed as one line.
Hardware- and config-bound values (screen, cores, memory, dpr, timezone,
languages, storage quota, heap limit, audio latency, device ids, canvas
hashes, GPU adapter strings) are compared only for *shape* unless a key is
named in EXACT. Exit 0 iff no line is printed outside the ignore set; the
point is the list, which the measurement doc turns into a backlog.

CAMOU_SEED picks the generated identity (default 1); --config <json> replaces it."""
import http.server
import json
import os
import pathlib
import subprocess
import sys
import threading

HOME = os.path.expanduser("~")
EXE = os.environ.get("CAMOU_EXE", f"{HOME}/chromium/src/out/Default/chrome")
PY = os.environ.get("CAMOU_VENV", f"{HOME}/camoucrome-verify/venv") + "/bin/python3"
NODE = os.environ.get("PLAYWRIGHT_NODEJS_PATH", f"{HOME}/camoucrome-driver/node")
CLIENT = pathlib.Path(os.environ.get("CAMOU_CLIENT", f"{HOME}/camoucrome-client"))
FONTS_DIR = os.environ.get("CAMOU_FONTS_DIR", str(CLIENT / "fonts"))
sys.path.insert(0, str(CLIENT / "scripts"))
import capture_host_oracle as cap  # noqa: E402

BASE = json.loads((CLIENT / "baselines" / "chrome-8010-stock-oracle-windows.json").read_text(encoding="utf-8"))["headed"]
# Values that legitimately follow the identity or the machine: compare type only.
SHAPE_ONLY = {"nav.hardwareConcurrency", "nav.deviceMemory", "nav.language", "nav.languages", "screen.width", "screen.height", "screen.availWidth",
              "screen.availHeight", "screen.availLeft", "screen.availTop", "win.dpr", "win.screenX", "win.screenY", "win.outerMinusInnerW",
              "win.outerMinusInnerH", "intl.dtf.timeZone", "intl.dtf.locale", "intl.nf.locale", "intl.collator", "intl.date0", "storage.quotaGiB",
              "storage.usage", "perfMem.jsHeapSizeLimit", "audio.baseLatency", "audio.outputLatency", "audioFp", "canvas.text", "canvas.shape",
              "gpu.info.description", "gpu.info.device", "gpu.info.vendor", "gpu.info.architecture", "gpu.limits.maxBufferSize",
              "gpu.limits.maxStorageBufferBindingSize", "gpu.features", "mediaDevices", "voices", "err.stack", "uadHigh.uaFullVersion",
              "uadHigh.fullVersionList", "uad.brands", "navConnection.rtt", "navConnection.downlink", "media.(color-gamut: p3)",
              "media.(dynamic-range: high)", "media.(video-dynamic-range: high)", "media.(prefers-color-scheme: dark)", "keyboard.size"}
# Leaves excluded from O1 with the reason each carries (printed as "known:" lines, never as DIFF):
KNOWN = {
    # The host is a headless PC with no mouse or keyboard attached: it reports pointer none / hover none and an empty
    # layout map. A desktop with input reports fine / hover, which d-pointer-touch derives for a Windows claim.
    "media.(pointer: fine)": "host has no mouse", "media.(pointer: none)": "host has no mouse", "media.(hover: hover)": "host has no mouse",
    "media.(any-pointer: fine)": "host has no mouse", "media.(any-hover: hover)": "host has no mouse",
    "keyboard.KeyA": "host has no keyboard", "keyboard.KeyQ": "host has no keyboard", "keyboard.Backquote": "host has no keyboard", "keyboard.Digit1": "host has no keyboard",
    # The probe's own init-script marker (patchright's add_init_script lands in the main world; verify_sp6b_driver excludes it too).
    "windowKeys": "probe marker __camou_init", "windowNames": "probe marker __camou_init", "protoCounts.Window": "probe marker __camou_init (+1)",
    # sp4-audio decided not to spoof the output rate (buffer-length coherence); the box renders at 44100, the host at 48000.
    "audio.sampleRate": "sp4-audio residual: real output rate (host 48000, box 44100)",
}


class H(http.server.BaseHTTPRequestHandler):
    body = b""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(H.body)

    def log_message(self, *a):
        pass


def flatten(v, prefix=""):
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            out.update(flatten(x, f"{prefix}.{k}" if prefix else k))
        return out
    return {prefix: v}


def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    H.body = cap.page().encode()
    env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}
    env["PLAYWRIGHT_NODEJS_PATH"] = NODE
    if "--config" in sys.argv:
        cfg = json.loads(sys.argv[sys.argv.index("--config") + 1])
    else:
        g = subprocess.run([PY, "-m", "camoucrome.gen", "--os", "windows", "--seed", os.environ.get("CAMOU_SEED", "1")], capture_output=True, text=True, timeout=120)
        if g.returncode != 0:
            sys.exit(g.stderr[-500:])
        cfg = json.loads(g.stdout)["config"]
    p = subprocess.run([PY, "-m", "camoucrome.probe", "--driver", "patchright", "--executable", EXE, "--url", f"http://127.0.0.1:{srv.server_port}/",
                        "--config", json.dumps(cfg), "--fonts-dir", FONTS_DIR, "--arg=--use-gl=angle", "--arg=--use-angle=swiftshader"],
                       capture_output=True, text=True, timeout=240, env=env)
    srv.shutdown()
    if p.returncode != 0:
        sys.exit(p.stderr[-800:])
    fork = json.loads(p.stdout)["report"]
    for key in ("windowKeys", "navProto", "windowNames"):  # lists: the set difference minus the probe marker, compared as sets
        h, f = set(BASE.get(key) or []), set(fork.get(key) or []) - {"__camou_init"}
        if h != f:
            print(f"DIFF {key}: host-only={sorted(h - f)} fork-only={sorted(f - h)}")
        BASE[key], fork[key] = sorted(h), sorted(f)
    if fork.get("protoCounts", {}).get("Window") == BASE.get("protoCounts", {}).get("Window", 0) + 1:
        fork["protoCounts"]["Window"] -= 1  # the probe marker
    host_f, fork_f = flatten(BASE), flatten(fork)
    diffs = []
    for k in sorted(set(host_f) | set(fork_f)):
        h, f = host_f.get(k, "<absent>"), fork_f.get(k, "<absent>")
        if any(k == s or k.startswith(s + ".") for s in SHAPE_ONLY):
            if type(h) != type(f):
                diffs.append((k, f"type {type(h).__name__}", f"type {type(f).__name__}"))
            continue
        if h != f:
            if k in KNOWN:
                print(f"known: {k}: host={json.dumps(h)[:80]} fork={json.dumps(f)[:80]} ({KNOWN[k]})")
                continue
            diffs.append((k, h, f))
    print("note: voices host=", json.dumps(BASE.get("voices"))[:300], "fork=", json.dumps(fork.get("voices"))[:300])
    print("note: audioFp host=", BASE.get("audioFp"), "fork=", fork.get("audioFp"), "| canvas host=", BASE.get("canvas"), "fork=", fork.get("canvas"))
    same = len(set(host_f) | set(fork_f)) - len(diffs)
    for k, h, f in diffs:
        print(f"DIFF {k}: host={json.dumps(h)[:160]} fork={json.dumps(f)[:160]}")
    print(f"{len(diffs)} DIFF, {same} same leaves; fork done={fork.get('done')} pageError={fork.get('pageError')}")
    results = {"O1 generated Windows identity: no difference from stock Windows Chrome outside the named set (host artefacts, identity-bound, probe marker, sampleRate)": not diffs}
    if "--config" not in sys.argv:
        # O2 RED: a Linux claim keeps Linux's shape -- the gated interfaces follow the claim, not the build.
        g = subprocess.run([PY, "-m", "camoucrome.gen", "--os", "linux", "--timezone", "UTC", "--seed", "1"], capture_output=True, text=True, timeout=120)
        lin = json.loads(g.stdout)["config"]
        r = subprocess.run([PY, sys.argv[0], "--config", json.dumps(lin)], capture_output=True, text=True, timeout=400, env=env)
        ok2 = "host-only=['bluetooth', 'canShare', 'share']" in r.stdout and "'queryLocalFonts'" in r.stdout
        if not ok2:
            print("O2 sub-run rc", r.returncode, "navProto line:", [l[:120] for l in r.stdout.splitlines() if l.startswith("DIFF navProto: host-only")],
                  "windowNames has queryLocalFonts:", any("queryLocalFonts" in l for l in r.stdout.splitlines() if l.startswith("DIFF windowNames")))
        results["O2 RED Linux claim: navigator.share / bluetooth absent, queryLocalFonts absent (the gate follows the claim)"] = ok2
        results.update(font_access_rows(cfg, env))
        results.update(brand_header_rows(cfg, env))
    n = sum(results.values())
    for k, v in results.items():
        print("PASS " if v else "FAIL ", k)
    print(f"{n} PASS {len(results) - n} FAIL")
    sys.exit(0 if n == len(results) else 1)


FA_PAGE = b"""<!doctype html><title>fa</title><button id=b>go</button><pre id=o></pre><script>
document.getElementById('b').onclick=async()=>{try{const fs=await queryLocalFonts();document.getElementById('o').textContent=JSON.stringify({n:fs.length,
faces:fs.map(f=>[f.postscriptName,f.fullName,f.family,f.style])})}catch(e){document.getElementById('o').textContent=JSON.stringify({error:e.name+': '+e.message})}};
</script>"""


def font_access_rows(cfg, env):
    """O3: queryLocalFonts() under the real permission flow. Without a grant the call needs the prompt (headless:
    denied => NotAllowedError, as stock without a grant); with the local-fonts permission granted and a click for
    activation it lists exactly the manifest's captured Windows faces, sorted by PostScript name, none of the bundle's."""
    script = f"""
import json, sys
sys.path.insert(0, {json.dumps(str(CLIENT / "client" / "python"))})
from camoucrome.launcher import launch
from patchright.sync_api import sync_playwright
import http.server, threading
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write({FA_PAGE!r})
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{{srv.server_port}}/"
out = {{}}
with sync_playwright() as pw:
    ctx = launch(pw, {json.dumps(EXE)}, config=json.loads({json.dumps(json.dumps(cfg))}), headless=True, args=["--no-sandbox"], fonts_dir={json.dumps(FONTS_DIR)})
    page = ctx.new_page(); page.goto(url); page.click("#b"); page.wait_for_function("document.getElementById('o').textContent !== ''", timeout=20000)
    out["nogrant"] = json.loads(page.locator("#o").text_content())
    ctx.grant_permissions(["local-fonts"], origin=url)
    page.goto(url); page.click("#b"); page.wait_for_function("document.getElementById('o').textContent !== ''", timeout=20000)
    out["granted"] = json.loads(page.locator("#o").text_content())
    ctx.close()
print(json.dumps(out))
"""
    p = subprocess.run([PY, "-c", script], capture_output=True, text=True, timeout=300, env=env)
    if p.returncode != 0:
        print("O3 probe failed:", p.stderr[-900:].replace("\n", " | "))
        return {"O3 queryLocalFonts()": False}
    r = json.loads(p.stdout.strip().splitlines()[-1])
    want = [f.split("\t") for f in cfg["fonts:local"]]
    got = r["granted"].get("faces")
    print(f"note: O3 no grant -> {json.dumps(r['nogrant'])[:120]}; granted -> n={r['granted'].get('n')} first={json.dumps((got or [])[:2])}")
    # Stock resolves with an empty list when the prompt is denied (headless denies it); with the grant and a click
    # for activation the list is the claimed host's.
    return {"O3 queryLocalFonts(): denied prompt -> [] as stock; granted + activated -> exactly the manifest's Windows faces in PostScript order, none of the bundle's": (
        r["nogrant"].get("n") == 0 and got == want and len(got or []) > 150 and not any("Selawik" in f[0] or "Liberation" in f[0] for f in got))}


def brand_header_rows(cfg, env):
    """O4: the brand list is produced twice, in the browser (Sec-CH-UA / Sec-CH-UA-Full-Version-List request headers)
    and in the renderer (navigator.userAgentData). Both must carry the host's stock list in its order; O1 only saw the
    renderer's copy."""
    script = f"""
import json, sys
sys.path.insert(0, {json.dumps(str(CLIENT / "client" / "python"))}); sys.path.insert(0, {json.dumps(str(CLIENT / "scripts"))})
import echo_server
from camoucrome.launcher import launch
from patchright.sync_api import sync_playwright
base, headers_for, stop = echo_server.start(["Sec-CH-UA-Full-Version-List"])
out = {{}}
with sync_playwright() as pw:
    ctx = launch(pw, {json.dumps(EXE)}, config=json.loads({json.dumps(json.dumps(cfg))}), headless=True, args=["--no-sandbox"], fonts_dir={json.dumps(FONTS_DIR)})
    page = ctx.new_page(); page.goto(base + "/"); page.goto(base + "/")  # second load carries the Accept-CH hints
    out["js"] = page.evaluate("navigator.userAgentData.getHighEntropyValues(['fullVersionList']).then(h => ({{brands: navigator.userAgentData.brands, full: h.fullVersionList}}))")
    h = {{k.lower(): v for k, v in (headers_for("/") or {{}}).items()}}
    out["hdr"] = {{"ua": h.get("sec-ch-ua"), "full": h.get("sec-ch-ua-full-version-list")}}
    ctx.close()
stop()
print(json.dumps(out))
"""
    p = subprocess.run([PY, "-c", script], capture_output=True, text=True, timeout=300, env=env)
    if p.returncode != 0:
        print("O4 probe failed:", p.stderr[-900:].replace("\n", " | "))
        return {"O4 brand headers": False}
    r = json.loads(p.stdout.strip().splitlines()[-1])

    def parse(sh):  # RFC 8941 list: "Google Chrome";v="153", ...
        return [{"brand": i.split('";v="')[0].strip().strip('"'), "version": i.split('";v="')[1].rstrip('"')} for i in (sh or "").split(", ") if '";v="' in i]
    host = BASE["uad"]["brands"], BASE["uadHigh"]["fullVersionList"]
    got = (r["js"]["brands"], r["js"]["full"], parse(r["hdr"]["ua"]), parse(r["hdr"]["full"]))
    print(f"note: O4 Sec-CH-UA={r['hdr']['ua']!r} full={r['hdr']['full']!r}")
    return {"O4 brands: Sec-CH-UA and Sec-CH-UA-Full-Version-List request headers == navigator.userAgentData == the host's stock list in stock order": (
        got[0] == host[0] and got[1] == host[1] and got[2] == host[0] and got[3] == host[1])}


if __name__ == "__main__":
    main()

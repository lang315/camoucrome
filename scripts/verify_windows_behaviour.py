#!/usr/bin/env python3
"""windows-behaviour: navigator.share() under a Windows/macOS claim behaves like a dismissed share sheet instead of
killing the renderer (the broker's "no binder" path); voices follow the claimed locale.

Runs on the box against out/Default/chrome (content_shell has no chrome/browser binders) through the patchright
client. RED for S1 is the pre-fix run: "Target crashed" (2026-09-12, share_probe.py)."""
import json
import os
import pathlib
import subprocess
import sys

HOME = os.path.expanduser("~")
EXE = os.environ.get("CAMOU_EXE", f"{HOME}/chromium/src/out/Default/chrome")
PY = os.environ.get("CAMOU_VENV", f"{HOME}/camoucrome-verify/venv") + "/bin/python3"
NODE = os.environ.get("PLAYWRIGHT_NODEJS_PATH", f"{HOME}/camoucrome-driver/node")
CLIENT = pathlib.Path(os.environ.get("CAMOU_CLIENT", f"{HOME}/camoucrome-client"))
FONTS_DIR = os.environ.get("CAMOU_FONTS_DIR", str(CLIENT / "fonts"))

PAGE = b"""<!doctype html><title>share</title><button id=b>go</button><pre id=o>idle</pre><script>
const o = document.getElementById('o');
function go() { o.textContent = 'pending'; const t0 = performance.now();
  navigator.share({title: 'x', text: 'y', url: location.href}).then(
    () => o.textContent = JSON.stringify({ok: 1, ms: performance.now() - t0}),
    e => o.textContent = JSON.stringify({err: e.name + ': ' + e.message, ms: performance.now() - t0})); }
document.getElementById('b').onclick = go;
if (location.search === '?auto') go();  // no user activation: the renderer rejects before any browser call
</script>"""


def probe(cfg, gesture, budget_ms, twice=False):
    """Returns {"typeof": ..., "result": <#o JSON or None>, "alive": <page still answers>}."""
    script = f"""
import json, sys, time
sys.path.insert(0, {json.dumps(str(CLIENT / "client" / "python"))})
from camoucrome.launcher import launch
from patchright.sync_api import sync_playwright
import http.server, threading
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write({PAGE!r})
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
out = {{}}
with sync_playwright() as pw:
    ctx = launch(pw, {json.dumps(EXE)}, config=json.loads({json.dumps(json.dumps(cfg))}), headless=True, args=["--no-sandbox"], fonts_dir={json.dumps(FONTS_DIR)})
    page = ctx.new_page(); page.goto(f"http://127.0.0.1:{{srv.server_port}}/" + ("" if {gesture!r} else "?auto"))
    out["typeof"] = page.evaluate("typeof navigator.share")
    if out["typeof"] == "function":
        if {gesture!r}:
            page.click("#b")
            if {twice!r}:
                page.wait_for_function("document.getElementById('o').textContent.startsWith('{{')", timeout={budget_ms})
                out["first"] = json.loads(page.locator("#o").text_content())
                page.click("#b")
        t = time.time(); v = "pending"
        while time.time() - t < {budget_ms} / 1000:
            try:
                v = page.locator("#o").text_content(timeout=2000)
            except Exception as e:
                out["crash"] = str(e).splitlines()[0]; break
            if v not in ("idle", "pending"): break
            time.sleep(0.1)
        out["result"] = json.loads(v) if v.startswith("{{") else v
    try:
        out["alive"] = page.evaluate("1 + 1") == 2
    except Exception as e:
        out["alive"] = False; out["crash"] = out.get("crash") or str(e).splitlines()[0]
    ctx.close()
print(json.dumps(out))
"""
    env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}
    env["PLAYWRIGHT_NODEJS_PATH"] = NODE
    p = subprocess.run([PY, "-c", script], capture_output=True, text=True, timeout=300, env=env)
    if p.returncode != 0:
        return {"error": p.stderr[-600:].replace("\n", " | ")}
    return json.loads(p.stdout.strip().splitlines()[-1])


def gen(os_name, locale=None):
    cmd = [PY, "-m", "camoucrome.gen", "--os", os_name, "--timezone", "UTC", "--seed", "1"] + (["--locale", locale] if locale else [])
    g = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if g.returncode != 0:
        sys.exit(g.stderr[-500:])
    return json.loads(g.stdout)["config"]


def main():
    results = {}
    win = gen("windows")
    ms = win["share:cancelMs"]
    r = probe(win, gesture=True, budget_ms=ms + 6000)
    res = r.get("result") or {}
    print(f"note: S1 cancelMs={ms} -> {json.dumps(r)[:200]}")
    results[f"S1 Windows claim + gesture: AbortError 'Share canceled' after >= share:cancelMs ({ms}) and < +3000, page alive (RED pre-fix: Target crashed)"] = (
        isinstance(res, dict) and res.get("err") == "AbortError: Share canceled" and ms <= res.get("ms", -1) < ms + 3000 and r.get("alive") is True)
    r = probe(win, gesture=True, budget_ms=2 * ms + 8000, twice=True)
    a, b = (r.get("first") or {}).get("ms"), (r.get("result") or {}).get("ms")
    print(f"note: S1b two gestures -> {a} ms then {b} ms")
    results["S1b two gestures in one page: both cancel within [cancelMs, cancelMs+3000) and the delays differ (per-call jitter)"] = (
        a is not None and b is not None and ms <= a < ms + 3000 and ms <= b < ms + 3000 and round(a) != round(b) and r.get("alive") is True)
    r = probe(win, gesture=False, budget_ms=3000)
    res = r.get("result") or {}
    print(f"note: S2 no gesture -> {json.dumps(r)[:160]}")
    results["S2 Windows claim, no gesture: NotAllowedError (renderer-side, unchanged), page alive"] = (
        isinstance(res, dict) and str(res.get("err", "")).startswith("NotAllowedError") and r.get("alive") is True)
    r = probe(gen("linux"), gesture=True, budget_ms=1000)
    results["S3 Linux claim: navigator.share undefined"] = r.get("typeof") == "undefined"
    bare = {k: v for k, v in win.items() if k != "share:cancelMs"}
    r = probe(bare, gesture=True, budget_ms=5000)
    res = r.get("result") or {}
    print(f"note: S4 absent -> {json.dumps(r)[:160]}")
    results["S4 key absent: cancels within the jitter alone (< 700 ms), page alive (fail-closed, never the broker kill)"] = (
        isinstance(res, dict) and res.get("err") == "AbortError: Share canceled" and res.get("ms", 1e9) < 700 and r.get("alive") is True)
    fr = gen("windows", "fr-FR")["voices:list"]
    results["V1 fr-FR Windows identity: voices Hortense (default), Julie, Paul, all fr-FR"] = (
        [v["name"].split(" - ")[0] for v in fr] == ["Microsoft Hortense", "Microsoft Julie", "Microsoft Paul"]
        and all(v["lang"] == "fr-FR" for v in fr) and [v["default"] for v in fr] == [True, False, False])
    nz, uk = gen("windows", "en-NZ")["voices:list"], gen("windows", "uk-UA")["voices:list"]
    results["V2 en-NZ -> the en-AU row (same language); uk-UA -> en-US"] = nz[0]["lang"] == "en-AU" and uk[0]["lang"] == "en-US"
    lin = gen("linux")
    results.update(audio_rows(win, lin))
    results.update(platform_version_rows(win, lin))
    mac = gen("macos")["voices:list"]
    results["V3 macOS claim: the measured Mac list (191 voices, Samantha default)"] = len(mac) == 191 and mac[0]["name"] == "Samantha" and mac[0]["default"] is True
    n = sum(results.values())
    for k, v in results.items():
        print("PASS " if v else "FAIL ", k)
    print(f"{n} PASS {len(results) - n} FAIL")
    sys.exit(0 if n == len(results) else 1)


PV_PAGE = b"""<!doctype html><title>pv</title><pre id=o></pre><script>
navigator.userAgentData.getHighEntropyValues(['platformVersion']).then(h => document.getElementById('o').textContent = JSON.stringify({pv: h.platformVersion, platform: navigator.userAgentData.platform}));
</script>"""


def platform_version_rows(win, lin):
    """U1: a Linux identity carries no ua:platformVersion (the pool has none); the real value shows -- and on Linux stock Chrome
    at the pin that value is the empty string (baselines/chrome-507c6ee3e2-stock-ua.json), so the pool's "" was never a tell."""
    def read(cfg):
        r = probe_page(cfg, PV_PAGE)
        return r if isinstance(r, dict) else {}
    l, bare, w = read(lin), read({}), read(win)
    stock = json.loads((CLIENT / "baselines" / "chrome-507c6ee3e2-stock-ua.json").read_text(encoding="utf-8"))["high_entropy"]["platformVersion"]
    print(f"note: U1 Linux claim -> {json.dumps(l)}; no config -> {json.dumps(bare)}; Windows claim -> {json.dumps(w)}")
    return {
        f"U1 Linux claim: platformVersion == the no-config value == pristine stock Linux at the pin ({stock!r}); the key is not emitted": (
            "ua:platformVersion" not in lin and l.get("pv") == bare.get("pv") == stock and l.get("platform") == "Linux"),
        "U2 Windows claim: platformVersion 10.0.0 (the manifest's pin)": w.get("pv") == "10.0.0",
    }


def probe_page(cfg, page):
    script = f"""
import json, sys
sys.path.insert(0, {json.dumps(str(CLIENT / "client" / "python"))})
from camoucrome.launcher import launch
from patchright.sync_api import sync_playwright
import http.server, threading
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write({page!r})
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
with sync_playwright() as pw:
    ctx = launch(pw, {json.dumps(EXE)}, config=json.loads({json.dumps(json.dumps(cfg))}), headless=True, args=["--no-sandbox"], fonts_dir={json.dumps(FONTS_DIR)})
    page = ctx.new_page(); page.goto(f"http://127.0.0.1:{{srv.server_port}}/")
    page.wait_for_function("document.getElementById('o').textContent !== ''", timeout=20000)
    print(page.locator("#o").text_content())
    ctx.close()
"""
    env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}
    env["PLAYWRIGHT_NODEJS_PATH"] = NODE
    p = subprocess.run([PY, "-c", script], capture_output=True, text=True, timeout=300, env=env)
    if p.returncode != 0:
        return {"error": p.stderr[-400:].replace("\n", " | ")}
    return json.loads(p.stdout.strip().splitlines()[-1])


AUDIO_PAGE = b"""<!doctype html><title>audio</title><button id=b>go</button><pre id=o></pre><script>
document.getElementById('b').onclick = async () => {
  const ac = new AudioContext(); await ac.resume();
  const off = new OfflineAudioContext(1, 4096, 44100); const osc = off.createOscillator(); osc.connect(off.destination); osc.start();
  const buf = await off.startRendering(); let peak = 0; for (const x of buf.getChannelData(0)) peak = Math.max(peak, Math.abs(x));
  document.getElementById('o').textContent = JSON.stringify({rate: ac.sampleRate, base: ac.baseLatency, frames: ac.baseLatency * ac.sampleRate, state: ac.state, offPeak: peak});
  ac.close();
};
</script>"""


def audio_probe(cfg):
    script = f"""
import json, sys
sys.path.insert(0, {json.dumps(str(CLIENT / "client" / "python"))})
from camoucrome.launcher import launch
from patchright.sync_api import sync_playwright
import http.server, threading
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write({AUDIO_PAGE!r})
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
with sync_playwright() as pw:
    ctx = launch(pw, {json.dumps(EXE)}, config=json.loads({json.dumps(json.dumps(cfg))}), headless=True, args=["--no-sandbox"], fonts_dir={json.dumps(FONTS_DIR)})
    page = ctx.new_page(); page.goto(f"http://127.0.0.1:{{srv.server_port}}/"); page.click("#b")
    page.wait_for_function("document.getElementById('o').textContent !== ''", timeout=20000)
    print(page.locator("#o").text_content())
    ctx.close()
"""
    env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}
    env["PLAYWRIGHT_NODEJS_PATH"] = NODE
    p = subprocess.run([PY, "-c", script], capture_output=True, text=True, timeout=300, env=env)
    if p.returncode != 0:
        return {"error": p.stderr[-400:].replace("\n", " | ")}
    return json.loads(p.stdout.strip().splitlines()[-1])


def audio_rows(win, lin):
    """A1-A3: the reported output rate follows audio:sampleRate; the render still runs and an offline render is non-silent."""
    a = audio_probe(win)
    bare = audio_probe({k: v for k, v in win.items() if k != "audio:sampleRate"})
    l = audio_probe(lin)
    print(f"note: A1 Windows claim -> {json.dumps(a)[:160]}; key absent -> {json.dumps(bare)[:100]}; Linux claim -> {json.dumps(l)[:100]}")
    want = win["audio:sampleRate"]
    frames = win["audio:bufferFrames"]
    return {
        f"A4 Windows claim: baseLatency == audio:bufferFrames / audio:sampleRate ({frames}/{want} = {frames / want:g}), the host's own 0.01 (RED: the box's 512 frames before the key)": (
            a.get("frames") is not None and round(a["frames"]) == frames and abs(a.get("base", 0) - frames / want) < 1e-9),
        f"A1 Windows claim: AudioContext.sampleRate == audio:sampleRate ({want}), baseLatency*rate an integer frame count, state running, offline render non-silent (RED: the box's real rate before the hook)": (
            a.get("rate") == want and abs(a.get("frames", 0) - round(a.get("frames", 0))) < 1e-6 and a.get("state") == "running" and a.get("offPeak", 0) > 0.5),
        f"A2 key absent: the device's real rate ({bare.get('rate')}), which on this box differs from the claim's -- the hook is config-gated": bare.get("rate") is not None and bare.get("rate") != want,
        "A3 Linux claim (no key emitted): the real rate, equal to A2": l.get("rate") == bare.get("rate") and l.get("rate") is not None,
    }


if __name__ == "__main__":
    main()

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
    n = sum(results.values())
    for k, v in results.items():
        print("PASS " if v else "FAIL ", k)
    print(f"{n} PASS {len(results) - n} FAIL")
    sys.exit(0 if n == len(results) else 1)


if __name__ == "__main__":
    main()

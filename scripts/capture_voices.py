#!/usr/bin/env python3
"""Captures speechSynthesis.getVoices() and the AudioContext output rate on a stock Chrome.

  --where mac       stock Chrome on this Mac, headed app window (headless hangs on this Mac)
  --where winhost   stock Chrome on the box's Windows host, headed over CDP (voices arrive on voiceschanged)

Writes settings/voices.json (macOS list, or the Windows row for --locale) and settings/audio.json.
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

PAGE = """<!doctype html><title>voices</title><pre id="o"></pre><script>
const get = () => speechSynthesis.getVoices().map(v => ({name: v.name, lang: v.lang, voiceURI: v.voiceURI, localService: v.localService, default: v.default}));
async function run() {
  let voices = get();
  if (voices.length === 0) await new Promise(r => { speechSynthesis.onvoiceschanged = r; setTimeout(r, 4000); });
  voices = get();
  const ac = new AudioContext();
  const out = {voices, sampleRate: ac.sampleRate, baseLatency: ac.baseLatency, state: ac.state, ua: navigator.userAgent};
  REPORT(out);
}
run();
</script>"""


def mac_capture():
    import http.server, shutil, subprocess, tempfile, threading, time
    body = PAGE.replace("REPORT(out);", "fetch('/r',{method:'POST',body:JSON.stringify(out)});document.getElementById('o').textContent=JSON.stringify(out);")
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(body.encode())

        def do_POST(self):
            got["r"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(204); self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    ver = subprocess.run([chrome, "--version"], capture_output=True, text=True).stdout.strip()
    prof = tempfile.mkdtemp()
    p = subprocess.Popen([chrome, f"--user-data-dir={prof}", "--no-first-run", "--no-default-browser-check", "--window-size=300,200",
                          "--window-position=2000,2000", f"--app=http://127.0.0.1:{srv.server_port}/"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(300):
        if "r" in got:
            break
        time.sleep(0.1)
    p.terminate(); p.wait(timeout=10); srv.shutdown(); shutil.rmtree(prof, ignore_errors=True)
    return got["r"], ver


def winhost_capture():
    import winhost
    body = PAGE.replace("REPORT(out);", "document.getElementById('o').textContent=JSON.stringify(out);")
    return json.loads(winhost.cdp_eval(body, headed=True, wait_ms=6000)), "host"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--where", choices=["mac", "winhost"], required=True)
    ap.add_argument("--locale", help="winhost: the language pack row this capture measures (e.g. fr-FR)")
    a = ap.parse_args()
    r, ver = mac_capture() if a.where == "mac" else winhost_capture()
    voices = r["voices"]
    print(f"{a.where}: {len(voices)} voices, sampleRate {r['sampleRate']}, baseLatency {r['baseLatency']}, {ver}")
    print("first:", json.dumps(voices[:3]))
    vp = ROOT / "settings" / "voices.json"
    v = json.loads(vp.read_text(encoding="utf-8"))
    if a.where == "mac":
        v["macOS"] = voices
        v.setdefault("measured", []).append("macOS")
    else:
        if not a.locale:
            sys.exit("--locale is required for winhost")
        row = [x for x in voices if x["lang"] == a.locale]
        if not row:
            sys.exit(f"no {a.locale} voices on the host: {[x['name'] for x in voices]}")
        v["Windows"][a.locale] = row
        if a.locale not in v["measured"]:
            v["measured"].append(a.locale)
        print("host row:", json.dumps(row))
    v["measured"] = sorted(set(v["measured"]))
    vp.write_text(json.dumps(v, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    apth = ROOT / "settings" / "audio.json"
    audio = json.loads(apth.read_text(encoding="utf-8")) if apth.exists() else {"$comment": "AudioContext.sampleRate of stock Chrome per host (capture_voices.py); emitted as audio:sampleRate under the claim."}
    audio["macOS" if a.where == "mac" else "Windows"] = {"sampleRate": r["sampleRate"], "baseLatency": r["baseLatency"], "chrome": ver}
    apth.write_text(json.dumps(audio, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

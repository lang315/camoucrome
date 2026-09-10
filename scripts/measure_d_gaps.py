"""Roadmap D "measure first" rows, one pass on chrome through the client probe.

Reports, per condition, what a page sees for the surfaces Camoufox spoofs and
Camoucrome does not:
  css media  color-gamut, dynamic-range, prefers-color-scheme, forced-colors,
             prefers-reduced-motion, pointer, hover, any-pointer, any-hover
  touch      navigator.maxTouchPoints, 'ontouchstart' in window, typeof TouchEvent
  system-ui  which candidate family renders at the same width as `system-ui`
             (canvas measureText), the CSS2 keyword fonts (caption, menu,
             small-caption, status-bar, message-box) as computed family/size and
             the rendered width of one string (what a fingerprinter measures),
             and whether the UI font each OS implies is installed (width with a
             monospace fallback differs from bare monospace; document.fonts.check
             is useless here, it answers true for any never-loaded family).

Conditions: headless stock (no config), headless claiming Windows with a
touch screen (ua:osInfo/platform + maxTouchPoints 5), headed (WSLg). A row
whose value follows the host rather than the claim is a candidate tell; the
doc decides which become keys. Prints one JSON object; nothing is asserted.
"""
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

PAGE = b"""<!doctype html><title>d-gaps</title><pre id="o"></pre>
<span id="k"></span><script>
const mq = q => matchMedia(q).matches;
const pick = (name, vals) => vals.find(v => mq(`(${name}: ${v})`)) || null;
const media = {
  'color-gamut': pick('color-gamut', ['rec2020', 'p3', 'srgb']),
  'dynamic-range': pick('dynamic-range', ['high', 'standard']),
  'prefers-color-scheme': pick('prefers-color-scheme', ['dark', 'light']),
  'forced-colors': pick('forced-colors', ['active', 'none']),
  'prefers-reduced-motion': pick('prefers-reduced-motion', ['reduce', 'no-preference']),
  pointer: pick('pointer', ['fine', 'coarse', 'none']),
  hover: pick('hover', ['hover', 'none']),
  'any-pointer': pick('any-pointer', ['fine', 'coarse', 'none']),
  'any-hover': pick('any-hover', ['hover', 'none']),
};
const touch = {
  maxTouchPoints: navigator.maxTouchPoints,
  ontouchstart: 'ontouchstart' in window,
  TouchEvent: typeof TouchEvent,
};
const ctx = document.createElement('canvas').getContext('2d');
const S = 'The quick brown fox jumps over the lazy dog 0123456789';
const width = f => { ctx.font = `16px ${f}`; return ctx.measureText(S).width; };
const sysW = width('system-ui');
const cands = ['Segoe UI', 'Tahoma', 'Arial', '-apple-system', 'BlinkMacSystemFont', 'Helvetica Neue',
               'Ubuntu', 'Cantarell', 'DejaVu Sans', 'Noto Sans', 'Liberation Sans', 'Roboto',
               'sans-serif', 'serif', 'monospace'];
const widths = Object.fromEntries(cands.map(f => [f, width(`"${f}"`)]));
const k = document.getElementById('k');
const keyword = kw => { k.style.font = kw; k.textContent = S; const cs = getComputedStyle(k); return (k.style.font || '<rejected>') + ' => ' + cs.fontFamily + ' / ' + cs.fontSize + ' / rendered ' + k.getBoundingClientRect().width.toFixed(2) + 'px'; };
const installed = f => width(`"${f}", monospace`) !== width('monospace');
document.getElementById('o').textContent = JSON.stringify({
  media, touch,
  systemUi: {
    width: sysW,
    matches: cands.filter(f => widths[f] === sysW),
    widths,
    keywords: Object.fromEntries(['caption', 'menu', 'small-caption', 'status-bar', 'message-box'].map(kw => [kw, keyword(kw)])),
    installed: Object.fromEntries(['Arial', 'Segoe UI', 'Tahoma', '.AppleSystemUIFont', 'Helvetica Neue', 'Ubuntu', 'Cantarell', 'DejaVu Sans', 'Noto Sans', 'Roboto']
      .map(f => [f, installed(f)])),
  },
  ua: { platform: navigator.platform, ch: navigator.userAgentData && navigator.userAgentData.platform },
});
</script>"""

WIN_TOUCH = {"ua:osInfo": "Windows NT 10.0; Win64; x64", "ua:platform": "Windows",
             "ua:platformVersion": "15.0.0", "navigator.platform": "Win32",
             "navigator.maxTouchPoints": 5}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *a):
        pass


def probe(url, config=None, headed=False):
    env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}
    env["PLAYWRIGHT_NODEJS_PATH"] = NODE
    cmd = [PY, "-m", "camoucrome.probe", "--driver", "patchright", "--executable", EXE, "--url", url]
    if config is not None:
        cmd += ["--config", json.dumps(config)]
    if headed:
        cmd.append("--headed")
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env)
    if p.returncode != 0:
        return {"error": p.stderr[-400:]}
    return json.loads(p.stdout)["report"]


def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"
    conditions = [("headless-stock", None, False), ("headless-win-touch", WIN_TOUCH, False)]
    if os.environ.get("DISPLAY"):
        conditions += [("headed-stock", None, True), ("headed-win-touch", WIN_TOUCH, True)]
    out = {name: probe(url, cfg, headed) for name, cfg, headed in conditions}
    json.dump(out, sys.stdout, indent=1)
    print()
    srv.shutdown()


if __name__ == "__main__":
    main()

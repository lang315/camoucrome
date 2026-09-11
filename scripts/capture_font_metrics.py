#!/usr/bin/env python3
"""Per-character advance widths of the claimed Windows families on the real
host (stock Chrome 153 on the box's Windows 10 host, headless --dump-dom) ->
baselines/chrome-8010-stock-font-metrics-windows.json. 100 px so 1/100 em is
one pixel; canvas advances are linear (unhinted) on DirectWrite and FreeType.
verify_font_metrics.py renders the same page in the fork and compares."""
import html
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "baselines" / "chrome-8010-stock-font-metrics-windows.json"
GRID_FAMILIES = ["Segoe UI", "Arial", "Times New Roman", "Courier New", "Calibri", "Cambria",
                 "Consolas", "Georgia", "Verdana", "Tahoma", "Trebuchet MS", "Segoe UI Variable"]
MAC_FAMILIES = ["Helvetica Neue", "Helvetica", "Arial", "Times New Roman", "Times", "Courier New", "Courier",
                "Georgia", "Verdana", "Tahoma", "Trebuchet MS", "Menlo", "Monaco", "Geneva", "Lucida Grande",
                "Avenir", "Gill Sans", "Palatino", "Baskerville", "-apple-system", "system-ui"]
FAMILIES = {"winhost": GRID_FAMILIES, "mac": MAC_FAMILIES}
OUTS = {"winhost": OUT, "mac": ROOT / "baselines" / "chrome-7922-stock-font-metrics-macos.json"}
CHARS = [chr(c) for c in range(0x20, 0x7F)] + [chr(c) for c in range(0xC0, 0xDE)]
PX = 100


def page(families):
    return ("<!doctype html><title>metrics</title><pre id=\"o\"></pre><script>"
            "const F=%s,C=%s,PX=%d;const ctx=document.createElement('canvas').getContext('2d');"
            "const w=(f,s)=>{ctx.font=PX+'px '+f;return ctx.measureText(s).width};"
            "const out={};for(const f of F){const q=f.startsWith('-')||f==='system-ui'?f:'\"'+f+'\"';"
            "const resolved=w(q+', monospace','The quick brown fox 0123')===w(q+', serif','The quick brown fox 0123');"
            "out[f]={resolved,widths:Object.fromEntries(C.map(c=>[c,w(q,c)]))}}"
            "document.getElementById('o').textContent=JSON.stringify(out).replace(/[\\u0080-\\uffff]/g,c=>'\\\\u'+c.charCodeAt(0).toString(16).padStart(4,'0'));</script>"
            % (json.dumps(families), json.dumps(CHARS), PX))


def parse(dom):
    m = re.search(r'<pre id="o">(.*?)</pre>', dom, re.S)
    return json.loads(html.unescape(m.group(1)))


def mac_capture(families):
    """Stock Chrome on this Mac, headed in a small app window (headless hangs on this Mac):
    the page POSTs its report back to a local server."""
    import http.server, shutil, subprocess, tempfile, threading, time
    body = page(families).replace("document.getElementById('o').textContent=",
                                  "fetch('/r',{method:'POST',body:JSON.stringify(out)});document.getElementById('o').textContent=")
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write(body.encode())

        def do_POST(self):
            got["r"] = json.loads(self.rfile.read(int(self.headers["Content-Length"]))); self.send_response(204); self.end_headers()

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    ver = subprocess.run([chrome, "--version"], capture_output=True, text=True).stdout.strip()
    prof = tempfile.mkdtemp(prefix="camou_metrics_")
    p = subprocess.Popen([chrome, f"--user-data-dir={prof}", "--no-first-run", "--no-default-browser-check", "--window-size=300,200",
                          "--window-position=2000,2000", f"--app=http://127.0.0.1:{srv.server_port}/"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        if "r" in got:
            break
        time.sleep(0.5)
    p.terminate(); p.wait(timeout=10); srv.shutdown(); shutil.rmtree(prof, ignore_errors=True)
    return got["r"], ver


def main():
    where = sys.argv[sys.argv.index("--where") + 1] if "--where" in sys.argv else "winhost"
    if where == "winhost":
        import winhost
        fams = winhost.dump_dom(page(GRID_FAMILIES), args=("--use-gl=angle", "--use-angle=d3d11"))  # dump_dom parses #o
        if isinstance(fams, str):
            fams = parse(fams)
        meta = {"chrome": "153.0.8010.36", "where": "stock Google Chrome on the build box's Windows 10 host (build 19045), headless --dump-dom, temp profile"}
    else:
        fams, ver = mac_capture(MAC_FAMILIES)
        meta = {"chrome": ver, "where": "stock Google Chrome on the Mac (macOS 15.7.4), headed 300x200 app window, temp profile; the page POSTs its report"}
    OUTS[where].write_text(json.dumps({**meta, "px": PX, "families": fams}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print({f: (v["resolved"], round(v["widths"]["a"], 2)) for f, v in fams.items()})


if __name__ == "__main__":
    main()

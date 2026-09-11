"""window.chrome shape + navigator.plugins/mimeTypes/pdfViewerEnabled (SP2 §4.7,
roadmap B1) on the fork's chrome, against baselines/chrome-8010-stock-window-chrome.json
(stock Chrome 153.0.8010.36 on the box's Windows host, headless + headed).

O1 fork headless tree == stock headless tree (recursive: names, kinds,
   descriptor flags, function length/name/toString) -- diff empty.
O2 plugins/mimeTypes/pdfViewerEnabled equal to stock headless.
O3 loadTimes()/csi() key sets equal to stock; csi().pageT >= 0.
O4 RED by construction: the same differ against content_shell (no window.chrome)
   reports a non-empty diff.
Also printed: whether stock headed differs from stock headless (a headless tell
for B7, named, not keyed here).
"""
import base64
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
BASELINE = pathlib.Path(os.environ.get("CAMOU_CHROME_BASELINE", f"{HOME}/camoucrome-client/baselines/chrome-8010-stock-window-chrome.json"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capture_chrome_object import PAGE  # noqa: E402


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        b = PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


def probe(url):
    env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}
    env["PLAYWRIGHT_NODEJS_PATH"] = NODE
    p = subprocess.run([PY, "-m", "camoucrome.probe", "--driver", "patchright", "--executable", EXE, "--url", url],
                       capture_output=True, text=True, timeout=180, env=env)
    if p.returncode != 0:
        sys.exit("probe failed: " + p.stderr[-500:])
    return json.loads(p.stdout)["report"]


def content_shell(url):
    import lib_shell
    values, err = lib_shell.session(None, ["() => JSON.parse(document.getElementById('o').textContent)"], navigate_to=url)
    return None if err else values[0]


def diff(a, b, path="chrome"):
    """Paths where two trees differ (a = fork, b = stock)."""
    out = []
    if a is None or b is None:
        return [f"{path}: {'absent' if a is None else 'present'} vs stock {'absent' if b is None else 'present'}"]
    for k in sorted(set(a) | set(b)):
        if k not in a:
            out.append(f"{path}.{k}: missing in fork")
        elif k not in b:
            out.append(f"{path}.{k}: extra in fork")
        else:
            ea, eb = a[k], b[k]
            for f in ("kind", "enumerable", "configurable", "writable", "length", "name", "str"):
                if ea.get(f) != eb.get(f):
                    out.append(f"{path}.{k}.{f}: {str(ea.get(f))[:60]!r} != {str(eb.get(f))[:60]!r}")
            if "props" in ea or "props" in eb:
                out += diff(ea.get("props"), eb.get("props"), f"{path}.{k}")
    return out


def main():
    base = json.loads(BASELINE.read_text())
    stock = base["headless"]
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"
    fork = probe(url)
    shell = content_shell(url)
    srv.shutdown()
    results, notes = {}, []
    d = diff(fork["tree"], stock["tree"])
    results["O1 window.chrome tree == stock headless (empty diff)"] = fork["typeofChrome"] == "object" and not d
    if d:
        notes.append("O1 diff: " + "; ".join(d[:12]))
    same_plugins = fork["plugins"] == stock["plugins"] and fork["mimeTypes"] == stock["mimeTypes"] and fork["pdfViewerEnabled"] == stock["pdfViewerEnabled"]
    results["O2 plugins/mimeTypes/pdfViewerEnabled == stock headless"] = same_plugins
    if not same_plugins:
        notes.append(f"O2 fork plugins={[p['name'] for p in fork['plugins']]} pdf={fork['pdfViewerEnabled']} stock={[p['name'] for p in stock['plugins']]} pdf={stock['pdfViewerEnabled']}")
    results["O3 loadTimes()/csi() key sets == stock, csi().pageT >= 0"] = (
        fork["loadTimes"].get("keys") == stock["loadTimes"].get("keys") and fork["csi"].get("keys") == stock["csi"].get("keys") and fork["csi"].get("pageT_ge_0") is True)
    red = diff(shell["tree"] if shell else None, stock["tree"])
    results["O4 RED: content_shell (no window.chrome) differs from stock"] = shell is not None and shell["typeofChrome"] == "undefined" and bool(red)
    hd = diff(base["headed"]["tree"], stock["tree"])
    notes.append(f"stock headed vs headless: tree diff {len(hd)} path(s){': ' + '; '.join(hd[:4]) if hd else ''}; plugins {[p['name'] for p in base['headed']['plugins']]} vs {[p['name'] for p in stock['plugins']]}; pdfViewerEnabled {base['headed']['pdfViewerEnabled']} vs {stock['pdfViewerEnabled']}")
    notes.append(f"fork tree top-level {sorted(fork['tree'] or {})}, {sum(1 for _ in json.dumps(fork['tree']).split('\"kind\"')) - 1} properties")
    for k, v in results.items():
        print(("PASS " if v else "FAIL "), k)
    for n in notes:
        print("  " + n[:900])
    n = sum(results.values())
    print(f"{n} PASS {len(results) - n} FAIL")
    sys.exit(0 if n == len(results) else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Fork (Windows claim + bundle) vs the host baseline, per family: fraction of
characters within 0.5 px at 100 px, max |diff|, mean signed diff.

M1 control: Arial / Times New Roman / Courier New >= 0.98 (Liberation is
   metric-compatible by design; below that the harness measures rendering, not fonts).
M2 Calibri (Carlito) >= 0.98; M2b Cambria (Caladea) numbers only (its Google Fonts build
   differs on digits/capitals, measured). M3 Georgia (Gelasio) >= 0.98.
M4 Tahoma (Wine) and M5 Segoe UI (Selawik): approximate clones, every char within 2 px.
M6 Verdana / Trebuchet MS / Consolas: numbers only (no clone exists)."""
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
FONTS = json.loads((CLIENT / "settings" / "fonts.json").read_text(encoding="utf-8"))
BASE = json.loads((CLIENT / "baselines" / "chrome-8010-stock-font-metrics-windows.json").read_text(encoding="utf-8"))
sys.path.insert(0, str(CLIENT / "scripts"))
import capture_font_metrics as cap  # noqa: E402

WIN = {"ua:osInfo": "Windows NT 10.0; Win64; x64", "ua:platform": "Windows", "ua:platformVersion": "10.0.0", "navigator.platform": "Win32"}
# (families, min fraction within 0.5 px, max |diff| px). Exact clones: 0.98 / 0.6.
# Approximate clones (Selawik for Segoe UI, Wine Tahoma): every character within 2 px
# at 100 px (2 % of em) -- measured 2026-09-11 at 1.1 / 1.6 px; the threshold names
# what they are, it does not make them exact.
THRESH = {"M1 control (Liberation)": (["Arial", "Times New Roman", "Courier New"], 0.98, 0.6),
          "M2 Carlito": (["Calibri"], 0.98, 0.6),
          "M3 Gelasio": (["Georgia"], 0.98, 0.6),
          "M4 Wine Tahoma (approximate)": (["Tahoma"], 0.5, 2.0),
          "M5 Selawik (approximate)": (["Segoe UI"], 0.5, 2.0)}
# Numbers only: Cambria's Google-Fonts Caladea build differs on digits and capitals
# (measured within 0.36, max 19.4 px); no clone exists for the M6 three.
REPORT = {"M2b Caladea": ["Cambria"], "M6 no clone": ["Verdana", "Trebuchet MS", "Consolas"], "host-absent": ["Segoe UI Variable"]}


class H(http.server.BaseHTTPRequestHandler):
    body = b""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(H.body)

    def log_message(self, *a):
        pass


def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    H.body = cap.page(cap.GRID_FAMILIES).encode()
    env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}
    env["PLAYWRIGHT_NODEJS_PATH"] = NODE
    cfg = {**WIN, "fonts:list": FONTS["families"]["Windows"]["list"] + FONTS["extra_allowed"]["Windows"],
           "fonts:alias": FONTS["alias_map"]["Windows"]}
    p = subprocess.run([PY, "-m", "camoucrome.probe", "--driver", "patchright", "--executable", EXE,
                        "--url", f"http://127.0.0.1:{srv.server_port}/", "--config", json.dumps(cfg), "--fonts-dir", FONTS_DIR],
                       capture_output=True, text=True, timeout=180, env=env)
    srv.shutdown()
    if p.returncode != 0:
        sys.exit(p.stderr[-600:])
    fork = json.loads(p.stdout)["report"]
    stats = {}
    for fam, host in BASE["families"].items():
        if not host["resolved"]:
            stats[fam] = None
            continue
        d = [fork[fam]["widths"][c] - host["widths"][c] for c in host["widths"]]
        stats[fam] = {"n": len(d), "within": sum(abs(x) <= 0.5 for x in d) / len(d),
                      "max": max(abs(x) for x in d), "mean": sum(d) / len(d), "resolved": fork[fam]["resolved"]}
    results = {}
    for row, (fams, th, mx) in THRESH.items():
        label = f"{row}: " + ", ".join(f"{f} within={stats[f]['within']:.3f} max={stats[f]['max']:.1f}px" if stats[f] else f"{f} unresolved on host" for f in fams)
        results[label] = all(stats[f] and stats[f]["resolved"] and stats[f]["within"] >= th and stats[f]["max"] <= mx for f in fams)
    for fam in [a[len("--detail="):] for a in sys.argv if a.startswith("--detail=")]:
        host = BASE["families"][fam]["widths"]
        print("detail:", fam, {c: round(fork[fam]["widths"][c] - host[c], 2) for c in host if abs(fork[fam]["widths"][c] - host[c]) > 0.5})
    for row, fams in REPORT.items():
        print("note:", row, {f: (stats[f] and {k: round(v, 3) for k, v in stats[f].items() if k != "n"}) for f in fams})
    for k, v in results.items():
        print("PASS " if v else "FAIL ", k)
    n = sum(results.values())
    print(f"{n} PASS {len(results) - n} FAIL")
    sys.exit(0 if n == len(results) else 1)


if __name__ == "__main__":
    main()

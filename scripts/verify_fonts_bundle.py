"""Font bundle + fontconfig alias layer (spec 2026-09-11 §1) on chrome through
the client probe. Width test only: document.fonts.check answers true for any
never-loaded family (measured 2026-09-11).

F1 RED (no --fonts-dir, no config): "Segoe UI" does not resolve (its width
   follows the fallback: monospace vs serif differ), "DejaVu Sans" does.
F2 --fonts-dir + Windows claim + the Windows fonts:list: every listed family
   resolves; DejaVu Sans / Ubuntu / Cantarell do not; system-ui, Selawik and
   Segoe UI render the string at one width; `font: caption` renders at it too.
F3 --fonts-dir + macOS claim + the macOS list: every listed family resolves;
   system-ui == Inter Variable == -apple-system.
F4 gen.py --os windows: its fonts:list is a subset of what F2 measured as
   resolving (page-measured, not table-asserted).
F5 (CAMOU_EXE = an extracted archive's chrome, no --fonts-dir): the launcher
   finds fonts/ beside the executable; the F2 rows pass.
"""
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

WIN = {"ua:osInfo": "Windows NT 10.0; Win64; x64", "ua:platform": "Windows", "ua:platformVersion": "15.0.0", "navigator.platform": "Win32"}
MAC = {"ua:osInfo": "Macintosh; Intel Mac OS X 10_15_7", "ua:platform": "macOS", "ua:platformVersion": "14.6.1", "navigator.platform": "MacIntel"}
HOST_ONLY = ["DejaVu Sans", "Ubuntu", "Cantarell"]
SPECIAL = ["system-ui", "Selawik", "Segoe UI", "Inter Variable", "-apple-system", "sans-serif"]


def page(families):
    return ("""<!doctype html><title>fonts</title><pre id="o"></pre><span id="k"></span><script>
const FAM = %s;
const ctx = document.createElement('canvas').getContext('2d');
const S = 'The quick brown fox jumps over the lazy dog 0123456789 àéîõü';
const width = f => { ctx.font = `16px ${f}`; return ctx.measureText(S).width; };
const mono = width('monospace');
// A resolvable family renders at its own width whatever the fallback; an unresolvable one
// renders as the fallback, so its width changes with it (monospace vs serif).
const resolves = Object.fromEntries(FAM.map(f => [f, width(`"${f}", monospace`) === width(`"${f}", serif`)]));
const widths = Object.fromEntries(%s.map(f => [f, width(f.startsWith('-') || f === 'system-ui' || f === 'sans-serif' ? f : `"${f}"`)]));
const k = document.getElementById('k'); k.style.font = 'caption'; k.textContent = S;
document.getElementById('o').textContent = JSON.stringify({ resolves, widths, caption: k.getBoundingClientRect().width, mono });
</script>""" % (json.dumps(families), json.dumps(SPECIAL))).encode()


class H(http.server.BaseHTTPRequestHandler):
    body = b""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(H.body)))
        self.end_headers()
        self.wfile.write(H.body)

    def log_message(self, *a):
        pass


def probe(url, config=None, fonts_dir=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}
    env["PLAYWRIGHT_NODEJS_PATH"] = NODE
    cmd = [PY, "-m", "camoucrome.probe", "--driver", "patchright", "--executable", EXE, "--url", url]
    if config is not None:
        cmd += ["--config", json.dumps(config)]
    if fonts_dir:
        cmd += ["--fonts-dir", fonts_dir]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env)
    if p.returncode != 0:
        sys.exit(f"probe failed: {p.stderr[-600:]}")
    return json.loads(p.stdout)["report"]


def same(w, *names):
    vals = [round(w[n], 2) for n in names]
    return len(set(vals)) == 1


def main():
    results, notes = {}, []
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"
    win_list, mac_list = FONTS["families"]["Windows"]["list"], FONTS["families"]["macOS"]["list"]
    archive = os.environ.get("CAMOU_ARCHIVE_MODE") == "1"  # F5: no --fonts-dir, the launcher must find fonts/ beside EXE
    fd = None if archive else FONTS_DIR

    H.body = page(["Segoe UI", "DejaVu Sans"])
    r = probe(url)
    results["F1 RED no bundle: Segoe UI unresolvable, DejaVu Sans resolves"] = (
        r["resolves"]["Segoe UI"] is False and r["resolves"]["DejaVu Sans"] is True)

    H.body = page(win_list + HOST_ONLY)
    r = probe(url, {**WIN, "fonts:list": win_list, "fonts:alias": FONTS["alias_map"]["Windows"]}, fd)
    missing = [f for f in win_list if not r["resolves"][f]]
    leaked = [f for f in HOST_ONLY if r["resolves"][f]]
    w = r["widths"]
    results[f"F2 Windows claim + bundle: all {len(win_list)} listed families resolve, host-only hidden, system-ui == Selawik == Segoe UI, caption at that width"] = (
        not missing and not leaked and same(w, "system-ui", "Selawik", "Segoe UI") and round(r["caption"], 1) == round(w["Selawik"], 1))
    if missing or leaked or not same(w, "system-ui", "Selawik", "Segoe UI"):
        notes.append(f"F2 missing={missing[:8]} leaked={leaked} widths={ {k: round(v, 2) for k, v in w.items()} } caption={r['caption']:.2f}")
    resolving = {f for f in win_list if r["resolves"][f]}

    H.body = page(mac_list + HOST_ONLY)
    r = probe(url, {**MAC, "fonts:list": mac_list, "fonts:alias": FONTS["alias_map"]["macOS"]}, fd)
    missing = [f for f in mac_list if not r["resolves"][f]]
    leaked = [f for f in HOST_ONLY if r["resolves"][f]]
    w = r["widths"]
    results[f"F3 macOS claim + bundle: all {len(mac_list)} listed families resolve, host-only hidden, system-ui == Inter Variable == -apple-system"] = (
        not missing and not leaked and same(w, "system-ui", "Inter Variable", "-apple-system"))
    if missing or leaked or not same(w, "system-ui", "Inter Variable", "-apple-system"):
        notes.append(f"F3 missing={missing[:8]} leaked={leaked} widths={ {k: round(v, 2) for k, v in w.items()} }")

    gen = subprocess.run([PY, "-m", "camoucrome.gen", "--os", "windows", "--timezone", "UTC", "--seed", "1"],
                         capture_output=True, text=True, timeout=120)
    emitted = json.loads(gen.stdout)["config"].get("fonts:list", []) if gen.returncode == 0 else None
    results["F4 gen.py --os windows emits a fonts:list that F2 measured as resolving"] = (
        bool(emitted) and set(emitted) <= resolving)
    if not emitted:
        notes.append("F4 gen: " + gen.stderr[-300:])
    srv.shutdown()
    for k, v in results.items():
        print(("PASS " if v else "FAIL "), k)
    for n in notes:
        print("  " + n[:700])
    n = sum(results.values())
    print(f"{n} PASS {len(results) - n} FAIL")
    sys.exit(0 if n == len(results) else 1)


if __name__ == "__main__":
    main()

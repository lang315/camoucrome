"""WebGL profile database (spec 2026-09-11 §3) on chrome through the client probe.

W1 RED-by-construction: no config -> the host's SwiftShader renderer and limits.
W2 Windows profile on a Windows claim: vendor/renderer read back on both
   contexts; every emitted numeric parameter equal; extension list equal as a
   set AND getExtension(name) non-null for every claimed name; all 12
   shader precision cells equal; strict start, zero camoucfg: lines.
W3 macOS profile on a macOS claim: same; W3-RED: the macOS profile on a
   Windows claim is refused under strict (webgl-renderer-backend-fits-os).
W4 informational: shaderPrecisionFormats / contextAttributes host vs profile
   diff count per context (8/12 precision cells differ on the SwiftShader
   host: the reason the generator emits them; contextAttributes agree).
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
WEBGL_DIR = pathlib.Path(os.environ.get("CAMOU_WEBGL_DIR", f"{HOME}/camoucrome-client/settings/webgl"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capture_webgl_profile import PAGE  # noqa: E402  the same page: what a profile captures is what a page reads

WIN = {"ua:osInfo": "Windows NT 10.0; Win64; x64", "ua:platform": "Windows", "ua:platformVersion": "15.0.0", "navigator.platform": "Win32"}
MAC = {"ua:osInfo": "Macintosh; Intel Mac OS X 10_15_7", "ua:platform": "macOS", "ua:platformVersion": "14.6.1", "navigator.platform": "MacIntel"}


def keys_of(p):
    return {"webGl:vendor": p["vendor"], "webGl:renderer": p["renderer"], "webGl2:vendor": p["vendor"],
            "webGl2:renderer": p["renderer"], "webGl:parameters": p["webgl"]["parameters"],
            "webGl2:parameters": p["webgl2"]["parameters"], "webGl:supportedExtensions": p["webgl"]["supportedExtensions"],
            "webGl2:supportedExtensions": p["webgl2"]["supportedExtensions"],
            "webGl:shaderPrecisionFormats": precision(p["webgl"]["shaderPrecisionFormats"]),
            "webGl2:shaderPrecisionFormats": precision(p["webgl2"]["shaderPrecisionFormats"])}


GL_ENUM = {"VERTEX_SHADER": 35633, "FRAGMENT_SHADER": 35632, "LOW_FLOAT": 36336, "MEDIUM_FLOAT": 36337,
           "HIGH_FLOAT": 36338, "LOW_INT": 36339, "MEDIUM_INT": 36340, "HIGH_INT": 36341}


def precision(spf):
    return {f"{GL_ENUM[s]}:{GL_ENUM[p]}": v for (s, p), v in ((k.split("/"), v) for k, v in spf.items())}


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


def probe(url, config=None, strict=False):
    env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}
    env["PLAYWRIGHT_NODEJS_PATH"] = NODE
    cmd = [PY, "-m", "camoucrome.probe", "--driver", "patchright", "--executable", EXE, "--url", url]
    if config is not None:
        cmd += ["--config", json.dumps(config)]
    if strict:
        cmd.append("--strict")
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env)
    rep = json.loads(p.stdout)["report"] if p.returncode == 0 else None
    return rep, p.stderr


def matches(rep, profile, ctx, notes, tag):
    r, want = rep[ctx], profile[ctx]
    if r is None:
        notes.append(f"{tag}/{ctx}: no context")
        return False
    bad = [k for k, v in want["parameters"].items() if r["parameters"].get(k) != v]
    extdiff = sorted(set(r["supportedExtensions"]) ^ set(want["supportedExtensions"]))
    extnull = [e for e in want["supportedExtensions"] if not r["extOk"].get(e)]
    badspf = [k for k, v in want["shaderPrecisionFormats"].items() if r["shaderPrecisionFormats"].get(k) != v]
    ok = (r["vendor"] == profile["vendor"] and r["renderer"] == profile["renderer"]
          and not bad and not extdiff and not extnull and not badspf)
    if not ok:
        notes.append(f"{tag}/{ctx}: renderer={r['renderer'][:60]!r} badparams={bad[:6]} extdiff={extdiff[:6]} extnull={extnull[:6]} badspf={badspf[:4]}")
    return ok


def main():
    results, notes = {}, []
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"
    win = json.loads((WEBGL_DIR / "windows-intel-uhd-630-d3d11.json").read_text())
    mac = json.loads((WEBGL_DIR / "macos-apple-m1-pro-metal.json").read_text())
    host, log = probe(url)
    results["W1 no config: host SwiftShader renderer and limits"] = (
        host is not None and "SwiftShader" in host["webgl"]["renderer"]
        and host["webgl"]["parameters"] != win["webgl"]["parameters"])
    if host is None:
        notes.append("W1 launch: " + log[-300:])
    rep, log = probe(url, {**WIN, **keys_of(win)}, strict=True)
    results["W2 Windows profile: identity, every parameter, extension set + getExtension non-null, 12 precision cells, both contexts, strict, zero camoucfg lines"] = (
        rep is not None and matches(rep, win, "webgl", notes, "W2") and matches(rep, win, "webgl2", notes, "W2")
        and "camoucfg:" not in log)
    if rep is None:
        notes.append("W2 launch: " + log[-400:])
    elif "camoucfg:" in log:
        notes.append("W2 log: " + [l for l in log.splitlines() if "camoucfg:" in l][0][:200])
    rep, log = probe(url, {**MAC, **keys_of(mac)}, strict=True)
    results["W3 macOS profile on a macOS claim: same"] = (
        rep is not None and matches(rep, mac, "webgl", notes, "W3") and matches(rep, mac, "webgl2", notes, "W3")
        and "camoucfg:" not in log)
    if rep is None:
        notes.append("W3 launch: " + log[-400:])
    red, log = probe(url, {**WIN, **keys_of(mac)}, strict=True)
    results["W3-RED macOS profile on a Windows claim refused under strict (webgl-renderer-backend-fits-os)"] = (
        red is None and "webgl-renderer-backend-fits-os" in log)
    if rep and host:
        for ctx in ("webgl", "webgl2"):
            d1 = sum(1 for k, v in mac[ctx]["shaderPrecisionFormats"].items() if host[ctx]["shaderPrecisionFormats"].get(k) != v)
            d2 = sum(1 for k, v in mac[ctx]["contextAttributes"].items() if host[ctx]["contextAttributes"].get(k) != v)
            e1 = sum(1 for k, v in win[ctx]["shaderPrecisionFormats"].items() if host[ctx]["shaderPrecisionFormats"].get(k) != v)
            notes.append(f"W4 {ctx}: host vs macOS profile: shaderPrecisionFormats differ in {d1}/12 cells, contextAttributes in {d2}; host vs Windows profile: {e1}/12 cells (why the generator emits webGl:shaderPrecisionFormats; contextAttributes agree, not emitted)")
    srv.shutdown()
    for k, v in results.items():
        print(("PASS " if v else "FAIL "), k)
    for n in notes:
        print("  " + n)
    n = sum(results.values())
    print(f"{n} PASS {len(results) - n} FAIL")
    sys.exit(0 if n == len(results) else 1)


if __name__ == "__main__":
    main()

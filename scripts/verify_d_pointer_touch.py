"""D gaps, the two tells (measurements/2026-09-11-d-gaps.md §2), on chrome
through the client probe. Each row is one launch; the derived values have no
key of their own -- they follow the claimed OS and navigator.maxTouchPoints.

V1 no config: the host's values (headless Linux: pointer none, no
   ontouchstart) -- rule 5, and the proof V2 changes something.
V2 Windows claim, no touch: pointer fine, hover hover, any-pointer fine and
   not coarse, any-hover hover; ontouchstart still absent; Object.keys(window)
   identical to V1 (no claim adds a key).
V3 Windows claim + maxTouchPoints 5: pointer fine, any-pointer fine AND
   coarse, hover hover; 'ontouchstart' in window; Object.keys(window) equals
   the stock touch build (V5) -- rule 2 for the claimed device.
V4 Android claim: pointer coarse, hover none, any-hover none.
V5 baseline for V3: no config, --touch-events=enabled (stock's own touch
   switch): ontouchstart present; its window keys are what V3 must match.
RED: on a tree without the derivation V2 reports pointer none (measured
2026-09-11 before the patch: every row said none/none/none/none).
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

PAGE = b"""<!doctype html><title>pointer-touch</title><pre id="o"></pre><script>
const mq = q => matchMedia(q).matches;
document.getElementById('o').textContent = JSON.stringify({
  pointer: ['fine', 'coarse', 'none'].find(v => mq(`(pointer: ${v})`)) || null,
  hover: ['hover', 'none'].find(v => mq(`(hover: ${v})`)) || null,
  anyFine: mq('(any-pointer: fine)'), anyCoarse: mq('(any-pointer: coarse)'), anyNone: mq('(any-pointer: none)'),
  anyHover: mq('(any-hover: hover)'),
  maxTouchPoints: navigator.maxTouchPoints,
  ontouchstart: 'ontouchstart' in window,
  keys: Object.keys(window),
});
</script>"""

WIN = {"ua:osInfo": "Windows NT 10.0; Win64; x64", "ua:platform": "Windows",
       "ua:platformVersion": "15.0.0", "navigator.platform": "Win32"}
WIN_TOUCH = {**WIN, "navigator.maxTouchPoints": 5}
ANDROID = {"ua:osInfo": "Linux; Android 14; Pixel 8", "ua:platform": "Android",
           "ua:platformVersion": "14.0.0", "navigator.platform": "Linux armv8l",
           "ua:mobile": True, "navigator.maxTouchPoints": 5}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *a):
        pass


def probe(url, config=None, extra=()):
    env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}
    env["PLAYWRIGHT_NODEJS_PATH"] = NODE
    cmd = [PY, "-m", "camoucrome.probe", "--driver", "patchright", "--executable", EXE, "--url", url]
    if config is not None:
        cmd += ["--config", json.dumps(config)]
    for a in extra:
        cmd.append(f"--arg={a}")  # the value itself starts with "--"
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env)
    if p.returncode != 0:
        sys.exit(f"probe failed: {p.stderr[-600:]}")
    return json.loads(p.stdout)["report"]


def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"
    v1, v2, v3, v4 = probe(url), probe(url, WIN), probe(url, WIN_TOUCH), probe(url, ANDROID)
    v5 = probe(url, extra=["--touch-events=enabled"])
    srv.shutdown()
    brief = lambda r: {k: r[k] for k in r if k != "keys"}
    results = {
        "V1 no config: host values, and V2 differs from them":
            v1["ontouchstart"] is False and brief(v1) != brief(v2),
        "V2 Windows claim: fine/hover, any-pointer fine not coarse, no ontouchstart, keys == V1":
            (v2["pointer"], v2["hover"], v2["anyFine"], v2["anyCoarse"], v2["anyNone"], v2["anyHover"])
            == ("fine", "hover", True, False, False, True)
            and v2["ontouchstart"] is False and v2["keys"] == v1["keys"],
        "V3 Windows + maxTouchPoints 5: fine, any-pointer fine and coarse, ontouchstart, keys == stock touch build":
            (v3["pointer"], v3["hover"], v3["anyFine"], v3["anyCoarse"], v3["anyHover"], v3["maxTouchPoints"])
            == ("fine", "hover", True, True, True, 5)
            and v3["ontouchstart"] is True and v3["keys"] == v5["keys"],
        "V4 Android claim: coarse, hover none, any-hover none":
            (v4["pointer"], v4["hover"], v4["anyHover"], v4["anyCoarse"]) == ("coarse", "none", False, True),
        "V5 --touch-events=enabled stock switch: ontouchstart present, keys differ from V1 by the touch handlers":
            v5["ontouchstart"] is True and set(v5["keys"]) - set(v1["keys"]) == {"ontouchstart", "ontouchmove", "ontouchend", "ontouchcancel"},
    }
    for name, ok in results.items():
        print(("PASS" if ok else "FAIL"), name)
    for tag, r in (("V1", v1), ("V2", v2), ("V3", v3), ("V4", v4), ("V5", v5)):
        print(f"  {tag} {json.dumps(brief(r))} keys={len(r['keys'])}")
    n = sum(results.values())
    print(f"{n} PASS {len(results) - n} FAIL")
    sys.exit(0 if n == len(results) else 1)


if __name__ == "__main__":
    main()

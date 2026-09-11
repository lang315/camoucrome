#!/usr/bin/env python3
"""The fork under a generated Windows identity vs stock Chrome 153 on the
Windows host (baselines/chrome-8010-stock-oracle-windows.json): the same
page (capture_host_oracle.page), every difference printed as one line.
Hardware- and config-bound values (screen, cores, memory, dpr, timezone,
languages, storage quota, heap limit, audio latency, device ids, canvas
hashes, GPU adapter strings) are compared only for *shape* unless a key is
named in EXACT. Exit 0 iff no line is printed outside the ignore set; the
point is the list, which the measurement doc turns into a backlog.

CAMOU_SEED picks the generated identity (default 1); --config <json> replaces it."""
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
sys.path.insert(0, str(CLIENT / "scripts"))
import capture_host_oracle as cap  # noqa: E402

BASE = json.loads((CLIENT / "baselines" / "chrome-8010-stock-oracle-windows.json").read_text(encoding="utf-8"))["headed"]
# Values that legitimately follow the identity or the machine: compare type only.
SHAPE_ONLY = {"nav.hardwareConcurrency", "nav.deviceMemory", "nav.language", "nav.languages", "screen.width", "screen.height", "screen.availWidth",
              "screen.availHeight", "screen.availLeft", "screen.availTop", "win.dpr", "win.screenX", "win.screenY", "win.outerMinusInnerW",
              "win.outerMinusInnerH", "intl.dtf.timeZone", "intl.dtf.locale", "intl.nf.locale", "intl.collator", "intl.date0", "storage.quotaGiB",
              "storage.usage", "perfMem.jsHeapSizeLimit", "audio.baseLatency", "audio.outputLatency", "audioFp", "canvas.text", "canvas.shape",
              "gpu.info.description", "gpu.info.device", "gpu.info.vendor", "gpu.info.architecture", "gpu.limits.maxBufferSize",
              "gpu.limits.maxStorageBufferBindingSize", "gpu.features", "mediaDevices", "voices", "err.stack", "uadHigh.uaFullVersion",
              "uadHigh.fullVersionList", "uad.brands", "navConnection.rtt", "navConnection.downlink", "media.(color-gamut: p3)",
              "media.(dynamic-range: high)", "media.(video-dynamic-range: high)", "media.(prefers-color-scheme: dark)", "keyboard.size"}


class H(http.server.BaseHTTPRequestHandler):
    body = b""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(H.body)

    def log_message(self, *a):
        pass


def flatten(v, prefix=""):
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            out.update(flatten(x, f"{prefix}.{k}" if prefix else k))
        return out
    return {prefix: v}


def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    H.body = cap.page().encode()
    env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}
    env["PLAYWRIGHT_NODEJS_PATH"] = NODE
    if "--config" in sys.argv:
        cfg = json.loads(sys.argv[sys.argv.index("--config") + 1])
    else:
        g = subprocess.run([PY, "-m", "camoucrome.gen", "--os", "windows", "--seed", os.environ.get("CAMOU_SEED", "1")], capture_output=True, text=True, timeout=120)
        if g.returncode != 0:
            sys.exit(g.stderr[-500:])
        cfg = json.loads(g.stdout)["config"]
    p = subprocess.run([PY, "-m", "camoucrome.probe", "--driver", "patchright", "--executable", EXE, "--url", f"http://127.0.0.1:{srv.server_port}/",
                        "--config", json.dumps(cfg), "--fonts-dir", FONTS_DIR, "--arg=--use-gl=angle", "--arg=--use-angle=swiftshader"],
                       capture_output=True, text=True, timeout=240, env=env)
    srv.shutdown()
    if p.returncode != 0:
        sys.exit(p.stderr[-800:])
    fork = json.loads(p.stdout)["report"]
    for key in ("windowKeys", "navProto", "windowNames"):  # lists: print the set difference, then compare as sets
        h, f = set(BASE.get(key) or []), set(fork.get(key) or [])
        if h != f:
            print(f"DIFF {key}: host-only={sorted(h - f)} fork-only={sorted(f - h)}")
        BASE[key], fork[key] = sorted(h), sorted(f)
    host_f, fork_f = flatten(BASE), flatten(fork)
    diffs = []
    for k in sorted(set(host_f) | set(fork_f)):
        h, f = host_f.get(k, "<absent>"), fork_f.get(k, "<absent>")
        if any(k == s or k.startswith(s + ".") for s in SHAPE_ONLY):
            if type(h) != type(f):
                diffs.append((k, f"type {type(h).__name__}", f"type {type(f).__name__}"))
            continue
        if h != f:
            diffs.append((k, h, f))
    print("note: voices host=", json.dumps(BASE.get("voices"))[:300], "fork=", json.dumps(fork.get("voices"))[:300])
    print("note: audioFp host=", BASE.get("audioFp"), "fork=", fork.get("audioFp"), "| canvas host=", BASE.get("canvas"), "fork=", fork.get("canvas"))
    same = len(set(host_f) | set(fork_f)) - len(diffs)
    for k, h, f in diffs:
        print(f"DIFF {k}: host={json.dumps(h)[:160]} fork={json.dumps(f)[:160]}")
    print(f"{len(diffs)} DIFF, {same} same leaves; fork done={fork.get('done')} pageError={fork.get('pageError')}")
    sys.exit(0 if not diffs else 1)


if __name__ == "__main__":
    main()

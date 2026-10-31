#!/usr/bin/env python3
"""The page-blind gate for one approach-B flag (spec 2026-10-31-fb-light-b-design.md section 3.2, local).

The fork under one generated Windows identity loads capture_host_oracle.page three times: twice without the flag,
once with it. A leaf that differs between the two flag-less captures is noise: it is skipped and listed. Any other
leaf where the flagged capture differs is a DIFF line. Exit 0: no DIFF. Exit 1: DIFF lines. Exit 3: UNMEASURED (the
identity or a capture failed). Runs on the Windows host in the owner's session through run-interactive.ps1, because
session 0 crashes the GPU process (S4). RED: --flag=--js-flags=--max-old-space-size=512 fails on perfMem.jsHeapSizeLimit."""
import argparse
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading

from lib_shell import CHROME as EXE, layout

HOME, PY, NODE, CLIENT, FONTS_DIR = layout()

sys.path.insert(0, str(CLIENT / "scripts"))
import capture_host_oracle as cap  # noqa: E402
from oracle_rules import flatten  # noqa: E402

ABSENT = "<absent>"


def leaf_diff(base1, base2, flagged):
    """(noise, lines). noise: leaves that differ between the two flag-less captures, sorted. lines: (leaf, without,
    with) for every other leaf where the flagged capture differs from the first, sorted; a missing leaf reads ABSENT."""
    a, b, f = flatten(base1), flatten(base2), flatten(flagged)
    keys = set(a) | set(b) | set(f)
    noise = sorted(k for k in keys if a.get(k, ABSENT) != b.get(k, ABSENT))
    lines = [(k, a.get(k, ABSENT), f.get(k, ABSENT)) for k in sorted(keys - set(noise))
             if a.get(k, ABSENT) != f.get(k, ABSENT)]
    return noise, lines


class H(http.server.BaseHTTPRequestHandler):
    body = b""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *a):
        pass


def capture(cfg_path, port, env, flag=None):
    """One probe run of the oracle page; the report dict, or None when the probe failed."""
    argv = [PY, "-m", "camoucrome.probe", "--driver", "patchright", "--executable", EXE, "--url", f"http://127.0.0.1:{port}/",
            "--config", "@" + cfg_path, "--fonts-dir", FONTS_DIR, "--arg=--use-gl=angle", "--arg=--use-angle=swiftshader"]
    if flag:
        argv.append("--arg=" + flag)
    p = subprocess.run(argv, capture_output=True, text=True, timeout=240, env=env)
    if p.returncode != 0:
        print(p.stderr[-400:], file=sys.stderr)
        return None
    return json.loads(p.stdout)["report"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--flag", required=True)
    ap.add_argument("--seed", type=int, default=1)
    x = ap.parse_args(argv)
    if os.name == "nt":
        import gpu_gate  # lazy, as in verify_host_oracle.py
        gpu_gate.require_interactive()
    g = subprocess.run([PY, "-m", "camoucrome.gen", "--os", "windows", "--seed", str(x.seed), "--gpu", "windows-intel-uhd-630-d3d11"],
                       capture_output=True, text=True, timeout=120)
    if g.returncode != 0:
        print("UNMEASURED light flag: gen failed")
        return 3
    cfg = json.loads(g.stdout)["config"]
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    H.body = cap.page().encode()
    env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}
    env["PLAYWRIGHT_NODEJS_PATH"] = NODE
    # by path: a generated Windows identity is ~37 KB, over CreateProcess's command-line cap
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(cfg, f)
    try:
        reps = [capture(f.name, srv.server_port, env), capture(f.name, srv.server_port, env),
                capture(f.name, srv.server_port, env, x.flag)]
    finally:
        srv.shutdown()
        os.unlink(f.name)
    if any(r is None for r in reps):
        print("UNMEASURED light flag: a capture failed")
        return 3
    noise, lines = leaf_diff(*reps)
    for k in noise:
        print(f"NOISE {k}")
    for k, a, b in lines:
        print(f"DIFF {k}: without={json.dumps(a)[:160]} with={json.dumps(b)[:160]}")
    print(f"LIGHTGATE {x.flag} {'PASS' if not lines else 'FAIL'} diff={len(lines)} noise={len(noise)}")
    return 0 if not lines else 1


if __name__ == "__main__":
    sys.exit(main())

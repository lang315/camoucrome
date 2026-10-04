#!/usr/bin/env python3
"""The fork under a generated Windows identity vs stock Chrome 154 on the
Windows host (baselines/chrome-8037-stock-oracle-windows.json): the same
page (capture_host_oracle.page), every difference printed as one line.
Hardware- and config-bound values (screen, cores, memory, dpr, timezone,
languages, storage quota, heap limit, audio latency, device ids, canvas
hashes, GPU adapter strings) are compared only for *shape* unless a key is
named in EXACT. Exit 0 iff no line is printed outside the ignore set; the
point is the list, which the measurement doc turns into a backlog.

CAMOU_SEED picks the generated identity (default 1); --config <json> replaces it."""
import contextlib
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

BASE = json.loads((CLIENT / "baselines" / "chrome-8037-stock-oracle-windows.json").read_text(encoding="utf-8"))["headed"]
# Values that legitimately follow the identity or the machine: compare type only.
SHAPE_ONLY = {"nav.hardwareConcurrency", "nav.deviceMemory", "nav.language", "nav.languages", "screen.width", "screen.height", "screen.availWidth",
              "screen.availHeight", "screen.availLeft", "screen.availTop", "win.dpr", "win.screenX", "win.screenY", "win.outerMinusInnerW",
              "win.outerMinusInnerH", "intl.dtf.timeZone", "intl.dtf.locale", "intl.nf.locale", "intl.collator", "intl.date0", "storage.quotaGiB",
              "storage.usage", "perfMem.jsHeapSizeLimit", "audio.baseLatency", "audio.outputLatency", "audioFp", "canvas.text", "canvas.shape",
              "gpu.info.description", "gpu.info.device", "gpu.info.vendor", "gpu.info.architecture", "gpu.limits.maxBufferSize",
              "gpu.limits.maxStorageBufferBindingSize", "gpu.features", "mediaDevices", "voices", "err.stack", "uadHigh.uaFullVersion",
              "uadHigh.fullVersionList", "uad.brands", "navConnection.rtt", "navConnection.downlink", "media.(color-gamut: p3)",
              "media.(dynamic-range: high)", "media.(video-dynamic-range: high)", "media.(prefers-color-scheme: dark)", "keyboard.size"}
HEVC = 'video/mp4; codecs="hev1.1.6.L93.B0"'
# Leaves excluded from O1 with the reason each carries (printed as "known:" lines, never as DIFF). A value is either a
# bare reason -- for a row whose evidence is the committed baseline itself, so a recapture is what retires it -- or
# (reason, predicate-on-the-fork's-report) for a row excused by something that can change under us.
KNOWN = {
    # The host is a headless PC with no mouse or keyboard attached: it reports pointer none / hover none and an empty
    # layout map. A desktop with input reports fine / hover, which d-pointer-touch derives for a Windows claim.
    "media.(pointer: fine)": "host has no mouse", "media.(pointer: none)": "host has no mouse", "media.(hover: hover)": "host has no mouse",
    "media.(any-pointer: fine)": "host has no mouse", "media.(any-hover: hover)": "host has no mouse",
    "keyboard.KeyA": "host has no keyboard", "keyboard.KeyQ": "host has no keyboard", "keyboard.Backquote": "host has no keyboard", "keyboard.Digit1": "host has no keyboard",
    # The probe's own init-script marker (patchright's add_init_script lands in the main world; verify_sp6b_driver excludes it too).
    "windowKeys": "probe marker __camou_init", "windowNames": "probe marker __camou_init", "protoCounts.Window": "probe marker __camou_init (+1)",
    # The host plays HEVC through the OS decoder; the WSL build box has none. This leaf is the PAIR
    # capture_host_oracle.py stores -- [canPlayType, MediaSource.isTypeSupported] -- so excluding it suppresses BOTH
    # measurements, not just canPlayType: host ["probably", true] against fork ["", false].
    # NOT a capture artefact and NOT excusable forever: a Windows claim that cannot play HEVC is a tell, in a <video>
    # element and in Media Source Extensions alike. The spoof is roadmap work (backlog "HEVC claim"), and this entry is
    # what keeps O1 usable until then -- delete it when the claim lands, so both measurements go back to being made.
    # Predicated for the same reason the gpu prefix is: the excuse is "this build answers no to HEVC", which stops
    # being true the moment the Windows build (it carries the proprietary-codec pair) answers yes. Then the row is
    # compared again, so a fork that answers canPlayType but not isTypeSupported -- or the reverse -- shows up instead
    # of staying invisible behind an exclusion whose own deletion was the only thing keeping it measured.
    f"codecs.{HEVC}": ("host decodes HEVC in hardware, the box has no decoder; suppresses canPlayType AND "
                       "MediaSource.isTypeSupported (backlog: HEVC claim)",
                       lambda fork: (fork.get("codecs") or {}).get(HEVC) == ["", False]),
}
# Subtrees excluded from O1 by PREFIX, same shape as KNOWN, but each one is excluded ONLY while its condition holds --
# an unconditional prefix exclusion is how a check stops measuring anything. `when` is a predicate on the fork's report.
KNOWN_PREFIX = {
    # WebGPU. The host is a desktop with Intel graphics and reports an adapter; on a GPU-less box, with this verify
    # driving the fork with --use-angle=swiftshader, navigator.gpu.requestAdapter() resolves to null and the whole
    # subtree is absent. Same class as "host has no mouse": that asymmetry is the test environment, not the fork.
    #
    # The `when` is the point. The reason above is a property of the MACHINE, so the exclusion has to be too: on a box
    # with a GPU (the Windows build box of roadmap step 1, or anyone dropping the SwiftShader argv below) the fork
    # returns a real adapter, and gpu.info.* plus gpu.limits.* would then be the host machine's real GPU reported under
    # a spoofed Windows identity -- the exact cross-profile tell backlog item 2 exists for. Excluding by key name alone
    # would print "0 DIFF ... PASS" on the one machine where O1 could finally see it. With the predicate, the subtree
    # goes back to being compared the moment an adapter appears.
    #
    # While it does hold, O1 cannot see a WebGPU identity difference, including the three capability integers
    # (maxTextureDimension2D, maxComputeWorkgroupSizeX, maxBindGroups) that are compared exactly when an adapter
    # exists -- they have no fork-side value to compare. The backlog entry "WebGPU adapter identity" is where this
    # gets measured, on a machine with a GPU.
    "gpu": ("box has no GPU, fork runs SwiftShader (backlog: WebGPU adapter identity)",
            lambda fork: fork.get("gpu") is None),
}


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


EXPECTED_ROWS = 4  # O1 O2 O3 O4


def compare(base, fork):
    """O1's comparison: returns (diffs, same_count, active_prefixes).

    A module-level function, not inline in main(), so the exclusion rules can be tested without a browser --
    scripts/test_verify_host_oracle.py pins the one property that is easy to lose: a prefix exclusion stops
    applying the moment its condition no longer holds.
    """
    host_f, fork_f = flatten(base), flatten(fork)
    # Each prefix exclusion is admitted once, here, by asking its own predicate about THIS run's report -- never per
    # leaf. A per-leaf "is this side absent?" test cannot do it: for the fork's bare `gpu` key the fork value is None
    # while the host has no such leaf at all, so that one row would escape the exclusion and print as a DIFF.
    active = {p: reason for p, (reason, when) in KNOWN_PREFIX.items() if when(fork)}
    diffs = []
    buckets = {"equal": 0, "shape_only": 0, "prefix_excluded": 0, "known": 0}
    for k in sorted(set(host_f) | set(fork_f)):
        h, f = host_f.get(k, "<absent>"), fork_f.get(k, "<absent>")
        # An active prefix first, and before SHAPE_ONLY: an excluded subtree that is absent on one side has no type to
        # compare either, and SHAPE_ONLY would report "type list vs type str" against the "<absent>" sentinel --
        # three such lines for gpu.* survived the first version of this exclusion, which is how the order was found.
        prefix = next((p for p in active if k == p or k.startswith(p + ".")), None)
        if prefix is not None:
            buckets["prefix_excluded"] += 1
            if h != f:
                print(f"known: {k}: host={json.dumps(h)[:80]} fork={json.dumps(f)[:80]} ({active[prefix]})")
            continue
        if any(k == s or k.startswith(s + ".") for s in SHAPE_ONLY):
            buckets["shape_only"] += 1
            if type(h) != type(f):
                diffs.append((k, f"type {type(h).__name__}", f"type {type(f).__name__}"))
            continue
        if h != f:
            entry = KNOWN.get(k)
            # A bare reason excludes unconditionally; a pair excludes only while its predicate holds.
            reason, when = entry if isinstance(entry, tuple) else (entry, None)
            if reason is not None and (when is None or when(fork)):
                buckets["known"] += 1
                print(f"known: {k}: host={json.dumps(h)[:80]} fork={json.dumps(f)[:80]} ({reason})")
                continue
            diffs.append((k, h, f))
        else:
            buckets["equal"] += 1
    # Four buckets, not one "same" number. `same` used to be
    # len(all leaves) - len(diffs), which counts every leaf the loop SKIPPED as
    # evidence of agreement: a prefix-excluded or KNOWN leaf was never compared
    # at all, and a shape-only leaf was compared for type, not value. Reporting
    # one number let "0 DIFF, 239 same leaves" read as 239 leaves proven
    # identical when about a quarter of them were not value-compared.
    return diffs, buckets, active


@contextlib.contextmanager
def cfg_file(cfg):
    """The config as a temp JSON file. Windows' CreateProcess command line is capped at 32767 characters and a
    generated Windows identity is ~37 KB, so it is passed by path, never on a command line."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(cfg, f)
    try:
        yield f.name
    finally:
        os.unlink(f.name)


def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    H.body = cap.page().encode()
    env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}
    env["PLAYWRIGHT_NODEJS_PATH"] = NODE
    if "--config" in sys.argv:
        a = sys.argv[sys.argv.index("--config") + 1]
        cfg = json.load(open(a[1:], encoding="utf-8")) if a.startswith("@") else json.loads(a)
    else:
        g = subprocess.run([PY, "-m", "camoucrome.gen", "--os", "windows", "--seed", os.environ.get("CAMOU_SEED", "1")], capture_output=True, text=True, timeout=120)
        if g.returncode != 0:
            sys.exit(g.stderr[-500:])
        cfg = json.loads(g.stdout)["config"]
    with cfg_file(cfg) as cf:
        p = subprocess.run([PY, "-m", "camoucrome.probe", "--driver", "patchright", "--executable", EXE, "--url", f"http://127.0.0.1:{srv.server_port}/",
                            "--config", "@" + cf, "--fonts-dir", FONTS_DIR, "--arg=--use-gl=angle", "--arg=--use-angle=swiftshader"],
                           capture_output=True, text=True, timeout=240, env=env)
    srv.shutdown()
    if p.returncode != 0:
        sys.exit(p.stderr[-800:])
    fork = json.loads(p.stdout)["report"]
    for key in ("windowKeys", "navProto", "windowNames"):  # lists: the set difference minus the probe marker, compared as sets
        h, f = set(BASE.get(key) or []), set(fork.get(key) or []) - {"__camou_init"}
        if h != f:
            print(f"DIFF {key}: host-only={sorted(h - f)} fork-only={sorted(f - h)}")
        BASE[key], fork[key] = sorted(h), sorted(f)
    if fork.get("protoCounts", {}).get("Window") == BASE.get("protoCounts", {}).get("Window", 0) + 1:
        fork["protoCounts"]["Window"] -= 1  # the probe marker
    diffs, buckets, active_prefixes = compare(BASE, fork)
    for p, (reason, when) in KNOWN_PREFIX.items():
        if p not in active_prefixes:
            print(f"note: prefix exclusion {p!r} NOT in effect this run ({reason}) -- the subtree is compared")
    print("note: voices host=", json.dumps(BASE.get("voices"))[:300], "fork=", json.dumps(fork.get("voices"))[:300])
    print("note: audioFp host=", BASE.get("audioFp"), "fork=", fork.get("audioFp"), "| canvas host=", BASE.get("canvas"), "fork=", fork.get("canvas"))
    for k, h, f in diffs:
        print(f"DIFF {k}: host={json.dumps(h)[:160]} fork={json.dumps(f)[:160]}")
    print(f"{len(diffs)} DIFF; {buckets['equal']} leaves equal by value, "
          f"{buckets['shape_only']} compared by type only, {buckets['known']} named in KNOWN, "
          f"{buckets['prefix_excluded']} prefix-excluded (NOT compared); "
          f"fork done={fork.get('done')} pageError={fork.get('pageError')}")
    results = {"O1 generated Windows identity: no difference from stock Windows Chrome outside the named set (host artefacts, identity-bound, probe marker, sampleRate)": not diffs}
    if "--config" not in sys.argv:
        # O2 RED: a Linux claim keeps Linux's shape -- the gated interfaces follow the claim, not the build.
        g = subprocess.run([PY, "-m", "camoucrome.gen", "--os", "linux", "--timezone", "UTC", "--seed", "1"], capture_output=True, text=True, timeout=120)
        lin = json.loads(g.stdout)["config"]
        with cfg_file(lin) as lf:
            r = subprocess.run([PY, sys.argv[0], "--config", "@" + lf], capture_output=True, text=True, timeout=400, env=env)
        # queryLocalFonts is stock on every OS (FontAccess at stock status), so it must NOT differ.
        qlf_diff = any("queryLocalFonts" in l for l in r.stdout.splitlines() if l.startswith("DIFF windowNames"))
        ok2 = "host-only=['bluetooth', 'canShare', 'share']" in r.stdout and not qlf_diff
        if not ok2:
            print("O2 sub-run rc", r.returncode, "navProto line:", [l[:120] for l in r.stdout.splitlines() if l.startswith("DIFF navProto: host-only")],
                  "windowNames has queryLocalFonts:", qlf_diff)
        results["O2 RED Linux claim: navigator.share / bluetooth absent (the gate follows the claim); queryLocalFonts present as on every stock OS, no windowNames diff"] = ok2
        results.update(font_access_rows(cfg, env))
        results.update(brand_header_rows(cfg, env))
    n = sum(results.values())
    for k, v in results.items():
        print("PASS " if v else "FAIL ", k)
    # O1 only in the --config sub-run; O1-O4 otherwise. A row that silently drops out
    # (a skipped branch, a duplicate key) must fail, not shrink the denominator.
    expected = 1 if "--config" in sys.argv else EXPECTED_ROWS
    print(f"{n} PASS {len(results) - n} FAIL")
    if len(results) != expected:
        print(f"FAIL  {len(results)} rows, expected {expected}")
    sys.exit(0 if n == len(results) == expected else 1)


FA_PAGE = b"""<!doctype html><title>fa</title><button id=b>go</button><pre id=o></pre><script>
document.getElementById('b').onclick=async()=>{try{const fs=await queryLocalFonts();document.getElementById('o').textContent=JSON.stringify({n:fs.length,
faces:fs.map(f=>[f.postscriptName,f.fullName,f.family,f.style])})}catch(e){document.getElementById('o').textContent=JSON.stringify({error:e.name+': '+e.message})}};
</script>"""


def font_access_rows(cfg, env):
    """O3: queryLocalFonts() under the real permission flow. Without a grant the call needs the prompt (headless:
    denied => NotAllowedError, as stock without a grant); with the local-fonts permission granted and a click for
    activation it lists exactly the manifest's captured Windows faces, sorted by PostScript name, none of the bundle's."""
    with cfg_file(cfg) as cf:  # by path: a Windows identity is ~37 KB, over the 32767-char command line
        script = f"""
import json, sys
sys.path.insert(0, {json.dumps(str(CLIENT / "client" / "python"))})
from camoucrome.launcher import launch
from patchright.sync_api import sync_playwright
import http.server, threading
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write({FA_PAGE!r})
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{{srv.server_port}}/"
out = {{}}
with sync_playwright() as pw:
    ctx = launch(pw, {json.dumps(EXE)}, config=json.load(open({json.dumps(cf)}, encoding="utf-8")), headless=True, args=["--no-sandbox"], fonts_dir={json.dumps(FONTS_DIR)})
    page = ctx.new_page(); page.goto(url); page.click("#b"); page.wait_for_function("document.getElementById('o').textContent !== ''", timeout=20000)
    out["nogrant"] = json.loads(page.locator("#o").text_content())
    ctx.grant_permissions(["local-fonts"], origin=url)
    page.goto(url); page.click("#b"); page.wait_for_function("document.getElementById('o').textContent !== ''", timeout=20000)
    out["granted"] = json.loads(page.locator("#o").text_content())
    ctx.close()
print(json.dumps(out))
"""
        p = subprocess.run([PY, "-c", script], capture_output=True, text=True, timeout=300, env=env)
    if p.returncode != 0:
        print("O3 probe failed:", p.stderr[-900:].replace("\n", " | "))
        return {"O3 queryLocalFonts()": False}
    r = json.loads(p.stdout.strip().splitlines()[-1])
    want = [f.split("\t") for f in cfg["fonts:local"]]
    got = r["granted"].get("faces")
    print(f"note: O3 no grant -> {json.dumps(r['nogrant'])[:120]}; granted -> n={r['granted'].get('n')} first={json.dumps((got or [])[:2])}")
    # Stock resolves with an empty list when the prompt is denied (headless denies it); with the grant and a click
    # for activation the list is the claimed host's.
    return {"O3 queryLocalFonts(): denied prompt -> [] as stock; granted + activated -> exactly the manifest's Windows faces in PostScript order, none of the bundle's": (
        r["nogrant"].get("n") == 0 and got == want and len(got or []) > 150 and not any("Selawik" in f[0] or "Liberation" in f[0] for f in got))}


def brand_header_rows(cfg, env):
    """O4: the brand list is produced twice, in the browser (Sec-CH-UA / Sec-CH-UA-Full-Version-List request headers)
    and in the renderer (navigator.userAgentData). Both must carry the host's stock list in its order; O1 only saw the
    renderer's copy."""
    with cfg_file(cfg) as cf:  # by path: a Windows identity is ~37 KB, over the 32767-char command line
        script = f"""
import json, sys
sys.path.insert(0, {json.dumps(str(CLIENT / "client" / "python"))}); sys.path.insert(0, {json.dumps(str(CLIENT / "scripts"))})
import echo_server
from camoucrome.launcher import launch
from patchright.sync_api import sync_playwright
base, headers_for, stop = echo_server.start(["Sec-CH-UA-Full-Version-List"])
out = {{}}
with sync_playwright() as pw:
    ctx = launch(pw, {json.dumps(EXE)}, config=json.load(open({json.dumps(cf)}, encoding="utf-8")), headless=True, args=["--no-sandbox"], fonts_dir={json.dumps(FONTS_DIR)})
    page = ctx.new_page(); page.goto(base + "/"); page.goto(base + "/")  # second load carries the Accept-CH hints
    out["js"] = page.evaluate("navigator.userAgentData.getHighEntropyValues(['fullVersionList']).then(h => ({{brands: navigator.userAgentData.brands, full: h.fullVersionList}}))")
    h = {{k.lower(): v for k, v in (headers_for("/") or {{}}).items()}}
    out["hdr"] = {{"ua": h.get("sec-ch-ua"), "full": h.get("sec-ch-ua-full-version-list")}}
    ctx.close()
stop()
print(json.dumps(out))
"""
        p = subprocess.run([PY, "-c", script], capture_output=True, text=True, timeout=300, env=env)
    if p.returncode != 0:
        print("O4 probe failed:", p.stderr[-900:].replace("\n", " | "))
        return {"O4 brand headers": False}
    r = json.loads(p.stdout.strip().splitlines()[-1])

    def parse(sh):  # RFC 8941 list: "Google Chrome";v="153", ...
        return [{"brand": i.split('";v="')[0].strip().strip('"'), "version": i.split('";v="')[1].rstrip('"')} for i in (sh or "").split(", ") if '";v="' in i]
    host = BASE["uad"]["brands"], BASE["uadHigh"]["fullVersionList"]
    got = (r["js"]["brands"], r["js"]["full"], parse(r["hdr"]["ua"]), parse(r["hdr"]["full"]))
    print(f"note: O4 Sec-CH-UA={r['hdr']['ua']!r} full={r['hdr']['full']!r}")
    return {"O4 brands: Sec-CH-UA and Sec-CH-UA-Full-Version-List request headers == navigator.userAgentData == the host's stock list in stock order": (
        got[0] == host[0] and got[1] == host[1] and got[2] == host[0] and got[3] == host[1])}


if __name__ == "__main__":
    main()

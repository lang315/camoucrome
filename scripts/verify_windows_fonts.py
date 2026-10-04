#!/usr/bin/env python3
"""Windows: what a page can learn about the host's fonts under a Windows claim.

Spec: docs/superpowers/specs/2026-10-04-step1-finish-design.md section 5. The
host has 118 families; the claimed families.Windows.list (116) is all present,
and the host adds ROG Fonts and AniMe Matrix - MB_EN (ASUS) -- fonts that
identify this machine.

F1     ROG Fonts is invisible to measureText in a window and a worker under a
       generated Windows identity, AND visible to stock (in the same row, so F1
       cannot pass on a font the host lacks)
F2-*   claimed families the host has (Arial, Segoe UI, Times New Roman, Verdana)
       measure as stock within JITTER_TOL (canvas:seed jitters measureText by
       design) and win over both fallbacks, through the Python, Go and Node clients. They
       measure the launcher rule (settings/launcher.json launch.native_fonts: the
       client drops fonts:alias/aliasLocal when the claimed OS is the host's).
       Confirmed 2026-10-04: before the fix every claimed family measured the
       same 1807.99 (the face the failed alias lookups fell through to, ~Segoe
       UI's own width) vs stock's distinct 1794.53 / 1808.06 / 1694.34 /
       2057.67; gen --os windows emits fonts:alias Arial -> Liberation Sans and
       GetFontPlatformData returns the alias target's lookup with no fallback.
F4     per-character system fallback (CJK, Thai, emoji in a family nobody has)
       measures as stock within JITTER_TOL (same canvas:seed jitter): the fallback is the host's real one, which is what a
       Windows host claiming Windows should show. fonts:list does not filter it
       (no patch touches PlatformFallbackFontForCharacter).
F3     note, measured: of the identity's fonts:list, how many families stock
       cannot resolve on this host (a real device would have them, so each is
       a tell), and up to 10 names
F5     note: whether two generated identities claim different font lists

RED: windows_verify_set.py red runs this with CAMOU_EXE = the stock chrome.exe;
stock sees ROG Fonts, so F1 fails.
"""
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_shell import CHROME as EXE, layout  # noqa: E402

HOME, PY, NODE, CLIENT, FONTS_DIR = layout()
import verify_windows_client as vwc  # noqa: E402  (PROBES, read_probe)

STOCK = os.environ.get("CAMOU_STOCK_EXE", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
HOST_ONLY = "ROG Fonts"
REAL = ["Arial", "Segoe UI", "Times New Roman", "Verdana"]
TEXT = "mmmmmmmmmmlli WWW 0123456789"
FALLBACK_TEXT = "\u6f22\u5b57\u304b\u306a \u0e44\u0e17\u0e22 \U0001F600"
EXPECTED = 5

PAGE_TMPL = """<!doctype html><title>fonts</title><script>
const FAMS = %s, TEXT = %s, FB = %s;
function measure(ctx) {
  const w = (font, t) => { ctx.font = font; return ctx.measureText(t).width; };
  const out = {};
  for (const f of FAMS) out[f] = [w('100px "' + f + '", monospace', TEXT), w('100px "' + f + '", serif', TEXT)];
  out.__mono = w('100px monospace', TEXT); out.__serif = w('100px serif', TEXT);
  out.__fallback = w('100px "Camoucrome No Such Family"', FB);
  return out;
}
const SRC = 'const FAMS=' + JSON.stringify(FAMS) + ',TEXT=' + JSON.stringify(TEXT) + ',FB=' + JSON.stringify(FB) + ';' +
  measure.toString() + 'self.postMessage(measure(new OffscreenCanvas(10,10).getContext("2d")));';
const wk = new Worker(URL.createObjectURL(new Blob([SRC], {type: 'text/javascript'})));
wk.onmessage = e => { const o = document.createElement('pre'); o.id = 'o';
  o.textContent = JSON.stringify({main: measure(document.createElement('canvas').getContext('2d')), worker: e.data});
  document.body.appendChild(o); };
</script>"""


def page(claimed):
    """The page measures HOST_ONLY, REAL and every claimed family (cheap, and the stock read needs them for F3)."""
    fams = list(dict.fromkeys([HOST_ONLY] + REAL + claimed))
    return PAGE_TMPL % (json.dumps(fams), json.dumps(TEXT), json.dumps(FALLBACK_TEXT))


# measureText jitter under canvas:seed measured at <= 0.12 px on a 28-char string at 100 px; distinct fonts here
# differ by >= 13 px except Segoe UI vs the monospace fallback (0.07 px), which the two-variant check decides.
JITTER_TOL = 1.0


def resolved(r, fam):
    mono, serif = r[fam]
    return abs(mono - r["__mono"]) > JITTER_TOL or abs(serif - r["__serif"]) > JITTER_TOL


def real_ok(r, sm):
    """Every REAL family won over BOTH fallbacks (variants agree) and sits within the jitter of stock."""
    # Arial/Times New Roman/Segoe UI alias to metric-compatible targets by design, so width vs stock alone cannot
    # detect the alias when the target is installed; the two-variant (resolved) check is what does.
    # The two-variant check only discriminates if bare monospace and serif differ by more than JITTER_TOL.
    return (r is not None and sm is not None and abs(r["__mono"] - r["__serif"]) > JITTER_TOL
            and all(abs(r[f][0] - r[f][1]) <= JITTER_TOL and abs(r[f][0] - sm[f][0]) <= JITTER_TOL for f in REAL))


def identity(seed):
    g = subprocess.run([PY, "-m", "camoucrome.gen", "--os", "windows", "--seed", str(seed)],
                       capture_output=True, text=True, timeout=120)
    if g.returncode != 0:
        sys.exit(g.stderr[-500:])
    return json.loads(g.stdout)["config"]


def python_read(url, exe, config):
    """{main, worker} through camoucrome.launch() in a subprocess, sandboxed."""
    # Windows' CreateProcess command line is capped at 32767 characters and a Windows identity is ~37 KB, so the
    # config goes by file path (null for the stock read), never into the -c source.
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(config, f)
    script = f"""
import json, sys
sys.path.insert(0, {json.dumps(str(CLIENT / "client" / "python"))})
from camoucrome import launch
from patchright.sync_api import sync_playwright
with sync_playwright() as pw:
    ctx = launch(pw, {json.dumps(exe)}, config=json.load(open({json.dumps(f.name)}, encoding="utf-8")), headless=True)
    page = ctx.new_page(); page.goto({json.dumps(url)})
    page.wait_for_selector("#o", state="attached", timeout=30000)
    print(page.locator("#o").text_content())
    ctx.close()
"""
    try:
        p = subprocess.run([PY, "-c", script], capture_output=True, text=True, timeout=300)
    finally:
        os.unlink(f.name)
    if p.returncode != 0:
        return None, p.stderr[-600:]
    return json.loads(p.stdout.strip().splitlines()[-1]), None


def main():
    cfg = identity(1)
    claimed = cfg.get("fonts:list") or []
    body = page(claimed).encode()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), type("H", (http.server.BaseHTTPRequestHandler,), {
        "do_GET": lambda s: (s.send_response(200), s.send_header("Content-Type", "text/html; charset=utf-8"),
                             s.end_headers(), s.wfile.write(body)),
        "log_message": lambda *a: None}))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"
    results, notes = {}, []
    fork, err = python_read(url, EXE, cfg)
    stock, serr = python_read(url, STOCK, None)
    if fork is None or stock is None:
        print("note: launch failed:", (err or serr or "").replace("\n", " | "))
        fork, stock = fork or {"main": None, "worker": None}, stock or {"main": None, "worker": None}
    fm, fw, sm = fork["main"], fork["worker"], stock["main"]
    results["F1 ROG Fonts hidden in window and worker under the identity, visible to stock"] = (
        fm is not None and fw is not None and sm is not None
        and not resolved(fm, HOST_ONLY) and not resolved(fw, HOST_ONLY) and resolved(sm, HOST_ONLY))
    real_equal = lambda r: real_ok(r, sm)
    results["F2-py claimed host families measure as stock (Python client)"] = real_equal(fm)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(cfg, f)
        cfg_file = f.name
    try:
        for k, label in (("G", "go"), ("N", "node")):
            _argv, main_r, _worker_r, perr = vwc.read_probe(vwc.PROBES[k], url, cfg_file)
            if perr:
                notes.append(f"F2-{label}: {str(perr)[:300]}")
            results[f"F2-{label} claimed host families measure as stock ({label} client)"] = real_equal(main_r)
    finally:
        os.unlink(cfg_file)
    results["F4 per-character system fallback measures as stock"] = (
        fm is not None and sm is not None and abs(fm["__fallback"] - sm["__fallback"]) <= JITTER_TOL)
    srv.shutdown()
    if fm is not None and sm is not None:
        notes.append("F2 widths fork mono|serif/stock: " + "; ".join(
            f"{x}={fm[x][0]:.2f}|{fm[x][1]:.2f}/{sm[x][0]:.2f}" for x in REAL))
        notes.append(f"F4 fallback width fork/stock: {fm['__fallback']:.2f}/{sm['__fallback']:.2f}")
    if sm is not None:
        lacking = [f for f in claimed if f in sm and not resolved(sm, f)]
        notes.append(f"F3: the identity claims {len(claimed)} families; stock cannot resolve {len(lacking)}"
                     f"{': ' + ', '.join(lacking[:10]) if lacking else ''}")
    else:
        notes.append("F3: stock read failed, nothing measured")
    other = identity(2).get("fonts:list") or []
    notes.append(f"F5: seeds 1 and 2 claim {'the SAME' if sorted(other) == sorted(claimed) else 'different'} "
                 f"font lists ({len(claimed)} vs {len(other)}) -- the SAME list on every profile is a "
                 f"cross-profile finding for backlog item 2, not a failure here")
    for k, v in results.items():
        print(("PASS " if v else "FAIL ") + " " + k)
    for n in notes:
        print("note:", n[:900])
    if len(results) != EXPECTED:
        sys.exit(f"expected {EXPECTED} rows, built {len(results)}")
    n = sum(results.values())
    print(f"{n} PASS {len(results) - n} FAIL")
    sys.exit(0 if n == len(results) else 1)


if __name__ == "__main__":
    main()

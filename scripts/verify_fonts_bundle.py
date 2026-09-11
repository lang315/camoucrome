"""Font bundle + fontconfig alias layer (spec 2026-09-11 §1) on chrome through
the client probe. Width test only: document.fonts.check answers true for any
never-loaded family (measured 2026-09-11).

F1 RED (no --fonts-dir, no config): "Segoe UI" does not resolve (its width
   follows the fallback: monospace vs serif differ), "DejaVu Sans" does.
F2 --fonts-dir + Windows claim + the Windows fonts:list + fonts:alias: every
   listed family resolves; DejaVu Sans / Ubuntu / Cantarell do not; system-ui
   and Segoe UI render the string at one width (Selawik through the alias)
   that differs from the unresolvable width; a direct "Selawik" request is
   blocked by the allowlist (the bundle's own names never leak).
F3 --fonts-dir + macOS claim + the macOS list: every listed family resolves;
   system-ui == -apple-system (Inter Variable through the alias); a direct
   "Inter Variable" request is blocked.
F4 gen.py --os windows: its fonts:list is a subset of what F2 measured as
   resolving (page-measured, not table-asserted).
F5 (CAMOU_EXE = an extracted archive's chrome, no --fonts-dir): the launcher
   finds fonts/ beside the executable; the F2 rows pass.
F6 worker parity (rule 3): a dedicated worker's OffscreenCanvas measures the
   aliased families at the main thread's widths under the F2 config.
F7 a cyclic fonts:alias ({A:B, B:A, Segoe UI:A}, non-strict) starts and loads
   the page: the alias is one hop, a bad map never recurses (no crash).
F8 emoji presence by colour, not width: U+1F600 in "Segoe UI Emoji" under the
   Windows claim + bundle paints >= 50 coloured pixels; RED: no bundle paints 0.
F9 CJK region: 骨/直 in "Yu Gothic" (JP form) differ from "Microsoft YaHei" (SC)
   pixel-for-pixel; RED: an alias map sending Yu Gothic to the SC face gives equal.
F10 RED (F-PSNAME): with family-level keys only, local("SegoeUI") errors.
F11 with the unique names the generator emits (fonts:aliasLocal): local("SegoeUI"),
   local("Segoe UI"), local("SegoeUI-Bold"), local("Georgia"), local("Calibri") and
   local("Symbol") load, the SegoeUI face is as wide as "Segoe UI";
   local("Selawik") / local("Selawik-Regular") error (bundle names stay blocked);
   a worker's local("SegoeUI") status equals the page's (rule 3).
F12 PostScript names are not CSS families: font-family "ArialMT" / "SegoeUI" /
   "TimesNewRomanPSMT" stay unresolved, as measured on stock Windows (RED, twice:
   with the unique names in fonts:alias they resolved; with them in fonts:list
   "SegoeUI" resolved through fontconfig's blank-insensitive family compare).
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
PAR = ["Segoe UI", "Consolas", "Calibri"]  # F6: aliased under the Windows map, measured on both threads
LOCALS = ["SegoeUI", "Segoe UI", "SegoeUI-Bold", "Georgia", "Calibri", "Symbol", "Selawik", "Selawik-Regular", "Tahoma-Bold"]  # F10/F11 local() names
PSN = ["ArialMT", "SegoeUI", "TimesNewRomanPSMT"]  # F12: PostScript names as CSS families (stock Windows: unresolved)


def text_for(family):
    """The probe string for a family: its script class's (an emoji font has no Latin glyphs)."""
    for cls, names in FONTS["script_class"].items():
        if family in names:
            return FONTS["probe_text"][cls]
    return FONTS["probe_text"]["sans"]


def page(families):
    return ("""<!doctype html><title>fonts</title><pre id="o"></pre><span id="k"></span><script>
const FAM = %s, TEXT = %s, PT = %s;
const ctx = document.createElement('canvas').getContext('2d');
const S = PT.sans;
const width = (f, s) => { ctx.font = `16px ${f}`; return ctx.measureText(s || S).width; };
const mono = width('monospace');
// A resolvable family renders at its own width whatever the fallback; an unresolvable one
// renders as the fallback, so its width changes with it (monospace vs serif).
const resolves = Object.fromEntries(FAM.map(f => [f, width(`"${f}", monospace`, TEXT[f]) === width(`"${f}", serif`, TEXT[f])]));
const widths = Object.fromEntries(%s.map(f => [f, width(f.startsWith('-') || f === 'system-ui' || f === 'sans-serif' ? f : `"${f}"`)]));
const k = document.getElementById('k'); k.style.font = 'caption'; k.textContent = S;
const PAR = %s;
const par = Object.fromEntries(PAR.map(f => [f, width(`"${f}"`)]));
const out = (wpar, local, wlocal) => { document.getElementById('o').textContent = JSON.stringify({ resolves, widths, caption: k.getBoundingClientRect().width, mono, par, wpar, cjk, emoji, local, wlocal }); };
const LOCALS = %s;
const localProbe = async (n, i) => { const f = new FontFace('lp' + i, 'local("' + n + '")'); try { await f.load(); document.fonts.add(f); } catch (e) {} return [n, { status: f.status, width: f.status === 'loaded' ? width('lp' + i) : null }]; };
const localsP = Promise.all(LOCALS.map(localProbe)).then(Object.fromEntries);
const src = `(async () => { const c = new OffscreenCanvas(1, 1).getContext('2d'); const widths = Object.fromEntries(${JSON.stringify(PAR)}.map(f => { c.font = '16px "' + f + '"'; return [f, c.measureText(${JSON.stringify(S)}).width]; })); const f = new FontFace('lp', 'local("${LOCALS[0]}")'); try { await f.load(); } catch (e) {} postMessage({ widths, local: f.status }); })();`;
const glyph = (fam, ch) => { const c = document.createElement('canvas'); c.width = 64; c.height = 64; const x = c.getContext('2d'); x.font = '48px "' + fam + '"'; x.fillText(ch, 4, 52); return c.toDataURL(); };
const coloured = fam => { const c = document.createElement('canvas'); c.width = 48; c.height = 48; const x = c.getContext('2d'); x.font = '32px "' + fam + '"'; x.fillText('\\u{1F600}', 4, 38); const d = x.getImageData(0, 0, 48, 48).data; let n = 0; for (let i = 0; i < d.length; i += 4) { if (d[i + 3] > 0 && Math.max(d[i], d[i + 1], d[i + 2]) - Math.min(d[i], d[i + 1], d[i + 2]) > 32) n++; } return n; };
const cjk = { jp: ['\\u9AA8', '\\u76F4'].map(ch => glyph('Yu Gothic', ch)), sc: ['\\u9AA8', '\\u76F4'].map(ch => glyph('Microsoft YaHei', ch)) };
const emoji = coloured('Segoe UI Emoji');
const wk = new Worker(URL.createObjectURL(new Blob([src], { type: 'text/javascript' })));
wk.onmessage = e => localsP.then(loc => out(e.data.widths, loc, e.data.local));
wk.onerror = e => out({ error: String(e.message) }, {}, null);
</script>""" % (json.dumps(families), json.dumps({f: text_for(f) for f in families}), json.dumps(FONTS["probe_text"]), json.dumps(SPECIAL), json.dumps(PAR), json.dumps(LOCALS))).encode()


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
    results["F8 RED no bundle: Segoe UI Emoji paints 0 coloured pixels"] = r["emoji"] == 0
    notes.append(f"F8 RED coloured={r['emoji']}")

    H.body = page(win_list + HOST_ONLY + PSN)
    win_keys = {"fonts:list": win_list + FONTS["extra_allowed"]["Windows"],
                "fonts:alias": FONTS["alias_map"]["Windows"], "fonts:aliasLocal": FONTS["unique_map"]["Windows"]}
    r = probe(url, {**WIN, **win_keys}, fd)
    results["F12 PostScript names are not CSS families: ArialMT / SegoeUI / TimesNewRomanPSMT unresolved (stock Windows: unresolved)"] = (
        not any(r["resolves"][n] for n in PSN))
    missing = [f for f in win_list if not r["resolves"][f]]
    leaked = [f for f in HOST_ONLY if r["resolves"][f]]
    w = r["widths"]
    blocked = w["Inter Variable"]  # not in the Windows list: the allowlist's fallback width
    results[f"F2 Windows claim + bundle: all {len(win_list)} listed families resolve, host-only hidden, system-ui == Segoe UI (Selawik via alias) != blocked, direct Selawik blocked"] = (
        not missing and not leaked and same(w, "system-ui", "Segoe UI") and w["Segoe UI"] != blocked and w["Selawik"] == blocked)
    if missing or leaked or not same(w, "system-ui", "Segoe UI"):
        notes.append(f"F2 missing={missing[:8]} leaked={leaked} widths={ {k: round(v, 2) for k, v in w.items()} } caption={r['caption']:.2f}")
    resolving = {f for f in win_list if r["resolves"][f]}
    results["F8 Windows claim + bundle: U+1F600 in Segoe UI Emoji paints >= 50 coloured pixels"] = r["emoji"] >= 50
    notes.append(f"F8 coloured={r['emoji']}")
    results["F9 CJK region: Yu Gothic (JP) glyphs 骨/直 differ from Microsoft YaHei (SC)"] = any(a != b for a, b in zip(r["cjk"]["jp"], r["cjk"]["sc"]))
    r9 = probe(url, {**WIN, "fonts:list": win_list + FONTS["extra_allowed"]["Windows"], "fonts:alias": {**FONTS["alias_map"]["Windows"], "Yu Gothic": "Noto Sans CJK SC"}}, fd)
    results["F9 RED: Yu Gothic aliased to the SC face renders equal to Microsoft YaHei"] = r9["cjk"]["jp"] == r9["cjk"]["sc"]
    loc = r["local"]
    results["F11 unique names: local(SegoeUI / Segoe UI / SegoeUI-Bold / Georgia / Calibri / Symbol) load, SegoeUI as wide as Segoe UI, local(Selawik*) error, worker status == page"] = (
        all(loc[n]["status"] == "loaded" for n in ("SegoeUI", "Segoe UI", "SegoeUI-Bold", "Georgia", "Calibri", "Symbol"))
        and same({"a": loc["SegoeUI"]["width"], "b": loc["Segoe UI"]["width"], "c": w["Segoe UI"]}, "a", "b", "c")
        and all(loc[n]["status"] == "error" for n in ("Selawik", "Selawik-Regular")) and r["wlocal"] == loc["SegoeUI"]["status"])
    notes.append("F11 local=" + json.dumps({n: (v["status"], v["width"] and round(v["width"], 2)) for n, v in loc.items()}) + f" worker={r['wlocal']}")
    r10 = probe(url, {**WIN, "fonts:list": win_list + FONTS["extra_allowed"]["Windows"], "fonts:alias": FONTS["alias_map"]["Windows"]}, fd)
    results["F10 RED family-level keys only: local(SegoeUI) errors (F-PSNAME over-block)"] = r10["local"]["SegoeUI"]["status"] == "error"
    results["F6 worker parity: a worker's OffscreenCanvas widths of Segoe UI/Consolas/Calibri == the main thread's"] = (
        "error" not in r["wpar"] and all(round(r["par"][f], 2) == round(r["wpar"][f], 2) for f in PAR))
    notes.append(f"F6 main={ {f: round(r['par'][f], 2) for f in PAR} } worker={ {f: round(v, 2) for f, v in r['wpar'].items()} }")

    H.body = page(mac_list + HOST_ONLY)
    r = probe(url, {**MAC, "fonts:list": mac_list + FONTS["extra_allowed"]["macOS"], "fonts:alias": FONTS["alias_map"]["macOS"]}, fd)
    missing = [f for f in mac_list if not r["resolves"][f]]
    leaked = [f for f in HOST_ONLY if r["resolves"][f]]
    w = r["widths"]
    blocked = w["Selawik"]  # not in the macOS list
    results[f"F3 macOS claim + bundle: all {len(mac_list)} listed families resolve, host-only hidden, system-ui == -apple-system (Inter via alias) != blocked, direct Inter Variable blocked"] = (
        not missing and not leaked and same(w, "system-ui", "-apple-system") and w["-apple-system"] != blocked and w["Inter Variable"] == blocked)
    if missing or leaked or not same(w, "system-ui", "-apple-system"):
        notes.append(f"F3 missing={missing[:8]} leaked={leaked} widths={ {k: round(v, 2) for k, v in w.items()} }")

    gen = subprocess.run([PY, "-m", "camoucrome.gen", "--os", "windows", "--timezone", "UTC", "--seed", "1"],
                         capture_output=True, text=True, timeout=120)
    emitted = json.loads(gen.stdout)["config"].get("fonts:list", []) if gen.returncode == 0 else None
    fam_part = set(emitted or []) & set(win_list)
    results["F4 gen.py --os windows emits a fonts:list whose families F2 measured as resolving (families only)"] = (
        bool(fam_part) and fam_part <= resolving and "SegoeUI" not in (emitted or []))
    if not emitted:
        notes.append("F4 gen: " + gen.stderr[-300:])
    H.body = page(["Segoe UI", "A", "B"])
    try:
        r = probe(url, {**WIN, "fonts:alias": {"A": "B", "B": "A", "Segoe UI": "A"}}, fd)
        ok = "resolves" in r
    except SystemExit as e:  # probe() exits when chrome dies or the page never reports
        ok, r = False, None
        notes.append(f"F7: {e}")
    results["F7 cyclic fonts:alias {A:B, B:A, Segoe UI:A} (non-strict): chrome starts and the page reports (one hop, no recursion)"] = ok
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

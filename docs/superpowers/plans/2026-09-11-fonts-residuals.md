# Fonts Residuals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the fonts residual list into numbers and code: a host-vs-fork metric grid, three open-licence clones kept only if they measure, a five-region CJK bundle, PostScript/full-name aliasing for `local()`, an emoji presence row, and UA-CH `platformVersion` tied to the captured list.

**Architecture:** Everything rides on the existing manifest (`settings/fonts.json`) → `gen_fontconfig.py` → generator pipeline plus `verify_fonts_bundle.py`. New scripts only for the metric grid (a capture on the Windows host through `winhost.dump_dom`, a verify on the fork through the probe). No C++ unless §3's RED-first measurement proves the unique-name hop needs one.

**Tech Stack:** Python 3 (stdlib + fontTools on the Mac only), PowerShell 5.1 on the Windows host, patchright probe on the box.

## Global Constraints

- Only open-licence fonts: SIL OFL 1.1 or LGPL 2.1+ (Wine); every entry sha256-pinned; `fonts/` stays git-ignored.
- Bad config never crashes a renderer; no JS injection; worker parity for `local()`.
- The Windows host is stock Chrome 153.0.8010.36 on Windows 10 build 19045; the fork is `out/Default/chrome` on the box with `--fonts-dir`.
- A clone that fails its M-row is removed from the manifest before the slice ships.
- The macOS build (47 GiB free), the macOS WebGL re-capture (Chrome 151) and hinting/AA are closed by fact in the doc, not worked.

---

### Task 1: Metric grid — host capture, baseline, fork verify

**Files:**
- Create: `scripts/capture_font_metrics.py`, `scripts/verify_font_metrics.py`
- Create: `baselines/chrome-8010-stock-font-metrics-windows.json`
- Test: the verify's own M1 control row (RED if the harness measures rendering, not fonts)

**Interfaces:** `GRID_FAMILIES`, `CHARS` (95 ASCII + 30 Latin-1), `page(families)` shared by both scripts via `capture_font_metrics.PAGE`. Baseline shape `{"chrome": "153.0.8010.36", "where": "...", "px": 100, "families": {fam: {"resolved": bool, "widths": {ch: w}}}}`.

- [ ] **Step 1: write `scripts/capture_font_metrics.py`**

```python
#!/usr/bin/env python3
"""Per-character advance widths of the claimed Windows families on the real
host (stock Chrome 153 on the box's Windows 10 host, headless --dump-dom) ->
baselines/chrome-8010-stock-font-metrics-windows.json. 100 px so 1/100 em is
one pixel; canvas advances are linear (unhinted) on DirectWrite and FreeType."""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "baselines" / "chrome-8010-stock-font-metrics-windows.json"
GRID_FAMILIES = ["Segoe UI", "Arial", "Times New Roman", "Courier New", "Calibri", "Cambria",
                 "Consolas", "Georgia", "Verdana", "Tahoma", "Trebuchet MS", "Segoe UI Variable"]
CHARS = [chr(c) for c in range(0x20, 0x7F)] + [chr(c) for c in range(0xC0, 0xDE)]
PX = 100

def page(families):
    return ("<!doctype html><title>metrics</title><pre id=o></pre><script>"
            "const F=%s,C=%s,PX=%d;const ctx=document.createElement('canvas').getContext('2d');"
            "const w=(f,s)=>{ctx.font=PX+'px '+f;return ctx.measureText(s).width};"
            "const out={};for(const f of F){const q='\"'+f+'\"';"
            "const resolved=w(q+', monospace','The quick brown fox 0123')===w(q+', serif','The quick brown fox 0123');"
            "out[f]={resolved,widths:Object.fromEntries(C.map(c=>[c,w(q,c)]))}}"
            "document.getElementById('o').textContent=JSON.stringify(out);</script>"
            % (json.dumps(families), json.dumps(CHARS), PX))

def main():
    import winhost
    dom = winhost.dump_dom(page(GRID_FAMILIES), args=("--use-gl=angle", "--use-angle=d3d11"))
    body = dom[dom.index("<pre id=\"o\">") + len("<pre id=\"o\">"):dom.index("</pre>")]
    import html; fams = json.loads(html.unescape(body))
    OUT.write_text(json.dumps({"chrome": "153.0.8010.36", "where": "stock Google Chrome on the build box's Windows 10 host (19045), headless --dump-dom, temp profile",
                               "px": PX, "families": fams}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print({f: (v["resolved"], round(v["widths"]["a"], 2)) for f, v in fams.items()})

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: run it** — `python3 scripts/capture_font_metrics.py`. Expected: 12 families, every one `resolved True` except possibly `Segoe UI Variable`; `a` widths differ per family.

- [ ] **Step 3: write `scripts/verify_font_metrics.py`** (runs on the box)

```python
#!/usr/bin/env python3
"""Fork (Windows claim + bundle) vs the host baseline, per family: fraction of
characters within 0.5 px at 100 px, max |diff|, mean signed diff.
M1 control Arial/Times New Roman/Courier New >= 0.98 (Liberation is metric-compatible
by design: below that the harness measures rendering, not fonts).
M2 Calibri/Cambria >= 0.98. M3 Georgia (Gelasio) >= 0.98. M4 Tahoma (Wine) >= 0.98.
M5 Segoe UI (Selawik), M6 Verdana/Trebuchet MS/Consolas: numbers only."""
import http.server, json, os, pathlib, subprocess, sys, threading
HOME = os.path.expanduser("~")
EXE = os.environ.get("CAMOU_EXE", f"{HOME}/chromium/src/out/Default/chrome")
PY = os.environ.get("CAMOU_VENV", f"{HOME}/camoucrome-verify/venv") + "/bin/python3"
NODE = os.environ.get("PLAYWRIGHT_NODEJS_PATH", f"{HOME}/camoucrome-driver/node")
CLIENT = pathlib.Path(os.environ.get("CAMOU_CLIENT", f"{HOME}/camoucrome-client"))
FONTS_DIR = os.environ.get("CAMOU_FONTS_DIR", str(CLIENT / "fonts"))
FONTS = json.loads((CLIENT / "settings" / "fonts.json").read_text(encoding="utf-8"))
BASE = json.loads((CLIENT / "baselines" / "chrome-8010-stock-font-metrics-windows.json").read_text(encoding="utf-8"))
sys.path.insert(0, str(CLIENT / "scripts")); import capture_font_metrics as cap
WIN = {"ua:osInfo": "Windows NT 10.0; Win64; x64", "ua:platform": "Windows", "ua:platformVersion": "10.0.0", "navigator.platform": "Win32"}
THRESH = {"M1 control": (["Arial", "Times New Roman", "Courier New"], 0.98), "M2 Carlito/Caladea": (["Calibri", "Cambria"], 0.98),
          "M3 Gelasio": (["Georgia"], 0.98), "M4 Wine Tahoma": (["Tahoma"], 0.98)}
REPORT = {"M5 Selawik": ["Segoe UI"], "M6 no clone": ["Verdana", "Trebuchet MS", "Consolas"]}

class H(http.server.BaseHTTPRequestHandler):
    body = b""
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write(H.body)
    def log_message(self, *a): pass

def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    H.body = cap.page(cap.GRID_FAMILIES).encode()
    env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}; env["PLAYWRIGHT_NODEJS_PATH"] = NODE
    cfg = {**WIN, "fonts:list": FONTS["families"]["Windows"]["list"] + FONTS["extra_allowed"]["Windows"], "fonts:alias": FONTS["alias_map"]["Windows"]}
    p = subprocess.run([PY, "-m", "camoucrome.probe", "--driver", "patchright", "--executable", EXE, "--url", f"http://127.0.0.1:{srv.server_port}/",
                        "--config", json.dumps(cfg), "--fonts-dir", FONTS_DIR], capture_output=True, text=True, timeout=180, env=env)
    if p.returncode != 0: sys.exit(p.stderr[-600:])
    fork = json.loads(p.stdout)["report"]; srv.shutdown()
    stats = {}
    for fam, host in BASE["families"].items():
        if not host["resolved"]: stats[fam] = None; continue
        d = [fork[fam]["widths"][c] - host["widths"][c] for c in host["widths"]]
        stats[fam] = {"n": len(d), "within": sum(abs(x) <= 0.5 for x in d) / len(d), "max": max(abs(x) for x in d), "mean": sum(d) / len(d), "resolved": fork[fam]["resolved"]}
    results = {}
    for row, (fams, th) in THRESH.items():
        results[f"{row}: " + ", ".join(f"{f} within={stats[f]['within']:.3f} max={stats[f]['max']:.1f}" for f in fams)] = all(stats[f] and stats[f]["within"] >= th and stats[f]["resolved"] for f in fams)
    for row, fams in REPORT.items():
        print("note:", row, {f: (stats[f] and {k: round(v, 3) for k, v in stats[f].items() if k != "resolved"}) for f in fams})
    n = sum(results.values())
    for k, v in results.items(): print("PASS " if v else "FAIL ", k)
    print(f"{n} PASS {len(results) - n} FAIL"); sys.exit(0 if n == len(results) else 1)

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: push and run on the box** (client copy gets `baselines/` + both scripts; fonts already there). Expected before Task 2: M1, M2 PASS; M3 FAIL (Georgia → Liberation Serif); M4 FAIL (Tahoma → Selawik); notes for M5/M6 with numbers. **This is the RED for Task 2.**

- [ ] **Step 5: commit** `feat(fonts): metric grid capture on the Windows host and the fork verify`

### Task 2: Clones and the CJK OTC

**Files:**
- Modify: `settings/fonts.json` (bundle, alias, script_class, class_font), `scripts/test_fonts.py`
- Regenerate: `settings/fontconfig/*.conf`, `alias_map`

- [ ] **Step 1: manifest edit (python)** — append bundle entries:

```python
{"name": "Gelasio", "family": "Gelasio", "files": ["Gelasio[wght].ttf", "Gelasio-Italic[wght].ttf"],
 "urls": ["https://raw.githubusercontent.com/google/fonts/main/ofl/gelasio/Gelasio%5Bwght%5D.ttf",
          "https://raw.githubusercontent.com/google/fonts/main/ofl/gelasio/Gelasio-Italic%5Bwght%5D.ttf"],
 "sha256": [], "licence_url": "https://raw.githubusercontent.com/google/fonts/main/ofl/gelasio/OFL.txt", "licence": "SIL OFL 1.1",
 "provides": ["Gelasio"], "why": "designed metric-compatible with Georgia (SorkinType)"}
{"name": "Wine Tahoma", "family": "Tahoma", "files": ["tahoma.ttf", "tahomabd.ttf"],
 "urls": ["https://gitlab.winehq.org/wine/wine/-/raw/master/fonts/tahoma.ttf", "https://gitlab.winehq.org/wine/wine/-/raw/master/fonts/tahomabd.ttf"],
 "sha256": [], "licence_url": "https://gitlab.winehq.org/wine/wine/-/raw/master/LICENSE", "licence": "LGPL 2.1+",
 "provides": ["Tahoma"], "why": "the Wine project's Tahoma replacement; the file's family name is Tahoma, so it resolves by its own name"}
```
Replace the `Noto Sans CJK SC` entry with `{"name": "Noto Sans CJK", "family": "Noto Sans CJK", "url": ".../Sans/OTC/NotoSansCJK-Regular.ttc", "files": ["NotoSansCJK-Regular.ttc"], "sha256": "", ..., "provides": ["Noto Sans CJK JP", "Noto Sans CJK KR", "Noto Sans CJK SC", "Noto Sans CJK TC", "Noto Sans CJK HK"]}`.
`alias["Georgia"] = "Gelasio"`. `script_class`: split `cjk` into `cjk_jp/kr/sc/tc/hk` with the name rules from the spec §2. `class_font[os]`: one target per region for both OSes. Test file: licence assertion accepts `{"SIL OFL 1.1", "LGPL 2.1+"}`; `alias_target(Windows, "Georgia") == "Gelasio"`, `("Windows", "Yu Gothic") == "Noto Sans CJK JP"`, `("macOS", "PingFang HK") == "Noto Sans CJK HK"`; a test that every former cjk name is in exactly one region.

- [ ] **Step 2: fetch (fills sha256), regenerate, test** — `python3 scripts/fetch_fonts.py && python3 scripts/gen_fontconfig.py && python3 -m pytest -q scripts/test_fonts.py`. Verify Wine Tahoma is not an alias key (`"Tahoma" not in alias_map.Windows`).

- [ ] **Step 3: box refetch + rerun `verify_font_metrics.py`** — decide: M3/M4 ≥ 0.98 keep, else drop the entry (and record the number). Rerun `verify_fonts_bundle.py` (F2/F3 counts unchanged; Tahoma resolves by name).

- [ ] **Step 4: F9 CJK region pixels** in `verify_fonts_bundle.py`: page draws 骨 and 直 at 64 px in `"Yu Gothic"` and `"Microsoft YaHei"` (Windows claim), reports the two canvases' `toDataURL()`; row passes iff `jp != sc` for at least one glyph. RED noted from the pre-split box run (identical). Note: the emitted `fonts:alias` now carries the region, so no other change.

- [ ] **Step 5: commit** `feat(fonts): Gelasio for Georgia, Wine Tahoma, five-region Noto Sans CJK; F9`

### Task 3: Unique names (F-PSNAME)

**Files:**
- Modify: `scripts/capture_fonts_list.py` (`--names`), `scripts/fetch_fonts.py` (faces), `scripts/gen_fontconfig.py` (`unique_map`), `client/python/camoucrome/gen.py` (`fonts_keys`), `scripts/test_fonts.py`, `client/python/tests/test_gen.py`, `scripts/verify_fonts_bundle.py` (F10, F11)

- [ ] **Step 1: RED** — add F10 to the verify: `local("SegoeUI")` under the current F2 config → status `error` (also measured: `local("Segoe UI")` — the family name works through the alias or not; recorded). Run on the box; expect F10's RED reading.

- [ ] **Step 2: `capture_fonts_list.py --names`** — Windows: push the stdlib name-table parser (already written in this session, `platform 3 / 0x409`, IDs 1/4/6, TTC aware) via `winhost.powershell` `Set-Content` + `python`, parse the JSON; macOS: fontTools over the four dirs. Write `families.<os>.unique_names = {name: {"family": fam, "style": "Regular|Bold|Italic|Bold Italic|<other>"}}` for full and PS names whose family is in the list; skip names equal to the family. Style from name ID 2 (subfamily) when present else from the full name's suffix. Also record `os_version` and `platform_version` (Task 5).

- [ ] **Step 3: `fetch_fonts.py` faces** — after writing each file, parse its name table (same stdlib parser, shared as `scripts/fontnames.py`) and store `entry["faces"] = [{"family", "full", "ps", "style"}]`; `main()` writes the manifest when faces changed.

- [ ] **Step 4: `gen_fontconfig.py unique_map`** — for each OS: for each host unique name → `alias_target(family)` → pick the target's face whose style equals the host style, else Regular → map name → face `full`. Bundled families' own unique names are never keys. `main()` writes `unique_map` beside `alias_map`; `--check` covers it. `gen.fonts_keys` returns `fonts:list` = list + extra_allowed + `sorted(unique_map)` keys and `fonts:alias` = alias_map ∪ unique_map. Tests: `unique_map.Windows["SegoeUI"] == "Selawik"`, `["SegoeUI-Bold"] == "Selawik Bold"`, `["ArialMT"] == "Liberation Sans"`; `gen` test: `"SegoeUI" in fonts:list and fonts:alias["SegoeUI"] == "Selawik"`.

- [ ] **Step 5: F11** — `local("SegoeUI")` and `local("SegoeUI-Bold")` load; the loaded probe face width == `"Segoe UI"` (and bold) width; `local("Selawik")` and `local("Selawik-Regular")` error; the same `local("SegoeUI")` status in a worker equals the page's. Run on the box. If the unique-name lookup does not see the bundle dir: record, stop, document (no C++ on a guess).

- [ ] **Step 6: commit** `feat(fonts): PostScript/full-name aliasing for local() (F-PSNAME)`

### Task 4: Emoji presence F8

- [ ] **Step 1:** page draws U+1F600 at 32 px in `"Segoe UI Emoji"` on a 48×48 canvas; counts pixels with `max(r,g,b) - min(r,g,b) > 32` and alpha > 0. F8: Windows claim + bundle ≥ 50; RED: F1 (no bundle, no config) reads 0 — if the box turns out to have a colour emoji font, the RED becomes a config whose `fonts:list` excludes every emoji family. Commit with Task 3 or alone.

### Task 5: Claim follows the list

- [ ] **Step 1:** capture records `os_version` (`Win32_OperatingSystem.Version`; `sw_vers -productVersion`) and `platform_version` (Windows 10 → `"10.0.0"`, macOS → the product version). Hand-write the values into the manifest for the existing captures too (the same hosts).
- [ ] **Step 2:** `gen.from_pool`: after `config.update(fonts_keys(...))`, if `"fonts:list" in config`: `config["ua:platformVersion"] = fonts["families"][platform]["platform_version"]`. Test: Windows → `"10.0.0"`, macOS → manifest, Linux → pool value.
- [ ] **Step 3:** generator verify on the box (N=10 this time, the doc's number) + `run_coherence_tests.sh`.
- [ ] **Step 4: commit** `feat(gen): ua:platformVersion follows the captured font list's OS version`

### Task 6: Docs, ledger, roadmap, push

- [ ] `docs/superpowers/measurements/2026-09-11-fonts-metrics.md`: the grid (table per family: within/max/mean), clones kept/dropped with numbers, CJK split, F-PSNAME result, emoji, platformVersion, and §"closed by fact" (macOS build 47 GiB, WebGL 151, hinting/AA, invariant reports only, one hop, N=10 count).
- [ ] fonts bundle doc §4 rewritten to what remains; roadmap C row; ledger; CLAUDE.md untouched unless a path changed; CI workflow adds nothing (tests already run).
- [ ] `check_checkout_sync.sh` PASS (no C++ change expected), commit, push, `gh run list`.

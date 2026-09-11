# Open Items Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the five items of `docs/superpowers/specs/2026-09-11-open-items-design.md`: one Windows-host/Mac capture round, the WebGL profile database, the locale→zone table, the open-font bundle with fontconfig aliases, and the chrome-binary to-dos.

**Architecture:** Reference data is captured once from stock Chrome 153.0.8010.36 on the box's Windows host (PowerShell over `ssh buildpc`) and from headed Chrome on the Mac, into `settings/` JSON with provenance. The generator (`client/python/camoucrome/gen.py`) reads three new tables (`settings/webgl/*.json`, `settings/locale_zones.json`, `settings/fonts.json`); the launchers gain one env duty (`FONTCONFIG_FILE`); `package.py` ships `fonts/` + two generated fontconfig files. Every verify runs on the box's `chrome` through `python -m camoucrome.probe`, RED first.

**Tech Stack:** Python 3.12 (box venv: patchright 1.62.3, browserforge 1.2.4), PowerShell over OpenSSH on the Windows host, fontconfig 2.15, Go 1.22 + playwright-go, Node 24.

## Global Constraints

- No JavaScript injection into page-visible scopes; every verify reads the page's own `<pre id="o">` through the probe (spec, CLAUDE.md).
- Windows-host launches always use a temp `--user-data-dir`, never the host's own Chrome profile (spec §3).
- A SwiftShader renderer string is not a profile; `capture_webgl_profile.py` refuses to write one (spec §3).
- fontconfig aliases are `binding="strong"`; the conf lists the bundled dir only, `<dir prefix="relative">../fonts</dir>`, `<cachedir prefix="xdg">camoucrome-fontconfig</cachedir>` (spec §1).
- Bundled fonts: SIL OFL 1.1 only (Selawik, Liberation 2.1.5, Carlito, Caladea, Noto Sans, Noto Serif, Noto Sans Symbols, Noto Sans CJK SC, Noto Color Emoji, Inter); no proprietary file (spec §1).
- `--timezone` optional; a locale not in `settings/locale_zones.json` refuses with the existing message (spec §4).
- `headless_shell` closed by decision, no code (spec §5).
- Box access: `source scratchpad/buildpc.sh` gives `runwsl '<bash>'` and `pushfile <local> <remote>`; long jobs run in the foreground under a Monitor; the Windows side is reached with `/usr/bin/ssh … buildpc '<powershell>'`.
- Commit every task; push after each green verify.

---

## File structure

| path | responsibility |
|---|---|
| `scripts/winhost.py` | run a PowerShell snippet on the Windows host, launch stock Chrome there on a temp profile with `--dump-dom` of a local HTML page, return the page's `#o` JSON |
| `scripts/capture_webgl_profile.py` | the WebGL page (both contexts, every numeric pname, extensions, precision formats, context attributes) + writers for Windows-host / Mac-headed / box; refuses SwiftShader |
| `settings/webgl/<id>.json` | one profile per (OS, GPU) |
| `scripts/capture_fonts_list.py` | family lists from the Windows host (PowerShell) and the Mac (`system_profiler`) → `settings/fonts.json` `families.*` |
| `settings/fonts.json` | bundle sources (url, sha256, licence file), alias table, script-class table, captured family lists |
| `scripts/fetch_fonts.py` | download + verify the bundle into `fonts/` |
| `scripts/gen_fontconfig.py` | `settings/fonts.json` → `settings/fontconfig/{windows,macos}.conf`, `--check` |
| `settings/locale_zones.json` | locale tag → IANA zones |
| `client/python/camoucrome/gen.py` | `--gpu`, `--timezone` optional via the table, `fonts:list` from `settings/fonts.json` |
| `client/python/camoucrome/launcher.py`, `client/go/camoucrome.go`, `client/node/index.js`, `settings/launcher.json` | `FONTCONFIG_FILE` duty |
| `scripts/package.py` | copies `fonts/` + `settings/fontconfig/` into the archive, stamp `fonts` |
| `scripts/capture_chrome_object.py`, `baselines/chrome-8010-stock-window-chrome.json`, `scripts/verify_chrome_object.py` | `window.chrome` tree + plugins capture and diff |
| `scripts/verify_webgl_profile.py`, `scripts/verify_fonts_bundle.py`, `scripts/verify_sp7_phonehome.py` (P4) | verifies |
| docs: `measurements/2026-09-11-webgl-profiles.md`, `2026-09-11-fonts-bundle.md`, `2026-09-11-chrome-binary-items.md`, generator doc §5, roadmap, SP2 spec D4, ledger | records |

---

### Task 1: Windows-host runner and the capture page harness

**Files:**
- Create: `scripts/winhost.py`
- Test: manual RED/GREEN on the host (no unit test: the module is an ssh wrapper)

**Interfaces:**
- Produces: `winhost.powershell(script: str) -> str` (stdout, CRs stripped); `winhost.dump_dom(html: str, args: list[str], headed=False) -> dict` — writes `html` to `C:\Users\<user>\AppData\Local\Temp\camou_<pid>.html` on the host, launches `C:\Program Files\Google\Chrome\Application\chrome.exe` with a temp `--user-data-dir`, `--no-first-run`, `--no-default-browser-check`, `--headless=new` (unless `headed`), `--dump-dom file:///…`, `args`, parses the `<pre id="o">` text as JSON; `winhost.CHROME` constant; raises `RuntimeError` with the tail of stderr when no `#o` is found.

- [ ] **Step 1: Write the module**

```python
"""Runs stock Chrome 153.0.8010.36 on the build box's Windows host (the
same tag as the pin) and returns what a page reports. PowerShell over
OpenSSH; every launch gets a temp profile and --dump-dom, so nothing on
the host's own Chrome is touched. Linux side: scripts/lib_shell.py."""
import json
import os
import re
import subprocess

SSH = ["/usr/bin/ssh", "-o", "BatchMode=yes", "-o", "PasswordAuthentication=no",
       "-o", "PubkeyAuthentication=no", "-o", "ControlMaster=no",
       "-o", f"ControlPath={os.path.expanduser('~')}/.ssh/cm-buildpc", "buildpc"]
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def powershell(script):
    p = subprocess.run(SSH + [script], capture_output=True, text=True, timeout=300)
    if p.returncode != 0:
        raise RuntimeError(f"powershell rc={p.returncode}: {p.stderr[-800:]}")
    return p.stdout.replace("\r", "")


def dump_dom(html, args=(), headed=False, timeout_s=60):
    """Loads `html` (a page that writes JSON into <pre id="o">) in stock Chrome
    on the host and returns that JSON."""
    b64 = __import__("base64").b64encode(html.encode()).decode()
    argv = ["--no-first-run", "--no-default-browser-check", "--disable-gpu-sandbox", *args]
    if not headed:
        argv.insert(0, "--headless=new")
    ps = f"""
$tmp = Join-Path $env:TEMP ("camou_" + $PID)
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$html = Join-Path $tmp "page.html"
[IO.File]::WriteAllBytes($html, [Convert]::FromBase64String("{b64}"))
$out = Join-Path $tmp "dom.html"
$err = Join-Path $tmp "err.txt"
$p = Start-Process -FilePath "{CHROME}" -ArgumentList @({", ".join(json.dumps(a) for a in argv)}, "--user-data-dir=$tmp\\profile", "--dump-dom", "file:///$($html -replace '\\\\','/')") -RedirectStandardOutput $out -RedirectStandardError $err -PassThru -WindowStyle Hidden
if (-not $p.WaitForExit({timeout_s * 1000})) {{ $p.Kill(); "TIMEOUT" }}
Get-Content -Raw $out
"----STDERR----"
Get-Content -Raw $err
Remove-Item -Recurse -Force $tmp
"""
    out = powershell(ps)
    m = re.search(r'<pre id="o">(.*?)</pre>', out, re.S)
    if not m:
        raise RuntimeError("no #o in the dumped DOM: " + out[-800:])
    return json.loads(__import__("html").unescape(m.group(1)))
```

- [ ] **Step 2: RED — a page with no `#o` raises**

Run: `python3 -c "import sys; sys.path.insert(0,'scripts'); import winhost; winhost.dump_dom('<html>x</html>')"`
Expected: `RuntimeError: no #o in the dumped DOM`

- [ ] **Step 3: GREEN — the host's stock Chrome reports its UA**

Run: `python3 -c "import sys; sys.path.insert(0,'scripts'); import winhost; print(winhost.dump_dom('<pre id=o></pre><script>document.getElementById(\"o\").textContent=JSON.stringify({ua:navigator.userAgent, plat:navigator.platform})</script>'))"`
Expected: `{'ua': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) … HeadlessChrome/153.0.8010.36 …', 'plat': 'Win32'}`

- [ ] **Step 4: Commit**

```bash
git add scripts/winhost.py
git commit -m "feat(harness): run stock Chrome 153 on the box's Windows host with --dump-dom"
```

---

### Task 2: WebGL profile capture (Windows host, Mac, refusal of SwiftShader)

**Files:**
- Create: `scripts/capture_webgl_profile.py`, `settings/webgl/windows-intel-uhd-630-d3d11.json`, `settings/webgl/macos-apple-m1-pro-metal.json`
- Test: `scripts/test_capture_webgl_profile.py` (the SwiftShader refusal and the file shape)

**Interfaces:**
- Produces: `PAGE` (HTML string reporting `{webgl: {vendor, renderer, parameters, supportedExtensions, shaderPrecisionFormats, contextAttributes}, webgl2: {...}}`); `profile_from_report(report, id, os, provenance) -> dict` raising `ValueError("SwiftShader is not a profile")` when either renderer contains `SwiftShader`; CLI `capture_webgl_profile.py --where winhost|mac|box --id ID --os Windows|macOS|Linux [--angle d3d11]` writing `settings/webgl/<id>.json`.
- Profile file keys: `id, os, vendor, renderer, webgl, webgl2, provenance` exactly as spec §3.

- [ ] **Step 1: Write the failing test**

```python
# scripts/test_capture_webgl_profile.py
import json, pathlib, sys
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import capture_webgl_profile as c

SW = "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)"
D3D = "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00003E92) Direct3D11 vs_5_0 ps_5_0, D3D11)"

def ctx(renderer):
    return {"vendor": "Google Inc. (Intel)", "renderer": renderer,
            "parameters": {"3379": 16384}, "supportedExtensions": ["ANGLE_instanced_arrays"],
            "shaderPrecisionFormats": {"VERTEX_SHADER/HIGH_FLOAT": [127, 127, 23]},
            "contextAttributes": {"alpha": True}}

def test_swiftshader_is_refused():
    with pytest.raises(ValueError, match="SwiftShader"):
        c.profile_from_report({"webgl": ctx(SW), "webgl2": ctx(D3D)}, "x", "Windows", {})

def test_profile_shape():
    p = c.profile_from_report({"webgl": ctx(D3D), "webgl2": ctx(D3D)}, "windows-intel", "Windows", {"how": "test"})
    assert list(p) == ["id", "os", "vendor", "renderer", "webgl", "webgl2", "provenance"]
    assert p["renderer"] == D3D and p["webgl2"]["parameters"] == {"3379": 16384}
    assert "37445" not in p["webgl"]["parameters"] and "37446" not in p["webgl"]["parameters"]

def test_page_enumerates_every_numeric_pname_by_name():
    assert "MAX_TEXTURE_SIZE" in c.PAGE and "MAX_3D_TEXTURE_SIZE" in c.PAGE
    assert "UNMASKED_RENDERER_WEBGL" in c.PAGE
```

- [ ] **Step 2: Run it, expect ModuleNotFoundError**

Run: `python3 -m pytest -q scripts/test_capture_webgl_profile.py`
Expected: `ModuleNotFoundError: No module named 'capture_webgl_profile'`

- [ ] **Step 3: Write the capture module**

```python
#!/usr/bin/env python3
"""Captures a WebGL profile (settings/webgl/<id>.json) from a real GPU.

    capture_webgl_profile.py --where winhost --id windows-intel-uhd-630-d3d11 --os Windows
    capture_webgl_profile.py --where mac     --id macos-apple-m1-pro-metal   --os macOS
    capture_webgl_profile.py --where box     --id ID --os Linux              (out/Default chrome)

The page reads both contexts: every numeric getParameter pname in the
WebGL/WebGL2 IDL constant tables (enumerated by name below, so a typo is a
missing key, not a wrong number), getSupportedExtensions(), the 18
getShaderPrecisionFormat cells and getContextAttributes(). String pnames
are identity, held by vendor/renderer. A SwiftShader renderer is the host's
software fallback, not a device: refused (the Windows headless launch
self-adds --use-angle=swiftshader-webgl unless --use-angle is given).
"""
import argparse, datetime, json, os, pathlib, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = pathlib.Path(__file__).resolve().parent.parent
GL1 = ["MAX_TEXTURE_SIZE", "MAX_CUBE_MAP_TEXTURE_SIZE", "MAX_RENDERBUFFER_SIZE",
       "MAX_VIEWPORT_DIMS", "MAX_VERTEX_ATTRIBS", "MAX_VERTEX_UNIFORM_VECTORS",
       "MAX_VARYING_VECTORS", "MAX_FRAGMENT_UNIFORM_VECTORS", "MAX_TEXTURE_IMAGE_UNITS",
       "MAX_VERTEX_TEXTURE_IMAGE_UNITS", "MAX_COMBINED_TEXTURE_IMAGE_UNITS",
       "ALIASED_LINE_WIDTH_RANGE", "ALIASED_POINT_SIZE_RANGE", "SUBPIXEL_BITS",
       "RED_BITS", "GREEN_BITS", "BLUE_BITS", "ALPHA_BITS", "DEPTH_BITS", "STENCIL_BITS",
       "SAMPLE_BUFFERS", "SAMPLES", "IMPLEMENTATION_COLOR_READ_TYPE",
       "IMPLEMENTATION_COLOR_READ_FORMAT"]
GL2 = GL1 + ["MAX_3D_TEXTURE_SIZE", "MAX_ARRAY_TEXTURE_LAYERS", "MAX_COLOR_ATTACHMENTS",
             "MAX_COMBINED_FRAGMENT_UNIFORM_COMPONENTS", "MAX_COMBINED_UNIFORM_BLOCKS",
             "MAX_COMBINED_VERTEX_UNIFORM_COMPONENTS", "MAX_DRAW_BUFFERS",
             "MAX_ELEMENT_INDEX", "MAX_ELEMENTS_INDICES", "MAX_ELEMENTS_VERTICES",
             "MAX_FRAGMENT_INPUT_COMPONENTS", "MAX_FRAGMENT_UNIFORM_BLOCKS",
             "MAX_FRAGMENT_UNIFORM_COMPONENTS", "MAX_PROGRAM_TEXEL_OFFSET", "MAX_SAMPLES",
             "MAX_SERVER_WAIT_TIMEOUT", "MAX_TEXTURE_LOD_BIAS",
             "MAX_TRANSFORM_FEEDBACK_INTERLEAVED_COMPONENTS",
             "MAX_TRANSFORM_FEEDBACK_SEPARATE_ATTRIBS",
             "MAX_TRANSFORM_FEEDBACK_SEPARATE_COMPONENTS", "MAX_UNIFORM_BLOCK_SIZE",
             "MAX_UNIFORM_BUFFER_BINDINGS", "MAX_VARYING_COMPONENTS",
             "MAX_VERTEX_OUTPUT_COMPONENTS", "MAX_VERTEX_UNIFORM_BLOCKS",
             "MAX_VERTEX_UNIFORM_COMPONENTS", "MIN_PROGRAM_TEXEL_OFFSET",
             "UNIFORM_BUFFER_OFFSET_ALIGNMENT"]
EXT_PNAMES = {"EXT_texture_filter_anisotropic": ["MAX_TEXTURE_MAX_ANISOTROPY_EXT"],
              "WEBGL_draw_buffers": ["MAX_COLOR_ATTACHMENTS_WEBGL", "MAX_DRAW_BUFFERS_WEBGL"],
              "OES_standard_derivatives": [], "WEBGL_debug_renderer_info": []}

PAGE = """<!doctype html><title>webgl-profile</title><pre id="o"></pre><script>
const GL1 = %s, GL2 = %s, EXT = %s;
const SH = ['VERTEX_SHADER', 'FRAGMENT_SHADER'], PR = ['LOW_FLOAT','MEDIUM_FLOAT','HIGH_FLOAT','LOW_INT','MEDIUM_INT','HIGH_INT'];
function read(kind, names) {
  const gl = document.createElement('canvas').getContext(kind);
  if (!gl) return null;
  const d = gl.getExtension('WEBGL_debug_renderer_info');
  const parameters = {};
  for (const n of names) { const v = gl.getParameter(gl[n]); parameters[String(gl[n])] = ArrayBuffer.isView(v) ? Array.from(v) : v; }
  for (const [e, ns] of Object.entries(EXT)) { const x = gl.getExtension(e); if (x) for (const n of ns) { const v = gl.getParameter(x[n]); parameters[String(x[n])] = ArrayBuffer.isView(v) ? Array.from(v) : v; } }
  const spf = {};
  for (const s of SH) for (const p of PR) { const f = gl.getShaderPrecisionFormat(gl[s], gl[p]); spf[s + '/' + p] = [f.rangeMin, f.rangeMax, f.precision]; }
  return { vendor: gl.getParameter(d.UNMASKED_VENDOR_WEBGL), renderer: gl.getParameter(d.UNMASKED_RENDERER_WEBGL),
           parameters, supportedExtensions: gl.getSupportedExtensions(), shaderPrecisionFormats: spf,
           contextAttributes: gl.getContextAttributes() };
}
document.getElementById('o').textContent = JSON.stringify({ webgl: read('webgl', GL1), webgl2: read('webgl2', GL2) });
</script>""" % (json.dumps(GL1), json.dumps(GL2), json.dumps(EXT_PNAMES))


def profile_from_report(report, id, os_name, provenance):
    for k in ("webgl", "webgl2"):
        ctx = report.get(k)
        if not ctx:
            raise ValueError(f"{k}: no context")
        if "SwiftShader" in ctx["renderer"] or "SwiftShader" in ctx["vendor"]:
            raise ValueError(f"{k}: SwiftShader is not a profile: {ctx['renderer']}")
    w = report["webgl"]
    return {"id": id, "os": os_name, "vendor": w["vendor"], "renderer": w["renderer"],
            "webgl": {k: w[k] for k in ("parameters", "supportedExtensions", "shaderPrecisionFormats", "contextAttributes")},
            "webgl2": {k: report["webgl2"][k] for k in ("parameters", "supportedExtensions", "shaderPrecisionFormats", "contextAttributes")},
            "provenance": provenance}


def capture_winhost(angle):
    import winhost
    attempts = [(["--use-angle=" + angle], False), (["--use-gl=angle", "--use-angle=" + angle], False), (["--use-angle=" + angle], True)]
    for args, headed in attempts:
        r = winhost.dump_dom(PAGE, args, headed=headed)
        if r["webgl"] and "SwiftShader" not in r["webgl"]["renderer"]:
            return r, {"binary": "Google Chrome 153.0.8010.36 (stock, the build box's Windows 10 host)",
                       "how": "scripts/capture_webgl_profile.py --where winhost", "headless": not headed, "args": args}
    raise SystemExit("every attempt reported SwiftShader; no profile written")


def capture_mac():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=False, args=["--window-size=300,200", "--window-position=0,0"])
        pg = b.new_page(); pg.set_content(PAGE); r = json.loads(pg.locator("#o").text_content()); ver = b.version; b.close()
    return r, {"binary": f"Google Chrome {ver} (stock, the Mac, headed 300x200: headless gives no context)",
               "how": "scripts/capture_webgl_profile.py --where mac", "headless": False}


def capture_box():
    import lib_shell
    values, err = lib_shell.session(None, ["() => JSON.parse(document.getElementById('o').textContent)"],
                                    navigate_to="data:text/html;base64," + __import__("base64").b64encode(PAGE.encode()).decode(),
                                    shell=lib_shell.CHROME, extra_flags=lib_shell.CHROME_FLAGS)
    if err:
        raise SystemExit(err)
    return values[0], {"binary": "fork chrome out/Default (box)", "how": "scripts/capture_webgl_profile.py --where box", "headless": True}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--where", choices=["winhost", "mac", "box"], required=True)
    ap.add_argument("--id", required=True); ap.add_argument("--os", required=True, choices=["Windows", "macOS", "Linux"])
    ap.add_argument("--angle", default="d3d11"); ap.add_argument("--out", default=str(ROOT / "settings" / "webgl"))
    a = ap.parse_args()
    report, prov = {"winhost": lambda: capture_winhost(a.angle), "mac": capture_mac, "box": capture_box}[a.where]()
    prov["captured"] = datetime.date.today().isoformat()
    profile = profile_from_report(report, a.id, a.os, prov)
    path = pathlib.Path(a.out) / f"{a.id}.json"; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=1) + "\n")
    print(f"{path}: {profile['renderer']} | {len(profile['webgl']['parameters'])}/{len(profile['webgl2']['parameters'])} pnames, "
          f"{len(profile['webgl']['supportedExtensions'])}/{len(profile['webgl2']['supportedExtensions'])} ext")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Tests pass**

Run: `python3 -m pytest -q scripts/test_capture_webgl_profile.py`
Expected: `3 passed`

- [ ] **Step 5: RED on the box — SwiftShader refused**

Run (box, via `runwsl`): `cd ~/camoucrome-verify && venv/bin/python3 capture_webgl_profile.py --where box --id sw --os Linux --out /home/lang/wgl`
Expected: exits with `SwiftShader is not a profile: ANGLE (Google, Vulkan 1.3.0 (SwiftShader …`

- [ ] **Step 6: Capture Windows and Mac**

Run: `python3 scripts/capture_webgl_profile.py --where winhost --id windows-intel-uhd-630-d3d11 --os Windows`
Expected: `settings/webgl/windows-intel-uhd-630-d3d11.json: ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00003E92) Direct3D11 vs_5_0 ps_5_0, D3D11) | 24/52 pnames, N/M ext` (the pname counts are the two lists' lengths plus extension pnames; record what prints)
Run: `python3 scripts/capture_webgl_profile.py --where mac --id macos-apple-m1-pro-metal --os macOS`
Expected: `… ANGLE (Apple, ANGLE Metal Renderer: Apple M1 Pro, Unspecified Version) …`

- [ ] **Step 7: Commit**

```bash
git add scripts/capture_webgl_profile.py scripts/test_capture_webgl_profile.py settings/webgl/
git commit -m "feat(sp5b): WebGL profile capture; first two real-GPU profiles (Intel UHD 630 D3D11, Apple M1 Pro Metal)"
```

---

### Task 3: Generator emits a WebGL profile (`--gpu`)

**Files:**
- Modify: `client/python/camoucrome/gen.py` (`from_pool`, `generate`, `main`, the "Never taken" docstring block)
- Modify: `client/go/generate.go` (`Generate` gains `gpu string`), `client/go/camoucrome_test.go`
- Test: `client/python/tests/test_gen.py`

**Interfaces:**
- Produces: `gen.load_profiles() -> dict[id, profile]` (reads `settings/webgl/*.json`, path from `ROOT`); `gen.webgl_keys(profile) -> dict` with `webGl:vendor`, `webGl:renderer`, `webGl2:vendor`, `webGl2:renderer`, `webGl:parameters`, `webGl2:parameters`, `webGl:supportedExtensions`, `webGl2:supportedExtensions`; `generate(os=None, timezone=None, locale=None, seed=None, gpu=None)`: `gpu` an id, else the first profile whose `os` equals the claimed OS, else no keys. Go: `Generate(python, osName, timezone, locale, gpu string, seed int)`.

- [ ] **Step 1: Failing tests**

```python
# append to client/python/tests/test_gen.py
def test_webgl_profile_keys_follow_the_claimed_os():
    profiles = gen.load_profiles()
    assert "windows-intel-uhd-630-d3d11" in profiles
    keys = gen.webgl_keys(profiles["windows-intel-uhd-630-d3d11"])
    assert set(keys) == {"webGl:vendor", "webGl:renderer", "webGl2:vendor", "webGl2:renderer",
                         "webGl:parameters", "webGl2:parameters", "webGl:supportedExtensions", "webGl2:supportedExtensions"}
    assert set(keys) <= KEYS
    assert "Direct3D11" in keys["webGl:renderer"] and keys["webGl2:renderer"] == keys["webGl:renderer"]
    assert all(k.isdigit() for k in keys["webGl:parameters"])

def test_from_pool_picks_the_os_profile_and_gpu_overrides():
    out = gen.from_pool(POOL, "America/New_York", rng=random.Random(1))
    assert "Direct3D11" in out["config"]["webGl:renderer"]
    mac = gen.from_pool(POOL, "America/New_York", rng=random.Random(1), gpu="macos-apple-m1-pro-metal")
    assert "Metal" in mac["config"]["webGl:renderer"]
    with pytest.raises(KeyError):
        gen.from_pool(POOL, "America/New_York", rng=random.Random(1), gpu="no-such-profile")
```

- [ ] **Step 2: Run, expect AttributeError on `load_profiles`**

Run: `python3 -m pytest -q client/python/tests/test_gen.py -k webgl`
Expected: `AttributeError: module 'camoucrome.gen' has no attribute 'load_profiles'`

- [ ] **Step 3: Implement**

In `gen.py` add (module level, after `DEVICE_MEMORY`):

```python
ROOT = pathlib.Path(__file__).resolve().parents[3]


def load_profiles():
    """settings/webgl/*.json by id: real-GPU captures (capture_webgl_profile.py)."""
    return {p.stem: json.loads(p.read_text()) for p in sorted((ROOT / "settings" / "webgl").glob("*.json"))}


def webgl_keys(profile):
    return {"webGl:vendor": profile["vendor"], "webGl:renderer": profile["renderer"],
            "webGl2:vendor": profile["vendor"], "webGl2:renderer": profile["renderer"],
            "webGl:parameters": profile["webgl"]["parameters"],
            "webGl2:parameters": profile["webgl2"]["parameters"],
            "webGl:supportedExtensions": profile["webgl"]["supportedExtensions"],
            "webGl2:supportedExtensions": profile["webgl2"]["supportedExtensions"]}


def profile_for(platform, gpu=None):
    profiles = load_profiles()
    if gpu:
        return profiles[gpu]
    return next((p for p in profiles.values() if p["os"] == platform), None)
```

`from_pool(fp, timezone, locale=None, rng=None, gpu=None)`: after `config.update(per_instance_config(rng))` add

```python
    profile = profile_for(platform, gpu)
    if profile:
        config.update(webgl_keys(profile))
```

`generate(os=None, timezone=None, locale=None, seed=None, gpu=None)` passes `gpu` to `from_pool`; `main()` adds `ap.add_argument("--gpu", help="a settings/webgl profile id; default: the first profile for the claimed OS")` and passes `a.gpu`. Replace the docstring's "No `webGl:*`" paragraph with: "`webGl:*` comes from `settings/webgl/` (real-GPU captures); an OS with no profile gets none." Add `import pathlib` if missing. In `client/go/generate.go`, `Generate(python, osName, timezone, locale, gpu string, seed int)` appends `"--gpu", gpu` when non-empty; update its test call.

- [ ] **Step 4: Tests pass**

Run: `python3 -m pytest -q client/python/tests && (cd client/go && go test ./...)`
Expected: all pass (gen tests 12 + launcher 7; go ok)

- [ ] **Step 5: Commit**

```bash
git add client/python/camoucrome/gen.py client/python/tests/test_gen.py client/go/generate.go client/go/camoucrome_test.go
git commit -m "feat(gen): emit webGl:* from the profile database, --gpu selects a profile"
```

---

### Task 4: `verify_webgl_profile.py` (box, RED first) + doc

**Files:**
- Create: `scripts/verify_webgl_profile.py`, `docs/superpowers/measurements/2026-09-11-webgl-profiles.md`
- Modify: roadmap A3 #2, `client/python/camoucrome/gen.py` docstring already done, generator doc §4 line

**Interfaces:**
- Consumes: `python -m camoucrome.probe --config JSON --url URL` (Task 0 infra), `settings/webgl/*.json`, `gen.webgl_keys`.

- [ ] **Step 1: Write the verify**

```python
"""WebGL profile database (spec §3) on chrome through the client probe.

W1 RED-by-construction: no config -> the host's SwiftShader renderer and limits.
W2 Windows profile on a Windows claim: vendor/renderer read back on both
   contexts; every emitted numeric parameter equal; extension list equal as a
   set AND getExtension(name) non-null for every claimed name; strict start,
   zero camoucfg: lines.
W3 macOS profile on a macOS claim: same; W3-RED: the macOS profile on a
   Windows claim is refused under strict (webgl-renderer-backend-fits-os).
W4 informational: shaderPrecisionFormats / contextAttributes host vs profile
   diff count per context (keys not emitted; the doc says whether they must be).
"""
import json, os, pathlib, subprocess, sys, tempfile
import http.server, threading
HOME = os.path.expanduser("~")
EXE = os.environ.get("CAMOU_EXE", f"{HOME}/chromium/src/out/Default/chrome")
PY = os.environ.get("CAMOU_VENV", f"{HOME}/camoucrome-verify/venv") + "/bin/python3"
NODE = os.environ.get("PLAYWRIGHT_NODEJS_PATH", f"{HOME}/camoucrome-driver/node")
WEBGL_DIR = pathlib.Path(os.environ.get("CAMOU_WEBGL_DIR", f"{HOME}/camoucrome-client/settings/webgl"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capture_webgl_profile import PAGE  # the same page: what a profile captures is what a page reads

WIN = {"ua:osInfo": "Windows NT 10.0; Win64; x64", "ua:platform": "Windows", "ua:platformVersion": "15.0.0", "navigator.platform": "Win32"}
MAC = {"ua:osInfo": "Macintosh; Intel Mac OS X 10_15_7", "ua:platform": "macOS", "ua:platformVersion": "14.6.1", "navigator.platform": "MacIntel"}


def keys_of(profile):
    return {"webGl:vendor": profile["vendor"], "webGl:renderer": profile["renderer"], "webGl2:vendor": profile["vendor"],
            "webGl2:renderer": profile["renderer"], "webGl:parameters": profile["webgl"]["parameters"],
            "webGl2:parameters": profile["webgl2"]["parameters"], "webGl:supportedExtensions": profile["webgl"]["supportedExtensions"],
            "webGl2:supportedExtensions": profile["webgl2"]["supportedExtensions"]}


PAGE2 = PAGE.replace("contextAttributes: gl.getContextAttributes() };",
                     "contextAttributes: gl.getContextAttributes(), extOk: Object.fromEntries(gl.getSupportedExtensions().map(e => [e, gl.getExtension(e) !== null])) };")


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        b = PAGE2.encode(); self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass


def probe(url, config=None, strict=False):
    env = {k: v for k, v in os.environ.items() if not k.startswith("CAMOU_")}; env["PLAYWRIGHT_NODEJS_PATH"] = NODE
    cmd = [PY, "-m", "camoucrome.probe", "--driver", "patchright", "--executable", EXE, "--url", url]
    if config is not None: cmd += ["--config", json.dumps(config)]
    if strict: cmd.append("--strict")
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env)
    rep = json.loads(p.stdout)["report"] if p.returncode == 0 else None
    return rep, p.stderr


def matches(rep, profile, ctx, notes, tag):
    r, want = rep[ctx], profile[ctx]
    ok = r["vendor"] == profile["vendor"] and r["renderer"] == profile["renderer"]
    bad = [k for k, v in want["parameters"].items() if r["parameters"].get(k) != v]
    ok = ok and not bad and set(r["supportedExtensions"]) == set(want["supportedExtensions"]) and all(r["extOk"].get(e) for e in want["supportedExtensions"])
    if not ok:
        notes.append(f"{tag}/{ctx}: renderer={r['renderer'][:50]!r} badparams={bad[:5]} extdiff={sorted(set(r['supportedExtensions']) ^ set(want['supportedExtensions']))[:5]} extnull={[e for e in want['supportedExtensions'] if not r['extOk'].get(e)][:5]}")
    return ok


def main():
    results, notes = {}, []
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"
    win = json.loads((WEBGL_DIR / "windows-intel-uhd-630-d3d11.json").read_text())
    mac = json.loads((WEBGL_DIR / "macos-apple-m1-pro-metal.json").read_text())
    host, _ = probe(url)
    results["W1 no config: host SwiftShader renderer and limits"] = host is not None and "SwiftShader" in host["webgl"]["renderer"] and host["webgl"]["parameters"] != win["webgl"]["parameters"]
    rep, log = probe(url, {**WIN, **keys_of(win)}, strict=True)
    results["W2 Windows profile: identity, every parameter, extension set + getExtension non-null, both contexts, strict, zero camoucfg lines"] = rep is not None and matches(rep, win, "webgl", notes, "W2") and matches(rep, win, "webgl2", notes, "W2") and "camoucfg:" not in log
    if rep is None: notes.append("W2 launch: " + log[-300:])
    rep, log = probe(url, {**MAC, **keys_of(mac)}, strict=True)
    results["W3 macOS profile on a macOS claim: same"] = rep is not None and matches(rep, mac, "webgl", notes, "W3") and matches(rep, mac, "webgl2", notes, "W3") and "camoucfg:" not in log
    red, log = probe(url, {**WIN, **keys_of(mac)}, strict=True)
    results["W3-RED macOS profile on a Windows claim refused under strict (webgl-renderer-backend-fits-os)"] = red is None and "webgl-renderer-backend-fits-os" in log
    if rep:
        for ctx in ("webgl", "webgl2"):
            d1 = sum(1 for k, v in mac[ctx]["shaderPrecisionFormats"].items() if rep[ctx]["shaderPrecisionFormats"].get(k) != v)
            d2 = sum(1 for k, v in mac[ctx]["contextAttributes"].items() if rep[ctx]["contextAttributes"].get(k) != v)
            notes.append(f"W4 {ctx}: shaderPrecisionFormats differ in {d1}/18 cells, contextAttributes in {d2} (host vs macOS profile; keys not emitted)")
    srv.shutdown()
    for k, v in results.items(): print("PASS " if v else "FAIL ", k)
    for n in notes: print("  " + n)
    n = sum(results.values()); print(f"{n} PASS {len(results) - n} FAIL"); sys.exit(0 if n == len(results) else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: RED on the box**

Before the profiles exist on the box (`CAMOU_WEBGL_DIR=/nonexistent`) the script must fail at the file read — that proves it reads the files; then with the profiles pushed, run once and read the W4 notes. Expected first real run: W1 PASS, W2/W3 PASS (the fork already replays `webGl:parameters`), W3-RED PASS. If W2 fails on `extnull`, the profile names an extension the SwiftShader host cannot back: record the list in the doc and drop those names from the profile's `supportedExtensions` with a `provenance.dropped_extensions` entry.

- [ ] **Step 3: Doc `2026-09-11-webgl-profiles.md`** — §1 the two captures (renderer strings, pname counts, which launch attempt gave the Intel string), §2 the verify table with counts, §3 W4's precision/attribute diff and whether those keys need emitting, §4 open (two profiles; AMD/NVIDIA one capture away; sampling weights). Roadmap A3 #2 → SHIPPED with the doc; generator doc §4 "No webGl" line replaced.

- [ ] **Step 4: Commit + push**

```bash
git add scripts/verify_webgl_profile.py docs/superpowers/measurements/2026-09-11-webgl-profiles.md docs/superpowers/plans/2026-09-09-completion-roadmap.md docs/superpowers/measurements/2026-09-10-sp6b-generator.md settings/webgl
git commit -m "feat(sp5b): verify the WebGL profiles on chrome; A3 #2 shipped with two real-GPU profiles"
```

---

### Task 5: Locale → zone table

**Files:**
- Create: `settings/locale_zones.json`
- Modify: `client/python/camoucrome/gen.py` (`generate`, `from_pool`, `main`), `client/go/generate.go` (timezone may be empty)
- Test: `client/python/tests/test_gen.py`

**Interfaces:**
- Produces: `gen.zone_for(locale: str, rng: random.Random) -> str` raising `ValueError` for an unknown locale; `settings/locale_zones.json` = `{"$comment": "...", "zones": {"en-US": ["America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles"], ...}}` with the 46 tags of spec §4.

- [ ] **Step 1: Failing tests**

```python
def test_zone_table_is_valid_iana_and_tags_parse():
    import zoneinfo
    table = json.loads((ROOT / "settings" / "locale_zones.json").read_text())["zones"]
    assert len(table) >= 40
    avail = zoneinfo.available_timezones()
    for tag, zones in table.items():
        assert re.fullmatch(r"[a-z]{2,3}-[A-Z]{2}", tag), tag
        assert zones and all(z in avail for z in zones), tag

def test_timezone_defaults_from_the_locale_table():
    out = gen.from_pool(POOL, None, "fr-FR", rng=random.Random(3))
    assert out["config"]["timezone:id"] == "Europe/Paris"
    a = gen.from_pool(POOL, None, None, rng=random.Random(5))["config"]["timezone:id"]  # pool language en-US
    b = gen.from_pool(POOL, None, None, rng=random.Random(5))["config"]["timezone:id"]
    assert a == b and a in {"America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles"}
    with pytest.raises(ValueError, match="no locale->zone"):
        gen.from_pool(POOL, None, "xx-ZZ", rng=random.Random(1))
```

- [ ] **Step 2: Run, expect FileNotFoundError then ValueError mismatch**

Run: `python3 -m pytest -q client/python/tests/test_gen.py -k "zone or timezone"`
Expected: FAIL (`locale_zones.json` missing; `from_pool` still requires timezone)

- [ ] **Step 3: Write the table and the code**

`settings/locale_zones.json`: `$comment` "Offline default for timezone:id when --timezone is absent: plausible IANA zones per locale tag, first = most common. No GeoIP (spec 2026-09-11 §4); a proxy-exit lookup is the caller's. Validated by test_gen.py (every zone in zoneinfo.available_timezones())." and `zones` with: en-US [New_York, Chicago, Denver, Los_Angeles], en-GB [Europe/London], fr-FR [Europe/Paris], de-DE [Europe/Berlin], es-ES [Europe/Madrid], es-MX [America/Mexico_City], pt-BR [America/Sao_Paulo], ja-JP [Asia/Tokyo], ko-KR [Asia/Seoul], zh-CN [Asia/Shanghai], zh-TW [Asia/Taipei], ru-RU [Europe/Moscow], it-IT [Europe/Rome], nl-NL [Europe/Amsterdam], pl-PL [Europe/Warsaw], tr-TR [Europe/Istanbul], id-ID [Asia/Jakarta], th-TH [Asia/Bangkok], vi-VN [Asia/Ho_Chi_Minh], en-AU [Australia/Sydney, Australia/Melbourne, Australia/Brisbane, Australia/Perth], en-CA [America/Toronto, America/Vancouver], fr-CA [America/Toronto, America/Montreal], en-IN [Asia/Kolkata], hi-IN [Asia/Kolkata], ar-SA [Asia/Riyadh], ar-EG [Africa/Cairo], sv-SE [Europe/Stockholm], da-DK [Europe/Copenhagen], nb-NO [Europe/Oslo], fi-FI [Europe/Helsinki], cs-CZ [Europe/Prague], hu-HU [Europe/Budapest], ro-RO [Europe/Bucharest], uk-UA [Europe/Kyiv], el-GR [Europe/Athens], he-IL [Asia/Jerusalem], ms-MY [Asia/Kuala_Lumpur], fil-PH [Asia/Manila], en-NZ [Pacific/Auckland], en-IE [Europe/Dublin], en-ZA [Africa/Johannesburg], de-AT [Europe/Vienna], de-CH [Europe/Zurich], fr-BE [Europe/Brussels], nl-BE [Europe/Brussels], pt-PT [Europe/Lisbon].

`gen.py`:

```python
def zone_for(locale, rng):
    table = json.loads((ROOT / "settings" / "locale_zones.json").read_text())["zones"]
    if locale not in table:
        raise ValueError(f"--timezone is required for {locale}: no locale->zone table row, and "
                         "locale:tag without timezone:id trips timezone-set-with-locale")
    return rng.choice(table[locale])
```

In `from_pool`, compute `tag` before the config dict (move the locale block up) and set `"timezone:id": timezone or zone_for(tag, rng or random.Random())`. `generate()` drops its timezone check; `main()` makes `--timezone` optional (help: "IANA zone; default from settings/locale_zones.json by locale"). Go `Generate`: append `--timezone` only when non-empty.

- [ ] **Step 4: Tests pass**

Run: `python3 -m pytest -q client/python/tests && (cd client/go && go test ./...)`
Expected: pass

- [ ] **Step 5: Oracle on the box** — `verify_sp6b_generator.py` regression (31/31) plus 10 configs generated without `--timezone` start strict with zero `camoucfg:` lines and `Intl.DateTimeFormat().resolvedOptions().timeZone` equals the emitted zone (add rows G5 to that verify: loop 10 seeds, `--locale` cycling en-US/fr-FR/ja-JP/vi-VN/de-DE).

- [ ] **Step 6: Commit + push**

```bash
git add settings/locale_zones.json client/python client/go scripts/verify_sp6b_generator.py docs/superpowers/measurements/2026-09-10-sp6b-generator.md
git commit -m "feat(gen): locale->timezone table, --timezone optional; no GeoIP by decision"
```

---

### Task 6: Font family capture + `settings/fonts.json` + fetch + fontconfig generator

**Files:**
- Create: `scripts/capture_fonts_list.py`, `settings/fonts.json`, `scripts/fetch_fonts.py`, `scripts/gen_fontconfig.py`, `settings/fontconfig/windows.conf`, `settings/fontconfig/macos.conf`
- Modify: `.gitignore` (+`fonts/`)
- Test: `scripts/test_fonts.py`

**Interfaces:**
- `settings/fonts.json`:
  ```json
  {"bundle": [{"name": "Selawik", "url": "https://github.com/microsoft/Selawik/releases/download/v1.0/Selawik.zip", "sha256": "…", "files": ["selawk.ttf", "selawkb.ttf", "selawkl.ttf", "selawksb.ttf"], "family": "Selawik", "licence": "OFL.txt"}, …],
   "generic": {"Windows": {"sans-serif": "Selawik", "serif": "Liberation Serif", "monospace": "Liberation Mono", "system-ui": "Selawik"}, "macOS": {"sans-serif": "Inter", "serif": "Liberation Serif", "monospace": "Liberation Mono", "system-ui": "Inter"}},
   "alias": {"Segoe UI": "Selawik", "Arial": "Liberation Sans", "Helvetica": "Liberation Sans", "Times New Roman": "Liberation Serif", "Courier New": "Liberation Mono", "Calibri": "Carlito", "Cambria": "Caladea", "-apple-system": "Inter", "BlinkMacSystemFont": "Inter", "Helvetica Neue": "Inter", "Segoe UI Emoji": "Noto Color Emoji", "Apple Color Emoji": "Noto Color Emoji"},
   "script_class": {"cjk": ["Yu Gothic", "Yu Gothic UI", "Meiryo", "Meiryo UI", "MS Gothic", "MS PGothic", "MS UI Gothic", "Microsoft YaHei", "Microsoft YaHei UI", "SimSun", "NSimSun", "SimHei", "Microsoft JhengHei", "Microsoft JhengHei UI", "PMingLiU", "MingLiU", "Malgun Gothic", "Gulim", "Batang", "Dotum", "PingFang SC", "PingFang TC", "PingFang HK", "Hiragino Sans", "Hiragino Kaku Gothic ProN", "Hiragino Mincho ProN", "Apple SD Gothic Neo", "Heiti SC", "Heiti TC", "Songti SC", "STHeiti", "STSong"], "serif": ["Georgia", "Cambria", "Constantia", "Book Antiqua", "Bookman Old Style", "Garamond", "Palatino Linotype", "Times", "Baskerville", "Didot", "Cochin", "Charter", "Hoefler Text", "Iowan Old Style", "New York"], "mono": ["Consolas", "Lucida Console", "Courier", "Menlo", "Monaco", "SF Mono", "Andale Mono", "PT Mono"], "symbol": ["Symbol", "Wingdings", "Wingdings 2", "Wingdings 3", "Webdings", "Segoe UI Symbol", "Segoe MDL2 Assets", "Segoe Fluent Icons", "Marlett", "Apple Symbols", "Zapf Dingbats", "Zapfino"], "emoji": ["Segoe UI Emoji", "Apple Color Emoji"]},
   "class_font": {"Windows": {"sans": "Selawik", "serif": "Liberation Serif", "mono": "Liberation Mono", "cjk": "Noto Sans CJK SC", "symbol": "Noto Sans Symbols", "emoji": "Noto Color Emoji"}, "macOS": {"sans": "Inter", "serif": "Liberation Serif", "mono": "Liberation Mono", "cjk": "Noto Sans CJK SC", "symbol": "Noto Sans Symbols", "emoji": "Noto Color Emoji"}},
   "families": {"Windows": {"captured": "2026-09-11", "how": "…", "list": []}, "macOS": {"captured": "…", "how": "…", "list": []}}}
  ```
- `gen_fontconfig.fontconfig_xml(fonts: dict, os_name: str) -> str`; `fetch_fonts.py [--dest fonts]`; `capture_fonts_list.py --where winhost|mac` updating `families.<os>`; `alias_target(fonts, os_name, family) -> str`.

- [ ] **Step 1: Failing test**

```python
# scripts/test_fonts.py
import json, pathlib, sys, xml.etree.ElementTree as ET
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gen_fontconfig as g
ROOT = pathlib.Path(__file__).resolve().parent.parent
FONTS = json.loads((ROOT / "settings" / "fonts.json").read_text())

def test_every_bundle_entry_is_ofl_with_a_licence_and_sha():
    for b in FONTS["bundle"]:
        assert b["licence"] and len(b["sha256"]) == 64 and b["url"].startswith("https://"), b["name"]

def test_alias_target_by_explicit_then_class_then_sans():
    assert g.alias_target(FONTS, "Windows", "Segoe UI") == "Selawik"
    assert g.alias_target(FONTS, "Windows", "Yu Gothic") == "Noto Sans CJK SC"
    assert g.alias_target(FONTS, "Windows", "Georgia") == "Liberation Serif"
    assert g.alias_target(FONTS, "Windows", "Some Unknown Family") == "Selawik"
    assert g.alias_target(FONTS, "macOS", "Some Unknown Family") == "Inter"

def test_xml_is_strong_relative_and_covers_every_captured_family():
    for os_name in ("Windows", "macOS"):
        xml = g.fontconfig_xml(FONTS, os_name)
        root = ET.fromstring(xml)
        d = root.find("dir"); assert d.get("prefix") == "relative" and d.text == "../fonts"
        assert root.find("cachedir").get("prefix") == "xdg"
        aliases = {a.find("family").text: a for a in root.findall("alias")}
        assert all(a.get("binding") == "strong" for a in aliases.values())
        for fam in FONTS["families"][os_name]["list"]:
            assert fam in aliases, fam
        assert "sans-serif" in aliases and "system-ui" in aliases

def test_checked_in_confs_match_the_generator():
    for os_name, f in (("Windows", "windows.conf"), ("macOS", "macos.conf")):
        assert (ROOT / "settings" / "fontconfig" / f).read_text() == g.fontconfig_xml(FONTS, os_name)
```

- [ ] **Step 2: Run, expect failures**

Run: `python3 -m pytest -q scripts/test_fonts.py` → `ModuleNotFoundError`/`FileNotFoundError`.

- [ ] **Step 3: Capture the family lists**

`scripts/capture_fonts_list.py`:

```python
"""Captured, not authored: the family names a stock Windows 10 / macOS host
exposes. Windows: the box's host over ssh (PowerShell, InstalledFontCollection);
macOS: system_profiler on this Mac. Writes families.<os> in settings/fonts.json."""
import argparse, datetime, json, pathlib, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
ROOT = pathlib.Path(__file__).resolve().parent.parent
PATH = ROOT / "settings" / "fonts.json"

def winhost_families():
    import winhost
    out = winhost.powershell('Add-Type -AssemblyName System.Drawing; (New-Object System.Drawing.Text.InstalledFontCollection).Families | ForEach-Object { $_.Name }')
    return sorted({l.strip() for l in out.splitlines() if l.strip()}), "PowerShell InstalledFontCollection on the build box's Windows 10 host (ssh buildpc)"

def mac_families():
    raw = subprocess.run(["system_profiler", "SPFontsDataType", "-json"], capture_output=True, text=True, check=True).stdout
    fams = set()
    for f in json.loads(raw)["SPFontsDataType"]:
        for t in f.get("typefaces", []):
            fams.add(t.get("family") or t["_name"])
    return sorted(f for f in fams if not f.startswith(".")), "system_profiler SPFontsDataType -json on the Mac (dot-prefixed system-private families dropped)"

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--where", choices=["winhost", "mac"], required=True); a = ap.parse_args()
    fams, how = winhost_families() if a.where == "winhost" else mac_families()
    d = json.loads(PATH.read_text())
    d["families"]["Windows" if a.where == "winhost" else "macOS"] = {"captured": datetime.date.today().isoformat(), "how": how, "list": fams}
    PATH.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n"); print(len(fams), "families")

if __name__ == "__main__":
    main()
```

Write `settings/fonts.json` with the bundle entries (URLs: Selawik `https://github.com/microsoft/Selawik/releases/download/v1.0/Selawik.zip`; Liberation `https://github.com/liberationfonts/liberation-fonts/files/7261482/liberation-fonts-ttf-2.1.5.tar.gz`; Carlito + Caladea from `https://github.com/googlefonts/carlito/…` / `https://github.com/googlefonts/caladea/…` release archives; Noto Sans / Serif / Symbols / CJK SC / Color Emoji from `https://github.com/notofonts/…/releases` and `https://github.com/googlefonts/noto-cjk/releases` (`NotoSansCJKsc-Regular.otf` + Bold) and `https://github.com/googlefonts/noto-emoji/raw/v2.047/fonts/NotoColorEmoji.ttf`; Inter from `https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip`) — `fetch_fonts.py` computes the sha256 on first download when the field is empty and prints it, refuses on a mismatch afterwards. Run the two captures:

Run: `python3 scripts/capture_fonts_list.py --where winhost && python3 scripts/capture_fonts_list.py --where mac`
Expected: `NNN families` twice (record the counts).

- [ ] **Step 4: Write `gen_fontconfig.py`**

```python
#!/usr/bin/env python3
"""settings/fonts.json -> settings/fontconfig/{windows,macos}.conf. --check refuses drift.
Strong bindings are load-bearing: Skia's fontconfig manager accepts a match
only when the resolved family equals the request under strong binding."""
import json, pathlib, sys
from xml.sax.saxutils import escape
ROOT = pathlib.Path(__file__).resolve().parent.parent
FILES = {"Windows": "windows.conf", "macOS": "macos.conf"}

def alias_target(fonts, os_name, family):
    if family in fonts["alias"]:
        return fonts["alias"][family]
    for cls, names in fonts["script_class"].items():
        if family in names:
            return fonts["class_font"][os_name][cls]
    return fonts["class_font"][os_name]["sans"]

def fontconfig_xml(fonts, os_name):
    families = sorted(set(fonts["families"][os_name]["list"]) | set(fonts["alias"]))
    out = ['<?xml version="1.0"?>', '<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">',
           f'<!-- generated by scripts/gen_fontconfig.py from settings/fonts.json for a {os_name} claim; do not edit -->',
           '<fontconfig>', '  <dir prefix="relative">../fonts</dir>',
           '  <cachedir prefix="xdg">camoucrome-fontconfig</cachedir>']
    for generic, target in fonts["generic"][os_name].items():
        out += [f'  <alias binding="strong"><family>{escape(generic)}</family><prefer><family>{escape(target)}</family></prefer></alias>']
    for fam in families:
        out += [f'  <alias binding="strong"><family>{escape(fam)}</family><prefer><family>{escape(alias_target(fonts, os_name, fam))}</family></prefer></alias>']
    out += ['</fontconfig>', '']
    return "\n".join(out)

def main():
    fonts = json.loads((ROOT / "settings" / "fonts.json").read_text())
    check = "--check" in sys.argv; bad = 0
    for os_name, f in FILES.items():
        p = ROOT / "settings" / "fontconfig" / f; want = fontconfig_xml(fonts, os_name)
        if check:
            if not p.exists() or p.read_text() != want: print(f"STALE {p}"); bad += 1
        else:
            p.parent.mkdir(parents=True, exist_ok=True); p.write_text(want); print(f"wrote {p}")
    if check: print("PASS fontconfig files match settings/fonts.json" if not bad else f"FAIL {bad} stale"); sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()
```

Note: the bundled fonts themselves must be **excluded from the alias loop** (a bundled family aliased to itself is harmless but noisy): filter `families` by `fam not in {b["family"] for b in fonts["bundle"]}`.

- [ ] **Step 5: `fetch_fonts.py`**

```python
#!/usr/bin/env python3
"""Downloads the open font bundle (settings/fonts.json) into fonts/ (git-ignored),
verifying each archive's sha256; a blank sha256 is filled in and printed on
first fetch so it can be committed. Extracts only the listed files plus the
licence file into fonts/<family>/."""
import hashlib, io, json, pathlib, sys, tarfile, urllib.request, zipfile
ROOT = pathlib.Path(__file__).resolve().parent.parent

def fetch(entry, dest):
    data = urllib.request.urlopen(entry["url"], timeout=120).read()
    digest = hashlib.sha256(data).hexdigest()
    if entry["sha256"] and digest != entry["sha256"]:
        sys.exit(f"{entry['name']}: sha256 {digest} != {entry['sha256']}")
    d = dest / entry["family"]; d.mkdir(parents=True, exist_ok=True)
    wanted = set(entry["files"]) | {entry["licence"]}
    if entry["url"].endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for n in z.namelist():
                if pathlib.Path(n).name in wanted: (d / pathlib.Path(n).name).write_bytes(z.read(n))
    elif entry["url"].endswith((".tar.gz", ".tgz", ".tar.xz")):
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            for m in t.getmembers():
                if pathlib.Path(m.name).name in wanted: (d / pathlib.Path(m.name).name).write_bytes(t.extractfile(m).read())
    else:
        (d / pathlib.Path(entry["url"]).name).write_bytes(data)
    missing = [f for f in wanted if not (d / f).exists()]
    if missing: sys.exit(f"{entry['name']}: not in archive: {missing}")
    return digest

def main():
    dest = pathlib.Path(sys.argv[sys.argv.index("--dest") + 1] if "--dest" in sys.argv else ROOT / "fonts")
    p = ROOT / "settings" / "fonts.json"; fonts = json.loads(p.read_text()); filled = False
    for e in fonts["bundle"]:
        digest = fetch(e, dest); print(f"{e['name']}: {digest[:12]} -> {dest / e['family']}")
        if not e["sha256"]: e["sha256"] = digest; filled = True
    if filled: p.write_text(json.dumps(fonts, indent=1, ensure_ascii=False) + "\n"); print("sha256 fields filled: commit settings/fonts.json")

if __name__ == "__main__":
    main()
```

Run: `python3 scripts/fetch_fonts.py` (fills the sha256s), then `python3 scripts/gen_fontconfig.py`, `python3 -m pytest -q scripts/test_fonts.py` → `4 passed`. Add `fonts/` to `.gitignore`.

- [ ] **Step 6: Commit**

```bash
git add settings/fonts.json settings/fontconfig scripts/capture_fonts_list.py scripts/fetch_fonts.py scripts/gen_fontconfig.py scripts/test_fonts.py .gitignore
git commit -m "feat(fonts): captured Windows/macOS family lists, OFL bundle manifest, generated strong-alias fontconfig files"
```

---

### Task 7: Launcher `FONTCONFIG_FILE` duty (contract, Python, Go, Node) + generator `fonts:list` + packager

**Files:**
- Modify: `settings/launcher.json` (`launch.fontconfig`), `client/python/camoucrome/launcher.py` (`build_env(..., fonts_dir=None)`, `fontconfig_for(config, preset, fonts_dir)`, `launch(..., fonts_dir=None)`), `client/go/camoucrome.go` (`Options.FontsDir`, `BuildEnv`), `client/node/index.js` (`buildEnv({fontsDir})`), `client/python/camoucrome/gen.py` (`fonts:list`), `scripts/package.py` (copy `fonts/` + `settings/fontconfig/`, stamp `fonts`), `client/python/camoucrome/probe.py` (`--fonts-dir`)
- Tests: `client/python/tests/test_launcher.py`, `client/go/camoucrome_test.go`, `client/node/test/launcher.test.js`, `client/python/tests/test_gen.py`, `scripts/test_package.py`

**Interfaces:**
- Contract: `"fontconfig": {"env": "FONTCONFIG_FILE", "files": {"Windows": "fontconfig/windows.conf", "macOS": "fontconfig/macos.conf"}, "why": "..."}`.
- Python: `fontconfig_for(config, preset, fonts_dir) -> str|None`: OS from `config["ua:platform"]` else `preset["os"]`; `fonts_dir` defaults to `<dirname(executable)>/fonts` when that exists; returns `<fonts_dir>/../<files[os]>` absolute, else None. `build_env(config, preset, strict, base, fontconfig=None)` sets the env var when given. `launch(..., fonts_dir=None)`.
- Go: `Options.FontsDir string`; `FontconfigFor(o Options) string`; `BuildEnv` sets it. Node: `fontconfigFor({config, preset, fontsDir})`, `buildEnv({..., fontconfig})`.
- Generator: `fonts:list` = `settings/fonts.json` `families[<claimed OS>].list` for Windows/macOS; nothing for Linux.
- Packager: `stage(...)` copies `ROOT/fonts` → `staging/fonts` and `ROOT/settings/fontconfig/*.conf` → `staging/fontconfig/` when `ROOT/fonts` exists and `--no-fonts` absent; stamp `"fonts": bool`.

- [ ] **Step 1: Failing tests** — Python: `test_fontconfig_env_follows_the_claimed_os(tmp_path)`: make `tmp_path/fonts` and `tmp_path/fontconfig/windows.conf`, assert `fontconfig_for({"ua:platform": "Windows"}, None, tmp_path/"fonts")` ends with `fontconfig/windows.conf`, `Linux` → None, preset `{"os": "macOS"}` → macos.conf; `build_env(fontconfig="/x")["FONTCONFIG_FILE"] == "/x"`. Go/Node: the same three cases against the contract's `files` map. gen: `from_pool(POOL, "America/New_York")["config"]["fonts:list"] == FONTS["families"]["Windows"]["list"]`. package: fixture adds `fonts/Selawik/selawk.ttf` under a fake ROOT via `monkeypatch.setattr(package, "ROOT", ...)`, stamp `fonts is True`, `staging/fonts/Selawik/selawk.ttf` and `staging/fontconfig/windows.conf` exist; `--no-fonts` → False and absent.

- [ ] **Step 2: Run each suite, expect the new tests to fail**

- [ ] **Step 3: Implement** — Python:

```python
def fontconfig_for(config=None, preset=None, fonts_dir=None, executable_path=None):
    """The FONTCONFIG_FILE for the claimed OS (contract launch.fontconfig): the
    generated conf beside the bundled fonts dir, which lives beside the
    executable in an archive. Linux claim or no fonts dir: None."""
    cfg = json.loads(config) if isinstance(config, str) else (config or {})
    pre = json.loads(preset) if isinstance(preset, str) else (preset or {})
    os_name = cfg.get("ua:platform") or pre.get("os")
    files = CONTRACT["launch"]["fontconfig"]["files"]
    if os_name not in files:
        return None
    if fonts_dir is None and executable_path is not None:
        cand = os.path.join(os.path.dirname(os.path.abspath(str(executable_path))), "fonts")
        fonts_dir = cand if os.path.isdir(cand) else None
    if fonts_dir is None:
        return None
    return os.path.abspath(os.path.join(fonts_dir, os.pardir, files[os_name]))
```

`build_env(config=None, preset=None, strict=False, base=None, fontconfig=None)` adds `if fontconfig: env[CONTRACT["launch"]["fontconfig"]["env"]] = fontconfig`. `launch(...)` passes `build_env(config, preset, strict, fontconfig=fontconfig_for(config, preset, fonts_dir, executable_path))`. `CONTRACT` is loaded the way `FORBIDDEN_OPTIONS` is (from `settings/launcher.json` beside the package or the repo). Go: `FontconfigFor(o Options) string` mirroring it with `contract.Launch.Fontconfig.Files[os]`; `BuildEnv` sets `env["FONTCONFIG_FILE"]`. Node: `fontconfigFor({config, preset, fontsDir, executablePath})` + `buildEnv({..., fontconfig})`. gen: `platform in ("Windows", "macOS")` → `config["fonts:list"] = FONTS["families"][platform]["list"]` (load `settings/fonts.json` once at import). package.py: after the presets copy,

```python
    fonts = (ROOT / "fonts").is_dir() and not no_fonts
    if fonts:
        shutil.copytree(ROOT / "fonts", staging / "fonts", dirs_exist_ok=True)
        shutil.copytree(ROOT / "settings" / "fontconfig", staging / "fontconfig", dirs_exist_ok=True)
```

and `"fonts": bool(fonts)` in the stamp; `--no-fonts` flag; `stage(..., no_fonts=False)`. probe.py: `--fonts-dir` passthrough to `launch(fonts_dir=...)`.

- [ ] **Step 4: All suites green** — `python3 -m pytest -q client/python/tests scripts/test_package.py scripts/test_fonts.py && (cd client/go && go test ./...) && (cd client/node && npm test)`.

- [ ] **Step 5: Commit**

```bash
git add settings/launcher.json client scripts/package.py scripts/test_package.py
git commit -m "feat(launcher): FONTCONFIG_FILE for the claimed OS; generator emits fonts:list; packager ships fonts/ + fontconfig"
```

---

### Task 8: `verify_fonts_bundle.py` on the box (RED first) + doc + archive re-cut

**Files:**
- Create: `scripts/verify_fonts_bundle.py`, `docs/superpowers/measurements/2026-09-11-fonts-bundle.md`
- Modify: roadmap A5 #3 and C, D rows for system-ui/CSS2, d-gaps doc §1 verdict lines, packaging doc §3 (third cut), generator doc

**Interfaces:**
- Consumes: probe `--fonts-dir`, `settings/fonts.json`, `fonts/` pushed to the box beside a copy of the extracted archive's `chrome` (F5) and beside `out/Default` (F1–F4: `--fonts-dir /home/lang/camoucrome-client/fonts`).

- [ ] **Step 1: Write the verify** — page: for each family in a list, `w(f) = width("\"f\", monospace")`, `mono = width("monospace")`, `resolves(f) = w(f) != mono`; also `width("system-ui")`, `width("Selawik")`, `width("Segoe UI")`, `width("Inter")`, `width("-apple-system")`, and a `<span style="font: caption">` rendered width. Rows:
  - F1 RED (no `--fonts-dir`, no config): `resolves("Segoe UI") is False` and `resolves("DejaVu Sans") is True`.
  - F2 (`--fonts-dir`, config `WIN` + `fonts:list` = Windows list): every listed family resolves (report the first 5 that do not); `DejaVu Sans`, `Ubuntu`, `Cantarell` do not; `width(system-ui) == width(Selawik) == width("Segoe UI")`; caption rendered width == `width(Selawik)` (same string).
  - F3 (`MAC` claim + macOS list): every listed family resolves; `width(system-ui) == width(Inter) == width(-apple-system)`.
  - F4: `gen.py --os windows --timezone UTC --seed 1` → its `fonts:list` ⊆ the set F2 measured as resolving.
  - F5: `CAMOU_EXE=<extracted>/chrome` with `fonts/` present beside it (no `--fonts-dir`: the launcher finds it) → F2 rows pass.
  Print `n PASS m FAIL`.

- [ ] **Step 2: Push `fonts/` (≈35 MB) to the box** — `tar czf fonts.tgz fonts settings/fontconfig`, push with `pushfile` (chunked base64; ~10 min) or `scp` through the ControlMaster if the master is alive; extract into `/home/lang/camoucrome-client/`. Run F1 first without the dir: expect `FAIL` on F2–F5 and `PASS` F1.

- [ ] **Step 3: GREEN** — expected `5 PASS 0 FAIL`. If F2 fails on `system-ui`: Chrome resolves `system-ui` through `gfx::Font` default (GTK setting) on Linux, not fontconfig's `sans-serif`; then add `--font-render-hinting`? No: measure what `system-ui` resolved to (width equality against every bundled family) and record; the fix if needed is aliasing the GTK default name (`Ubuntu`/`DejaVu Sans`/`Cantarell`) to Selawik in the conf — add those three to `alias` for Windows and macOS.

- [ ] **Step 4: Third archive cut** — on the box: `fetch_fonts.py --dest ~/camoucrome-cs/fonts` (network) or copy the pushed dir, `gen_fontconfig.py` output already in `settings/fontconfig`, `package.py … --changeset-commit <sha>`; record size, `fonts: true`, F5 on the extracted tree, the driver sweep.

- [ ] **Step 5: Doc + roadmap** — `2026-09-11-fonts-bundle.md`: §1 decision (no proprietary files; the table), §2 captured lists (counts, provenance), §3 the conf (strong binding, relative dir, cachedir), §4 verify table F1–F5 with counts, §5 open (Selawik metrics, Georgia/Verdana/Tahoma, CJK single region, hinting/AA, Windows/macOS hosts, F-PSNAME). Roadmap: A5 #3 SHIPPED, C "Font redistribution" decided, D rows system-ui/CSS2 → shipped via the bundle; d-gaps doc §1 verdict cells get a "closed by the bundle" note; packaging doc §3 third cut.

- [ ] **Step 6: Commit + push**

```bash
git add scripts/verify_fonts_bundle.py docs
git commit -m "feat(fonts): open font bundle with strong fontconfig aliases closes system-ui/CSS2/presence tells; C decided"
```

---

### Task 9: `window.chrome` tree + plugins capture and diff (stock Windows 153 vs fork)

**Files:**
- Create: `scripts/capture_chrome_object.py`, `baselines/chrome-8010-stock-window-chrome.json`, `scripts/verify_chrome_object.py`, `docs/superpowers/measurements/2026-09-11-chrome-binary-items.md`
- Modify: roadmap B1 cell, SP2 spec D4 (one sentence), `docs/superpowers/specs/2026-08-26-sp2-automation-hiding-design.md` §4.7 status line

**Interfaces:**
- `capture_chrome_object.PAGE`: reports `{tree: walk(window.chrome, depth 4), plugins: [{name, filename, description, mimeTypes: [{type, suffixes, description}]}], mimeTypes: [...], pdfViewerEnabled, loadTimes: {keys, ordering: {startLoadTime_le_firstPaintTime, requestTime_le_startLoadTime}}, csi: {keys, pageT_ge_0}}` where `walk` records for each own property name: kind (`function`/`object`/`value`), for functions `length`, `name`, `toString()`, for values `typeof`; recursion into objects; functions' own props too. Excludes value contents (times).
- `verify_chrome_object.py`: CLI `--baseline path` (default the repo file), runs the fork on the box through the probe, prints the tree diff (paths added/removed/kind-changed), plugins diff (names, filenames, mime types), `pdfViewerEnabled` equality; RED-by-construction row: the same differ against a content_shell capture is non-empty (`typeof window.chrome === 'undefined'`).

- [ ] **Step 1: Capture stock** — `python3 scripts/capture_chrome_object.py --where winhost` (headless) and `--where winhost --headed` → `baselines/chrome-8010-stock-window-chrome.json` `{headless: {...}, headed: {...}, provenance}`. Record whether headed and headless differ (plugins in `--headless=new`: expected 5 PDF entries both; if headless has 0, that is a headless tell for B7 — named, not keyed).
- [ ] **Step 2: Verify on the box** — fork headless tree == stock headless tree (diff empty); plugins equal; `pdfViewerEnabled` equal; RED: content_shell → non-empty diff. Expected: PASS; any difference is written to the doc as a finding with the path.
- [ ] **Step 3: Doc + roadmap** — `2026-09-11-chrome-binary-items.md` §1 window.chrome (tree size, diff result, loadTimes/csi ordering), §2 plugins/mimeTypes/pdfViewerEnabled (stock headless vs headed vs fork), §3 Sec-CH-UA end-to-end (already 34/34: the roadmap sentence corrected, `verify_sp1a_chrome.py` re-run count), §4 headless_shell closed by decision, §5 SP7 P4 (Task 10). Roadmap B1 cell rewritten to the doc's findings; SP2 spec D4 gets "2026-09-11: headless_shell is neither shipped nor tested (package.py targets //chrome:chrome; the contract's executable is chrome); closed."
- [ ] **Step 4: Commit + push**

---

### Task 10: SP7 P4 — `X-Client-Data` on a Google host, RED from the stock two-launch profile

**Files:**
- Modify: `scripts/verify_sp7_phonehome.py` (add `run_p4`), `docs/superpowers/measurements/2026-09-09-sp7-phone-home.md` ("still open" list), `2026-09-11-chrome-binary-items.md` §5
- Create: `scripts/winhost_xclientdata.py` (the stock RED: two launches on one temp profile with `--remote-debugging-port`, CDP `Network.enable` + `requestWillBeSentExtraInfo` through playwright `connect_over_cdp` from the Mac over an ssh port-forward `-L 9333:127.0.0.1:9333`)

**Interfaces:**
- `run_p4()`: launches the fork twice on one profile (`lib_shell.launch(None, shell=lib_shell.CHROME, extra_flags=CHROME_FLAGS + ["--user-data-dir=<same tmp>"])`), second launch: CDP session `Network.enable`, `page.goto("https://www.google.com/generate_204")`, collects `requestWillBeSentExtraInfo` headers for requests to `*.google.com`, asserts no `X-Client-Data` (case-insensitive) and no request host in `{clientservices.googleapis.com, update.googleapis.com}` during 20 s. Result row `P4`.
- Stock RED script: same shape on the Windows host; prints the header value found on the second run (`X-Client-Data: <base64>`), which is the RED evidence recorded in the doc.

- [ ] **Step 1: Run the stock RED on the Windows host** (temp profile, `--remote-debugging-port=9333`, two launches, ssh port-forward). Expected: second launch's request to `google.com/generate_204` carries `x-client-data`. If the first run does not fetch a seed within 60 s (stock fetches on first run after a delay), extend to 120 s; record what was seen.
- [ ] **Step 2: Fork P4 on the box**: no `x-client-data` either launch, no googleapis hosts. Expected `P4 PASS`; full script `4 PASS 0 FAIL`.
- [ ] **Step 3: Docs + commit + push**

---

### Task 11: Final sweep, ledger, memory

- [ ] Run on the box: `verify_sp6b_driver.py`, `verify_sp6b_launcher.py`, `verify_sp6b_generator.py`, `verify_d_pointer_touch.py`, `verify_sp1a_chrome.py`, `run_coherence_tests.sh`; record counts in the ledger `.superpowers/sdd/progress.md`.
- [ ] `check_checkout_sync.sh` PASS; `gen_keys.py --check`, `gen_fontconfig.py --check`, `check_additions_build.py` PASS; CI green.
- [ ] Memory: `buildpc-client-layout.md` gains the Windows-host facts (stock Chrome 153 at `C:\Program Files\Google\Chrome\Application\chrome.exe`, PowerShell shell over ssh, Intel UHD 630; `fonts/` on the box under `~/camoucrome-client/fonts`).
- [ ] Commit + push; recap.

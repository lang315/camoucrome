#!/usr/bin/env python3
"""Captures a WebGL profile (settings/webgl/<id>.json) from a real GPU.

    capture_webgl_profile.py --where winhost --id windows-intel-uhd-630-d3d11 --os Windows
    capture_webgl_profile.py --where mac     --id macos-apple-m1-pro-metal   --os macOS
    capture_webgl_profile.py --where box     --id ID --os Linux              (out/Default chrome)

The page reads both contexts: every numeric getParameter pname in the
WebGL/WebGL2 IDL constant tables (enumerated by name below, so a typo is a
missing key, not a wrong number), getSupportedExtensions(), the 12
getShaderPrecisionFormat cells and getContextAttributes(). String pnames
are identity, held by vendor/renderer. A SwiftShader renderer is the host's
software fallback, not a device: refused (the Windows headless launch
self-adds --use-angle=swiftshader-webgl unless --use-angle is given).
"""
import argparse
import base64
import datetime
import json
import os
import pathlib
import sys

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
              "WEBGL_draw_buffers": ["MAX_COLOR_ATTACHMENTS_WEBGL", "MAX_DRAW_BUFFERS_WEBGL"]}

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
  const exts = gl.getSupportedExtensions();
  return { vendor: gl.getParameter(d.UNMASKED_VENDOR_WEBGL), renderer: gl.getParameter(d.UNMASKED_RENDERER_WEBGL),
           parameters, supportedExtensions: exts, shaderPrecisionFormats: spf,
           contextAttributes: gl.getContextAttributes(),
           extOk: Object.fromEntries(exts.map(e => [e, gl.getExtension(e) !== null])) };
}
document.getElementById('o').textContent = JSON.stringify({ webgl: read('webgl', GL1), webgl2: read('webgl2', GL2) });
</script>""" % (json.dumps(GL1), json.dumps(GL2), json.dumps(EXT_PNAMES))

FIELDS = ("parameters", "supportedExtensions", "shaderPrecisionFormats", "contextAttributes")


def profile_from_report(report, id, os_name, provenance):
    for k in ("webgl", "webgl2"):
        ctx = report.get(k)
        if not ctx:
            raise ValueError(f"{k}: no context")
        if "SwiftShader" in ctx["renderer"] or "SwiftShader" in ctx["vendor"]:
            raise ValueError(f"{k}: SwiftShader is not a profile: {ctx['renderer']}")
    w = report["webgl"]
    return {"id": id, "os": os_name, "vendor": w["vendor"], "renderer": w["renderer"],
            "webgl": {k: w[k] for k in FIELDS},
            "webgl2": {k: report["webgl2"][k] for k in FIELDS},
            "provenance": provenance}


def capture_winhost(angle):
    import winhost
    attempts = [(["--use-angle=" + angle], False),
                (["--use-gl=angle", "--use-angle=" + angle], False),
                (["--use-angle=" + angle], True)]
    for args, headed in attempts:
        r = winhost.dump_dom(PAGE, args, headed=headed)
        if r["webgl"] and "SwiftShader" not in r["webgl"]["renderer"]:
            return r, {"binary": "Google Chrome 153.0.8010.36 (stock, the build box's Windows 10 host)",
                       "how": "scripts/capture_webgl_profile.py --where winhost", "headless": not headed, "args": args}
        print(f"attempt {args} headed={headed}: {r['webgl'] and r['webgl']['renderer']}", file=sys.stderr)
    raise SystemExit("every attempt reported SwiftShader; no profile written")


def capture_mac():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=False,
                              args=["--window-size=300,200", "--window-position=0,0"])
        pg = b.new_page()
        pg.set_content(PAGE)
        r = json.loads(pg.locator("#o").text_content())
        ver = b.version
        b.close()
    return r, {"binary": f"Google Chrome {ver} (stock, the Mac, headed 300x200: headless gives no context)",
               "how": "scripts/capture_webgl_profile.py --where mac", "headless": False}


def capture_box():
    import lib_shell
    url = "data:text/html;base64," + base64.b64encode(PAGE.encode()).decode()
    values, err = lib_shell.session(None, ["() => JSON.parse(document.getElementById('o').textContent)"],
                                    navigate_to=url, shell=lib_shell.CHROME, extra_flags=lib_shell.CHROME_FLAGS)
    if err:
        raise SystemExit(err)
    return values[0], {"binary": "fork chrome out/Default (box)",
                       "how": "scripts/capture_webgl_profile.py --where box", "headless": True}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--where", choices=["winhost", "mac", "box"], required=True)
    ap.add_argument("--id", required=True)
    ap.add_argument("--os", required=True, choices=["Windows", "macOS", "Linux"])
    ap.add_argument("--angle", default="d3d11")
    ap.add_argument("--out", default=str(ROOT / "settings" / "webgl"))
    a = ap.parse_args()
    report, prov = {"winhost": lambda: capture_winhost(a.angle), "mac": capture_mac, "box": capture_box}[a.where]()
    prov["captured"] = datetime.date.today().isoformat()
    profile = profile_from_report(report, a.id, a.os, prov)
    path = pathlib.Path(a.out) / f"{a.id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=1) + "\n")
    print(f"{path}: {profile['renderer']} | {len(profile['webgl']['parameters'])}/{len(profile['webgl2']['parameters'])} pnames, "
          f"{len(profile['webgl']['supportedExtensions'])}/{len(profile['webgl2']['supportedExtensions'])} ext")


if __name__ == "__main__":
    main()

"""SP5b preset loader: CAMOU_PRESET expands into configuration keys inside
ParsedConfig(), explicit CAMOU_CONFIG keys win, and a bad preset never
crashes the browser. content_shell under SwiftShader so both WebGL contexts
exist.

P0  RED: with nothing set, every measured surface differs from the fixture
    (otherwise P1 would prove nothing on this machine).
P1  preset only: screen, locale, timezone, UA OS, both contexts' identity
    and MAX_TEXTURE_SIZE equal the fixture.
P2  preset + CAMOU_CONFIG {"screen.width":1600}: width is 1600, everything
    else still the preset's.
P3  preset only, startup log: zero invariant lines, zero wrong-type
    warnings, zero milestone warnings (fixture milestone == build's).
P4  preset with milestone 120: the log names the mismatch (warning only,
    the browser starts and the hardware claims still apply).
P5  RED: malformed preset, not strict: browser starts, real values (the P0
    ones), the log says the preset was ignored -- and NOT ParseConfig's
    "all spoofing is disabled", which would be false here.
P6  malformed preset under CAMOU_CONFIG_STRICT: exits during startup.
"""
import json
import sys

import lib_shell

GL_FLAGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
FLAGS = lib_shell.SHELL_FLAGS + GL_FLAGS

RENDERER = ("ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002504) "
            "Direct3D11 vs_5_0 ps_5_0, D3D11)")
# A fixture for the loader, not a preset: the GPU is invented, which is
# exactly what a shipped preset must never be (settings/presets/ holds
# captures only).
FIXTURE = {
    "milestone": 153,
    "os": "Windows",
    "gpu": {"vendor": "Google Inc. (NVIDIA)", "renderer": RENDERER,
            "parameters": {"3379": 16384}},
    "screen": {"width": 1920, "height": 1080,
               "availWidth": 1920, "availHeight": 1040},
    "locale": "fr-FR",
    "timezone": "Europe/Paris",
}

GL = """(type) => {
  const gl = document.createElement('canvas').getContext(type);
  if (!gl) return 'no-context';
  const ext = gl.getExtension('WEBGL_debug_renderer_info');
  return [gl.getParameter(0x9245), gl.getParameter(0x9246),
          gl.getParameter(0x0D33)].join('|');
}"""
EXPRS = ["screen.width", "screen.availHeight", "navigator.language",
         "JSON.stringify(navigator.languages)",
         "Intl.DateTimeFormat().resolvedOptions().timeZone",
         "navigator.userAgent", f"({GL})('webgl')", f"({GL})('webgl2')"]
NAMES = ["width", "availHeight", "language", "languages", "tz", "ua",
         "webgl", "webgl2"]
GL_EXPECTED = f"Google Inc. (NVIDIA)|{RENDERER}|16384"
EXPECTED = {"width": 1920, "availHeight": 1040, "language": "fr-FR",
            "languages": '["fr-FR","fr"]', "tz": "Europe/Paris",
            "webgl": GL_EXPECTED, "webgl2": GL_EXPECTED}


def run(preset, config=None, strict=False):
    values, err = lib_shell.session(
        None if config is None else json.dumps(config), EXPRS,
        extra_flags=FLAGS, strict=strict,
        preset=None if preset is None else (
            preset if isinstance(preset, str) else json.dumps(preset)))
    log = open(lib_shell.STDERR_LOG, errors="replace").read()
    return (dict(zip(NAMES, values)) if values else None), err, log


results, notes = {}, []

real, err, _ = run(None)
P0 = "0 RED: nothing set, every measured surface differs from the fixture"
same = [] if real else ["launch failed"]
if real:
    same = [k for k, v in EXPECTED.items() if real[k] == v]
    if "Windows NT 10.0; Win64; x64" in real["ua"]:
        same.append("ua")
results[P0] = err is None and not same
if same:
    notes.append(f"0: fixture equals the real value for {same}; {err}")

got, err, log = run(FIXTURE)
P1 = "1 preset only: screen, locale, timezone, UA OS, both GL identities"
bad = [] if got else [f"launch: {err}"]
if got:
    bad = [f"{k}={got[k]!r}" for k, v in EXPECTED.items() if got[k] != v]
    if "Windows NT 10.0; Win64; x64" not in got["ua"]:
        bad.append(f"ua={got['ua']!r}")
results[P1] = not bad
if bad:
    notes.append("1: " + "; ".join(bad))

P3 = "3 preset only: no invariant, wrong-type or milestone line at startup"
lines = [l for l in log.splitlines()
         if "invariant '" in l or "falling back to the real value" in l
         or "preset milestone" in l]
results[P3] = got is not None and not lines
if lines:
    notes.append("3: " + " // ".join(l[-120:] for l in lines[:3]))

got, err, _ = run(FIXTURE, {"screen.width": 1600})
P2 = "2 explicit CAMOU_CONFIG key wins over the preset, the rest survive"
results[P2] = (got is not None and got["width"] == 1600
               and got["language"] == "fr-FR" and got["tz"] == "Europe/Paris"
               and got["webgl2"] == GL_EXPECTED)
if not results[P2]:
    notes.append(f"2: {err or got}")

got, err, log = run(dict(FIXTURE, milestone=120))
P4 = "4 preset milestone 120 starts and logs the mismatch against 153"
hit = [l for l in log.splitlines()
       if "preset milestone 120 differs from this build's 153" in l]
results[P4] = got is not None and got["tz"] == "Europe/Paris" and bool(hit)
if not results[P4]:
    notes.append(f"4: {err or ('no milestone line; ' + repr(got['tz']))}")

got, err, log = run("{not json")
P5 = "5 RED: malformed preset, not strict: starts, real values, one error line"
results[P5] = (got is not None and real is not None
               and got["width"] == real["width"] and got["tz"] == real["tz"]
               and "preset is not a JSON object; ignored" in log
               and "all spoofing is disabled" not in log)
if not results[P5]:
    notes.append(f"5: {err or got}")

got, err, _ = run("{not json", strict=True)
P6 = "6 malformed preset under CAMOU_CONFIG_STRICT exits during startup"
results[P6] = got is None and "exited during startup" in str(err)
if not results[P6]:
    notes.append(f"6: started={got is not None}; {err}")

for name in [P0, P1, P2, P3, P4, P5, P6]:
    print(f"{'PASS' if results[name] else 'FAIL'}  {name}")
for n in notes:
    print("  " + n)
ok = all(results.values())
print(f"{sum(results.values())} PASS {len(results) - sum(results.values())} FAIL")
sys.exit(0 if ok else 1)

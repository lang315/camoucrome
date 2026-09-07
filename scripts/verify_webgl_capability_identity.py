"""Verifies the WebGL capability<->identity presence check.

A spoofed capability surface (parameters / supportedExtensions /
shaderPrecisionFormats / contextAttributes) configured while BOTH identity
strings (webGl:renderer, webGl:vendor) are absent lets a page read the spoofed
GPU capability beside this machine's real GPU identity. Reported at startup;
refuses under CAMOU_CONFIG_STRICT. One-directional (identity-only is fine) and
gated on both identity strings absent (partial identity is the pairing check's).

Modelled on verify_sp5a.py: reads the browser's stderr for the LOG(ERROR) and
discriminates a strict exit 13 from a hang. One row (CP-MOTIVATION) reads the
page under SwiftShader to show the leak is real. Any fault becomes a FAIL line.
"""
import json
import sys
import lib_shell

GL = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]

V_RENDERER = "NVIDIA GeForce RTX 4090"
V_VENDOR = "Google Inc. (NVIDIA)"
PARAMS = {"webGl:parameters": {"3379": 16384}}
EXTENSIONS = {"webGl:supportedExtensions":
              ["EXT_texture_filter_anisotropic", "OES_element_index_uint"]}
SHADERPREC = {"webGl:shaderPrecisionFormats": {"35633:36338": [100, 100, 20]}}
CTXATTRS = {"webGl:contextAttributes":
            {"antialias": False, "powerPreference": "high-performance",
             "preserveDrawingBuffer": True}}
WITH_IDENTITY = {**PARAMS, "webGl:renderer": V_RENDERER, "webGl:vendor": V_VENDOR}
PARTIAL_IDENTITY = {**PARAMS, "webGl:renderer": V_RENDERER}  # vendor absent
IDENTITY_ONLY = {"webGl:renderer": V_RENDERER, "webGl:vendor": V_VENDOR}
WEBGL2 = {"webGl2:parameters": {"3379": 16384}}
EMPTY_DICT = {"webGl:parameters": {}}
EMPTY_LIST = {"webGl:supportedExtensions": []}
WRONG_TYPE = {"webGl:parameters": "oops"}


def cap_line(cap_key, webgl2=False):
    r = "webGl2:renderer" if webgl2 else "webGl:renderer"
    v = "webGl2:vendor" if webgl2 else "webGl:vendor"
    return f"camoucfg: '{cap_key}' is set but neither '{r}' nor '{v}' is."


PAIRING_VENDOR_ABSENT = (
    "camoucfg: 'webGl:renderer' is set but its pair 'webGl:vendor' is not.")
# Any capability line at all, for the absence assertions.
ANY_CAP = "is set but neither"
REFUSAL = ("camoucfg: configuration is incoherent and CAMOU_CONFIG_STRICT is "
           "set; refusing to start.")

MOTIVATION = """(() => {
  const c=document.createElement('canvas'); c.width=16;c.height=16;
  const gl=c.getContext('webgl');
  if(!gl) return {err:'no-gl'};
  const ext=gl.getExtension('WEBGL_debug_renderer_info');
  return { maxTex: gl.getParameter(0x0D33),
           renderer: ext ? gl.getParameter(0x9246) : null };
})()"""

results = {}
notes = []


def failed(keys, label, exc):
    for key in keys:
        results[key] = False
    notes.append(f"{label}: {type(exc).__name__}: {exc}")


def read_stderr():
    try:
        with open(lib_shell.STDERR_LOG, "rb") as handle:
            return handle.read().decode("utf-8", "replace"), None
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc


def expect_line(name, config, present, absent=()):
    _, err = lib_shell.session(json.dumps(config), ["1"])
    if err is not None:
        failed([name], f"{name} session", err)
        return
    stderr, read_err = read_stderr()
    if read_err is not None:
        failed([name], f"{name} stderr read", read_err)
        return
    results[name] = all(s in stderr for s in present) and all(
        s not in stderr for s in absent)
    if not results[name]:
        notes.append(f"{name}: stderr={stderr!r}")


def expect_strict_exit_13(name, config):
    _, err = lib_shell.session(json.dumps(config), ["1"], strict=True)
    if err is None:
        results[name] = False
        notes.append(f"{name}: started under CAMOU_CONFIG_STRICT=1; expected 13")
        return
    if "exited during startup" not in str(err):
        results[name] = False
        notes.append(f"{name}: not exit-during-startup: {type(err).__name__}: {err}")
        return
    code_text = str(err).rsplit("code ", 1)[-1]
    try:
        code = int(code_text)
    except ValueError:
        code = None
    if code != 13:
        results[name] = False
        notes.append(f"{name}: wrong exit code: {err}")
        return
    stderr, read_err = read_stderr()
    if read_err is not None:
        failed([name], f"{name} stderr read", read_err)
        return
    results[name] = REFUSAL in stderr
    if not results[name]:
        notes.append(f"{name}: exited 13 but no refusal: {stderr!r}")


# CP-MOTIVATION: the leak is real (page-side), unchanged before/after.
NB = "CP-MOTIVATION params-only leaks spoofed maxTex beside host renderer (unchanged)"
vals, err = lib_shell.session(json.dumps(PARAMS), [MOTIVATION], extra_flags=GL)
if err is not None:
    failed([NB], "motivation", err)
else:
    m = vals[0]
    if not isinstance(m, dict) or "err" in m:
        results[NB] = False
        notes.append(f"CP-MOTIVATION: {m}")
    else:
        results[NB] = m["maxTex"] == 16384 and m["renderer"] and "NVIDIA" not in m["renderer"]
        notes.append(f"CP-MOTIVATION: maxTex={m['maxTex']} renderer={m['renderer']!r}")

# The rows that flip RED -> GREEN: each capability alone logs, naming itself.
expect_line("CP-PARAMS-LOG parameters alone logs", PARAMS,
            [cap_line("webGl:parameters")])
expect_strict_exit_13("CP-PARAMS-STRICT parameters alone, strict, exits 13", PARAMS)
expect_line("CP-EXT-LOG supportedExtensions alone logs", EXTENSIONS,
            [cap_line("webGl:supportedExtensions")])
expect_line("CP-SHADERPREC-LOG shaderPrecisionFormats alone logs", SHADERPREC,
            [cap_line("webGl:shaderPrecisionFormats")])
expect_line("CP-CTXATTRS-LOG contextAttributes alone logs", CTXATTRS,
            [cap_line("webGl:contextAttributes")])

# Identity present -> silent. Partial identity -> pairing owns it, cap silent.
expect_line("CP-WITH-IDENTITY params + renderer + vendor is silent",
            WITH_IDENTITY, present=[], absent=[ANY_CAP])
expect_line("CP-PARTIAL-IDENTITY params + renderer only: pairing fires, cap silent",
            PARTIAL_IDENTITY, present=[PAIRING_VENDOR_ABSENT], absent=[ANY_CAP])
expect_line("CP-IDENTITY-ONLY renderer + vendor, no capability, is silent",
            IDENTITY_ONLY, present=[], absent=[ANY_CAP])

# webGl2 independent: webGl2:parameters alone logs the webGl2 line (naming
# webGl2:renderer/vendor) and the webGl line is absent. The other three fields'
# webGl2 paths are covered structurally, not by a row: the Cap[] loop keys all
# four fields off one is_webgl2 and sets renderer_key/vendor_key once per
# iteration, so this single row exercises the is_webgl2=true wiring for the
# whole loop. (Per-field webGl2 rows were trialed but dropped -- see the doc.)
expect_line("CP-WEBGL2 webGl2:parameters alone logs webGl2, webGl silent",
            WEBGL2, present=[cap_line("webGl2:parameters", webgl2=True)],
            absent=[cap_line("webGl:parameters")])

# Presence semantics: empty = absent (both dict and list), wrong-type = absent.
expect_line("CP-EMPTY-DICT empty parameters dict is silent (empty = absent)",
            EMPTY_DICT, present=[], absent=[ANY_CAP])
expect_line("CP-EMPTY-LIST empty extensions list is silent (falls through to real)",
            EMPTY_LIST, present=[], absent=[ANY_CAP])
expect_line("CP-WRONG-TYPE non-dict parameters is silent (type-aware presence)",
            WRONG_TYPE, present=[], absent=[ANY_CAP])

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for note in notes:
    print(f"      {note}")

sys.exit(0 if results and all(results.values()) else 1)

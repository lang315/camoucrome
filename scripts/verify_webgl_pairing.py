"""Verifies the webGl renderer/vendor all-or-nothing pairing check.

The check runs at browser-process startup (ValidateAtStartup -> browser_main_
loop's diagnostic block), so like verify_sp5a.py it reads the browser's stderr
for the LOG(ERROR) line and discriminates a strict-mode exit 13 from a hang.
One extra row (WP-MOTIVATION) reads the page through WEBGL_debug_renderer_info
under SwiftShader to prove the leak the check is about is real -- a spoofed
renderer beside this machine's real GL vendor.

Structured like verify_sp5a.py: any fault in one session becomes FAIL lines,
never a traceback that discards results already collected.

IMPORTANT (stated in the measurement doc, restated here): this check does NOT
change what the page sees. WP-MOTIVATION reads the same leaked host vendor
before and after the code change -- the design rejects, it does not repair.
The rows that flip RED->GREEN are the LOG(ERROR) and the strict exit.
"""

import json
import sys

import lib_shell

GL_FLAGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]

# The in-repo WebGL identity strings (verify_sp3b.py:70-71). The renderer is
# NVIDIA; a coherent vendor would be "Google Inc. (NVIDIA)". The host vendor
# under SwiftShader is something else entirely, so a renderer-only config makes
# the pair disagree -- that disagreement is the leak.
V_RENDERER = "NVIDIA GeForce RTX 4090"
V_VENDOR = "Google Inc. (NVIDIA)"

RENDERER_ONLY = {"webGl:renderer": V_RENDERER}
VENDOR_ONLY = {"webGl:vendor": V_VENDOR}
BOTH = {"webGl:renderer": V_RENDERER, "webGl:vendor": V_VENDOR}
# 37445 == 0x9245 UNMASKED_VENDOR_WEBGL: vendor supplied through the parameters
# table, not the dedicated key. getParameter() resolves it, so the pair IS
# complete and the check must stay silent -- the false-refusal guard.
PARAMS_GUARD_VENDOR = {
    "webGl:renderer": V_RENDERER,
    "webGl:parameters": {"37445": V_VENDOR},
}
# The mirror: 37446 == 0x9246 UNMASKED_RENDERER_WEBGL, renderer via the
# parameters table beside a dedicated vendor. GLStringResolves is symmetric in
# the pname it reads (0x9245 vs 0x9246); this is the ONLY test that exercises
# the renderer arm of that ternary -- the config singleton makes it un-unit-
# testable, so a pname swap in the renderer arm would otherwise ship silent.
PARAMS_GUARD_RENDERER = {
    "webGl:vendor": V_VENDOR,
    "webGl:parameters": {"37446": V_RENDERER},
}
# webGl renderer + webGl2 vendor: each API is half-configured, so this is two
# violations, not zero -- the two surfaces are independent.
CROSS = {"webGl:renderer": V_RENDERER, "webGl2:vendor": V_VENDOR}

# Reads the unmasked renderer/vendor a page sees. Returns {err} rather than
# throwing when the context or extension is unavailable, so a GL failure is a
# FAIL line, never a silent pass (verify_sp3b.py's PROBE does the same).
MOTIVATION = """(() => {
  const c = document.createElement('canvas'); c.width = 16; c.height = 16;
  const gl = c.getContext('webgl');
  if (!gl) return { err: 'no-context' };
  const ext = gl.getExtension('WEBGL_debug_renderer_info');
  if (!ext) return { err: 'no-debug-renderer-info-ext' };
  return { renderer: gl.getParameter(0x9246), vendor: gl.getParameter(0x9245) };
})()"""

# The pairing LOG(ERROR) lines, matched as substrings. Named for the key the
# message reports MISSING. Keep in sync with coherence_validator.cc's
# PairingViolation loop.
RENDERER_MISSING_MSG = (
    "camoucfg: 'webGl:vendor' is set but its pair 'webGl:renderer' is not.")
VENDOR_MISSING_MSG = (
    "camoucfg: 'webGl:renderer' is set but its pair 'webGl:vendor' is not.")
WEBGL2_RENDERER_MISSING_MSG = (
    "camoucfg: 'webGl2:vendor' is set but its pair 'webGl2:renderer' is not.")
REFUSAL = ("camoucfg: configuration is incoherent and CAMOU_CONFIG_STRICT is "
           "set; refusing to start.")

results = {}
notes = []


def failed(keys, label, exc):
    for key in keys:
        results[key] = False
    notes.append(f"{label}: {type(exc).__name__}: {exc}")


def read_stderr():
    """Guarded read of this session's browser stderr (verify_sp5a.py's helper).

    launch() opens the log 'wb', truncating it, so each read sees only its own
    session's stderr.
    """
    try:
        with open(lib_shell.STDERR_LOG, "rb") as handle:
            return handle.read().decode("utf-8", "replace"), None
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc


def stderr_after(config):
    """Runs a trivial session and returns (stderr, err). No GL needed: the
    pairing check runs at startup, before any page."""
    _, err = lib_shell.session(json.dumps(config), ["1"])
    if err is not None:
        return None, err
    return read_stderr()


def expect_line(name, config, present, absent=()):
    """PASS iff every string in `present` is in stderr and none in `absent`."""
    stderr, err = stderr_after(config)
    if err is not None:
        failed([name], f"{name} session", err)
        return
    results[name] = all(s in stderr for s in present) and all(
        s not in stderr for s in absent)
    if not results[name]:
        notes.append(f"{name}: stderr={stderr!r}")


def expect_strict_exit_13(name, config):
    """PASS iff a strict session exits during startup with code 13 and the
    refusal message. A hang (browser unusable) must not pass as a refusal --
    same discrimination as verify_sp5a.py C3."""
    _, err = lib_shell.session(json.dumps(config), ["1"], strict=True)
    if err is None:
        results[name] = False
        notes.append(f"{name}: browser started under CAMOU_CONFIG_STRICT=1 "
                     "with a half-configured pair; expected exit 13")
        return
    if "exited during startup" not in str(err):
        results[name] = False
        notes.append(
            f"{name}: not an exit-during-startup failure: "
            f"{type(err).__name__}: {err}")
        return
    code_text = str(err).rsplit("code ", 1)[-1]
    try:
        code = int(code_text)
    except ValueError:
        code = None
    if code != 13:
        results[name] = False
        notes.append(f"{name}: exited, but with the wrong code: {err}")
        return
    stderr, read_err = read_stderr()
    if read_err is not None:
        failed([name], f"{name} stderr read", read_err)
        return
    results[name] = REFUSAL in stderr
    if not results[name]:
        notes.append(f"{name}: exited 13 but stderr lacked the refusal: "
                     f"{stderr!r}")


# --- WP-MOTIVATION: the leak is real (page-side, under SwiftShader) ---
# Baseline reads the host renderer/vendor; the renderer-only config then reads
# the spoofed renderer beside the SAME host vendor. host_renderer != spoofed is
# the differ-guarantee (CLAUDE.md #4): the green cannot come from the host.
WP_MOT = ("WP-MOTIVATION renderer-only leaks host vendor beside spoofed "
          "renderer (unchanged by this slice)")
base_vals, base_err = lib_shell.session(None, [MOTIVATION], extra_flags=GL_FLAGS)
ro_vals, ro_err = lib_shell.session(
    json.dumps(RENDERER_ONLY), [MOTIVATION], extra_flags=GL_FLAGS)
if base_err is not None:
    failed([WP_MOT], "motivation baseline", base_err)
elif ro_err is not None:
    failed([WP_MOT], "motivation renderer-only", ro_err)
else:
    base, ro = base_vals[0], ro_vals[0]
    if not isinstance(base, dict) or "err" in base:
        results[WP_MOT] = False
        notes.append(f"WP-MOTIVATION baseline: {base}")
    elif not isinstance(ro, dict) or "err" in ro:
        results[WP_MOT] = False
        notes.append(f"WP-MOTIVATION renderer-only: {ro}")
    else:
        host_renderer, host_vendor = base["renderer"], base["vendor"]
        # Spoofed renderer applied AND differs from host (control),
        # while the vendor is the leaked host value, NOT the coherent one.
        results[WP_MOT] = (
            ro["renderer"] == V_RENDERER
            and host_renderer != V_RENDERER
            and ro["vendor"] == host_vendor
            and ro["vendor"] != V_VENDOR)
        notes.append(
            f"WP-MOTIVATION: host=({host_renderer!r},{host_vendor!r}) "
            f"renderer-only=({ro['renderer']!r},{ro['vendor']!r})")

# --- The rows this slice flips RED -> GREEN ---
expect_line("WP-HALF-LOG renderer-only logs webGl:vendor absent",
            RENDERER_ONLY, present=[VENDOR_MISSING_MSG])
expect_strict_exit_13(
    "WP-HALF-STRICT renderer-only under strict exits 13", RENDERER_ONLY)
expect_line("WP-VENDOR-ONLY vendor-only logs webGl:renderer absent",
            VENDOR_ONLY, present=[RENDERER_MISSING_MSG])
expect_line("WP-BOTH both set logs no pairing line",
            BOTH, present=[], absent=["is set but its pair"])
expect_line(
    "WP-PARAMS-GUARD-VENDOR vendor via parameters table logs no pairing line "
    "(false-refusal guard)",
    PARAMS_GUARD_VENDOR, present=[], absent=["is set but its pair"])
expect_line(
    "WP-PARAMS-GUARD-RENDERER renderer via parameters table logs no pairing "
    "line (false-refusal guard, renderer arm of GLStringResolves)",
    PARAMS_GUARD_RENDERER, present=[], absent=["is set but its pair"])
expect_line(
    "WP-CROSS webGl renderer + webGl2 vendor logs both APIs' absent pairs",
    CROSS, present=[VENDOR_MISSING_MSG, WEBGL2_RENDERER_MISSING_MSG])
expect_line("WP-NONE unconfigured logs no pairing line",
            {}, present=[], absent=["is set but its pair"])

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for note in notes:
    print(f"      {note}")

sys.exit(0 if results and all(results.values()) else 1)

"""Reproduces the shared-stderr-capture race that lib_shell.py fixes with O_APPEND.

The bug: content_shell's GPU process (which fails EGL init in WSL and spams
libEGL warnings) could write INSIDE a browser-process LOG line in the captured
stderr, so a verify script's exact-substring assertion missed the diagnostic
about one launch in a hundred. See
docs/superpowers/measurements/2026-09-08-verify-stderr-interleave-flake.md.

It is a timing race that needs the multi-launch SEQUENCE, not one config (50
launches of a single config were clean; the faithful sequence below caught it in
128). Run this against a build with lib_shell reverted to `open(STDERR_LOG,"wb")`
to see LINE-ABSENT misses; against the O_APPEND version to see none.

Not a CI test -- it launches content_shell hundreds of times and leaves /tmp
dumps of any miss. Run: python3 scripts/measure_stderr_capture_race.py [M] [nogl]
  M     -- repeats of the row sequence (default 8)
  nogl  -- drop the GL MOTIVATION row (it exhausts the WSLg display under rapid
           repeat, an unrelated X11 abort; drop it to isolate the capture race)
"""
import json
import sys

import lib_shell

GL = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
V_R, V_V = "NVIDIA GeForce RTX 4090", "Google Inc. (NVIDIA)"
PARAMS = {"webGl:parameters": {"3379": 16384}}


def cap(k, w2=False):
    r = "webGl2:renderer" if w2 else "webGl:renderer"
    v = "webGl2:vendor" if w2 else "webGl:vendor"
    return f"camoucfg: '{k}' is set but neither '{r}' nor '{v}' is."


# (name, config, flags, strict, want): want=str expected present, "" = silent,
# None = GL page-probe row (only its startup matters here).
ROWS = [
    ("MOTIVATION", PARAMS, GL, False, None),
    ("PARAMS-LOG", PARAMS, None, False, cap("webGl:parameters")),
    ("PARAMS-STRICT", PARAMS, None, True, "STRICT13"),
    ("EXT-LOG", {"webGl:supportedExtensions": ["EXT_texture_filter_anisotropic", "OES_element_index_uint"]}, None, False, cap("webGl:supportedExtensions")),
    ("SHADERPREC-LOG", {"webGl:shaderPrecisionFormats": {"35633:36338": [100, 100, 20]}}, None, False, cap("webGl:shaderPrecisionFormats")),
    ("CTXATTRS-LOG", {"webGl:contextAttributes": {"antialias": False, "preserveDrawingBuffer": True}}, None, False, cap("webGl:contextAttributes")),
    ("WITH-IDENTITY", {**PARAMS, "webGl:renderer": V_R, "webGl:vendor": V_V}, None, False, ""),
    ("PARTIAL-IDENTITY", {**PARAMS, "webGl:renderer": V_R}, None, False, ""),
    ("IDENTITY-ONLY", {"webGl:renderer": V_R, "webGl:vendor": V_V}, None, False, ""),
    ("WEBGL2", {"webGl2:parameters": {"3379": 16384}}, None, False, cap("webGl2:parameters", True)),
    ("WEBGL2-EXT", {"webGl2:supportedExtensions": ["EXT_texture_filter_anisotropic", "OES_element_index_uint"]}, None, False, cap("webGl2:supportedExtensions", True)),
    ("WEBGL2-SHADERPREC", {"webGl2:shaderPrecisionFormats": {"35633:36338": [100, 100, 20]}}, None, False, cap("webGl2:shaderPrecisionFormats", True)),
    ("WEBGL2-CTXATTRS", {"webGl2:contextAttributes": {"antialias": False, "preserveDrawingBuffer": True}}, None, False, cap("webGl2:contextAttributes", True)),
    ("EMPTY-DICT", {"webGl:parameters": {}}, None, False, ""),
    ("EMPTY-LIST", {"webGl:supportedExtensions": []}, None, False, ""),
    ("WRONG-TYPE", {"webGl:parameters": "oops"}, None, False, ""),
]

M = int(sys.argv[1]) if len(sys.argv) > 1 else 8
if "nogl" in sys.argv[2:]:
    ROWS = [r for r in ROWS if r[2] is None]

miss = {}
lens = []
for rep in range(M):
    for name, cfg, flags, strict, want in ROWS:
        _, err = lib_shell.session(json.dumps(cfg), ["1"], extra_flags=flags,
                                   strict=strict)
        try:
            with open(lib_shell.STDERR_LOG, "rb") as h:
                se = h.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001 - any fault must count as a miss
            se = f"<read-err {exc}>"
        bad = None
        if want == "STRICT13":
            if not (err and "code 13" in str(err)):
                bad = f"SESSION-ERR:{err}" if err else "NO-EXIT13"
        elif want is None:
            if err:
                bad = f"GL-STARTUP-ERR:{err}"
        elif want == "":
            if err:
                bad = f"SESSION-ERR:{err}"
            elif "is set but neither" in se:
                bad = "UNEXPECTED-LINE"
        else:
            lens.append(len(se))
            if err:
                bad = f"SESSION-ERR:{err}"
            elif want not in se:
                bad = "LINE-ABSENT"
        if bad:
            kind = bad.split(":")[0]
            miss[(name, kind)] = miss.get((name, kind), 0) + 1
            fn = f"/tmp/stderr_race_{rep}_{name}.log"
            with open(fn, "w") as d:
                d.write(f"# rep={rep} row={name} bad={bad} len={len(se)}\n{se}")
            print(f"MISS rep{rep} {name}: {bad} len={len(se)} -> {fn}")
    print(f"-- rep {rep} done --")

print(f"\n=== misses over {M} reps ({M * len(ROWS)} launches) ===")
for (name, kind), n in sorted(miss.items()):
    print(f"  {n:2d}  {name:18s} {kind}")
if not miss:
    print("  none")
if lens:
    print(f"line-expecting stderr len: min={min(lens)} max={max(lens)}")
sys.exit(0)

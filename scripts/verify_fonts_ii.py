"""Verifies fonts-ii (@font-face src:local() gating) against a built content_shell.

Structured like verify_sp5a.py: any one session's fault becomes a FAIL line, not
a traceback that discards the results already collected.

The behavioral RED is F-LEAK. Against a content_shell built BEFORE the
local_font_face_source gate, an excluded local() family still resolves
(FontFace.status == "loaded"); after, it is "error". FontFace.status is the
discriminator on purpose -- document.fonts.check() returns true for both loaded
and errored faces (per the sp4-fonts measurement), so a check()-based verify
would go green for free.
"""

import json
import os
import sys

import lib_shell

# A font the host actually has (fc-list on the WSL box; the installed set on the
# Windows host), so local() can resolve it and the leak is observable -- the
# cross-method tell is not "structurally blind" when the probe font is
# host-present. HOST_SERIF must not be the host's default sans-serif (F-DIRECT
# confound); on Windows neither Verdana nor Georgia is a generic default
# (Arial, Times New Roman and Consolas are).
if os.name == "nt":
    HOST_FONT, HOST_FONT_PS, HOST_SERIF = "Verdana", "Verdana", "Georgia"
else:
    HOST_FONT = "DejaVu Sans"
    HOST_FONT_PS = "DejaVuSans"      # its PostScript name (resolves too)
    HOST_SERIF = "DejaVu Serif"      # not the box sans-serif default (F-DIRECT confound)

results = {}
notes = []


def failed(keys, label, exc):
    for key in keys:
        results[key] = False
    notes.append(f"{label}: {type(exc).__name__}: {exc}")


def page_probe(name):
    # FontFace.status after load() settles, evaluated in the page.
    return (
        "(async () => {"
        f"  const f = new FontFace('probe', 'local(\"{name}\")');"
        "  try { await f.load(); } catch (e) {}"
        "  return f.status;"
        "})()"
    )


def worker_probe(name):
    # Same probe inside a DedicatedWorker (WorkerGlobalScope has FontFace + fonts).
    code = (
        "self.onmessage = async () => {"
        f"  const f = new FontFace('probe', 'local(\"{name}\")');"
        "  try { await f.load(); } catch (e) {}"
        "  self.postMessage(f.status);"
        "};"
    )
    return (
        "(async () => {"
        f"  const blob = new Blob([{json.dumps(code)}], "
        "    {type: 'application/javascript'});"
        "  const w = new Worker(URL.createObjectURL(blob));"
        "  return await new Promise((res) => {"
        "    w.onmessage = (e) => res(e.data);"
        "    w.postMessage(0);"
        "  });"
        "})()"
    )


ABSENT_FONT = "NoSuchFontXYZ123"
# A listed host font that local() loads, for the loaded decoy: its full name must be
# its family name (local() matches full and PostScript names; Lato's is "Lato Regular").
# Every F-CHECK config lists it.
LOAD_SRC = HOST_SERIF
CHECK_LIST = sorted({"Lato", LOAD_SRC})


def check_probe(name, worker=False):
    # document.fonts.check(font, 'a') for [name, ABSENT_FONT] in three forms:
    #   plain:    no face of that name (true for any name: verify_sp4_fonts F4);
    #   unloaded: a never-loaded FontFace decoy of each name; check() answers from
    #             the platform predicate (true: the host has it) or the decoy
    #             (false: not loaded and its range holds 'a') -- the leak's form;
    #   loaded:   the decoy replaced by a loaded local(LOAD_SRC) face (true either way).
    # status is the loaded decoys' FontFace.status: a load that failed would measure
    # the unloaded form again.
    names = json.dumps([name, ABSENT_FONT])
    body = (
        f"const fs = {'self' if worker else 'document'}.fonts;"
        f"const names = {names};"
        "const chk = () => names.map((n) => fs.check('40px \\\"' + n + '\\\"', 'a'));"
        "const out = {plain: chk()};"
        "let faces = names.map((n) => new FontFace(n, 'url(/decoy-never-loaded.woff2)'));"
        "faces.forEach((f) => fs.add(f));"
        "out.unloaded = chk();"
        "faces.forEach((f) => fs.delete(f));"
        f"faces = names.map((n) => new FontFace(n, 'local(\\\"{LOAD_SRC}\\\")'));"
        "faces.forEach((f) => fs.add(f));"
        "await Promise.all(faces.map((f) => f.load().catch(() => null)));"
        "out.loaded = chk();"
        "out.status = faces.map((f) => f.status);"
    )
    if not worker:
        return f"(async () => {{ {body} return out; }})()"
    code = f"self.onmessage = async () => {{ {body} self.postMessage(out); }};"
    return (
        "(async () => {"
        f"  const blob = new Blob([{json.dumps(code)}], "
        "    {type: 'application/javascript'});"
        "  const w = new Worker(URL.createObjectURL(blob));"
        "  return await new Promise((res) => {"
        "    w.onmessage = (e) => res(e.data);"
        "    w.postMessage(0);"
        "  });"
        "})()"
    )


# check_probe answers: a hidden host family must read exactly as the absent name
# (stock for a family the machine lacks); a listed one as stock.
HIDDEN = {"plain": [True, True], "unloaded": [False, False], "loaded": [True, True],
          "status": ["loaded", "loaded"]}
SHOWN = {"plain": [True, True], "unloaded": [True, False], "loaded": [True, True],
         "status": ["loaded", "loaded"]}


def status_case(key, cfg, js, want):
    config = json.dumps(cfg) if cfg is not None else None
    values, err = lib_shell.session(config, [js])
    if err is not None:
        failed([key], key, err)
        return
    got = values[0]
    results[key] = (got == want)
    if not results[key]:
        notes.append(f"{key}: got status {got!r}, want {want!r}")


# --- F-LEAK: an excluded local() family must not resolve (the RED) ---
status_case(
    "F-LEAK excluded local() family -> error (RED: loaded pre-fix)",
    {"fonts:list": ["Lato"]}, page_probe(HOST_FONT), "error")

# --- F-LISTED: a listed local() family still resolves (anti-overblock) ---
status_case(
    "F-LISTED listed local() family still loaded",
    {"fonts:list": [HOST_FONT, "Lato"]}, page_probe(HOST_FONT), "loaded")

# --- F-STOCK: no fonts:list is a no-op (rule 5) ---
status_case(
    "F-STOCK no fonts:list -> loaded",
    None, page_probe(HOST_FONT), "loaded")

# --- F-WORKER: worker parity, both halves ---
status_case(
    "F-WORKER excluded local() in a worker -> error (parity)",
    {"fonts:list": ["Lato"]}, worker_probe(HOST_FONT), "error")
# The listed half too: a gate that blocked every local() in a worker would pass
# the excluded case above while breaking rendering, so assert a listed family
# still resolves in the worker (matches F-LISTED on the window side).
status_case(
    "F-WORKER-LISTED listed local() in a worker -> loaded (parity)",
    {"fonts:list": [HOST_FONT, "Lato"]}, worker_probe(HOST_FONT), "loaded")

# --- F-CHECK: document.fonts.check() must not tell a hidden host family from an
# absent one (RED pre-fix: unloaded [true, false]; FontCache::IsPlatformFamilyMatchAvailable
# answered for the host) ---
status_case(
    "F-CHECK hidden host family reads as absent in check() (RED: unloaded [true, false] pre-fix)",
    {"fonts:list": CHECK_LIST}, check_probe(HOST_FONT), HIDDEN)
status_case(
    "F-CHECK-WORKER hidden host family reads as absent in a worker's check() (parity)",
    {"fonts:list": CHECK_LIST}, check_probe(HOST_FONT, worker=True), HIDDEN)
status_case(
    "F-CHECK-LISTED listed host family answers check() as stock",
    {"fonts:list": sorted({HOST_FONT, *CHECK_LIST})}, check_probe(HOST_FONT), SHOWN)
status_case(
    "F-CHECK-STOCK no fonts:list -> check() as stock",
    None, check_probe(HOST_FONT), SHOWN)
if os.name == "nt":
    # A Windows suffix name of a listed family (font_cache_skia_win.cc strips " semibold"
    # and finds Segoe UI) answers as stock does: the gate admits it as font_fallback_list
    # does (#228), under a Windows claim only.
    status_case(
        "F-CHECK-SUFFIX listed family's suffix name answers check() as stock (Windows)",
        {"fonts:list": sorted({"Segoe UI", *CHECK_LIST}), "ua:platform": "Windows"},
        check_probe("Segoe UI Semibold"), SHOWN)

# --- F-DIRECT: sp4-fonts direct-probe gate still holds (regression) ---
F_DIRECT = "F-DIRECT excluded measureText falls back (sp4-fonts intact)"
direct_js = (
    "(() => {"
    "  const c = document.createElement('canvas').getContext('2d');"
    f"  c.font = '40px \"{HOST_SERIF}\", monospace';"
    "  const w1 = c.measureText('mmmmmwwwwwiiiii').width;"
    "  c.font = '40px monospace';"
    "  const w2 = c.measureText('mmmmmwwwwwiiiii').width;"
    "  return [w1, w2];"
    "})()"
)
values, err = lib_shell.session(json.dumps({"fonts:list": ["Lato"]}), [direct_js])
if err is not None:
    failed([F_DIRECT], F_DIRECT, err)
else:
    w1, w2 = values[0]
    # Excluded specific family must resolve to the trailing generic, so the two
    # widths match. (If DejaVu Serif leaked, w1 != w2.)
    results[F_DIRECT] = (w1 == w2)
    if not results[F_DIRECT]:
        notes.append(f"{F_DIRECT}: widths differ, {w1} vs {w2} (font leaked)")

# --- F-PSNAME: residual MEASUREMENT, not pass/fail ---
# A listed font probed by its PostScript name. A family allowlist cannot match a
# PS name, so after the fix this is over-blocked (error). Recorded as a number.
values, err = lib_shell.session(
    json.dumps({"fonts:list": [HOST_FONT]}), [page_probe(HOST_FONT_PS)])
ps_status = err if err is not None else values[0]
notes.append(
    f"[residual] F-PSNAME listed font by PS name '{HOST_FONT_PS}' -> {ps_status!r} "
    f"(over-block expected after fix; family allowlist can't match a PS name)")

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for note in notes:
    print(f"      {note}")

sys.exit(0 if results and all(results.values()) else 1)

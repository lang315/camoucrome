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
import sys

import lib_shell

# A font the WSL host actually has (fc-list), so local() can resolve it and the
# leak is observable on Linux -- the cross-method tell is not "structurally
# blind" here when the probe font is host-present.
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

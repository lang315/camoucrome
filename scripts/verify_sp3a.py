"""Verifies the SP3a canvas-readback hooks: with canvas:seed set, the pixels
that leave a canvas through EVERY page-reachable readback path carry
deterministic noise, while an unconfigured build stays byte-identical to stock.

Ten criteria, all driven with Playwright's sync API over content_shell's CDP,
the same shape as verify_sp2b.py / verify_sp1a.py -- a fault in any one session
becomes FAIL lines, never a traceback that discards results already collected.

Snapshot family (Task 4):
  C1 seeded toDataURL is deterministic across two reads (HIGHEST -- a re-read of
     the same canvas must reproduce, or the noise is itself a tell).
  C2 seeded toDataURL differs from the stock baseline (spoof visible).
  C3 unconfigured toDataURL is byte-identical to stock (off by default, rule 5).
  C4 seeded toBlob is deterministic and differs from stock.

Direct-read family (Task 5):
  C5 seeded getImageData is deterministic across two reads, differs from stock,
     and is byte-identical to stock when unconfigured.
  C6 seeded WebGL readPixels is deterministic, differs from stock, and is
     byte-identical to stock unconfigured (run under SwiftShader for a stable,
     host-independent GL context -- SP3 spec Section 6).
  C7 seeded OffscreenCanvas.convertToBlob is deterministic and differs from
     stock -- closes the Task-4 gap that convertToBlob had no runtime criterion.

Cross-cutting:
  C8 worker parity: an OffscreenCanvas rendered + read back inside a DEDICATED
     worker is deterministic and differs from stock, proving the noise reaches
     worker-thread readback via the process-inherited config (Section 4.4).
     (SharedWorker, in its own process, needs a real HTTP origin and is a
     documented follow-up; a dedicated worker exercises the worker readback
     path this task wired.)
  C9 screen unchanged: a DevTools Page.captureScreenshot (NOT a canvas readback)
     of the rendered canvas is byte-identical between the seeded and stock
     builds -- proves noise is applied at readback, never at draw time (item 10).
  C10 accessors native: toDataURL / getImageData / readPixels prototype methods
     still stringify to "[native code]" and Object.keys(window) is unchanged vs
     stock (rule 2).

The "stock" reference is a PERSISTED baseline captured once from a STOCK
content_shell (before the Blink edit exists), into baselines/, exactly as
verify_sp1a captures its stock UA. Run with --capture-baseline against the stock
binary FIRST; that run also prints the criteria (the "differs" ones FAIL on
stock, since a stock seeded run == stock), which is the required RED-first
evidence. Every later run reads that frozen baseline.
"""

import hashlib
import json
import os
import sys

from playwright.sync_api import sync_playwright

import lib_shell

CANVAS = json.dumps({"canvas:seed": 987654321})
# SwiftShader gives a stable, host-independent GL context so WebGL readback is
# reproducible; --enable-unsafe-swiftshader is required on current Chromium for
# the fallback to engage at all (SP3 spec Section 6).
GL_FLAGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]

BASELINE = os.path.expanduser(
    "~/camoucrome-verify/baselines/content_shell-sp3a-stock-canvas.json")

# A fixed, non-trivial 2D scene: a diagonal three-stop gradient, a translucent
# circle, an opaque rectangle, and anti-aliased text. Content varies across the
# frame so PerturbRgba's content-hash fold has real input, and the alpha + text
# exercise the alpha channel the noise must leave untouched. Drawn identically
# every run, so any byte difference between two runs is the noise.
SCENE_2D = """
  const c = document.createElement('canvas');
  c.width = 300; c.height = 200;
  const ctx = c.getContext('2d');
  const g = ctx.createLinearGradient(0, 0, 300, 200);
  g.addColorStop(0, '#ff2d00');
  g.addColorStop(0.5, '#00c853');
  g.addColorStop(1, '#1a2fff');
  ctx.fillStyle = g; ctx.fillRect(0, 0, 300, 200);
  ctx.fillStyle = 'rgba(255,255,255,0.6)';
  ctx.beginPath(); ctx.arc(150, 100, 55, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = '#123456'; ctx.fillRect(20, 20, 90, 44);
  ctx.fillStyle = '#000000'; ctx.font = '22px sans-serif';
  ctx.fillText('Camoucrome-SP3a', 24, 160);
"""

# A stable content-hash (FNV-1a-ish djb2) over every byte of a typed array,
# computed in-page so we never ship 240KB of pixels back over CDP.
HASH_FN = """
  const H = (d) => { let h = 5381 >>> 0;
    for (let i = 0; i < d.length; i++) h = (((h << 5) + h) ^ d[i]) >>> 0;
    return h; };
"""

# Draws SCENE_2D and reads it back four ways in one document: toDataURL x2,
# toBlob x2 (as base64), getImageData x2 (hashed). Screenshot is captured
# separately via CDP so it cannot go through a canvas readback API.
DRAW_AND_READ = f"""() => new Promise((resolve, reject) => {{
  try {{
    {SCENE_2D}
    {HASH_FN}
    const d1 = c.toDataURL('image/png');
    const d2 = c.toDataURL('image/png');
    const gi1 = H(ctx.getImageData(0, 0, 300, 200).data);
    const gi2 = H(ctx.getImageData(0, 0, 300, 200).data);
    const asBlob = () => new Promise((res, rej) =>
      c.toBlob((b) => b ? res(b) : rej(new Error('toBlob null')), 'image/png'));
    const toB64 = (blob) => new Promise((res, rej) => {{
      const fr = new FileReader();
      fr.onload = () => res(fr.result); fr.onerror = () => rej(fr.error);
      fr.readAsDataURL(blob);
    }});
    (async () => {{
      const b1 = await toB64(await asBlob());
      const b2 = await toB64(await asBlob());
      resolve({{ d1, d2, b1, b2, gi1, gi2 }});
    }})().catch(reject);
  }} catch (e) {{ reject(e); }}
}})
"""

# WebGL readPixels x2 of a fixed clear color. Flat colour is deliberate: the
# content-hash fold makes the noise depend on content, so a flat frame is the
# hardest case for "differs from stock" and the easiest to reason about.
DRAW_AND_READ_GL = f"""() => {{
  const c = document.createElement('canvas'); c.width = 64; c.height = 64;
  const gl = c.getContext('webgl');
  if (!gl) return {{ err: 'no-webgl' }};
  gl.clearColor(0.2, 0.5, 0.8, 1.0); gl.clear(gl.COLOR_BUFFER_BIT);
  {HASH_FN}
  const p1 = new Uint8Array(64 * 64 * 4);
  gl.readPixels(0, 0, 64, 64, gl.RGBA, gl.UNSIGNED_BYTE, p1);
  const p2 = new Uint8Array(64 * 64 * 4);
  gl.readPixels(0, 0, 64, 64, gl.RGBA, gl.UNSIGNED_BYTE, p2);
  return {{ r1: H(p1), r2: H(p2) }};
}}
"""

# OffscreenCanvas.convertToBlob in a DEDICATED worker: draws the same-shaped 2D
# scene on an OffscreenCanvas the worker owns, reads it back via getImageData,
# and returns two hashes. The worker runs on its own thread and derives the seed
# from the process-inherited CAMOU_CONFIG (Section 4.4), so a difference from
# stock proves the noise reaches worker readback.
WORKER_READBACK = """() => new Promise((resolve, reject) => {
  const src = `
    self.onmessage = () => {
      const c = new OffscreenCanvas(300, 200);
      const ctx = c.getContext('2d');
      const g = ctx.createLinearGradient(0, 0, 300, 200);
      g.addColorStop(0, '#ff2d00'); g.addColorStop(0.5, '#00c853');
      g.addColorStop(1, '#1a2fff');
      ctx.fillStyle = g; ctx.fillRect(0, 0, 300, 200);
      ctx.fillStyle = '#000000'; ctx.font = '22px sans-serif';
      ctx.fillText('Camoucrome-SP3a', 24, 160);
      const H = (d) => { let h = 5381 >>> 0;
        for (let i = 0; i < d.length; i++) h = (((h << 5) + h) ^ d[i]) >>> 0;
        return h; };
      const w1 = H(ctx.getImageData(0, 0, 300, 200).data);
      const w2 = H(ctx.getImageData(0, 0, 300, 200).data);
      self.postMessage({ w1, w2 });
    };`;
  try {
    const w = new Worker(URL.createObjectURL(
      new Blob([src], { type: 'text/javascript' })));
    w.onmessage = (e) => resolve(e.data);
    w.onerror = (e) => reject(new Error(e.message || 'worker error'));
    w.postMessage('go');
  } catch (e) { reject(e); }
})
"""

# Native-accessor probe (rule 2). Returns whether each prototype method still
# stringifies to [native code], plus a hash of Object.keys(window) so a leaked
# global (e.g. a setter left on window) shows as a mismatch vs stock.
NATIVE_PROBE = """() => {
  const nat = (o, m) => {
    try { return /\\[native code\\]/.test(
      Object.getOwnPropertyDescriptor(o, m).value.toString()); }
    catch (e) { return false; }
  };
  const H = (s) => { let h = 5381 >>> 0;
    for (let i = 0; i < s.length; i++) h = (((h << 5) + h) ^ s.charCodeAt(i)) >>> 0;
    return h; };
  return {
    toDataURL: nat(HTMLCanvasElement.prototype, 'toDataURL'),
    getImageData: nat(CanvasRenderingContext2D.prototype, 'getImageData'),
    readPixels: nat(WebGLRenderingContext.prototype, 'readPixels'),
    winkeys: H(Object.keys(window).sort().join(',')),
  };
}
"""


def session(config, fn, extra_flags=None, screenshot=False):
    """One content_shell session. Runs page-function `fn` (a JS string) after
    navigating to about:blank, or captures a CDP screenshot if `screenshot`.
    Returns (value, err); any fault becomes a FAIL, never a traceback."""
    proc = None
    try:
        proc = lib_shell.launch(config, extra_flags=extra_flags)
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(
                f"http://127.0.0.1:{proc.cdp_port}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("about:blank", wait_until="load")
            if screenshot:
                # Draw the scene into the visible document, then screenshot via
                # the DevTools protocol -- NOT a canvas readback API.
                page.evaluate(f"() => {{ {SCENE_2D} document.body.appendChild(c); }}")
                cdp = context.new_cdp_session(page)
                shot = cdp.send("Page.captureScreenshot", {"format": "png"})
                return shot["data"], None
            return page.evaluate(fn), None
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)


def sha(s):
    if not isinstance(s, str):
        s = json.dumps(s)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


capture = "--capture-baseline" in sys.argv[1:]
results = {}
notes = []

# --- Live runs on the binary under test ---
seeded, seeded_err = session(CANVAS, DRAW_AND_READ)
unconf, unconf_err = session(None, DRAW_AND_READ)
seeded_gl, seeded_gl_err = session(CANVAS, DRAW_AND_READ_GL, extra_flags=GL_FLAGS)
unconf_gl, unconf_gl_err = session(None, DRAW_AND_READ_GL, extra_flags=GL_FLAGS)
seeded_w, seeded_w_err = session(CANVAS, WORKER_READBACK)
seeded_shot, seeded_shot_err = session(CANVAS, None, screenshot=True)
unconf_shot, unconf_shot_err = session(None, None, screenshot=True)
native, native_err = session(CANVAS, NATIVE_PROBE)

# --- OffscreenCanvas.convertToBlob (main thread) for C7 ---
CONVERT_TO_BLOB = f"""() => new Promise((resolve, reject) => {{
  try {{
    const oc = new OffscreenCanvas(300, 200);
    const ctx = oc.getContext('2d');
    const g = ctx.createLinearGradient(0, 0, 300, 200);
    g.addColorStop(0, '#ff2d00'); g.addColorStop(0.5, '#00c853');
    g.addColorStop(1, '#1a2fff');
    ctx.fillStyle = g; ctx.fillRect(0, 0, 300, 200);
    ctx.fillStyle = '#000'; ctx.font = '22px sans-serif';
    ctx.fillText('Camoucrome-SP3a', 24, 160);
    {HASH_FN}
    const rd = (blob) => new Promise((res, rej) => {{
      const fr = new FileReader();
      fr.onload = () => res(new Uint8Array(fr.result));
      fr.onerror = () => rej(fr.error);
      fr.readAsArrayBuffer(blob);
    }});
    (async () => {{
      const h1 = H(await rd(await oc.convertToBlob({{ type: 'image/png' }})));
      const h2 = H(await rd(await oc.convertToBlob({{ type: 'image/png' }})));
      resolve({{ o1: h1, o2: h2 }});
    }})().catch(reject);
  }} catch (e) {{ reject(e); }}
}})
"""
seeded_oc, seeded_oc_err = session(CANVAS, CONVERT_TO_BLOB)

if capture:
    if unconf is None or unconf_gl is None or unconf_shot is None:
        notes.append("capture: a stock session failed; baseline incomplete")
    b = {}
    if unconf is not None:
        b["toDataURL"] = sha(unconf["d1"])
        b["toBlob"] = sha(unconf["b1"])
        b["getImageData"] = unconf["gi1"]
    if unconf_gl is not None and "r1" in unconf_gl:
        b["readPixels"] = unconf_gl["r1"]
    if seeded_oc is not None:  # OffscreenCanvas has no seed-free host divergence
        pass
    # convertToBlob + worker stock refs come from unconfigured runs:
    oc_stock, _ = session(None, CONVERT_TO_BLOB)
    if oc_stock is not None:
        b["convertToBlob"] = oc_stock["o1"]
    w_stock, _ = session(None, WORKER_READBACK)
    if w_stock is not None:
        b["worker"] = w_stock["w1"]
    if unconf_shot is not None:
        b["screenshot"] = sha(unconf_shot)
    if native is not None:
        b["winkeys"] = native["winkeys"]
    os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
    with open(BASELINE, "w") as fh:
        json.dump(b, fh, indent=2)
    notes.append(f"capture: wrote stock baseline to {BASELINE}")

baseline = None
try:
    with open(BASELINE) as fh:
        baseline = json.load(fh)
except Exception as exc:  # noqa: BLE001
    notes.append(f"baseline load from {BASELINE}: {type(exc).__name__}: {exc}")


def bl(key):
    return baseline.get(key) if baseline else None


C1 = "1  seeded toDataURL deterministic across two reads"
C2 = "2  seeded toDataURL differs from stock"
C3 = "3  unconfigured toDataURL byte-identical to stock"
C4 = "4  seeded toBlob deterministic and differs from stock"
C5 = "5  seeded getImageData deterministic, differs from stock, off==stock"
C6 = "6  seeded readPixels deterministic, differs from stock, off==stock"
C7 = "7  seeded OffscreenCanvas.convertToBlob deterministic and differs"
C8 = "8  worker OffscreenCanvas readback deterministic and differs (parity)"
C9 = "9  DevTools screenshot identical seeded vs stock (screen unchanged)"
C10 = "10 accessors native + window keys unchanged"

# C1
if seeded is None:
    results[C1] = False
    notes.append(f"C1: {type(seeded_err).__name__}: {seeded_err}")
else:
    results[C1] = seeded["d1"] == seeded["d2"]
    if not results[C1]:
        notes.append("C1: two toDataURL reads differ -- noise not reproducible")

# C2
results[C2] = bool(seeded and baseline and sha(seeded["d1"]) != bl("toDataURL"))
if seeded and baseline and not results[C2]:
    notes.append("C2: seeded toDataURL equals stock -- no visible spoof")

# C3
if unconf is None or baseline is None:
    results[C3] = False
    if unconf_err:
        notes.append(f"C3: {type(unconf_err).__name__}: {unconf_err}")
else:
    results[C3] = sha(unconf["d1"]) == bl("toDataURL")
    if not results[C3]:
        notes.append("C3: unconfigured toDataURL differs from stock -- wrap "
                     "altered bytes when noise off")

# C4
if seeded is None or baseline is None:
    results[C4] = False
else:
    results[C4] = (seeded["b1"] == seeded["b2"]
                   and sha(seeded["b1"]) != bl("toBlob"))
    if not results[C4]:
        notes.append("C4: toBlob not deterministic or equals stock")

# C5 getImageData
if seeded is None or unconf is None or baseline is None:
    results[C5] = False
else:
    determ = seeded["gi1"] == seeded["gi2"]
    differs = seeded["gi1"] != bl("getImageData")
    off_eq = unconf["gi1"] == bl("getImageData")
    results[C5] = determ and differs and off_eq
    if not results[C5]:
        notes.append(f"C5: determ={determ} differs={differs} off==stock={off_eq}")

# C6 readPixels
if seeded_gl is None or unconf_gl is None or baseline is None:
    results[C6] = False
    if seeded_gl_err:
        notes.append(f"C6: {type(seeded_gl_err).__name__}: {seeded_gl_err}")
elif "err" in seeded_gl or "err" in unconf_gl:
    results[C6] = False
    notes.append("C6: WebGL unavailable in content_shell even under SwiftShader "
                 "-- not a pass; investigate the GL context (do not fake-pass)")
else:
    determ = seeded_gl["r1"] == seeded_gl["r2"]
    differs = seeded_gl["r1"] != bl("readPixels")
    off_eq = unconf_gl["r1"] == bl("readPixels")
    results[C6] = determ and differs and off_eq
    if not results[C6]:
        notes.append(f"C6: determ={determ} differs={differs} off==stock={off_eq}")

# C7 convertToBlob
if seeded_oc is None or baseline is None:
    results[C7] = False
    if seeded_oc_err:
        notes.append(f"C7: {type(seeded_oc_err).__name__}: {seeded_oc_err}")
else:
    results[C7] = (seeded_oc["o1"] == seeded_oc["o2"]
                   and seeded_oc["o1"] != bl("convertToBlob"))
    if not results[C7]:
        notes.append("C7: convertToBlob not deterministic or equals stock")

# C8 worker parity
if seeded_w is None or baseline is None:
    results[C8] = False
    if seeded_w_err:
        notes.append(f"C8: {type(seeded_w_err).__name__}: {seeded_w_err}")
else:
    results[C8] = (seeded_w["w1"] == seeded_w["w2"]
                   and seeded_w["w1"] != bl("worker"))
    if not results[C8]:
        notes.append("C8: worker readback not deterministic or equals stock -- "
                     "noise did not reach the worker thread")

# C9 screen unchanged
if seeded_shot is None or baseline is None:
    results[C9] = False
    if seeded_shot_err:
        notes.append(f"C9: {type(seeded_shot_err).__name__}: {seeded_shot_err}")
else:
    results[C9] = sha(seeded_shot) == bl("screenshot")
    if not results[C9]:
        notes.append("C9: seeded screenshot differs from stock -- noise leaked "
                     "to draw time / composited output")

# C10 native accessors
if native is None or baseline is None:
    results[C10] = False
    if native_err:
        notes.append(f"C10: {type(native_err).__name__}: {native_err}")
else:
    all_native = (native["toDataURL"] and native["getImageData"]
                  and native["readPixels"])
    keys_same = native["winkeys"] == bl("winkeys")
    results[C10] = all_native and keys_same
    if not results[C10]:
        notes.append(f"C10: native={all_native} winkeys_same={keys_same}")

EXPECTED = 10

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")

if len(results) != EXPECTED:
    notes.append(f"expected {EXPECTED} criteria, found {len(results)} -- a "
                 "criterion was added/removed without updating EXPECTED")

for note in notes:
    print(f"      {note}")

if results and len(results) == EXPECTED and all(results.values()):
    print("ALL_PASS")
    sys.exit(0)
print("FAIL")
sys.exit(1)

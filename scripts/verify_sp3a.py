"""Verifies the SP3a canvas-readback hooks: with canvas:seed set, the pixels
that leave a canvas through EVERY page-reachable readback path carry
deterministic noise, while an unconfigured build stays byte-identical to stock.

A hundred and five criteria, all driven with Playwright's sync API over content_shell's CDP,
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
  C6 seeded WebGL readPixels of a gradient triangle is deterministic and
     differs from the unconfigured live run (SwiftShader for a stable,
     host-independent GL context -- SP3 spec Section 6); C11 keeps the
     unconfigured-clear == stock baseline check.
  C7 seeded OffscreenCanvas.convertToBlob of a gradient + arc scene (no text,
     so the hook is measured, not the text offset) is deterministic and differs
     from a live UNCONFIGURED session of the same scene.

Cross-cutting:
  C8 worker parity: an OffscreenCanvas (gradient + arc, no text) rendered + read
     back inside a DEDICATED worker is deterministic and differs from a live
     unconfigured worker run, proving the noise reaches worker-thread readback
     via the process-inherited config (Section 4.4).
     (SharedWorker, in its own process, needs a real HTTP origin and is a
     documented follow-up; a dedicated worker exercises the worker readback
     path this task wired.)
  C9 screen unchanged: a DevTools Page.captureScreenshot (NOT a canvas readback)
     of a text-free scene is byte-identical between the seeded and the
     unconfigured run -- readback noise never reaches the screen. (Text moves
     by the per-seed sub-pixel offset on screen too, so it is left out.)
  C10 accessors native: toDataURL / getImageData / readPixels prototype methods
     still stringify to "[native code]" and Object.keys(window) is unchanged vs
     stock (rule 2).

Canvas noise redesign rows:
  C11 flat drawings (solid, edge, 1px line, WebGL clear, worker) read as
     unconfigured; solid and clear stay one colour. Each 2D canvas also has a
     corner arc (so the canvas is eligible) and is read away from the arc.
  C12 putImageData of a random pattern reads back exact (the canvas is eligible:
     an arc was drawn first).
  C13 drawImage and createImageBitmap copies agree with getImageData (the
     destination is eligible until the import: an arc was drawn first).
  C14 the host oracle's shape canvases vary over 8 seeds, none stock; its text canvas is stock.
  C15 text under ctx.scale(40,40) lands within 1 device px of unconfigured (the
      text offset is in device space, so a page cannot magnify it).
  C16 a decoded image drawn onto an eligible canvas reads as unconfigured (any
      drawImage source makes the canvas carry no readback noise).
  C17 readPixels at PACK_ALIGNMENT 8 with an odd width agrees, pixel for
      pixel, with the default layout; the padding bytes are untouched.
  C18 a WebGL2 PACK_ROW_LENGTH / SKIP_PIXELS / SKIP_ROWS readPixels agrees with
      the default read; every byte outside the layout is untouched.
  C19 a readPixels rect reaching past the buffer: its in-buffer part equals
      the default read, differs from the unconfigured one, and every byte
      outside the buffer is what the unconfigured read leaves there.
  C20 a readPixels GL rejects (INVALID_OPERATION: SKIP_PIXELS + width does not
      fit one row) leaves the page's buffer untouched.

Canvas noise S2b rows (patch-keyed field, per-region eligibility):
  C21 one arc at two whole-pixel offsets gets the same noise.
  C22 a draw elsewhere does not change a region's noise.
  C23 an arc plus a putImageData pattern elsewhere: the arc carries noise,
      the pattern reads back exactly.
  C24a-d a diagonal lineTo triangle, a round-cap stroke, a curved clip()
      with fillRect, and fillRect with shadowBlur each carry noise.
  C25 a reused canvas (putImageData, clearRect, arc) reads like a fresh one.
  C26 createPattern alone marks nothing; a pattern fill reads exact.
  C27 1px random colours under a diagonal line stay exact: eligibility
      follows coverage, not bounding boxes.
  C28 a WebGL readPixels sub-rect equals the full read's part.
  C29 WebGL toDataURL agrees with readPixels on every opaque pixel.
  C30-C32 a canvas wiped exact by destination-out, transferToImageBitmap or
      a 'copy' fill, then drawn with translucent 1px random colours, reads
      like a fresh canvas with the same drawing (no stale aa marks).
  C33a-d 1px random opaque colours stay byte-equal to unconfigured after a
      fully transparent arc, an all-transparent gradient arc, an opaque fill
      with an off-canvas shadow (then a speckle), and a blurred corner fillRect.
  C33e the same canvas after a fully transparent arc with a visible shadow:
      stock draws nothing, so it must equal unconfigured (and its own pre-draw state).
  C34 a 'copy' STROKE wipes the whole clip like a copy fill: after a translucent
      speckle the canvas reads like a fresh one with the same stroke.
  C35 a framebuffer readPixels of a gradient triangle is noised and deterministic.
  C36 a framebuffer readPixels sub-rect equals the matching part of the full read.
  C36b the same for rects whose margin or body crosses the far edge, and one
      with a negative origin (the row/column probe and the margin read).
  C37 a framebuffer read leaves translucent pixels exact and changes an opaque one.
  C38 texImage2D(webgl canvas) read in a second context equals the source's read.
  C39 getImageData of a sub-rect equals the whole-snapshot field (full read and copy).
  C40 one flush or many give one mask.
  C41 a read with READ_BUFFER NONE leaves the page's buffer and the GL error as stock.
  C42 the same for a drawingBufferStorage(RGBA16F) default framebuffer.
  C43 a globalAlpha 0 drawImage over an arc's region leaves the region's noise
      unchanged (a draw that changes no pixel marks none).
  C44 a shadowed drawImage far from an arc leaves the arc's noise unchanged
      (the shadow marks its own pixels, not the whole clip).
  C44b the same with an opaque ({alpha:false}) source, whose shadow is drawn
      through a looper rather than a filtered layer.
  C45 getImageData of rects that cross the canvas edge (negative origin, past
      the far edge, negative size, a 1x1 corner) equals the full read's pixels
      (zero outside) and the same rect of a drawImage copy.
  C46 R8 and RG8 texture framebuffers read RGBA / UNSIGNED_BYTE as stock (G and
      B stay 0); an RGBA8 one with the same scene is noised.
  C46b an RGBA4 renderbuffer framebuffer reads as stock; an RGBA8 one is noised.
  C47 a drawingBufferStorage(SRGB8_ALPHA8) readPixels is noised and deterministic.
  C48 a globalAlpha 0 drawImage of an SVG image over an arc's region leaves
      the region's noise unchanged (an SVG draws through a layer and a nested
      record; a layer that composites nothing marks nothing).
  C49 a large readPixels sub-rect (above the one-piece size, so only its
      margin strips are read again), from the default framebuffer and from a
      page framebuffer, equals the matching part of the full read.
  C50 readPixels into a SharedArrayBuffer view (read and noised in private
      scratch, then copied once) equals the same read into a plain view, a
      padded layout and a sub-rect, and leaves the padding untouched (a
      session with SharedArrayBuffer enabled; the race it closes is not
      testable deterministically).
  C51 a shadowed globalAlpha 0 drawImage of a translucent canvas over an arc's
      region leaves the region's noise unchanged (the shadow's drop-shadow
      layer holds only a draw that paints nothing).
  C52 a url() filter that floods and then drop-shadows (feFlood, then
      feDropShadow in sRGB), over an alpha-0 fill on AA strokes: every pixel
      the filter paints reads as unconfigured (the filter paints from
      nothing, so its layer is marked).
  C53 the C18 layout (WebGL2 PACK_ROW_LENGTH / SKIP_PIXELS / SKIP_ROWS) read
      from a page framebuffer agrees with the default layout; every byte
      outside the layout is untouched.

  C100 an arc, then N one-pixel putImageData calls, then one getImageData of the arc's box, all in one task
      (N = 0, 1, 20, 40, 200): each seeded read differs from the unseeded read of the same scene.
  C101 a page draws 100 heavy 2D frames on one canvas with no read, then reads once: the seeded read is
      noised and stable; its time against none is reported (the read walks the backlog, rule D3).
  C102 overdraw elision: a clearRect of the whole canvas drops the queued mask jobs (CamouElided) and the
      next draw reads noised; a partial or clipped clear, a full-canvas fillRect, and no seed drop none.

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


import lib_shell

CANVAS = json.dumps({"canvas:seed": 987654321})
# SwiftShader gives a stable, host-independent GL context so WebGL readback is
# reproducible; --enable-unsafe-swiftshader is required on current Chromium for
# the fallback to engage at all (SP3 spec Section 6).
GL_FLAGS = lib_shell.SHELL_FLAGS + ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
# CAMOU_SP3A_GPU_CANVAS=1: every session without flags of its own runs on ANGLE/SwiftShader, whose 2D canvas is
# GPU-rastered (a default canvas differs from the SVG shapes it draws; content_shell's default one is a CPU canvas,
# exact). Readback noise is only put on GPU-rastered pixels (release -5, CPU gate), so the noise rows need it.
GPU_CANVAS = os.environ.get("CAMOU_SP3A_GPU_CANVAS") == "1"

# The stock reference of rows 2-5 is a canvas capture, and a CPU canvas and a GPU-rastered one read differently: one
# baseline per mode. The GPU-canvas one is captured box-locally under CAMOU_SP3A_GPU_CANVAS=1 (SwiftShader is
# deterministic) with --capture-baseline.
BASELINE = os.path.expanduser(
    "~/camoucrome-verify/baselines/content_shell-sp3a-stock-canvas" + ("-gpu" if GPU_CANVAS else "") + ".json")

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

# SCENE_2D without its text: under the target design text draws at a
# per-seed sub-pixel origin on screen too, so C9 checks the rest is untouched.
SCENE_NO_TEXT = SCENE_2D.split("  ctx.fillStyle = '#000000'; ctx.font")[0]

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

# WebGL readPixels x2 of a gradient triangle over a clear. A plain clear has no
# pixel unlike its neighbours, so the edge-only noise (canvas noise redesign)
# correctly leaves it alone; the triangle's interpolated colours and its
# anti-aliased edges give the noise something to touch.
DRAW_AND_READ_GL = "() => {" + HASH_FN + """
  const c = document.createElement('canvas'); c.width = 64; c.height = 64;
  const gl = c.getContext('webgl');
  if (!gl) return { err: 'no-webgl' };
  const sh = (type, src) => { const s = gl.createShader(type);
    gl.shaderSource(s, src); gl.compileShader(s); return s; };
  const pr = gl.createProgram();
  gl.attachShader(pr, sh(gl.VERTEX_SHADER,
    'attribute vec2 p;attribute vec3 k;varying vec3 v;void main(){v=k;gl_Position=vec4(p,0,1);}'));
  gl.attachShader(pr, sh(gl.FRAGMENT_SHADER,
    'precision mediump float;varying vec3 v;void main(){gl_FragColor=vec4(v,1);}'));
  gl.linkProgram(pr); gl.useProgram(pr);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(
    [-0.9, -0.8, 1, 0, 0,  0.85, -0.6, 0, 1, 0,  -0.1, 0.9, 0, 0, 1]), gl.STATIC_DRAW);
  const lp = gl.getAttribLocation(pr, 'p'), lk = gl.getAttribLocation(pr, 'k');
  gl.enableVertexAttribArray(lp); gl.vertexAttribPointer(lp, 2, gl.FLOAT, false, 20, 0);
  gl.enableVertexAttribArray(lk); gl.vertexAttribPointer(lk, 3, gl.FLOAT, false, 20, 8);
  gl.clearColor(0.2, 0.5, 0.8, 1.0); gl.clear(gl.COLOR_BUFFER_BIT);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
  const p1 = new Uint8Array(64 * 64 * 4);
  gl.readPixels(0, 0, 64, 64, gl.RGBA, gl.UNSIGNED_BYTE, p1);
  const p2 = new Uint8Array(64 * 64 * 4);
  gl.readPixels(0, 0, 64, 64, gl.RGBA, gl.UNSIGNED_BYTE, p2);
  return { r1: H(p1), r2: H(p2) };
}"""

# A DEDICATED worker: draws a gradient plus an arc on an OffscreenCanvas the
# worker owns (no text, so the text offset is not what is measured), reads it
# back via getImageData, and returns two hashes. The worker runs on its own
# thread and derives the seed from the process-inherited CAMOU_CONFIG
# (Section 4.4), so a difference from a live unconfigured worker run proves
# the noise reaches worker readback.
WORKER_READBACK = """() => new Promise((resolve, reject) => {
  const src = `
    self.onmessage = () => {
      const c = new OffscreenCanvas(300, 200);
      const ctx = c.getContext('2d');
      const g = ctx.createLinearGradient(0, 0, 300, 200);
      g.addColorStop(0, '#ff2d00'); g.addColorStop(0.5, '#00c853');
      g.addColorStop(1, '#1a2fff');
      ctx.fillStyle = g; ctx.fillRect(0, 0, 300, 200);
      ctx.fillStyle = 'rgba(255,255,255,0.6)'; ctx.beginPath();
      ctx.arc(150, 100, 55, 0, Math.PI * 2); ctx.fill();
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

# S1: flat drawings -- one colour, a hard edge, a 1px line, a WebGL clear (the
# old C6 drawing, so its unconfigured hash is the baseline's readPixels), and a
# worker OffscreenCanvas fill. Noise must leave each as unconfigured reads it.
FLAT = "() => new Promise((resolve, reject) => {" + HASH_FN + """
  const distinct = (d) => { const s = new Set();
    for (let i = 0; i < d.length; i += 4) s.add(d[i] + ',' + d[i+1] + ',' + d[i+2] + ',' + d[i+3]);
    return s.size; };
  const mk = () => { const c = document.createElement('canvas');
    c.width = 64; c.height = 64; return c.getContext('2d'); };
  // A corner arc makes the canvas eligible; only 0..48 is read, away from it.
  const arc = (c) => { c.fillStyle = '#f60'; c.beginPath(); c.arc(58, 58, 4, 0, 7); c.fill(); };
  const out = {};
  let x = mk(); x.fillStyle = 'rgb(10,20,30)'; x.fillRect(0, 0, 64, 64);
  arc(x);
  const d = x.getImageData(0, 0, 48, 48).data; out.solid = H(d); out.solidColours = distinct(d);
  x = mk(); x.fillStyle = 'rgb(10,20,30)'; x.fillRect(0, 0, 64, 64);
  x.fillStyle = 'rgb(200,100,50)'; x.fillRect(0, 0, 32, 64);
  arc(x);
  out.edge = H(x.getImageData(0, 0, 48, 48).data);
  x = mk(); x.strokeStyle = 'rgb(200,100,50)'; x.lineWidth = 1;
  x.beginPath(); x.moveTo(0, 10.5); x.lineTo(64, 10.5); x.stroke();
  arc(x);
  out.line = H(x.getImageData(0, 0, 48, 48).data);
  x = mk(); x.fillStyle = 'rgb(10,20,30)'; x.fillRect(0, 0, 64, 64);
  x.fillStyle = '#f60'; x.beginPath(); x.arc(58, 58, 4, 0, 7); x.fill();
  out.solidEligible = H(x.getImageData(0, 0, 32, 32).data);
  const g = document.createElement('canvas'); g.width = 64; g.height = 64;
  const gl = g.getContext('webgl');
  if (gl) {
    gl.clearColor(0.2, 0.5, 0.8, 1.0); gl.clear(gl.COLOR_BUFFER_BIT);
    const p = new Uint8Array(64 * 64 * 4);
    gl.readPixels(0, 0, 64, 64, gl.RGBA, gl.UNSIGNED_BYTE, p);
    out.glClear = H(p); out.glClearColours = distinct(p);
  } else { out.glClear = 'no-webgl'; }
  const src = `self.onmessage = () => {
    const H = (d) => { let h = 5381 >>> 0;
      for (let i = 0; i < d.length; i++) h = (((h << 5) + h) ^ d[i]) >>> 0;
      return h; };
    const arc = (c) => { c.fillStyle = '#f60'; c.beginPath(); c.arc(58, 58, 4, 0, 7); c.fill(); };
    let x = new OffscreenCanvas(64, 64).getContext('2d');
    x.fillStyle = 'rgb(10,20,30)'; x.fillRect(0, 0, 64, 64);
    arc(x);
    const solid = H(x.getImageData(0, 0, 48, 48).data);
    x = new OffscreenCanvas(64, 64).getContext('2d');
    x.fillStyle = 'rgb(10,20,30)'; x.fillRect(0, 0, 64, 64);
    x.fillStyle = 'rgb(200,100,50)'; x.fillRect(0, 0, 32, 64);
    arc(x);
    self.postMessage({ solid, edge: H(x.getImageData(0, 0, 48, 48).data) }); };`;
  try {
    const w = new Worker(URL.createObjectURL(new Blob([src], { type: 'text/javascript' })));
    w.onmessage = (e) => { out.worker = e.data; resolve(out); };
    w.onerror = (e) => reject(new Error(e.message || 'worker error'));
    w.postMessage('go');
  } catch (e) { reject(e); }
})"""

# putImageData of a random opaque pattern over text, read straight back. Stock
# returns the bytes unchanged; readback noise would not.
ROUNDTRIP = """() => {
  const c = document.createElement('canvas'); c.width = 64; c.height = 64;
  const x = c.getContext('2d');
  x.fillStyle = '#f60'; x.beginPath(); x.arc(32, 32, 10, 0, 7); x.fill();
  x.font = '22px sans-serif'; x.fillText('Camoucrome', 2, 40);
  const img = x.createImageData(64, 64); let s = 12345;
  for (let i = 0; i < img.data.length; i += 4) {
    for (let k = 0; k < 3; k++) {
      s = (Math.imul(s, 1103515245) + 12345) >>> 0; img.data[i + k] = s >>> 24; }
    img.data[i + 3] = 255;
  }
  x.putImageData(img, 0, 0);
  const back = x.getImageData(0, 0, 64, 64).data;
  for (let i = 0; i < back.length; i++)
    if (back[i] !== img.data[i]) return { exact: false, first: i };
  return { exact: true };
}"""

# SCENE_2D copied at a 1px offset through drawImage and through
# createImageBitmap; both copies must read what getImageData of the original
# reads. The offset matters: an unshifted copy has the original's state hash
# and would get the same field by accident.
COPY = "() => new Promise((resolve, reject) => { try {" + SCENE_2D + HASH_FN + """
  const a = H(ctx.getImageData(0, 0, 300, 200).data);
  const shifted = (src) => { const b = document.createElement('canvas');
    b.width = 301; b.height = 200; const bx = b.getContext('2d');
    bx.fillStyle = '#f60'; bx.beginPath(); bx.arc(150, 100, 30, 0, 7); bx.fill();
    bx.drawImage(src, 1, 0); return H(bx.getImageData(1, 0, 300, 200).data); };
  const viaDraw = shifted(c);
  createImageBitmap(c).then((bm) => resolve({ a, viaDraw, viaBitmap: shifted(bm) }), reject);
} catch (e) { reject(e); } })"""

# The host oracle's canvas step (capture_host_oracle.py), verbatim: the text
# canvas and the shape canvas, hashed from toDataURL. S2: per seed they must
# differ from stock and from each other.
ORACLE_CANVAS = """() => {
  const fnv = (s) => { let h = 2166136261;
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; }
    return h.toString(16); };
  const c = document.createElement('canvas'); c.width = 220; c.height = 40;
  const x = c.getContext('2d');
  x.font = '16px Arial'; x.fillText('Cwm fjordbank glyphs vext quiz 1234', 4, 26);
  x.font = '16px "Segoe UI"'; x.fillText('Cwm fjordbank glyphs vext quiz', 4, 38);
  const text = fnv(c.toDataURL());
  x.clearRect(0, 0, 220, 40);
  x.fillStyle = '#f60'; x.beginPath(); x.arc(50, 20, 15, 0, 7); x.fill();
  x.fillStyle = 'rgba(0,80,255,.5)'; x.fillRect(40, 10, 60, 20);
  return { text, shape: fnv(c.toDataURL()) };
}"""


# C17-C19: the C6 gradient triangle read back at other pack layouts. __GL__ is
# the context type, __W__ x __H__ the canvas, __BODY__ the reads.
TRI = """() => {
  const c = document.createElement('canvas'); c.width = __W__; c.height = __H__;
  const gl = c.getContext('__GL__');
  if (!gl) return { err: 'no-__GL__' };
  const sh = (type, src) => { const s = gl.createShader(type);
    gl.shaderSource(s, src); gl.compileShader(s); return s; };
  const pr = gl.createProgram();
  gl.attachShader(pr, sh(gl.VERTEX_SHADER,
    'attribute vec2 p;attribute vec3 k;varying vec3 v;void main(){v=k;gl_Position=vec4(p,0,1);}'));
  gl.attachShader(pr, sh(gl.FRAGMENT_SHADER,
    'precision mediump float;varying vec3 v;void main(){gl_FragColor=vec4(v,1);}'));
  gl.linkProgram(pr); gl.useProgram(pr);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(
    [-0.9, -0.8, 1, 0, 0,  0.85, -0.6, 0, 1, 0,  -0.1, 0.9, 0, 0, 1]), gl.STATIC_DRAW);
  const lp = gl.getAttribLocation(pr, 'p'), lk = gl.getAttribLocation(pr, 'k');
  gl.enableVertexAttribArray(lp); gl.vertexAttribPointer(lp, 2, gl.FLOAT, false, 20, 0);
  gl.enableVertexAttribArray(lk); gl.vertexAttribPointer(lk, 3, gl.FLOAT, false, 20, 8);
  gl.clearColor(0.2, 0.5, 0.8, 1.0); gl.clear(gl.COLOR_BUFFER_BIT);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
  __HASH__
  const RGBA = gl.RGBA, UB = gl.UNSIGNED_BYTE;
  __BODY__
}"""


def tri(gl, w, h, body):
    return (TRI.replace("__GL__", gl).replace("__W__", str(w))
            .replace("__H__", str(h)).replace("__HASH__", HASH_FN)
            .replace("__BODY__", body))


# 63x64: a row is 252 bytes, so the default read (alignment 4) is tight and
# the alignment-8 read pads each row to 256.
ALIGN8 = tri("webgl", 63, 64, """
  const A = new Uint8Array(63 * 64 * 4); gl.readPixels(0, 0, 63, 64, RGBA, UB, A);
  gl.pixelStorei(gl.PACK_ALIGNMENT, 8);
  const B = new Uint8Array(63 * 256 + 252).fill(0xAB);
  gl.readPixels(0, 0, 63, 64, RGBA, UB, B);
  let pix = 0, pad = 0;
  for (let y = 0; y < 64; y++) {
    for (let i = 0; i < 252; i++) if (B[y * 256 + i] !== A[y * 252 + i]) pix++;
    if (y < 63) for (let i = 252; i < 256; i++) if (B[y * 256 + i] !== 0xAB) pad++;
  }
  return { pix, pad, h: H(A) };""")

# WebGL2: ROW_LENGTH 80, SKIP_PIXELS 3, SKIP_ROWS 2 into a 64x64 read.
LAYOUT = tri("webgl2", 64, 64, """
  const A = new Uint8Array(64 * 64 * 4); gl.readPixels(0, 0, 64, 64, RGBA, UB, A);
  gl.pixelStorei(gl.PACK_ROW_LENGTH, 80);
  gl.pixelStorei(gl.PACK_SKIP_PIXELS, 3);
  gl.pixelStorei(gl.PACK_SKIP_ROWS, 2);
  const off = 2 * 320 + 3 * 4;
  const B = new Uint8Array(off + 63 * 320 + 64 * 4).fill(0xAB);
  gl.readPixels(0, 0, 64, 64, RGBA, UB, B);
  let inside = 0, outside = 0;
  const used = new Uint8Array(B.length);
  for (let y = 0; y < 64; y++) for (let i = 0; i < 256; i++) {
    const o = off + y * 320 + i; used[o] = 1;
    if (B[o] !== A[y * 256 + i]) inside++; }
  for (let o = 0; o < B.length; o++) if (!used[o] && B[o] !== 0xAB) outside++;
  return { inside, outside, h: H(A) };""")

# A rect reaching 8 px past the buffer on two sides: hash of its in-buffer part.
PAST = tri("webgl", 64, 64, """
  const A = new Uint8Array(64 * 64 * 4); gl.readPixels(0, 0, 64, 64, RGBA, UB, A);
  const B = new Uint8Array(72 * 72 * 4).fill(0xAB);
  gl.readPixels(-8, -8, 72, 72, RGBA, UB, B);
  const part = new Uint8Array(64 * 64 * 4), rest = [];
  for (let y = 0; y < 72; y++) for (let x = 0; x < 72; x++) {
    const o = (y * 72 + x) * 4;
    if (x >= 8 && y >= 8) for (let k = 0; k < 4; k++) part[((y - 8) * 64 + x - 8) * 4 + k] = B[o + k];
    else for (let k = 0; k < 4; k++) rest.push(B[o + k]);
  }
  let eqA = true; for (let i = 0; i < A.length; i++) if (A[i] !== part[i]) { eqA = false; break; }
  return { h: H(part), eqA, rest: H(rest) };""")

# A layout GL rejects (SKIP_PIXELS 1 + width 64 > row 64): nothing may be written.
REJECT = tri("webgl2", 64, 64, """
  const buf = new Uint8Array(64 * 64 * 4);
  for (let y = 0; y < 64; y++) for (let x = 0; x < 64; x++) {
    const v = ((x + y) & 1) ? 200 : 60, i = (y * 64 + x) * 4;
    buf[i] = v; buf[i + 1] = 255 - v; buf[i + 2] = v >> 1; buf[i + 3] = 255; }
  const pre = buf.slice();
  gl.getError();
  gl.pixelStorei(gl.PACK_SKIP_PIXELS, 1);
  gl.readPixels(0, 0, 64, 64, RGBA, UB, buf);
  const err = gl.getError(); let changed = 0;
  for (let i = 0; i < buf.length; i++) if (buf[i] !== pre[i]) changed++;
  return { glerr: err, invalid: gl.INVALID_OPERATION, changed };""")

# C28: a sub-rect read equals the matching part of a full read, byte for byte.
SUBRECT = tri("webgl", 64, 64, """
  const A = new Uint8Array(64 * 64 * 4); gl.readPixels(0, 0, 64, 64, RGBA, UB, A);
  const B = new Uint8Array(32 * 32 * 4); gl.readPixels(16, 16, 32, 32, RGBA, UB, B);
  let diff = 0;
  for (let y = 0; y < 32; y++) for (let i = 0; i < 128; i++)
    if (B[y * 128 + i] !== A[(y + 16) * 256 + 64 + i]) diff++;
  return { diff, h: H(B) };""")

# C29: toDataURL of the WebGL canvas, decoded through a 2D canvas (whose
# drawImage marks it imported, so it adds no noise), equals readPixels
# flipped to top-down, on every opaque pixel.
AGREE = tri("webgl", 64, 64, """
  const R = new Uint8Array(64 * 64 * 4); gl.readPixels(0, 0, 64, 64, RGBA, UB, R);
  const url = c.toDataURL('image/png');
  return (async () => {
    const im = new Image(); im.src = url; await im.decode();
    const d2 = document.createElement('canvas'); d2.width = 64; d2.height = 64;
    const x2 = d2.getContext('2d'); x2.drawImage(im, 0, 0);
    const D = x2.getImageData(0, 0, 64, 64).data;
    let diff = 0, opaque = 0;
    for (let y = 0; y < 64; y++) for (let i = 0; i < 64; i++) {
      const r = ((63 - y) * 64 + i) * 4, o = (y * 64 + i) * 4;
      if (R[r + 3] !== 255) continue;
      opaque++;
      for (let k = 0; k < 4; k++) if (D[o + k] !== R[r + k]) { diff++; break; }
    }
    return { diff, opaque, h: H(R) };
  })();""")

# C15: text under ctx.scale(40,40); the ink bounding box's min x / min y.
SCALED_TEXT = """() => {
  const c = document.createElement('canvas'); c.width = 300; c.height = 300;
  const x = c.getContext('2d');
  x.scale(40, 40); x.font = '4px sans-serif'; x.fillText('H', 1, 5);
  const d = x.getImageData(0, 0, 300, 300).data;
  let minx = -1, miny = -1;
  for (let y = 0; y < 300; y++) for (let i = 0; i < 300; i++)
    if (d[(y * 300 + i) * 4 + 3] > 0) {
      if (minx < 0 || i < minx) minx = i;
      if (miny < 0) miny = y;
    }
  return { minx, miny };
}"""

# C16: a decoded image (of a putImageData random pattern) drawn over an arc.
DECODED_IMAGE = "async () => {" + HASH_FN + """
  const src = document.createElement('canvas'); src.width = 64; src.height = 64;
  const sx = src.getContext('2d');
  const img = sx.createImageData(64, 64); let s = 12345;
  for (let i = 0; i < img.data.length; i += 4) {
    for (let k = 0; k < 3; k++) {
      s = (Math.imul(s, 1103515245) + 12345) >>> 0; img.data[i + k] = s >>> 24; }
    img.data[i + 3] = 255;
  }
  sx.putImageData(img, 0, 0);
  const im = new Image(); im.src = src.toDataURL('image/png'); await im.decode();
  const c = document.createElement('canvas'); c.width = 64; c.height = 64;
  const x = c.getContext('2d');
  x.fillStyle = '#f60'; x.beginPath(); x.arc(32, 32, 10, 0, 7); x.fill();
  x.drawImage(im, 0, 0);
  return H(x.getImageData(0, 0, 64, 64).data);
}"""

# S2b rows C21-C27: one page, every 2D drawing on its own canvas. `elig`
# counts interior, non-transparent pixels unlike all four neighbours -- the
# vacuity guard: a drawing with none of them cannot show noise.
ELIG_FN = """
  const elig = (d, w, x0 = 1, y0 = 1, x1 = w - 1, y1 = d.length / 4 / w - 1) => {
    const hgt = d.length / 4 / w;
    const same = (a, b) => d[a] === d[b] && d[a + 1] === d[b + 1]
      && d[a + 2] === d[b + 2] && d[a + 3] === d[b + 3];
    let n = 0;
    for (let y = Math.max(y0, 1); y < Math.min(y1, hgt - 1); y++)
      for (let x = Math.max(x0, 1); x < Math.min(x1, w - 1); x++) {
        const i = (y * w + x) * 4;
        if (d[i + 3] && !same(i, i - 4) && !same(i, i + 4)
            && !same(i, i - w * 4) && !same(i, i + w * 4)) n++;
      }
    return n; };
"""

# C35-C37: reads from a page framebuffer. FBO_FN renders the C6 gradient
# triangle into a 64x64 RGBA8 texture framebuffer (no multisampling) and leaves
# it bound.
FBO_FN = """
  const fbo = (w, h) => { const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texImage2D(gl.TEXTURE_2D, 0, RGBA, w, h, 0, RGBA, UB, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    const f = gl.createFramebuffer(); gl.bindFramebuffer(gl.FRAMEBUFFER, f);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0);
    gl.viewport(0, 0, w, h); gl.clearColor(0.2, 0.5, 0.8, 1.0);
    gl.clear(gl.COLOR_BUFFER_BIT); gl.drawArrays(gl.TRIANGLES, 0, 3); return f; };
"""

# C53: LAYOUT's reads, from a page framebuffer (an RGBA8 texture).
LAYOUT_FBO = tri("webgl2", 64, 64, FBO_FN + """
  fbo(64, 64);""" + LAYOUT[LAYOUT.index("const A = new Uint8Array(64 * 64 * 4)"):LAYOUT.rindex('return { inside, outside, h: H(A) };')]
  + "return { inside, outside, h: H(A) };")

# C35: a framebuffer read is noised and deterministic.
FBOREAD = tri("webgl", 64, 64, FBO_FN + ELIG_FN + """
  fbo(64, 64);
  const A = new Uint8Array(64 * 64 * 4); gl.readPixels(0, 0, 64, 64, RGBA, UB, A);
  const B = new Uint8Array(64 * 64 * 4); gl.readPixels(0, 0, 64, 64, RGBA, UB, B);
  let same = true; for (let i = 0; i < A.length; i++) if (A[i] !== B[i]) { same = false; break; }
  return { h: H(A), same, e: elig(A, 64) };""")

# C36: a framebuffer sub-rect read equals the matching part of a full read.
FBOSUB = tri("webgl", 64, 64, FBO_FN + """
  fbo(64, 64);
  const A = new Uint8Array(64 * 64 * 4); gl.readPixels(0, 0, 64, 64, RGBA, UB, A);
  const B = new Uint8Array(32 * 32 * 4); gl.readPixels(16, 16, 32, 32, RGBA, UB, B);
  let diff = 0;
  for (let y = 0; y < 32; y++) for (let i = 0; i < 128; i++)
    if (B[y * 128 + i] !== A[(y + 16) * 256 + 64 + i]) diff++;
  return { diff, h: H(B) };""")

# C49: a 520x520 sub-rect of a 1024x1024 read: its rect plus margin (522^2)
# is above the one-piece size, so its neighbours come from the margin strips.
# Every edge of the rect crosses the triangle's gradient.
STRIPS = tri("webgl", 1024, 1024, FBO_FN + """
  const run = () => {
    const A = new Uint8Array(1024 * 1024 * 4); gl.readPixels(0, 0, 1024, 1024, RGBA, UB, A);
    const B = new Uint8Array(520 * 520 * 4); gl.readPixels(200, 200, 520, 520, RGBA, UB, B);
    let diff = 0;
    for (let y = 0; y < 520; y++) for (let i = 0; i < 2080; i++)
      if (B[y * 2080 + i] !== A[(y + 200) * 4096 + 800 + i]) diff++;
    return [diff, H(B)]; };
  const d = run(); fbo(1024, 1024); const f = run();
  return { diff: [d[0], f[0]], h: [d[1], f[1]], glerr: gl.getError() };""")

# C50: the same reads into a SharedArrayBuffer view and a plain one: a
# padded full read (PACK_ALIGNMENT 8, odd width) and a sub-rect with margins.
SHARED = tri("webgl", 63, 64, """
  if (typeof SharedArrayBuffer !== 'function') return { err: 'no-sharedarraybuffer' };
  const sab = (n) => new Uint8Array(new SharedArrayBuffer(n));
  gl.pixelStorei(gl.PACK_ALIGNMENT, 8);
  const n = 63 * 256 + 252;
  const P = new Uint8Array(n).fill(0xAB), S = sab(n).fill(0xAB);
  gl.readPixels(0, 0, 63, 64, RGBA, UB, P); gl.readPixels(0, 0, 63, 64, RGBA, UB, S);
  gl.pixelStorei(gl.PACK_ALIGNMENT, 4);
  const P2 = new Uint8Array(32 * 32 * 4), S2 = sab(32 * 32 * 4);
  gl.readPixels(16, 16, 32, 32, RGBA, UB, P2); gl.readPixels(16, 16, 32, 32, RGBA, UB, S2);
  let diff = 0, pad = 0;
  for (let i = 0; i < n; i++) if (P[i] !== S[i]) diff++;
  for (let i = 0; i < P2.length; i++) if (P2[i] !== S2[i]) diff++;
  for (let y = 0; y < 63; y++) for (let i = 252; i < 256; i++) if (S[y * 256 + i] !== 0xAB) pad++;
  return { diff, pad, h: H(new Uint8Array(S2)), glerr: gl.getError() };""")

# C36b: framebuffer reads whose margin or rect crosses the far edge, and one
# with a negative origin: each in-framebuffer part equals the full read's.
FBOEDGE = tri("webgl", 64, 64, FBO_FN + """
  fbo(64, 64);
  const A = new Uint8Array(64 * 64 * 4); gl.readPixels(0, 0, 64, 64, RGBA, UB, A);
  const part = (x, y, w, h) => { const B = new Uint8Array(w * h * 4);
    gl.readPixels(x, y, w, h, RGBA, UB, B); let diff = 0; const inb = [];
    for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) {
      const fx = x + i, fy = y + j;
      if (fx < 0 || fy < 0 || fx >= 64 || fy >= 64) continue;
      for (let k = 0; k < 4; k++) { const b = B[(j * w + i) * 4 + k]; inb.push(b);
        if (b !== A[(fy * 64 + fx) * 4 + k]) diff++; } }
    return { diff, h: H(inb) }; };
  const r = [part(16, 16, 48, 48), part(24, 24, 48, 48), part(-4, -4, 20, 20)];
  return { diff: r.map(v => v.diff), h: r.map(v => v.h), glerr: gl.getError() };""")

# C46: WebGL2 R8 and RG8 texture framebuffers with the C6 scene, read
# RGBA / UNSIGNED_BYTE: stock returns G = B = 0 (R8) and B = 0 (RG8), which a
# noised read would break. The RGBA8 read of the same scene is the guard: it
# must be noised.
FBOFMT = tri("webgl2", 64, 64, ELIG_FN + """
  const read = (ifmt, fmt) => { const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texImage2D(gl.TEXTURE_2D, 0, ifmt, 64, 64, 0, fmt, UB, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    const f = gl.createFramebuffer(); gl.bindFramebuffer(gl.FRAMEBUFFER, f);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0);
    if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE) return null;
    gl.viewport(0, 0, 64, 64); gl.clearColor(0.2, 0.5, 0.8, 1.0);
    gl.clear(gl.COLOR_BUFFER_BIT); gl.drawArrays(gl.TRIANGLES, 0, 3);
    const A = new Uint8Array(64 * 64 * 4); gl.readPixels(0, 0, 64, 64, RGBA, UB, A);
    return A; };
  gl.getError();
  const r8 = read(gl.R8, gl.RED), rg8 = read(gl.RG8, gl.RG), rgba8 = read(gl.RGBA8, RGBA);
  if (!r8 || !rg8 || !rgba8) return { err: 'fbo-incomplete' };
  let stray = 0;
  for (let i = 0; i < r8.length; i += 4) {
    if (r8[i + 1] || r8[i + 2]) stray++;
    if (rg8[i + 2]) stray++; }
  return { r8: H(r8), rg8: H(rg8), rgba8: H(rgba8), stray, glerr: gl.getError(),
           e8: elig(r8, 64), eg: elig(rg8, 64) };""")

# C46b: a WebGL1 RGBA4 renderbuffer framebuffer with the C6 scene reads as
# stock (a +-1 would leave the 4-bit lattice); the RGBA8 texture framebuffer
# of the same scene is the guard.
FBORGBA4 = tri("webgl", 64, 64, FBO_FN + ELIG_FN + """
  gl.getError();
  const rb = gl.createRenderbuffer(); gl.bindRenderbuffer(gl.RENDERBUFFER, rb);
  gl.renderbufferStorage(gl.RENDERBUFFER, gl.RGBA4, 64, 64);
  const f = gl.createFramebuffer(); gl.bindFramebuffer(gl.FRAMEBUFFER, f);
  gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.RENDERBUFFER, rb);
  if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE)
    return { err: 'fbo-incomplete' };
  gl.viewport(0, 0, 64, 64); gl.clearColor(0.2, 0.5, 0.8, 1.0);
  gl.clear(gl.COLOR_BUFFER_BIT); gl.drawArrays(gl.TRIANGLES, 0, 3);
  const A = new Uint8Array(64 * 64 * 4); gl.readPixels(0, 0, 64, 64, RGBA, UB, A);
  fbo(64, 64);
  const B = new Uint8Array(64 * 64 * 4); gl.readPixels(0, 0, 64, 64, RGBA, UB, B);
  return { h: H(A), g: H(B), e: elig(A, 64), glerr: gl.getError() };""")

# C47: a drawingBufferStorage(SRGB8_ALPHA8) default framebuffer (8-bit, read
# as RGBA / UNSIGNED_BYTE) with the C6 scene is noised and deterministic.
SRGBREAD = tri("webgl2", 64, 64, ELIG_FN + """
  if (!gl.drawingBufferStorage) return { err: 'no-drawingBufferStorage' };
  gl.getError();
  gl.drawingBufferStorage(gl.SRGB8_ALPHA8, 64, 64);
  if (gl.getError() !== 0) return { err: 'drawingBufferStorage-rejected' };
  gl.viewport(0, 0, 64, 64); gl.clearColor(0.2, 0.5, 0.8, 1.0);
  gl.clear(gl.COLOR_BUFFER_BIT); gl.drawArrays(gl.TRIANGLES, 0, 3);
  const A = new Uint8Array(64 * 64 * 4); gl.readPixels(0, 0, 64, 64, RGBA, UB, A);
  const B = new Uint8Array(64 * 64 * 4); gl.readPixels(0, 0, 64, 64, RGBA, UB, B);
  let same = true; for (let i = 0; i < A.length; i++) if (A[i] !== B[i]) { same = false; break; }
  return { h: H(A), same, e: elig(A, 64), glerr: gl.getError() };""")

# C37: random 1px texels uploaded into a framebuffer's texture: the left half
# translucent (alpha 1..254), the right half opaque. Translucent texels read
# back exact; at least one opaque texel changes under a seed.
FBOTRANS = tri("webgl", 64, 64, """
  const src = new Uint8Array(64 * 64 * 4); let s = 99;
  for (let y = 0; y < 64; y++) for (let x = 0; x < 64; x++) {
    const i = (y * 64 + x) * 4;
    for (let k = 0; k < 3; k++) { s = (Math.imul(s, 1103515245) + 12345) >>> 0; src[i + k] = s >>> 24; }
    s = (Math.imul(s, 1103515245) + 12345) >>> 0;
    src[i + 3] = x < 32 ? 1 + ((s >>> 24) % 254) : 255;
    if (src[i + 3] < 255) for (let k = 0; k < 3; k++) src[i + k] = Math.min(src[i + k], src[i + 3]); }
  const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
  gl.texImage2D(gl.TEXTURE_2D, 0, RGBA, 64, 64, 0, RGBA, UB, src);
  const f = gl.createFramebuffer(); gl.bindFramebuffer(gl.FRAMEBUFFER, f);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0);
  const A = new Uint8Array(64 * 64 * 4); gl.readPixels(0, 0, 64, 64, RGBA, UB, A);
  let trans = 0, transDiff = 0, opaqueDiff = 0;
  for (let i = 0; i < A.length; i += 4) {
    let d = false; for (let k = 0; k < 4; k++) if (A[i + k] !== src[i + k]) d = true;
    if (src[i + 3] < 255) { trans++; if (d) transDiff++; } else if (d) opaqueDiff++; }
  // The right half's framebuffer edge (x = 63, and rows 0 and 63 for x >= 32)
  // is opaque random texels: never noised, since the framebuffer edge has no
  // neighbour there (a misread extent would noise it).
  let edgeDiff = 0;
  for (let y = 0; y < 64; y++) for (let x = 32; x < 64; x++) {
    if (x !== 63 && y !== 0 && y !== 63) continue;
    const i = (y * 64 + x) * 4;
    for (let k = 0; k < 4; k++) if (A[i + k] !== src[i + k]) { edgeDiff++; break; } }
  return { trans, transDiff, opaqueDiff, edgeDiff, h: H(A) };""")

# C41: WebGL2 without antialiasing, the default framebuffer bound, READ_BUFFER
# NONE: stock rejects readPixels and leaves the destination untouched. The
# noise must not write (or read back) anything either, for a sub-rect and a
# full read.
_RUN = """  const run = (x, y, w, h) => {
    // Sentinel: opaque pixels (a translucent one is never noised, so it
    // could not show an in-place noise pass).
    // Random texels: noise only touches pixels that differ from a neighbour.
    const b = new Uint8Array(w * h * 4); let r = 7;
    for (let i = 0; i < b.length; i++) {
      r = (Math.imul(r, 1103515245) + 12345) >>> 0; b[i] = i % 4 === 3 ? 0xFF : r >>> 24; }
    const s = b.slice();
    gl.readPixels(x, y, w, h, gl.RGBA, gl.UNSIGNED_BYTE, b);
    const e = gl.getError(); let n = 0;
    for (let i = 0; i < b.length; i++) if (b[i] !== s[i]) n++;
    return { e, n }; };
"""
READNONE = ("""() => {
  const c = document.createElement('canvas'); c.width = 64; c.height = 64;
  const gl = c.getContext('webgl2', { antialias: false });
  if (!gl) return { err: 'no-webgl2' };
  gl.clearColor(0.2, 0.5, 0.8, 1.0); gl.clear(gl.COLOR_BUFFER_BIT);
  gl.readBuffer(gl.NONE); gl.getError();
""" + _RUN + """
  return { sub: run(1, 1, 8, 8), full: run(0, 0, 64, 64) }; }""")

# C42: the same reads from a default framebuffer whose storage is RGBA16F
# (drawingBufferStorage, WebGL2): GL rejects RGBA / UNSIGNED_BYTE, so stock
# leaves the destination alone and the noise must too. A missing API or
# extension is an error row, not a pass.
READ16F = ("""() => {
  const c = document.createElement('canvas'); c.width = 64; c.height = 64;
  const gl = c.getContext('webgl2', { antialias: false });
  if (!gl) return { err: 'no-webgl2' };
  if (!gl.drawingBufferStorage) return { err: 'no-drawingBufferStorage' };
  if (!gl.getExtension('EXT_color_buffer_float') &&
      !gl.getExtension('EXT_color_buffer_half_float')) return { err: 'no-float-buffer' };
  gl.drawingBufferStorage(gl.RGBA16F, 64, 64);
  if (gl.getError() !== 0) return { err: 'drawingBufferStorage-rejected' };
  gl.clearColor(0.2, 0.5, 0.8, 1.0); gl.clear(gl.COLOR_BUFFER_BIT); gl.getError();
""" + _RUN + """
  return { sub: run(1, 1, 8, 8), full: run(0, 0, 64, 64) }; }""")


# C38: texImage2D of the WebGL canvas into a second context (flipped to GL
# orientation), read through that context's framebuffer: equals the source's
# own readPixels (noised once, not twice), and is noised.
TEXIMAGE = tri("webgl", 64, 64, """
  const R = new Uint8Array(64 * 64 * 4); gl.readPixels(0, 0, 64, 64, RGBA, UB, R);
  const c2 = document.createElement('canvas'); c2.width = 64; c2.height = 64;
  const g2 = c2.getContext('webgl'); if (!g2) return { err: 'no-webgl-second' };
  const t = g2.createTexture(); g2.bindTexture(g2.TEXTURE_2D, t);
  g2.pixelStorei(g2.UNPACK_FLIP_Y_WEBGL, true);
  g2.texImage2D(g2.TEXTURE_2D, 0, g2.RGBA, g2.RGBA, g2.UNSIGNED_BYTE, c);
  const f = g2.createFramebuffer(); g2.bindFramebuffer(g2.FRAMEBUFFER, f);
  g2.framebufferTexture2D(g2.FRAMEBUFFER, g2.COLOR_ATTACHMENT0, g2.TEXTURE_2D, t, 0);
  const B = new Uint8Array(64 * 64 * 4); g2.readPixels(0, 0, 64, 64, g2.RGBA, g2.UNSIGNED_BYTE, B);
  let eq = true; for (let i = 0; i < R.length; i++) if (R[i] !== B[i]) { eq = false; break; }
  return { eq, h: H(B) };""")


# C48: an arc's region read (A), then a globalAlpha 0 drawImage of an SVG
# image over the whole region, read again (B). An SVG draws as a saveLayer at
# the draw's alpha around a nested record, unlike C43's canvas source.
SVG_ALPHA0 = "async () => {" + HASH_FN + ELIG_FN + """
  const c = document.createElement('canvas'); c.width = 64; c.height = 64;
  const x = c.getContext('2d');
  x.fillStyle = '#f60'; x.beginPath(); x.arc(32, 32, 12, 0, 7); x.fill();
  const im = new Image();
  im.src = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg"'
    + ' width="33" height="33"><rect width="33" height="33" fill="#0a0"/></svg>');
  await im.decode();
  const a = x.getImageData(16, 16, 33, 33).data;
  x.globalAlpha = 0; x.drawImage(im, 16, 16); x.globalAlpha = 1;
  return { a: H(a), b: H(x.getImageData(16, 16, 33, 33).data), e: elig(a, 33) };
}"""

# C52: AA strokes over the whole canvas, read (A); then a url() filter whose
# last primitive is an feDropShadow (sRGB, so no colour-space wrapper) over
# an feFlood, applied to a fully transparent fillRect, read again (B). The
# filter paints the flood and its blurred shadow from nothing (the shadow's
# own subregion is the whole canvas: by default it would be the flood's, and
# the flood would hide it). Both reads are
# returned whole; the row compares seeded and unconfigured B on the pixels
# the filter changed in the unconfigured run.
FLOOD_SHADOW = "() => {" + """
  document.body.insertAdjacentHTML('beforeend',
    '<svg width="0" height="0" style="position:absolute"><filter id="camouflood"'
    + ' filterUnits="userSpaceOnUse" x="0" y="0" width="64" height="64">'
    + '<feFlood flood-color="#3a7" x="20" y="18" width="19" height="17"/>'
    + '<feDropShadow x="0" y="0" width="64" height="64" dx="3" dy="2"'
    + ' stdDeviation="2.5" flood-color="#000" color-interpolation-filters="sRGB"/>'
    + '</filter></svg>');
  const c = document.createElement('canvas'); c.width = 64; c.height = 64;
  document.body.appendChild(c);
  const x = c.getContext('2d');
  x.strokeStyle = '#f60'; x.lineWidth = 1.3;
  for (let r = 2.3; r < 44; r += 2.7) { x.beginPath(); x.arc(31.6, 30.4, r, 0, 7); x.stroke(); }
  const a = x.getImageData(0, 0, 64, 64).data;
  x.filter = 'url(#camouflood)'; x.fillStyle = 'rgba(0,0,0,0)'; x.fillRect(0, 0, 64, 64);
  x.filter = 'none';
  const b = x.getImageData(0, 0, 64, 64).data;
  return { a: Array.from(a), b: Array.from(b) };
}"""

S2B_2D = "() => {" + HASH_FN + ELIG_FN + """
  const mk = (w, h) => { const c = document.createElement('canvas');
    c.width = w; c.height = h; return c.getContext('2d'); };
  const arc = (x, cx, cy, r, col) => { x.fillStyle = col || '#f60'; x.beginPath();
    x.arc(cx, cy, r, 0, 7); x.fill(); };
  const rnd = (x, w, h) => { const img = x.createImageData(w, h); let s = 12345;
    for (let i = 0; i < img.data.length; i += 4) {
      for (let k = 0; k < 3; k++) {
        s = (Math.imul(s, 1103515245) + 12345) >>> 0; img.data[i + k] = s >>> 24; }
      img.data[i + 3] = 255; }
    return img; };
  const get = (x, l, t, w, h) => x.getImageData(l, t, w, h).data;
  const out = {};
  // C21: one arc at two whole-pixel offsets, (20,20) and (84,36).
  let x = mk(128, 64); arc(x, 20, 20, 10); arc(x, 84, 36, 10);
  let a = get(x, 8, 8, 25, 25);
  out.pos = { ha: H(a), hb: H(get(x, 72, 24, 25, 25)), e: elig(a, 25) };
  // C22: read region A, draw far from it, read A again.
  x = mk(128, 64); arc(x, 20, 20, 10);
  a = get(x, 8, 8, 25, 25); const r1 = H(a);
  arc(x, 100, 40, 10, '#06f');
  out.edit = { r1, r2: H(get(x, 8, 8, 25, 25)), e: elig(a, 25) };
  // C23: an arc, plus a putImageData pattern elsewhere.
  x = mk(128, 64); arc(x, 20, 20, 10);
  const img = rnd(x, 32, 32); x.putImageData(img, 80, 16);
  a = get(x, 8, 8, 25, 25); const back = get(x, 80, 16, 32, 32);
  let exact = true;
  for (let i = 0; i < back.length; i++) if (back[i] !== img.data[i]) { exact = false; break; }
  out.mixed = { arc: H(a), exact, e: elig(a, 25) };
  // C24: operations the old anti-aliasing list missed.
  const hole = (draw) => { const y = mk(64, 64); draw(y); const d = get(y, 0, 0, 64, 64);
    return { h: H(d), e: elig(d, 64) }; };
  out.holes = {
    a: hole((y) => { y.fillStyle = '#f60'; y.beginPath(); y.moveTo(5, 5); y.lineTo(58, 12);
      y.lineTo(20, 58); y.closePath(); y.fill(); }),
    b: hole((y) => { y.strokeStyle = '#06f'; y.lineWidth = 6; y.lineCap = 'round';
      y.beginPath(); y.moveTo(10, 32); y.lineTo(54, 32); y.stroke(); }),
    c: hole((y) => { y.beginPath(); y.arc(32, 32, 20, 0, 7); y.clip();
      y.fillStyle = '#0a6'; y.fillRect(0, 0, 64, 64); }),
    d: hole((y) => { y.shadowBlur = 4; y.shadowColor = 'rgba(0,0,0,0.8)';
      y.fillStyle = '#c33'; y.fillRect(16, 16, 32, 32); }),
  };
  // C25: a reused canvas reads like a fresh one.
  x = mk(64, 64); x.putImageData(rnd(x, 64, 64), 0, 0); x.clearRect(0, 0, 64, 64);
  arc(x, 32, 32, 12); const h1 = H(get(x, 0, 0, 64, 64));
  x = mk(64, 64); arc(x, 32, 32, 12); a = get(x, 0, 0, 64, 64);
  out.reuse = { h1, h2: H(a), e: elig(a, 64) };
  // C26: createPattern alone marks nothing; a pattern fill marks its area only.
  const tile = mk(8, 8); tile.putImageData(rnd(tile, 8, 8), 0, 0);
  x = mk(64, 64); x.createPattern(tile.canvas, 'repeat'); arc(x, 32, 32, 12);
  a = get(x, 0, 0, 64, 64); const p1 = H(a);
  x = mk(64, 64); arc(x, 16, 16, 10); x.fillStyle = x.createPattern(tile.canvas, 'repeat');
  x.fillRect(32, 32, 32, 32);
  out.pattern = { p1, e: elig(a, 64), hB: H(get(x, 32, 32, 32, 32)) };
  // C27: 1px random opaque colours (every 3x3 patch distinct, so noise cannot
  // miss by a coin flip), a diagonal line across them, an arc in a corner.
  // Pixels 4+ px from the line must stay exact.
  x = mk(64, 64); let cs = 54321;
  for (let yy = 0; yy < 40; yy++) for (let xx = 0; xx < 40; xx++) {
    const c3 = [0, 0, 0].map(() => { cs = (Math.imul(cs, 1103515245) + 12345) >>> 0; return cs >>> 24; });
    x.fillStyle = `rgb(${c3[0]},${c3[1]},${c3[2]})`; x.fillRect(xx, yy, 1, 1); }
  x.strokeStyle = '#000'; x.lineWidth = 1;
  x.beginPath(); x.moveTo(0, 0); x.lineTo(40, 40); x.stroke();
  arc(x, 56, 56, 5);
  const d = get(x, 0, 0, 64, 64), sel = [];
  for (let yy = 1; yy < 39; yy++) for (let xx = 1; xx < 39; xx++)
    if (Math.abs(xx - yy) >= 4) for (let k = 0; k < 4; k++) sel.push(d[(yy * 64 + xx) * 4 + k]);
  out.cover = { h: H(sel), e: elig(d, 64, 1, 1, 39, 39) };
  // C30-C32: draws that leave pixels exact must not leave stale aa marks:
  // translucent 1px random colours over a wiped canvas read like a fresh one.
  const speckle = (y) => { let ss = 777;
    y.globalCompositeOperation = 'source-over'; y.globalAlpha = 0.5;
    for (let yy = 0; yy < 40; yy++) for (let xx = 0; xx < 40; xx++) {
      const col = [];
      for (let k = 0; k < 3; k++) {
        ss = (Math.imul(ss, 1103515245) + 12345) >>> 0; col.push(ss >>> 24); }
      y.fillStyle = 'rgb(' + col.join(',') + ')'; y.fillRect(xx, yy, 1, 1); }
    y.globalAlpha = 1; };
  const grad = (y) => { const g = y.createLinearGradient(0, 0, 64, 64);
    g.addColorStop(0, '#ff2d00'); g.addColorStop(1, '#1a2fff');
    y.fillStyle = g; y.fillRect(0, 0, 64, 64); };
  const fresh = (pre) => { const y = mk(64, 64); if (pre) pre(y); speckle(y);
    return get(y, 0, 0, 64, 64); };
  const freshH = H(fresh(null)), freshE = elig(fresh(null), 64, 1, 1, 39, 39);
  // C30: destination-out with an opaque fill wipes the gradient.
  x = mk(64, 64); grad(x);
  x.globalCompositeOperation = 'destination-out'; x.fillStyle = '#000';
  x.fillRect(0, 0, 64, 64); speckle(x);
  out.dstout = { h: H(get(x, 0, 0, 64, 64)), fresh: freshH, e: freshE };
  // C31: transferToImageBitmap hands the bitmap over; the canvas restarts clear.
  const oc = new OffscreenCanvas(64, 64), ox = oc.getContext('2d');
  grad(ox); oc.transferToImageBitmap(); speckle(ox);
  out.transfer = { h: H(ox.getImageData(0, 0, 64, 64).data), fresh: freshH, e: freshE };
  // C32: 'copy' replaces the whole clip with an opaque fill.
  x = mk(64, 64); grad(x);
  x.globalCompositeOperation = 'copy'; x.fillStyle = '#123456'; x.fillRect(0, 0, 64, 64);
  speckle(x);
  const solid = (y) => { y.fillStyle = '#123456'; y.fillRect(0, 0, 64, 64); };
  out.copy = { h: H(get(x, 0, 0, 64, 64)), fresh: H(fresh(solid)),
    e: elig(fresh(solid), 64, 1, 1, 39, 39) };
  // C34: 'copy' with a STROKE wipes the whole clip too; stale marks inside it
  // must go (a stroke-styled clear would clear only the clip's outline).
  x = mk(64, 64); grad(x);
  x.globalCompositeOperation = 'copy'; x.strokeStyle = '#123456'; x.lineWidth = 2;
  x.strokeRect(20, 20, 10, 10); speckle(x);
  const ring = (y) => { y.strokeStyle = '#123456'; y.lineWidth = 2; y.strokeRect(20, 20, 10, 10); };
  out.copystroke = { h: H(get(x, 0, 0, 64, 64)), fresh: H(fresh(ring)),
    e: elig(fresh(ring), 64, 1, 1, 39, 39) };
  // C33: exact pixels stay exact through draws that change none of them:
  // 64x64 opaque random 1px colours, then (a) a fully transparent arc, (b) an
  // arc filled with an all-transparent gradient, (c) an opaque fill whose
  // shadow lands off the canvas, then a translucent speckle, (d) a blurred
  // fillRect in a corner. The whole canvas must equal unconfigured.
  const exactDraw = (draw) => { const y = mk(64, 64); let es = 4242;
    for (let yy = 0; yy < 64; yy++) for (let xx = 0; xx < 64; xx++) {
      const col = [];
      for (let k = 0; k < 3; k++) {
        es = (Math.imul(es, 1103515245) + 12345) >>> 0; col.push(es >>> 24); }
      y.fillStyle = 'rgb(' + col.join(',') + ')'; y.fillRect(xx, yy, 1, 1); }
    const pre = H(get(y, 0, 0, 64, 64));
    draw(y); const d = get(y, 0, 0, 64, 64);
    return { h: H(d), e: elig(d, 64), pre }; };
  out.exact = {
    a: exactDraw((y) => { y.fillStyle = 'rgba(0,0,0,0)'; y.beginPath();
      y.arc(32, 32, 20, 0, 7); y.fill(); }),
    b: exactDraw((y) => { const g = y.createLinearGradient(0, 0, 64, 64);
      g.addColorStop(0, 'rgba(255,0,0,0)'); g.addColorStop(1, 'rgba(0,0,255,0)');
      y.fillStyle = g; y.beginPath(); y.arc(32, 32, 20, 0, 7); y.fill(); }),
    c: exactDraw((y) => { y.shadowColor = '#000'; y.shadowOffsetX = 1000;
      y.fillStyle = '#123456'; y.fillRect(0, 0, 64, 64);
      y.shadowColor = 'rgba(0,0,0,0)'; y.shadowOffsetX = 0; speckle(y); }),
    d: exactDraw((y) => { y.filter = 'blur(1px)'; y.fillStyle = '#123456';
      y.fillRect(56, 56, 8, 8); y.filter = 'none'; }),
    e: exactDraw((y) => { y.shadowColor = '#000'; y.shadowOffsetX = 3;
      y.shadowOffsetY = 3; y.fillStyle = 'rgba(0,0,0,0)'; y.beginPath();
      y.arc(32, 32, 20, 0, 7); y.fill();
      y.shadowColor = 'rgba(0,0,0,0)'; y.shadowOffsetX = 0; y.shadowOffsetY = 0; }),
  };
  // C39: getImageData of a sub-rect equals the whole-snapshot field, on opaque
  // and translucent anti-aliased content: against a full read, and against a
  // drawImage copy (marked imported, so it carries the snapshot's noise once).
  x = mk(64, 64); arc(x, 24, 24, 16, 'rgba(255,96,0,0.6)'); arc(x, 40, 40, 16, '#06f');
  // The sub-rect is read first: a whole-canvas read fills the noise cache, and a
  // read after it would be served from the cache, not the regional path.
  const sub = get(x, 10, 12, 40, 36), full = get(x, 0, 0, 64, 64);
  const cpy = mk(64, 64); cpy.drawImage(x.canvas, 0, 0); const cp = get(cpy, 10, 12, 40, 36);
  let dF = 0, dC = 0, trans = 0; const tv = [];
  for (let yy = 0; yy < 36; yy++) for (let xx = 0; xx < 40; xx++) {
    const o = (yy * 40 + xx) * 4, f = ((yy + 12) * 64 + xx + 10) * 4;
    for (let k = 0; k < 4; k++) { if (sub[o + k] !== full[f + k]) dF++; if (sub[o + k] !== cp[o + k]) dC++; }
    if (sub[o + 3] > 0 && sub[o + 3] < 255) { trans++; for (let k = 0; k < 4; k++) tv.push(sub[o + k]); } }
  out.region = { dF, dC, trans, tH: H(tv), e: elig(full, 64) };
  // C40: the same twelve arcs, flushed after every draw (1x1 getImageData)
  // or only at the end, give one final read.
  const seq = (flushEach) => { const y = mk(64, 64);
    for (let i = 0; i < 12; i++) { arc(y, 8 + i * 4, 10 + (i * 7) % 40, 6, i & 1 ? '#f60' : '#06f');
      if (flushEach) get(y, 0, 0, 1, 1); }
    return get(y, 0, 0, 64, 64); };
  const m2 = seq(false);
  out.flushes = { h1: H(seq(true)), h2: H(m2), e: elig(m2, 64) };
  // C43: an arc's region read (A), then a globalAlpha 0 drawImage over the
  // whole region, read again (B): a draw that changes no pixel changes no
  // noise. (Over only part of the edge, at density 0.04, no noised pixel
  // may fall under the image, and the row passes on the faulty build.)
  x = mk(64, 64); arc(x, 32, 32, 12);
  const src = mk(33, 33); src.fillStyle = '#0a0'; src.fillRect(0, 0, 33, 33);
  a = get(x, 16, 16, 33, 33);
  x.globalAlpha = 0; x.drawImage(src.canvas, 16, 16); x.globalAlpha = 1;
  out.alpha0 = { a: H(a), b: H(get(x, 16, 16, 33, 33)), e: elig(a, 33) };
  // C44: an arc at (50,50) read (A), then a shadowed 10x10 drawImage at
  // (150,150), read again (B): the shadow marks its own pixels, not the clip.
  x = mk(200, 200); arc(x, 50, 50, 12);
  const tile10 = mk(10, 10); tile10.fillStyle = '#0a0'; tile10.fillRect(0, 0, 10, 10);
  a = get(x, 34, 34, 33, 33);
  x.shadowBlur = 2; x.shadowOffsetX = 3; x.shadowOffsetY = 3;
  x.shadowColor = 'rgba(0,0,0,0.5)'; x.drawImage(tile10.canvas, 150, 150);
  out.shadowimg = { a: H(a), b: H(get(x, 34, 34, 33, 33)), e: elig(a, 33) };
  // C44b: the same with an opaque source canvas: an opaque image's shadow is
  // a looper on the image's own flags, not a filtered layer.
  x = mk(200, 200); arc(x, 50, 50, 12);
  const opq = document.createElement('canvas'); opq.width = 10; opq.height = 10;
  const opqx = opq.getContext('2d', { alpha: false });
  opqx.fillStyle = '#0a0'; opqx.fillRect(0, 0, 10, 10);
  a = get(x, 34, 34, 33, 33);
  x.shadowBlur = 2; x.shadowOffsetX = 3; x.shadowOffsetY = 3;
  x.shadowColor = 'rgba(0,0,0,0.5)'; x.drawImage(opq, 150, 150);
  out.shadowopq = { a: H(a), b: H(get(x, 34, 34, 33, 33)), e: elig(a, 33) };
  // C45: rects that leave the canvas: the regional read must place the region
  // at the clipped origin. Each rect is checked against the full read (zero
  // outside the canvas) and against the same rect of a drawImage copy.
  x = mk(64, 64); arc(x, 24, 24, 16, 'rgba(255,96,0,0.6)'); arc(x, 40, 40, 16, '#06f');
  arc(x, 62, 62, 12, '#0a0');
  // The rects are read before the full read and the copy, which fill the cache.
  const rects = [[-5, -7, 30, 30], [50, 50, 30, 30], [40, 40, -30, -30], [63, 63, 1, 1]];
  const rs = rects.map(([sx, sy, sw, sh]) => get(x, sx, sy, sw, sh));
  const full2 = get(x, 0, 0, 64, 64);
  const cpy2 = mk(64, 64); cpy2.drawImage(x.canvas, 0, 0);
  let dF2 = 0, dC2 = 0, cnt = 0;
  for (const [n, [sx, sy, sw, sh]] of rects.entries()) {
    const r = rs[n], c = get(cpy2, sx, sy, sw, sh);
    const nx = sw < 0 ? sx + sw : sx, ny = sh < 0 ? sy + sh : sy;
    const w = Math.abs(sw), h = Math.abs(sh);
    for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) {
      const X = nx + i, Y = ny + j, o = (j * w + i) * 4;
      const inside = X >= 0 && X < 64 && Y >= 0 && Y < 64;
      for (let k = 0; k < 4; k++) {
        const f = inside ? full2[(Y * 64 + X) * 4 + k] : 0;
        if (r[o + k] !== f) dF2++;
        if (r[o + k] !== c[o + k]) dC2++;
        cnt++; } } }
  out.edgeRects = { dF: dF2, dC: dC2, cnt, tH: H(full2), e: elig(full2, 64) };
  // C51: an arc's region read (A), then a globalAlpha 0 drawImage of a
  // translucent canvas with a shadow set over the whole region, read again
  // (B): the draw opens a drop-shadow layer around an op that paints nothing.
  x = mk(64, 64); arc(x, 32, 32, 12);
  const tr = mk(33, 33); tr.fillStyle = 'rgba(0,160,0,0.5)'; tr.fillRect(0, 0, 33, 33);
  a = get(x, 16, 16, 33, 33);
  x.shadowBlur = 4; x.shadowColor = 'black'; x.globalAlpha = 0;
  x.drawImage(tr.canvas, 16, 16);
  x.globalAlpha = 1; x.shadowBlur = 0; x.shadowColor = 'rgba(0,0,0,0)';
  out.shadowalpha0 = { a: H(a), b: H(get(x, 16, 16, 33, 33)), e: elig(a, 33) };
  return out;
}"""


def session(config, fn, extra_flags=None, screenshot=False, gate=False):
    """One content_shell session. Runs page-function `fn` (a JS string) after
    navigating to about:blank, or captures a CDP screenshot if `screenshot`.
    Returns (value, err); any fault becomes a FAIL, never a traceback."""
    proc = conn = None
    if extra_flags is None and GPU_CANVAS:
        extra_flags = GL_FLAGS
    try:
        proc, conn = lib_shell.launch_and_prime(
            lambda: lib_shell.launch(config, extra_flags=extra_flags),
            lambda p: lib_shell.attach(p, lambda page: page.goto("about:blank", wait_until="load")))
        page = conn.page
        if screenshot:
            # Draw the scene into the visible document, then screenshot via
            # the DevTools protocol -- NOT a canvas readback API.
            page.evaluate(f"() => {{ {SCENE_NO_TEXT} document.body.appendChild(c); }}")
            cdp = conn.context.new_cdp_session(page)
            shot = cdp.send("Page.captureScreenshot", {"format": "png"})
            return shot["data"], None
        value = page.evaluate(fn)
        if gate:    # a host GPU run: the GPU process must not have crashed during the launch (else UNMEASURED)
            import gpu_gate
            n = gpu_gate.read_ctx(conn.context)
            if n != 0:
                return None, gpu_gate.GpuCrashed(n)
        return value, None
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc
    finally:
        if conn is not None:
            conn.close()
        if proc is not None:
            lib_shell.shutdown(proc)


def sha(s):
    if not isinstance(s, str):
        s = json.dumps(s)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


capture = "--capture-baseline" in sys.argv[1:]
results = {}
notes = []

# --- Which canvas this launch gives a page ---
# Readback noise is put on GPU-rastered pixels only (release -5, rule B). Where the default 2D canvas is a CPU canvas
# (content_shell without ANGLE/SwiftShader, a machine without GPU raster) the noise rows have nothing to measure: the
# valid modes are CAMOU_SP3A_GPU_CANVAS=1 on the build box and a GPU host (default launch). CAMOU_SP3A_ALLOW_CPU_DEFAULT=1
# runs the rows anyway (a RED run on an older binary, whose seeded canvases were noised everywhere).
CPU_PROBE = """async () => {
  const W = 200, H = 100;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}"><rect width="200" height="100" fill="#fff"/>` +
              `<circle cx="100" cy="50" r="38.3" fill="rgb(128,128,128)"/></svg>`;
  const im = new Image(); await new Promise((res, rej) => { im.onload = res; im.onerror = rej;
    im.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg); });
  const ref = document.createElement('canvas'); ref.width = W; ref.height = H;
  const xr = ref.getContext('2d', { willReadFrequently: true }); xr.drawImage(im, 0, 0);
  const c = document.createElement('canvas'); c.width = W; c.height = H;
  const x = c.getContext('2d'); x.fillStyle = '#fff'; x.fillRect(0, 0, W, H); x.fillStyle = 'rgb(128,128,128)';
  x.beginPath(); x.arc(100, 50, 38.3, 0, Math.PI * 2); x.fill();
  const a = x.getImageData(0, 0, W, H).data, b = xr.getImageData(0, 0, W, H).data;
  let d = 0; for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) d++;
  return { diff: d };
}"""
_probe, _probe_err = session(None, f"() => ({CPU_PROBE})()")
if _probe is None:
    print(f"UNMEASURED: the canvas probe session failed ({_probe_err}): the mode of this launch is unknown")
    sys.exit(3)
if not _probe["diff"] and os.environ.get("CAMOU_SP3A_ALLOW_CPU_DEFAULT") != "1":
    print("UNMEASURED: the default 2D canvas of this launch is a CPU canvas (it reads exact against the SVG shapes): the "
          "noise rows have nothing to measure. Run with CAMOU_SP3A_GPU_CANVAS=1 (build box) or on a GPU host.")
    sys.exit(3)

# --- Live runs on the binary under test ---
seeded, seeded_err = session(CANVAS, DRAW_AND_READ)
unconf, unconf_err = session(None, DRAW_AND_READ)
seeded_gl, seeded_gl_err = session(CANVAS, DRAW_AND_READ_GL, extra_flags=GL_FLAGS)
unconf_gl, unconf_gl_err = session(None, DRAW_AND_READ_GL, extra_flags=GL_FLAGS)
seeded_w, seeded_w_err = session(CANVAS, WORKER_READBACK)
seeded_shot, seeded_shot_err = session(CANVAS, None, screenshot=True)
unconf_shot, unconf_shot_err = session(None, None, screenshot=True)
native, native_err = session(CANVAS, NATIVE_PROBE)
# chrome has window.chrome and content_shell does not, so a content_shell baseline cannot hold a chrome window-key
# hash (224 vs 223 keys). Row 10 then compares the config arm with the no-config arm of the same binary: it is
# config vs no-config, not vs stock.
CHROME_RUN = os.environ.get("CAMOU_SHELL") == "chrome"
native_noconf, native_noconf_err = session(None, NATIVE_PROBE) if CHROME_RUN else (None, None)

# --- OffscreenCanvas.convertToBlob (main thread) for C7 ---
CONVERT_TO_BLOB = f"""() => new Promise((resolve, reject) => {{
  try {{
    const oc = new OffscreenCanvas(300, 200);
    const ctx = oc.getContext('2d');
    const g = ctx.createLinearGradient(0, 0, 300, 200);
    g.addColorStop(0, '#ff2d00'); g.addColorStop(0.5, '#00c853');
    g.addColorStop(1, '#1a2fff');
    ctx.fillStyle = g; ctx.fillRect(0, 0, 300, 200);
    ctx.fillStyle = 'rgba(255,255,255,0.6)'; ctx.beginPath();
    ctx.arc(150, 100, 55, 0, Math.PI * 2); ctx.fill();
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
unconf_oc, unconf_oc_err = session(None, CONVERT_TO_BLOB)
unconf_w, unconf_w_err = session(None, WORKER_READBACK)
seeded_flat, seeded_flat_err = session(CANVAS, FLAT, extra_flags=GL_FLAGS)
unconf_flat, unconf_flat_err = session(None, FLAT, extra_flags=GL_FLAGS)
seeded_rt, seeded_rt_err = session(CANVAS, ROUNDTRIP)
seeded_copy, seeded_copy_err = session(CANVAS, COPY)
unconf_scaled, unconf_scaled_err = session(None, SCALED_TEXT)
seeds_scaled = [session(json.dumps({"canvas:seed": s}), SCALED_TEXT)
                for s in (987654321, 1, 2, 3)]
unconf_dec, unconf_dec_err = session(None, DECODED_IMAGE)
gl17 = {k: (session(CANVAS, js, extra_flags=GL_FLAGS), session(None, js, extra_flags=GL_FLAGS))
        for k, js in (("align", ALIGN8), ("layout", LAYOUT), ("past", PAST),
                           ("reject", REJECT), ("subrect", SUBRECT), ("agree", AGREE),
                           ("fbo", FBOREAD), ("fbosub", FBOSUB), ("fbotrans", FBOTRANS),
                           ("teximage", TEXIMAGE), ("readnone", READNONE), ("read16f", READ16F),
                           ("fboedge", FBOEDGE), ("fbofmt", FBOFMT), ("fborgba4", FBORGBA4),
                           ("srgb", SRGBREAD), ("strips", STRIPS),
                           ("layoutfbo", LAYOUT_FBO))}
SAB_FLAGS = GL_FLAGS + ["--enable-features=SharedArrayBuffer"]
gl17["shared"] = (session(CANVAS, SHARED, extra_flags=SAB_FLAGS),
                  session(None, SHARED, extra_flags=SAB_FLAGS))
seeded_dec, seeded_dec_err = session(CANVAS, DECODED_IMAGE)
oracle_stock, oracle_stock_err = session(None, ORACLE_CANVAS)
oracle_seeded = [session(json.dumps({"canvas:seed": s}), ORACLE_CANVAS) for s in range(1, 9)]
s2b_seeded, s2b_seeded_err = session(CANVAS, S2B_2D)
s2b_unconf, s2b_unconf_err = session(None, S2B_2D)
svg_runs = (session(CANVAS, SVG_ALPHA0), session(None, SVG_ALPHA0))
flood_runs = (session(CANVAS, FLOOD_SHADOW), session(None, FLOOD_SHADOW))

if capture:
    if unconf is None or unconf_gl is None or unconf_shot is None:
        notes.append("capture: a stock session failed; baseline incomplete")
    b = {}
    if unconf is not None:
        b["toDataURL"] = sha(unconf["d1"])
        b["toBlob"] = sha(unconf["b1"])
        b["getImageData"] = unconf["gi1"]
    # readPixels is the FLAT run's plain clear (the old baseline drawing), not
    # the gradient triangle C6 draws now.
    if unconf_flat is not None and isinstance(unconf_flat.get("glClear"), int):
        b["readPixels"] = unconf_flat["glClear"]
    else:
        notes.append("capture: no WebGL clear; baseline readPixels missing")
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
C6 = "6  seeded readPixels of a gradient triangle deterministic, differs from unconfigured"
C7 = "7  seeded OffscreenCanvas.convertToBlob deterministic, differs from unconfigured"
C8 = "8  worker OffscreenCanvas readback deterministic, differs from unconfigured (parity)"
C9 = "9  DevTools screenshot of a text-free scene identical seeded vs unconfigured"
C10 = ("10 accessors native + window keys equal the no-config arm (config vs no-config, not vs stock)"
       if CHROME_RUN else "10 accessors native + window keys unchanged")

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
if seeded_gl is None or unconf_gl is None:
    results[C6] = False
    if seeded_gl_err:
        notes.append(f"C6: {type(seeded_gl_err).__name__}: {seeded_gl_err}")
elif "err" in seeded_gl or "err" in unconf_gl:
    results[C6] = False
    notes.append("C6: WebGL unavailable in content_shell even under SwiftShader "
                 "-- not a pass; investigate the GL context (do not fake-pass)")
else:
    # The drawing is no longer the baseline's clear, so "differs" compares with
    # the unconfigured live run; C11 keeps the WebGL rule-5 baseline check.
    determ = seeded_gl["r1"] == seeded_gl["r2"]
    differs = seeded_gl["r1"] != unconf_gl["r1"]
    results[C6] = determ and differs
    if not results[C6]:
        notes.append(f"C6: determ={determ} differs={differs}")

# C7 convertToBlob
if seeded_oc is None or unconf_oc is None:
    results[C7] = False
    notes.append(f"C7: {seeded_oc_err or unconf_oc_err}")
else:
    results[C7] = (seeded_oc["o1"] == seeded_oc["o2"]
                   and seeded_oc["o1"] != unconf_oc["o1"])
    if not results[C7]:
        notes.append("C7: convertToBlob not deterministic or equals unconfigured")

# C8 worker parity
if seeded_w is None or unconf_w is None:
    results[C8] = False
    notes.append(f"C8: {seeded_w_err or unconf_w_err}")
else:
    results[C8] = (seeded_w["w1"] == seeded_w["w2"]
                   and seeded_w["w1"] != unconf_w["w1"])
    if not results[C8]:
        notes.append("C8: worker readback not deterministic or equals unconfigured -- "
                     "noise did not reach the worker thread")

# C9 screen unchanged
if seeded_shot is None or unconf_shot is None:
    results[C9] = False
    if seeded_shot_err:
        notes.append(f"C9: {type(seeded_shot_err).__name__}: {seeded_shot_err}")
else:
    results[C9] = sha(seeded_shot) == sha(unconf_shot)
    if not results[C9]:
        notes.append("C9: seeded screenshot differs from stock -- noise leaked "
                     "to draw time / composited output")

# C10 native accessors
c10_ref = native_noconf["winkeys"] if CHROME_RUN and native_noconf is not None else (
    None if CHROME_RUN else bl("winkeys"))
if native is None or c10_ref is None or (not CHROME_RUN and baseline is None):
    results[C10] = False
    if native_err:
        notes.append(f"C10: {type(native_err).__name__}: {native_err}")
    if native_noconf_err:
        notes.append(f"C10: no-config arm {type(native_noconf_err).__name__}: {native_noconf_err}")
else:
    all_native = (native["toDataURL"] and native["getImageData"]
                  and native["readPixels"])
    keys_same = native["winkeys"] == c10_ref
    results[C10] = all_native and keys_same
    if not results[C10]:
        notes.append(f"C10: native={all_native} winkeys_same={keys_same}")

C11 = "11 flat drawings read as unconfigured (solid, edge, 1px line, WebGL clear, worker)"
C12 = "12 putImageData round trip exact"
C13 = "13 drawImage and createImageBitmap copies agree with getImageData"
C15 = "15 text under ctx.scale(40,40) lands within 1 device px of unconfigured"
C16 = "16 decoded image drawn on an eligible canvas reads as unconfigured"
C17 = "17 readPixels at PACK_ALIGNMENT 8, odd width, agrees with the default layout"
C18 = "18 WebGL2 PACK_ROW_LENGTH/SKIP_PIXELS/SKIP_ROWS read agrees with the default read"
C19 = "19 readPixels rect past the buffer: in-buffer part equals the default read, not unconfigured"
C20 = "20 readPixels rejected by GL leaves the buffer untouched"
C14 = "14 oracle shape canvases vary over 8 seeds, none stock; the text canvas is stock for every seed"

# C11 flat drawings (S1)
if seeded_flat is None or unconf_flat is None:
    results[C11] = False
    notes.append(f"C11: {seeded_flat_err or unconf_flat_err}")
else:
    differ = sorted(k for k in unconf_flat if seeded_flat.get(k) != unconf_flat[k])
    colours = (seeded_flat.get("solidColours"), seeded_flat.get("glClearColours"))
    gl_stock = bool(baseline) and unconf_flat.get("glClear") == bl("readPixels")
    results[C11] = not differ and colours == (1, 1) and gl_stock
    if not results[C11]:
        notes.append(f"C11: differ from unconfigured {differ}, colours (2D, WebGL) "
                     f"{colours}, unconfigured clear == stock baseline {gl_stock}")

# C12 putImageData round trip
results[C12] = bool(seeded_rt and seeded_rt.get("exact"))
if not results[C12]:
    notes.append(f"C12: {seeded_rt or seeded_rt_err}")

# C13 copy paths
results[C13] = bool(seeded_copy
                    and seeded_copy["a"] == seeded_copy["viaDraw"] == seeded_copy["viaBitmap"])
if not results[C13]:
    notes.append(f"C13: {seeded_copy or seeded_copy_err}")

# C14 S2: per-seed variation of the oracle's canvases
errs = [str(e) for _, e in oracle_seeded if e] + ([str(oracle_stock_err)] if oracle_stock_err else [])
if errs:
    results[C14] = False
    notes.append(f"C14: {errs[0]}")
else:
    texts = {v["text"] for v, _ in oracle_seeded}
    shapes = {v["shape"] for v, _ in oracle_seeded}
    # Canvas text carries no noise and no origin shift since release -5 (canvas audit N2: stock rasters canvas text and SVG
    # text identically, so any shift is a tell): the text canvas is the unconfigured one for every seed.
    results[C14] = (texts == {oracle_stock["text"]}
                    and len(shapes) == 8 and oracle_stock["shape"] not in shapes)
    if not results[C14]:
        notes.append(f"C14: text {len(texts)} distinct, stock among them "
                     f"{oracle_stock['text'] in texts}; shape {len(shapes)} distinct, "
                     f"stock among them {oracle_stock['shape'] in shapes}")

# C15 text offset in device space
sc = [v for v, _ in seeds_scaled]
if unconf_scaled is None or None in sc:
    results[C15] = False
    notes.append(f"C15: {unconf_scaled_err or [e for _, e in seeds_scaled if e]}")
elif unconf_scaled["minx"] < 0:
    results[C15] = False
    notes.append("C15: vacuous -- the unconfigured run drew no ink")
else:
    deltas = [(v["minx"] - unconf_scaled["minx"], v["miny"] - unconf_scaled["miny"])
              for v in sc]
    results[C15] = all(abs(dx) <= 1 and abs(dy) <= 1 for dx, dy in deltas)
    if not results[C15]:
        notes.append(f"C15: (dx, dy) per seed {deltas}; unconfigured bbox "
                     f"({unconf_scaled['minx']}, {unconf_scaled['miny']})")

# C16 decoded image
if seeded_dec is None or unconf_dec is None:
    results[C16] = False
    notes.append(f"C16: {seeded_dec_err or unconf_dec_err}")
else:
    results[C16] = seeded_dec == unconf_dec
    if not results[C16]:
        notes.append(f"C16: seeded {seeded_dec} != unconfigured {unconf_dec}")

# C17-C19: other pack layouts must carry the same field and leave padding alone.
def gl_row(name, key, ok_fn):
    (seeded_v, seeded_e), (unconf_v, unconf_e) = gl17[key]
    if seeded_v is None or unconf_v is None:
        results[name] = False
        notes.append(f"{name[:3]}: {seeded_e or unconf_e}")
    elif "err" in seeded_v or "err" in unconf_v:
        results[name] = False
        notes.append(f"{name[:3]}: {seeded_v.get('err') or unconf_v.get('err')} -- "
                     "context unavailable under SwiftShader, not a pass")
    else:
        results[name] = ok_fn(seeded_v, unconf_v)
        if not results[name]:
            notes.append(f"{name[:3]}: seeded {seeded_v}, unconfigured {unconf_v}")


gl_row(C17, "align", lambda s, u: s["pix"] == 0 and s["pad"] == 0 and s["h"] != u["h"])
gl_row(C18, "layout", lambda s, u: s["inside"] == 0 and s["outside"] == 0 and s["h"] != u["h"])
gl_row(C19, "past", lambda s, u: s["eqA"] and s["h"] != u["h"] and s["rest"] == u["rest"])
gl_row(C20, "reject", lambda s, u: all(v["glerr"] == v["invalid"] and v["changed"] == 0
                                       for v in (s, u)))

C21 = "21 one arc at two whole-pixel offsets gets the same noise"
C22 = "22 a draw elsewhere does not change a region's noise"
C23 = "23 arc plus putImageData elsewhere: arc noised, pattern exact"
C24 = {k: f"24{k} {what} carries noise" for k, what in (
    ("a", "diagonal lineTo triangle"), ("b", "round-cap stroke"),
    ("c", "curved clip() + fillRect"), ("d", "fillRect with shadowBlur"))}
C25 = "25 a reused canvas reads like a fresh one"
C26 = "26 createPattern alone marks nothing; a pattern fill reads exact"
C27 = "27 1px random colours under a diagonal line stay exact (coverage, not bbox)"
C28 = "28 WebGL readPixels sub-rect equals the full read's part, byte for byte"
C29 = "29 WebGL toDataURL agrees with readPixels on every opaque pixel"


def s2b_row(name, get, guard, ok, runs=None):
    """One S2b 2D row: FAIL with a note on a session fault or a vacuous drawing.
    `runs` is ((seeded, err), (unconfigured, err)), S2B_2D's by default."""
    (sv, se), (uv, ue) = runs or ((s2b_seeded, s2b_seeded_err),
                                  (s2b_unconf, s2b_unconf_err))
    if sv is None or uv is None:
        results[name] = False
        notes.append(f"{name[:3]}: {se or ue}")
        return
    s, u = get(sv), get(uv)
    if not guard(u):
        results[name] = False
        notes.append(f"{name[:3]}: vacuous -- unconfigured drawing {u}")
        return
    results[name] = ok(s, u)
    if not results[name]:
        notes.append(f"{name[:3]}: seeded {s}, unconfigured {u}")


s2b_row(C21, lambda r: r["pos"], lambda u: u["e"] > 0 and u["ha"] == u["hb"],
        lambda s, u: s["ha"] == s["hb"] and s["ha"] != u["ha"])
s2b_row(C22, lambda r: r["edit"], lambda u: u["e"] > 0,
        lambda s, u: s["r1"] == s["r2"] and s["r1"] != u["r1"])
s2b_row(C23, lambda r: r["mixed"], lambda u: u["e"] > 0 and u["exact"],
        lambda s, u: s["arc"] != u["arc"] and s["exact"])
for k in "abcd":
    s2b_row(C24[k], lambda r, k=k: r["holes"][k], lambda u: u["e"] > 0,
            lambda s, u: s["h"] != u["h"])
s2b_row(C25, lambda r: r["reuse"], lambda u: u["e"] > 0 and u["h1"] == u["h2"],
        lambda s, u: s["h1"] == s["h2"] and s["h2"] != u["h2"])
s2b_row(C26, lambda r: r["pattern"], lambda u: u["e"] > 0,
        lambda s, u: s["p1"] != u["p1"] and s["hB"] == u["hB"])
s2b_row(C27, lambda r: r["cover"], lambda u: u["e"] > 0,
        lambda s, u: s["h"] == u["h"])
gl_row(C28, "subrect", lambda s, u: s["diff"] == 0 and u["diff"] == 0 and s["h"] != u["h"])
gl_row(C29, "agree", lambda s, u: s["opaque"] > 0 and s["diff"] == 0 and u["diff"] == 0
       and s["h"] != u["h"])
C30 = "30 destination-out wipe then translucent speckle reads like a fresh canvas"
C31 = "31 transferToImageBitmap then translucent speckle reads like a fresh canvas"
C32 = "32 copy fill then translucent speckle reads like a fresh canvas"
for name, key in ((C30, "dstout"), (C31, "transfer"), (C32, "copy")):
    s2b_row(name, lambda r, key=key: r[key],
            lambda u: u["e"] > 0 and u["h"] == u["fresh"],
            lambda s, u: s["h"] == s["fresh"])

C33 = {k: f"33{k} exact pixels stay exact after {what}" for k, what in (
    ("a", "a fully transparent arc"),
    ("b", "an all-transparent gradient arc"),
    ("c", "an opaque fill with an off-canvas shadow, then a speckle"),
    ("d", "a blurred corner fillRect"),
    ("e", "a transparent arc with a visible shadow"))}
for k in "abcd":
    s2b_row(C33[k], lambda r, k=k: r["exact"][k], lambda u: u["e"] > 0,
            lambda s, u: s["h"] == u["h"])
# (e): stock draws nothing, so the canvas must still equal its pre-draw state.
s2b_row(C33["e"], lambda r: r["exact"]["e"],
        lambda u: u["e"] > 0 and u["pre"] == u["h"],
        lambda s, u: s["h"] == u["h"])

C34 = "34 copy stroke then translucent speckle reads like a fresh canvas"
s2b_row(C34, lambda r: r["copystroke"],
        lambda u: u["e"] > 0 and u["h"] == u["fresh"],
        lambda s, u: s["h"] == s["fresh"])

C35 = "35 framebuffer readPixels of a gradient triangle noised and deterministic"
C36 = "36 framebuffer readPixels sub-rect equals the full framebuffer read's part"
C37 = "37 framebuffer read leaves translucent pixels exact, changes an opaque one"
C38 = "38 texImage2D(webgl canvas) read in a second context equals the source's read"
C39 = "39 getImageData sub-rect equals the whole-snapshot field (full read and copy)"
C40 = "40 one flush or many give one mask"
C41 = "41 READ_BUFFER NONE: the page buffer and the GL error stay as stock"
C42 = "42 RGBA16F drawing buffer: the page buffer and the GL error stay as stock"
gl_row(C35, "fbo", lambda s, u: u["e"] > 0 and s["same"] and s["h"] != u["h"])
gl_row(C36, "fbosub", lambda s, u: s["diff"] == 0 and u["diff"] == 0 and s["h"] != u["h"])
gl_row(C37, "fbotrans", lambda s, u: u["trans"] > 0 and u["transDiff"] == 0
       and u["opaqueDiff"] == 0 and s["transDiff"] == 0 and s["opaqueDiff"] > 0
       and s["edgeDiff"] == 0)
gl_row(C38, "teximage", lambda s, u: u["eq"] and s["eq"] and s["h"] != u["h"])
s2b_row(C39, lambda r: r["region"],
        lambda u: u["e"] > 0 and u["trans"] > 0 and u["dF"] == 0 and u["dC"] == 0,
        lambda s, u: s["dF"] == 0 and s["dC"] == 0 and s["tH"] != u["tH"])
# C40 needs the unconfigured drawing to give one picture for one flush or many; a GPU raster does not (the host's GPU
# canvas, SwiftShader's): then the row has no verdict (UNMEASURED below), it is not a FAIL.
C40_VACUOUS = s2b_unconf is not None and not (s2b_unconf["flushes"]["e"] > 0
                                              and s2b_unconf["flushes"]["h1"] == s2b_unconf["flushes"]["h2"])
if not C40_VACUOUS:
    s2b_row(C40, lambda r: r["flushes"], lambda u: u["e"] > 0 and u["h1"] == u["h2"],
            lambda s, u: s["h1"] == s["h2"] and s["h1"] != u["h1"])

def rejected_read_unchanged(s, u):
    return (all(v[k]["n"] == 0 for v in (s, u) for k in ("sub", "full"))
            and all(s[k]["e"] == u[k]["e"] for k in ("sub", "full")))


gl_row(C41, "readnone", rejected_read_unchanged)
gl_row(C42, "read16f", rejected_read_unchanged)

C43 = "43 a globalAlpha 0 drawImage leaves a region's noise unchanged"
C44 = "44 a shadowed drawImage elsewhere leaves a region's noise unchanged"
C44B = "44b a shadowed opaque drawImage elsewhere leaves a region's noise unchanged"
for name, key in ((C43, "alpha0"), (C44, "shadowimg"), (C44B, "shadowopq")):
    s2b_row(name, lambda r, key=key: r[key],
            lambda u: u["e"] > 0 and u["a"] == u["b"],
            lambda s, u: s["a"] == s["b"] and s["a"] != u["a"])

C45 = "45 getImageData of rects crossing the canvas edge equals the full read and a copy"
s2b_row(C45, lambda r: r["edgeRects"],
        lambda u: u["e"] > 0 and u["cnt"] > 0 and u["dF"] == 0 and u["dC"] == 0,
        lambda s, u: s["dF"] == 0 and s["dC"] == 0 and s["cnt"] == u["cnt"]
        and s["tH"] != u["tH"])

C36B = "36b framebuffer reads crossing the far edge or the origin equal the full read's part"
C46 = "46 R8 / RG8 framebuffer reads stay stock (G and B stay 0)"
C46B = "46b RGBA4 renderbuffer framebuffer read stays stock"
C47 = "47 SRGB8_ALPHA8 drawing buffer readPixels noised and deterministic"
gl_row(C36B, "fboedge", lambda s, u: s["glerr"] == u["glerr"] == 0
       and all(d == 0 for v in (s, u) for d in v["diff"])
       and all(a != b for a, b in zip(s["h"], u["h"])))
gl_row(C46, "fbofmt", lambda s, u: s["glerr"] == u["glerr"] == 0
       and u["e8"] > 0 and u["eg"] > 0 and u["stray"] == 0 and s["stray"] == 0
       and s["r8"] == u["r8"] and s["rg8"] == u["rg8"] and s["rgba8"] != u["rgba8"])
gl_row(C46B, "fborgba4", lambda s, u: s["glerr"] == u["glerr"] == 0
       and u["e"] > 0 and s["h"] == u["h"] and s["g"] != u["g"])
gl_row(C47, "srgb", lambda s, u: s["glerr"] == u["glerr"] == 0
       and u["e"] > 0 and s["same"] and u["same"] and s["h"] != u["h"])

C48 = "48 a globalAlpha 0 drawImage of an SVG image leaves a region's noise unchanged"
s2b_row(C48, lambda r: r, lambda u: u["e"] > 0 and u["a"] == u["b"],
        lambda s, u: s["a"] == s["b"] and s["a"] != u["a"], runs=svg_runs)

C49 = "49 a large readPixels sub-rect (margin strips) equals the full read's part"
gl_row(C49, "strips", lambda s, u: s["glerr"] == u["glerr"] == 0
       and all(d == 0 for v in (s, u) for d in v["diff"])
       and all(a != b for a, b in zip(s["h"], u["h"])))

C50 = "50 readPixels into a SharedArrayBuffer view equals a plain view's read"
gl_row(C50, "shared", lambda s, u: s["glerr"] == u["glerr"] == 0
       and all(v["diff"] == 0 and v["pad"] == 0 for v in (s, u)) and s["h"] != u["h"])

C51 = "51 a shadowed globalAlpha 0 drawImage leaves a region's noise unchanged"
s2b_row(C51, lambda r: r["shadowalpha0"], lambda u: u["e"] > 0 and u["a"] == u["b"],
        lambda s, u: s["a"] == s["b"] and s["a"] != u["a"])

C52 = "52 a flooding url() drop-shadow filter's pixels read as unconfigured"


def flood_row():
    (sv, se), (uv, ue) = flood_runs
    if sv is None or uv is None:
        results[C52] = False
        notes.append(f"C52: {se or ue}")
        return
    sa, sb, ua, ub = sv["a"], sv["b"], uv["a"], uv["b"]
    px = lambda d, i: tuple(d[i * 4:i * 4 + 4])
    changed = [i for i in range(64 * 64) if px(ub, i) != px(ua, i)]
    flood = sum(px(ub, i) == (51, 170, 119, 255) for i in changed)

    def elig(i):
        y, x = divmod(i, 64)
        if not (0 < x < 63 and 0 < y < 63) or ub[i * 4 + 3] == 0:
            return False
        return all(px(ub, i) != px(ub, j) for j in (i - 1, i + 1, i - 64, i + 64))
    e = sum(map(elig, changed))
    diff = sum(px(sb, i) != px(ub, i) for i in changed)
    guard = len(changed) > 0 and flood > 0 and e > 0 and sa != ua
    results[C52] = guard and diff == 0
    if not results[C52]:
        notes.append(f"C52: changed {len(changed)}, flood {flood}, eligible {e}, "
                     f"seeded A noised {sa != ua}, seeded B differs on {diff}")


flood_row()
C53 = "53 a WebGL2 PACK_ROW_LENGTH / SKIP readPixels from a page framebuffer agrees with the default"
gl_row(C53, "layoutfbo", lambda s, u: s["inside"] == 0 and s["outside"] == 0 and s["h"] != u["h"])

# N1: noise keeps the relations between channels that stock anti-aliasing
# keeps. One launch per seed draws all four scenes (the WebGL one needs
# GL_FLAGS, so every launch has them); the unseeded launch is the "differs"
# reference. Each scene reports its bad-pixel count and a hash of the read.
N1_SEEDS = range(1, 21)
N1_SCENES = "() => {" + HASH_FN + """
  const out = {};
  const arc = (bg, fg, bad) => {
    const c = document.createElement('canvas'); c.width = 200; c.height = 100;
    const x = c.getContext('2d');   // a default 200x100 canvas: GPU-rastered, the only kind that carries noise
    if (bg) { x.fillStyle = bg; x.fillRect(0, 0, 200, 100); }
    x.fillStyle = fg; x.beginPath(); x.arc(100, 50, 38.3, 0, Math.PI * 2); x.fill();
    const d = x.getImageData(0, 0, 200, 100).data;
    let n = 0;
    for (let i = 0; i < d.length; i += 4) if (bad(d[i], d[i + 1], d[i + 2], d[i + 3])) n++;
    return { bad: n, h: H(d) };
  };
  out.a = arc(null, 'rgb(0,0,0)', (r, g, b, a) => a > 0 && (r | g | b) !== 0);
  out.b = arc('rgb(255,255,255)', 'rgb(128,128,128)', (r, g, b) => r !== g || g !== b);
  out.c = arc('rgb(0,0,255)', 'rgb(255,0,0)', (r, g) => g !== 0);
  const c = document.createElement('canvas'); c.width = 128; c.height = 128;
  const gl = c.getContext('webgl', { antialias: true });
  if (!gl) { out.d = { err: 'no-webgl' }; return out; }
  const sh = (t, s) => { const o = gl.createShader(t); gl.shaderSource(o, s);
    gl.compileShader(o); return o; };
  const pr = gl.createProgram();
  gl.attachShader(pr, sh(gl.VERTEX_SHADER,
    'attribute vec2 p;void main(){gl_Position=vec4(p,0,1);}'));
  gl.attachShader(pr, sh(gl.FRAGMENT_SHADER,
    // A grey ramp (R = G = B) whose pixels all differ from their 4 neighbours,
    // so the triangle's interior is eligible: a flat fill leaves ~11 eligible
    // pixels and a quarter of the seeds read as unseeded.
    'precision highp float;void main(){gl_FragColor=vec4(vec3(' +
    'mod(floor(gl_FragCoord.x)*3.0+floor(gl_FragCoord.y)*5.0,256.0)/255.0),1);}'));
  gl.linkProgram(pr); gl.useProgram(pr);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-0.8, -0.7, 0.75, -0.55, -0.15, 0.85]),
    gl.STATIC_DRAW);
  const lp = gl.getAttribLocation(pr, 'p');
  gl.enableVertexAttribArray(lp); gl.vertexAttribPointer(lp, 2, gl.FLOAT, false, 0, 0);
  gl.clearColor(1, 1, 1, 1); gl.clear(gl.COLOR_BUFFER_BIT);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
  const p = new Uint8Array(128 * 128 * 4);
  gl.readPixels(0, 0, 128, 128, gl.RGBA, gl.UNSIGNED_BYTE, p);
  let n = 0;
  for (let i = 0; i < p.length; i += 4) if (p[i] !== p[i + 1] || p[i + 1] !== p[i + 2]) n++;
  out.d = { bad: n, h: H(p) };
  return out;
}"""

n1_unseeded = session(None, N1_SCENES, extra_flags=GL_FLAGS)
n1_seeded = {s: session(json.dumps({"canvas:seed": s}), N1_SCENES, extra_flags=GL_FLAGS)
             for s in N1_SEEDS}

N1_ROWS = (("a", "N1a black arc on transparent keeps RGB 0 (seeds 1-20)"),
           ("b", "N1b grey arc on white keeps R == G == B (seeds 1-20)"),
           ("c", "N1c red arc on blue keeps G == 0 (seeds 1-20)"),
           ("d", "N1d WebGL grey-ramp triangle keeps R == G == B (seeds 1-20)"))
for key, name in N1_ROWS:
    uv, ue = n1_unseeded
    faults = [str(e) for (v, e) in [n1_unseeded, *n1_seeded.values()] if v is None]
    scenes = [v[key] for (v, e) in [n1_unseeded, *n1_seeded.values()] if v is not None]
    if faults or any("err" in sc for sc in scenes):
        results[name] = False
        notes.append(f"{name[:4]}: session fault or no WebGL: {faults[:1] or scenes[0]}")
        continue
    bad = {s: v[key]["bad"] for s, (v, e) in n1_seeded.items()}
    same = [s for s, (v, e) in n1_seeded.items() if v[key]["h"] == uv[key]["h"]]
    results[name] = uv[key]["bad"] == 0 and not any(bad.values()) and not same
    if not results[name]:
        notes.append(f"{name[:4]}: unseeded bad {uv[key]['bad']}; bad per seed {bad}; "
                     f"seeds whose read equals unseeded {same}")

# --- Canvas audit N2-N4 (release -5): C65, C66, C67 ---
# Each row can read UNMEASURED (`unmeasured`: row name -> reason): a precondition it needs was not met, so it has
# no PASS or FAIL. results[name] is None for those rows.
unmeasured = {}
REAL_GPU = os.environ.get("CAMOU_SP3A_REAL_GPU") == "1"       # C66, C67 on the host's own GPU, not SwiftShader
# The host's own GPU needs a headed browser: --headless always renders in software (SwiftShader), so the real-GPU
# flags are the default ones without the headless switches.
GL_ROW_FLAGS = ([f for f in lib_shell.SHELL_FLAGS if f not in ("--headless", "--ozone-platform=headless")]
                if REAL_GPU else GL_FLAGS)
PLANT_C65 = os.environ.get("CAMOU_SP3A_PLANT") == "c65"       # test-only: the seeded sessions draw text 0.5 px lower
N234_SEEDS = range(1, 9)
PLANT_C67 = os.environ.get("CAMOU_SP3A_PLANT") == "c67"       # test-only: C67 compares the 2D read with itself
C67_SIZE = 300
C67_MIN_NOISED = 100                                           # fewer noised pixels than this is no rate
if REAL_GPU:
    import gpu_gate
    gpu_gate.require_interactive()      # session 0 crashes the GPU process once per launch: UNMEASURED, exit 3

C65 = "C65 text transition points match unconfigured (8 seeds)"
C65D = "C65d the same text reads the same at the identity and under scale(1 + 1e-6) (8 seeds)"
C65E = "C65e canvas fillText equals drawImage of the same SVG text (16 origins, 8 seeds)"
C68 = "C68 a willReadFrequently canvas reads like the SVG shapes it draws (8 seeds)"
C68B = "C68b a default canvas that has switched to the CPU reads like the SVG shapes it draws (8 seeds)"
C68C = "C68c unchanged content reads the same before and after the CPU switch (8 seeds)"
C68G = "C68g the idle walk of one 3000-op recording is no long task (a seeded canvas, drawn once, left idle for 1.5 s)"
C68F = "C68f text drawn after the GPU->CPU switch leaves the noise of pixels outside its ink as it was (8 seeds)"
C68E = "C68e text drawn after the GPU->CPU switch, over cells an earlier GPU draw marked, reads noise-free on its ink (8 seeds)"
C68D = "C68d a default 200 x 50 canvas keeps its noise where stock rasters it on the GPU: size is no CPU criterion (8 seeds)"
C66 = "C66 RGB implementation-format read equals the RGBA read"
# Rows outside EXPECTED: UNMEASURED by construction somewhere, so they must not block ALL_PASS, while a measured FAIL
# still fails the script. C66 and C65d: no reference on the backends measured. C68d: UNMEASURED where the unconfigured
# default canvas is a CPU canvas (no GPU raster). Row 40 needs one picture for one flush or many, which a GPU raster
# does not give (UNMEASURED there, measured on a CPU canvas).
SOFT_ROWS = (C66, C65D, C68D, C40)
C67 = "C67 WebGL upload oracle does not de-noise a 2D read"


soft = {}   # rows outside EXPECTED: C66 is UNMEASURED on every backend measured, so it must not block ALL_PASS


def mark_unmeasured(name, why):
    """The row has no verdict: it is named in `unmeasured` (and only there: results[name] is never read for it)."""
    if name in SOFT_ROWS:
        results.pop(name, None)
    (soft if name in SOFT_ROWS else results)[name] = False
    unmeasured[name] = why


if C40_VACUOUS:
    mark_unmeasured(C40, "an unconfigured GPU raster does not give one picture for one flush or many (vacuous); the "
                         "lazy mask's one-or-many equivalence is LazyCanvasNoiseMaskTest")
elif C40 in results:
    soft[C40] = results.pop(C40)

# C65: where the ink of a glyph jumps as the draw position moves in 1/64 px steps. Stock quantises glyph positions,
# so the jump points are CPU constants, the same on every machine; a seed-dependent origin shift moves them.
# Three sweeps: y (a), x (b), y under scale(1.5) (c). The ink's bounding box counts pixels of alpha >= 200 only,
# so the noise on the anti-aliased edge cannot move it.
C65_SCENE = """(shift, shiftX) => {
  const sweep = (mode) => {
    const c = document.createElement('canvas'); c.width = 200; c.height = 160;
    const x = c.getContext('2d', { willReadFrequently: true });
    const sig = [];
    for (let k = 0; k < 64; k++) {
      x.setTransform(1, 0, 0, 1, 0, 0); x.clearRect(0, 0, 200, 160);
      x.fillStyle = '#000'; x.font = '48px sans-serif';
      if (mode === 'ys') x.scale(1.5, 1.5);
      const px = mode === 'x' ? 20 + k / 64 + shiftX : 20;
      const py = mode === 'x' ? 80 : (mode === 'ys' ? 50 : 80) + shift + k / 64;
      x.fillText('H', px, py);
      const d = x.getImageData(0, 0, 200, 160).data;
      let top = 999, bot = -1, left = 999, right = -1;
      for (let j = 0; j < 160; j++) for (let i = 0; i < 200; i++) {
        if (d[(j * 200 + i) * 4 + 3] >= 200) {
          if (j < top) top = j; if (j > bot) bot = j; if (i < left) left = i; if (i > right) right = i; } }
      sig.push(bot < 0 ? 'blank' : (mode === 'x' ? left + ',' + right : top + ',' + bot));
    }
    return sig;
  };
  // d: the same text at the identity and under scale(1 + 1e-6), which stock renders the same: a profile that moves
  // text by a gate on the transform (or on anything but the draw itself) renders the two differently.
  const same = () => {
    const out = [];
    for (let j = 0; j < 16; j++) {
      const c = document.createElement('canvas'); c.width = 200; c.height = 160;
      const x = c.getContext('2d', { willReadFrequently: true });
      const draw = (m) => { x.setTransform(m, 0, 0, m, 0, 0); x.clearRect(0, 0, 200, 160);
        x.fillStyle = '#000'; x.font = '48px sans-serif'; x.fillText('H', (20 + j / 16) / m, 80 / m);
        return x.getImageData(0, 0, 200, 160).data; };
      const a = draw(1), b = draw(1 + 1e-6);
      let eq = true; for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) { eq = false; break; }
      out.push(eq);
    }
    return out;
  };
  return { a: sweep('y'), b: sweep('x'), c: sweep('ys'), d: same() };
}"""


def transitions(sig):
    return [k for k in range(1, len(sig)) if sig[k] != sig[k - 1]]


def reading(key, sig):
    return transitions(sig)


def c65_row():
    def run(config, shift, shiftx):
        return session(config, f"() => ({C65_SCENE})({shift}, {shiftx})")
    un, un_e = run(None, 0, 0)
    # the plant moves the seeded text 0.5 px in y and 0.125 px (half a bin) in x
    seeded = {s: run(json.dumps({"canvas:seed": s}), 0.5 if PLANT_C65 else 0, 0.125 if PLANT_C65 else 0)
              for s in N234_SEEDS}
    faults = [str(e) for (v, e) in [(un, un_e), *seeded.values()] if v is None]
    if un is None or faults:
        results[C65] = False
        mark_unmeasured(C65D, "C65's sessions faulted: no reading")
        notes.append(f"C65: session fault: {faults[:1]}")
        return
    d_ref = all(un["d"])
    if not d_ref:
        mark_unmeasured(C65D, f"stock renders the same text differently at the identity and under scale(1 + 1e-6) "
                        f"({un['d'].count(False)} of 16 positions): no reference (C65e is the oracle there)")
    ref = {k: reading(k, un[k]) for k in "abc"}
    blank = [k for k in "abc" if "blank" in un[k] or not ref[k]]
    if blank:
        mark_unmeasured(C65, f"no ink transition in sweep(s) {blank} of the unconfigured run "
                        f"(blank glyph or a missing font): {[ref[k] for k in blank]}")
        if C65D not in unmeasured:
            mark_unmeasured(C65D, "C65 has no ink to read (blank glyph or a missing font)")
        return
    bad, bad_d = {}, {}
    for s, (v, e) in seeded.items():
        if v is None:
            bad[s] = str(e)
            continue
        off = [k for k in "abc" if reading(k, v[k]) != ref[k]]
        if off:
            bad[s] = {k: reading(k, v[k]) for k in off}
        if d_ref and not all(v["d"]):
            bad_d[s] = f"{v['d'].count(False)} of 16 positions differ at scale(1 + 1e-6)"
    results[C65] = not bad
    if d_ref:
        soft[C65D] = not bad_d
        if bad_d:
            notes.append(f"C65d: seeds whose text differs under scale(1 + 1e-6): {bad_d}")
    notes.append(f"C65 unconfigured transitions: a {ref['a']}, b {ref['b']}, c {ref['c']}")
    if bad:
        notes.append(f"C65: seeds whose transitions differ: {bad}")


c65_row()

# C65e: stock rasters canvas text and SVG <text> identically (measured 2026-11-15: 16 of 16 origins, pixel for pixel), so
# a text origin moved for fillText alone shows against the SVG text drawn at the same origin: no seed and no stock
# reference are needed. Equal at every origin for the unconfigured run (else UNMEASURED) and for seeds 1..8.
C65E_SCENE = """async () => {
  const W = 200, H = 160, Y = 80, out = [];
  const svgImage = (x) => new Promise((res, rej) => {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}"><text x="${x}" y="${Y}" font-size="48px" font-family="sans-serif" fill="#000">H</text></svg>`;
    const im = new Image(); im.onload = () => res(im); im.onerror = () => rej(new Error('svg image')); im.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  });
  for (let j = 0; j < 16; j++) {
    const x = 20 + j / 16;
    const a = document.createElement('canvas'); a.width = W; a.height = H;
    const ca = a.getContext('2d', { willReadFrequently: true });
    ca.fillStyle = '#000'; ca.font = '48px sans-serif'; ca.fillText('H', x, Y);
    const b = document.createElement('canvas'); b.width = W; b.height = H;
    const cb = b.getContext('2d', { willReadFrequently: true });
    cb.drawImage(await svgImage(x), 0, 0);
    const da = ca.getImageData(0, 0, W, H).data, db = cb.getImageData(0, 0, W, H).data;
    let ink = 0, diff = 0;
    for (let i = 3; i < da.length; i += 4) { if (da[i] || db[i]) ink++; if (da[i] !== db[i]) diff++; }
    out.push({ ink, diff });
  }
  return out;
}"""


def c65e_row():
    un, un_e = session(None, C65E_SCENE)
    if un is None:
        results[C65E] = False
        notes.append(f"C65e: session fault: {un_e}")
        return
    if any(r["ink"] == 0 for r in un) or any(r["diff"] for r in un):
        mark_unmeasured(C65E, "the unconfigured run does not read equal: "
                        f"{sum(1 for r in un if r['diff'])} of 16 origins differ, {sum(1 for r in un if r['ink'] == 0)} blank")
        return
    bad = {}
    for seed in N234_SEEDS:
        v, e = session(json.dumps({"canvas:seed": seed}), C65E_SCENE)
        if v is None:
            bad[seed] = str(e)
        elif any(r["diff"] for r in v):
            bad[seed] = f"{sum(1 for r in v if r['diff'])} of 16 origins differ ({max(r['diff'] for r in v)} px at most)"
    results[C65E] = not bad
    if bad:
        notes.append(f"C65e: seeds whose text differs from the SVG text: {bad}")


c65e_row()

# C68 (owner 2026-11-15, canvas audit shape oracle): pixels a 2D canvas rasterised on the CPU are exact in stock: an
# arc and a fractional rect equal the same shapes imported as an SVG image, pixel for pixel, so readback noise on them
# is detectable without a seed. C68: a willReadFrequently canvas. C68b: a default canvas that stock switched to the
# CPU after repeated reads, drawn on afterwards. C68c: the same unchanged content read before and after the switch must
# read the same (a gate decided per canvas, not per raster, would flip it). The unconfigured run must be exact (GPU
# canvases are not: stock differs from the SVG by tens of levels), else UNMEASURED.
C68_SCENE = """async (mode) => {
  const small = mode === 'small';            // 200 x 50: under 128 x 129 px, a CPU canvas in stock
  const W = 200, H = small ? 50 : 100, CY = H / 2, R = small ? 19.3 : 38.3;
  const svgImg = (inner) => new Promise((res, rej) => {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">${inner}</svg>`;
    const im = new Image(); im.onload = () => res(im); im.onerror = () => rej(new Error('svg image'));
    im.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  });
  const SVG = `<rect width="200" height="${H}" fill="#fff"/><circle cx="100" cy="${CY}" r="${R}" fill="rgb(128,128,128)"/>` +
              '<rect x="10.3" y="10.6" width="30.2" height="12.7" fill="rgb(20,60,200)"/>';
  const draw = (x) => { x.fillStyle = '#fff'; x.fillRect(0, 0, W, H); x.fillStyle = 'rgb(128,128,128)';
    x.beginPath(); x.arc(100, CY, R, 0, Math.PI * 2); x.fill();
    x.fillStyle = 'rgb(20,60,200)'; x.fillRect(10.3, 10.6, 30.2, 12.7); };
  const read = (x) => x.getImageData(0, 0, W, H).data;
  const same = (a, b) => { let d = 0; for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) d++; return d; };
  const ref = document.createElement('canvas'); ref.width = W; ref.height = H;
  const xr = ref.getContext('2d', { willReadFrequently: true }); xr.drawImage(await svgImg(SVG), 0, 0);
  const svgPx = read(xr);
  const c = document.createElement('canvas'); c.width = W; c.height = H;
  if (mode === 'small') {
    const x = c.getContext('2d'); draw(x);
    const d = read(x); let h = 2166136261;
    for (let i = 0; i < d.length; i++) h = Math.imul(h ^ d[i], 16777619) >>> 0;
    return { diff: same(d, svgPx), h };
  }
  if (mode === 'wrf') {
    const x = c.getContext('2d', { willReadFrequently: true }); draw(x);
    return { diff: same(read(x), svgPx) };
  }
  const x = c.getContext('2d');
  draw(x);
  const before = Array.from(read(x));              // unchanged content, before the switch
  const pre = same(before, svgPx);                 // > 0: GPU-rastered until now (a CPU canvas from the start reads exact)
  for (let i = 0; i < 8; i++) read(x);              // repeated reads: stock switches the canvas to the CPU
  const after = Array.from(read(x));               // the same content after it
  const kept = same(before, after);
  x.clearRect(0, 0, W, H); draw(x);                // drawn after the switch
  const post = same(read(x), svgPx);               // 0: the canvas is a CPU canvas now (the switch happened)
  return { diff: mode === 'same' ? kept : post, pre, post };
}"""


def c68_rows():
    for name, mode in ((C68, "wrf"), (C68B, "after"), (C68C, "same"), (C68D, "small")):
        un, un_e = session(None, f"() => ({C68_SCENE})('{mode}')")
        if un is None:
            (soft if name in SOFT_ROWS else results)[name] = False
            notes.append(f"{name[:4]}: session fault: {un_e}")
            continue
        if mode in ("after", "same") and not un["pre"]:
            mark_unmeasured(name, "the canvas reads exact before any readback: a CPU canvas from the start, so there is "
                                  "no GPU->CPU switch to test")
            continue
        if mode in ("after", "same") and un["post"]:
            mark_unmeasured(name, f"the redraw after {8} readbacks is not exact ({un['post']} channel bytes differ): "
                                  f"the canvas did not switch to the CPU")
            continue
        if un["diff"] and mode != "small":
            mark_unmeasured(name, f"the unconfigured canvas is not exact against the SVG shapes here "
                                  f"({un['diff']} channel bytes differ): a GPU-rastered canvas, no reference")
            continue
        bad = {}
        if mode == "small":
            # AcceleratedSmallCanvases is stable: a small default canvas is GPU-rastered like a large one, so it keeps
            # N1 noise (opposite polarity to C68: the seeded read must differ from the exact one).
            if not un["diff"]:
                mark_unmeasured(name, "the unconfigured 200 x 50 canvas is exact against the SVG shapes: a CPU canvas "
                                      "here (no GPU rasterization), nothing to keep")
                continue
        unswitched = []
        for seed in N234_SEEDS:
            v, e = session(json.dumps({"canvas:seed": seed}), f"() => ({C68_SCENE})('{mode}')")
            if v is None:
                bad[seed] = str(e)
            elif mode == "same" and v["post"]:
                unswitched.append(seed)       # this seeded canvas did not switch: its before/after pair says nothing
            elif mode == "small":
                if v["h"] == un["h"]:
                    bad[seed] = "the seeded read equals the unconfigured one: no noise on a GPU-rastered small canvas"
            elif v["diff"]:
                bad[seed] = f"{v['diff']} channel bytes differ"
        if unswitched:
            mark_unmeasured(name, f"the seeded canvas did not switch to the CPU after eight readbacks (seeds {unswitched})")
            continue
        (soft if name in SOFT_ROWS else results)[name] = not bad
        if bad:
            notes.append(f"{name[:4]}: seeds whose read differs from the exact one: {bad}")


c68_rows()

# C68e: the rule-B hole. After stock switches a canvas to the CPU, text drawn over cells that GPU-era draws marked
# anti-aliased must not keep their noise: the ink's pixels read as the unconfigured canvas reads them. A dense field of
# small circles (GPU-rastered, anti-aliased edges everywhere in the box), eight readbacks (the switch), a corner circle
# that proves the switch (CPU: exact against the SVG), then fillText over the field. The ink is the SVG text's own alpha.
C68E_SCENE = """async () => {
  const W = 200, H = 100;
  const load = (svg) => new Promise((res, rej) => { const im = new Image(); im.onload = () => res(im); im.onerror = () => rej(new Error('svg'));
    im.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg); });
  const wrap = (inner) => `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">${inner}</svg>`;
  const refPx = async (inner) => { const c = document.createElement('canvas'); c.width = W; c.height = H;
    const x = c.getContext('2d', { willReadFrequently: true }); x.drawImage(await load(wrap(inner)), 0, 0);
    return x.getImageData(0, 0, W, H).data; };
  const dots = [];
  // the field spans the canvas, well past the text's bounds (Skia's blob bounds are conservative: about x - 1.0 * size to
  // x + 1.8 * size across, y - 1.2 * size to y + 0.5 * size), so noise outside the text's area exists to prove the row measures
  for (let i = 0; i < 32; i++) for (let j = 0; j < 18; j++) {
    const px = 22.3 + 5 * i, py = 7.3 + 5 * j;
    if (px > 140 && py < 38) continue;                                 // the corner circle's own place
    dots.push([px, py]);
  }
  const FIELD = dots.map(([cx, cy]) => `<circle cx="${cx}" cy="${cy}" r="3.3" fill="rgb(128,128,128)"/>`).join('');
  const CORNER = '<circle cx="170" cy="15" r="10.3" fill="rgb(0,0,0)"/>';
  const fieldRef = await refPx('<rect width="200" height="100" fill="#fff"/>' + FIELD);
  const cornerRef = await refPx('<rect width="200" height="100" fill="#fff"/>' + CORNER);
  const inkRef = await refPx('<text x="86" y="58" font-family="sans-serif" font-size="36" fill="#000">H</text>');
  const c = document.createElement('canvas'); c.width = W; c.height = H;
  const x = c.getContext('2d');
  x.fillStyle = '#fff'; x.fillRect(0, 0, W, H); x.fillStyle = 'rgb(128,128,128)';
  for (const [cx, cy] of dots) { x.beginPath(); x.arc(cx, cy, 3.3, 0, Math.PI * 2); x.fill(); }
  const first = x.getImageData(0, 0, W, H).data;
  let pre = 0; for (let i = 0; i < first.length; i++) if (first[i] !== fieldRef[i]) pre++;     // > 0: GPU-rastered so far
  for (let i = 0; i < 8; i++) x.getImageData(0, 0, 1, 1);                                        // stock switches to the CPU
  x.fillStyle = 'rgb(0,0,0)'; x.beginPath(); x.arc(170, 15, 10.3, 0, Math.PI * 2); x.fill();
  x.font = '36px sans-serif'; x.fillText('H', 86, 58);
  const d = x.getImageData(0, 0, W, H).data;
  let corner = 0;                                                                                  // the corner circle, exact on a CPU canvas
  for (let y = 0; y < 30; y++) for (let xx = 150; xx < 200; xx++) for (let k = 0; k < 4; k++)
    if (d[(y * W + xx) * 4 + k] !== cornerRef[(y * W + xx) * 4 + k]) corner++;
  const ink = []; for (let i = 3; i < inkRef.length; i += 4) if (inkRef[i] > 0) ink.push((i - 3) / 4);
  return { pre, corner, ink, px: Array.from(d) };
}"""


def c68e_row():
    un, un_e = session(None, f"() => ({C68E_SCENE})()")
    if un is None:
        results[C68E] = False
        notes.append(f"C68e: session fault: {un_e}")
        return
    if not un["pre"]:
        mark_unmeasured(C68E, "the field reads exact before any readback: a CPU canvas from the start, no GPU->CPU switch")
        return
    if un["corner"]:
        mark_unmeasured(C68E, f"the corner circle drawn after eight readbacks is not exact ({un['corner']} channel bytes "
                              f"differ): the canvas did not switch to the CPU")
        return
    ink = [4 * i + k for i in un["ink"] for k in range(4)]
    if not ink:
        mark_unmeasured(C68E, "the SVG text has no ink (a missing font)")
        return
    bad, vacuous = {}, True
    for seed in N234_SEEDS:
        v, e = session(json.dumps({"canvas:seed": seed}), f"() => ({C68E_SCENE})()")
        if v is None:
            bad[seed] = str(e)
            continue
        if v["corner"] or not v["pre"]:
            mark_unmeasured(C68E, f"the seeded canvas (seed {seed}) did not switch to the CPU or was a CPU canvas from the start "
                                  f"(corner {v['corner']} channel bytes off, pre {v['pre']})")
            return
        off = sum(1 for i in ink if v["px"][i] != un["px"][i])
        if off:
            bad[seed] = f"{off} channel bytes of the ink differ from the unconfigured read"
        if v["px"] != un["px"]:
            vacuous = False       # noise acted somewhere (the GPU-era field), so equality on the ink says something
    if vacuous and not bad:
        mark_unmeasured(C68E, "no seed changed any pixel of the canvas: no noise to keep off the ink")
        return
    results[C68E] = not bad
    if bad:
        notes.append(f"C68e: seeds whose ink carries noise: {bad}")


c68e_row()

# C68f: a CPU op on a switched canvas merges its real coverage, not its conservative bounds. A large GPU circle (its edge
# cells are marked anti-aliased), eight readbacks (the switch), a read, a corner circle that proves the switch, then
# fillText whose BOUNDS cover the circle's right edge while its ink does not, and a second read: every pixel outside the
# ink (and outside the corner) reads as it did the first time. Marking the bounds would drop the noise of the edge.
C68F_SCENE = """async () => {
  const W = 200, H = 100;
  const load = (svg) => new Promise((res, rej) => { const im = new Image(); im.onload = () => res(im); im.onerror = () => rej(new Error('svg'));
    im.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg); });
  const wrap = (inner) => `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">${inner}</svg>`;
  const refPx = async (inner) => { const c = document.createElement('canvas'); c.width = W; c.height = H;
    const x = c.getContext('2d', { willReadFrequently: true }); x.drawImage(await load(wrap(inner)), 0, 0);
    return x.getImageData(0, 0, W, H).data; };
  const BG = '<rect width="200" height="100" fill="#fff"/>';
  const circleRef = await refPx(BG + '<circle cx="100" cy="50" r="38.3" fill="rgb(128,128,128)"/>');
  const cornerRef = await refPx(BG + '<circle cx="170" cy="15" r="10.3" fill="rgb(0,0,0)"/>');
  const inkRef = await refPx('<text x="100" y="58" font-family="sans-serif" font-size="28" fill="#000">H</text>');
  const c = document.createElement('canvas'); c.width = W; c.height = H;
  const x = c.getContext('2d');
  x.fillStyle = '#fff'; x.fillRect(0, 0, W, H); x.fillStyle = 'rgb(128,128,128)';
  x.beginPath(); x.arc(100, 50, 38.3, 0, Math.PI * 2); x.fill();
  const first = Array.from(x.getImageData(0, 0, W, H).data);
  let pre = 0; for (let i = 0; i < first.length; i++) if (first[i] !== circleRef[i]) pre++;      // > 0: GPU-rastered so far
  for (let i = 0; i < 8; i++) x.getImageData(0, 0, 1, 1);                                          // stock switches to the CPU
  x.fillStyle = 'rgb(0,0,0)'; x.beginPath(); x.arc(170, 15, 10.3, 0, Math.PI * 2); x.fill();
  x.font = '28px sans-serif'; x.fillText('H', 100, 58);
  const second = Array.from(x.getImageData(0, 0, W, H).data);
  let corner = 0;
  for (let y = 0; y < 30; y++) for (let xx = 150; xx < 200; xx++) for (let k = 0; k < 4; k++)
    if (second[(y * W + xx) * 4 + k] !== cornerRef[(y * W + xx) * 4 + k]) corner++;
  const ink = []; for (let i = 3; i < inkRef.length; i += 4) if (inkRef[i] > 0) ink.push((i - 3) / 4);
  return { pre, corner, ink, first, second };
}"""


def c68f_row():
    seeds = [None, *N234_SEEDS]
    runs = {}
    for seed in seeds:
        cfg = None if seed is None else json.dumps({"canvas:seed": seed})
        runs[seed] = session(cfg, f"() => ({C68F_SCENE})()")
    un, un_e = runs[None]
    if un is None:
        results[C68F] = False
        notes.append(f"C68f: session fault: {un_e}")
        return
    for seed, (v, e) in runs.items():
        if v is None:
            if seed is None:
                continue
            results[C68F] = False
            notes.append(f"C68f: seed {seed} session fault: {e}")
            return
        if not v["pre"] or v["corner"]:
            mark_unmeasured(C68F, f"the {'unconfigured' if seed is None else 'seeded (seed %s)' % seed} canvas was a CPU canvas from "
                                  f"the start or did not switch (pre {v['pre']}, corner {v['corner']} channel bytes off)")
            return
    skip = set(un["ink"])
    skip.update(y * 200 + x for y in range(30) for x in range(150, 200))      # the corner circle is drawn between the reads
    keep = [4 * i + k for i in range(200 * 100) if i not in skip for k in range(4)]
    if all(runs[s][0]["first"] == un["first"] for s in N234_SEEDS):
        mark_unmeasured(C68F, "no seed changed the first read: no noise on the circle's edge to keep")
        return
    bad = {}
    for seed in N234_SEEDS:
        v = runs[seed][0]
        off = sum(1 for i in keep if v["first"][i] != v["second"][i])
        if off:
            bad[seed] = f"{off} channel bytes outside the ink changed between the two reads"
    results[C68F] = not bad
    if bad:
        notes.append(f"C68f: {bad}")


c68f_row()

# C68g (a GUARD, not a RED row: it also passes on the build that walked a recording in one piece, which the box does not
# turn into a 'longtask' entry): an idle task that walks one flush's recording in one piece is a long task a seeded page does
# not have. A 3000-op
# recording of large circles is drawn once and the page idles for 1.5 s while the mask is walked; a 'longtask' entry (>= 50 ms of main-thread
# task) would be the walk. The unconfigured run is the control: a long task there is the page's own, not the walk's.
C68G_SCENE = """async () => {
  if (!PerformanceObserver.supportedEntryTypes || !PerformanceObserver.supportedEntryTypes.includes('longtask'))
    return { unsupported: true };
  await new Promise((r) => setTimeout(r, 300));
  const durations = [];
  new PerformanceObserver((l) => { for (const e of l.getEntries()) durations.push(Math.round(e.duration)); })
    .observe({ type: 'longtask', buffered: false });
  const c = document.createElement('canvas'); c.width = 256; c.height = 256;
  const x = c.getContext('2d');
  // one recording of 3000 large circles: a walk rasters each one's coverage (about 30 us each on the box), so
  // walking it in one piece is a task of about 90 ms; small ops would be flushed in pieces too small to show
  for (let i = 0; i < 3000; i++) { x.fillStyle = i & 1 ? '#f60' : '#06f'; x.beginPath();
    x.arc(128, 128, 90 + (i % 30), 0, Math.PI * 2); x.fill(); }
  await new Promise((r) => setTimeout(r, 1500));
  return { durations };
}"""


def c68g_row():
    un, un_e = session(None, f"() => ({C68G_SCENE})()")
    sd, sd_e = session(json.dumps({"canvas:seed": 7}), f"() => ({C68G_SCENE})()")
    if un is None or sd is None:
        results[C68G] = False
        notes.append(f"C68g: session fault: {un_e or sd_e}")
        return
    if un.get("unsupported") or sd.get("unsupported"):
        mark_unmeasured(C68G, "PerformanceObserver does not report 'longtask' here")
        return
    if un["durations"]:
        mark_unmeasured(C68G, f"the unconfigured control has long tasks of its own: {un['durations']}")
        return
    results[C68G] = not sd["durations"]
    if sd["durations"]:
        notes.append(f"C68g: the seeded page has long tasks (ms): {sd['durations']}")


c68g_row()

# C66: the implementation-format read. A framebuffer with an RGB8 attachment reports (RGB, UNSIGNED_BYTE) as its
# read pair; stock returns the rendered bytes for both reads, so the RGB bytes of an RGB read equal the first three
# bytes of the RGBA read. C66a: an RGB8 texture framebuffer with the C6 scene. C66b: an alpha:false default buffer,
# 63 px wide (a row of 189 bytes: with PACK_ALIGNMENT 4 the padding bytes stay untouched).
C66_SCENE = tri("webgl2", 63, 64, """
  const GLRGB = gl.RGB, pairOf = () => [gl.getParameter(gl.IMPLEMENTATION_COLOR_READ_FORMAT),
                                         gl.getParameter(gl.IMPLEMENTATION_COLOR_READ_TYPE)];
  const cmp = (w, h) => {
    const pair = pairOf();
    const A = new Uint8Array(w * h * 4); gl.readPixels(0, 0, w, h, RGBA, UB, A);
    if (pair[0] !== GLRGB || pair[1] !== UB) return { pair };
    const stride = Math.ceil(w * 3 / 4) * 4;
    const B = new Uint8Array(stride * h).fill(0xAB); gl.readPixels(0, 0, w, h, GLRGB, UB, B);
    let pix = 0, pad = 0;
    for (let y = 0; y < h; y++) {
      for (let i = 0; i < w; i++) for (let c = 0; c < 3; c++) if (B[y * stride + i * 3 + c] !== A[(y * w + i) * 4 + c]) pix++;
      if (y < h - 1) for (let i = w * 3; i < stride; i++) if (B[y * stride + i] !== 0xAB) pad++; }
    return { pair, pix, pad, h: H(A) };
  };
  const out = {};
  const dbg = gl.getExtension('WEBGL_debug_renderer_info');
  out.renderer = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null;
  // (a) an RGB8 texture framebuffer, 64 x 64
  const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB8, 64, 64, 0, gl.RGB, UB, null);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  const f = gl.createFramebuffer(); gl.bindFramebuffer(gl.FRAMEBUFFER, f);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0);
  if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE) out.a = { err: 'fbo-incomplete' };
  else { gl.viewport(0, 0, 64, 64); gl.clearColor(0.2, 0.5, 0.8, 1.0); gl.clear(gl.COLOR_BUFFER_BIT);
         gl.drawArrays(gl.TRIANGLES, 0, 3); out.a = cmp(64, 64); }
  return out;""")
# (b) the alpha:false default framebuffer of a 63-wide canvas: its own context, the C6 scene again
C66B_SCENE = C66_SCENE.replace("c.getContext('webgl2')", "c.getContext('webgl2', { alpha: false })").replace(
    "  // (a) an RGB8", "  gl.bindFramebuffer(gl.FRAMEBUFFER, null); gl.viewport(0, 0, 63, 64);\n"
    "  gl.clearColor(0.2, 0.5, 0.8, 1.0); gl.clear(gl.COLOR_BUFFER_BIT); gl.drawArrays(gl.TRIANGLES, 0, 3);\n"
    "  out.b = cmp(63, 64);\n  return out;\n  // (a) an RGB8")


def gpu_unmeasured(name, errs, renderers):
    """True (and the row marked UNMEASURED) when a host GPU run cannot give a verdict: a gated session saw a GPU
    crash, or the unconfigured session's renderer is software (headless, or no GPU) or unreadable."""
    import gpu_gate
    crash = [e for e in errs if isinstance(e, gpu_gate.Unmeasured)]
    if crash:
        mark_unmeasured(name, str(crash[0]))
        return True
    if REAL_GPU:
        # every session of the row, the unconfigured and the seeded: a seeded launch that fell back to software
        # would measure the wrong thing
        fams = [gpu_gate.renderer_family(r) for r in renderers]
        notes.append(f"{name[:3]} renderer family: {sorted({f for f, _ in fams})}")
        if not fams or any(sw or not r for (_, sw), r in zip(fams, renderers)):
            mark_unmeasured(name, f"a host GPU session rendered in software or its renderer is unreadable "
                                  f"({sorted({f for f, _ in fams})})")
            return True
    return False


def c66_row():
    seed7 = json.dumps({"canvas:seed": 7})
    parts = {}
    for key, scene in (("a", C66_SCENE), ("b", C66B_SCENE)):
        u, ue = session(None, scene, extra_flags=GL_ROW_FLAGS, gate=REAL_GPU)
        sd, se = session(seed7, scene, extra_flags=GL_ROW_FLAGS, gate=REAL_GPU)
        parts[key] = (u, sd, ue or se)
    if gpu_unmeasured(C66, [e for _, _, e in parts.values()],
                      [(x or {}).get("renderer") for p in parts.values() for x in p[:2]]):
        return
    why, fail = [], []
    for key, (u, sd, err) in parts.items():
        if u is None or sd is None:
            fail.append(f"C66{key}: session fault {err}")
            continue
        ru, rs = u.get(key) or {}, sd.get(key) or {}
        if "err" in u or "err" in ru or "err" in rs:
            why.append(f"C66{key}: {ru.get('err') or rs.get('err') or u.get('err')}")
        elif ru.get("pair") != [0x1907, 0x1401]:
            why.append(f"C66{key}: implementation pair {ru.get('pair')} is not (RGB, UNSIGNED_BYTE)")
        elif "pix" not in rs:
            why.append(f"C66{key}: the seeded pair {rs.get('pair')} is not (RGB, UNSIGNED_BYTE)")
        elif rs["h"] == ru["h"]:
            why.append(f"C66{key}: the seeded RGBA read equals the unconfigured one (the noise did not act)")
        elif rs["pix"] or rs["pad"]:
            fail.append(f"C66{key}: RGB bytes differing from the RGBA read {rs['pix']}, touched padding bytes {rs['pad']}")
        else:
            notes.append(f"C66{key} measured: pair (RGB, UNSIGNED_BYTE), {rs['pix']} differing bytes, {rs['pad']} padding bytes touched")
    if fail:
        soft[C66] = False
        notes.extend(fail)
    elif why:
        mark_unmeasured(C66, "; ".join(why))
    else:
        soft[C66] = True


c66_row()

# C67: the WebGL upload oracle. A page can upload pixels it chose (an ImageData: clean bytes) to WebGL, draw them
# NEAREST and read them back: that read carries WebGL's noise on a patch of the page's choosing. If WebGL drew its
# noise from the same keys as the 2D canvas, the noise on a patch would be the same field in both, so a page could
# learn it there and strip it from 2D reads of the same patches (canvas audit N4). The scene is an opaque 2D drawing;
# S is its unconfigured read, N2d its seeded getImageData, NW the seeded WebGL read of S uploaded as ImageData.
# Where N2d differs from S, shared keys make NW equal N2d; separate keys leave them equal only where WebGL did
# not move the pixel as 2D did.
C67_SCENE = """(clean) => {
  const c = document.createElement('canvas'); c.width = 300; c.height = 300;
  const x = c.getContext('2d');   // GPU-rastered: a CPU canvas carries no noise
  x.fillStyle = '#fff'; x.fillRect(0, 0, 300, 300);
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) {       // nine arcs: enough edge pixels for a rate
    x.fillStyle = `rgb(${200 - 30 * i},${40 + 50 * j},${40 + 60 * i})`;
    x.beginPath(); x.arc(50 + 100 * i, 50 + 100 * j, 31.3 + 2.1 * i + 1.7 * j, 0, Math.PI * 2); x.fill();
  }
  x.fillStyle = 'rgb(20,60,200)'; x.fillRect(10.3, 10.6, 30.2, 12.7);
  const n2d = Array.from(x.getImageData(0, 0, 300, 300).data);
  const g = document.createElement('canvas'); g.width = 300; g.height = 300;
  const gl = g.getContext('webgl', { antialias: false, premultipliedAlpha: false });
  if (!gl) return { err: 'no-webgl' };
  const sh = (t, s) => { const o = gl.createShader(t); gl.shaderSource(o, s); gl.compileShader(o); return o; };
  const pr = gl.createProgram();
  gl.attachShader(pr, sh(gl.VERTEX_SHADER, 'attribute vec2 p;varying vec2 u;void main(){u=p*0.5+0.5;gl_Position=vec4(p,0,1);}'));
  gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, 'precision mediump float;varying vec2 u;uniform sampler2D t;void main(){gl_FragColor=texture2D(t,u);}'));
  gl.linkProgram(pr); gl.useProgram(pr);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
  const lp = gl.getAttribLocation(pr, 'p'); gl.enableVertexAttribArray(lp); gl.vertexAttribPointer(lp, 2, gl.FLOAT, false, 0, 0);
  const tx = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, tx);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  const src = new ImageData(new Uint8ClampedArray(clean || n2d), 300, 300);   // clean bytes: no canvas snapshot, no 2D noise
  // readPixels rows run bottom-up and the noise reads them as such: flipping on upload makes buffer row 0 the image's
  // bottom row, so the WebGL field sees the same top-down patches the 2D read does (flipped back below).
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, src);
  gl.viewport(0, 0, 300, 300); gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  const p = new Uint8Array(300 * 300 * 4); gl.readPixels(0, 0, 300, 300, gl.RGBA, gl.UNSIGNED_BYTE, p);
  const dbg = gl.getExtension('WEBGL_debug_renderer_info');
  return { n2d, nw: Array.from(p), renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null };
}"""


def c67_row():
    u, ue = session(None, f"() => ({C67_SCENE})(null)", extra_flags=GL_ROW_FLAGS, gate=REAL_GPU)
    if u is None or "err" in u:
        if gpu_unmeasured(C67, [ue], [None]):
            return
        results[C67] = False if u is None else None
        if u is not None:
            mark_unmeasured(C67, str(u.get("err")))
        else:
            notes.append(f"C67: session fault: {ue}")
        return
    S = u["n2d"]
    sd, se = session(json.dumps({"canvas:seed": 7}), f"() => ({C67_SCENE})({json.dumps(S)})",
                     extra_flags=GL_ROW_FLAGS, gate=REAL_GPU)
    import gpu_gate
    if sd is None and not isinstance(se, gpu_gate.Unmeasured):
        results[C67] = False                  # a seeded session that faulted is a fault of the build under test
        notes.append(f"C67: session fault: {se}")
        return
    if gpu_unmeasured(C67, [ue, se], [u.get("renderer"), (sd or {}).get("renderer")]):
        return
    if "err" in sd:
        mark_unmeasured(C67, str(sd.get("err")))
        return
    N, W = sd["n2d"], sd["nw"]
    W = [b for r in range(C67_SIZE - 1, -1, -1) for b in W[r * C67_SIZE * 4:(r + 1) * C67_SIZE * 4]]   # buffer rows are bottom-up
    if PLANT_C67:
        W = list(N)     # test-only: the WebGL read IS the 2D read (shared keys): the row must FAIL
    diff = [i for i in range(0, len(S), 4) if S[i:i + 4] != N[i:i + 4]]
    if len(diff) < C67_MIN_NOISED:
        mark_unmeasured(C67, f"only {len(diff)} pixels carry 2D noise (need {C67_MIN_NOISED}): no rate to compare")
        return
    if not PLANT_C67 and W == S:
        mark_unmeasured(C67, "the WebGL read of the clean pixels equals the clean pixels: WebGL added no noise")
        return
    same = sum(1 for i in diff if W[i:i + 4] == N[i:i + 4])
    frac = same / len(diff)
    # Threshold from the measurements of 2026-11-15 (this scene's predecessor, 29 pixels): separate keys read 0% equal,
    # shared keys 100%; 0.5 sits between them with the slack of an independent noise rate.
    results[C67] = frac <= 0.5
    notes.append(f"C67: {len(diff)} pixels carry 2D noise; the WebGL read of the same clean pixels equals the 2D read at "
                 f"{same} ({frac:.0%}; shared keys give 100%, separate keys the chance both moved a pixel alike)")


c67_row()

# --- WebGL readback leaks (2026-11-19): C70-C74 ---
# Two WebGL paths returned the host's raw pixels under canvas:seed: the WebGL2 readPixels overload into a bound
# PIXEL_PACK_BUFFER (read back with getBufferSubData), and OffscreenCanvas.transferToImageBitmap (main thread and worker).
# One page function runs every path; it runs in four sessions: no config, seed A, seed B, seed A again.
C70 = "C70 WebGL2 PBO readPixels + getBufferSubData is noised: seed A != none, A != B, A == A again"
C71 = "C71 PBO bytes equal the readPixels(view) bytes of the same page (no config and both seeds), binding and GL error intact"
C72 = "C72 PBO with PACK_ALIGNMENT 8, a rect past the framebuffer and an offset equals the view read; every byte outside the written rect is still 0xAB"
C72B = "C72b PBO read from an RGBA8 texture FBO (PACK_ROW_LENGTH w + 16, SKIP_PIXELS 3, SKIP_ROWS 2; 64, 600 and a 598 inset) equals the view read"
C73 = "C73 transferToImageBitmap then 2D getImageData: noised (A != none, A != B, A == A again), equals drawImage(canvas)"
C74 = "C74 the same in a worker: noised, equal to the main thread's drawImage(canvas) hash"
LEAKS = """async () => {
  const H = (u8) => { let h = 2166136261;
    for (let i = 0; i < u8.length; i++) { h ^= u8[i]; h = Math.imul(h, 16777619) >>> 0; }
    return h.toString(16); };
  const scene = (gl, w, h) => {
    const sh = (type, src) => { const s = gl.createShader(type);
      gl.shaderSource(s, src); gl.compileShader(s); return s; };
    const pr = gl.createProgram();
    gl.attachShader(pr, sh(gl.VERTEX_SHADER,
      'attribute vec2 p;attribute vec3 k;varying vec3 v;varying vec2 q;void main(){v=k;q=p;gl_Position=vec4(p,0,1);}'));
    gl.attachShader(pr, sh(gl.FRAGMENT_SHADER,
      'precision mediump float;varying vec3 v;varying vec2 q;void main(){gl_FragColor=vec4(v*(0.75+0.25*sin(q.x*40.0+q.y*17.0)),1);}'));
    gl.linkProgram(pr); gl.useProgram(pr);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(
      [-0.9, -0.8, 1, 0, 0,  0.85, -0.6, 0, 1, 0,  -0.1, 0.9, 0, 0, 1]), gl.STATIC_DRAW);
    const lp = gl.getAttribLocation(pr, 'p'), lk = gl.getAttribLocation(pr, 'k');
    gl.enableVertexAttribArray(lp); gl.vertexAttribPointer(lp, 2, gl.FLOAT, false, 20, 0);
    gl.enableVertexAttribArray(lk); gl.vertexAttribPointer(lk, 3, gl.FLOAT, false, 20, 8);
    gl.clearColor(0.2, 0.5, 0.8, 1.0); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  };
  const eq = (a, b) => { if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false; return true; };
  const R = {};
  const c = document.createElement('canvas'); c.width = 64; c.height = 64;
  const gl = c.getContext('webgl2', { preserveDrawingBuffer: true });
  if (!gl) return { err: 'no-webgl2' };
  scene(gl, 64, 64);
  const RGBA = gl.RGBA, UB = gl.UNSIGNED_BYTE, PPB = gl.PIXEL_PACK_BUFFER;
  // The page's pack buffer binding is part of the state the page left.
  const view = new Uint8Array(64 * 64 * 4); gl.readPixels(0, 0, 64, 64, RGBA, UB, view);
  const pb = gl.createBuffer(); gl.bindBuffer(PPB, pb); gl.bufferData(PPB, view.length, gl.STREAM_READ);
  gl.readPixels(0, 0, 64, 64, RGBA, UB, 0);
  const got = new Uint8Array(view.length); gl.getBufferSubData(PPB, 0, got);
  R.view = H(view); R.pbo = H(got); R.pboEqView = eq(got, view);
  R.bound = gl.getParameter(gl.PIXEL_PACK_BUFFER_BINDING) === pb;
  R.glerr = gl.getError();
  // PACK_ALIGNMENT 8, a 71 x 72 rect at (-8, -8) (8 px past the framebuffer on two sides), 16 bytes into the buffer.
  gl.pixelStorei(gl.PACK_ALIGNMENT, 8);
  const N = 16 + 72 * 288;
  const lay = new Uint8Array(N).fill(0xAB);
  gl.bindBuffer(PPB, null);    // a view read is INVALID_OPERATION while a pack buffer is bound
  gl.readPixels(-8, -8, 71, 72, RGBA, UB, lay, 16);
  gl.bindBuffer(PPB, pb);
  gl.bufferData(PPB, new Uint8Array(N).fill(0xAB), gl.STREAM_READ);
  gl.readPixels(-8, -8, 71, 72, RGBA, UB, 16);
  const lay2 = new Uint8Array(N); gl.getBufferSubData(PPB, 0, lay2);
  R.layEq = eq(lay, lay2); R.layPbo = H(lay2);
  R.layDiff = 0; R.layFirst = -1;
  for (let i = 0; i < N; i++) if (lay[i] !== lay2[i]) { if (R.layDiff++ === 0) R.layFirst = i; }
  // The rect's in-framebuffer part: rows 8..71, pixels 8..70 (63 of 71), 288-byte rows, from byte 16.
  const inRect = new Uint8Array(N);
  for (let r = 8; r < 72; r++) for (let i = 0; i < 252; i++) inRect[16 + r * 288 + 32 + i] = 1;
  R.outsideN = 0; R.outsideBad = 0;
  for (let i = 0; i < N; i++) if (!inRect[i]) { R.outsideN++; if (lay2[i] !== 0xAB) R.outsideBad++; }
  R.layBound = gl.getParameter(gl.PIXEL_PACK_BUFFER_BINDING) === pb; R.layGlerr = gl.getError();
  gl.bindBuffer(PPB, null);
  // A pack-buffer read from an RGBA8 texture framebuffer, against the view read of the same rect and layout.
  const fboRead = (w, x, y, rw) => {
    const g = document.createElement('canvas').getContext('webgl2');
    const tex = g.createTexture(); g.bindTexture(g.TEXTURE_2D, tex);
    g.texImage2D(g.TEXTURE_2D, 0, g.RGBA8, w, w, 0, g.RGBA, g.UNSIGNED_BYTE, null);
    const fb = g.createFramebuffer(); g.bindFramebuffer(g.FRAMEBUFFER, fb);
    g.framebufferTexture2D(g.FRAMEBUFFER, g.COLOR_ATTACHMENT0, g.TEXTURE_2D, tex, 0);
    g.viewport(0, 0, w, w); scene(g, w, w);
    const rl = w + 16;
    g.pixelStorei(g.PACK_ROW_LENGTH, rl); g.pixelStorei(g.PACK_SKIP_PIXELS, 3); g.pixelStorei(g.PACK_SKIP_ROWS, 2);
    const n = (2 * rl + 3) * 4 + (rw - 1) * rl * 4 + rw * 4;
    const v = new Uint8Array(n).fill(0xAB);
    g.readPixels(x, y, rw, rw, g.RGBA, g.UNSIGNED_BYTE, v);
    const b = g.createBuffer(); g.bindBuffer(g.PIXEL_PACK_BUFFER, b);
    g.bufferData(g.PIXEL_PACK_BUFFER, new Uint8Array(n).fill(0xAB), g.STREAM_READ);
    g.readPixels(x, y, rw, rw, g.RGBA, g.UNSIGNED_BYTE, 0);
    const p = new Uint8Array(n); g.getBufferSubData(g.PIXEL_PACK_BUFFER, 0, p);
    return { eq: eq(v, p), h: H(p), glerr: g.getError() };
  };
  R.fbo = [fboRead(64, 0, 0, 64), fboRead(600, 0, 0, 600), fboRead(600, 1, 1, 598)];
  // transferToImageBitmap, drawn to a 2D canvas and read, against drawImage(canvas) of the same scene.
  const dom = document.createElement('canvas'); dom.width = 64; dom.height = 64;
  scene(dom.getContext('webgl2', { preserveDrawingBuffer: true }), 64, 64);
  const read2d = (src) => { const c2 = document.createElement('canvas'); c2.width = 64; c2.height = 64;
    const x = c2.getContext('2d', { willReadFrequently: true }); x.drawImage(src, 0, 0);
    return H(x.getImageData(0, 0, 64, 64).data); };
  const oc = new OffscreenCanvas(64, 64); scene(oc.getContext('webgl2'), 64, 64);
  R.tibMain = read2d(oc.transferToImageBitmap()); R.drawMain = read2d(dom);
  // Report only: texImage2D of the transferred bitmap and of the canvas, each read back from a texture FBO.
  const viaTex = (src) => { try {
    const g = document.createElement('canvas').getContext('webgl2');
    const tex = g.createTexture(); g.bindTexture(g.TEXTURE_2D, tex);
    g.texImage2D(g.TEXTURE_2D, 0, g.RGBA, g.RGBA, g.UNSIGNED_BYTE, src);
    const fb = g.createFramebuffer(); g.bindFramebuffer(g.FRAMEBUFFER, fb);
    g.framebufferTexture2D(g.FRAMEBUFFER, g.COLOR_ATTACHMENT0, g.TEXTURE_2D, tex, 0);
    const v = new Uint8Array(64 * 64 * 4); g.readPixels(0, 0, 64, 64, g.RGBA, g.UNSIGNED_BYTE, v); return H(v);
  } catch (e) { return 'err:' + e.message; } };
  const oc3 = new OffscreenCanvas(64, 64); scene(oc3.getContext('webgl2'), 64, 64);
  R.texBitmap = viaTex(oc3.transferToImageBitmap()); R.texCanvas = viaTex(dom);
  const wsrc = `const H = ${H.toString()}; const scene = ${scene.toString()};
    onmessage = () => { const oc = new OffscreenCanvas(64, 64); const g = oc.getContext('webgl2');
      if (!g) { postMessage({ err: 'no-webgl2' }); return; }
      scene(g, 64, 64); const bmp = oc.transferToImageBitmap();
      const c2 = new OffscreenCanvas(64, 64); const x = c2.getContext('2d', { willReadFrequently: true });
      x.drawImage(bmp, 0, 0); postMessage({ tib: H(x.getImageData(0, 0, 64, 64).data) }); };`;
  R.tibWorker = await new Promise((resolve, reject) => {
    const w = new Worker(URL.createObjectURL(new Blob([wsrc], { type: 'text/javascript' })));
    w.onmessage = (e) => resolve(e.data.err ? { err: e.data.err } : e.data.tib);
    w.onerror = (e) => reject(new Error(e.message || 'worker error'));
    w.postMessage('go');
  });
  return R;
}"""


def leaks_rows():
    arms = {}
    for name, cfg in (("none", None), ("A", json.dumps({"canvas:seed": 1111})), ("B", json.dumps({"canvas:seed": 2222})),
                      ("A2", json.dumps({"canvas:seed": 1111}))):
        v, e = session(cfg, LEAKS, extra_flags=GL_ROW_FLAGS)
        if v is None or "err" in v:
            for row in (C70, C71, C72, C72B, C73, C74):
                results[row] = False
            notes.append(f"C70-C74: arm {name}: {e if v is None else v['err']}")
            return
        arms[name] = v

    def noised(key):    # seed A moves the none value, seed B moves A's, A again reproduces A
        return (arms["A"][key] != arms["none"][key] and arms["A"][key] != arms["B"][key]
                and arms["A"][key] == arms["A2"][key])

    # The read path that was already noised must have moved, or "A != none" below measures nothing.
    if not noised("view"):
        for row in (C70, C71, C72, C72B, C73, C74):
            mark_unmeasured(row, "readPixels(view) is not noised across the arms: the scene or the config does not reach the hook")
        return
    results[C70] = noised("pbo")
    results[C71] = all(a["pboEqView"] and a["bound"] and a["glerr"] == 0 for a in arms.values())
    results[C72] = (all(a["layEq"] and a["layBound"] and a["layGlerr"] == 0 for a in arms.values())
                    and all(a["outsideBad"] == 0 and a["outsideN"] > 2000 for a in arms.values()) and noised("layPbo"))
    results[C72B] = all(all(c["eq"] and c["glerr"] == 0 for c in a["fbo"]) for a in arms.values()) and all(
        arms["A"]["fbo"][i]["h"] != arms["none"]["fbo"][i]["h"] and arms["A"]["fbo"][i]["h"] != arms["B"]["fbo"][i]["h"]
        and arms["A"]["fbo"][i]["h"] == arms["A2"]["fbo"][i]["h"] for i in range(3))
    results[C73] = noised("tibMain") and all(a["tibMain"] == a["drawMain"] for a in arms.values())
    results[C74] = (noised("tibWorker") and all(a["tibWorker"] == a["drawMain"] for a in arms.values()))
    for arm, a in arms.items():
        notes.append(f"C70-C74 {arm}: view {a['view']} pbo {a['pbo']} lay {a['layPbo']} outside {a['outsideBad']}/{a['outsideN']} "
                     f"layEq {a['layEq']} layDiff {a['layDiff']} first {a['layFirst']} layBound {a['layBound']} layGlerr {a['layGlerr']} "
                     f"tibMain {a['tibMain']} drawMain {a['drawMain']} tibWorker {a['tibWorker']} "
                     f"fbo {[(c['eq'], c['h']) for c in a['fbo']]} texBitmap {a['texBitmap']} texCanvas {a['texCanvas']}")


leaks_rows()

# --- Lazy transferToImageBitmap noise (2026-11-19): C75-C83 ---
# C85/C86 run PrepareTransferableResource (a mutant that drops the image there fails both) but, on SwiftShader, the
# MakeAccelerated copy and the MakeUnaccelerated copy do not happen (the image is already CPU-side, so no copy
# loses the tag): their tag-keeping code has no RED here; it needs a real GPU host run.
# transferToImageBitmap does no readback: the bitmap is tagged, and every consumer that lets the page read its pixels
# asks for the noised ones (the field drawImage(webglCanvas) gives). One page function runs every consumer; the
# reference of each is the same read of the WebGL canvas itself, in the same arm.
C75 = "C75 drawImage(bitmap) to a willReadFrequently and to a default 2D canvas: noised, equal to drawImage(webglCanvas)"
C76 = "C76 createPattern(bitmap) fill: noised, equal to createPattern(webglCanvas)"
C77 = "C77 new VideoFrame(bitmap).copyTo: noised, equal to new VideoFrame(webglCanvas).copyTo"
C78 = "C78 createImageBitmap(bitmap) plain and cropped: noised, equal to drawImage(webglCanvas) / its crop"
C79 = "C79 postMessage(bitmap, [bitmap]) to a worker, drawImage there: noised, equal to drawImage(webglCanvas)"
C80 = "C80 postMessage(bitmap) (structured clone) to a worker, drawImage there: noised, equal to drawImage(webglCanvas)"
C81 = "C81 bitmaprenderer canvas holding the bitmap: toDataURL, toBlob, drawImage(canvas) noised, equal to the WebGL canvas's"
C82 = "C82 OffscreenCanvas bitmaprenderer holding the bitmap: convertToBlob noised, equal to the WebGL OffscreenCanvas's"
C84 = "C84 postMessage(bitmap, [bitmap]) while a second ImageBitmap shares the image (Transfer() must clone it): noised, equal to drawImage(webglCanvas)"
C83 = "C83 per-frame cost with a seed equals none (transferToImageBitmap 512 and 1080p, and transfer + transferFromImageBitmap display 1080p)"
LEAKS2 = """async () => {
  const H = (u8) => { let h = 2166136261;
    for (let i = 0; i < u8.length; i++) { h ^= u8[i]; h = Math.imul(h, 16777619) >>> 0; }
    return h.toString(16); };
  const scene = (gl, w, h) => {
    const sh = (type, src) => { const s = gl.createShader(type);
      gl.shaderSource(s, src); gl.compileShader(s); return s; };
    const pr = gl.createProgram();
    gl.attachShader(pr, sh(gl.VERTEX_SHADER,
      'attribute vec2 p;attribute vec3 k;varying vec3 v;varying vec2 q;void main(){v=k;q=p;gl_Position=vec4(p,0,1);}'));
    gl.attachShader(pr, sh(gl.FRAGMENT_SHADER,
      'precision mediump float;varying vec3 v;varying vec2 q;void main(){gl_FragColor=vec4(v*(0.75+0.25*sin(q.x*40.0+q.y*17.0)),1);}'));
    gl.linkProgram(pr); gl.useProgram(pr);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(
      [-0.9, -0.8, 1, 0, 0,  0.85, -0.6, 0, 1, 0,  -0.1, 0.9, 0, 0, 1]), gl.STATIC_DRAW);
    const lp = gl.getAttribLocation(pr, 'p'), lk = gl.getAttribLocation(pr, 'k');
    gl.enableVertexAttribArray(lp); gl.vertexAttribPointer(lp, 2, gl.FLOAT, false, 20, 0);
    gl.enableVertexAttribArray(lk); gl.vertexAttribPointer(lk, 3, gl.FLOAT, false, 20, 8);
    gl.clearColor(0.2, 0.5, 0.8, 1.0); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  };
  const Hs = (str) => H(new TextEncoder().encode(str));
  const R = {};
  const dom = document.createElement('canvas'); dom.width = 64; dom.height = 64;
  scene(dom.getContext('webgl2', { preserveDrawingBuffer: true }), 64, 64);
  const mkTib = () => { const oc = new OffscreenCanvas(64, 64); scene(oc.getContext('webgl2'), 64, 64);
    return oc.transferToImageBitmap(); };
  const c2d = (w, h, opts) => { const c = document.createElement('canvas'); c.width = w; c.height = h;
    return [c, c.getContext('2d', opts)]; };
  const read2d = (src, wrf) => { const [, x] = c2d(64, 64, wrf ? { willReadFrequently: true } : {});
    x.drawImage(src, 0, 0); return H(x.getImageData(0, 0, 64, 64).data); };
  R.ref = read2d(dom, true);
  R.drawWrf = read2d(mkTib(), true);
  R.drawGpu = read2d(mkTib(), false);
  const pat = (src) => { const [, x] = c2d(64, 64, { willReadFrequently: true });
    x.fillStyle = x.createPattern(src, 'no-repeat'); x.fillRect(0, 0, 64, 64);
    return H(x.getImageData(0, 0, 64, 64).data); };
  R.patBitmap = pat(mkTib()); R.patCanvas = pat(dom);
  const vf = async (src) => { try { const f = new VideoFrame(src, { timestamp: 0 });
    const b = new Uint8Array(f.allocationSize()); await f.copyTo(b); const fmt = f.format; f.close();
    return fmt + ':' + H(b); } catch (e) { return 'err:' + e.message; } };
  R.vfBitmap = await vf(mkTib()); R.vfCanvas = await vf(dom);
  R.cibPlain = read2d(await createImageBitmap(mkTib()), true);
  const crop = (src, sx) => { const [, x] = c2d(40, 40, { willReadFrequently: true });
    if (sx) x.drawImage(src, 8, 8, 40, 40, 0, 0, 40, 40); else x.drawImage(src, 0, 0);
    return H(x.getImageData(0, 0, 40, 40).data); };
  R.cibCrop = crop(await createImageBitmap(mkTib(), 8, 8, 40, 40), false); R.cropRef = crop(dom, true);
  const wsrc = `const H = ${H.toString()};
    onmessage = (e) => { const c = new OffscreenCanvas(64, 64); const x = c.getContext('2d', { willReadFrequently: true });
      x.drawImage(e.data, 0, 0); postMessage(H(x.getImageData(0, 0, 64, 64).data)); };`;
  const viaWorker = async (mode) => { const b = mkTib();
    // A second ImageBitmap on the same image: Transfer() cannot move it and must copy it (the clone fallback).
    const keep = mode === 'xferClone' ? await createImageBitmap(b) : null;
    const w = new Worker(URL.createObjectURL(new Blob([wsrc], { type: 'text/javascript' })));
    const r = new Promise((resolve, reject) => { w.onmessage = (e) => resolve(e.data);
      w.onerror = (e) => reject(new Error(e.message || 'worker error')); });
    if (mode === 'clone') w.postMessage(b); else w.postMessage(b, [b]);
    const out = await r; if (keep) keep.close(); return out; };
  R.xfer = await viaWorker('xfer'); R.clone = await viaWorker('clone'); R.xferClone = await viaWorker('xferClone');
  const br = () => { const c = document.createElement('canvas'); c.width = 64; c.height = 64;
    c.getContext('bitmaprenderer').transferFromImageBitmap(mkTib()); return c; };
  const blobHash = (c) => new Promise((res) => c.toBlob((b) => b.arrayBuffer().then((a) => res(H(new Uint8Array(a))))));
  R.brData = Hs(br().toDataURL()); R.refData = Hs(dom.toDataURL());
  R.brBlob = await blobHash(br()); R.refBlob = await blobHash(dom);
  R.brDraw = read2d(br(), true);
  const offBlob = async (oc) => H(new Uint8Array(await (await oc.convertToBlob()).arrayBuffer()));
  const ocw = new OffscreenCanvas(64, 64); scene(ocw.getContext('webgl2'), 64, 64); R.refOffBlob = await offBlob(ocw);
  const ocb = new OffscreenCanvas(64, 64); ocb.getContext('bitmaprenderer').transferFromImageBitmap(mkTib());
  R.brOffBlob = await offBlob(ocb);
  // cost per frame: the transfer alone (worker loop), and transfer + display on a bitmaprenderer canvas
  const csrc = `onmessage = (e) => { const [w, h, n] = e.data; const oc = new OffscreenCanvas(w, h); const gl = oc.getContext('webgl2');
    const t = []; for (let r = 0; r < 5; r++) { const a = performance.now();
      for (let i = 0; i < n; i++) { gl.clearColor(i / n, 0.5, 0.8, 1); gl.clear(gl.COLOR_BUFFER_BIT); oc.transferToImageBitmap().close(); }
      t.push((performance.now() - a) / n); }
    t.sort((a, b) => a - b); postMessage(t[2]); };`;
  const cost = (w, h) => new Promise((resolve) => { const wk = new Worker(URL.createObjectURL(new Blob([csrc])));
    wk.onmessage = (e) => resolve(+e.data.toFixed(4)); wk.postMessage([w, h, 20]); });
  R.cost512 = await cost(512, 512); R.cost1080 = await cost(1920, 1080);
  { const oc = new OffscreenCanvas(1920, 1080); const gl = oc.getContext('webgl2');
    const c = document.createElement('canvas'); c.width = 1920; c.height = 1080; const b = c.getContext('bitmaprenderer');
    const t = []; for (let r = 0; r < 5; r++) { const a = performance.now();
      for (let i = 0; i < 20; i++) { gl.clearColor(i / 20, 0.5, 0.8, 1); gl.clear(gl.COLOR_BUFFER_BIT); b.transferFromImageBitmap(oc.transferToImageBitmap()); }
      t.push((performance.now() - a) / 20); }
    t.sort((a, b2) => a - b2); R.costShow1080 = +t[2].toFixed(4); }
  return R;
}"""


def leaks2_rows():
    arms = {}
    for name, cfg in (("none", None), ("A", json.dumps({"canvas:seed": 1111})), ("B", json.dumps({"canvas:seed": 2222})),
                      ("A2", json.dumps({"canvas:seed": 1111}))):
        v, e = session(cfg, LEAKS2, extra_flags=GL_ROW_FLAGS)
        if v is None or "err" in v:
            for row in (C75, C76, C77, C78, C79, C80, C81, C82, C83, C84):
                results[row] = False
            notes.append(f"C75-C83: arm {name}: {e if v is None else v['err']}")
            return
        arms[name] = v

    def noised(key):    # seed A moves the none value, seed B moves A's, A again reproduces A
        return (arms["A"][key] != arms["none"][key] and arms["A"][key] != arms["B"][key]
                and arms["A"][key] == arms["A2"][key])

    def equals(key, ref):   # in every arm, the consumer's value is the WebGL canvas's own read
        return all(a[key] == a[ref] for a in arms.values())

    if not noised("ref"):
        for row in (C75, C76, C77, C78, C79, C80, C81, C82, C83, C84):
            mark_unmeasured(row, "drawImage(webglCanvas) is not noised across the arms: nothing to compare the bitmaps with")
        return
    results[C75] = noised("drawWrf") and equals("drawWrf", "ref") and noised("drawGpu") and equals("drawGpu", "ref")
    results[C76] = noised("patBitmap") and equals("patBitmap", "patCanvas")
    if any(a["vfBitmap"].startswith("err:") or a["vfCanvas"].startswith("err:") for a in arms.values()):
        mark_unmeasured(C77, f"VideoFrame unavailable: {arms['A']['vfBitmap']} / {arms['A']['vfCanvas']}")
    else:
        results[C77] = noised("vfBitmap") and equals("vfBitmap", "vfCanvas")
    results[C78] = noised("cibPlain") and equals("cibPlain", "ref") and noised("cibCrop") and equals("cibCrop", "cropRef")
    results[C79] = noised("xfer") and equals("xfer", "ref")
    results[C80] = noised("clone") and equals("clone", "ref")
    results[C84] = noised("xferClone") and equals("xferClone", "ref")
    results[C81] = (noised("brData") and equals("brData", "refData") and noised("brBlob") and equals("brBlob", "refBlob")
                    and noised("brDraw") and equals("brDraw", "ref"))
    results[C82] = noised("brOffBlob") and equals("brOffBlob", "refOffBlob")

    def cheap(key):     # a flag, not a readback: within noise of none (an eager readback was 2.4 and 18 ms)
        return all(arms[s][key] <= 2 * arms["none"][key] + 0.25 for s in ("A", "B", "A2"))

    results[C83] = cheap("cost512") and cheap("cost1080") and cheap("costShow1080")
    for arm, a in arms.items():
        notes.append(f"C75-C83 {arm}: ref {a['ref']} draw {a['drawWrf']}/{a['drawGpu']} pat {a['patBitmap']}/{a['patCanvas']} "
                     f"vf {a['vfBitmap']}/{a['vfCanvas']} cib {a['cibPlain']} crop {a['cibCrop']}/{a['cropRef']} "
                     f"xfer {a['xfer']}/{a['xferClone']} clone {a['clone']} br {a['brData']}/{a['refData']} {a['brBlob']}/{a['refBlob']} "
                     f"{a['brDraw']} off {a['brOffBlob']}/{a['refOffBlob']} "
                     f"cost {a['cost512']} {a['cost1080']} show {a['costShow1080']} ms")


leaks2_rows()

C85 = "C85 bitmaprenderer canvas in the document (the compositor asks for its resource): toDataURL and drawImage(canvas) noised, equal to the WebGL canvas's"
C86 = "C86 the same with --disable-gpu-compositing"
LEAKS3 = """async () => {
  const H = (u8) => { let h = 2166136261;
    for (let i = 0; i < u8.length; i++) { h ^= u8[i]; h = Math.imul(h, 16777619) >>> 0; }
    return h.toString(16); };
  const Hs = (str) => H(new TextEncoder().encode(str));
  const scene = (gl, w, h) => {
    const sh = (type, src) => { const s = gl.createShader(type);
      gl.shaderSource(s, src); gl.compileShader(s); return s; };
    const pr = gl.createProgram();
    gl.attachShader(pr, sh(gl.VERTEX_SHADER,
      'attribute vec2 p;attribute vec3 k;varying vec3 v;varying vec2 q;void main(){v=k;q=p;gl_Position=vec4(p,0,1);}'));
    gl.attachShader(pr, sh(gl.FRAGMENT_SHADER,
      'precision mediump float;varying vec3 v;varying vec2 q;void main(){gl_FragColor=vec4(v*(0.75+0.25*sin(q.x*40.0+q.y*17.0)),1);}'));
    gl.linkProgram(pr); gl.useProgram(pr);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(
      [-0.9, -0.8, 1, 0, 0,  0.85, -0.6, 0, 1, 0,  -0.1, 0.9, 0, 0, 1]), gl.STATIC_DRAW);
    const lp = gl.getAttribLocation(pr, 'p'), lk = gl.getAttribLocation(pr, 'k');
    gl.enableVertexAttribArray(lp); gl.vertexAttribPointer(lp, 2, gl.FLOAT, false, 20, 0);
    gl.enableVertexAttribArray(lk); gl.vertexAttribPointer(lk, 3, gl.FLOAT, false, 20, 8);
    gl.clearColor(0.2, 0.5, 0.8, 1.0); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  };
  const R = {};
  const dom = document.createElement('canvas'); dom.width = 64; dom.height = 64;
  scene(dom.getContext('webgl2', { preserveDrawingBuffer: true }), 64, 64);
  const mkTib = () => { const oc = new OffscreenCanvas(64, 64); scene(oc.getContext('webgl2'), 64, 64);
    return oc.transferToImageBitmap(); };
  const read2d = (src) => { const c = document.createElement('canvas'); c.width = 64; c.height = 64;
    const x = c.getContext('2d', { willReadFrequently: true }); x.drawImage(src, 0, 0);
    return H(x.getImageData(0, 0, 64, 64).data); };
  R.ref = read2d(dom); R.refData = Hs(dom.toDataURL());
  // In the document, so the compositor asks the context for its resource (PrepareTransferableResource).
  const c = document.createElement('canvas'); c.width = 64; c.height = 64;
  c.style.cssText = 'position:fixed;left:0;top:0'; document.body.appendChild(c);
  c.getContext('bitmaprenderer').transferFromImageBitmap(mkTib());
  const frame = () => new Promise((r) => { requestAnimationFrame(() => r()); setTimeout(r, 300); });
  for (let i = 0; i < 6; i++) await frame();
  await new Promise((r) => setTimeout(r, 300));
  R.brData = Hs(c.toDataURL()); R.brDraw = read2d(c);
  return R;
}"""


def composited_row(row, flags, label):
    arms = {}
    for name, cfg in (("none", None), ("A", json.dumps({"canvas:seed": 1111})), ("B", json.dumps({"canvas:seed": 2222})),
                      ("A2", json.dumps({"canvas:seed": 1111}))):
        v, e = session(cfg, LEAKS3, extra_flags=flags)
        if v is None or "err" in v:
            results[row] = False
            notes.append(f"{row[:3]}: arm {name}: {e if v is None else v['err']}")
            return
        arms[name] = v

    def noised(key):
        return (arms["A"][key] != arms["none"][key] and arms["A"][key] != arms["B"][key]
                and arms["A"][key] == arms["A2"][key])

    ok = (noised("brData") and noised("brDraw") and all(a["brData"] == a["refData"] and a["brDraw"] == a["ref"] for a in arms.values()))
    results[row] = ok
    notes.append(f"{row[:3]} {label}: " + " | ".join(f"{k} ref {a['ref']} draw {a['brDraw']} data {a['brData']}/{a['refData']}"
                                                  for k, a in arms.items()))


composited_row(C85, GL_ROW_FLAGS, "gpu compositing")
composited_row(C86, GL_ROW_FLAGS + ["--disable-gpu-compositing"], "software compositing")

# Report only (no row): paths a reviewer flagged as possibly unnoised on a real GPU, measured here on SwiftShader.
LEAKS4 = """async () => {
  const H = (u8) => { let h = 2166136261;
    for (let i = 0; i < u8.length; i++) { h ^= u8[i]; h = Math.imul(h, 16777619) >>> 0; }
    return h.toString(16); };
  const Hs = (str) => H(new TextEncoder().encode(str));
  const scene = (gl, w, h) => {
    const sh = (type, src) => { const s = gl.createShader(type);
      gl.shaderSource(s, src); gl.compileShader(s); return s; };
    const pr = gl.createProgram();
    gl.attachShader(pr, sh(gl.VERTEX_SHADER,
      'attribute vec2 p;attribute vec3 k;varying vec3 v;varying vec2 q;void main(){v=k;q=p;gl_Position=vec4(p,0,1);}'));
    gl.attachShader(pr, sh(gl.FRAGMENT_SHADER,
      'precision mediump float;varying vec3 v;varying vec2 q;void main(){gl_FragColor=vec4(v*(0.75+0.25*sin(q.x*40.0+q.y*17.0)),1);}'));
    gl.linkProgram(pr); gl.useProgram(pr);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(
      [-0.9, -0.8, 1, 0, 0,  0.85, -0.6, 0, 1, 0,  -0.1, 0.9, 0, 0, 1]), gl.STATIC_DRAW);
    const lp = gl.getAttribLocation(pr, 'p'), lk = gl.getAttribLocation(pr, 'k');
    gl.enableVertexAttribArray(lp); gl.vertexAttribPointer(lp, 2, gl.FLOAT, false, 20, 0);
    gl.enableVertexAttribArray(lk); gl.vertexAttribPointer(lk, 3, gl.FLOAT, false, 20, 8);
    gl.clearColor(0.2, 0.5, 0.8, 1.0); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  };
  const R = {};
  const read2d = (src) => { const c = document.createElement('canvas'); c.width = 64; c.height = 64;
    const x = c.getContext('2d', { willReadFrequently: true }); x.drawImage(src, 0, 0);
    return H(x.getImageData(0, 0, 64, 64).data); };
  const dom = document.createElement('canvas'); dom.width = 64; dom.height = 64;
  scene(dom.getContext('webgl2', { preserveDrawingBuffer: true }), 64, 64);
  R.ref = read2d(dom);
  // captureStream of a WebGL canvas, read back through a <video>
  try { const c = document.createElement('canvas'); c.width = 64; c.height = 64;
    const gl = c.getContext('webgl2', { preserveDrawingBuffer: true }); scene(gl, 64, 64);
    const v = document.createElement('video'); v.muted = true; v.srcObject = c.captureStream(30);
    await v.play().catch(() => {});
    let n = 0;
    await new Promise((res) => { const cb = () => { if (++n >= 5) return res(); scene(gl, 64, 64); v.requestVideoFrameCallback(cb); };
      scene(gl, 64, 64); v.requestVideoFrameCallback(cb); setTimeout(res, 5000); });
    R.cap = read2d(v) + ' frames ' + n + ' ' + v.videoWidth + 'x' + v.videoHeight;
  } catch (e) { R.cap = 'err:' + e.message; }
  // transferControlToOffscreen: the worker renders, the main thread reads the placeholder canvas
  try { const c = document.createElement('canvas'); c.width = 64; c.height = 64; document.body.appendChild(c);
    const off = c.transferControlToOffscreen();
    const w = new Worker(URL.createObjectURL(new Blob([`const scene = ${scene.toString()};
      onmessage = (e) => { scene(e.data.getContext('webgl2'), 64, 64); postMessage('drawn'); };`])));
    await new Promise((res) => { w.onmessage = res; w.postMessage(off, [off]); });
    for (let i = 0; i < 6; i++) await new Promise((r) => { requestAnimationFrame(() => r()); setTimeout(r, 300); });
    R.phUrl = 'n/a'; R.phDraw = 'n/a';
    try { R.phUrl = Hs(c.toDataURL()); } catch (e) { R.phUrl = 'err:' + e.message; }
    try { R.phDraw = read2d(c); } catch (e) { R.phDraw = 'err:' + e.message; }
  } catch (e) { R.phUrl = 'err:' + e.message; R.phDraw = R.phUrl; }
  return R;
}"""


def report_only():
    for label, flags in (("default", GL_ROW_FLAGS), ("OneCopyCanvasCapture", GL_ROW_FLAGS + ["--enable-features=OneCopyCanvasCapture"])):
        row = []
        for name, cfg in (("none", None), ("A", json.dumps({"canvas:seed": 1111})), ("B", json.dumps({"canvas:seed": 2222}))):
            v, e = session(cfg, LEAKS4, extra_flags=flags)
            row.append(f"{name}: " + (f"ERR {e}" if v is None else f"ref {v['ref']} captureStream {v['cap']} "
                                      f"placeholder toDataURL {v['phUrl']} drawImage {v['phDraw']}"))
        notes.append(f"REPORT-ONLY (no row) [{label}]: " + " | ".join(row))


report_only()

# --- transferControlToOffscreen placeholder noise (2026-11-19): C87-C93 ---
# A worker renders into a canvas the main thread transferred control of; the page reads the placeholder canvas on the main
# thread. The worker commits its frames with a noise record; the main thread noises the frame when the page reads it, as the
# worker's own context would (convertToBlob). A 2D worker and a WebGL worker, in every row.
C87 = "C87 placeholder toBlob and toDataURL equal the worker's own convertToBlob, 2D and WebGL workers: noised (A != none, A != B, A == A again)"
C88 = "C88 drawImage(placeholder) to 2D, getImageData: noised, equal to the same read of a main-thread canvas with the same scene"
C89 = "C89 createImageBitmap(placeholder), drawImage, getImageData: noised, equal to the main-thread canvas's read"
C90 = "C90 captureStream(placeholder) to a video, drawImage, getImageData: noised, equal to the main-thread canvas's read"
C91 = ("C91 two frames on a 64 x 256 canvas, the second frame's imported patch in another mask chunk than the first's: the second read is "
       "the second frame's noise (neither a per-frame cache nor a shared mask chunk is stale)")
C92 = ("C92 a worker bitmaprenderer on the placeholder (WebGL -> transferToImageBitmap -> transferFromImageBitmap): toBlob, toDataURL and "
       "drawImage noised, equal to the worker's own read")
C93 = ("C93 worker frame period with a seed within max(3 % + 0.5 ms, 1.5 x the none runs' own spread) of none (median of 3), per case: 2D static, 2D moving, 2D heavy (120 paths + 20 text "
       "lines per frame), WebGL, at 512 and 1080p (vsync limit off, one commit per frame counted from the trace)")
C94 = ("C94 mean OffscreenCanvas::PushFrame per commit under a blink trace, seed within 0.5 ms of none (median of 3 alternating runs), "
       "2D moving at 1080p and 2D heavy at 512 (120 paths + 20 text lines per frame), and the seeded 2D frames carry their mask unapplied "
       "(CamouFrameNoise defer=deferred is traced): a commit no longer walks the worker's recordings")
C95 = ("C95 heavy 2D worker (120 paths + 20 text lines per rAF frame, 12 frames, read, then 20 frames, read, then one frame of 8 heavy scenes applied by the idle walk and a tiny frame on top, read): "
       "the placeholder's toBlob, toDataURL, drawImage equal the worker's own convertToBlob after each, noised (A != none, A != B, A == A again); the second read is past the queue's 16-job cap, so the oldest "
       "unwalked recordings were merged (or parked) on both sides alike (traced: a committed frame carried 16 and at least one recording was merged or shed)")
C96 = ("C96 re-read: a heavy 2D worker draws only the top half in 20 rAF frames, then only the bottom half in 40 more without ever idling or reading; the page reads "
       "after the first 20 (the worker has already merged some of their recordings) and again after the 40: the top rows of the "
       "second read equal the first's, and the worker's own read of them (noised: A != none, A != B, A == A again); the trace shows the cap crossed "
       "(recordings merged, or parked and then walked) and a signal received")
C97 = ("C97 the same reads as C87-C89 and C91 (toBlob, toDataURL, drawImage, createImageBitmap, the second frame) on a 2D scene with no drawn image, so its recordings "
       "can be carried unapplied: equal to the worker's own read and to a main-thread canvas, noised (A != none, A != B, A == A again); the trace shows frames "
       "committed deferred")
C99 = ("C99 (no crash, same noise; the trace is not asserted to show the signal undelivered: a terminating worker may still run its last tasks) a read whose signal "
       "outlives its worker: the page reads, the worker is terminated at once, the page reads again (the placeholder keeps its last frame: the same noise), the canvas leaves "
       "the page and a second canvas and worker do the same; and with no seed a run emits no frame-noise, signal, parking or replay trace event at all (nothing is recorded, "
       "posted or parked)")
C98 = ("C98 captureStream(placeholder) of a busy heavy 2D worker: the main thread's replays of consecutive frames continue the last one's walk (>= half 'continue'), "
       "and its per-frame cost, seed vs none, is reported")
SOFT_ROWS = SOFT_ROWS + (C90, C93, C94, C98)
PH_SCENES = """
  const scene2d = (c, v) => { const x = c.getContext('2d'); const g = x.createLinearGradient(0, 0, c.width, c.height);
    g.addColorStop(0, v ? '#1f6' : '#f60'); g.addColorStop(1, v ? '#f16' : '#16f'); x.fillStyle = g; x.fillRect(0, 0, c.width, c.height);
    x.fillStyle = 'rgba(255,255,255,0.6)'; x.beginPath(); x.arc(c.width / 2 + (v ? 9 : 0), c.height / 2, c.width * 0.3, 0, 7); x.fill();
    // an imported patch of noisy pixels, in a different 64-row mask chunk in each frame: the mask must keep the noise off it, and
    // it changes from one frame to the next (a stale mask or a shared stale chunk would noise the second frame's patch)
    const patch = new OffscreenCanvas(16, 16); const px = patch.getContext('2d');
    for (let i = 0; i < 256; i++) { const h = Math.imul(i + 1, 2654435761) >>> 0;
      px.fillStyle = 'rgb(' + (h & 255) + ',' + ((h >> 8) & 255) + ',' + ((h >> 16) & 255) + ')'; px.fillRect(i % 16, (i / 16) | 0, 1, 1); }
    x.drawImage(patch, v ? 8 : 40, v ? 200 : 40); };
  const sceneGl = (c, v) => { const gl = c.getContext('webgl2', { preserveDrawingBuffer: true });
    const sh = (t, s) => { const o = gl.createShader(t); gl.shaderSource(o, s); gl.compileShader(o); return o; };
    const pr = gl.createProgram();
    gl.attachShader(pr, sh(gl.VERTEX_SHADER, 'attribute vec2 p;attribute vec3 k;varying vec3 v;varying vec2 q;void main(){v=k;q=p;gl_Position=vec4(p,0,1);}'));
    gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, 'precision mediump float;varying vec3 v;varying vec2 q;void main(){gl_FragColor=vec4(v*(0.75+0.25*sin(q.x*40.0+q.y*17.0)),1);}'));
    gl.linkProgram(pr); gl.useProgram(pr); gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    const o = v ? 0.15 : 0;
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-0.9 + o, -0.8, 1, 0, 0, 0.85, -0.6, 0, 1, 0, -0.1, 0.9 - o, 0, 0, 1]), gl.STATIC_DRAW);
    const lp = gl.getAttribLocation(pr, 'p'), lk = gl.getAttribLocation(pr, 'k');
    gl.enableVertexAttribArray(lp); gl.vertexAttribPointer(lp, 2, gl.FLOAT, false, 20, 0);
    gl.enableVertexAttribArray(lk); gl.vertexAttribPointer(lk, 3, gl.FLOAT, false, 20, 8);
    gl.clearColor(0.2, 0.5, 0.8, 1); gl.clear(gl.COLOR_BUFFER_BIT); gl.drawArrays(gl.TRIANGLES, 0, 3); };
"""
# the same scene without the drawn patch: a drawn image makes the context apply its queue at once, so no frame of it carries recordings
# unapplied. An aa ellipse stroke in a different mask chunk in each frame takes the patch's place.
_cut_a = PH_SCENES.index("    // an imported patch")
_cut_b = PH_SCENES.index("x.drawImage(patch, v ? 8 : 40, v ? 200 : 40); };") + len("x.drawImage(patch, v ? 8 : 40, v ? 200 : 40); };")
# the patch as 256 one-pixel opaque fillRects (a solid draw clears the cells it covers: the mask keeps noise off them, as it did off the
# drawn patch) plus an aa ellipse stroke: a replay that is skipped or wrong noises the patch, which the scene's own gradient edges do not show
PH_SCENES_DEFERRED = (PH_SCENES[:_cut_a] +
                      "    for (let i = 0; i < 256; i++) { const h = Math.imul(i + 1, 2654435761) >>> 0;\n"
                      "      x.fillStyle = 'rgb(' + (h & 255) + ',' + ((h >> 8) & 255) + ',' + ((h >> 16) & 255) + ')';\n"
                      "      x.fillRect((v ? 8 : 40) + i % 16, (v ? 200 : 40) + ((i / 16) | 0), 1, 1); }\n"
                      "    x.strokeStyle = 'rgba(0,0,0,0.7)'; x.lineWidth = 3; x.beginPath(); x.ellipse(c.width / 2, v ? 120 : 160, 20, 12, 0, 0, 7); x.stroke(); };" +
                      PH_SCENES[_cut_b:])
assert PH_SCENES_DEFERRED != PH_SCENES and "drawImage(patch" not in PH_SCENES_DEFERRED
LEAKS6 = """async () => {
  const H = (u8) => { let h = 2166136261;
    for (let i = 0; i < u8.length; i++) { h ^= u8[i]; h = Math.imul(h, 16777619) >>> 0; }
    return h.toString(16); };
  const Hs = (s) => H(new TextEncoder().encode(s));
  const W = 64, HT = 256;
  __SCENES__
  const wsrc = `const scene2d = ${scene2d.toString()}; const sceneGl = ${sceneGl.toString()};
    let off = null;
    onmessage = async (e) => { const [kind, v, o] = e.data;
      if (o) off = o;
      const draw = kind === '2d' ? scene2d : sceneGl;
      // the worker's own noised read of the canvas it renders into, as it is right now
      if (kind === 'cur') { postMessage(await (await off.convertToBlob()).arrayBuffer()); return; }
      if (kind === 'ref2d' || kind === 'refgl') { const c = new OffscreenCanvas(${W}, ${HT}); (kind === 'ref2d' ? scene2d : sceneGl)(c, v);
        postMessage(await (await c.convertToBlob()).arrayBuffer()); return; }
      draw(off, v); postMessage('drawn'); };`;
  const url = URL.createObjectURL(new Blob([wsrc]));
  const call = (w, msg, tr) => new Promise((r) => { w.onmessage = (e) => r(e.data); w.postMessage(msg, tr || []); });
  const frames = async (n) => { for (let i = 0; i < n; i++) await new Promise((r) => { requestAnimationFrame(() => r()); setTimeout(r, 250); }); };
  const b64 = (u8) => { let s = ''; for (let i = 0; i < u8.length; i++) s += String.fromCharCode(u8[i]); return btoa(s); };
  const read2d = (src) => { const d = document.createElement('canvas'); d.width = W; d.height = HT;
    const x = d.getContext('2d', { willReadFrequently: true }); x.drawImage(src, 0, 0); return H(x.getImageData(0, 0, W, HT).data); };
  const R = {};
  self.__p = [];
  for (const kind of ['2d', 'gl']) {
    const w = new Worker(url);
    self.__p.push(kind + ' start');
    const refBytes = new Uint8Array(await call(w, ['ref' + kind, 0]));
    const c = document.createElement('canvas'); c.width = W; c.height = HT; document.body.appendChild(c);
    const off = c.transferControlToOffscreen();
    self.__p.push(kind + ' refs');
    await call(w, [kind, 0, off], [off]);
    self.__p.push(kind + ' drawn');
    await frames(8);
    self.__p.push(kind + ' frames');
    const blobBytes = async () => new Uint8Array(await (await new Promise((r) => c.toBlob(r))).arrayBuffer());
    const r = {};
    r.blob = H(await blobBytes()); r.refBlob = H(refBytes);
    r.cur = H(new Uint8Array(await call(w, ['cur', 0])));
    self.__p.push(kind + ' blob');
    r.url = Hs(c.toDataURL()); r.refUrl = Hs('data:image/png;base64,' + b64(refBytes));
    // the same scene on a main-thread canvas: the reference of the reads that go through a 2D canvas
    const m = document.createElement('canvas'); m.width = W; m.height = HT; (kind === '2d' ? scene2d : sceneGl)(m, 0);
    r.draw = read2d(c); r.refDraw = read2d(m);
    self.__p.push(kind + ' draw');
    r.cib = read2d(await createImageBitmap(c));
    self.__p.push(kind + ' cib');
    try { const v = document.createElement('video'); v.muted = true; v.srcObject = c.captureStream(30); v.play().catch(() => {});
      // the stream only carries frames the worker commits after it started: keep redrawing scene 0 until one arrives
      let n = 0; const cb = () => { n++; v.requestVideoFrameCallback(cb); }; v.requestVideoFrameCallback(cb);
      for (let i = 0; i < 6 && n < 2; i++) { await call(w, [kind, 0]); await frames(3); }
      r.cap = n ? read2d(v) : 'noframe'; } catch (e) { r.cap = 'err:' + e.message; }
    self.__p.push(kind + ' cap');
    // a second frame, whose patch is in another mask chunk; the worker's own read of the same canvas now (the history of its
    // mask, frame 1's patch stays marked, is part of it)
    const before = r.blob;
    await call(w, [kind, 1]); await frames(8);
    r.blob2 = H(await blobBytes()); r.refBlob2 = H(new Uint8Array(await call(w, ['cur', 0]))); r.before = before;
    R[kind] = r; w.terminate();
  }
  return R;
}""".replace("__SCENES__", PH_SCENES)
LEAKS6_DEFERRED = LEAKS6.replace(PH_SCENES, PH_SCENES_DEFERRED)
assert LEAKS6_DEFERRED != LEAKS6
# a worker bitmaprenderer on the placeholder: the frames it commits are copies of a WebGL transfer
LEAKS8 = """async () => {
  const H = (u8) => { let h = 2166136261;
    for (let i = 0; i < u8.length; i++) { h ^= u8[i]; h = Math.imul(h, 16777619) >>> 0; }
    return h.toString(16); };
  const Hs = (s) => H(new TextEncoder().encode(s));
  const W = 64, HT = 256;
  __SCENES__
  const wsrc = `const sceneGl = ${sceneGl.toString()};
    let off = null;
    onmessage = async (e) => { const [kind, o] = e.data; if (o) off = o;
      if (kind === 'cur') { postMessage(await (await off.convertToBlob()).arrayBuffer()); return; }
      const oc = new OffscreenCanvas(${W}, ${HT}); sceneGl(oc, 0);
      off.getContext('bitmaprenderer').transferFromImageBitmap(oc.transferToImageBitmap()); postMessage('drawn'); };`;
  const w = new Worker(URL.createObjectURL(new Blob([wsrc])));
  const call = (msg, tr) => new Promise((r) => { w.onmessage = (e) => r(e.data); w.postMessage(msg, tr || []); });
  const frames = async (n) => { for (let i = 0; i < n; i++) await new Promise((r) => { requestAnimationFrame(() => r()); setTimeout(r, 250); }); };
  const read2d = (src) => { const d = document.createElement('canvas'); d.width = W; d.height = HT;
    const x = d.getContext('2d', { willReadFrequently: true }); x.drawImage(src, 0, 0); return H(x.getImageData(0, 0, W, HT).data); };
  const c = document.createElement('canvas'); c.width = W; c.height = HT; document.body.appendChild(c);
  const off = c.transferControlToOffscreen();
  await call(['br', off], [off]); await frames(8);
  const R = {};
  R.blob = H(new Uint8Array(await (await new Promise((r) => c.toBlob(r))).arrayBuffer()));
  R.cur = H(new Uint8Array(await call(['cur'])));
  R.url = Hs(c.toDataURL());
  const m = document.createElement('canvas'); m.width = W; m.height = HT; sceneGl(m, 0);
  R.draw = read2d(c); R.refDraw = read2d(m);
  w.terminate();
  return R;
}""".replace("__SCENES__", PH_SCENES)
# the heavy 2D scene: 120 filled and stroked paths and 20 text lines per frame, on a canvas that is drawn into again every frame
HEAVY2D = """const heavy2d = (c, n) => { const x = c.getContext('2d'); if (n === 0) { x.fillStyle = '#16f'; x.fillRect(0, 0, c.width, c.height); }
        x.font = '14px sans-serif';
        for (let i = 0; i < 120; i++) { const px = (n * 7 + i * 37) % c.width, py = (n * 5 + i * 53) % c.height;
          x.beginPath(); x.moveTo(px, py); x.bezierCurveTo(px + 30, py - 20, px + 50, py + 40, px + 80, py + 10); x.lineTo(px + 40, py + 60); x.closePath();
          x.fillStyle = 'rgba(' + ((i * 11) % 255) + ',' + ((i * 23) % 255) + ',' + ((i * 47) % 255) + ',0.6)'; x.fill();
          x.strokeStyle = '#fff'; x.lineWidth = 2; x.stroke(); }
        for (let i = 0; i < 20; i++) x.fillText('camoucrome ' + i + ' ' + n, (n * 3 + i * 91) % c.width, (i * 41 + n) % c.height + 14); };"""
# the cost cases: [kind, w, h]; each runs 120 rAF frames in a worker that draws into a transferred canvas
COST_WORKER = """const scene2d = ${scene2d.toString()}; const sceneGl = ${sceneGl.toString()};
      const move2d = (c, n) => { const x = c.getContext('2d'); if (n === 0) { x.fillStyle = '#16f'; x.fillRect(0, 0, c.width, c.height); }
        const g = x.createRadialGradient(0, 0, 0, 0, 0, 40); g.addColorStop(0, '#fff'); g.addColorStop(1, '#f60');
        x.save(); x.translate((n * 53) % c.width, (n * 29) % c.height); x.fillStyle = g; x.beginPath(); x.arc(0, 0, 40, 0, 7); x.fill(); x.restore(); };
      __HEAVY__
      onmessage = async (e) => { const [kind, off] = e.data;
        const draw = kind === 'gl' ? (c, n) => sceneGl(c, 0) : kind === '2d-move' ? move2d : kind === '2d-heavy' ? heavy2d
          : (c, n) => { if (n === 0) scene2d(c, 0); else c.getContext('2d').fillRect(0, 0, 1, 1); };
        const ts = []; await new Promise((res) => { let n = 0, last = performance.now();
          const f = (now) => { ts.push(now - last); last = now; draw(off, n); if (++n < 120) requestAnimationFrame(f); else res(); };
          requestAnimationFrame(f); });
        const med = (a) => a.slice().sort((p, q) => p - q)[a.length >> 1];
        postMessage({ lap1: med(ts.slice(1, 60)), lap2: med(ts.slice(60)), n: ts.length }); };"""


def cost_js(cases):
    return """async () => {
  __SCENES__
  const R = {};
  const frames = async (n) => { for (let i = 0; i < n; i++) await new Promise((r) => { requestAnimationFrame(() => r()); setTimeout(r, 100); }); };
  for (const [kind, w, h] of __CASES__) {
    const wsrc = `__WORKER__`;
    const worker = new Worker(URL.createObjectURL(new Blob([wsrc])));
    const c = document.createElement('canvas'); c.width = w; c.height = h; document.body.appendChild(c);
    const off = c.transferControlToOffscreen();
    R[kind + '-' + w] = await new Promise((res) => { worker.onmessage = (e) => res({ lap1: +e.data.lap1.toFixed(2), lap2: +e.data.lap2.toFixed(2), n: e.data.n });
      worker.postMessage([kind, off], [off]); });
    worker.terminate(); c.remove(); await frames(2);
  }
  return R;
}""".replace("__SCENES__", PH_SCENES).replace("__WORKER__", COST_WORKER.replace("__HEAVY__", HEAVY2D)).replace("__CASES__", json.dumps(cases))


COST_CASES = [[k, w, h] for k in ("2d-static", "2d-move", "2d-heavy", "gl") for (w, h) in ((512, 512), (1920, 1080))]


def traced(config, js, flags):
    """One session under a blink trace: (the page's value, the number of OffscreenCanvas::PushFrame events)."""
    value, events = traced_events(config, js, flags)
    if value is None:
        return None, events
    return value, sum(1 for ev in events if ev.get("name") == "OffscreenCanvas::PushFrame" and ev.get("ph") in ("X", "B"))


def traced_events(config, js, flags):
    """One session under a blink trace: (the page's value, every trace event); (None, the exception) when the session fails."""
    import threading
    proc = conn = None
    try:
        proc, conn = lib_shell.launch_and_prime(
            lambda: lib_shell.launch(config, extra_flags=flags),
            lambda p: lib_shell.attach(p, lambda page: page.goto("about:blank", wait_until="load")))
        page = conn.page
        cdp = conn.context.browser.new_browser_cdp_session()
        events, done = [], threading.Event()
        cdp.on("Tracing.dataCollected", lambda e: events.extend(e["value"]))
        cdp.on("Tracing.tracingComplete", lambda e: done.set())
        cdp.send("Tracing.start", {"categories": "blink", "transferMode": "ReportEvents"})
        value = page.evaluate(js)
        cdp.send("Tracing.end")
        for _ in range(100):
            if done.is_set():
                break
            page.wait_for_timeout(100)
        return value, events
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc
    finally:
        if conn is not None:
            conn.close()
        if proc is not None:
            lib_shell.shutdown(proc)


def placeholder_rows():
    arms = {}
    arms8 = {}
    for name, cfg in (("none", None), ("A", json.dumps({"canvas:seed": 1111})), ("B", json.dumps({"canvas:seed": 2222})),
                      ("A2", json.dumps({"canvas:seed": 1111}))):
        v, e = session(cfg, LEAKS6, extra_flags=GL_ROW_FLAGS)
        if v is None or "err" in v:
            for row in (C87, C88, C89, C91):
                results[row] = False
            soft[C90] = False
            notes.append(f"C87-C91: arm {name}: {e if v is None else v['err']}")
            return
        arms[name] = v
        v8, e8 = session(cfg, LEAKS8, extra_flags=GL_ROW_FLAGS)
        if v8 is None or "err" in v8:
            results[C92] = False
            notes.append(f"C92: arm {name}: {e8 if v8 is None else v8['err']}")
        else:
            arms8[name] = v8

    def noised(kind, key):
        return (arms["A"][kind][key] != arms["none"][kind][key] and arms["A"][kind][key] != arms["B"][kind][key]
                and arms["A"][kind][key] == arms["A2"][kind][key])

    def equals(key, ref):
        return all(a[k][key] == a[k][ref] for a in arms.values() for k in ("2d", "gl"))

    kinds = ("2d", "gl")
    results[C87] = (all(noised(k, "blob") and noised(k, "url") for k in kinds) and equals("blob", "refBlob")
                    and equals("blob", "cur") and equals("url", "refUrl"))
    results[C88] = all(noised(k, "draw") for k in kinds) and equals("draw", "refDraw")
    results[C89] = all(noised(k, "cib") for k in kinds) and equals("cib", "refDraw")
    results[C91] = (equals("blob2", "refBlob2") and all(arms[a][k]["blob2"] != arms[a][k]["blob"] for a in ("A", "B") for k in kinds)
                    and all(noised(k, "blob2") for k in kinds))
    if len(arms8) == 4:
        def noised8(key):
            return (arms8["A"][key] != arms8["none"][key] and arms8["A"][key] != arms8["B"][key]
                    and arms8["A"][key] == arms8["A2"][key])
        results[C92] = (noised8("blob") and noised8("url") and noised8("draw")
                        and all(a["blob"] == a["cur"] and a["draw"] == a["refDraw"] for a in arms8.values()))
        for name, a in arms8.items():
            notes.append(f"C92 {name}: blob {a['blob']}/{a['cur']} url {a['url']} draw {a['draw']}/{a['refDraw']}")
    capframes = [arms[a][k]["cap"] for a in arms for k in kinds]
    if any(str(x).startswith(("noframe", "err")) for x in capframes):
        mark_unmeasured(C90, f"no video frame from captureStream(placeholder): {sorted(set(map(str, capframes)))[:3]}")
    else:
        soft[C90] = all(noised(k, "cap") for k in kinds) and equals("cap", "refDraw")
    for name, a in arms.items():
        notes.append(f"C87-C91 {name}: " + " | ".join(
            f"{k}: blob {a[k]['blob']}/{a[k]['refBlob']}/{a[k]['cur']} url {a[k]['url']}/{a[k]['refUrl']} draw {a[k]['draw']}/{a[k]['refDraw']} "
            f"cib {a[k]['cib']} cap {a[k]['cap']} blob2 {a[k]['blob2']}/{a[k]['refBlob2']}" for k in kinds))
    if os.environ.get("CAMOU_SP3A_NO_COST") == "1":    # a host busy with a build: no timing is worth taking
        mark_unmeasured(C93, "CAMOU_SP3A_NO_COST=1")
        return
    # cost: the worker's frame period, vsync limit off so the push cost is not hidden behind the 16.7 ms tick
    # three alternating runs per arm and the median per case: one run of a heavy scene moves by a millisecond or two on its own
    runs = {"none": [], "A": []}
    flags = GL_ROW_FLAGS + ["--disable-frame-rate-limit", "--disable-gpu-vsync"]
    for _ in range(3):
        for name, cfg in (("none", None), ("A", json.dumps({"canvas:seed": 1111}))):
            v, e = session(cfg, cost_js(COST_CASES), extra_flags=flags)
            if v is None or "err" in v:
                mark_unmeasured(C93, f"cost session {name}: {e if v is None else v['err']}")
                return
            runs[name].append(v)

    def med(vals):
        return sorted(vals)[len(vals) // 2]

    cost = {name: {k: {lap: round(med([r[k][lap] for r in rs]), 2) for lap in ("lap1", "lap2")} for k in rs[0]}
            for name, rs in runs.items()}
    spread = {k: round(max(r[k]["lap2"] for r in runs["none"]) - min(r[k]["lap2"] for r in runs["none"]), 2) for k in runs["none"][0]}
    notes.append(f"C93 spread of lap 2 over the three none runs, ms (the noise): {spread}")
    # one commit per frame: count the worker's PushFrame events under a trace for the two moving 2D cases
    pushes = {}
    for case in (["2d-move", 512, 512], ["2d-move", 1920, 1080]):
        v, n = traced(json.dumps({"canvas:seed": 1111}), cost_js([case]), flags)
        pushes[f"{case[0]}-{case[1]}"] = (None, None) if v is None else (v[f"{case[0]}-{case[1]}"]["n"], n)
    notes.append("C93 worker frame period ms, median of 3 (lap 1 = mask still growing, lap 2 = settled), none | seed: " + " ; ".join(
        f"{k} {cost['none'][k]['lap1']}/{cost['none'][k]['lap2']} | {cost['A'][k]['lap1']}/{cost['A'][k]['lap2']}" for k in cost["none"]))
    notes.append("C93 commits: rAF frames vs PushFrame events under a trace: " + ", ".join(f"{k} {a} vs {b}" for k, (a, b) in pushes.items()))
    bad = [k for k, (a, b) in pushes.items() if a is None or b is None or b < 0.9 * a]
    if bad:
        mark_unmeasured(C93, f"the frame period is not one commit per rAF frame ({pushes}): the cost of a commit is not what it times")
        return
    pinned, over = [], []
    for k in cost["none"]:
        for lap in ("lap1", "lap2"):
            n0, a0 = cost["none"][k][lap], cost["A"][k][lap]
            if 16.0 <= n0 <= 17.5:      # the frame period is the vsync tick: a commit's cost is hidden in it
                pinned.append(f"{k}/{lap}")
            elif a0 > n0 + max(0.03 * n0 + 0.5, 1.5 * spread[k]):    # a heavy scene's own runs differ by 2 ms: no resolution below it
                over.append(f"{k}/{lap} {n0}->{a0}")
    notes.append(f"C93 pinned at the vsync tick (not measured): {pinned}; over max(3 % + 0.5 ms, 1.5 x the none runs' spread): {over}")
    if len(pinned) == 2 * len(cost["none"]):
        mark_unmeasured(C93, "every case's frame period is pinned at the vsync tick with the limit off")
    else:
        soft[C93] = not over


# CAMOU_SP3A_ONLY=ph,c95,c96,c97,c98 runs only those row groups (mutant runs: the rows of the other groups are then absent)
ONLY = {t for t in os.environ.get("CAMOU_SP3A_ONLY", "").split(",") if t}


def want(tag):
    return not ONLY or tag in ONLY


if want("ph"):
    placeholder_rows()


def push_durations(events):
    """The duration in ms of every OffscreenCanvas::PushFrame event ('X' complete events, or 'B'/'E' pairs per thread)."""
    out, open_ts = [], {}
    for ev in events:
        if ev.get("name") != "OffscreenCanvas::PushFrame":
            continue
        ph, key = ev.get("ph"), (ev.get("pid"), ev.get("tid"))
        if ph == "X" and "dur" in ev:
            out.append(ev["dur"] / 1000.0)
        elif ph == "B":
            open_ts.setdefault(key, []).append(ev["ts"])
        elif ph == "E" and open_ts.get(key):
            out.append((ev["ts"] - open_ts[key].pop()) / 1000.0)
    return out


def push_by_status(events):
    """Mean OffscreenCanvas::PushFrame ms per CamouFrameNoise defer status: the status instant inside the event's span, same thread."""
    spans, status = [], []
    for ev in events:
        if ev.get("name") == "OffscreenCanvas::PushFrame" and ev.get("ph") == "X" and "dur" in ev:
            spans.append((ev.get("pid"), ev.get("tid"), ev["ts"], ev["ts"] + ev["dur"]))
        elif ev.get("name") == "CamouFrameNoise":
            status.append((ev.get("pid"), ev.get("tid"), ev["ts"], (ev.get("args") or {}).get("defer", "?")))
    out = {}
    for pid, tid, t0, t1 in spans:
        for p2, t2, ts, st in status:
            if p2 == pid and t2 == tid and t0 <= ts <= t1:
                n, tot = out.get(st, (0, 0.0))
                out[st] = (n + 1, tot + (t1 - t0) / 1000.0)
                break
    return {k: f"{n} commits, mean {tot / n:.2f} ms" for k, (n, tot) in out.items()}


def max_defer_jobs(events):
    """The most unwalked recordings any committed frame carried (the 'jobs' trace arg of CamouFrameNoise)."""
    return max([(ev.get("args") or {}).get("jobs", 0) for ev in events if ev.get("name") == "CamouFrameNoise"] or [0])


def max_arg(events, name, arg):
    """The largest value of a trace arg over the instants called `name` (the counters it reports only grow)."""
    return max([(ev.get("args") or {}).get(arg, 0) for ev in events if ev.get("name") == name] or [0])


def replay_stats(events):
    """(replays, mean ms of a CamouDeferredReplay, {mode: count}) of the main thread's walks of the frames the page read."""
    durs = [ev["dur"] / 1000.0 for ev in events if ev.get("name") == "CamouDeferredReplay" and ev.get("ph") == "X" and "dur" in ev]
    modes = {}
    for ev in events:
        if ev.get("name") == "CamouReplayMode":
            m = (ev.get("args") or {}).get("mode", "?")
            modes[m] = modes.get(m, 0) + 1
    return len(durs), (sum(durs) / len(durs) if durs else 0.0), modes


def defer_counts(events):
    """How many frames the worker committed, per CamouFrameNoise defer status (the trace arg of CamouMakeFrameNoise)."""
    counts = {}
    for ev in events:
        if ev.get("name") == "CamouFrameNoise":
            status = (ev.get("args") or {}).get("defer", "?")
            counts[status] = counts.get(status, 0) + 1
    return counts


# a page's first read of a heavy placeholder frame (8 frames drawn back to back: the recordings are still unwalked at the last commit),
# against the same read of a main-thread canvas with the same 8 frames
LEAKS9 = """async () => {
  const W = 512, HT = 512;
  __HEAVY__
  // the frames are back-to-back messages: the worker never idles between them, so every recording is still unwalked at the last commit
  const wsrc = 'const heavy2d = ' + heavy2d.toString() + '; let off, i = 0; onmessage = (e) => { const [k, o] = e.data; if (o) off = o;' +
    ' if (k === "frame") heavy2d(off, i++); else postMessage("done"); };';
  const frames = async (n) => { for (let i = 0; i < n; i++) await new Promise((r) => { requestAnimationFrame(() => r()); setTimeout(r, 100); }); };
  const read = (src) => { const d = document.createElement('canvas'); d.width = W; d.height = HT;
    const x = d.getContext('2d', { willReadFrequently: true }); const t0 = performance.now();
    x.drawImage(src, 0, 0); x.getImageData(0, 0, W, HT); const t1 = performance.now();
    x.drawImage(src, 0, 0); x.getImageData(0, 0, W, HT); return [t1 - t0, performance.now() - t1]; };
  const R = {};
  const w = new Worker(URL.createObjectURL(new Blob([wsrc])));
  const c = document.createElement('canvas'); c.width = W; c.height = HT; document.body.appendChild(c);
  const off = c.transferControlToOffscreen();
  w.postMessage(['init', off], [off]);
  for (let k = 0; k < 8; k++) w.postMessage(['frame']);
  await new Promise((res) => { w.onmessage = () => res(); w.postMessage(['done']); });
  await frames(3);
  [R.ph1, R.ph2] = read(c);
  const m = document.createElement('canvas'); m.width = W; m.height = HT;
  for (let i = 0; i < 8; i++) heavy2d(m, i);
  [R.m1, R.m2] = read(m);
  w.terminate();
  for (const k in R) R[k] = +R[k].toFixed(2);
  return R;
}""".replace("__HEAVY__", HEAVY2D)


LEAKS10 = """async () => {
  const H = (u8) => { let h = 2166136261;
    for (let i = 0; i < u8.length; i++) { h ^= u8[i]; h = Math.imul(h, 16777619) >>> 0; }
    return h.toString(16); };
  const Hs = (s) => H(new TextEncoder().encode(s));
  const b64 = (u8) => { let s = ''; for (let i = 0; i < u8.length; i++) s += String.fromCharCode(u8[i]); return btoa(s); };
  const W = 512, HT = 512;
  __HEAVY__
  const wsrc = 'const heavy2d = ' + heavy2d.toString() + '; let off;' +
    ' const sleep = (ms) => new Promise((r) => setTimeout(r, ms));' +
    ' onmessage = async (e) => { const [k, o, n] = e.data; if (o) off = o;' +
    ' if (k === "cur") { postMessage(await (await off.convertToBlob()).arrayBuffer()); return; }' +
    // one frame of 8 heavy scenes, then the worker sits idle until its idle walk has applied that recording to the mask; the next,
    // tiny, frame then commits with the applied mask as the base of its record and one recording unwalked on top of it (a case
    // none of the rAF legs has: a base that holds marks plus a pending job). The walk was never seen to stop inside a recording
    // here (a trace of the jobs per committed frame shows only whole jobs), so a half-walked job is covered by the unit tests only
    ' if (k === "big") { for (let j = 0; j < 8; j++) heavy2d(off, 100 + j); await sleep(1500); postMessage("done"); return; }' +
    ' if (k === "tiny") { off.getContext("2d").fillRect(0, 0, 3, 3); await sleep(50); postMessage("done"); return; }' +
    ' let i = 0; const f = () => { heavy2d(off, i); if (++i < n) requestAnimationFrame(f); else postMessage("done"); }; requestAnimationFrame(f); };';
  const w = new Worker(URL.createObjectURL(new Blob([wsrc])));
  const call = (msg, tr) => new Promise((r) => { w.onmessage = (e) => r(e.data); w.postMessage(msg, tr || []); });
  const frames = async (n) => { for (let i = 0; i < n; i++) await new Promise((r) => { requestAnimationFrame(() => r()); setTimeout(r, 100); }); };
  const read2d = (src) => { const d = document.createElement('canvas'); d.width = W; d.height = HT;
    const x = d.getContext('2d', { willReadFrequently: true }); x.drawImage(src, 0, 0); return H(x.getImageData(0, 0, W, HT).data); };
  const c = document.createElement('canvas'); c.width = W; c.height = HT; document.body.appendChild(c);
  const off = c.transferControlToOffscreen();
  const R = {};
  // every surface of the placeholder against the worker's own noised PNG of the same canvas (the pixels are opaque, so the PNG's
  // decoded pixels are the noised bytes themselves, and drawn to a 2D canvas they are imported: no noise on top)
  const snap = async (k) => {
    R['blob' + k] = H(new Uint8Array(await (await new Promise((r) => c.toBlob(r))).arrayBuffer()));
    R['url' + k] = Hs(c.toDataURL());
    R['draw' + k] = read2d(c);
    const cur = new Uint8Array(await call(['cur']));
    R['cur' + k] = H(cur); R['refUrl' + k] = Hs('data:image/png;base64,' + b64(cur));
    R['refDraw' + k] = read2d(await createImageBitmap(new Blob([cur], { type: 'image/png' })));
  };
  await call(['run', off, 12], [off]); await frames(3); await snap(1);
  await call(['run', null, 20]); await frames(3); await snap(2);
  await call(['big']); await call(['tiny']); await frames(3); await snap(3);
  w.terminate();
  return R;
}""".replace("__HEAVY__", HEAVY2D)


def deferral_rows():
    arms = {}
    for name, cfg in (("none", None), ("A", json.dumps({"canvas:seed": 1111})), ("B", json.dumps({"canvas:seed": 2222})),
                      ("A2", json.dumps({"canvas:seed": 1111}))):
        v, e = session(cfg, LEAKS10, extra_flags=GL_ROW_FLAGS)
        if v is None or "err" in v:
            results[C95] = False
            notes.append(f"C95: arm {name}: {e if v is None else v['err']}")
            break
        arms[name] = v
    legs = ("1", "2", "3")
    if len(arms) == 4:
        results[C95] = (all(a["blob" + k] == a["cur" + k] and a["url" + k] == a["refUrl" + k] and a["draw" + k] == a["refDraw" + k]
                            for a in arms.values() for k in legs)
                        and all(arms["A"][f + k] != arms["none"][f + k] and arms["A"][f + k] != arms["B"][f + k]
                                and arms["A"][f + k] == arms["A2"][f + k] for f in ("blob", "url", "draw") for k in legs))
        for name, a in arms.items():
            notes.append(f"C95 {name}: " + " ; ".join(f"leg {k}: blob {a['blob' + k]}/{a['cur' + k]} url {a['url' + k]}/{a['refUrl' + k]} "
                                                      f"draw {a['draw' + k]}/{a['refDraw' + k]}" for k in legs))
        # the second leg's read is after more than 16 unread flushes: past the queue's cap (16) the oldest recordings are merged
        # (2026-11-24, rule D2), on the worker's own read and on the frame alike. The trace shows the backlog did reach the cap, else
        # the row did not cross it
        v, events = traced_events(json.dumps({"canvas:seed": 1111}), LEAKS10, GL_ROW_FLAGS)
        if v is None:
            notes.append(f"C95: trace session: {events}")
            mark_unmeasured(C95, "trace session failed")
        else:
            most = max_defer_jobs(events)
            shed = max_arg(events, "CamouParked", "parked")
            merged = max_arg(events, "CamouMerged", "merged")
            notes.append(f"C95 most recordings one committed frame carried unwalked: {most} (the cap is 16); recordings merged {merged}, "
                         f"shed from the queue and parked {shed}")
            if any(v["blob" + k] != v["cur" + k] or v["url" + k] != v["refUrl" + k] or v["draw" + k] != v["refDraw" + k] for k in legs):
                results[C95] = False
            if most < 16 or shed + merged < 1:
                mark_unmeasured(C95, f"the worker's idle walk kept the backlog at {most} < 16 / {merged} merged, {shed} shed: the cap was not crossed")
    if os.environ.get("CAMOU_SP3A_NO_COST") == "1":
        mark_unmeasured(C94, "CAMOU_SP3A_NO_COST=1")
        return
    flags = GL_ROW_FLAGS + ["--disable-frame-rate-limit", "--disable-gpu-vsync"]
    cases = (["2d-move", 1920, 1080], ["2d-heavy", 512, 512])
    mean, deferred, by_status = {}, {}, {}
    for case in cases:
        key = f"{case[0]}-{case[1]}"
        runs = {"none": [], "A": []}
        for _ in range(3):
            for name, cfg in (("none", None), ("A", json.dumps({"canvas:seed": 1111}))):
                v, events = traced_events(cfg, cost_js([case]), flags)
                if v is None:
                    mark_unmeasured(C94, f"trace session {key} {name}: {events}")
                    return
                ds = push_durations(events)
                if len(ds) < 100:
                    mark_unmeasured(C94, f"{key} {name}: {len(ds)} PushFrame durations in the trace (120 frames drawn)")
                    return
                runs[name].append((sum(ds) / len(ds), defer_counts(events)))
                if name == "A" and not by_status.get(key):
                    by_status[key] = push_by_status(events)
        for name, rs in runs.items():
            mean[key, name] = sorted(m for m, _ in rs)[1]
        deferred[key] = [c for _, c in runs["A"]]
    notes.append("C94 mean PushFrame ms per commit (median of 3), none | seed: " + " ; ".join(
        f"{k} {mean[k, 'none']:.2f} | {mean[k, 'A']:.2f}" for k in (f"{c[0]}-{c[1]}" for c in cases)))
    notes.append(f"C94 seeded commits by CamouFrameNoise defer status, per run: {deferred}")
    notes.append(f"C94 seeded PushFrame cost by status (first seeded run): {by_status}")
    over = [k for k in (f"{c[0]}-{c[1]}" for c in cases) if mean[k, "A"] > mean[k, "none"] + 0.5]
    # the seeded runs must have deferred frames: a row that measures a build that never defers measures nothing about the deferral
    no_defer = [k for k, cs in deferred.items() if not any(c.get("deferred", 0) for c in cs)]
    notes.append(f"C94 over none + 0.5 ms: {over}; no deferred commit in any seeded run: {no_defer}")
    low = [k for k, cs in deferred.items()
           if any(c.get("deferred", 0) < 0.9 * sum(c.values()) for c in cs)]
    notes.append(f"C94 a seeded run with under 90 % of its commits deferred: {low}")
    soft[C94] = not over and not no_defer and not low
    # the cost moves to the page's read: report it (not a row). The read of a main-thread canvas and of a placeholder both include
    # the raster and the readback, so each arm's cost is what the seed adds to the same read: seed minus none, per scene
    reads = {"none": [], "A": []}
    for _ in range(3):
        for name, cfg in (("none", None), ("A", json.dumps({"canvas:seed": 1111}))):
            v, e = session(cfg, LEAKS9, extra_flags=GL_ROW_FLAGS)
            if v is None or "err" in v:
                notes.append(f"C94 read cost: {e if v is None else v['err']}")
                return
            reads[name].append(v)
    med = {a: {k: sorted(r[k] for r in rs)[1] for k in rs[0]} for a, rs in reads.items()}
    v, events = traced_events(json.dumps({"canvas:seed": 1111}), LEAKS9, GL_ROW_FLAGS)
    carried = [(ev["ts"], (ev.get("args") or {}).get("jobs", 0)) for ev in events if ev.get("name") == "CamouFrameNoise"] if v is not None else []
    notes.append(f"C94 read cost scene: recordings the committed frames carried unwalked, in order: {[j for _, j in sorted(carried)]}")
    replays = [((ev.get("args") or {}).get("jobs"), round(ev["dur"] / 1000.0, 1)) for ev in events
               if ev.get("name") == "CamouDeferredReplay" and ev.get("ph") == "X" and "dur" in ev] if v is not None else []
    notes.append(f"C94 the walk the page's reads ran on the main thread (CamouDeferredReplay), (recordings, ms) per frame read: {replays}")
    notes.append("C94 read cost ms (report only), heavy 512, median of 3, none | seed: " + " ; ".join(
        f"{lbl} {med['none'][k]} | {med['A'][k]} (seed adds {med['A'][k] - med['none'][k]:+.1f})"
        for lbl, k in (("placeholder first read", "ph1"), ("placeholder again", "ph2"),
                       ("main-thread canvas first read", "m1"), ("main-thread canvas again", "m2"))))


if want("c95"):
    deferral_rows()

# the top half only (12 frames), then the bottom half only (40 frames): no worker read, no idle; what the page read of the top must stay
LEAKS11 = """async () => {
  const H = (u8) => { let h = 2166136261;
    for (let i = 0; i < u8.length; i++) { h ^= u8[i]; h = Math.imul(h, 16777619) >>> 0; }
    return h.toString(16); };
  const W = 512, HT = 512, ROWS = 192;
  const wsrc = `const heavyHalf = (c, n, yo) => { const x = c.getContext('2d'); if (n === 0) { x.fillStyle = '#16f'; x.fillRect(0, 0, c.width, c.height); }
      x.font = '14px sans-serif';
      for (let i = 0; i < 120; i++) { const px = (n * 7 + i * 37) % c.width, py = yo + (n * 5 + i * 53) % 256;
        x.beginPath(); x.moveTo(px, py); x.bezierCurveTo(px + 30, py - 20, px + 50, py + 40, px + 80, py + 10); x.lineTo(px + 40, py + 60); x.closePath();
        x.fillStyle = 'rgba(' + ((i * 11) % 255) + ',' + ((i * 23) % 255) + ',' + ((i * 47) % 255) + ',0.6)'; x.fill();
        x.strokeStyle = '#fff'; x.lineWidth = 2; x.stroke(); }
      for (let i = 0; i < 20; i++) x.fillText('camoucrome ' + i + ' ' + n, (n * 3 + i * 91) % c.width, yo + (i * 41 + n) % 256 + 14); };
    let off;
    onmessage = async (e) => { const [k, o, n1, n2] = e.data; if (o) off = o;
      if (k === 'cur') { postMessage(await (await off.convertToBlob()).arrayBuffer()); return; }
      let i = 0; const f = () => { heavyHalf(off, i, i < n1 ? 0 : 256); i++; if (i === n1) postMessage('phase1');
        if (i < n1 + n2) requestAnimationFrame(f); else postMessage('done'); };
      requestAnimationFrame(f); };`;
  const w = new Worker(URL.createObjectURL(new Blob([wsrc])));
  const waiting = {};
  const wait = (k) => new Promise((r) => { waiting[k] = r; });
  w.onmessage = (e) => { const k = typeof e.data === 'string' ? e.data : 'cur'; if (waiting[k]) waiting[k](e.data); };
  const frames = async (n) => { for (let i = 0; i < n; i++) await new Promise((r) => { requestAnimationFrame(() => r()); setTimeout(r, 100); }); };
  const top = (src) => { const d = document.createElement('canvas'); d.width = W; d.height = HT;
    const x = d.getContext('2d', { willReadFrequently: true }); x.drawImage(src, 0, 0); return H(x.getImageData(0, 0, W, ROWS).data); };
  const c = document.createElement('canvas'); c.width = W; c.height = HT; document.body.appendChild(c);
  const off = c.transferControlToOffscreen();
  const p1 = wait('phase1'), pd = wait('done');
  w.postMessage(['run', off, 20, 40], [off]);
  await p1; await frames(2);
  const R = {};
  R.r1 = top(c);
  await pd;
  R.r2 = top(c);
  const cur = wait('cur'); w.postMessage(['cur']);
  R.cur = top(await createImageBitmap(new Blob([new Uint8Array(await cur)], { type: 'image/png' })));
  w.terminate();
  return R;
}"""


_a = LEAKS11.index("const wsrc = `") + len("const wsrc = `")
HALF_WORKER = LEAKS11[_a:LEAKS11.index("`;\n  const w = new Worker")]
LEAKS13 = """async () => {
  const H = (u8) => { let h = 2166136261;
    for (let i = 0; i < u8.length; i++) { h ^= u8[i]; h = Math.imul(h, 16777619) >>> 0; }
    return h.toString(16); };
  const W = 512, HT = 512, ROWS = 192;
  const wsrc = `__HALF__`;
  const frames = async (n) => { for (let i = 0; i < n; i++) await new Promise((r) => { requestAnimationFrame(() => r()); setTimeout(r, 100); }); };
  const top = (src) => { const d = document.createElement('canvas'); d.width = W; d.height = HT;
    const x = d.getContext('2d', { willReadFrequently: true }); x.drawImage(src, 0, 0); return H(x.getImageData(0, 0, W, ROWS).data); };
  const R = {};
  for (const round of [0, 1]) {
    const w = new Worker(URL.createObjectURL(new Blob([wsrc])));
    let seen; const p1 = new Promise((r) => { seen = r; });
    w.onmessage = (e) => { if (e.data === 'phase1') seen(); };
    const c = document.createElement('canvas'); c.width = W; c.height = HT; document.body.appendChild(c);
    const off = c.transferControlToOffscreen();
    w.postMessage(['run', off, 20, 40], [off]);
    await p1; await frames(2);
    R['a' + round] = top(c);       // the signal of this read is on its way to the worker
    w.terminate();                 // the worker dies with it unprocessed
    await frames(4);
    R['b' + round] = top(c);       // the placeholder keeps its last frame
    c.remove();                    // and the canvas leaves the page
    await frames(2);
  }
  R.alive = true;
  return R;
}""".replace("__HALF__", HALF_WORKER)

# the same heavy frames on a main-thread canvas, captured: the reference for what a seeded capture costs a main thread that walks its own recordings
LEAKS14 = """async () => {
  const W = 512, HT = 512;
  __HEAVY__
  const c = document.createElement('canvas'); c.width = W; c.height = HT; document.body.appendChild(c);
  const v = document.createElement('video'); v.muted = true; v.srcObject = c.captureStream(30); v.play().catch(() => {});
  let n = 0; const cb = () => { n++; v.requestVideoFrameCallback(cb); }; v.requestVideoFrameCallback(cb);
  const t0 = performance.now();
  await new Promise((res) => { let i = 0; const f = () => { heavy2d(c, i); if (++i < 150) requestAnimationFrame(f); else res(); }; requestAnimationFrame(f); });
  return { frames: n, ms: +(performance.now() - t0).toFixed(0) };
}""".replace("__HEAVY__", HEAVY2D)


def lifecycle_rows():
    arms = {}
    for name, cfg in (("none", None), ("A", json.dumps({"canvas:seed": 1111})), ("A2", json.dumps({"canvas:seed": 1111}))):
        v, e = session(cfg, LEAKS13, extra_flags=GL_ROW_FLAGS)
        if v is None or "err" in v or not v.get("alive"):
            results[C99] = False
            notes.append(f"C99: arm {name}: {e if v is None else v}")
            return
        arms[name] = v
    for name, a in arms.items():
        notes.append(f"C99 {name}: round 1 read {a['a0']} then after terminate {a['b0']}; round 2 read {a['a1']} then {a['b1']}")
    results[C99] = (all(a["a0"] == a["b0"] and a["a1"] == a["b1"] for a in arms.values())
                    and arms["A"]["a0"] != arms["none"]["a0"] and arms["A"]["a0"] == arms["A2"]["a0"])
    # no seed: nothing is recorded, posted or parked, so none of the trace events of this change is emitted
    v, events = traced_events(None, LEAKS13, GL_ROW_FLAGS)
    if v is None:
        notes.append(f"C99: trace session: {events}")
        mark_unmeasured(C99, "trace session failed")
        return
    names = ("CamouFrameNoise", "CamouParked", "CamouMerged", "CamouParkedWalk", "CamouFrameRead", "CamouReplayMode", "CamouDeferredReplay")
    seen = {n: sum(1 for ev in events if ev.get("name") == n) for n in names}
    pushes = sum(1 for ev in events if ev.get("name") == "OffscreenCanvas::PushFrame")
    notes.append(f"C99 no seed: trace events of this change {seen}; PushFrame events {pushes}")
    if any(seen.values()):
        results[C99] = False
    if results[C99] and pushes < 5:
        mark_unmeasured(C99, f"only {pushes} PushFrame events in the trace of the unseeded run")


def evicted_before_first_signal(events):
    """Unseen recordings the worker dropped (evicted from the parked list) before the page's first read signal reached it: a
    race of the run, not a verdict. 0 when no signal was ever received (that is the row's business: it fails then)."""
    reads = sorted(ev["ts"] for ev in events if ev.get("name") == "CamouFrameRead")
    if not reads:
        return 0
    return max([(ev.get("args") or {}).get("evicted", 0) for ev in events if ev.get("name") == "CamouParked" and ev["ts"] < reads[0]] or [0])


def reread_attempt():
    """One launch of each arm of C96 (the seeded ones traced): (arms, the seeded arms' events, arms where the worker evicted before the first signal)."""
    arms, events, raced = {}, {}, []
    for name, cfg in (("none", None), ("A", json.dumps({"canvas:seed": 1111})), ("B", json.dumps({"canvas:seed": 2222})),
                      ("A2", json.dumps({"canvas:seed": 1111}))):
        if cfg is None:
            v, e = session(cfg, LEAKS11, extra_flags=GL_ROW_FLAGS)
            ev = []
        else:
            v, ev = traced_events(cfg, LEAKS11, GL_ROW_FLAGS)
            e = ev if v is None else None
        if v is None or "err" in v:
            return None, f"arm {name}: {e if v is None else v['err']}", []
        arms[name], events[name] = v, ev
        if evicted_before_first_signal(ev):
            raced.append(name)
    return arms, events, raced


def reread_rows():
    arms = events = None
    for attempt in range(3):
        arms, events, raced = reread_attempt()
        if arms is None:
            results[C96] = False
            notes.append(f"C96: {events}")
            return
        if not raced:
            break
        notes.append(f"C96 launch {attempt + 1}: the worker evicted unseen recordings before the first signal reached it in arm(s) {raced}: a race, not a verdict; "
                     + ("retrying" if attempt < 2 else "giving up"))
    else:
        mark_unmeasured(C96, "the worker evicted unseen recordings before the page's first signal in all 3 launches (the read lagged the worker)")
        return
    for name, a in arms.items():
        notes.append(f"C96 {name}: top rows read 1 {a['r1']} read 2 {a['r2']} worker's own {a['cur']}")
    results[C96] = (all(a["r1"] == a["r2"] and a["r2"] == a["cur"] for a in arms.values())
                    and arms["A"]["r2"] != arms["none"]["r2"] and arms["A"]["r2"] != arms["B"]["r2"] and arms["A"]["r2"] == arms["A2"]["r2"])
    ev = events["A"]
    parked, evicted = max_arg(ev, "CamouParked", "parked"), max_arg(ev, "CamouParked", "evicted")
    merged = max_arg(ev, "CamouMerged", "merged")
    signals = max_arg(ev, "CamouFrameRead", "signals")
    walked, seen = max_arg(ev, "CamouParkedWalk", "walked"), max_arg(ev, "CamouParkedWalk", "seen")
    notes.append(f"C96 trace (seed A): merged {merged}, shed and parked {parked}, evicted unwalked {evicted} (before the first signal: {evicted_before_first_signal(ev)}), "
                 f"signals received {signals}, parked walked {walked}, seen recordings walked instead of dropped {seen}, most carried by a frame {max_defer_jobs(ev)}")
    # rule D2 (2026-11-24): past the cap recordings merge; a run that parks must still walk what it parked
    crossed = merged >= 1 or (parked >= 1 and seen + walked >= 1)
    if results[C96] and (not crossed or signals < 1):
        mark_unmeasured(C96, f"the run did not cross the cap and signal (merged {merged}, parked {parked}, walked {walked + seen}, signals {signals})")


if want("c96"):
    reread_rows()


def deferred_scene_rows():
    arms = {}
    for name, cfg in (("none", None), ("A", json.dumps({"canvas:seed": 1111})), ("B", json.dumps({"canvas:seed": 2222})),
                      ("A2", json.dumps({"canvas:seed": 1111}))):
        v, e = session(cfg, LEAKS6_DEFERRED, extra_flags=GL_ROW_FLAGS)
        if v is None or "err" in v:
            results[C97] = False
            notes.append(f"C97: arm {name}: {e if v is None else v['err']}")
            return
        arms[name] = v

    def noised(kind, key):
        return (arms["A"][kind][key] != arms["none"][kind][key] and arms["A"][kind][key] != arms["B"][kind][key]
                and arms["A"][kind][key] == arms["A2"][kind][key])

    def equals(key, ref):
        return all(a["2d"][key] == a["2d"][ref] for a in arms.values())

    results[C97] = (noised("2d", "blob") and noised("2d", "url") and noised("2d", "draw") and noised("2d", "cib") and noised("2d", "blob2")
                    and equals("blob", "refBlob") and equals("blob", "cur") and equals("url", "refUrl") and equals("draw", "refDraw")
                    and equals("cib", "refDraw") and equals("blob2", "refBlob2")
                    and all(arms[a]["2d"]["blob2"] != arms[a]["2d"]["blob"] for a in ("A", "B")))
    for name, a in arms.items():
        k = a["2d"]
        notes.append(f"C97 {name}: blob {k['blob']}/{k['refBlob']}/{k['cur']} url {k['url']}/{k['refUrl']} draw {k['draw']}/{k['refDraw']} "
                     f"cib {k['cib']} cap {k['cap']} blob2 {k['blob2']}/{k['refBlob2']}")
    v, events = traced_events(json.dumps({"canvas:seed": 1111}), LEAKS6_DEFERRED, GL_ROW_FLAGS)
    if v is None:
        notes.append(f"C97: trace session: {events}")
        mark_unmeasured(C97, "trace session failed")
        return
    counts = defer_counts(events)
    replays, mean_ms, modes = replay_stats(events)
    notes.append(f"C97 frames committed by defer status: {counts}; replays on the main thread {replays} (mean {mean_ms:.1f} ms) {modes}")
    if results[C97] and (not counts.get("deferred") or not replays):
        mark_unmeasured(C97, f"no frame of the scene was committed deferred / read by a replay ({counts}): the deferred path was not reached")


if want("c97"):
    deferred_scene_rows()

# captureStream(placeholder) of a worker that draws heavy frames without idling: the page reads every frame the stream takes
LEAKS12 = """async () => {
  const W = 512, HT = 512;
  __HEAVY__
  const wsrc = 'const heavy2d = ' + heavy2d.toString() + '; let off; onmessage = (e) => { const [k, o, n] = e.data; if (o) off = o;' +
    ' let i = 0; const f = () => { heavy2d(off, i); if (++i < n) requestAnimationFrame(f); else postMessage("done"); }; requestAnimationFrame(f); };';
  const w = new Worker(URL.createObjectURL(new Blob([wsrc])));
  const c = document.createElement('canvas'); c.width = W; c.height = HT; document.body.appendChild(c);
  const off = c.transferControlToOffscreen();
  const v = document.createElement('video'); v.muted = true; v.srcObject = c.captureStream(30); v.play().catch(() => {});
  let n = 0; const cb = () => { n++; v.requestVideoFrameCallback(cb); }; v.requestVideoFrameCallback(cb);
  const t0 = performance.now();
  await new Promise((res) => { w.onmessage = () => res(); w.postMessage(['run', off, 150], [off]); });
  const ms = performance.now() - t0;
  w.terminate();
  return { frames: n, ms: +ms.toFixed(0) };
}""".replace("__HEAVY__", HEAVY2D)


LEAKS15 = LEAKS12.replace("""  const v = document.createElement('video'); v.muted = true; v.srcObject = c.captureStream(30); v.play().catch(() => {});
  let n = 0; const cb = () => { n++; v.requestVideoFrameCallback(cb); }; v.requestVideoFrameCallback(cb);""", "  let n = 0;")
assert LEAKS15 != LEAKS12


def mask_add_stats(events):
    """The worker's CamouMaskAdd spans (queue push + shed + parked walk): count, mean, p95, max ms and how many took over 5 ms."""
    ds = sorted(ev["dur"] / 1000.0 for ev in events if ev.get("name") == "CamouMaskAdd" and ev.get("ph") == "X" and "dur" in ev)
    if not ds:
        return "no CamouMaskAdd span"
    return (f"{len(ds)} flushes, mean {sum(ds) / len(ds):.2f} ms, p95 {ds[int(len(ds) * 0.95) - 1]:.2f} ms, max {ds[-1]:.1f} ms, "
            f"{sum(1 for d in ds if d > 5.0)} over 5 ms")


def capture_rows():
    out = {}
    for name, cfg in (("none", None), ("A", json.dumps({"canvas:seed": 1111}))):
        v, events = traced_events(cfg, LEAKS12, GL_ROW_FLAGS)
        if v is None or "err" in v:
            mark_unmeasured(C98, f"capture session {name}: {events if v is None else v['err']}")
            return
        out[name] = (v, replay_stats(events), defer_counts(events))
        if name == "A":
            add_read = mask_add_stats(events)
    (vn, _, _), (va, (replays, mean_ms, modes), counts) = out["none"], out["A"]
    # report only: what the worker's flush pays (CamouMaskAdd: push, shedding, parking, the walk of an evicted seen recording) with the
    # page reading the placeholder (the capture above) and with nobody reading it
    v, ev = traced_events(json.dumps({"canvas:seed": 1111}), LEAKS15, GL_ROW_FLAGS)
    add_noread = mask_add_stats(ev) if v is not None else f"session failed: {ev}"
    notes.append(f"C98b report only, worker CamouMaskAdd per flush, 150 heavy 512 frames, seed: page READING the placeholder (captureStream): {add_read}; nobody reading: {add_noread}")
    notes.append(f"C98 captureStream(placeholder), 150 heavy 512 frames, video frames seen / run ms: none {vn['frames']} / {vn['ms']}, seed {va['frames']} / {va['ms']}; "
                 f"seed: {replays} replays on the main thread, mean {mean_ms:.1f} ms each (per frame read), modes {modes}, commits {counts}")
    # the reference: the same frames drawn on a main-thread canvas and captured, where the page's own thread walks the recordings
    ref = {}
    for name, cfg in (("none", None), ("A", json.dumps({"canvas:seed": 1111}))):
        v, e = session(cfg, LEAKS14, extra_flags=GL_ROW_FLAGS)
        if v is None or "err" in v:
            notes.append(f"C98 main-thread canvas reference {name}: {e if v is None else v['err']}")
            break
        ref[name] = v
    if len(ref) == 2:
        notes.append(f"C98 reference, a MAIN-THREAD canvas with the same 150 frames captured: video frames / run ms: none {ref['none']['frames']} / {ref['none']['ms']}, "
                     f"seed {ref['A']['frames']} / {ref['A']['ms']} (the walk is the page's own either way: this row reports, it asserts only the continuation)")
    if replays < 5:
        mark_unmeasured(C98, f"only {replays} frame reads were replays ({counts}): the stream did not read deferred frames")
        return
    cont = modes.get("continue", 0)
    soft[C98] = cont * 2 >= replays


if want("c98"):
    capture_rows()

if want("c99"):
    lifecycle_rows()

# C69: many flushes and no read between them must not lose the marks of the first. A canvas outside the page flushes its recording at
# the end of every task that drew on it (FinalizeFrame; a worker's OffscreenCanvas does not, measured on the box). The 160 tasks are
# MessageChannel messages queued at once (64 gave only 32 traced flushes on -17 on the real GPU, under the floor of 40), so they
# run back to back and every flush is still queued when the read comes. The first
# circles must read noised: they differ from the unconfigured read. The trace proves the flushes happened (a coalesced or CPU-rastered
# run queues nothing and is UNMEASURED, not PASS).
C69A = ("C69a a canvas outside the page: three circles, then 160 MessageChannel tasks of one arc each queued at once (one flush each), "
        "then one read: the same in two seeded runs, and the first circles read differently from unconfigured (seed 7); fewer than 40 "
        "traced flushes, or last arcs that read like unconfigured, is UNMEASURED")
C69A_MIN_FLUSHES = 40
C69A_SCENE = """async () => {
  const c = document.createElement('canvas'); c.width = 500; c.height = 40; const x = c.getContext('2d'); x.fillStyle = '#f60';
  for (let j = 0; j < 3; j++) { x.beginPath(); x.arc(12 + j * 20, 20, 8.3, 0, Math.PI * 2); x.fill(); }
  const ch = new MessageChannel(); let n = 0;
  await new Promise((done) => { ch.port1.onmessage = (e) => { const i = e.data;
      x.beginPath(); x.arc(400, 20, 6.3 + (i & 1) * 0.5, 0, Math.PI * 2); x.fill(); if (++n === 160) done(); };
    for (let i = 0; i < 160; i++) ch.port2.postMessage(i); });
  const d = x.getImageData(0, 0, 500, 40).data; const first = [], last = [];
  for (let y = 0; y < 40; y++) for (let q = 0; q < 500; q++) { const o = (y * 500 + q) * 4;
    (q < 60 ? first : q >= 340 ? last : []).push(d[o], d[o + 1], d[o + 2], d[o + 3]); }
  return { first: first.join(','), last: last.join(',') };
}"""


def c69a_row():
    seed = json.dumps({"canvas:seed": 7})
    un, ue = session(None, C69A_SCENE, extra_flags=GL_ROW_FLAGS)
    a, ae = session(seed, C69A_SCENE, extra_flags=GL_ROW_FLAGS)
    b, events = traced_events(seed, C69A_SCENE, GL_ROW_FLAGS)
    if un is None or a is None or b is None:
        results[C69A] = False
        notes.append(f"C69a: session fault: {ue or ae or events}")
        return
    flushes = sum(1 for e in events if e.get("name") == "CamouMaskAdd" and e.get("ph") in ("X", "B"))
    notes.append(f"C69a: {flushes} traced flushes; same twice {a == b}; first differs from unconfigured {a['first'] != un['first']}")
    if flushes < C69A_MIN_FLUSHES or a["last"] == un["last"]:
        mark_unmeasured(C69A, f"{flushes} traced flushes (need {C69A_MIN_FLUSHES}), last arcs differ from unconfigured "
                              f"{a['last'] != un['last']}: the queue was not exercised")
        return
    results[C69A] = a == b and a["first"] != un["first"]


if want("c69"):
    c69a_row()

C102 = ("C102 overdraw elision: after 30000 draws (queued, unwalked), a clearRect of the whole canvas drops the queued mask jobs (a "
        "CamouElided trace instant), and the arc drawn after it reads noised; a partial clear, a clipped clear, an alpha or opaque "
        "full-canvas fillRect, and an unseeded page emit none")
# a bare 2D canvas, one task: 30000 iterations of the timing plant's ops (about 4 MB, past Blink's 2 MB auto-flush) queue mask jobs that
# the idle walk cannot reach before the clear. Blink's own overdraw check (CheckOverdraw) decides; it covers clearRect only, so a
# full-canvas fillRect is not elided (reported, not a defect).
ELIDE_SCENE = """() => {""" + HASH_FN + """
  const c = document.createElement('canvas'); c.width = 300; c.height = 200; const x = c.getContext('2d');
  for (let i = 0; i < 30000; i++) { x.fillStyle = i & 1 ? '#f60' : '#06f'; x.beginPath(); x.arc((i * 37) % 300, (i * 91) % 200, 6, 0, 7);
    x.fill(); x.fillRect((i * 13) % 290, (i * 29) % 190, 5, 5); }
  x.save(); __CLEAR__ x.restore();
  x.fillStyle = 'rgb(128,128,128)'; x.beginPath(); x.arc(150, 100, 55.3, 0, Math.PI * 2); x.fill();
  return { h: H(x.getImageData(0, 0, 300, 200).data) };
}"""
ELIDE_ARMS = {
    "full": "x.clearRect(0, 0, 300, 200);",
    "partial": "x.clearRect(0, 0, 299, 200);",
    "clipped": "x.beginPath(); x.rect(0, 0, 150, 200); x.clip(); x.clearRect(0, 0, 300, 200);",
    "alpha-fill": "x.fillStyle = 'rgba(0,0,0,0.5)'; x.fillRect(0, 0, 300, 200);",
    "opaque-fill": "x.fillStyle = '#000'; x.fillRect(0, 0, 300, 200);",
}


def c102_row():
    seed = json.dumps({"canvas:seed": 1111})
    got = {}
    for arm, clear in list(ELIDE_ARMS.items()) + [("full-unseeded", ELIDE_ARMS["full"])]:
        v, ev = traced_events(None if arm == "full-unseeded" else seed, ELIDE_SCENE.replace("__CLEAR__", clear), GL_ROW_FLAGS)
        if v is None:
            mark_unmeasured(C102, f"arm {arm}: {ev}")
            return
        got[arm] = (sum(1 for e in ev if e.get("name") == "CamouElided"), max_arg(ev, "CamouElided", "jobs"), v["h"])
    notes.append("C102 CamouElided (events, max jobs) per arm: " + ", ".join(f"{a} {n}/{j}" for a, (n, j, _) in got.items()))
    noised = got["full"][2] != got["full-unseeded"][2]
    notes.append(f"C102 the arc after the full clear reads {'noised' if noised else 'EQUAL to unseeded'}")
    results[C102] = (got["full"][0] >= 1 and got["full"][1] >= 1 and noised
                     and all(n == 0 for a, (n, _, _) in got.items() if a != "full"))


if want("c102"):
    c102_row()

C100 = ("C100 an arc (non-integer radius), then N one-pixel putImageData far from it, then getImageData of the arc's box, all in one task "
        "(N = 0, 1, 20, 40, 200): each seeded read differs from the unseeded read of the same scene")
# a bare 2D canvas (the default one, GPU-rastered on a GPU host or under CAMOU_SP3A_GPU_CANVAS=1); no await and no read between the draw
# and the final read. The arc is what carries noise (text alone reads stock). The put goes at (290, 5), outside the box that is read.
PUT_BURST = """() => {""" + HASH_FN + """
  const n = __N__;
  const c = document.createElement('canvas'); c.width = 300; c.height = 200;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, 300, 200);
  ctx.fillStyle = 'rgb(128,128,128)'; ctx.beginPath(); ctx.arc(150, 100, 55.3, 0, Math.PI * 2); ctx.fill();
  for (let i = 0; i < n; i++) ctx.putImageData(new ImageData(1, 1), 290, 5);
  return { h: H(ctx.getImageData(90, 40, 120, 120).data) };
}"""


def put_burst_rows():
    # CAMOU_SP3A_PUT_SEED_OFF=1: the mutant, the seeded arm runs unseeded, so every arm must equal raw (UNMEASURED, not PASS).
    # CAMOU_SP3A_PUT_EXTRA: burst sizes after 0, 1, 20 (default 40,200).
    seed = None if os.environ.get("CAMOU_SP3A_PUT_SEED_OFF") == "1" else json.dumps({"canvas:seed": 1111})
    extra = [int(t) for t in os.environ.get("CAMOU_SP3A_PUT_EXTRA", "40,200").split(",") if t]
    differs = {}
    for n in [0, 1, 20] + extra:
        js = PUT_BURST.replace("__N__", str(n))
        a, ea = session(seed, js, extra_flags=GL_ROW_FLAGS, gate=REAL_GPU)
        r, er = session(None, js, extra_flags=GL_ROW_FLAGS, gate=REAL_GPU)
        if a is None or r is None:
            err = ea if a is None else er
            if REAL_GPU and type(err).__name__ == "GpuCrashed":   # a crashed GPU process: no verdict, never FAIL
                mark_unmeasured(C100, f"N={n}: {err}")
            else:
                results[C100] = False
            notes.append(f"C100: N={n}: {err}")
            return
        differs[n] = a["h"] != r["h"]
        notes.append(f"C100 N={n}: seeded {a['h']} raw {r['h']} -> {'differs' if differs[n] else 'EQUALS raw'}")
    if not differs[0]:
        mark_unmeasured(C100, "N=0 equals raw: no noise on this canvas (wrong raster path, or no seed)")
    elif not differs[1]:
        results[C100] = False
        notes.append("C100: N=1 equals raw while N=0 differs")
    else:
        results[C100] = all(differs.values())


if want("c100"):
    put_burst_rows()

C101 = ("C101 a page draws 100 heavy 2D frames (120 paths + 20 text lines each) on one canvas with no read between, then reads it once: the "
        "seeded read is noised (differs from none) and the same in all 3 runs; the read time, seed against none (median of 3), is reported, not "
        "judged: rule D3 pays the backlog's walk at the read")
SOFT_ROWS = SOFT_ROWS + (C101,)
# a main-thread canvas: every frame's recording stays queued (merged past 16) until the one read walks it; a worker's placeholder
# would not show this backlog (a frame past the deferred cap is walked at its commit)
C101_SCENE = """async () => {""" + HASH_FN + """
  __HEAVY__
  const c = document.createElement('canvas'); c.width = 512; c.height = 512;
  for (let i = 0; i < 100; i++) heavy2d(c, i);
  const x = c.getContext('2d');
  const t0 = performance.now(); const data = x.getImageData(0, 0, 512, 512).data; const ms = performance.now() - t0;
  return { ms, h: H(data) };
}""".replace("__HEAVY__", HEAVY2D)


def c101_row():
    runs = {"none": [], "seed": []}
    hashes = {"none": set(), "seed": set()}
    for _ in range(3):
        for arm, cfg in (("none", None), ("seed", json.dumps({"canvas:seed": 1111}))):
            v, e = session(cfg, C101_SCENE, extra_flags=GL_ROW_FLAGS)
            if v is None:
                mark_unmeasured(C101, f"arm {arm}: {e}")
                return
            runs[arm].append(v["ms"])
            hashes[arm].add(v["h"])
    med = {k: sorted(v)[1] for k, v in runs.items()}
    spread = max(runs["none"]) - min(runs["none"])
    soft[C101] = len(hashes["seed"]) == 1 and not (hashes["seed"] & hashes["none"])
    notes.append(f"C101 read ms, median of 3 (reported, rule D3): none {med['none']:.1f} seed {med['seed']:.1f} "
                 f"(the walk at the read: {med['seed'] - med['none']:+.1f}; none spread {spread:.1f}); "
                 f"read hashes none {sorted(hashes['none'])} seed {sorted(hashes['seed'])}")


if want("c101"):
    c101_row()

EXPECTED = 105   # the soft rows (SOFT_ROWS) are not counted

for name, ok in sorted({**results, **soft}.items()):
    print(f"{'UNMEASURED' if name in unmeasured else 'PASS' if ok else 'FAIL'}  {name}")
for name, why in unmeasured.items():
    print(f"      {name[:4]}: UNMEASURED: {why}")

if len(results) != EXPECTED:
    notes.append(f"expected {EXPECTED} criteria, found {len(results)} -- a "
                 "criterion was added/removed without updating EXPECTED")

for note in notes:
    print(f"      {note}")

failed = [n for n, ok in {**results, **soft}.items() if n not in unmeasured and not ok]
hard_unmeasured = [n for n in unmeasured if n not in SOFT_ROWS]
if len(results) == EXPECTED and not failed and not hard_unmeasured:
    print("ALL_PASS")
    sys.exit(0)
if len(results) == EXPECTED and not failed:
    print("UNMEASURED")
    sys.exit(3)
print("FAIL")
sys.exit(1)

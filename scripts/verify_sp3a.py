"""Verifies the SP3a canvas-readback hooks: with canvas:seed set, the pixels
that leave a canvas through EVERY page-reachable readback path carry
deterministic noise, while an unconfigured build stays byte-identical to stock.

Twenty criteria, all driven with Playwright's sync API over content_shell's CDP,
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
  C14 the host oracle's text and shape canvases vary over 8 seeds, none stock.
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
                page.evaluate(f"() => {{ {SCENE_NO_TEXT} document.body.appendChild(c); }}")
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
                           ("reject", REJECT))}
seeded_dec, seeded_dec_err = session(CANVAS, DECODED_IMAGE)
oracle_stock, oracle_stock_err = session(None, ORACLE_CANVAS)
oracle_seeded = [session(json.dumps({"canvas:seed": s}), ORACLE_CANVAS) for s in range(1, 9)]

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

C11 = "11 flat drawings read as unconfigured (solid, edge, 1px line, WebGL clear, worker)"
C12 = "12 putImageData round trip exact"
C13 = "13 drawImage and createImageBitmap copies agree with getImageData"
C15 = "15 text under ctx.scale(40,40) lands within 1 device px of unconfigured"
C16 = "16 decoded image drawn on an eligible canvas reads as unconfigured"
C17 = "17 readPixels at PACK_ALIGNMENT 8, odd width, agrees with the default layout"
C18 = "18 WebGL2 PACK_ROW_LENGTH/SKIP_PIXELS/SKIP_ROWS read agrees with the default read"
C19 = "19 readPixels rect past the buffer: in-buffer part equals the default read, not unconfigured"
C20 = "20 readPixels rejected by GL leaves the buffer untouched"
C14 = "14 oracle text (>=6) and shape (8) canvases vary over 8 seeds, none stock"

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
    results[C14] = (len(texts) >= 6 and len(shapes) == 8
                    and oracle_stock["text"] not in texts and oracle_stock["shape"] not in shapes)
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

EXPECTED = 20

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

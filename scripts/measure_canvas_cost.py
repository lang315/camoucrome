"""Canvas noise cost (S2c spec "Success criteria"): the fork with canvas:seed
against the fork without it, plus a seeded arm at canvas:noiseDensity 0 that
does every copy and replay but no noise (attribution), on WSL content_shell
(CPU raster, SwiftShader GL). Two interleaved rounds; medians.

  per_draw_us  10 x 2000 arcs on a 1024 x 1024 2D canvas, no read: us per draw
  draw_only    10 x 10 000 arcs, no read: ms per frame
  draw_read    10 x (10 000 arcs + getImageData(0,0,1,1)): ms per frame
  read_2d      getImageData(0,0,1,1) after one new arc on 1024 x 1024: ms
  gl_*.large   readPixels 1024 x 1024 (flat scene, 4 px random blocks): ms
  gl_*.small   readPixels 64 x 64 sub-rect: ms
  gl_fbo.*     the same reads from a page framebuffer

Exit 0 always: this is a measurement, not a gate. Each target prints PASS or
MISS; a MISS is recorded with its attribution, not hidden.

The driver sends Runtime.enable (Playwright evaluate) in every arm, so the
absolute times include that overhead; the ratios compare like with like.
Set CAMOU_OUT to measure a build other than ~/chromium/src/out/Default.
"""

import json
import statistics

import lib_shell

GL = lib_shell.SHELL_FLAGS + ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
ARMS = {
    "none": None,
    "seed": json.dumps({"canvas:seed": 987654321}),
    "seed_d0": json.dumps({"canvas:seed": 987654321, "canvas:noiseDensity": 0}),
}

ARCS = """
  const arcs = (x, n, off) => { for (let i = 0; i < n; i++) {
    x.fillStyle = i & 1 ? '#f60' : '#06f'; x.beginPath();
    x.arc(((i + off) * 37) % 1024, ((i + off) * 91) % 1024, 6, 0, 7); x.fill(); } };
  const c = document.createElement('canvas'); c.width = 1024; c.height = 1024;
  const x = c.getContext('2d'); const t = [];
"""

PER_DRAW = "() => {" + ARCS + """
  for (let f = 0; f < 10; f++) { const t0 = performance.now(); arcs(x, 2000, f);
    t.push((performance.now() - t0) / 2000 * 1000); }
  x.getImageData(0, 0, 1, 1); return t; }"""

DRAW_ONLY = "() => {" + ARCS + """
  for (let f = 0; f < 10; f++) { const t0 = performance.now(); arcs(x, 10000, f);
    t.push(performance.now() - t0); }
  x.getImageData(0, 0, 1, 1); return t; }"""

DRAW_READ = "() => {" + ARCS + """
  for (let f = 0; f < 10; f++) { const t0 = performance.now(); arcs(x, 10000, f);
    x.getImageData(0, 0, 1, 1); t.push(performance.now() - t0); }
  return t; }"""

READ_2D = "() => {" + ARCS + """
  arcs(x, 10000, 0); x.getImageData(0, 0, 1, 1);
  for (let f = 0; f < 10; f++) { arcs(x, 1, f * 7 + 1); const t0 = performance.now();
    x.getImageData(0, 0, 1, 1); t.push(performance.now() - t0); }
  return t; }"""


def read_gl(scene, target):
    return """() => {
  const c = document.createElement('canvas'); c.width = 1024; c.height = 1024;
  const gl = c.getContext('webgl', {preserveDrawingBuffer: true});
  if (!gl) return { err: 'no-webgl' };
  if ('""" + target + """' === 'fbo') {
    const tx = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, tx);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1024, 1024, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    const fb = gl.createFramebuffer(); gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tx, 0);
    if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE)
      return { err: 'fbo-incomplete' }; }
  gl.clearColor(0.2, 0.5, 0.8, 1); gl.clear(gl.COLOR_BUFFER_BIT); gl.enable(gl.SCISSOR_TEST);
  if ('""" + scene + """' === 'flat') {
    for (let i = 0; i < 64; i++) { gl.scissor(i * 16, (i * 37) % 1000, 9, 9);
      gl.clearColor((i * 7 % 10) / 10, (i * 3 % 10) / 10, 0.5, 1); gl.clear(gl.COLOR_BUFFER_BIT); }
  } else {
    let s = 1; const r = () => (s = (Math.imul(s, 1103515245) + 12345) >>> 0) / 4294967296;
    for (let y = 0; y < 1024; y += 4) for (let xx = 0; xx < 1024; xx += 4) {
      gl.scissor(xx, y, 4, 4); gl.clearColor(r(), r(), r(), 1); gl.clear(gl.COLOR_BUFFER_BIT); }
  }
  gl.disable(gl.SCISSOR_TEST);
  const time = (n, w, o) => { const p = new Uint8Array(w * w * 4), t = [];
    for (let i = 0; i < n; i++) { const t0 = performance.now();
      gl.readPixels(o, o, w, w, gl.RGBA, gl.UNSIGNED_BYTE, p); t.push(performance.now() - t0); }
    return t; };
  const out = { small: time(50, 64, 100), large: time(20, 1024, 0) };
  if (gl.getError() !== gl.NO_ERROR) return { err: 'gl-error' };
  return out; }"""


CASES = [("per_draw_us", PER_DRAW, None), ("draw_only", DRAW_ONLY, None),
         ("draw_read", DRAW_READ, None), ("read_2d", READ_2D, None),
         ("gl_flat", read_gl("flat", "default"), GL),
         ("gl_edges", read_gl("edges", "default"), GL),
         ("gl_fbo", read_gl("edges", "fbo"), GL)]

# (case, kind, limit): kind "ratio" is seeded / unconfigured, "abs" is the
# seeded median in ms.
TARGETS = [("per_draw_us", "ratio", 1.2), ("draw_read", "ratio", 2.0),
           ("read_2d", "abs", 0.5), ("gl_flat.large", "ratio", 3.0),
           ("gl_edges.large", "ratio", 3.0), ("gl_edges.small", "ratio", 1.5)]

results = {}
for _ in range(2):
    for name, fn, flags in CASES:
        for arm, conf in ARMS.items():
            values, err = lib_shell.session(conf, [fn], navigate_to="about:blank",
                                            extra_flags=flags)
            if err is not None:
                print(f"{name} {arm}: ERROR {err}")
                continue
            v = values[0]
            if isinstance(v, dict) and "err" in v:
                print(f"{name} {arm}: {v['err']}")
                continue
            for key, arr in (v.items() if isinstance(v, dict) else [(None, v)]):
                results.setdefault((f"{name}.{key}" if key else name, arm), []).extend(arr)

med = {k: statistics.median(v) for k, v in results.items()}
for case in sorted({k[0] for k in med}):
    u = med.get((case, "none"))
    cells = []
    for arm in ARMS:
        m = med.get((case, arm))
        if m is None:
            cells.append(f"{arm}=UNMEASURED")
        elif u:
            cells.append(f"{arm}={m:.3f} ({m / u:.2f}x)")
        else:
            cells.append(f"{arm}={m:.3f}")
    print(f"{case:18s} " + "  ".join(cells))
for case, kind, limit in TARGETS:
    s, u = med.get((case, "seed")), med.get((case, "none"))
    if s is None or (kind == "ratio" and not u):
        print(f"target {case} {kind}<={limit}: UNMEASURED")
        continue
    value = s / u if kind == "ratio" else s
    print(f"target {case} {kind}<={limit}: {value:.2f} {'PASS' if value <= limit else 'MISS'}")

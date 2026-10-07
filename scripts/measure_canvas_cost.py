"""Canvas noise S2b cost (spec "Cost, measured"): the fork with canvas:seed
against the fork without it, on WSL content_shell (CPU raster, SwiftShader
GL), so the numbers are this box's, not a GPU host's.

  draw  10 frames of 10 000 arcs on a 1024 x 1024 2D canvas, each frame
        closed by a 1x1 getImageData (which flushes and noises the snapshot)
  read  50 readPixels of 64 x 64 and 20 of 1024 x 1024 from a WebGL canvas

Prints per-run medians and the seeded / unconfigured ratio. Exit 0 always:
this is a measurement, not a gate; the plan records the ratio against the
spec's 2x line.

The driver sends Runtime.enable (Playwright evaluate) in both arms, so absolute
times include that overhead; the ratio compares like with like.
"""

import json
import statistics

import lib_shell

GL_FLAGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
SEEDED = json.dumps({"canvas:seed": 987654321})

DRAW = """() => {
  const c = document.createElement('canvas'); c.width = 1024; c.height = 1024;
  const x = c.getContext('2d'); const t = [];
  for (let f = 0; f < 10; f++) {
    const t0 = performance.now();
    for (let i = 0; i < 10000; i++) {
      x.fillStyle = i & 1 ? '#f60' : '#06f'; x.beginPath();
      x.arc((i * 37) % 1024, (i * 91) % 1024, 6, 0, 7); x.fill(); }
    x.getImageData(0, 0, 1, 1);
    t.push(performance.now() - t0); }
  return t; }"""

READ = """() => {
  const c = document.createElement('canvas'); c.width = 1024; c.height = 1024;
  const gl = c.getContext('webgl'); if (!gl) return { err: 'no-webgl' };
  gl.clearColor(0.2, 0.5, 0.8, 1); gl.clear(gl.COLOR_BUFFER_BIT);
  gl.enable(gl.SCISSOR_TEST);
  for (let i = 0; i < 64; i++) { gl.scissor(i * 16, (i * 37) % 1000, 9, 9);
    gl.clearColor((i * 7 % 10) / 10, (i * 3 % 10) / 10, 0.5, 1); gl.clear(gl.COLOR_BUFFER_BIT); }
  const time = (n, w) => { const p = new Uint8Array(w * w * 4), t = [];
    for (let i = 0; i < n; i++) { const t0 = performance.now();
      gl.readPixels(0, 0, w, w, gl.RGBA, gl.UNSIGNED_BYTE, p); t.push(performance.now() - t0); }
    return t; };
  return { small: time(50, 64), large: time(20, 1024) }; }"""


def run(config, fn, flags=None):
    values, error = lib_shell.session(config, [fn], navigate_to="about:blank",
                                      extra_flags=flags)
    if error is not None:
        raise error
    return values[0]


def ratio(name, seeded, unconf):
    s, u = statistics.median(seeded), statistics.median(unconf)
    if u == 0:
        print(f"{name}: UNMEASURED (unconfigured median 0 ms)")
        return
    print(f"{name}: seeded median {s:.2f} ms, unconfigured median {u:.2f} ms, "
          f"seeded/unconfigured ratio {s / u:.2f}")


GL = lib_shell.SHELL_FLAGS + GL_FLAGS
ratio("draw", run(SEEDED, DRAW), run(None, DRAW))
rs, ru = run(SEEDED, READ, GL), run(None, READ, GL)
if "err" in rs or "err" in ru:
    print(f"readPixels: UNMEASURED ({rs.get('err') or ru.get('err')})")
else:
    ratio("readPixels 64x64", rs["small"], ru["small"])
    ratio("readPixels 1024x1024", rs["large"], ru["large"])

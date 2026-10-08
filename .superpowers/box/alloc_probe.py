import json, statistics, sys
sys.path.insert(0, "/tmp/s2c-tree/scripts")
import lib_shell
GL = lib_shell.SHELL_FLAGS + ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
JS = """() => {
  const t = []; for (let i = 0; i < 20; i++) { const t0 = performance.now();
    const a = new Uint8Array(1026 * 1026 * 4); a.fill(0xFF); const b = new Uint8Array(1026 * 1026 * 4); b.fill(0);
    t.push(performance.now() - t0); }
  const c = document.createElement('canvas'); const gl = c.getContext('webgl');
  const tx = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, tx);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1024, 1024, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
  const fb = gl.createFramebuffer(); gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tx, 0);
  gl.clearColor(0.2, 0.5, 0.8, 1); gl.clear(gl.COLOR_BUFFER_BIT);
  const p = new Uint8Array(1026 * 1026 * 4), r = [], r2 = [];
  for (let i = 0; i < 20; i++) { let t0 = performance.now(); gl.readPixels(-1, -1, 1026, 1026, gl.RGBA, gl.UNSIGNED_BYTE, p); r.push(performance.now() - t0); }
  for (let i = 0; i < 20; i++) { let t0 = performance.now(); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, p); r2.push(performance.now() - t0); }
  return { alloc: t, oob: r, one: r2 }; }"""
for name, conf in (("none", None), ("seed", json.dumps({"canvas:seed": 987654321}))):
    v, e = lib_shell.session(conf, [JS], navigate_to="about:blank", extra_flags=GL)
    v = v[0]
    print(name, "alloc+fill 2x4MB %.2f  oob read %.2f  1px read %.3f" % tuple(statistics.median(v[k]) for k in ("alloc", "oob", "one")))

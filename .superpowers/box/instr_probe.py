import json, statistics, sys
sys.path.insert(0, "/tmp/s2c-tree/scripts")
import lib_shell
GL = lib_shell.SHELL_FLAGS + ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
JS = """() => {
  const c = document.createElement('canvas'); const gl = c.getContext('webgl');
  const tx = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, tx);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1024, 1024, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
  const fb = gl.createFramebuffer(); gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tx, 0);
  gl.clearColor(0.2, 0.5, 0.8, 1); gl.clear(gl.COLOR_BUFFER_BIT);
  const p = new Uint8Array(1024 * 1024 * 4), out = [];
  for (let i = 0; i < 6; i++) { const t0 = performance.now();
    gl.readPixels(0, 0, 1024, 1024, gl.RGBA, gl.UNSIGNED_BYTE, p);
    out.push([performance.now() - t0, ...new Uint32Array(p.buffer, 0, 4)]); }
  return out; }"""
v, e = lib_shell.session(json.dumps({"canvas:seed": 987654321}), [JS], navigate_to="about:blank", extra_flags=GL)
for r in v[0]: print("total %.1f ms; alloc %d us, reads %d us, scan %d us, noise %d us" % (r[0], r[1], r[2], r[3], r[4]))

"""SP3b timing tell: the WebGL unmasked renderer/vendor override must cost what
the real query costs (backlog 4c, step 6 Task 8: BrowserScan reads "WebGL
exception" on a fork with webGl2:renderer set, because getParameter(0x9246)
returned in ~0.3 us against 55-90 us for the stock path to the GPU process).

The page can time getParameter. A configured value that skips the GPU round
trip is visible whatever the value is, so the override must read the real
string first and only then substitute it. No artificial delay.

  T0 probe capability: unconfigured, UNMASKED_RENDERER costs at least 3x the
     control pname (MAX_TEXTURE_SIZE, answered from the client's cache). If it
     does not, the probe measures nothing on this build and the other rows are
     not evidence (FAIL, never a fake pass).
  T1 webgl:   configured median >= RATIO x unconfigured median, for
     UNMASKED_RENDERER and UNMASKED_VENDOR.
  T2 webgl2:  the same on a webgl2 context.
  T3 worker:  the same on an OffscreenCanvas webgl2 context in a dedicated worker.

  T4 parameter table: a webGl:parameters / webGl2:parameters entry for each pname
     whose real query is a GPU round trip (measured 2026-10-24 on SwiftShader:
     SUBPIXEL_BITS, the RED/GREEN/BLUE/ALPHA/DEPTH bits, VERSION,
     SHADING_LANGUAGE_VERSION, SAMPLE_BUFFERS, SAMPLES, the aliased point and
     line ranges, IMPLEMENTATION_COLOR_READ_TYPE/FORMAT) costs the same.
     The cached pnames (MAX_TEXTURE_SIZE and the like) answer in under a
     microsecond configured or not, so they carry no tell.

RATIO is 0.5: the fork's own unconfigured path was measured 1.6x stock, so a
configured path that is within 2x of unconfigured is not separable from noise
by a page, while the tell was 200-300x. Each cost is the median of 15 batches
of 200 calls (microseconds per call).
"""
import json
import sys

import lib_shell

GL_FLAGS = lib_shell.SHELL_FLAGS + ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
RATIO = 0.5
CONFIG = {"webGl:renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00009BC5) Direct3D11 vs_5_0 ps_5_0, D3D11)",
          "webGl:vendor": "Google Inc. (Intel)",
          "webGl2:renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00009BC5) Direct3D11 vs_5_0 ps_5_0, D3D11)",
          "webGl2:vendor": "Google Inc. (Intel)"}

# Runs in the page and in a worker: median microseconds per call for each pname on one context.
MEASURE = """
const med = a => a.slice().sort((x, y) => x - y)[a.length >> 1];
const cost = (gl, pname) => {
  for (let i = 0; i < 200; i++) gl.getParameter(pname);
  const b = [];
  for (let k = 0; k < 15; k++) {
    const t = performance.now();
    for (let i = 0; i < 200; i++) gl.getParameter(pname);
    b.push((performance.now() - t) * 1000 / 200);
  }
  return med(b);
};
const read = (gl) => {
  if (!gl) return null;
  if (!gl.getExtension('WEBGL_debug_renderer_info')) return {err: 'no WEBGL_debug_renderer_info'};
  return {renderer: cost(gl, 0x9246), vendor: cost(gl, 0x9245), control: cost(gl, 0x0D33)};
};
"""
PAGE = "async () => {" + MEASURE + """
  const out = {};
  out.webgl = read(document.createElement('canvas').getContext('webgl'));
  out.webgl2 = read(document.createElement('canvas').getContext('webgl2'));
  const src = `""" + MEASURE.replace("`", "") + """
    self.onmessage = () => { try {
      self.postMessage(read(new OffscreenCanvas(16, 16).getContext('webgl2')) || {err: 'no offscreen webgl2'});
    } catch (e) { self.postMessage({err: String(e)}); } };`;
  out.worker = await new Promise((resolve) => {
    const w = new Worker(URL.createObjectURL(new Blob([src], {type: 'text/javascript'})));
    w.onmessage = (e) => resolve(e.data);
    w.onerror = (e) => resolve({err: e.message || 'worker error'});
    w.postMessage('go');
  });
  return out;
}"""


SLOW = {3408: 4, 3410: 8, 3411: 8, 3412: 8, 3413: 8, 3414: 24, 32936: 0, 32937: 0, 33901: [1, 1024], 33902: [1, 1],
        35738: 5121, 35739: 6408, 7938: "WebGL 1.0 (OpenGL ES 2.0 Chromium)", 35724: "WebGL GLSL ES 1.0 (OpenGL ES GLSL ES 1.0 Chromium)"}
PARAMS_CFG = {"webGl:parameters": {str(k): v for k, v in SLOW.items()},
              "webGl2:parameters": {str(k): v for k, v in SLOW.items()}}
TABLE_PAGE = """() => {
  const med = a => a.slice().sort((x, y) => x - y)[a.length >> 1];
  const out = {};
  for (const kind of ['webgl', 'webgl2']) {
    const gl = document.createElement('canvas').getContext(kind), r = {};
    for (const p of %s) {
      for (let i = 0; i < 20; i++) gl.getParameter(p);
      const b = [];
      for (let k = 0; k < 9; k++) { const t = performance.now(); for (let i = 0; i < 100; i++) gl.getParameter(p); b.push((performance.now() - t) * 10); }
      r[p] = med(b);
    }
    out[kind] = r;
  }
  return out;
}""" % json.dumps(sorted(SLOW))


def measure_table(config):
    vals, err = lib_shell.session(json.dumps(config) if config else None, [TABLE_PAGE], extra_flags=GL_FLAGS)
    return (None, f"{type(err).__name__}: {err}") if err is not None else (vals[0], None)


def measure(config):
    vals, err = lib_shell.session(json.dumps(config) if config else None, [PAGE], extra_flags=GL_FLAGS)
    if err is not None:
        return None, f"{type(err).__name__}: {err}"
    return vals[0], None


def main():
    results, notes = {}, []
    base, e1 = measure(None)
    conf, e2 = measure(CONFIG)
    if base is None or conf is None:
        for k in ("T0", "T1", "T2", "T3"):
            results[k] = False
        notes.append(f"session failed: {e1 or e2}")
    else:
        notes.append("unconfigured us/call: " + json.dumps(base))
        notes.append("configured   us/call: " + json.dumps(conf))
        b = base.get("webgl") or {}
        results["T0 probe capability: unconfigured UNMASKED_RENDERER >= 3x the control pname"] = (
            "renderer" in b and b["renderer"] >= 3 * b["control"])
        for name, scope in (("T1 webgl", "webgl"), ("T2 webgl2", "webgl2"), ("T3 worker offscreen webgl2", "worker")):
            u, c = base.get(scope) or {}, conf.get(scope) or {}
            ok = all(k in u and k in c and c[k] >= RATIO * u[k] for k in ("renderer", "vendor"))
            results[f"{name}: configured UNMASKED_RENDERER/VENDOR cost >= {RATIO} x unconfigured"] = ok
    tb, t1 = measure_table(None)
    tc, t2 = measure_table(PARAMS_CFG)
    if tb is None or tc is None:
        results["T4 parameter table"] = False
        notes.append(f"T4 session failed: {t1 or t2}")
    else:
        for scope in ("webgl", "webgl2"):
            fast = sorted(int(p) for p, v in tc[scope].items() if v < RATIO * tb[scope][p])
            results[f"T4 {scope} parameter table: every GPU-round-trip pname costs >= {RATIO} x unconfigured"] = not fast
            if fast:
                notes.append(f"T4 {scope} configured fast path: pnames {fast} (unconfigured median us: "
                             f"{sorted(round(tb[scope][str(p)]) for p in fast)[:3]}...)")
    for name, passed in sorted(results.items()):
        print(f"{'PASS' if passed else 'FAIL'}  {name}")
    for n in notes:
        print(f"      {n}")
    if len(results) == 6 and all(results.values()):
        print("ALL_PASS")
        return 0
    print("FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())

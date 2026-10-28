#!/usr/bin/env python3
"""Step 6 Task 9: with noise off, a generated identity renders the host's real pixels.

Five fork identities (seeds 1-5, drawn with the host's real renderer and fonts, per-instance
seeds removed) are compared with stock Chrome on the same host: the 2D canvas hashes and a
WebGL readback hash must be equal. Two REDs show the check can fail:
  noise-on   identity 1 with its canvas:seed kept: the 2D hashes must differ from stock;
  macos-gpu  identity 1 forced onto the macOS profile: record whether the readback differs
             (it should not: the pixels stay real) and what the page reads as the renderer.
Run on the Windows host in session 1 (run-interactive.ps1), headed:
  CAMOU_FORK_EXE=...\\chrome.exe python verify_pixels_real.py [--out DIR]
Exit 0 when the five identities equal stock and noise-on differs."""
import argparse
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import measure_step2 as m2  # noqa: E402
import gpu_gate  # noqa: E402
from windows_verify_set import STOCK_APP  # noqa: E402

PAGE = b"""<!doctype html><title>pixels</title><pre id="o"></pre><canvas id="c" width="220" height="40"></canvas><script>
const fnv=s=>{let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)}return (h>>>0).toString(16)};
const out={};
const c=document.getElementById('c'),x=c.getContext('2d');
x.font='16px Arial';x.fillText('Cwm fjordbank glyphs vext quiz 1234',4,26);x.font='16px "Segoe UI"';x.fillText('Cwm fjordbank glyphs vext quiz',4,38);
out.canvasText=fnv(c.toDataURL());
x.clearRect(0,0,220,40);x.fillStyle='#f60';x.beginPath();x.arc(50,20,15,0,7);x.fill();x.fillStyle='rgba(0,80,255,.5)';x.fillRect(40,10,60,20);
out.canvasShape=fnv(c.toDataURL());
const g=document.createElement('canvas');g.width=g.height=128;const gl=g.getContext('webgl');
if(gl){const vs=gl.createShader(gl.VERTEX_SHADER);gl.shaderSource(vs,'attribute vec2 p;varying vec2 v;void main(){v=p;gl_Position=vec4(p,0,1)}');gl.compileShader(vs);
const fs=gl.createShader(gl.FRAGMENT_SHADER);gl.shaderSource(fs,'precision mediump float;varying vec2 v;void main(){gl_FragColor=vec4(0.5+0.5*v.x,0.5+0.5*v.y,fract(v.x*v.y*7.0),1)}');gl.compileShader(fs);
const pr=gl.createProgram();gl.attachShader(pr,vs);gl.attachShader(pr,fs);gl.linkProgram(pr);gl.useProgram(pr);
const b=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1,-0.2,0.3,0.9,-0.8]),gl.STATIC_DRAW);
const l=gl.getAttribLocation(pr,'p');gl.enableVertexAttribArray(l);gl.vertexAttribPointer(l,2,gl.FLOAT,false,0,0);
gl.clearColor(0.1,0.2,0.3,1);gl.clear(gl.COLOR_BUFFER_BIT);gl.drawArrays(gl.TRIANGLE_STRIP,0,4);gl.drawArrays(gl.TRIANGLES,1,3);
const px=new Uint8Array(128*128*4);gl.readPixels(0,0,128,128,gl.RGBA,gl.UNSIGNED_BYTE,px);let h=2166136261;for(let i=0;i<px.length;i++){h^=px[i];h=Math.imul(h,16777619)}
out.webglRead=(h>>>0).toString(16);out.webglUrl=fnv(g.toDataURL());
const d=gl.getExtension('WEBGL_debug_renderer_info');out.renderer=d?gl.getParameter(d.UNMASKED_RENDERER_WEBGL):'none'}else out.webglRead='no context';
document.getElementById('o').textContent=JSON.stringify(out);
</script>"""

HASHES = ("canvasText", "canvasShape", "webglRead", "webglUrl")


def read(pw, arm, ident, config="arm"):
    with m2.serve(PAGE) as url, m2.opened(pw, arm, "headed", ident=ident, config=config) as ctx:
        page = m2.first_page(ctx)
        page.goto(url, wait_until="load")
        page.wait_for_function("document.getElementById('o').textContent !== ''", timeout=60000)
        return json.loads(page.locator("#o").text_content())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    gpu_gate.require_interactive()
    from patchright.sync_api import sync_playwright
    from camoucrome import SEED_KEYS
    stock = m2.Arm("stock", os.path.join(os.environ.get("CAMOU_STOCK_APP", STOCK_APP), "chrome.exe"), None)
    fork_exe = os.environ["CAMOU_FORK_EXE"]
    m2.HOST_DRAW.update(m2.probe_host_draw(fork_exe))
    if not m2.HOST_DRAW["host_renderer"]:
        sys.exit("UNMEASURED: no hardware renderer read from the host")

    def noise_off(ident):
        return {k: v for k, v in ident["config"].items() if k not in SEED_KEYS}

    table = {}
    with sync_playwright() as pw:
        table["stock-1"] = read(pw, stock, None)
        table["stock-2"] = read(pw, stock, None)
        for seed in m2.LINK_SEEDS:
            ident = m2.identity(seed)
            table[f"fork-{seed}"] = read(pw, m2.Arm("fork", fork_exe, ident), ident, config=noise_off(ident))
        ident = m2.identity(1)
        table["red-noise-on"] = read(pw, m2.Arm("fork", fork_exe, ident), ident)
        from camoucrome.gen import generate
        mac = generate("windows", seed=1, gpu="macos-apple-m1-pro-metal", **m2.HOST_DRAW)
        table["red-macos-gpu"] = read(pw, m2.Arm("fork", fork_exe, mac), mac, config=noise_off(mac))

    ref = table["stock-1"]
    verdict = {"stock stable": all(table["stock-2"][h] == ref[h] for h in HASHES)}
    for seed in m2.LINK_SEEDS:
        verdict[f"fork-{seed} equals stock"] = all(table[f"fork-{seed}"][h] == ref[h] for h in HASHES)
    verdict["RED noise-on differs on 2D"] = any(table["red-noise-on"][h] != ref[h] for h in ("canvasText", "canvasShape"))
    verdict["RED macos-gpu readback equals stock (pixels stay real)"] = all(table["red-macos-gpu"][h] == ref[h] for h in HASHES)
    verdict["RED macos-gpu page reads Apple"] = "Apple" in table["red-macos-gpu"].get("renderer", "")
    for name, row in table.items():
        print(name, {h: ("=" if row[h] == ref[h] else row[h]) for h in HASHES}, row.get("renderer", "")[:60])
    for k, v in verdict.items():
        print(("PASS " if v else "FAIL ") + k)
    if a.out:
        out = pathlib.Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "pixels.json").write_text(json.dumps({"table": table, "verdict": verdict}, indent=1), encoding="utf-8")
    must = ["stock stable", "RED noise-on differs on 2D"] + [f"fork-{s} equals stock" for s in m2.LINK_SEEDS]
    return 0 if all(verdict[k] for k in must) else 1


if __name__ == "__main__":
    sys.exit(main())

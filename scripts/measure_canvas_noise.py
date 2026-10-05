"""Canvas noise on the Windows host: the spike's P1-P5 and the redesign's S1/S2
rows, stock Chrome against the fork without config and under N canvas seeds.

Run in the client venv on the host, holding the build lock:
  python measure_canvas_noise.py run [--seeds 8] [--density D] [--mode headed|headless] [--out DIR] [--label L]
Prints one verdict line per row and writes the cells to DIR/<label>.json.
Spec: docs/superpowers/specs/2026-10-05-canvas-noise-redesign-design.md.
"""
import argparse
import datetime
import json
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# text/shape: the oracle's own canvas step (capture_host_oracle.py). textBig: the
# same text on a 512x128 canvas, large enough to be a GPU canvas candidate.
# textCpu: willReadFrequently, the CPU raster path. solid/edge/line/glClear: flat
# drawings that must read as stock (the 2D ones carry a corner arc so the canvas
# is eligible, and are read as 48x48 away from it). roundtrip: putImageData of a random opaque
# pattern over text, read back. copy/bitmap: drawImage and createImageBitmap at a
# 1px offset agree with getImageData (the source is opaque, so the destination's
# own arc cannot show through). shift: text at x and x+1 differ only by the
# shift.
PAGE = b"""<!doctype html><title>canvas-noise</title><pre id="o"></pre><script>
const fnv=s=>{let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)>>>0}return h.toString(16)};
const H=d=>{let h=2166136261;for(let i=0;i<d.length;i++){h^=d[i];h=Math.imul(h,16777619)>>>0}return h.toString(16)};
const distinct=d=>{const s=new Set();for(let i=0;i<d.length;i+=4)s.add(d[i]+','+d[i+1]+','+d[i+2]+','+d[i+3]);return s.size};
const mk=(w,h,o)=>{const c=document.createElement('canvas');c.width=w;c.height=h;return [c,c.getContext('2d',o)]};
const text=(x,dx)=>{dx=dx||0;x.font='16px Arial';x.fillText('Cwm fjordbank glyphs vext quiz 1234',4+dx,26);x.font='16px "Segoe UI"';x.fillText('Cwm fjordbank glyphs vext quiz',4+dx,38)};
const arc=x=>{x.fillStyle='#f60';x.beginPath();x.arc(58,58,4,0,7);x.fill()};
const shape=x=>{x.fillStyle='#f60';x.beginPath();x.arc(50,20,15,0,7);x.fill();x.fillStyle='rgba(0,80,255,.5)';x.fillRect(40,10,60,20)};
const same=(a,b)=>{if(a.length!==b.length)return false;for(let i=0;i<a.length;i++)if(a[i]!==b[i])return false;return true};
(async()=>{const out={};
let [c,x]=mk(220,40);text(x);out.text=fnv(c.toDataURL());
[c,x]=mk(220,40);shape(x);out.shape=fnv(c.toDataURL());
[c,x]=mk(512,128);text(x);out.textBig=fnv(c.toDataURL());
[c,x]=mk(220,40,{willReadFrequently:true});text(x);out.textCpu=fnv(c.toDataURL());
[c,x]=mk(64,64);x.fillStyle='rgb(10,20,30)';x.fillRect(0,0,64,64);arc(x);let d=x.getImageData(0,0,48,48).data;out.solid=H(d);out.solidColours=distinct(d);
[c,x]=mk(64,64);x.fillStyle='rgb(10,20,30)';x.fillRect(0,0,64,64);x.fillStyle='rgb(200,100,50)';x.fillRect(0,0,32,64);arc(x);out.edge=H(x.getImageData(0,0,48,48).data);
[c,x]=mk(64,64);x.strokeStyle='rgb(200,100,50)';x.lineWidth=1;x.beginPath();x.moveTo(0,10.5);x.lineTo(64,10.5);x.stroke();arc(x);out.line=H(x.getImageData(0,0,48,48).data);
[c,x]=mk(64,64);text(x);x.fillStyle='#f60';x.beginPath();x.arc(32,32,10,0,7);x.fill();const img=x.createImageData(64,64);let s=12345;
for(let i=0;i<img.data.length;i+=4){for(let k=0;k<3;k++){s=(Math.imul(s,1103515245)+12345)>>>0;img.data[i+k]=s>>>24}img.data[i+3]=255}
x.putImageData(img,0,0);out.roundtrip=same(x.getImageData(0,0,64,64).data,img.data);
[c,x]=mk(220,40);x.fillStyle='#fff';x.fillRect(0,0,220,40);x.fillStyle='#000';text(x);shape(x);const a=x.getImageData(0,0,220,40).data;
let [b,y]=mk(221,40);y.fillStyle='#f60';y.beginPath();y.arc(110,20,15,0,7);y.fill();y.drawImage(c,1,0);out.copy=same(y.getImageData(1,0,220,40).data,a);
const bm=await createImageBitmap(c);[b,y]=mk(221,40);y.fillStyle='#f60';y.beginPath();y.arc(110,20,15,0,7);y.fill();y.drawImage(bm,1,0);out.bitmap=same(y.getImageData(1,0,220,40).data,a);
[c,x]=mk(220,40);text(x);[b,y]=mk(221,40);text(y,1);out.shift=same(y.getImageData(1,0,220,40).data,x.getImageData(0,0,220,40).data);
const g=document.createElement('canvas');g.width=g.height=64;const gl=g.getContext('webgl');
if(gl){gl.clearColor(10/255,20/255,30/255,1);gl.clear(gl.COLOR_BUFFER_BIT);const p=new Uint8Array(64*64*4);gl.readPixels(0,0,64,64,gl.RGBA,gl.UNSIGNED_BYTE,p);out.glClear=H(p);out.glClearColours=distinct(p)}else out.glClear='no context';
document.getElementById('o').textContent=JSON.stringify(out)})().catch(e=>{document.getElementById('o').textContent=JSON.stringify({error:String(e)})});
</script>"""

FLAT = ("solid", "edge", "line", "glClear")


def _distinct_unlike(values, stock, need):
    got = set(values)
    return (len(got) >= need and stock not in got,
            f"{len(got)} distinct of {len(values)}, stock among them: {stock in got}")


def verdicts(stock, unconfigured, seeded):
    """(name, ok, detail) rows; ok is None when the row measured nothing."""
    n = len(seeded)
    out = []
    # A missing WebGL context ('no context', no glClearColours) leaves P3 and S1 unmeasured.
    nogl = [name for name, c in [("stock", stock)] + [(f"seed {i}", c) for i, c in enumerate(seeded, 1)]
            if c.get("glClear") == "no context"]
    nogl_d = "no WebGL context in: " + ", ".join(nogl) if nogl else ""
    ok, d = _distinct_unlike([c["textBig"] for c in seeded], stock["textBig"], min(6, n))
    out.append(("P1 text, 512x128 canvas, varies across seeds", ok, d))
    ok, d = _distinct_unlike([c["textCpu"] for c in seeded], stock["textCpu"], min(6, n))
    out.append(("P2 text, willReadFrequently canvas, varies across seeds", ok, d))
    bad = sorted({k for c in seeded for k in FLAT if c.get(k) != stock.get(k)})
    rt = all(c["roundtrip"] for c in seeded)
    out.append(("P3 flat drawings equal stock, putImageData round trip exact",
                None if nogl else not bad and rt, nogl_d or f"differ: {bad}, round trip exact: {rt}"))
    cp = all(c["copy"] and c["bitmap"] for c in seeded)
    out.append(("P4 drawImage and createImageBitmap agree with getImageData", cp, f"all agree: {cp}"))
    if not stock["shift"]:
        out.append(("P5 text at x and x+1 differ only by the shift", None, "stock itself differs"))
    else:
        sh = all(c["shift"] for c in seeded)
        out.append(("P5 text at x and x+1 differ only by the shift", sh, f"all equal: {sh}"))
    ok, d = _distinct_unlike([c["text"] for c in seeded], stock["text"], min(6, n))
    out.append(("S2 oracle text canvas varies (>=6 distinct)", ok, d))
    ok, d = _distinct_unlike([c["shape"] for c in seeded], stock["shape"], n)
    out.append(("S2 oracle shape canvas varies (all distinct)", ok, d))
    colours = [] if nogl else sorted({(c["solidColours"], c["glClearColours"]) for c in seeded})
    out.append(("S1 solid fill and WebGL clear read one colour",
                None if nogl else colours == [(1, 1)], nogl_d or f"colours: {colours}"))
    off = sorted(k for k in stock if unconfigured.get(k) != stock[k])
    out.append(("rule 5: the fork without config reads as stock", not off, f"differ: {off}"))
    return out


def run_cmd(a):
    from patchright.sync_api import sync_playwright

    import measure_step2 as m2
    import step2_rows as rows
    from windows_verify_set import STOCK_APP, pin_tag

    client = os.environ.get("CAMOU_CLIENT", str(HERE.parent))
    stock_exe = os.path.join(os.environ.get("CAMOU_STOCK_APP", STOCK_APP), "chrome.exe")
    fork_exe = os.environ["CAMOU_FORK_EXE"]
    bad = rows.version_problems({"control": m2.exe_version(stock_exe), "fork": m2.exe_version(fork_exe)},
                                pin_tag(client))
    if bad:
        sys.exit("precondition: " + "; ".join(bad))
    extra = {} if a.density is None else {"canvas:noiseDensity": a.density}

    def cell(pw, exe, config):
        with m2.serve(PAGE) as url, m2.opened(pw, m2.Arm("x", exe, None), a.mode, config=config) as ctx:
            page = m2.first_page(ctx)
            page.goto(url, wait_until="load")
            page.wait_for_function("document.getElementById('o').textContent !== ''", timeout=60000)
            got = json.loads(page.locator("#o").text_content())
        if "error" in got:
            sys.exit(f"page error: {got['error']}")
        return got

    with sync_playwright() as pw:
        stock = cell(pw, stock_exe, None)
        unconfigured = cell(pw, fork_exe, None)
        seeded = [cell(pw, fork_exe, {"canvas:seed": s, **extra}) for s in range(1, a.seeds + 1)]
    rows_out = verdicts(stock, unconfigured, seeded)
    label = a.label or datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = pathlib.Path(a.out or tempfile.gettempdir())
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{label}.json").write_text(json.dumps(
        {"mode": a.mode, "density": a.density, "stock": stock, "unconfigured": unconfigured,
         "seeded": seeded, "verdicts": rows_out}, indent=1), encoding="utf-8")
    for name, ok, detail in rows_out:
        print(f"{'UNMEASURED' if ok is None else 'PASS' if ok else 'FAIL'}  {name}  ({detail})")
    print(f"cells: {out_dir / (label + '.json')}")
    return 0


def _seeds(v):
    n = int(v)
    if n < 1:
        raise argparse.ArgumentTypeError(f"--seeds must be at least 1, got {n}")
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--seeds", type=_seeds, default=8)
    r.add_argument("--density", type=float)
    r.add_argument("--mode", choices=("headed", "headless"), default="headed")
    r.add_argument("--out")
    r.add_argument("--label")
    a = ap.parse_args(argv)
    return run_cmd(a)


if __name__ == "__main__":
    sys.exit(main())

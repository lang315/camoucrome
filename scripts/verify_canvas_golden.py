"""Golden corpus of seeded canvas readbacks: a read-path cut must not change one noised pixel.

  verify_canvas_golden.py capture --out FILE     write {case: sha256} for every case
  verify_canvas_golden.py check --golden FILE    rc 0 all equal; 1 one line per differing case; 3 UNMEASURED

Each case draws on a fresh canvas and reads it back with a fixed canvas:seed. The page returns the bytes
(base64); the SHA-256 is taken here. Run on the box with CAMOU_SP3A_GPU_CANVAS=1: noise is only put on
GPU-rastered pixels, so a CPU canvas reads exact and the corpus would measure nothing (rc 3).
The golden file is box-local (~/camoucrome-verify/golden-canvas-<box sha>.json) and never committed.
"""
import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SEED = json.dumps({"canvas:seed": 987654321})
GPU_CANVAS = os.environ.get("CAMOU_SP3A_GPU_CANVAS") == "1"
CASE_NAMES = ["kinds_aa", "kinds_imported", "kinds_clear", "solid_opaque_cover", "solid_alpha", "text",
              "clip_transform", "layers", "harness_ops_64", "harness_ops_4096", "region_read", "idle_then_read",
              "wrf_canvas", "switch_after_gpu", "read_then_drawimage", "over_cap",
              "rect_int_clip", "rect_aa_clip", "rect_scale2", "rect_rotate", "rect_translate_half", "rect_huge",
              "rect_skew", "rect_circle_clip"]
EXPECTED_CASES = 24  # harness_ops counts twice
_HEX = re.compile(r"^[0-9a-f]{64}$")


def capture_doc(hashes):
    """The golden document: exactly the case names, each a SHA-256 hex."""
    if set(hashes) != set(CASE_NAMES):
        raise ValueError(f"cases {sorted(set(hashes) ^ set(CASE_NAMES))} missing or extra")
    for k, v in hashes.items():
        if not isinstance(v, str) or not _HEX.match(v):
            raise ValueError(f"{k}: not a sha256 hex")
    return {k: hashes[k] for k in CASE_NAMES}


def check(golden, now):
    """(rc, lines): 1 with one line per differing, missing or extra case, else 0."""
    lines = []
    for name in CASE_NAMES:
        if name not in golden:
            lines.append(f"{name}: missing in golden")
        elif name not in now:
            lines.append(f"{name}: missing in this run")
        elif golden[name] != now[name]:
            lines.append(f"{name}: DIFFERS golden {golden[name][:12]} now {now[name][:12]}")
    for name in sorted((set(golden) | set(now)) - set(CASE_NAMES)):
        lines.append(f"{name}: not a corpus case")
    return (1 if lines else 0), lines


# The exact canvasOps of measure_timing_parity.py.
CORPUS_JS = r"""async () => {
  const b64 = (u8) => { let s = ''; for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000)); return btoa(s); };
  const mk = (w = 256, h = 256, o) => { const c = document.createElement('canvas'); c.width = w; c.height = h; return [c, c.getContext('2d', o)]; };
  const read = (x, a = 0, b = 0, w = 256, h = 256) => b64(new Uint8Array(x.getImageData(a, b, w, h).data.buffer));
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const raf = () => new Promise((r) => requestAnimationFrame(() => r()));
  const canvasOps = (cx, n, s = 0) => { for (let i = s; i < s + n; i++) { cx.fillStyle = i & 1 ? '#f60' : '#06f'; cx.beginPath(); cx.arc((i * 37) % 256, (i * 91) % 256, 6, 0, 7); cx.fill(); cx.fillRect((i * 13) % 250, (i * 29) % 250, 5, 5); } };
  const solidBg = (x) => { x.fillStyle = '#fff'; x.fillRect(0, 0, 256, 256); };
  const out = {};
  { const [, x] = mk(); const g = x.createLinearGradient(0, 0, 256, 256); g.addColorStop(0, '#f00'); g.addColorStop(0.5, '#0c8'); g.addColorStop(1, '#12f');
    x.fillStyle = g; x.beginPath(); x.arc(120, 120, 80, 0, 7); x.fill();
    x.shadowColor = 'rgba(0,0,0,.6)'; x.shadowBlur = 9; x.shadowOffsetX = 5; x.fillStyle = '#fa0'; x.beginPath(); x.arc(60, 190, 30, 0, 7); x.fill();
    x.shadowBlur = 0; x.shadowOffsetX = 0; x.filter = 'blur(2px)'; x.fillStyle = '#909'; x.beginPath(); x.arc(190, 60, 25, 0, 7); x.fill();
    out.kinds_aa = read(x); }
  { const [, x] = mk(); const [p0, px] = mk(16, 16); px.fillStyle = '#c33'; px.fillRect(0, 0, 8, 8); px.fillStyle = '#39c'; px.fillRect(8, 8, 8, 8);
    x.fillStyle = x.createPattern(p0, 'repeat'); x.beginPath(); x.arc(100, 100, 70, 0, 7); x.fill();
    x.drawImage(p0, 150.5, 20.5, 60, 60); const id = new ImageData(32, 32); for (let i = 0; i < id.data.length; i++) id.data[i] = (i * 7) & 255;
    x.putImageData(id, 10, 200); out.kinds_imported = read(x); }
  { const [, x] = mk(); canvasOps(x, 40); x.clearRect(30, 30, 90, 90);
    x.globalCompositeOperation = 'destination-out'; x.fillStyle = '#000'; x.fillRect(150, 150, 60, 60); x.beginPath(); x.arc(200, 60, 30, 0, 7); x.fill();
    out.kinds_clear = read(x); }
  { const [, x] = mk(); x.fillStyle = '#e33'; x.beginPath(); x.arc(128, 128, 70, 0, 7); x.fill(); x.fillStyle = '#fff'; x.fillRect(0, 0, 256, 256);
    x.fillStyle = '#06f'; x.fillRect(10, 10, 100, 100); out.solid_opaque_cover = read(x); }
  { const [, x] = mk(); solidBg(x); x.fillStyle = 'rgba(200,30,30,.5)'; x.fillRect(20, 20, 120, 120); x.fillStyle = 'rgba(30,30,200,.3)'; x.fillRect(80, 80, 120, 120);
    out.solid_alpha = read(x); }
  { const [, x] = mk(); solidBg(x); x.font = '28px sans-serif'; x.fillStyle = '#123'; x.fillText('Camou 0123 fi', 10, 50);
    const [p0, px] = mk(8, 8); px.fillStyle = '#c33'; px.fillRect(0, 0, 4, 4); x.fillStyle = x.createPattern(p0, 'repeat'); x.font = 'bold 40px serif'; x.fillText('Pat', 20, 120);
    x.strokeStyle = '#a0a'; x.strokeText('stroke', 20, 200); out.text = read(x); }
  { const [, x] = mk(); x.save(); x.translate(128, 128); x.rotate(0.6); x.scale(1.7, 0.8); x.beginPath(); x.moveTo(-60, -40); x.lineTo(70, -20); x.lineTo(20, 60); x.closePath(); x.clip();
    x.fillStyle = '#2a7'; x.fillRect(-100, -100, 200, 200); x.fillStyle = '#e50'; x.beginPath(); x.arc(0, 0, 40, 0, 7); x.fill(); x.restore();
    x.save(); x.beginPath(); x.rect(10, 200, 100, 40); x.clip(); x.fillStyle = '#05f'; x.beginPath(); x.arc(60, 220, 50, 0, 7); x.fill(); x.restore(); out.clip_transform = read(x); }
  { const [, x] = mk(); x.save(); x.globalAlpha = 0.5; x.fillStyle = '#f00'; x.beginPath(); x.arc(90, 90, 60, 0, 7); x.fill(); x.restore();
    x.save(); x.filter = 'drop-shadow(4px 4px 3px #000)'; x.fillStyle = '#0a0'; x.beginPath(); x.arc(160, 160, 50, 0, 7); x.fill(); x.restore();
    x.fillStyle = '#00f'; x.beginPath(); x.arc(200, 60, 20, 0, 7); x.fill(); out.layers = read(x); }
  for (const n of [64, 4096]) { const [, x] = mk(); canvasOps(x, n); out['harness_ops_' + n] = read(x); }
  { const [, x] = mk(); canvasOps(x, 200); out.region_read = read(x, 100, 100, 40, 40); }
  { const [, x] = mk(); canvasOps(x, 80); await raf(); await sleep(200); canvasOps(x, 80); out.idle_then_read = read(x); }
  { const [, x] = mk(256, 256, { willReadFrequently: true }); canvasOps(x, 200); out.wrf_canvas = read(x); }
  { const [, x] = mk(); canvasOps(x, 100); await raf(); read(x, 0, 0, 8, 8); for (let i = 0; i < 9; i++) read(x, 0, 0, 8, 8);
    canvasOps(x, 100); out.switch_after_gpu = read(x); }
  { const [c1, x1] = mk(); canvasOps(x1, 150); const a = read(x1); const [, x2] = mk(); x2.drawImage(c1, 0, 0); out.read_then_drawimage = a + '|' + read(x2); }
  // Attached, with a 25 ms busy wait per frame: an idle period between frames would walk the queue and the 16-job cap
  // would never be reached (measured with the Task 3 instrument: 20 flushes, 4 dropped, 16 walked by the read). Each frame draws
  // other pixels (start f * 12): a dropped job's pixels must not be redrawn by a later one, or the drop is invisible.
  { const [c, x] = mk(); document.body.appendChild(c);
    for (let f = 0; f < 20; f++) { canvasOps(x, 12, f * 12); const t = performance.now(); while (performance.now() - t < 25); await raf(); }
    out.over_cap = read(x); c.remove(); }
  // The aligned-rect fast path of the walk (canvas-walk-fastpath): each case draws aa arcs first, then an opaque
  // integer fillRect that the fast path must take (rect_int_clip, rect_scale2, rect_huge) or must leave to the
  // raster (the others): a wrong predicate marks the rect's bounds where the raster covers less, and the arcs'
  // aa cells that the raster keeps are cleared.
  const arcs = (x) => { for (let i = 0; i < 300; i++) { x.fillStyle = i & 1 ? '#f60' : '#06f'; x.beginPath(); x.arc((i * 37) % 256, (i * 91) % 256, 6, 0, 7); x.fill(); } };
  const white = (x) => { x.fillStyle = '#fff'; };
  { const [, x] = mk(); arcs(x); x.save(); x.beginPath(); x.rect(20, 20, 150, 150); x.clip(); white(x); x.fillRect(40, 40, 100, 100); x.restore(); out.rect_int_clip = read(x); }
  { const [, x] = mk(); arcs(x); x.save(); x.beginPath(); x.rect(10.5, 10.5, 150, 150); x.clip(); white(x); x.fillRect(40, 40, 100, 100); x.fillRect(0, 0, 256, 256); x.restore(); out.rect_aa_clip = read(x); }
  { const [, x] = mk(); arcs(x); x.save(); x.scale(2, 2); white(x); x.fillRect(20, 20, 60, 60); x.restore(); out.rect_scale2 = read(x); }
  { const [, x] = mk(); arcs(x); x.save(); x.rotate(0.3); white(x); x.fillRect(60, 20, 80, 80); x.restore(); out.rect_rotate = read(x); }
  { const [, x] = mk(); arcs(x); x.save(); x.translate(0.5, 0); white(x); x.fillRect(40, 40, 100, 100); x.restore(); out.rect_translate_half = read(x); }
  { const [, x] = mk(); arcs(x); white(x); x.fillRect(-40000, 0, 80256, 256); out.rect_huge = read(x); }
  { const [, x] = mk(); arcs(x); x.save(); x.transform(1, 0, 1, 1, 0, 0); white(x); x.fillRect(10, 10, 60, 60); x.restore(); out.rect_skew = read(x); }
  { const [, x] = mk(); arcs(x); x.save(); x.beginPath(); x.arc(128, 128, 80, 0, 7); x.clip(); white(x); x.fillRect(40, 40, 176, 176); x.restore(); out.rect_circle_clip = read(x); }
  return out;
}"""

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


def _sha(b64s):
    """SHA-256 of the page's base64 text (one-to-one with the bytes)."""
    return hashlib.sha256(b64s.encode()).hexdigest()


def run_corpus():
    """(hashes, None) or (None, rc). rc 3 = UNMEASURED (not a GPU canvas, or the session failed)."""
    import lib_shell
    flags = lib_shell.SHELL_FLAGS + ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] if GPU_CANVAS else None
    probe, err = lib_shell.session(None, [f"({CPU_PROBE})()"], navigate_to="about:blank", extra_flags=flags)
    if probe is None:
        print(f"UNMEASURED: the probe session failed ({err})")
        return None, 3
    if not probe[0]["diff"]:
        print("UNMEASURED: the default 2D canvas is a CPU canvas (reads exact): the corpus measures nothing. "
              "Run with CAMOU_SP3A_GPU_CANVAS=1")
        return None, 3
    vals, err = lib_shell.session(SEED, [f"({CORPUS_JS})()"], navigate_to="about:blank", extra_flags=flags)
    if vals is None:
        print(f"UNMEASURED: the corpus session failed ({err})")
        return None, 3
    return {k: _sha(v) for k, v in vals[0].items()}, None


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("capture").add_argument("--out", required=True)
    sub.add_parser("check").add_argument("--golden", required=True)
    a = ap.parse_args(argv)
    hashes, rc = run_corpus()
    if rc:
        return rc
    if a.cmd == "capture":
        doc = capture_doc(hashes)
        with open(a.out, "w") as f:
            json.dump(doc, f, indent=1)
        print(f"captured {len(doc)} cases -> {a.out}")
        return 0
    with open(a.golden) as f:
        golden = json.load(f)
    rc, lines = check(golden, hashes)
    for l in lines:
        print(l)
    print(f"{'GOLDEN_OK' if rc == 0 else 'GOLDEN_DIFF'}: {len(hashes)} cases")
    return rc


if __name__ == "__main__":
    sys.exit(main())

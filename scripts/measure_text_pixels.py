#!/usr/bin/env python3
"""Can a page see textMetrics:seed jitter in rendered pixels? For each cell (font x size x string)
the page records the full measureText result, the pixel bbox of fillText from getImageData, and a
width probe (pixels whose alpha differs between fillText(s+s) and two fillText(s) calls placed by
measureText(s).width). A field is VISIBLE when the pixel-minus-metric edge delta moves against the
baseline arm by more than 0.5 px (antialias tolerance), or when the probe count changes.

  measure_text_pixels.py --exe <chrome>

Arms: stock twice, textMetrics:seed 1..5, canvas:seed:1 alone (noise control), and canvas:seed:1 +
textMetrics:seed:1 (compared against canvas:seed:1 alone, not stock). Exit 3 + UNMEASURED when the
second stock run is not stable or a jitter arm moves nothing. Launch mirrors measure_audio_text.py
(--dump-dom, no CDP). Not measured: fontBoundingBox*, emHeight*, baselines (no pixel shows them).
"""
import argparse
import html
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

FONTS = ["DejaVu Sans", "Liberation Serif", "monospace", "Arial"]
SIZES = [16, 48, 120]
STRINGS = ["Hxg", "The quick brown fox", "ÅÉgjpqy", "mmmm", "Ω≈ç√"]
X0, Y0 = 200, 250
TOL = 0.5
FIELDS = {"left": 0, "ascent": 1, "right": 2, "descent": 3}  # field -> edge index of metric_box

PROBE = r"""<!doctype html><meta charset="utf-8"><pre id="r">pending</pre><script>
(() => {
  const FONTS = __FONTS__, SIZES = __SIZES__, STRINGS = __STRINGS__, X0 = __X0__, Y0 = __Y0__;
  const out = {cells: {}};
  try {
    const c = document.createElement('canvas'); c.width = 2000; c.height = 400;
    const g = c.getContext('2d', {willReadFrequently: true});
    const alpha = () => { const d = g.getImageData(0, 0, 2000, 400).data, a = new Uint8Array(2000 * 400);
      for (let i = 0; i < a.length; i++) a[i] = d[i * 4 + 3]; return a; };
    const clear = () => { g.clearRect(0, 0, 2000, 400); };
    for (const f of FONTS) for (const sz of SIZES) for (const s of STRINGS) {
      clear();
      g.font = sz + 'px ' + (f === 'monospace' ? f : '"' + f + '"');
      g.fillStyle = '#000'; g.textBaseline = 'alphabetic'; g.textAlign = 'left';
      const t = g.measureText(s), m = {};
      for (const k in t) if (typeof t[k] === 'number') m[k] = t[k];
      g.fillText(s, X0, Y0);
      const a = alpha(); let x0 = 2000, y0 = 400, x1 = -1, y1 = -1;
      for (let y = 0; y < 400; y++) for (let x = 0; x < 2000; x++) if (a[y * 2000 + x] > 0) {
        if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
      const bbox = x1 < 0 ? null : [x0, y0, x1 + 1, y1 + 1];
      clear(); g.fillText(s + s, X0, Y0); const one = alpha();
      clear(); g.fillText(s, X0, Y0); g.fillText(s, X0 + t.width, Y0); const two = alpha();
      let probe = 0; for (let i = 0; i < one.length; i++) if (one[i] !== two[i]) probe++;
      out.cells[f + '|' + sz + '|' + s] = {m, bbox, probe};
    }
    out.done = true;
  } catch (e) { out.error = String(e); }
  document.getElementById('r').textContent = JSON.stringify(out);
})();
</script>"""
for _k, _v in {"__FONTS__": FONTS, "__SIZES__": SIZES, "__STRINGS__": STRINGS, "__X0__": X0, "__Y0__": Y0}.items():
    PROBE = PROBE.replace(_k, json.dumps(_v, ensure_ascii=False))


def bbox_from_alpha(alpha, width, height):
    xs = [i % width for i, a in enumerate(alpha) if a > 0]
    if not xs:
        return None
    ys = [i // width for i, a in enumerate(alpha) if a > 0]
    return (min(xs), min(ys), max(xs) + 1, max(ys) + 1)


def metric_box(m, x0, y0):
    return (x0 - m["actualBoundingBoxLeft"], y0 - m["actualBoundingBoxAscent"],
            x0 + m["actualBoundingBoxRight"], y0 + m["actualBoundingBoxDescent"])


def _deltas(c):
    if c["bbox"] is None:
        return None
    return [p - q for p, q in zip(c["bbox"], metric_box(c["m"], X0, Y0))]


def raw_hist(cells, field):
    """Histogram of the raw edge delta (pixel - metric) rounded to 0.25 px, over cells that drew."""
    h = {}
    for c in cells.values():
        d = _deltas(c)
        if d is not None:
            k = round(d[FIELDS[field]] * 4) / 4 + 0.0  # + 0.0 turns -0.0 into 0.0
            h[k] = h.get(k, 0) + 1
    return dict(sorted(h.items()))


def probe_summary(cells):
    p = sorted(c["probe"] for c in cells.values())
    return (p[0], p[len(p) // 2], p[-1])


def visible_fields(stock, arm, tol=TOL):
    """field -> sorted cell ids where that field moved in pixels against the baseline."""
    out = {}
    for cid, s in stock.items():
        a = arm[cid]
        ds, da = _deltas(s), _deltas(a)
        if (ds is None) != (da is None):  # one side drew nothing: every edge changed
            hits = list(FIELDS)
        elif ds is None:
            hits = []
        else:
            hits = [f for f, i in FIELDS.items() if abs(da[i] - ds[i]) > tol]
        if s["probe"] != a["probe"]:
            hits.append("probe")
        for f in hits:
            out.setdefault(f, []).append(cid)
    return {f: sorted(v) for f, v in out.items()}


def visible_cells(stock, arm, tol=TOL):
    return sorted({c for v in visible_fields(stock, arm, tol).values() for c in v})


def moved_cells(stock, arm):
    return sorted(cid for cid, s in stock.items() if s["m"] != arm[cid]["m"])


def parse(dom):
    m = re.search(r'<pre id="r">(.*?)</pre>', dom, re.S)
    if not m:
        return None
    try:
        got = json.loads(html.unescape(m.group(1)))
    except ValueError:
        return None
    return got if isinstance(got, dict) and got.get("done") is True else None


def clean_env(environ, config):
    env = {k: v for k, v in environ.items() if not k.startswith(("CAMOU_CONFIG", "CAMOU_PRESET"))}
    if config:
        env["CAMOU_CONFIG"] = config
    return env


def launch(exe, config, page):
    prof = tempfile.mkdtemp(prefix="tp-")
    argv = [exe, "--headless=new", "--no-first-run", "--no-default-browser-check",
            f"--user-data-dir={prof}", "--virtual-time-budget=20000", "--dump-dom", page.as_uri()]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=300, env=clean_env(os.environ, config))
        return parse(p.stdout)
    except subprocess.TimeoutExpired:
        return None
    finally:
        shutil.rmtree(prof, ignore_errors=True)


def report(name, base_name, base, arm):
    n = len(base)
    vf = visible_fields(base, arm)
    mv = moved_cells(base, arm)
    vis = visible_cells(base, arm)
    per = " ".join(f"{f}={len(vf.get(f, []))}" for f in [*FIELDS, "probe"])
    print(f"ARM {name} vs {base_name}: moved {len(mv)}/{n} visible {len(vis)}/{n} | per-field visible {per}")
    for cid in vis[:5]:
        ds, da = _deltas(base[cid]), _deltas(arm[cid])
        d = None if ds is None or da is None else [round(y - x, 3) for x, y in zip(ds, da)]
        print(f"  {cid}: edge-delta change (l,t,r,b)={d} probe {base[cid]['probe']}->{arm[cid]['probe']}")
    return len(mv), len(vis)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    a = ap.parse_args(argv)
    pagedir = pathlib.Path(tempfile.mkdtemp(prefix="tp-page-"))
    page = pagedir / "probe.html"
    page.write_text(PROBE, encoding="utf-8")
    try:
        arms = [("stock1", None), ("stock2", None)]
        arms += [(f"tm{i}", json.dumps({"textMetrics:seed": i})) for i in range(1, 6)]
        arms += [("canvas1", json.dumps({"canvas:seed": 1})),
                 ("canvas1+tm1", json.dumps({"canvas:seed": 1, "textMetrics:seed": 1}))]
        got = {}
        for name, cfg in arms:
            r = launch(a.exe, cfg, page)
            if r is None:
                print(f"UNMEASURED arm {name}: probe did not finish")
                return 3
            got[name] = r["cells"]
    finally:
        shutil.rmtree(pagedir, ignore_errors=True)
    for name in ("stock1", "canvas1", "tm1", "tm2", "tm3", "tm4", "tm5", "canvas1+tm1"):
        for f in FIELDS:
            print(f"RAW {name} {f}: {raw_hist(got[name], f)}")
        print(f"RAW {name} probe min/median/max: {probe_summary(got[name])}")
    base = got["stock1"]
    _, vis = report("stock2", "stock1", base, got["stock2"])
    if vis:
        print("UNMEASURED stock2 not stable (visible > 0)")
        return 3
    report("canvas1", "stock1", base, got["canvas1"])
    any_visible, bad = False, False
    for i in range(1, 6):
        mv, vis = report(f"tm{i}", "stock1", base, got[f"tm{i}"])
        any_visible |= vis > 0
        bad |= mv == 0
    mv, vis = report("canvas1+tm1", "canvas1", got["canvas1"], got["canvas1+tm1"])
    any_visible |= vis > 0
    bad |= mv == 0
    if bad:
        print("UNMEASURED a textMetrics arm moved nothing")
        return 3
    print(f"VERDICT visible-in-any-arm={'yes' if any_visible else 'no'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

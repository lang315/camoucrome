#!/usr/bin/env python3
"""M0 (spec 2026-11-03-camoufox-port-pivot-design §2): does a browser render audio and
measure text the same on every launch? Launches <exe> headless N times, each with a fresh
profile, loads a self-contained probe page by --dump-dom (no CDP), and prints one JSON line
per launch, then the number of distinct values per probe.

  measure_audio_text.py --exe <chrome> [--runs 5] [--config '{"textMetrics:seed":1}'] [--label x]

A launch whose probe did not finish is UNMEASURED and is not counted as a value; its JSON
line carries "seen", the first 200 characters of the page's <pre> (pending, an error, or no pre).
--virtual-time-budget is virtual time, not a wait: the audio render and crypto.subtle run off
the main thread, so a tiny budget can still finish and a large one is no guarantee.
The audio probe is fingerprintjs' (the one camoufox's audio study used); the text probe is
measureText at 72px for six families, every TextMetrics field the metric-jitter patch moves.
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

FONTS = ["Arial", "Times New Roman", "Courier New", "sans-serif", "serif", "monospace"]

PROBE = r"""<!doctype html><meta charset="utf-8"><pre id="r">pending</pre><script>
(async () => {
  const out = {};
  try {
    const ctx = new OfflineAudioContext(1, 5000, 44100);
    const osc = ctx.createOscillator();
    osc.type = 'triangle'; osc.frequency.value = 10000;
    const c = ctx.createDynamicsCompressor();
    c.threshold.value = -50; c.knee.value = 40; c.ratio.value = 12; c.attack.value = 0; c.release.value = 0.25;
    osc.connect(c); c.connect(ctx.destination); osc.start(0);
    const buf = await ctx.startRendering();
    const d = buf.getChannelData(0);
    let s = 0; for (let i = 4500; i < 5000; i++) s += Math.abs(d[i]);
    out.fpjs = String(s);
    const h = await crypto.subtle.digest('SHA-256', d.buffer);
    out.bufSha = Array.from(new Uint8Array(h)).map(b => b.toString(16).padStart(2, '0')).join('');
    const g = document.createElement('canvas').getContext('2d');
    out.text = {};
    for (const f of FONTS) {
      g.font = '72px ' + (f.includes(' ') ? '"' + f + '"' : f);
      const t = g.measureText('mmmmmmmmmmlli 0123456789 Ñ ẞ');
      out.text[f] = [t.width, t.actualBoundingBoxLeft, t.actualBoundingBoxRight,
                     t.actualBoundingBoxAscent, t.actualBoundingBoxDescent, t.fontBoundingBoxAscent];
    }
    out.done = true;
  } catch (e) { out.error = String(e); }
  document.getElementById('r').textContent = JSON.stringify(out);
})();
</script>""".replace("FONTS", json.dumps(FONTS))


def parse(dom):
    m = re.search(r'<pre id="r">(.*?)</pre>', dom, re.S)
    if not m:
        return None
    try:
        got = json.loads(html.unescape(m.group(1)))
    except ValueError:
        return None
    return got if isinstance(got, dict) and got.get("done") is True else None


def seen(dom):
    m = re.search(r'<pre id="r">(.*?)</pre>', dom, re.S)
    return html.unescape(m.group(1))[:200] if m else "no pre"


def clean_env(environ, config):
    """Copy of environ without any CAMOU_CONFIG* / CAMOU_PRESET* variable (the browser reads
    CAMOU_CONFIG_1..N and CAMOU_PRESET too), then CAMOU_CONFIG=config when given."""
    env = {k: v for k, v in environ.items() if not k.startswith(("CAMOU_CONFIG", "CAMOU_PRESET"))}
    if config:
        env["CAMOU_CONFIG"] = config
    return env


def summarize(results):
    keys = {}
    for r in results:
        keys.setdefault("fpjs", set()).add(r["fpjs"])
        keys.setdefault("bufSha", set()).add(r["bufSha"])
        for font, v in r["text"].items():
            keys.setdefault(f"text.{font}", set()).add(json.dumps(v))
    return {k: len(v) for k, v in keys.items()}


def launch(exe, config, budget_ms, page):
    prof = tempfile.mkdtemp(prefix="m0-")
    env = clean_env(os.environ, config)
    argv = [exe, "--headless=new", "--no-first-run", "--no-default-browser-check",
            f"--user-data-dir={prof}", f"--virtual-time-budget={budget_ms}", "--dump-dom", page.as_uri()]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=120, env=env)
        return p.stdout
    except subprocess.TimeoutExpired:
        return ""
    finally:
        shutil.rmtree(prof, ignore_errors=True)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--config")
    ap.add_argument("--label", default="")
    ap.add_argument("--budget-ms", type=int, default=10000,
                    help="--virtual-time-budget in virtual ms; NOT a real-time wait for the async probe")
    a = ap.parse_args(argv)
    pagedir = pathlib.Path(tempfile.mkdtemp(prefix="m0-page-"))
    page = pagedir / "probe.html"
    page.write_text(PROBE, encoding="utf-8")
    measured, unmeasured = [], 0
    try:
        for i in range(a.runs):
            dom = launch(a.exe, a.config, a.budget_ms, page)
            r = parse(dom)
            if r is None:
                unmeasured += 1
                print(json.dumps({"label": a.label, "run": i, "outcome": "UNMEASURED", "seen": seen(dom)}))
                continue
            measured.append(r)
            print(json.dumps({"label": a.label, "run": i, "fpjs": r["fpjs"], "bufSha": r["bufSha"],
                              "text": r["text"]}))
    finally:
        shutil.rmtree(pagedir, ignore_errors=True)
    print(json.dumps({"label": a.label, "config": a.config, "measured": len(measured),
                      "unmeasured": unmeasured, "distinct": summarize(measured)}))
    return 0 if measured else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

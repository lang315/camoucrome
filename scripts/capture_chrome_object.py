#!/usr/bin/env python3
"""window.chrome shape + navigator.plugins/mimeTypes/pdfViewerEnabled (SP2
§4.7, roadmap B1), captured from stock Chrome 153.0.8010.36 on the build
box's Windows host (headless and headed) into
baselines/chrome-8010-stock-window-chrome.json; scripts/verify_chrome_object.py
diffs the fork against it. The tree records, per own property (depth 4):
kind, descriptor flags, and for functions length/name/toString -- shapes,
never the timing values loadTimes()/csi() return.

    capture_chrome_object.py --where winhost [--out baselines/...]
"""
import argparse
import datetime
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "baselines" / "chrome-8010-stock-window-chrome.json"

PAGE = """<!doctype html><title>chrome-object</title><pre id="o"></pre><script>
function walk(obj, depth, seen) {
  const out = {};
  for (const name of Object.getOwnPropertyNames(obj).sort()) {
    const d = Object.getOwnPropertyDescriptor(obj, name);
    let v; try { v = d.value; } catch (e) { v = undefined; }
    const e = { kind: d.get ? 'accessor' : typeof v, enumerable: d.enumerable, configurable: d.configurable };
    if ('writable' in d) e.writable = d.writable;
    if (typeof v === 'function') { e.length = v.length; e.name = v.name; e.str = Function.prototype.toString.call(v); }
    if (v && (typeof v === 'object' || typeof v === 'function') && depth < 4 && !seen.has(v)) { seen.add(v); e.props = walk(v, depth + 1, seen); }
    out[name] = e;
  }
  return out;
}
const c = window.chrome;
let lt = null, csi = null;
try { const t = c.loadTimes(); lt = { keys: Object.keys(t), startLoadTime_le_firstPaintTime: t.startLoadTime <= t.firstPaintTime, requestTime_le_startLoadTime: t.requestTime <= t.startLoadTime, npn: typeof t.npnNegotiatedProtocol }; } catch (e) { lt = { error: String(e) }; }
try { const t = c.csi(); csi = { keys: Object.keys(t), pageT_ge_0: t.pageT >= 0 }; } catch (e) { csi = { error: String(e) }; }
document.getElementById('o').textContent = JSON.stringify({
  typeofChrome: typeof c,
  protoIsObjectPrototype: c ? Object.getPrototypeOf(c) === Object.prototype : null,
  tree: c ? walk(c, 0, new Set([c])) : null,
  loadTimes: lt, csi,
  plugins: Array.from(navigator.plugins).map(p => ({ name: p.name, filename: p.filename, description: p.description,
    mimeTypes: Array.from(p).map(m => ({ type: m.type, suffixes: m.suffixes, description: m.description })) })),
  mimeTypes: Array.from(navigator.mimeTypes).map(m => ({ type: m.type, suffixes: m.suffixes, description: m.description, plugin: m.enabledPlugin && m.enabledPlugin.name })),
  pdfViewerEnabled: navigator.pdfViewerEnabled,
  ua: navigator.userAgent,
});
</script>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--where", choices=["winhost"], default="winhost")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    import winhost
    headless = winhost.dump_dom(PAGE)
    headed = winhost.dump_dom(PAGE, headed=True)
    doc = {"provenance": {"binary": "Google Chrome 153.0.8010.36 (stock, the build box's Windows 10 host, temp profile, --dump-dom)",
                          "captured": datetime.date.today().isoformat(), "how": "scripts/capture_chrome_object.py --where winhost",
                          "ua_headless": headless.pop("ua"), "ua_headed": headed.pop("ua")},
           "headless": headless, "headed": headed}
    pathlib.Path(a.out).write_text(json.dumps(doc, indent=1) + "\n")
    for k in ("headless", "headed"):
        d = doc[k]
        print(f"{k}: typeof chrome={d['typeofChrome']} top-level={sorted(d['tree'] or {})} plugins={[p['name'] for p in d['plugins']]} "
              f"mimeTypes={[m['type'] for m in d['mimeTypes']]} pdfViewerEnabled={d['pdfViewerEnabled']} loadTimes={d['loadTimes']} csi={d['csi']}")
    print("headless == headed:", doc["headless"] == doc["headed"])


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Per-character advance widths of the claimed Windows families on the real
host (stock Chrome 153 on the box's Windows 10 host, headless --dump-dom) ->
baselines/chrome-8010-stock-font-metrics-windows.json. 100 px so 1/100 em is
one pixel; canvas advances are linear (unhinted) on DirectWrite and FreeType.
verify_font_metrics.py renders the same page in the fork and compares."""
import html
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "baselines" / "chrome-8010-stock-font-metrics-windows.json"
GRID_FAMILIES = ["Segoe UI", "Arial", "Times New Roman", "Courier New", "Calibri", "Cambria",
                 "Consolas", "Georgia", "Verdana", "Tahoma", "Trebuchet MS", "Segoe UI Variable"]
CHARS = [chr(c) for c in range(0x20, 0x7F)] + [chr(c) for c in range(0xC0, 0xDE)]
PX = 100


def page(families):
    return ("<!doctype html><title>metrics</title><pre id=\"o\"></pre><script>"
            "const F=%s,C=%s,PX=%d;const ctx=document.createElement('canvas').getContext('2d');"
            "const w=(f,s)=>{ctx.font=PX+'px '+f;return ctx.measureText(s).width};"
            "const out={};for(const f of F){const q='\"'+f+'\"';"
            "const resolved=w(q+', monospace','The quick brown fox 0123')===w(q+', serif','The quick brown fox 0123');"
            "out[f]={resolved,widths:Object.fromEntries(C.map(c=>[c,w(q,c)]))}}"
            "document.getElementById('o').textContent=JSON.stringify(out).replace(/[\\u0080-\\uffff]/g,c=>'\\\\u'+c.charCodeAt(0).toString(16).padStart(4,'0'));</script>"
            % (json.dumps(families), json.dumps(CHARS), PX))


def parse(dom):
    m = re.search(r'<pre id="o">(.*?)</pre>', dom, re.S)
    return json.loads(html.unescape(m.group(1)))


def main():
    import winhost
    fams = winhost.dump_dom(page(GRID_FAMILIES), args=("--use-gl=angle", "--use-angle=d3d11"))  # dump_dom parses #o
    if isinstance(fams, str):
        fams = parse(fams)
    OUT.write_text(json.dumps({"chrome": "153.0.8010.36",
                               "where": "stock Google Chrome on the build box's Windows 10 host (build 19045), headless --dump-dom, temp profile",
                               "px": PX, "families": fams}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print({f: (v["resolved"], round(v["widths"]["a"], 2)) for f, v in fams.items()})


if __name__ == "__main__":
    main()

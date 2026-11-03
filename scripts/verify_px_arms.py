#!/usr/bin/env python3
"""PerimeterX arms N and S2 are what they claim, before a byte of proxy traffic is paid for
(docs/superpowers/plans/2026-10-28-px-arms-n-s2.md, section 6 item 2).

Fork identity = the generated one (seed 13, UTC/en-US), exactly as the layer-3 harness builds it. Arm N drops canvas:seed from
that config; arm S2 drops every screen.* and window.* key. Each config is read in content_shell on the box
(lib_shell.session, no CDP domain beyond Runtime.evaluate) and compared with no config at all ("stock"):
  N1     arm N: the 2D canvas hash equals stock's (the noise is gone)
  R1     RED: arm F (noise kept): the same hash DIFFERS from stock (the check can fail)
  S1     arm S2: screen.* and window.outer* equal stock's (the claim is gone)
  R3     RED: arm F: screen.width/height or window.outer* DIFFER from stock (the claim is live)
  X1     arm N keeps F's screen/window claim; X2 arm S2 keeps F's canvas noise (an arm differs only by its own keys)
Run on the box (clean env, Linux content_shell): python3 verify_px_arms.py     Exit 0 when every row passes."""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lib_shell  # noqa: E402
import measure_layer3 as ml  # noqa: E402

DROPS = {"keys": [("N", "canvas:seed")], "prefixes": [("S2", "screen."), ("S2", "window.")]}

JS_CANVAS = """(() => { const fnv = s => { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) } return (h >>> 0).toString(16) };
  const c = document.createElement('canvas'); c.width = 220; c.height = 40; const x = c.getContext('2d');
  x.font = '16px Arial'; x.fillText('Cwm fjordbank glyphs vext quiz 1234', 4, 26); x.fillStyle = '#f60'; x.beginPath(); x.arc(50, 20, 15, 0, 7); x.fill();
  x.fillStyle = 'rgba(0,80,255,.5)'; x.fillRect(40, 10, 60, 20); return fnv(c.toDataURL()) })()"""

JS_GEOM = "JSON.stringify([screen.width, screen.height, screen.availWidth, screen.availHeight, window.outerWidth, window.outerHeight])"


def configs(ident_config):
    return {"stock": {}, "F": ident_config, "N": ml.drop_keys(ident_config, "N", DROPS), "S2": ml.drop_keys(ident_config, "S2", DROPS)}


def read(config):
    vals, err = lib_shell.session(json.dumps(config), [JS_CANVAS, JS_GEOM])
    if err is not None:
        raise RuntimeError(f"content_shell session failed: {err!r}")
    return {"canvas": vals[0], "geom": vals[1]}


def rows(r):
    """r: arm -> {"canvas", "geom"}. Returns [(passed, text)]."""
    s, f, n, s2 = r["stock"], r["F"], r["N"], r["S2"]
    return [
        (n["canvas"] == s["canvas"], f"N1 arm N 2D canvas hash equals stock's ({n['canvas']} vs {s['canvas']})"),
        (f["canvas"] != s["canvas"], f"R1 RED arm F 2D canvas hash differs from stock's ({f['canvas']} vs {s['canvas']})"),
        (s2["geom"] == s["geom"], f"S1 arm S2 screen/window equal stock's ({s2['geom']} vs {s['geom']})"),
        (f["geom"] != s["geom"], f"R3 RED arm F screen/window differ from stock's ({f['geom']} vs {s['geom']})"),
        (n["geom"] == f["geom"], f"X1 arm N keeps F's screen/window claim ({n['geom']} vs {f['geom']})"),
        (s2["canvas"] == f["canvas"], "X2 arm S2 keeps F's canvas noise"),
    ]


def main():
    sys.path.insert(0, str(HERE.parent / "client" / "python"))
    from camoucrome.gen import generate
    ident = generate("windows", seed=13, timezone="UTC", locale="en-US")
    cfgs = configs(ident["config"])
    for arm, key in (("N", "canvas:seed"),):
        if key not in ident["config"]:
            print(f"FAIL precondition: the generated config has no {key}; the harness would drop nothing for arm {arm}")
            return 1
    res = {arm: read(c) for arm, c in cfgs.items()}
    out = rows(res)
    for ok, text in out:
        print(("PASS " if ok else "FAIL ") + text)
    n = sum(ok for ok, _ in out)
    print(f"{n}/{len(out)} PASS")
    return 0 if n == len(out) else 1


if __name__ == "__main__":
    sys.exit(main())

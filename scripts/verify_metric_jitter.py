"""Verify the TextMetrics metric-jitter slice (J1-J11).

measureText() is the classic canvas font fingerprint. This checks that under a
canvas:seed the readback is jittered (J1/J4), that the jitter is deterministic
within a session and across process launches (J2/J3), that seed-absent is a
byte-exact no-op (J5), that deltas stay on the sub-pixel/integer grid and every
field remains float32-round-trippable (J6/J7), that the zero guard holds (J8),
that font-constant fields are text-independent while width is not (J9/J10), and
-- the mirror gate -- that the seed-keyed rewrite of the y-block preserves every
cross-baseline / cross-align identity a page could invert (J11).

NO CDP: measureText is not secure-context gated, so about:blank is enough. Each
lib_shell.session() is a fresh content_shell launch (own user-data-dir), so J3
is two separate session() calls and J2 is two probes inside one session's JS.
"""

import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell

FONT = "48px serif"
# ascenders (H) + descenders (g,j,p,q,y) so glyph_bounds.y()/.bottom() are both
# non-zero and their jitter is observable.
TC = "Hgjpqy"

FIELDS = [
    "width",
    "actualBoundingBoxLeft", "actualBoundingBoxRight",
    "actualBoundingBoxAscent", "actualBoundingBoxDescent",
    "fontBoundingBoxAscent", "fontBoundingBoxDescent",
    "alphabeticBaseline", "hangingBaseline", "ideographicBaseline",
]

# One probe per (font,text,align,baseline). textAlign/textBaseline are set on the
# 2D context *before* measureText, which is what shifts the align/baseline-relative
# fields -- exactly the state the C++ Update() reads.
_PROBE = r"""(() => {
  const c = document.createElement('canvas'), ctx = c.getContext('2d');
  const F = ['width','actualBoundingBoxLeft','actualBoundingBoxRight',
    'actualBoundingBoxAscent','actualBoundingBoxDescent',
    'fontBoundingBoxAscent','fontBoundingBoxDescent',
    'alphabeticBaseline','hangingBaseline','ideographicBaseline'];
  const specs = %s, out = [];
  for (const s of specs) {
    ctx.font = s[0]; ctx.textAlign = s[2]; ctx.textBaseline = s[3];
    const m = ctx.measureText(s[1]), r = {};
    for (const f of F) r[f] = m[f];
    out.push(r);
  }
  return out;
})()"""


def measure(config, specs):
    """One content_shell session; returns a list of field-dicts, one per spec."""
    v, e = lib_shell.session(config, [_PROBE % json.dumps(specs)],
                             navigate_to="about:blank")
    if e:
        raise e
    return v[0]


def cfg(seed):
    return json.dumps({"canvas:seed": seed})


STOCK = json.dumps({})          # no canvas:seed -> jitter off (rule 5)
SEED_A, SEED_B = 12345, 54321


def is_f32(v):
    return struct.unpack("f", struct.pack("f", v))[0] == v


def bound_for(stock_val):
    # PerturbMetric: integer source -> |delta| <= 1 ; fractional -> <= 8/64 = 0.125.
    return 1.0 if float(stock_val).is_integer() else 0.125


# ---- J11 residual model -----------------------------------------------------
# specs, in a fixed order the residual fn indexes by position.
SPECS11 = [
    [FONT, TC, "left", "alphabetic"],    # 0: default tb; C reference; D(left)
    [FONT, TC, "left", "hanging"],       # 1: B_hanging; C(hanging)
    [FONT, TC, "left", "ideographic"],   # 2: B_ideographic; C(ideographic)
    [FONT, TC, "left", "top"],           # 3: C(top)
    [FONT, TC, "left", "bottom"],        # 4: C(bottom)
    [FONT, TC, "left", "middle"],        # 5: C(middle)
    [FONT, TC, "center", "alphabetic"],  # 6: D(center)
    [FONT, TC, "right", "alphabetic"],   # 7: D(right)
]


def residuals(recs):
    """Max residual per J11 identity (0 == identity holds exactly)."""
    a = recs[0]  # left, alphabetic
    R = {}
    # Identity A -- default tb=alphabetic, one call.
    R["A1_hang~0.8fBBA"] = abs(a["hangingBaseline"] - 0.8 * a["fontBoundingBoxAscent"])
    R["A2_ideo==-fBBD"] = abs(a["ideographicBaseline"] - (-a["fontBoundingBoxDescent"]))
    # Identity B -- own-named baseline ~ 0.
    R["B_hanging~0"] = abs(recs[1]["hangingBaseline"])
    R["B_ideographic~0"] = abs(recs[2]["ideographicBaseline"])
    R["B_alphabetic~0"] = abs(a["alphabeticBaseline"])
    # Identity C -- one baseline_y' across all four fields, for every tb.
    cmax = 0.0
    for rec in recs[1:6]:
        d_fBBA = rec["fontBoundingBoxAscent"] - a["fontBoundingBoxAscent"]
        d_aBBA = rec["actualBoundingBoxAscent"] - a["actualBoundingBoxAscent"]
        d_fBBD = rec["fontBoundingBoxDescent"] - a["fontBoundingBoxDescent"]
        d_aBBD = rec["actualBoundingBoxDescent"] - a["actualBoundingBoxDescent"]
        cmax = max(cmax, abs(d_fBBA - d_aBBA), abs(d_fBBA + d_fBBD),
                   abs(d_fBBA + d_aBBD))
    R["C_baseline_y'"] = cmax
    # Identity D -- textAlign shift (width is text-only, equal across aligns).
    w = a["width"]
    R["D_center==w/2"] = abs((recs[6]["actualBoundingBoxLeft"]
                              - a["actualBoundingBoxLeft"]) - w / 2.0)
    R["D_right==-w"] = abs((recs[7]["actualBoundingBoxRight"]
                            - a["actualBoundingBoxRight"]) - (-w))
    return R


ABS_CAP = 1e-2   # stock must satisfy each identity to this; catches a wrong reading.
JIT_MARGIN = 1e-3  # jittered residual may exceed stock's only by FP noise (<< 1/64).


def main():
    r = {}
    SP = [FONT, TC, "left", "alphabetic"]

    # J1 -- jitter happens: width differs from stock for >=1 seed.
    stock_sp = measure(STOCK, [SP])[0]
    r["J1"] = any(measure(cfg(s), [SP])[0]["width"] != stock_sp["width"]
                  for s in (SEED_A, SEED_B, 777, 2024, 8, 99))

    # J2 -- same-session determinism: two probes in ONE session, all fields ==.
    two = measure(cfg(SEED_A), [SP, SP])
    r["J2"] = two[0] == two[1]

    # J3 -- cross-session determinism: two separate launches, same seed/inputs ==.
    r["J3"] = (measure(cfg(SEED_A), [SP])[0]
               == measure(cfg(SEED_A), [SP])[0])

    # J4 -- seed sensitivity: seed A vs B differ for >=1 of N strings.
    strs = ["mmmmmmmmmmlli", "Cwm fjordbank", "aA0!", "abcdefghijklmnop", TC]
    specs4 = [[FONT, t, "left", "alphabetic"] for t in strs]
    mA, mB = measure(cfg(SEED_A), specs4), measure(cfg(SEED_B), specs4)
    r["J4"] = any(mA[i]["width"] != mB[i]["width"] for i in range(len(strs)))

    # J5 -- no-op absent: seed-absent {} === explicit seed 0, exact, every field.
    specs5 = [SP, ["14px Arial", "aA0!", "center", "top"],
              [FONT, TC, "right", "hanging"]]
    m_absent, m_zero = measure(STOCK, specs5), measure(cfg(0), specs5)
    r["J5"] = all(m_absent[i] == m_zero[i] for i in range(len(specs5)))

    # J6 -- bound, scoped to (left, alphabetic) where each field == one source.
    #   fractional source |delta| <= 0.125 ; integer source |delta| <= 1.
    #   hangingBaseline = fa*0.8f is a *scaled* source -> bound 0.8*bound(fBBA).
    st6 = measure(STOCK, [SP])[0]
    j6 = True
    for s in (SEED_A, SEED_B, 777):
        m = measure(cfg(s), [SP])[0]
        for f in FIELDS:
            d = abs(m[f] - st6[f])
            if f == "hangingBaseline":
                bnd = 0.8 * bound_for(st6["fontBoundingBoxAscent"]) + 1e-4
            else:
                bnd = bound_for(st6[f]) + 1e-4  # +eps covers SetRect round-trip ULP
            if d > bnd:
                j6 = False
                print(f"  J6 miss: {f} delta={d} > {bnd} (seed {s})")
    r["J6"] = j6

    # J7 -- grid: every jittered field survives a float32 round-trip.
    m7 = measure(cfg(SEED_A), [SP])[0]
    r["J7"] = all(is_f32(m7[f]) for f in FIELDS)

    # J8 -- zero guard: empty ink -> the perturbed sources stay exactly 0.
    m8 = measure(cfg(SEED_A), [[FONT, "", "left", "alphabetic"]])[0]
    r["J8"] = (m8["width"] == 0
               and m8["actualBoundingBoxAscent"] == 0
               and m8["actualBoundingBoxDescent"] == 0)

    # J9 -- font metrics are text-independent (keyed on font-only f_index).
    specs9 = [[FONT, "a", "left", "alphabetic"],
              [FONT, "wwwww", "left", "alphabetic"]]
    m9 = measure(cfg(SEED_A), specs9)
    fm = ["fontBoundingBoxAscent", "fontBoundingBoxDescent",
          "alphabeticBaseline", "hangingBaseline", "ideographicBaseline"]
    r["J9"] = all(m9[0][f] == m9[1][f] for f in fm)

    # J10 -- width still depends on text.
    r["J10"] = m9[0]["width"] != m9[1]["width"]

    # J11 -- cross-state coherence mirror. Stock must satisfy every identity
    # (<= ABS_CAP); jittered may exceed stock's residual only by FP noise.
    Rstock = residuals(measure(STOCK, SPECS11))
    j11 = True
    print("  J11 residuals (identity: stock -> jit seeds):")
    seeds11 = (SEED_A, SEED_B, 777)
    Rjs = [residuals(measure(cfg(s), SPECS11)) for s in seeds11]
    for k in Rstock:
        stock_ok = Rstock[k] <= ABS_CAP
        jit_ok = all(Rjs[i][k] <= Rstock[k] + JIT_MARGIN for i in range(len(seeds11)))
        if not (stock_ok and jit_ok):
            j11 = False
        jit_str = ", ".join(f"{Rjs[i][k]:.3e}" for i in range(len(seeds11)))
        flag = "" if (stock_ok and jit_ok) else "  <-- FAIL"
        print(f"    {k:22s} {Rstock[k]:.3e} -> {jit_str}{flag}")
    # Evidence that identity B is actually exercised (font metrics jitter): print
    # delta_fa/delta_fd per seed. Not a gate (would fail RED where jitter is off).
    for i, s in enumerate(seeds11):
        d_fa = Rjs and (measure(cfg(s), [SP])[0]["fontBoundingBoxAscent"]
                        - st6["fontBoundingBoxAscent"])
        d_fd = (measure(cfg(s), [SP])[0]["fontBoundingBoxDescent"]
                - st6["fontBoundingBoxDescent"])
        print(f"    seed {s}: delta_fa={d_fa:+.5f} delta_fd={d_fd:+.5f}")
    r["J11"] = j11

    EXPECTED = 11
    keys = [f"J{i}" for i in range(1, 12)]
    for k in keys:
        print(f"{k}: {'PASS' if r[k] else 'FAIL'}")
    n = sum(1 for k in keys if r[k])
    print(f"{n}/{EXPECTED} " + ("ALL_PASS" if n == EXPECTED else "FAIL"))
    sys.exit(0 if n == EXPECTED else 1)


if __name__ == "__main__":
    main()

# metric-jitter surfaces measurement (2026-09-05)

Checkout HEAD `a727b57805`, `out/Default` content_shell, about:blank (canvas
`measureText` is NOT secure-context gated).

Canvas `TextMetrics` (the return of `CanvasRenderingContext2D.measureText`) is a
**readback** surface — the classic canvas-font fingerprint vector. sp3a spoofs
canvas *pixel* readback (`toDataURL`/`toBlob`) with seeded noise but leaves the
text-metric readback truthful. This slice extends the same seeded-rotation
philosophy to `TextMetrics`, reusing the sp3a `canvas:seed` and the
`DeriveDelta` primitive — no new key, no new DEPS, no new BUILD dep.

Readback, not layout: `measureText` does not drive DOM layout, so unlike
`innerWidth`/`clientWidth` (window-geometry §4) a getter-lie here has no
layout-coherence trap. The only coherence traps are internal to `TextMetrics`
(fields must agree with each other's grid and text-(in)dependence) — the whole
subject of §3.

---

## 1. Stock behavior (measured)

Determinism: two runs in the same and in separate content_shell launches return
**bit-identical** metrics for the same `(text, font)`. Real Chrome is the same —
`measureText` is a pure function of `(text, font, platform text-shaping)`. So the
spoof must preserve that: seeded jitter that is **stable within a profile** and
rotates across profiles/seed changes (exactly sp3a canvas-noise's contract).

Per-field grid, across `14px Arial`, `48px serif`, `11px monospace`
(`measure_metric_grid.py`):

| field | grid | text-dependent? |
|---|---|---|
| `width` | dyadic fractional (denominator 2ⁿ, up to /4096) | **yes** |
| `actualBoundingBoxRight` | dyadic fractional (some samples integer) | **yes** |
| `actualBoundingBoxLeft` | integer (small: 0, −1, −2) | **yes** |
| `actualBoundingBoxAscent` | integer | **yes** |
| `actualBoundingBoxDescent` | integer (often 0 — no descender) | **yes** |
| `fontBoundingBoxAscent` | integer | **NO — font-constant** |
| `fontBoundingBoxDescent` | integer | **NO — font-constant** |
| `hangingBaseline` | integer or dyadic-fractional | **NO — font-constant** |
| `ideographicBaseline` | integer | **NO — font-constant** |
| `alphabeticBaseline` | always `-0.0` | **NO — font-constant, always 0** |
| `emHeightAscent/Descent` | `null` in stock | (gated off, see §4) |

Sample widths: `148.0458984375`, `8.28515625`, `547.875`, `86.09326171875` —
all dyadic (power-of-two denominators, Skia sub-pixel). `fontBoundingBoxAscent`:
`13,13,13 / 45,45,45 / 10,10,10` — **identical for every string of a given
font** (a pure font metric).

## 2. The tell being closed

`measureText(str).width` (and the actualBoundingBox set) is hashed at **full
float precision** by mainstream fingerprint libraries (CreepJS, fingerprintjs).
It is deterministic per `(platform, font, text)`, so it is a **stable
cross-session identifier**. metric-jitter rotates it per-seed so it stops being a
stable re-identification key — the same reason sp3a rotates canvas pixels.

**Not in scope (documented, #44 lesson 1 — don't over-claim):** on Linux
content_shell `14px Arial` resolves to Liberation/DejaVu; the stock widths are
already a *platform-font* tell against a Windows/Mac UA. metric-jitter rotates
the identity; it does **not** fix that platform mismatch. That is fonts-ii
(Wave D).

## 3. Two coherence traps a naive "jitter every field" introduces

The scope decision (2026-09-05) is **coherent-all** — jitter every JS-readable
field. Measurement shows a uniform sub-pixel content-hash jitter over all fields
ships two *new* tells; coherent-all must handle them per field-class:

1. **Grid tell.** Half the fields are integer-valued. Adding a sub-pixel delta
   (`45 → 45.05`) fails `x === Math.round(x)` — an integer readback that is
   suddenly fractional is impossible in real Chrome. **Fix:** integer-valued
   stock gets an *integer* delta (stays on the integer grid); dyadic-fractional
   stock gets a `k/64` px delta (stays dyadic). The perturb helper branches on
   `stock == trunc(stock)`.

2. **Text-independence tell.** `fontBoundingBoxAscent`, `fontBoundingBoxDescent`,
   `hangingBaseline`, `ideographicBaseline` are **font metrics** — identical for
   every string of a font. Keying their jitter by `(text, font)` makes
   `measureText("a").fontBoundingBoxAscent !== measureText("b").fontBoundingBoxAscent`
   — impossible in real Chrome, an instant tell. **Fix:** font-constant fields
   are keyed by the **font only** (index = hash(font), no text), so they jitter
   once per font and stay text-independent.

Zero guard (both classes): stock `== 0` is left untouched. Real Chrome returns
exact `0` for `measureText("").width`, for `actualBoundingBoxDescent` of a
descenderless string, and for `alphabeticBaseline`; a non-zero there is itself a
tell.

## 4. Blink choke point and port — perturb SOURCES, not derived members

`third_party/blink/renderer/core/html/canvas/text_metrics.cc`,
`TextMetrics::Update()`. **The naive "jitter each derived member at the tail" is
wrong** — the members are not independent, they are derived from a few source
quantities through arithmetic that a page can invert:

- **`text_align_dx_`** (center/right) is computed from the stock `width`, and
  `actual_bounding_box_{left,right}` subtract it. Jitter `width_` at the tail and
  `aBBL_center − aBBL_left = width/2` no longer holds (off by Δ_w/2).
- **`baseline_y = GetFontBaseline(textBaseline, font_data)`** is a common additive
  pivot for `fontBoundingBox*`, `actualBoundingBox{Ascent,Descent}`, `emHeight*`,
  and the three `baselines_`; AND it re-reads the very font metrics (`FloatAscent`,
  `FloatDescent`, the baseline tables) that the font-constant jitter targets. So a
  constant per-field delta does **not** cancel — measured on Linux (fallback
  branches), `hangingBaseline = 0.8 × fontBoundingBoxAscent` and
  `ideographicBaseline = −fontBoundingBoxDescent` **exactly, in one default call**;
  and at `textBaseline='hanging'` the own baseline is ≈0. Independent result-jitter
  breaks all three.

**Port = perturb the source quantities, then let stock arithmetic reproduce every
member and every internal identity.** Config is global (`ScopeFor` ignores its arg
→ GlobalScope) → `camoucfg::CanvasSeed(camoucfg::ScopeFor(nullptr))`, no signature
threading. Seed absent/0 → nothing is perturbed (rule 5).

**(a) Text-dependent sources** — right after `auto [xpos, glyph_bounds] =
MeasureRuns(...)`, jitter `xpos` and the four glyph-bounds edges as independent
scalars (`tf_index`, not `SetRect` — `x+width` in float32 can miss the jittered
right edge by an ulp):

| source scalar | feeds | domain |
|---|---|---|
| `xpos` | `width_`, `text_align_dx_` | `tm.w` |
| `glyph_bounds.x()` | `actualBoundingBoxLeft` | `tm.l` |
| `glyph_bounds.right()` | `actualBoundingBoxRight` | `tm.r` |
| `glyph_bounds.y()` | `actualBoundingBoxAscent` | `tm.a` |
| `glyph_bounds.bottom()` | `actualBoundingBoxDescent` | `tm.d` |

**(b) Font-constant sources — the metric set M′, computed once (`f_index`).** The
font-constants all trace to `{FloatAscent, FloatDescent, NormalizedTypoAscent,
NormalizedTypoDescent, HangingBaseline, IdeographicBaseline, AlphabeticBaseline}`
— read once, jitter each (font-only key, distinct domain, value-branch grid,
zero-guard), the table baselines **only when `has_value()`** (else the fallback
formula owns them). Then a **file-local `MirroredBaseline(textBaseline, M′)`**
reproduces `GetFontBaseline`'s switch *exactly* on M′ (including the
`kHangingAsPercentOfAscent/100.0` **double** in `GetFontBaseline` vs the `/100.0f`
**float** in the y-block's setHanging fallback — the asymmetry sets stock's
residual at `tb=hanging`). The y-block, `emHeight*`, and all three `baselines_`
setters are rewritten to consume **only M′ and `baseline_y′ = MirroredBaseline`**
— zero fresh `font_metrics.*` reads downstream. Every font-constant field for every
`textBaseline` then traces to the same jittered M′ → all cross-baseline identities
hold. The static `GetFontBaseline` itself is left untouched (its other caller,
line ~439, is the ExtendedTextMetrics path, gated off — documented residual).

Helper (added to `components/camoucfg/canvas_noise.{h,cc}`, mirrors `PerturbRgba`):

```cpp
// Grid-preserving, seed-keyed jitter of one scalar readback source. Pure.
//   seed==0 || stock==0  -> stock            (rule-5 no-op / zero guard)
//   integer stock        -> stock + DeriveDelta(seed,domain,index,1)         (integer grid)
//   fractional stock     -> stock + DeriveDelta(seed,domain,index,8)/64.0    (dyadic, <=0.125px)
double PerturbMetric(double stock, uint64_t seed, uint64_t index,
                     std::string_view domain);
uint64_t CanvasSeed(const ConfigScope& scope);   // GetUint32(kCanvasSeed).value_or(0)
```

`index` is a **content hash computed in Blink** (canvas_noise, a `//components`
lib, cannot depend on Blink's `String`/`FontDescription`):
- text-dependent sources: `tf_index = FNV(text code units) ^ f_index`.
- font-constant sources (M′): `f_index = FNV(resolved-font descriptor)`.

Key by the **RESOLVED** font, not the requested family — `ctx.font='serif'` and
`'Liberation Serif'` resolve identically and stock returns identical metrics, so
`f_index` must too: hash `font->PrimaryFont()->PlatformData()` typeface family +
`ComputedSize()` bits + weight/slope. Must be **reproducible across process
launches** (content-derived, no pointers) — gated by J2 (same session) and **J3
(separate launches)**.

Distinct domain per source → each derives an independent delta from the one seed,
so the sources don't all shift by the same amount (itself a tell).

## 5. Deferred / residual (documented)

- **`emHeightAscent/Descent`** — the C++ members derive from
  `NormalizedTypoAscentAndDescent` (= `nta'/ntd'` once the y-block is rewritten
  onto M′), so they inherit the jitter coherently — but the IDL attribute is
  `[RuntimeEnabled=ExtendedTextMetrics]`, **off** in this build (they read `null`).
  Effectively unreadable here; coherent if ever enabled.
- **`getActualBoundingBox` / `getSelectionRects` / `getTextClusters` /
  `getIndexFromOffset`** — all `[RuntimeEnabled=ExtendedTextMetrics]`, off. These
  derive from `runs_with_offset_`, NOT from the jittered members; **if the flag
  were on**, `getActualBoundingBox(0,len)` would contradict a jittered
  `actualBoundingBoxLeft/Right`, and the static `GetFontBaseline` (line ~439 path)
  would use stock baselines vs the jittered ones. Off here → not exercised;
  flagged for whoever enables ExtendedTextMetrics.
- **`text_align_dx_`** — internal, not exposed; derives from jittered `xpos`.
- **Rebase fragility (#44 lesson 3 — state what the guard cannot see).** The
  font-constant half couples to `GetFontBaseline`'s switch AND the y-block/baseline
  formulas: `MirroredBaseline` must be re-diffed against `GetFontBaseline` on every
  Chromium rebase (a formula change upstream silently desyncs the mirror). Add a
  rebase checklist item. J11 is the tripwire but it runs on **Linux**, where the
  fonts have no baseline tables → only the **fallback** branches
  (`kHanging`→0.8·ascent, `kIdeographic`→−descent, `kAlphabetic`→0) are exercised.
  Windows/macOS fonts with real `HangingBaseline()/IdeographicBaseline()/
  AlphabeticBaseline()` tables take the `has_value()` paths the Linux guard never
  sees — the M′ jitter covers them by construction, but is unverified here.
- **J11 is structurally blind to two things (code-review-enforced, per the Task 2
  review):** (1) a `MirroredBaseline` desync for `textBaseline ∈ {top,bottom,middle}`
  at ANY seed — identity C (`fBBA+fBBD`) is `baseline_y`-invariant and those three
  have no own-named baseline field, so only inspection confirms the mirror consumes
  the *jittered* `nta/ntd` there; (2) the `nta/ntd` jitter itself has no witness field
  in J1–J11 (`emHeight*` are gated off; top/bottom/middle probe only invariant
  identities). Both hold by construction and were verified by reading the diff, not by
  the harness — re-check them on any rebase alongside `MirroredBaseline`.

## 6. Scope summary

| surface | this slice |
|---|---|
| `width`, `actualBoundingBox{Left,Right,Ascent,Descent}` | **spoof** — text+font-keyed, grid-preserving |
| `fontBoundingBox{Ascent,Descent}`, `hanging`/`ideographic`/`alphabetic Baseline` | **spoof** — font-only-keyed (text-independent), grid-preserving |
| `emHeight*`, `getActualBoundingBox`/`getSelectionRects`/`getTextClusters` | **defer** — ExtendedTextMetrics off (documented) |
| config key | **reuse `canvas:seed`** — no new key (78 unchanged) |
| DEPS / BUILD | **no change** — `canvas_noise.h` already blink-DEPS-allowed, camoucfg already in the target |

# metric-jitter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Seed-jitter the canvas `TextMetrics` readback at the Blink level so
`measureText(str)` stops being a stable cross-session fingerprint, reusing the
sp3a `canvas:seed` and `DeriveDelta` — coherently across every JS-readable field
(no grid tell, no text-independence tell).

**Architecture:** A pure grid-preserving helper `camoucfg::PerturbMetric` in
`components/camoucfg/canvas_noise.{h,cc}` (mirrors `PerturbRgba`), called from a
single block at the tail of `TextMetrics::Update()`
(`core/html/canvas/text_metrics.cc`). Config value (`canvas:seed`) drives it;
absent/0 → no-op (rule 5). See `docs/superpowers/measurements/2026-09-05-metric-jitter-surfaces.md`.

**Tech Stack:** Chromium/Blink C++ (`core/html/canvas`), `//components/camoucfg`,
GN, Playwright verify over content_shell CDP.

**Harness:** `source /private/tmp/claude-501/-Users-lang-GolandProjects-github-com-lang315-camoufox/a03cdf7f-ea24-4267-99be-5f18eeb765f3/scratchpad/buildpc.sh`
(`pushcfg`/`pushfile`/`pullfile`/`unittests`/`contentshell`/`verify`). Checkout
`/home/lang/chromium/src` HEAD `a727b57805`. Confirm **NON-ZERO** build steps
(stale `.o` → silent 0-step no-op). Long builds via `run_in_background`.

## Global Constraints

- All spoofing at the C++/Blink level, NEVER injected JS. (project invariant)
- **Reuse `canvas:seed`** (`keys::kCanvasSeed`). **NO new key** — count stays 78.
  No `keys.h`/`keys_unittest.cc` change. No `DEPS` change (`canvas_noise.h`,
  `mask_config.h`, `blink_scope.h` already blink-DEPS-allowed — sp3a includes
  `canvas_noise.h` from the same `core/html/canvas/` dir). No `BUILD.gn` change
  (`canvas_noise` already in the camoucfg target; the blink target already deps
  camoucfg via `html_canvas_element.cc`).
- **Grid preservation (measurement §3 trap 1):** integer stock → integer delta
  (`DeriveDelta(...,bound=1)`); dyadic-fractional stock → `DeriveDelta(...,bound=8)/64.0`
  (≤0.125px, stays dyadic). Branch on `stock == std::trunc(stock)`.
- **Text-independence (trap 2):** font-constant fields keyed by `hash(font)` only;
  text-dependent fields keyed by `hash(text) ^ hash(font)`. See the field table.
- **Zero guard:** `stock == 0.0` → return stock unchanged (both classes).
- **Determinism contract:** the Blink-computed `index` must be reproducible across
  process launches (content-derived, no pointers). Gated by J2 (same session) and
  **J3 (separate launches)**.
- Blink files live only in the checkout; edit via `pullfile`/`pushto`; extract to
  `patches/` in the final task. `text_metrics.cc` is CLEAN in the WSL dirty list —
  clean `git diff HEAD` extraction (do NOT touch `base_rendering_context_2d.cc`,
  which is already ` M`).
- Verify: `measureText` is NOT secure-context gated — `about:blank`, NO CDP,
  `CAMOU_CONFIG` only.

---

### Task 1: `PerturbMetric` + `CanvasSeed` in canvas_noise (+ unit tests)

**Files:**
- Modify: `additions/camoucfg/canvas_noise.h` (2 decls)
- Modify: `additions/camoucfg/canvas_noise.cc` (2 defs)
- Modify: `additions/camoucfg/canvas_noise_unittest.cc` (grid/no-op/determinism tests)

**Interfaces:**
- Produces `camoucfg::PerturbMetric(double stock, uint64_t seed, uint64_t index, std::string_view domain)`
  and `camoucfg::CanvasSeed(const ConfigScope&)`. Task 2 consumes both.

- [ ] **Step 1: canvas_noise.h** — add after `PerturbRgbaFromConfig`:
```cpp
// Grid-preserving, seed-keyed jitter of ONE TextMetrics readback (metric-jitter
// slice). Pure: the same (stock, seed, index, domain) yields the same output, so
// a page re-reading the same (text, font) sees identical metrics and cannot
// detect the jitter by re-measuring.
//   - seed == 0  -> stock unchanged (rule 5: no canvas:seed -> real value).
//   - stock == 0 -> stock unchanged (zero guard: real Chrome returns exact 0 for
//     empty ink / empty string / zero baseline; a non-zero there is a tell).
//   - integer stock -> stock + DeriveDelta(seed, domain, index, 1)      (integer grid).
//   - fractional    -> stock + DeriveDelta(seed, domain, index, 8)/64.0 (dyadic, <=0.125px).
// `domain` separates fields so each derives an independent delta from one seed.
// `index` is a caller-supplied content hash: for text-dependent fields
// hash(text)^hash(font); for font-constant fields hash(font) only (keeps them
// text-independent). See metric-jitter measurement §3-4.
double PerturbMetric(double stock, uint64_t seed, uint64_t index,
                     std::string_view domain);

// canvas:seed as a uint64 (0 if absent). The one place the metric path reads the
// seed key; Blink reads it once per measureText and calls PerturbMetric per field.
uint64_t CanvasSeed(const ConfigScope& scope);
```
Add `#include <string_view>` to the header if not present.

- [ ] **Step 2: canvas_noise.cc** — add `#include <cmath>` (for `std::trunc`) and
  the two defs (after `PerturbRgbaFromConfig`):
```cpp
double PerturbMetric(double stock, uint64_t seed, uint64_t index,
                     std::string_view domain) {
  if (seed == 0 || stock == 0.0) {
    return stock;
  }
  if (stock == std::trunc(stock)) {  // integer field -> integer delta, on-grid
    return stock + DeriveDelta(seed, domain, index, /*bound=*/1);
  }
  // dyadic-fractional field -> sub-pixel delta on a 1/64 grid (a multiple of any
  // finer dyadic grid the stock already sits on), bounded to +-8/64 = 0.125 px.
  return stock + DeriveDelta(seed, domain, index, /*bound=*/8) / 64.0;
}

uint64_t CanvasSeed(const ConfigScope& scope) {
  return GetUint32(scope, keys::kCanvasSeed).value_or(0);
}
```
(`DeriveDelta`, `GetUint32`, `keys::kCanvasSeed` are already included/used in this
file. `ConfigScope` comes via `mask_config.h`.)

- [ ] **Step 3: canvas_noise_unittest.cc** — add a `PerturbMetric` test block:
  - **NoOpWhenSeedZero:** `PerturbMetric(148.04, 0, 99, "tm.w") == 148.04`;
    integer `PerturbMetric(45.0, 0, 99, "tm.fa") == 45.0`.
  - **ZeroGuard:** `PerturbMetric(0.0, 1234, 99, "tm.d") == 0.0`.
  - **IntegerStaysInteger:** for several seeds/indices,
    `PerturbMetric(45.0, seed, i, "tm.fa")` is integer (`== std::trunc(result)`)
    and `|result-45| <= 1`.
  - **FractionalStaysDyadicAndBounded:** `r = PerturbMetric(148.0458984375, seed, i, "tm.w")`;
    `|r-stock| <= 0.125 + eps`; `r*64.0` differs from stock*64 by an integer
    (delta is `k/64`) — assert `std::abs((r-stock)*64.0 - std::round((r-stock)*64.0)) < 1e-9`.
  - **Deterministic:** same args twice → equal.
  - **DomainSeparation / spread:** across many indices with fixed seed, the deltas
    are not all identical (guards a constant-delta mutant — mirrors sp3a ledger
    M2); and two different domains give different deltas for the same (seed,index)
    for at least some samples.

- [ ] **Step 4: push + build + run**
```bash
source /private/tmp/.../scratchpad/buildpc.sh
pushcfg canvas_noise.h && pushcfg canvas_noise.cc && pushcfg canvas_noise_unittest.cc
unittests 'CanvasNoiseTest.*:PerturbRgbaTest.*'
```
Expected: NON-ZERO build, all PASS (new PerturbMetric tests + existing PerturbRgba
unchanged). RED-first: run the tests once BEFORE adding the .cc defs (compile
error / missing symbol) is optional here since it's a pure add; the mutant-style
spread test is the real guard.

- [ ] **Step 5: Commit**
```bash
git add additions/camoucfg/canvas_noise.h additions/camoucfg/canvas_noise.cc additions/camoucfg/canvas_noise_unittest.cc
git commit -m "feat(metric-jitter): PerturbMetric grid-preserving TextMetrics jitter + CanvasSeed"
```

---

### Task 2: Blink — jitter TextMetrics::Update() SOURCES + mirror (+ verify J1–J11)

**Files:**
- Modify (checkout): `third_party/blink/renderer/core/html/canvas/text_metrics.cc`
- Create (Mac): `scripts/verify_metric_jitter.py`

**Interfaces:** Consumes `camoucfg::PerturbMetric` / `camoucfg::CanvasSeed`.

> **Design (measurement §4): perturb SOURCES, not derived members.** Jittering the
> final `width_`/`aBB*`/`fBB*`/baselines at the tail breaks internal identities a
> page can invert (`text_align_dx_` derives from stock width; `baseline_y`
> re-reads the font metrics you are jittering). Instead jitter the source scalars
> and let stock arithmetic reproduce every member. ~40–50 lines, one file,
> **version-coupled** to `GetFontBaseline` + the y-block formulas (documented,
> user-accepted). J11 is the coherence gate.

- [ ] **Step 1: verify script `scripts/verify_metric_jitter.py`** (about:blank, NO
  CDP). Probe takes `(font, text, textAlign, textBaseline)` and returns the 10
  fields. Seeds below are examples — **pin seeds with known nonzero deltas**
  (integer branch bound=1 → delta 0 for ~⅓ of seeds; any "jittered ≠ stock" check
  must either pin such a seed or assert "differs for ≥1 of N", never "always
  differs"). Prefer measuring stock live under config `{}` in the same run and
  comparing, over hardcoding.
  - **J1 (jittered):** a pinned seed → `measureText('mmmmmmmmmmlli', 48px serif).width !== stock`.
  - **J2 (same-session determinism):** seed set, measure same inputs twice in ONE
    session → ALL 10 fields identical. *(critical)*
  - **J3 (cross-session determinism):** two separate `session()` calls (separate
    content_shell launches — confirmed: `lib_shell` fresh Popen + user-data-dir per
    call), same seed, same inputs → identical. *(critical — pins the content hash
    is launch-reproducible; a pointer-based font hash turns this red)*
  - **J4 (seed sensitivity):** seed A vs seed B, over N strings → `width` differs
    for ≥1 (not "always").
  - **J5 (no-op absent):** config `{}` → every field === stock exact (rule 5).
  - **J6 (bound):** fractional fields `|Δ| <= 0.125+eps`; integer fields `|Δ| <= 1`.
  - **J7 (grid = float32 round-trip):** for EVERY field, `Math.fround(v) === v`
    (every member is a float widened to double; `k/64` and `±1` both preserve
    float32-ness). Stronger and simpler than "dyadic ×4096".
  - **J8 (zero guard):** `measureText('').width === 0`; a descenderless glyph's
    `actualBoundingBoxDescent === 0` under seed.
  - **J9 (text-independence):** seed set, `measureText('a')` vs `measureText('wwwww')`
    SAME font → identical `fontBoundingBox{Ascent,Descent}`, `hangingBaseline`,
    `ideographicBaseline`, `alphabeticBaseline` (font metrics must not vary by text).
  - **J10 (text-dependence preserved):** seed set, `measureText('a').width !==
    measureText('wwwww').width`.
  - **J11 (cross-state coherence — THE mirror gate).** Run on STOCK first, record
    the max residual per identity; jittered must land in the SAME order (these are
    invariants, not jitter checks — they PASS on stock, must still PASS jittered):
    - default tb, one call: `|hangingBaseline − 0.8·fontBoundingBoxAscent| <= stock_residual`;
      `ideographicBaseline === −fontBoundingBoxDescent`.
    - `tb ∈ {hanging, ideographic, alphabetic}`: the own-named baseline ≈ 0 (≤ stock_residual).
    - ∀ `tb`: `fBBA(tb)−fBBA(alpha) === aBBA(tb)−aBBA(alpha) === −(fBBD(tb)−fBBD(alpha))
      === −(aBBD(tb)−aBBD(alpha))` (one `baseline_y′` across all fields).
    - textAlign ∈ {left,center,right}: `aBBL(center)−aBBL(left) ≈ width/2`,
      `aBBR(right)−aBBL(left) ≈ −width` (tol 1e-4).

- [ ] **Step 2: RED-first** — push + run BEFORE the .cc edit. RED expectation:
  J1/J4 FAIL (all stock), J2/J3/J5/J8/J11 PASS (stock is deterministic, unchanged,
  and internally coherent), J6/J7/J9/J10 vacuously PASS. **J11 PASSING on stock is
  required** — it proves the identities/tolerances are right before they must
  survive jitter. Record.
```bash
pushfile scripts/verify_metric_jitter.py "$VERIFY/verify_metric_jitter.py"
verify verify_metric_jitter.py
```

- [ ] **Step 3: text_metrics.cc — includes, index folds, source jitter, M′ + mirror.**
  Add includes: `components/camoucfg/blink_scope.h`,
  `components/camoucfg/canvas_noise.h`, `components/camoucfg/mask_config.h`.

  **(i) Index folds (file-local statics or inline).** `f_index` = FNV-1a over the
  **RESOLVED** font (not the requested family): `font->PrimaryFont()->PlatformData()`
  typeface family name + `GetFontDescription().ComputedSize()` bits + weight +
  slope. `tf_index = f_index ^ FNV-1a(text_ code units)`. Reproducible across
  launches (no pointers) — **J3 is the gate**; if a chosen field is not
  launch-stable, fix the fold, never weaken J3.

  **(ii) Text-dependent sources** — immediately after
  `auto [xpos, glyph_bounds] = MeasureRuns(text_painter);`, with
  `uint64_t seed = camoucfg::CanvasSeed(camoucfg::ScopeFor(nullptr));` (compute
  once at top of Update; the whole jitter is `if (seed) { … }`):
```cpp
  if (seed) {
    xpos = camoucfg::PerturbMetric(xpos, seed, tf_index, "tm.w");
    const float jx = camoucfg::PerturbMetric(glyph_bounds.x(),      seed, tf_index, "tm.l");
    const float jr = camoucfg::PerturbMetric(glyph_bounds.right(),  seed, tf_index, "tm.r");
    const float jy = camoucfg::PerturbMetric(glyph_bounds.y(),      seed, tf_index, "tm.a");
    const float jb = camoucfg::PerturbMetric(glyph_bounds.bottom(), seed, tf_index, "tm.d");
    glyph_bounds.SetRect(jx, jy, jr - jx, jb - jy);   // 4 independent jittered edges
  }
```
  (`SetRect(jx, jy, jr-jx, jb-jy)` is acceptable because `aBBL/aBBR` read
  `glyph_bounds.x()/.right()`, and `right = x + width` reconstructs `jr` — but if a
  verify shows an ulp miss on `aBBR`, store the four edges in locals and use them
  directly instead of round-tripping through `RectF`.) Everything downstream
  (`real_width = xpos`, `text_align_dx_`, `actual_bounding_box_*`) now derives from
  jittered sources through **unchanged** stock arithmetic.

  **(iii) Font-constant sources — the M′ set + mirror**, rewriting the y-block
  (lines ~133–170). Read each font metric once, jitter it (font-only `f_index`,
  distinct domain), tables only when `has_value()`:
```cpp
  // M' — jitter each font metric ONCE; downstream reads ONLY these + baseline_y'.
  float fa  = font_metrics.FloatAscent(kAlphabeticBaseline, FontMetrics::ApplyBaselineTable(true));
  float fd  = font_metrics.FloatDescent(kAlphabeticBaseline, FontMetrics::ApplyBaselineTable(true));
  const FontHeight typo = font_data->NormalizedTypoAscentAndDescent();
  float nta = typo.ascent.ToFloat();
  float ntd = typo.descent.ToFloat();
  std::optional<float> hb = font_metrics.HangingBaseline()
      ? std::optional<float>(font_metrics.HangingBaseline().value()) : std::nullopt;
  std::optional<float> ib = font_metrics.IdeographicBaseline()
      ? std::optional<float>(font_metrics.IdeographicBaseline().value()) : std::nullopt;
  std::optional<float> ab = font_metrics.AlphabeticBaseline()
      ? std::optional<float>(font_metrics.AlphabeticBaseline().value()) : std::nullopt;
  if (seed) {
    fa  = camoucfg::PerturbMetric(fa,  seed, f_index, "tm.fa");
    fd  = camoucfg::PerturbMetric(fd,  seed, f_index, "tm.fd");
    nta = camoucfg::PerturbMetric(nta, seed, f_index, "tm.nta");
    ntd = camoucfg::PerturbMetric(ntd, seed, f_index, "tm.ntd");
    if (hb) hb = camoucfg::PerturbMetric(*hb, seed, f_index, "tm.bh");
    if (ib) ib = camoucfg::PerturbMetric(*ib, seed, f_index, "tm.bi");
    if (ab) ab = camoucfg::PerturbMetric(*ab, seed, f_index, "tm.ba");
  }
  // baseline_y' — file-local MirroredBaseline reproducing GetFontBaseline EXACTLY
  // on M', incl. the /100.0 (double) here vs /100.0f (float) in setHanging below.
  const float baseline_y_p = MirroredBaseline(baseline, fa, fd, nta, ntd, hb, ib, ab);
  baseline_y = baseline_y_p;                         // member still set for other uses
  font_bounding_box_ascent_  = fa - baseline_y_p;
  font_bounding_box_descent_ = fd + baseline_y_p;
  actual_bounding_box_ascent_  = -glyph_bounds.y() - baseline_y_p;
  actual_bounding_box_descent_ =  glyph_bounds.bottom() + baseline_y_p;
  em_height_ascent_  = nta - baseline_y_p;           // now on M' (was normalized_typo_metrics)
  em_height_descent_ = ntd + baseline_y_p;
  baselines_->setAlphabetic(ab ? *ab - baseline_y_p : -baseline_y_p);
  baselines_->setHanging(hb ? *hb - baseline_y_p
      : fa * kHangingAsPercentOfAscent / 100.0f - baseline_y_p);   // /100.0f — matches stock
  baselines_->setIdeographic(ib ? *ib - baseline_y_p : -fd - baseline_y_p);
```
  where the file-local helper mirrors `GetFontBaseline`'s switch on M′:
```cpp
  namespace {
  float MirroredBaseline(V8CanvasTextBaseline::Enum tb, float fa, float fd,
                         float nta, float ntd, std::optional<float> hb,
                         std::optional<float> ib, std::optional<float> ab) {
    switch (tb) {
      case V8CanvasTextBaseline::Enum::kTop:        return nta;
      case V8CanvasTextBaseline::Enum::kHanging:
        return hb ? *hb : fa * kHangingAsPercentOfAscent / 100.0;   // /100.0 double — matches GetFontBaseline
      case V8CanvasTextBaseline::Enum::kIdeographic: return ib ? *ib : -fd;
      case V8CanvasTextBaseline::Enum::kBottom:     return -ntd;
      case V8CanvasTextBaseline::Enum::kMiddle:     return (nta - ntd) / 2.0f;
      case V8CanvasTextBaseline::Enum::kAlphabetic: return ab ? *ab : 0;
      default:                                      return 0;
    }
  }
  }  // namespace
```
  **Do NOT** separately jitter any derived member or baseline result — they inherit
  from M′/jittered sources. **Do NOT** touch the static `GetFontBaseline` (its
  line-~439 caller is the gated-off ExtendedTextMetrics path — documented residual).
  Keep the `/100.0` vs `/100.0f` asymmetry byte-for-byte (stock's `tb=hanging`
  residual depends on it; J11 checks it).

- [ ] **Step 4: Build + verify GREEN** — `contentshell` (NON-ZERO steps),
  `verify verify_metric_jitter.py` → all J1–J11 PASS. If J11 fails, the mirror
  desynced from `GetFontBaseline`/the y-block — diff them, do not loosen J11.

- [ ] **Step 5: Commit the Mac verify script**
```bash
git add scripts/verify_metric_jitter.py
git commit -m "test(metric-jitter): verify J1-J11 (jitter, determinism, grid, coherence mirror)"
```

---

### Task 3: Extract patch, wire apply.sh, regression

**Files:** Create `patches/metric-jitter.patch`; Modify `scripts/apply.sh`.

- [ ] **Step 1: Extract** `text_metrics.cc` to `patches/metric-jitter.patch` with
  `git diff HEAD -- third_party/blink/renderer/core/html/canvas/text_metrics.cc`
  (redirect Mac-side via `pullfile` of the diff, or `runwsl "... > /tmp/mj.patch"`
  then `pullfile`). Confirm ONE file, non-empty, and that the camoucfg includes
  appear as `+` lines (not context — the delta-only trap from sp4-tz-locale).
- [ ] **Step 2: Round-trip** — `git checkout --` the file in the checkout,
  `pushto patches/metric-jitter.patch`, `git apply --3way`, `echo APPLY_OK`,
  `contentshell` (NON-ZERO), `verify verify_metric_jitter.py` → all PASS.
- [ ] **Step 3: apply.sh** — append `"$ROOT/patches/metric-jitter.patch"` LAST,
  after `"$ROOT/patches/window-geometry.patch"`.
- [ ] **Step 4: Full regression** (record counts):
```bash
unittests 'CamoucfgKeysTest.*:CanvasNoiseTest.*:PerturbRgbaTest.*:DeriveTest.*:DeriveDeltaTest.*:DeriveUnitTest.*:MaskConfigTest.*:GettersTest.*'
verify verify_metric_jitter.py   # J1-J11
verify verify_sp3a.py            # sp3a canvas PIXEL noise — the shared canvas_noise.cc neighbour (MUST stay green)
verify verify_window_geometry.py # 7/7 (last slice)
```
  Expected: camoucfg all PASS (78 keys unchanged), sp3a canvas verify UNCHANGED
  (proves the `canvas_noise.cc` edit didn't regress `PerturbRgba`). Missing
  baseline → `--capture-baseline` once, note it.
- [ ] **Step 5: Commit**
```bash
git add patches/metric-jitter.patch scripts/apply.sh
git commit -m "feat(metric-jitter): config-driven TextMetrics jitter — patch + apply wiring"
```

---

## Self-Review notes

- **Spec coverage:** 10 JS-readable fields (measurement §4) via **source-quantity
  perturbation** — text-dependent sources (`xpos` + 4 glyph edges, `tf_index`) and
  the font-metric set M′ (`f_index`) + `MirroredBaseline`; grid-preserving
  (value-branch: integer stock → integer ±1, dyadic → k/64); zero-guarded.
  em_height / extended methods gated off (§5).
- **Coherence gates:** J11 pins cross-textAlign/textBaseline identities (the mirror
  is correct); J9 pins font-constants stay text-independent; J7 = float32
  round-trip pins grid; J2/J3 pin determinism (resolved-font key, launch-stable);
  J5 pins rule-5 no-op. J11 must pass on STOCK first (RED-first Step 2).
- **No key/DEPS/BUILD change** — reuse `canvas:seed`; the whole slice is
  `canvas_noise.{h,cc,unittest}` (additions) + `text_metrics.cc` (patch).
- **Shared-file risk:** `canvas_noise.cc` is also sp3a's; Task 3 regression runs
  the sp3a canvas verify to prove no `PerturbRgba` regression.
- **REBASE CHECKLIST (version-coupled — flag in the ledger):** on every Chromium
  uprev, re-diff `MirroredBaseline` against the upstream `GetFontBaseline` switch
  AND the y-block/baseline formulas; an upstream formula change silently desyncs
  the mirror. J11 is the tripwire but runs on Linux (fallback branches only — Win/
  mac `has_value()` table paths unverified here, #44 lesson 3).

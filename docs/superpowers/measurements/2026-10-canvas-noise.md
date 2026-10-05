# Canvas noise redesign (S1 + S2): measurements

Spec: `specs/2026-10-05-canvas-noise-redesign-design.md`. Plan:
`plans/2026-10-05-canvas-noise-redesign.md`. Host runner:
`scripts/measure_canvas_noise.py` (stock Chrome 154.0.8037.93 against
`out\Release\chrome.exe`, 8 seeds, one launch per cell).

## 1. RED: today's build (tree 0327015f65e4c691bb785b05f0ad03c0a44e09ec)

Stock control: Chrome `154.0.8037.93`. Rows are the runner's verdict lines,
copied from `red-headed.log`, `red-headless.log` and `red-dense.log`
(`--mode headed`, `--mode headless`, `--mode headed --density 0.05`).

| row | headed | headless | headed, density 0.05 |
|---|---|---|---|
| P1 text, 512x128, varies across seeds | FAIL (2 distinct of 8, stock among them) | FAIL (2 of 8, stock among them) | PASS (8 of 8, stock not among them) |
| P2 text, willReadFrequently, varies | FAIL (3 of 8, stock among them) | FAIL (3 of 8, stock among them) | PASS (8 of 8) |
| P3 flat drawings equal stock, putImageData round trip exact | FAIL (differ: edge, glClear, line, solid; round trip exact: False) | FAIL (same) | FAIL (same) |
| P4 drawImage / createImageBitmap agree with getImageData | FAIL (all agree: False) | FAIL | FAIL |
| P5 text at x and x+1 differ only by the shift | FAIL (all equal: False) | FAIL | FAIL |
| S2 oracle text canvas varies (>=6 distinct) | FAIL (3 of 8, stock among them) | FAIL (3 of 8) | PASS (8 of 8) |
| S2 oracle shape canvas varies (all distinct) | FAIL (7 of 8, stock among them) | FAIL (7 of 8) | PASS (8 of 8) |
| S1 solid fill and WebGL clear read one colour | FAIL (colours: (2,4) (3,5) (4,3) (4,4) (5,4)) | FAIL (same five) | FAIL (colours: (13,13) (13,16) (15,17) (16,13) (16,14) (16,16) (16,17)) |
| rule 5: fork without config reads as stock | PASS (differ: []) | PASS | PASS |

Reading:

- Headed and headless are identical on today's build.
- S1 grows with density (5 colours at the default, 7 at 0.05, each far
  further apart), so calibrating today's rule cannot make solid and
  WebGL clear agree.
- Density 0.05 buys S2 and P1/P2 (all 8 distinct, stock absent) but P3,
  P4, P5 and S1 still fail: more noise is not the fix.
- P4 FAILS at the default density 0.0005, as the spec assumed (no surprise
  there). The `red-dense` run also fails it.
- Rule 5 passes, so the client sets no `CAMOU_CONFIG` for
  `launch(config=None)` and the browser without config equals stock.

## 2. Spike: a seeded sub-pixel text offset (throwaway)

Built on Windows only (49 steps, 52 s), applied to `base_rendering_context_2d.cc`
on top of the pin plus the change set, measured, then reversed (file hash back
to its original, rebuild 49 steps, 48 s). Nothing of it is committed. The spike
adds two edits:

```cpp
#include "components/camoucfg/canvas_readback.h"
#include "components/camoucfg/derive.h"      // added

  location.Offset(0, TextMetrics::GetFontBaseline(baseline, *font_data));
  // SPIKE (throwaway): a per-seed sub-pixel text origin.
  if (const uint64_t camou_seed =
          camoucfg::CanvasSeed(camoucfg::ScopeFor(GetTopExecutionContext()))) {
    location.Offset(
        static_cast<float>(camoucfg::DeriveUnit(camou_seed, "canvas-text-offset-x", 0)),
        static_cast<float>(camoucfg::DeriveUnit(camou_seed, "canvas-text-offset-y", 0)));
  }
```

Raw `[0, 1)` offsets, no quantisation (Skia's subpixel binning does that).

Why density 0: the spike build still carries today's readback noise, and RED
showed P3, P4 and P5 already FAIL from that noise alone. To isolate the text
offset, the two decision runs set `--density 0` (readback noise off through
config); the offset still follows `canvas:seed`. A third run at the default
density is reference only.

| Row | spike-headed (density 0) | spike-headless (density 0) | spike-default (headed, reference) |
|---|---|---|---|
| P1 text varies | PASS (8 of 8, stock absent) | PASS (same) | PASS (8 of 8) |
| P2 willReadFrequently text varies | PASS (8 of 8) | PASS (same) | PASS (8 of 8) |
| P3 flat drawings equal stock, round trip | PASS (differ: [], exact) | PASS | FAIL (differ: edge, glClear, line, solid) |
| P4 drawImage / createImageBitmap agree | PASS | PASS | FAIL |
| P5 text at x and x+1 differ only by the shift | PASS | PASS | FAIL |
| S2 text canvas varies (>=6) | PASS (8 of 8) | PASS | PASS (8 of 8) |
| S2 shape canvas varies | FAIL (1 of 8, stock among them) | FAIL (same) | FAIL (7 of 8) |
| S1 solid and WebGL clear one colour | PASS (1,1) | PASS | FAIL (5 colours) |
| rule 5 | PASS | PASS | PASS |

Reading: with readback noise off, P3 `edge`/`line`/`roundtrip` do not differ
from stock, so the offset leaves shapes and lines alone. P5 passes, so text at
x and x+1 is the same glyph run shifted. S2 shape failing at density 0 is
expected (no readback noise, no shape variation) and is not a decision input.
The default-density run reproduces RED's failures, which come from readback
noise, not from the offset.

## 3. Decision: target

P1 to P5 all PASS in both modes at density 0, so the design is the **target**:
a draw-time sub-pixel text offset from `canvas:seed`. Skia does not snap the
glyphs away (P1, P2: 8 distinct of 8 on both canvas kinds), and the lever is no
tell (P3, P4, P5 pass with noise off). S1, S2 and rule-5 rows are recorded
above and were not used for the decision.

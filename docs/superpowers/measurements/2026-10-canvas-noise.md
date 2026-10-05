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

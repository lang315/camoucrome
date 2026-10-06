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

## 4. verify_sp3a RED

`scripts/verify_sp3a.py` at branch commit 7e9fdbf (box tree SHA 7e9fdbf) on today's unchanged WSL build. C11-C14 fail as the plan expects; C6 passes.

```
PASS  1  seeded toDataURL deterministic across two reads
PASS  10 accessors native + window keys unchanged
FAIL  11 flat drawings read as unconfigured (solid, edge, 1px line, WebGL clear, worker)
FAIL  12 putImageData round trip exact
FAIL  13 drawImage and createImageBitmap copies agree with getImageData
FAIL  14 oracle text (>=6) and shape (8) canvases vary over 8 seeds, none stock
PASS  2  seeded toDataURL differs from stock
PASS  3  unconfigured toDataURL byte-identical to stock
PASS  4  seeded toBlob deterministic and differs from stock
PASS  5  seeded getImageData deterministic, differs from stock, off==stock
PASS  6  seeded readPixels of a gradient triangle deterministic, differs from unconfigured
PASS  7  seeded OffscreenCanvas.convertToBlob deterministic and differs
PASS  8  worker OffscreenCanvas readback deterministic and differs (parity)
PASS  9  DevTools screenshot identical seeded vs stock (screen unchanged)
      C11: differ from unconfigured ['edge', 'glClear', 'glClearColours', 'solid', 'solidColours', 'worker'], colours (2D, WebGL) (3, 4), unconfigured clear == stock baseline True
      C12: {'exact': False, 'first': 6082}
      C13: {'a': 3226468587, 'viaDraw': 2415289306, 'viaBitmap': 2415289306}
      C14: text 1 distinct, stock among them True; shape 7 distinct, stock among them True
FAIL
rc=1
```

## 5. Calibration

Windows host, fork built from tree 1dced0a (target design), 8 seeds, `canvas:noiseDensity` set through config, no rebuild per value. Only the S2 shape row depends on density; P1-P5, S2 text, S1 and rule 5 PASS in every completed run.

| D | mode | S2 text | S2 shape |
|---|---|---|---|
| 0.0005 (old default, `cn-default`) | headed | PASS, 8 of 8 | FAIL, 3 of 8, stock among them |
| 0.01 | headed | runner crashed twice (a seed's cell had no WebGL clear count; per-seed probe at 0.01 then read all 8 fine), not measured | not measured |
| 0.01 | headless | PASS, 8 of 8 | FAIL, 7 of 8, stock among them |
| 0.02 | headed | PASS, 8 of 8 | PASS, 8 of 8, stock not among them |
| 0.02 | headless | PASS, 8 of 8 | PASS, 8 of 8, stock not among them |

Chosen: the smallest passing D is 0.02 (0.01 fails headless). The default is 2 x D = **0.04**, because 8 seeds is a small sample. At 0.04 (the rebuilt binary, headless) every row PASSES, including P3, P4, P5, S1 and rule 5. The 0.04 headed run was not repeated.

## 6. Final

Tree `f8c327f` (target design, default density 0.04), fork `out\Release\chrome.exe`
against stock Chrome 154.0.8037.93, 8 seeds, lock `cn final`. Both modes, one
run each; every verdict row PASS, including the S2 shape row at 8 of 8:

```
final-headed and final-headless (identical):
PASS  P1 text, 512x128 canvas, varies across seeds  (8 distinct of 8, stock among them: False)
PASS  P2 text, willReadFrequently canvas, varies across seeds  (8 distinct of 8, stock among them: False)
PASS  P3 flat drawings equal stock, putImageData round trip exact  (differ: [], round trip exact: True)
PASS  P4 drawImage and createImageBitmap agree with getImageData  (all agree: True)
PASS  P5 text at x and x+1 differ only by the shift  (all equal: True)
PASS  S2 oracle text canvas varies (>=6 distinct)  (8 distinct of 8, stock among them: False)
PASS  S2 oracle shape canvas varies (all distinct)  (8 distinct of 8, stock among them: False)
PASS  S1 solid fill and WebGL clear read one colour  (colours: [(1, 1)])
PASS  rule 5: the fork without config reads as stock  (differ: [])
```

The headed run is the headed evidence at 0.04 that section 5 lacked.

`verify_sp3a` on Windows `chrome` (`sp3a-win.log`, rc=1): the stock baseline
`content_shell-sp3a-stock-canvas.json` is not on the host (`baseline load ...
FileNotFoundError`), so every clause that compares with it is UNMEASURED, not
passed. Their FAIL lines are that missing file, not a measured difference.

| clause | result |
|---|---|
| C1 deterministic, C9 text-free screenshot, C12 round trip exact, C13 copies agree, C14 oracle text (>=6) and shape (8) vary, none stock | PASS |
| C11 live part: differ from unconfigured `[]`, colours (2D, WebGL) (1, 1) | measured, no difference |
| C11 "unconfigured clear == stock baseline" (False), C2 to C8, C10 | UNMEASURED (baseline absent) |

Regression verifies on the host (idle, same env): `verify_windows_client.py`
`11 PASS 0 FAIL`, rc=0; `verify_sp6b_driver.py` `ALL_PASS`, rc=0 (its stock-driver
RED rows C1 and C5 print FAIL by design).

WebGL context missing (`glClear='no context'`), observed: 0 of 2 stock, 0 of 2
unconfigured and 0 of 16 seeded cells in the two final runs. In section 5's runs
it crashed the runner three times (`cn-default` once, `cal-0.01-headed` twice;
the cell is not recorded), all in seeded arms. A probe of the same configs read
WebGL on every seed. That is intermittent, ties to the roadmap's S4
(fork instability), and the runner now reports S1 and P3 as UNMEASURED naming
the cells, instead of crashing (`measure_canvas_noise.py`, two pytest cases).

Carry-overs from earlier sections:

- Section 1 (Task 2): the build lock was held and the stock version was checked.
  The WebGL clear read 4 colours in one RED run and 5 in another, and the S2 text
  count in RED differed from Step 2's baseline; WebGL colour count is noisy
  between launches.
- Section 2 (Task 3): H0 = `35C9CB5C78E3FD2E14F72CF9D307DB6A82C95E72E36AA105A629CBFFF9686FE9`
  (hash of `base_rendering_context_2d.cc`); the post-reversal hash is equal.
- Section 5 (Task 9): the first `cn` build failed on a clang out-of-memory error
  (5 failed steps) and the retry took 218 steps; the density rebuild took 59
  steps; one `cal-0.01-headed` crash log exists; the 0.04 headless row was logged as `final-headless.log`
  (this section's run reused that label and overwrote it).

### WSL verify at HEAD

Final fix wave, branch `s1/canvas-noise`, box `content_shell` built from the tree
at `aec6675` plus the flag-placement change (lock `cn finalfix`). The imported-pixels
flag now sets only after the early returns (`drawImage` after the empty-source-rect
return, `createPattern` just before the successful return), and the anti-aliased
rect flag sets after `ValidateRectForCanvas` in `fillRect` and `strokeRect`. Build:
`Build Succeeded: 19 steps`; gtest PASSED 10, 10, 8; `gn check` core, modules/canvas
and modules/webgl each `Header dependency check OK`; checkdeps on canvas2d and
core/html/canvas `SUCCESS`.

`verify_sp3a.py`, default density 0.04 (the verify rows C12 and C13 now draw an arc
first, so their canvases are eligible; FLAT gained `solidEligible`):

```
PASS  1 .. PASS  14 (all fourteen), ALL_PASS
PASS  11 flat drawings read as unconfigured (solid, edge, 1px line, WebGL clear, worker)
PASS  12 putImageData round trip exact
PASS  13 drawImage and createImageBitmap copies agree with getImageData
PASS  14 oracle text (>=6) and shape (8) canvases vary over 8 seeds, none stock
```

Mutation proof (not committed): removing `camou_imported_pixels_ = true;` from
`PutByteArray` and from the `drawImage` block, rebuild `4 steps`:

```
FAIL  12 putImageData round trip exact
FAIL  13 drawImage and createImageBitmap copies agree with getImageData
      C12: {'exact': False, 'first': 310}
      C13: {'a': 2404197551, 'viaDraw': 3214157266, 'viaBitmap': 3214157266}
FAIL                 (every other row PASS)
```

Restored from a byte copy (sha256 equal before and after), rebuilt `4 steps`, and
`verify_sp3a` returned to ALL_PASS.

`verify_review_2026_09_24.py`: R1 and R2 now draw an arc so the canvas is eligible
under the target design (R1 diffs the seeded arc canvas against the unconfigured
one and also requires the solid corner pixel to stay `100,150,200,255`; R2 keeps its
sub-rect check on a canvas with an arc):

```
PASS  R1 seed 4000000000 noises the arc canvas, not the solid fill
PASS  R2 sub-rect getImageData agrees with full read
PASS  R3 .. PASS  R12 (ten more rows)
12/12 ALL_PASS
```

### final2 (Windows host, flag placement and eligible-canvas rows)

Tree `9cf82ac` then `d169041`, default density 0.04, lock `windows cn finalfix`. The
one changed Blink file (`canvas_2d_recorder_context.cc`) went to the Windows tree by
per-file replacement: pre-hash `2B0BAD65...F8C1A` equal to the previous box-tip blob,
post-hash `F47ABFE6...9425D` equal to the new tip blob; the tree's sp3a patch sha256
`D122B6C4...830AE` equals the Mac's. Build `final2`: `Build Succeeded: 49 steps`,
rc=0, 52 s.

Logs (earlier logs untouched): `final2-headed.log` (first run, two FAIL rows, below),
`final2-headed-b.log`, `final2-headless.log`.

First headed run `final2-headed.log`, tree `9cf82ac`: P4 FAIL (all agree: False, 8 of
8 seeds) and rule 5 FAIL (`glClear`, `glClearColours`: the unconfigured cell had no
WebGL context, the known flake). P4 was a runner defect, not the engine: the copy
destination's new arc showed through the transparent parts of the source canvas, so
the copy could not equal the source read. The source is now filled opaque first
(`d169041`); the WSL `COPY` row already had an opaque scene.

```
final2-headed-b and final2-headless (identical verdicts):
PASS  P1 text, 512x128 canvas, varies across seeds  (8 distinct of 8, stock among them: False)
PASS  P2 text, willReadFrequently canvas, varies across seeds  (8 distinct of 8, stock among them: False)
PASS  P3 flat drawings equal stock, putImageData round trip exact  (differ: [], round trip exact: True)
PASS  P4 drawImage and createImageBitmap agree with getImageData  (all agree: True)
PASS  P5 text at x and x+1 differ only by the shift  (all equal: True)
PASS  S2 oracle text canvas varies (>=6 distinct)  (8 distinct of 8, stock among them: False)
PASS  S2 oracle shape canvas varies (all distinct)  (8 distinct of 8, stock among them: False)
PASS  S1 solid fill and WebGL clear read one colour  (colours: [(1, 1)])
PASS  rule 5: the fork without config reads as stock  (differ: [])
```

## 7. Step 2 re-measure

`measure_step2.py run` on the host, fork against stock, both modes, 0 errors.
Only scrubbed numbers are copied; no detector text, screenshots or run files.

| check | result |
|---|---|
| `noise.canvas2d`, `noise.webgl` | 1 and 1, both modes, both arms |
| `oracle.canvas.text`, `oracle.canvas.shape` | fork differs from control, headed and headless |
| linkability: `canvas.text`, `canvas.shape` among shared leaves | control: both shared; fork: neither, in both modes (fork shares 215 of 234 headed, 217 headless; control 230) |
| stability: canvas leaves changed across relaunch | none, either arm, either mode |
| CreepJS "rgba noise" | absent in all four captures (non-empty: canvas and webgl sections present) |

Not clean, and not canvas: in this run the fork's headless relaunch changed the
WebGPU leaves and the HEVC codec answer (12 leaves), the S4 instability. The
control changed nothing.

## 8. Known gaps

- Any image draw leaves the canvas without readback noise (the draw-time text
  offset still applies). `drawImage` and `createPattern` of an
  image, video, VideoFrame, SVG, canvas, OffscreenCanvas or ImageBitmap set the
  imported-pixels flag, so the VideoFrame gap of the first draft is closed.
- `transferToImageBitmap` is not covered (the spec lists it). Partly addressed
  by S2b: the noise mask now resets on transfer, but the transfer itself is
  still not covered (measurements/2026-10-canvas-noise-s2b.md).
- A pattern created on one context and filled on another does not flag the second
  context (`createPattern` across contexts). Closed by S2b (measurements/2026-10-canvas-noise-s2b.md).
- Cost, UNMEASURED. Every consumer behind `GetSourceImageForCanvas` now pays a
  `GetSwSkImage()` readback plus a full-canvas noise pass whenever its source
  changed: `drawImage(canvas)`, `createPattern`, `texImage2D(canvas)` and
  captureStream's two-copy frames. For an accelerated source that is a GPU-to-CPU
  sync where stock has none. Frame timing was not measured. Whether `GetImage()`
  returns the same object for an unchanged GPU canvas, so the CamouNoised cache
  hits, is also UNMEASURED.
- There is no `texImage2D(canvas)` verify row.
- The text offset's dirty rect: `DidDraw` bounds come from the unshifted origin, so
  a shifted glyph may land up to 1 px outside it. Not checked on screen.
- `verify_sp3a` has no stock baseline on the Windows host (section 6), so its
  baseline clauses are unmeasured there.
- `createPattern` flips eligibility without a draw. A `createPattern` from a canvas
  source flips the creating context to stock even if the pattern is never used. An
  off-canvas or transparent arc flips eligibility on. A pattern created on one
  context and used on another does not flag the second. Closed by S2b (measurements/2026-10-canvas-noise-s2b.md).
- Any edit reseeds the readback field. The seed folds in `CanvasStateHash`, so
  reading one region before and after an unrelated draw elsewhere differs, where
  stock does not. Closed by S2b (measurements/2026-10-canvas-noise-s2b.md).
- The field is keyed by position. The same shape drawn twice at whole-pixel offsets
  gets two different fields. Closed by S2b (measurements/2026-10-canvas-noise-s2b.md).
- WebGL `readPixels` keys by position within the in-buffer part of the rect and by a
  hash of the first 1024 bytes of a tight copy of its pixels, so a sub-rect read
  disagrees with a full read. The sub-rect gap predates this branch. Closed by S2b (measurements/2026-10-canvas-noise-s2b.md).
- A seed's text offset may fall in Skia's zero subpixel bin and draw text exactly as
  stock. The 8-seed P1 cannot bound how often.

## 9. PR #27 review fixes

Review items 1, 2, 4, 7, 8, 9, 10 and 11. Verify changes at 1aabe7d; Blink and
patch change at 38b2d84. Locks `pr27 fix` (WSL) and `windows pr27` (Windows),
both released.

### RED on the build before the Blink edits (WSL, `verify_sp3a.py`)

New rows C15 (text under `ctx.scale(40,40)`) and C16 (decoded image on an
eligible canvas); the other 14 pass, so C7 and C8 against live unconfigured
sessions already pass on the old build (they measure the hook).

```
FAIL  15 text under ctx.scale(40,40) lands within 1 device px of unconfigured
FAIL  16 decoded image drawn on an eligible canvas reads as unconfigured
      C15: (dx, dy) per seed [(36, 5), (33, 9), (34, 24), (30, 19)]; unconfigured bbox (55, 83)
      C16: seeded 2468318143 != unconfigured 953644402
FAIL
```

### GREEN after the edits (WSL)

- Build: `Build Succeeded: 190 steps` (content_shell, components_unittests).
- gtest `PerturbRgba*:CanvasStateHash*:CanvasNoise*:NoisedImage*`: 10 + 10 + 8 passed.
- `gn check` of `modules/canvas` and `modules/webgl`: Header dependency check OK.
  `checkdeps.py` on both directories: SUCCESS.
- `verify_sp3a.py`: C1-C16 PASS, `ALL_PASS` (16/16).
- `verify_review_2026_09_24.py`: R1-R12 PASS, `12/12 ALL_PASS` (R1 counts changed
  pixels outside the arc's box plus 2 px and requires 0; R3 draws a
  half-transparent arc and requires seeded to differ from unconfigured).

### Mutation proof for item 11 (WSL)

`PerturbRgbaEdges` made to skip the four same-as-neighbour tests (any pixel with
enough alpha eligible), rebuilt (9 steps):

```
FAIL  11 flat drawings read as unconfigured (solid, edge, 1px line, WebGL clear, worker)
      C11: differ from unconfigured ['edge', 'glClear', 'glClearColours', 'line', 'solid', 'solidColours', 'solidEligible', 'worker'], ...
```

C11 is the only failing row. The file was restored from a copy: sha256 before and
after both `bd0d5ac73b9ecac2c98eee42bd98e06cce0e6292a2c8da2f23ef04b334e473a2`,
rebuilt (10 steps). The mutation was never committed.

### Export

Fixup into `sp3a-canvas-noise` (Ruling 6; no `components/camoucfg` path changed),
autosquash: 38 commits, 0 fixups, clean tree, `check_checkout_sync` PASS. Changed
patches (sha256): `sp3a-canvas-noise.patch`
`cbc70e550f647be2d1c09c551b58476afdcf9eb03fc7cdb1e49f2ff4864f2f96`;
`sp3b-webgl-profile.patch` (index line only)
`02015d949c3f1da8e42fc3873081771aaffe9cae1491b289b24923f4470300dd`. Both equal the
box's after transfer.

### Windows (Ruling 11)

Pre and post sha256 matched for all four Blink files:

Per file, `pre` then `post` sha256:

- `base_rendering_context_2d.cc`
  - pre `c4776c111417df3d3e255a481db6cac6a550264f68ace7a87ce4df919c13f633`
  - post `a7042345f0b2406525103623152e6830e48d9b81f0c2bf06d4c9be6ea11d71a3`
- `canvas_2d_recorder_context.cc`
  - pre `f47abfe6491d25abdc36e95b4755960e733152d961f7b23af8e18b536b99425d`
  - post `f03bf454f7dec24040b28fc4c675e12a35aaf3a66395f54cc5058fb2ea7fad3c`
- `canvas_2d_recorder_context.h`
  - pre `4733179ad8bf78be61824668dfc5ef3cf2e82a55c03a3ee2401feb467746e0fd`
  - post `6ddff2392266c652191c13b7870989780f943de56f095f954f2689b13c2f7097`
- `webgl_rendering_context_base.cc`
  - pre `dfcbdbf25266e27bfc11a44bb5c763f87f1ecf2e2e5068e491b24dc642fc0a65`
  - post `e9a0e333611dd7cbf3007c77ec43e0fed11219e0822ee0159547911a21671d66`

Build: `Build Succeeded: 70 steps`, rc=0. Host runner, shipped density 0.04:

- `final3-headed`: first run 8/9, the rule 5 row failed because the unconfigured
  cell had no WebGL context (`glClear` = "no context"; log kept as
  `final3-headed-try1.log`). Rerun once as the brief says: 9/9 PASS.
- `final3-headless`: 9/9 PASS.

`verify_sp3a.py` on Windows `chrome` (`sp3a-win3.log`): C6, C7, C8, C9, C12, C13,
C14, C15 and C16 PASS. C2, C3, C4, C5, C10 FAIL only because there is no stock
baseline file on the host (UNMEASURED; the WSL run covers them). C11 fails only
its baseline clause: its seeded rows equal unconfigured (`differ []`) and both
colour counts are 1.

### Round 2: readPixels at the real pack layout

Re-review found two problems in round 1's `readPixels` rule: it ignored
`PACK_ALIGNMENT`, so aligned reads were noised at the wrong stride (I-1), and
every other skipped read (WebGL2 `PACK_ROW_LENGTH` / `SKIP_PIXELS` /
`SKIP_ROWS`, rects reaching past the buffer) returned the clean render, a bypass
a page could diff against a default read (I-2).
Ruling: readPixels noise goes on the in-buffer part of the rect at the real
pack layout; the field is keyed by a tight copy of the pixels, so the layout
does not change it. The field is relative to the in-buffer part of the rect; a read whose in-buffer part is a strict sub-rect of the buffer gets a different field from a full read (the recorded sub-rect gap). `PerturbRgba` and
`PerturbRgbaFromConfig` gained a `row_bytes` parameter. New rows C17 (alignment
8, odd width), C18 (WebGL2 row length / skip pixels / skip rows) and C19 (rect
past the buffer); `EXPECTED = 19`. Locks `pr27 fix2` and `windows pr27 fix2`,
both released.

RED on the round-1 build (WSL):

```
FAIL  17 readPixels at PACK_ALIGNMENT 8, odd width, agrees with the default layout
FAIL  18 WebGL2 PACK_ROW_LENGTH/SKIP_PIXELS/SKIP_ROWS read agrees with the default read
FAIL  19 readPixels rect past the buffer: in-buffer part differs from unconfigured
      17 : seeded {'pix': 228, 'pad': 0, ...}, unconfigured {'pix': 0, 'pad': 0, ...}
      18 : seeded {'inside': 118, 'outside': 0, ...}, unconfigured {'inside': 0, ...}
      19 : seeded {'h': 2741506969}, unconfigured {'h': 2741506969}
```

Unit RED: with the new tests and the round-1 `canvas_noise.h`,
`components_unittests` fails to compile: `canvas_noise_unittest.cc:34:3: error: no
matching function for call to 'PerturbRgba'` (and lines 35, 41, ...).

GREEN (WSL): first build failed on `-Wunsafe-buffer-usage` for the pointer
arithmetic in `ReadPixelsHelper` (fixed with `UNSAFE_BUFFERS` and a SAFETY
comment); second build `Build Succeeded: 34 steps`. gtest `PerturbRgba*`
including `PaddedRowsGetTheTightField` and `RowBytesBelowWidthIsNoOp` pass;
`gn check` (webgl, canvas, camoucfg) OK; `checkdeps` SUCCESS on all three.
`verify_sp3a.py`: 19 PASS, `ALL_PASS`. `verify_review_2026_09_24.py`: 12/12.
Export: fixups into `sp3a-canvas-noise` (Blink) and `windows-behaviour-ii`
(`canvas_noise.{h,cc}` and its test); 38 commits, 0 fixups, sync PASS, additions
identical. Patches: `sp3a-canvas-noise.patch`
`8264e1ba0b657df2074a0611717614636016609fc12137e4ec18358e823fcaf1`,
`sp3b-webgl-profile.patch` (index line)
`d95ce8f6efa01234b554002a8a6de342d3a67f6b71d96c572b8b97fdee7247db`.

Windows (Ruling 11), pre then post sha256:

- `canvas_noise.cc`: `bd0d5ac73b9ecac2c98eee42bd98e06cce0e6292a2c8da2f23ef04b334e473a2`, `97c61511305f642bd16cd73c3f8e0bdb297a6c36123547abda8f529327ccab2d`
- `canvas_noise.h`: `7fcc8b1ff04fb7c3d964dca17b3855715c6dac94f54061635f256785eebe4514`, `0e33c24046a100210c3b6e35425e3e1f2c84e6372b253dd027b21890ece4c90e`
- `canvas_noise_unittest.cc`: `27aa934100b31f02e4bd9284d9156d0bab2e5fcf9189ceb68ac50a8678168668`, `639d2fbf00645fa5745782d7c82137add09e74bf40d56ce7ff658c608830e3d1`
- `canvas_2d_recorder_context.h`: `6ddff2392266c652191c13b7870989780f943de56f095f954f2689b13c2f7097`, `9cc0bc855115b09dc44a3c24894e43bb7bce9aeb4f8ea8e73f758488687aa05e`
- `webgl_rendering_context_base.cc`: `e9a0e333611dd7cbf3007c77ec43e0fed11219e0822ee0159547911a21671d66`, `b4d6a64917aafe5d24544cee1ceca5f7354b2cea560654d3cae149e62c1c7fc0`

Build `Build Succeeded: 78 steps`, rc=0. Host runner at 0.04: `final4-headed` first run
hit a stock cell without WebGL (P3 and S1 UNMEASURED, rule 5 FAIL; log
`final4-headed-try1.log`), rerun 9/9 PASS. `final4-headless` first run lost
WebGL in seed 2 (two UNMEASURED; `final4-headless-try1.log`), rerun 9/9 PASS.
`verify_sp3a.py` on Windows `chrome` (`sp3a-win4.log`): C6 to C9 and C12 to C19
PASS; C2 to C5, C10 and C11's baseline clause fail only for lack of a stock
baseline file (UNMEASURED); C11's seeded rows equal unconfigured.

### Round 3: layouts GL rejects, C19 tightened

Locks `pr27 fix3` and `windows pr27 fix3`, both released.

- **N-1.** GL rejects `readPixels` (INVALID_OPERATION, nothing written) when
  `skip_pixels + width > (row_length ? row_length : width)`. New row C20 draws the
  triangle on a 64x64 webgl2 canvas, prefills an opaque checkerboard, sets
  `PACK_SKIP_PIXELS` 1, reads, and requires `getError()` INVALID_OPERATION and 0
  changed bytes, seeded and unconfigured. **It already PASSED on the round-2 build**
  (20/20), so an earlier check rejects the call before our block runs and the
  guard is defensive; no RED exists for it. (A first run showed C20 FAIL only
  because my row's result key `err` collided with the page's "no context" marker;
  renamed to `glerr`, not a product failure.) The guard now reads
  `skip_pixels + width <= stride_px`, GL's rule verbatim, with a comment.
- **N-2.** C19 now requires the in-buffer part of `readPixels(-8, -8, 72, 72)` (prefilled
  `0xAB`) to equal the default read A byte for byte, to differ from the unconfigured
  in-buffer part, and every out-of-buffer byte to equal the unconfigured read's.
  The field is relative to the in-buffer part of the rect; a read whose in-buffer
  part is a strict sub-rect of the buffer gets a different field from a full read
  (the recorded sub-rect gap).
- **N-3.** Wording fixed (round 2 text above, spec line 105, section 8).

GREEN (WSL): build `Build Succeeded: 192 steps`; gtest `PerturbRgba*` pass; `gn check` and
`checkdeps` OK; `verify_sp3a.py` 20 PASS `ALL_PASS`; `verify_review_2026_09_24.py` 12/12.
Export: 38 commits, 0 fixups, sync PASS. Patches: `sp3a-canvas-noise.patch`
`e765dfe638b4158aae573129a3e852bdf990571ede04a920e2f3a33d5a385c42`,
`sp3b-webgl-profile.patch` (index line)
`4c97fe5d3fcb3bf6199c0c695ee3bd371262b2cc5e918f63d1efa7afaca6e3ed`.

Windows: `webgl_rendering_context_base.cc` pre
`b4d6a64917aafe5d24544cee1ceca5f7354b2cea560654d3cae149e62c1c7fc0`, post
`25759bebb910b9b2a062ce33c410ad5f0c30ffb02146a4408769f114b87072a5`, both matched.
Build `Build Succeeded: 49 steps`, rc=0.

- `final5-headless`: 9/9 PASS.
- `final5-headed`: first run 8 PASS and rule 5 FAIL (the unconfigured cell had no WebGL
  context; `final5-headed-try1.log`). The one allowed rerun: 7 PASS, P3 and S1
  UNMEASURED (no WebGL context in seeds 1 and 6), rule 5 PASS. No run was 9/9; every
  row that could be measured passed, and no row failed on a measured value. Not
  rerun a third time (rerun cap).
- `verify_sp3a.py` on Windows `chrome` (`sp3a-win5.log`): C6 to C9 and C12 to C20 PASS;
  C2 to C5, C10 and C11's baseline clause fail only for lack of a stock baseline
  file (UNMEASURED).

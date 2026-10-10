# Canvas noise S2b: RED and cost before the change

Measurements for `docs/superpowers/specs/2026-10-06-canvas-noise-s2b-design.md`
and its implementation plan. This file holds the state of the build before S2b
(PR #27 head, box commit `55d16f07`): the new verify rows C21-C29 failing, and
the cost baseline. Later sections record the same after each task.

## 1. RED on the build before S2b (WSL, `55d16f07`)

`scripts/verify_sp3a.py` at branch commit `301ed1e`, 0-step build (the box
build is current). The 32 verdict lines, verbatim (sorted by name, as the
script prints them):

```
PASS  1  seeded toDataURL deterministic across two reads
PASS  10 accessors native + window keys unchanged
PASS  11 flat drawings read as unconfigured (solid, edge, 1px line, WebGL clear, worker)
PASS  12 putImageData round trip exact
PASS  13 drawImage and createImageBitmap copies agree with getImageData
PASS  14 oracle text (>=6) and shape (8) canvases vary over 8 seeds, none stock
PASS  15 text under ctx.scale(40,40) lands within 1 device px of unconfigured
PASS  16 decoded image drawn on an eligible canvas reads as unconfigured
PASS  17 readPixels at PACK_ALIGNMENT 8, odd width, agrees with the default layout
PASS  18 WebGL2 PACK_ROW_LENGTH/SKIP_PIXELS/SKIP_ROWS read agrees with the default read
PASS  19 readPixels rect past the buffer: in-buffer part equals the default read, not unconfigured
PASS  2  seeded toDataURL differs from stock
PASS  20 readPixels rejected by GL leaves the buffer untouched
FAIL  21 one arc at two whole-pixel offsets gets the same noise
FAIL  22 a draw elsewhere does not change a region's noise
FAIL  23 arc plus putImageData elsewhere: arc noised, pattern exact
FAIL  24a diagonal lineTo triangle carries noise
FAIL  24b round-cap stroke carries noise
FAIL  24c curved clip() + fillRect carries noise
FAIL  24d fillRect with shadowBlur carries noise
FAIL  25 a reused canvas reads like a fresh one
FAIL  26 createPattern alone marks nothing; a pattern fill reads exact
FAIL  27 checkerboard under a diagonal line stays exact (coverage, not bbox)
FAIL  28 WebGL readPixels sub-rect equals the full read's part, byte for byte
FAIL  29 WebGL toDataURL agrees with readPixels on every opaque pixel
PASS  3  unconfigured toDataURL byte-identical to stock
PASS  4  seeded toBlob deterministic and differs from stock
PASS  5  seeded getImageData deterministic, differs from stock, off==stock
PASS  6  seeded readPixels of a gradient triangle deterministic, differs from unconfigured
PASS  7  seeded OffscreenCanvas.convertToBlob deterministic, differs from unconfigured
PASS  8  worker OffscreenCanvas readback deterministic, differs from unconfigured (parity)
PASS  9  DevTools screenshot of a text-free scene identical seeded vs unconfigured
```

Notes for C21-C29, verbatim:

```
21 : seeded {'ha': 3183026031, 'hb': 882312527, 'e': 70}, unconfigured {'ha': 612045226, 'hb': 612045226, 'e': 70}
22 : seeded {'r1': 33446050, 'r2': 1417751380, 'e': 70}, unconfigured {'r1': 612045226, 'r2': 612045226, 'e': 70}
23 : seeded {'arc': 612045226, 'exact': True, 'e': 70}, unconfigured {'arc': 612045226, 'exact': True, 'e': 70}
24a: seeded {'h': 4071154615, 'e': 192}, unconfigured {'h': 4071154615, 'e': 192}
24b: seeded {'h': 504083845, 'e': 16}, unconfigured {'h': 504083845, 'e': 16}
24c: seeded {'h': 1193301648, 'e': 136}, unconfigured {'h': 1193301648, 'e': 136}
24d: seeded {'h': 2875827717, 'e': 164}, unconfigured {'h': 2875827717, 'e': 164}
25 : seeded {'h1': 1847293814, 'h2': 712641204, 'e': 78}, unconfigured {'h1': 1847293814, 'h2': 1847293814, 'e': 78}
26 : seeded {'p1': 1847293814, 'e': 78, 'hB': 3555660037}, unconfigured {'p1': 1847293814, 'e': 78, 'hB': 3555660037}
27 : seeded {'h': 23700512, 'e': 1444}, unconfigured {'h': 3912342789, 'e': 1444}
28 : seeded {'diff': 136, 'h': 4118271887}, unconfigured {'diff': 0, 'h': 1106472337}
29 : seeded {'diff': 207, 'opaque': 4096, 'h': 1317655965}, unconfigured {'diff': 0, 'opaque': 4096, 'h': 2741506969}
```

Result: `FAIL`, rc=1. C1-C20 PASS; C21-C29 FAIL (12 lines); no row is vacuous
(every unconfigured guard held, `e` > 0).

### Addendum: C27 redrawn (2026-10-06)

C27 redrawn (2026-10-06): the 2-colour checkerboard has only 2 distinct 3x3
patch types, so under the per-patch key whether noise lands on it is one coin
flip per seed, and the row passed on a build where the whole canvas is still
eligible. It now draws 1px pseudo-random opaque colours (`b21a376`). On the
Task 2 build (the old AA flag still marks the whole canvas) it FAILs as it
should:

```
FAIL  27 1px random colours under a diagonal line stay exact (coverage, not bbox)
      27 : seeded {'h': 2074514327, 'e': 1444}, unconfigured {'h': 2277842109, 'e': 1444}
```

## 2. Cost before S2b

`scripts/measure_canvas_cost.py` on WSL `content_shell` (CPU raster,
SwiftShader GL), seeded against unconfigured. These are PR #27's costs:

```
draw: seeded median 35.70 ms, unconfigured median 24.90 ms, seeded/unconfigured ratio 1.43
readPixels 64x64: seeded median 0.40 ms, unconfigured median 0.30 ms, seeded/unconfigured ratio 1.33
readPixels 1024x1024: seeded median 28.60 ms, unconfigured median 1.80 ms, seeded/unconfigured ratio 15.89
```

## 3. Task 2: patch key

Noise is keyed by each pixel's 3x3 source patch (bottom-up aware) and gated
by a `NoiseMask`; `CanvasStateHash` and the content fold are gone. The Blink
call site passes `min_alpha` 1, no mask, and the snapshot's orientation.

RED (unit tests committed first, `components_unittests` on the box):

```
../../components/camoucfg/canvas_noise_unittest.cc:34:3: error: no matching function for call to 'PerturbRgba'
```

GREEN, `Build Succeeded: 72 steps`. Every gtest PASSED, 0 FAILED, including
the 8 new tests (the brief counted 7): `PerturbRgbaEdgesTest.{SamePatchGetsSameNoiseAnywhere,
BottomUpMatchesTopDown, MaskGatesEachPixel, CoarseMaskCellCoversItsPixels,
MaskOfAnotherSizeIsNoOp}`, `PerturbRgbaTest.SubRectInteriorMatchesFullRead`,
`NoisedImageTest.{EditElsewhereKeepsAPixelsNoise, MinAlpha255LeavesPartialAlpha}`
(2 old tests deleted).

`verify_sp3a.py`: C1-C20 PASS, C21 PASS, C22 PASS, C27 PASS, C29 PASS;
C23, C24a-d, C25, C26, C28 FAIL (C28: sub-rect diff 7 bytes, was 136).
`verify_review_2026_09_24.py`: 12/12 ALL_PASS. `gn check` core: OK;
checkdeps: clean.

Export: only `patches/sp3a-canvas-noise.patch` changed (the call site); the
additions came back byte-identical to the pushed tree.

## 4. Task 3: mask

- RED (tests only, `9593a8f`): `autoninja components_unittests` fails with
  `canvas_mask_unittest.cc:5:10: fatal error: 'components/camoucfg/canvas_mask.h' file not found`.
- GREEN (`eac3d99`): `Build Succeeded: 87 steps` (non-zero). `CanvasNoiseMaskTest.*`: 9/9 pass
  (StartsEmptyAndFullOpaqueCoverMarksNothing, PartialCoverageMarksAaFullDoesNot,
  FullSolidOpaqueCoverClearsBothMarks, SolidNotOpaqueLeavesMarksOnFullCoverage,
  ImportedWinsAndClearRectResets, GradientAndPatternKindsMarkEveryCoveredPixel,
  CoverageOutsideTheCanvasIsIgnored, GenerationBumpsOnlyOnChange, CoarseCellsAboveTheCap).
  The other filtered suites still pass.
- Box: three new files and `BUILD.gn` fixed up into the `components/camoucfg/BUILD.gn`
  last-touch commit; 38 commits, 0 fixups, tree clean. Export reproduced the pushed
  tree byte for byte (no patch, no additions change), `check_checkout_sync` PASS,
  `check_additions_build` PASS (42 files).

## 5. Task 4: 2D masks

RED (the Task 2 build; section 3 and the C27 addendum): C21, C22 and C29 PASS
there; C23, C24a-d, C25, C26, C27 and C28 FAIL:

```
FAIL  23 arc plus putImageData elsewhere: arc noised, pattern exact
FAIL  24a diagonal lineTo triangle carries noise
FAIL  24b round-cap stroke carries noise
FAIL  24c curved clip() + fillRect carries noise
FAIL  24d fillRect with shadowBlur carries noise
FAIL  25 a reused canvas reads like a fresh one
FAIL  26 createPattern alone marks nothing; a pattern fill reads exact
FAIL  27 1px random colours under a diagonal line stay exact (coverage, not bbox)
FAIL  28 WebGL readPixels sub-rect equals the full read's part, byte for byte
```

GREEN (`ae2296e`): `Build Succeeded: 276 steps`; `components_unittests` filter
PASSED 10/10/10/10/5, 0 FAILED. `gn check` core, canvas and webgl: `Header
dependency check OK` each. `checkdeps` on `modules/canvas` and
`core/html/canvas`: `SUCCESS`, rc 0. (`gn check` takes one label per call; the
W5g one-liner with three labels prints a usage error.)

`verify_sp3a.py`: C1-C27 and C29 PASS (31 rows), C28 FAIL as planned
(`28 : seeded {'diff': 7, ...}`, Task 5), rc=1. `verify_review_2026_09_24.py`:
12/12 ALL_PASS. C11, C12, C13, C16 PASS.

Mutation proof (C27 needs coverage): the `DrawInternal` replay line replaced by
"every replayed draw marks its dirty rect aa" (`CamouMarkRect(area, kAa)`).
`Build Succeeded: 22 steps`. Result: `FAIL  27 1px random colours under a
diagonal line stay exact` (seeded `h` 2074514327 vs unconfigured 2277842109),
and `FAIL 26` and `FAIL 28`; C11, C12, C13, C16, C21, C23 still PASS. Reverted
(`grep -c MUTATION` 0, header sha256 equal to the pre-mutation backup),
`Build Succeeded: 23 steps`, rerun: the GREEN result above.

Export: only `patches/sp3a-canvas-noise.patch` changed (DEPS, core, canvas2d);
additions byte-identical. Box branch: 38 commits, 0 fixups, tree clean;
`check_checkout_sync` PASS (45 files), `check_additions_build` PASS (42 files),
`gen_keys.py --check` PASS.

## 5b. Task 4 fix round 1

RED (C30-C32 added, `284d995`, no build; the Task 4 build): 31 PASS, 4 FAIL,
rc=1, none vacuous (`e` 1444):

```
FAIL  28 WebGL readPixels sub-rect equals the full read's part, byte for byte
FAIL  30 destination-out wipe then translucent speckle reads like a fresh canvas
FAIL  31 transferToImageBitmap then translucent speckle reads like a fresh canvas
FAIL  32 copy fill then translucent speckle reads like a fresh canvas
      30 : seeded {'h': 2808637224, 'fresh': 313168094, 'e': 1444}, unconfigured {'h': 313168094, 'fresh': 313168094, 'e': 1444}
      31 : seeded {'h': 2808637224, 'fresh': 313168094, 'e': 1444}, unconfigured {'h': 313168094, 'fresh': 313168094, 'e': 1444}
      32 : seeded {'h': 1759471716, 'fresh': 1148931243, 'e': 1444}, unconfigured {'h': 1148931243, 'fresh': 1148931243, 'e': 1444}
```

GREEN (`406a527`): `Build Succeeded: 354 steps`; gtest PASSED, 0 FAILED; `gn check`
core, canvas, webgl OK; checkdeps SUCCESS. `verify_sp3a.py`: 35 rows, C1-C27
PASS, C28 FAIL (Task 5; `diff` 7), C29-C32 PASS, rc=1.
`verify_review_2026_09_24.py`: 12/12.

Pattern-styled text: no verify row, because the per-seed text offset makes it differ from unconfigured; covered by code review only.

## 6. Task 5: WebGL

RED (Task 4 fix round, `406a527`): `verify_sp3a.py` 35 rows, C28 FAIL
(`diff` 7), the WebGL sub-rect against the full read. All other rows PASS.

Change: `readPixels` reads up to four 1px margin strips from the drawing
buffer into a tight bottom-up scratch, noises the scratch, and copies the
in-buffer part back; `CamouNoiseMinAlpha()` is 255 in WebGL, so the snapshot
and `readPixels` share one field. A binder failure leaves the read unnoised.

First build failed with 8 `-Wshorten-64-to-32` errors (brief's EDITS used
`int64_t` for `GLint` args and `size_t` for `Vector` sizes). Only casts were
added (`static_cast<GLint>`, `static_cast<wtf_size_t>`), no behaviour change.

GREEN: `Build Succeeded: 141 steps`; gtest PASSED (10, 10, 10, 10, 5), 0
FAILED; `gn check` core, canvas, webgl: `Header dependency check OK`;
checkdeps webgl and canvas: SUCCESS. Export: 38 commits, 0 fixup, box clean,
sync gate PASS (45 files). Changed: `sp3a-canvas-noise.patch`,
`sp3b-webgl-profile.patch` (index line only).

```
verify_sp3a.py: 35 PASS (C1-C32 incl. 24a-d), ALL_PASS, rc=0
  17 PASS, 18 PASS, 19 PASS, 20 PASS (pack layouts unchanged)
  28 PASS  WebGL readPixels sub-rect equals the full read's part, byte for byte
  29 PASS  WebGL toDataURL agrees with readPixels on every opaque pixel
verify_review_2026_09_24.py: 12/12 ALL_PASS
```

Cost (WSL `content_shell`, CPU raster, SwiftShader GL):

| | before (Task 1) | after (Task 5) |
|---|---|---|
| draw | 1.43 (35.70 / 24.90 ms) | 4.35 (109.95 / 25.25 ms) |
| readPixels 64x64 | 1.33 | ~~1.11 (1.00 / 0.90 ms)~~ INVALID, see section 12 |
| readPixels 1024x1024 | 15.89 | ~~7.06 (29.65 / 4.20 ms)~~ INVALID, see section 12 |

The two struck `readPixels` values are invalid: they were measured before the Task 5 seed
gate, when the unconfigured arm also did the strips and the scratch copy, so its
denominator (0.90 / 4.20 ms) was inflated. Section 12 has the corrected figures.

The draw ratio is above 2.0. It is attributed to the 2D mask replay (Tasks 3-4);
no draw ratio was measured between Task 1 and Task 5. This task touches
`readPixels` only. Recorded as a known gap for S2c. It does not block. Partly closed by S2c: the draw-time cost is gone, but the replay moved to flush time and `draw_read` remains a MISS (measurements/2026-10-canvas-noise-s2c.md §10, §12).

Fix round 1: the strip block is gated on `canvas:seed != 0`, so an
unconfigured build does no strip reads, scratch or copies (rule 5).
`Build Succeeded: 354 steps`; `verify_sp3a.py` 35/35 ALL_PASS rc=0;
`verify_review_2026_09_24.py` 12/12.

## 7. Windows (`out\Release`, branch head `fdf56c1`)

### W12 per-file replacement

Every post hash equals the box's sha256 for `camoucrome/main`. Pre hashes are the
PR #27 state; `ABSENT` is a new file. Hashes truncated to 12 hex digits.

| file | pre | post (= box) |
|---|---|---|
| components/camoucfg/BUILD.gn | e141b743dc5d | 85b54c68b660 |
| components/camoucfg/canvas_mask.cc | ABSENT | 47f2819e0d9d |
| components/camoucfg/canvas_mask.h | ABSENT | b8decbd4bbba |
| components/camoucfg/canvas_mask_unittest.cc | ABSENT | cf9f45dce8ef |
| components/camoucfg/canvas_noise.cc | 97c61511305f | b1fd0f9d0483 |
| components/camoucfg/canvas_noise.h | 0e33c24046a1 | eba8b58df32f |
| components/camoucfg/canvas_noise_unittest.cc | 639d2fbf0064 | a9a2438b2fb6 |
| components/camoucfg/canvas_readback.cc | 6bb1c20a0ce7 | b6c18de0a13c |
| components/camoucfg/canvas_readback.h | b0ee14d1fc5a | 0fb5e9d6233e |
| components/camoucfg/canvas_readback_unittest.cc | 1e4b5b45d51c | 93e72828eb1c |
| blink/renderer/DEPS | 0c8cb5db049b | 545f6f65e01a |
| blink/renderer/core/html/canvas/canvas_rendering_context.cc | 38b3f3b32d22 | 15feef8cd3d2 |
| blink/renderer/core/html/canvas/canvas_rendering_context.h | 922ec7c5793f | f8db6e7b3d57 |
| blink/.../canvas2d/base_rendering_context_2d.cc | a7042345f052 | 4c7ee7e2cdf8 |
| blink/.../canvas2d/base_rendering_context_2d.h | cb63d4800cdf | ab3704c81bce |
| blink/.../canvas2d/canvas_2d_recorder_context.cc | f03bf454f7dd | 5cbca18df60f |
| blink/.../canvas2d/canvas_2d_recorder_context.h | 9cc0bc855115 | 2a96f42a1389 |
| blink/.../offscreencanvas2d/offscreen_canvas_rendering_context_2d.cc | fc1037ed3f1e | 81fd661e42cc |
| blink/.../modules/webgl/webgl_rendering_context_base.cc | 25759bebb910 | 72d084be746f |
| blink/.../modules/webgl/webgl_rendering_context_base.h | 4760dde2a955 | 43956d64916b |

### Build

First start died after 88 s: siso `fatal error: out of memory` (`VirtualAlloc ... errno=1455`),
not clang. W9 restart of the same label: `Build Succeeded: 231 steps`, `rc=0 secs=339`.

### Calibration at the default density 0.04 (8 seeds)

No density change; the default stays 0.04.

| mode | S2 text | S2 shape | stock among |
|---|---|---|---|
| headless | 8 of 8 distinct | 8 of 8 | none |
| headed | 8 of 8 distinct | 8 of 8 | none |

The headless calibration run had P3 and S1 UNMEASURED (`no WebGL context in: stock`);
the other 7 rows PASS. Not rerun, since calibration reads only S2.

### Final host runs

| label | attempts | P1 | P2 | P3 | P4 | P5 | S1 | S2 text | S2 shape | rule 5 |
|---|---|---|---|---|---|---|---|---|---|---|
| s2b-final-headless | 1 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| s2b-final-headed | 1 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |

9/9 in both modes on the first attempt. S2 text and shape: 8 distinct of 8, stock among
them False. S1 colours `[(1, 1)]`. Rule 5 differ `[]`.

### `verify_sp3a` on Windows `chrome`

35 rows. PASS: C1, C6-C9, C12-C32 (C24 a-d included). Not passing, all on the
missing stock baseline (`baseline load ... FileNotFoundError`; no stock baseline
on the host): C2, C3, C4, C5, C10, C11. Recorded as UNMEASURED, not as a pass.
C11's own measurable parts read fine: differ from unconfigured `[]`, colours (2D, WebGL) `(1, 1)`;
only `unconfigured clear == stock baseline` is False, from the absent baseline.

### Regression verifies

`verify_windows_client.py`: `11 PASS 0 FAIL`. `verify_sp6b_driver.py`: `ALL_PASS`.

### Step 2 re-measure (scrubbed numbers only)

- `noise.canvas2d` and `noise.webgl`: 1 and 1, in fork and control, headed and headless.
- oracle `canvas.text` and `canvas.shape`: fork differs from control in both modes.
- linkability: control shares `canvas.text` and `canvas.shape` with the host baseline
  (230 of 234 leaves shared); fork shares neither (215 headed, 217 headless of 234).
  No `canvas` leaf in the fork's shared list.
- stability across relaunch: 236 leaves compared, none changed in control (both modes)
  and fork headed. Fork headless: 1 changed leaf, `codecs.video/mp4; codecs="hev1.1.6.L93.B0"`,
  which is a codec-support probe, not a canvas leaf. Canvas leaves unchanged.
- CreepJS: 82 rows per run, no `rgba noise` row in any of the four runs.

## 8. Gaps

### Closed by S2b

| PR #27 gap | Closed by |
|---|---|
| The field was keyed by position | C21 |
| Any edit reseeded the field (narrowed, see Remaining: a draw that touches a region's 3x3 patches without covering its pixels still re-rolls that region's noise) | C22 |
| The WebGL sub-rect read differed from a full read | C28 |
| `toDataURL` disagreed with `readPixels` | C29 |
| The imported flag was sticky for the whole canvas | C23, C25 |
| `createPattern` flipped eligibility without a draw | C26 |
| The anti-aliasing list had holes (diagonal polygons, curved clips, round caps, shadow blur) | C24a-d |
| A pattern created on one context and filled on another | The imported mark is made at fill time on the filling context's mask; no verify row |

Also closed in the Task 4 fix round: pattern-styled text marks imported (code review
only, no verify row); the layer and allocation-failure fallbacks mark imported;
`destination-out` and `copy` clear marks (C30, C32); `transferToImageBitmap` resets the
mask (C31). C27 was redrawn as random 1px colours. `readPixels` margin strips run only
with `canvas:seed` (rule 5). `verify_sp3a` has 40 rows (35 here, plus C33a-e).

### Remaining

- Canvases above 4096 x 4096 are over-marked.
- Layers mark their whole area, as imported (no noise). Narrowed by S2c: layer and looper areas are now tight (C44, C44b); see measurements/2026-10-canvas-noise-s2c.md §7.
- Neighbour re-roll (narrowed C22): noise is keyed by each pixel's 3x3 patch, so a
  draw that touches a region's patches without covering its pixels re-rolls that
  region's noise. Stock pixels depend only on draws that cover them. This is inherent
  to patch keying and is documented, not fixed.
- `drawMesh` (experimental Canvas2dMesh): an image texture cannot be replayed, so it
  under-marks.
- No row covers GPU-accelerated 2D raster: every S2b 2D row uses a canvas of 128 px or
  less.
- A `readPixels` strip-read binder failure returns the stock render.
- A composited draw (a filter, a full-canvas composite mode, or a composited shadow)
  marks its whole clip imported. Noise then stays off for that clip until an opaque
  solid draw covers it fully. A page can switch noise off for a region that way. That
  costs linkability, not detectability.
- A translucent shape with a shadow keeps aa on its own pixels where its shadow reaches them
  (the shadow pass marks aa; the translucent shape's pass is kSolid and does not clear).
- The shadow pass keeps a pattern's shader. A texture-backed pattern played onto a CPU
  canvas is expected to draw nothing; that is unverified.
- A draw that changes no pixel can still switch noise off: `drawImage` of an empty or
  transparent source marks its whole dirty rect imported, and so does a composited draw
  of a transparent shape (its whole clip). Closed by S2c for the transparent `drawImage` (C43; measurements/2026-10-canvas-noise-s2c.md §7); the composited-shape case stays. This is linkability, not detectability, and
  it is narrower than PR #27, where any `drawImage` disabled the whole canvas.
- Replay cost on huge canvases: every non-text draw rasterises a full-resolution A8
  bitmap of its dirty rect, also on coarse masks. A failed allocation marks the area
  imported. This is part of the 4.35x draw cost (S2c). Closed by S2c (measurements/2026-10-canvas-noise-s2c.md §10, §12): the draw-time cost is gone (`per_draw_us` 0.93x in the S2c final run, §12.6); the replay moved to flush time (`draw_read` 2.64x, a remaining MISS).
- `scripts/measure_canvas_cost.py` drives the page with Playwright `evaluate`, which sends
  `Runtime.enable`, in both arms: absolute times include that overhead, and the ratio
  compares like with like.
- Image draws mark `imported` over their whole dirty rect, with no replay. This errs
  toward no noise.
- The captureStream one-copy path and the `transferControlToOffscreen` placeholder are
  not covered. `transferToImageBitmap` only resets the mask.
- WebGL is eligible everywhere.
- `DrawFocusRing` paints outside `Draw`, so the focus ring is unmarked and gets no noise.
- The shadow extent of the dirty rect was not verified; unmarked shadow pixels get no
  noise.
- No verify row covers a transformed (rotated or scaled) replay.
- The scratch copy in `readPixels` doubles memory on huge seeded reads.
- The Windows `verify_sp3a` baseline clauses are UNMEASURED: the host has no stock
  baseline (C2-C5, C10, C11).
- Cost, WSL `content_shell` (CPU raster, SwiftShader GL), so GPU raster is not
  represented. Draw ratio 1.43 before, 4.35 after; above the spec's 2x line, so a known
  gap for S2c. `readPixels` 64x64 1.33x to ~3.3x; 1024x1024 15.89x to ~21.5x (seeded
  40.9 ms vs unconfigured 1.9 ms). This is a regression against PR #27, and an S2c gap next
  to the draw cost (the earlier 1.11x and 7.06x are invalid, see section 6 and section 12). Closed by S2c (measurements/2026-10-canvas-noise-s2c.md §10, §12.6): default-framebuffer `readPixels` large reads 1.37x and 1.44x in the final run; the small reads, `draw_read` and the page-framebuffer large read (4.16x, accepted) remain MISSes there.

### Step 2

The fork's headless relaunch changed one HEVC codec leaf. That is S4 instability, not
canvas; canvas leaves were unchanged.

## 9. Final-review fix wave

Branch head `e867573`. Fixes: F1a (no-op draws), F1a' (gradient alpha), F1b (shadow
two-pass), F1c (composited draws mark imported), F3 (clearRect area), F4 (mask is
top-down only), F5 (comments), plus rows C33a-d.

### RED (WSL, additions-only build, before the Blink edit)

- Build: 356 steps; `components_unittests` canvas filters PASS, including the new
  `PerturbRgbaEdgesTest.MaskWithBottomUpIsNoOp`.
- A first RED run measured nothing: the C33 page script reused the name `exact`, a
  `SyntaxError` failed every row from C21 on (18 FAIL). The helper was renamed
  (`6026393`) and the RED run repeated.
- Repeated RED: `verify_sp3a` 35 PASS, 4 FAIL. The four are exactly C33a, C33b, C33c and
  C33d, so each new row fails on the build without the fix.

### Build and GREEN (WSL)

- Edits: `final_fix_edits.py` (7 entries, sha256 `204a9e83`) applied with no anchor
  correction and no API-shape correction (`nothingToDraw`, `setLooper`,
  `ComputeDirtyRect` all compiled as written).
- Build: `content_shell` + `components_unittests`, 201 steps, rc 0. `gn check` (core,
  canvas, webgl): Header dependency check OK. `checkdeps` on both canvas dirs: SUCCESS.
- `verify_sp3a`: 39 of 39, `ALL_PASS`, rc 0. `verify_review_2026_09_24`: 12/12
  `ALL_PASS`. C24d, C27, C11-C13 and C16 did not regress.
- Export: 38 commits, 0 fixup. Only `patches/sp3a-canvas-noise.patch` changed
  (sha256 `8da4db67`, 41009 bytes); the additions are identical to the pushed tree.

### Windows (W12, base `55d16f07`)

| file | Windows pre (8) | post = box sha256 (8) |
|---|---|---|
| `components/camoucfg/BUILD.gn` | same as post | 85b54c68 |
| `components/camoucfg/canvas_mask.cc` | same as post | 47f2819e |
| `components/camoucfg/canvas_mask.h` | same as post | b8decbd4 |
| `components/camoucfg/canvas_mask_unittest.cc` | same as post | cf9f45dc |
| `components/camoucfg/canvas_noise.cc` | B1FD0F9D | 0943682e |
| `components/camoucfg/canvas_noise.h` | EBA8B58D | 09df99ee |
| `components/camoucfg/canvas_noise_unittest.cc` | A9A2438B | d9ad2483 |
| `components/camoucfg/canvas_readback.cc` | same as post | b6c18de0 |
| `components/camoucfg/canvas_readback.h` | same as post | 0fb5e9d6 |
| `components/camoucfg/canvas_readback_unittest.cc` | same as post | 93e72828 |
| `third_party/blink/renderer/DEPS` | same as post | 545f6f65 |
| `third_party/blink/renderer/core/html/canvas/canvas_rendering_context.cc` | same as post | 15feef8c |
| `third_party/blink/renderer/core/html/canvas/canvas_rendering_context.h` | F8DB6E7B | c19792f7 |
| `third_party/blink/renderer/modules/canvas/canvas2d/base_rendering_context_2d.cc` | same as post | 4c7ee7e2 |
| `third_party/blink/renderer/modules/canvas/canvas2d/base_rendering_context_2d.h` | same as post | ab3704c8 |
| `third_party/blink/renderer/modules/canvas/canvas2d/canvas_2d_recorder_context.cc` | 5CBCA18D | 3145696d |
| `third_party/blink/renderer/modules/canvas/canvas2d/canvas_2d_recorder_context.h` | 2A96F42A | 9052864b |
| `third_party/blink/renderer/modules/canvas/offscreencanvas2d/offscreen_canvas_rendering_context_2d.cc` | same as post | 81fd661e |
| `third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc` | same as post | 72d084be |
| `third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.h` | same as post | 43956d64 |

All 20 post hashes equal the box's sha256. The other 14 files were already identical.

Windows build (`out\Release`, label `s2b-2`): two attempts stopped on clang out of memory
(one with 42 steps done, one with 16; the second also hit the paging-file limit). The
third attempt, resumed from the cache, ended `Build Succeeded: 201 steps`, rc 0.

### Final host runs

| label | attempts | result |
|---|---|---|
| s2b-final2-headless | 2 | attempt 1: P3 and S1 UNMEASURED (no WebGL context in stock) and rule 5 FAIL on `glClear`, `shape`, `text`, `textBig`; attempt 2: 9/9 PASS |
| s2b-final2-headed | 2 | attempt 1: P3 and S1 UNMEASURED (no WebGL context in seed 1), others PASS; attempt 2: 9/9 PASS |

The rule 5 FAIL in headless attempt 1 came with a host WebGL failure on the stock side
and did not reproduce in the next attempt or in either headed attempt; it is recorded as
a host flake, not as a pass.

### `verify_sp3a` on Windows `chrome`

39 rows: 33 PASS (C1, C6-C9, C12-C33a-d), 6 fail on the missing stock baseline as before
(C2-C5, C10, C11), recorded as UNMEASURED. Log `D:\camou-win\s2b\sp3a-win2.log`.

## 10. Residual fix (WSL)

Branch head after the code fix: see `git log`. A transparent fill, or `globalAlpha` 0,
with a visible shadow took CamouMark's looper branch, because `nothingToDraw()` is false
while a looper is set. The branch now builds the no-looper shape flags first and returns
if the shape draws nothing. Row C33e covers it; the CamouReplay declaration comment was
corrected.

- RED (current build, no rebuild): `verify_sp3a` 39 PASS, 1 FAIL, the FAIL being C33e
  (seeded hash differs; unconfigured hash equals its own pre-draw hash, so stock draws
  nothing).
- Build: `content_shell` + `components_unittests`, 354 steps, rc 0.
- GREEN: `verify_sp3a` 40/40 `ALL_PASS`, rc 0; `verify_review` 12/12 `ALL_PASS`;
  canvas unit tests pass; the 6 and 10 test groups all PASSED.
- `gn check` core, canvas, webgl: Header dependency check OK. `checkdeps` on
  `modules/canvas` and `core/html/canvas`: SUCCESS.
- Export: 38 commits, 0 fixup; only `patches/sp3a-canvas-noise.patch` changed (sha256
  `64be287c`).

Windows re-run pending: another session's Windows build occupies D:\camou-win; the S2b
Windows re-run follows it.

## 11. Windows at head

Branch head `f0e4879` (code fix `de92306`). Tree refreshed from the pushed branch; the
file set is the same 20 files as before, none of the other session's files.

### W12 (base `55d16f07`)

| file | Windows pre (8) | post = box sha256 (8) |
|---|---|---|
| `components/camoucfg/BUILD.gn` | 85b54c68 | 85b54c68 |
| `components/camoucfg/canvas_mask.cc` | 47f2819e | 47f2819e |
| `components/camoucfg/canvas_mask.h` | b8decbd4 | b8decbd4 |
| `components/camoucfg/canvas_mask_unittest.cc` | cf9f45dc | cf9f45dc |
| `components/camoucfg/canvas_noise.cc` | 0943682e | 0943682e |
| `components/camoucfg/canvas_noise.h` | 09df99ee | 09df99ee |
| `components/camoucfg/canvas_noise_unittest.cc` | d9ad2483 | d9ad2483 |
| `components/camoucfg/canvas_readback.cc` | b6c18de0 | b6c18de0 |
| `components/camoucfg/canvas_readback.h` | 0fb5e9d6 | 0fb5e9d6 |
| `components/camoucfg/canvas_readback_unittest.cc` | 93e72828 | 93e72828 |
| `third_party/blink/renderer/DEPS` | 545f6f65 | 545f6f65 |
| `third_party/blink/renderer/core/html/canvas/canvas_rendering_context.cc` | 15feef8c | 15feef8c |
| `third_party/blink/renderer/core/html/canvas/canvas_rendering_context.h` | c19792f7 | c19792f7 |
| `third_party/blink/renderer/modules/canvas/canvas2d/base_rendering_context_2d.cc` | 4c7ee7e2 | 4c7ee7e2 |
| `third_party/blink/renderer/modules/canvas/canvas2d/base_rendering_context_2d.h` | ab3704c8 | ab3704c8 |
| `third_party/blink/renderer/modules/canvas/canvas2d/canvas_2d_recorder_context.cc` | 3145696d | 3145696d |
| `third_party/blink/renderer/modules/canvas/canvas2d/canvas_2d_recorder_context.h` | 9052864b | 72235f65 |
| `third_party/blink/renderer/modules/canvas/offscreencanvas2d/offscreen_canvas_rendering_context_2d.cc` | 81fd661e | 81fd661e |
| `third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc` | 72d084be | 72d084be |
| `third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.h` | 43956d64 | 43956d64 |

All 20 post hashes equal the box's sha256. Only `canvas_2d_recorder_context.h` differed
(the residual fix); the other 19 were already identical.

### Build

`out\Release`, label `s2b-3`: `Build Succeeded: 257 steps`, rc 0, first attempt (369 s).

### Host runs

| label | attempts | result |
|---|---|---|
| s2b-final3-headless | 1 | 9/9 PASS |
| s2b-final3-headed | 1 | 9/9 PASS |

### `verify_sp3a` on Windows `chrome`

40 rows: 34 PASS (C1, C6-C9, C12-C33e), 6 fail on the missing stock baseline as before
(C2-C5, C10, C11), recorded as UNMEASURED. Log `D:\camou-win\s2b\sp3a-win3.log`.

## 12. Code-review round

Branch head `73ae177`. Findings fixed: F1 (a `copy` clear with a stroke now clears the whole
clip, row C34), F2 (eligibility counts aa-only cells, `CanvasNoiseMask::has_aa()`), F3
(fallible `readPixels` scratch and fallible source copies), F4 (no replay for a context
with no canvas host), F5 (one `CamouEnsureMask` helper, comments, spec), F6 (the cost
script uses `lib_shell.session`).

### Checks on the box

- `base::UncheckedMalloc`, `UncheckedFree` and `CheckedNumeric` exist at the pin
  (`base/process/memory.h`).
- F4 host question: `Canvas2DRecorderContext::GetCanvasRenderingContextHost()` defaults to
  nullptr and only the canvas and offscreen 2D contexts override it. The paint worklet's
  `PaintRenderingContext2D` does not, so the nullptr gate used, with no virtual override.
- The `readPixels` noise block is the tail of `ReadPixelsHelper` (only closing braces
  follow), so the failure path may `return`.

### RED and GREEN (WSL)

- Additions-only build: 363 steps; `HasAaCountsAaOnlyCells` and `HasAaOnCoarseCells` pass,
  as do all other canvas noise tests.
- RED (before the Blink edit): `verify_sp3a` 40 PASS, 1 FAIL = C34 (seeded hash differs;
  unconfigured equals the fresh canvas, so the guard holds).
- Blink edits: `cr_edits.py` (11 entries, sha256 `32de890c`) applied with no anchor or API
  correction. Build: 29 steps, rc 0.
- GREEN: `verify_sp3a` 41/41 `ALL_PASS`, rc 0; `verify_review` 12/12; `gn check` (core,
  canvas, webgl) OK; `checkdeps` on both canvas dirs SUCCESS.
- Export: 38 commits, 0 fixup. Changed: `sp3a-canvas-noise.patch` (sha256 `fe0162ae`) and
  `sp3b-webgl-profile.patch` (sha256 `d8cbe13e`; context lines and offsets only, since it
  shares `webgl_rendering_context_base.cc` with the new includes).

### Cost (WSL `content_shell`, seeded / unconfigured)

| arm | seeded median | unconfigured median | ratio |
|---|---|---|---|
| draw | 118.00 ms | 26.35 ms | 4.48 |
| readPixels 64x64 | 1.05 ms | 0.30 ms | 3.50 |
| readPixels 1024x1024 | 40.00 ms | 1.90 ms | 21.05 |

The section 6 `readPixels` values (1.11x and 7.06x) were measured before the Task 5 seed
gate, so the unconfigured arm also did the strips and scratch: 0.90 / 4.20 ms, against
0.30 / 1.80 ms for PR #27 and 0.30 / 1.90 ms now. That inflated denominator, not the script
flags, is the cause of the apparent improvement; the true `readPixels` cost is a regression
against PR #27 (1.33x and 15.89x). The controller re-measured on WSL with the new script:
4.68 / 3.33 / 21.53 (draw / 64x64 / 1024x1024), and 4.47 / 3.67 / 22.05 from a copy whose
A/B `sed` did not match, so that run is not a flags test. The flags' own effect was not
isolated. The seeded 1024x1024 arm also rose from 29.65 ms (section 6) to about 40-41 ms,
which is unexplained. The draw ratio is close to the earlier 4.35.

### Windows (W12, base `55d16f07`)

| file | Windows pre (8) | post = box sha256 (8) |
|---|---|---|
| `components/camoucfg/BUILD.gn` | same as post | 85b54c68 |
| `components/camoucfg/canvas_mask.cc` | 47f2819e | 960bb10c |
| `components/camoucfg/canvas_mask.h` | b8decbd4 | d35a897a |
| `components/camoucfg/canvas_mask_unittest.cc` | cf9f45dc | 76e0df18 |
| `components/camoucfg/canvas_noise.cc` | 0943682e | 3fde6623 |
| `components/camoucfg/canvas_noise.h` | same as post | 09df99ee |
| `components/camoucfg/canvas_noise_unittest.cc` | same as post | d9ad2483 |
| `components/camoucfg/canvas_readback.cc` | b6c18de0 | dcd7e0be |
| `components/camoucfg/canvas_readback.h` | same as post | 0fb5e9d6 |
| `components/camoucfg/canvas_readback_unittest.cc` | same as post | 93e72828 |
| `third_party/blink/renderer/DEPS` | same as post | 545f6f65 |
| `third_party/blink/renderer/core/html/canvas/canvas_rendering_context.cc` | same as post | 15feef8c |
| `third_party/blink/renderer/core/html/canvas/canvas_rendering_context.h` | same as post | c19792f7 |
| `third_party/blink/renderer/modules/canvas/canvas2d/base_rendering_context_2d.cc` | same as post | 4c7ee7e2 |
| `third_party/blink/renderer/modules/canvas/canvas2d/base_rendering_context_2d.h` | ab3704c8 | 78aeadeb |
| `third_party/blink/renderer/modules/canvas/canvas2d/canvas_2d_recorder_context.cc` | 3145696d | 9dd8c718 |
| `third_party/blink/renderer/modules/canvas/canvas2d/canvas_2d_recorder_context.h` | 72235f65 | 222b6950 |
| `third_party/blink/renderer/modules/canvas/offscreencanvas2d/offscreen_canvas_rendering_context_2d.cc` | same as post | 81fd661e |
| `third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc` | 72d084be | 413d51d2 |
| `third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.h` | same as post | 43956d64 |

All 20 post hashes equal the box's sha256. The build (`out\Release`, label `s2b-4`) hit
clang out of memory twice (30 and 32 steps done); the third attempt ended `Build Succeeded:
197 steps`, rc 0.

| label | attempts | result |
|---|---|---|
| s2b-final4-headless | 2 | attempt 1: rule 5 FAIL (differ: `glClear`, `glClearColours`, `shape`, `text`, `textBig`), the host flake seen before; attempt 2: 9/9 PASS |
| s2b-final4-headed | 2 | attempt 1: P3 and S1 UNMEASURED (no WebGL context); attempt 2: 9/9 PASS |

`verify_sp3a` on Windows `chrome`: 41 rows, 35 PASS (C1, C6-C9, C12-C34), 6 fail on the
missing stock baseline as before (C2-C5, C10, C11), recorded as UNMEASURED. Log
`D:\camou-win\s2b\sp3a-win4.log`.

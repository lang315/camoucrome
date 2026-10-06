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
| readPixels 64x64 | 1.33 | 1.11 (1.00 / 0.90 ms) |
| readPixels 1024x1024 | 15.89 | 7.06 (29.65 / 4.20 ms) |

The draw ratio is above 2.0. It is attributed to the 2D mask replay (Tasks 3-4);
no draw ratio was measured between Task 1 and Task 5. This task touches
`readPixels` only. Recorded as a known gap for S2c. It does not block.

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
| components/camoucfg/canvas_noise_unittest.cc | 639d2fbf00645 | a9a2438b2fb6 |
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

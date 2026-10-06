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

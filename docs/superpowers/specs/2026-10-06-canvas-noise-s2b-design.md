# Canvas noise S2b: patch-keyed field and per-region eligibility — design

Backlog item S2b from the roadmap. It is the follow-up to S1 and S2 (PR #27,
`specs/2026-10-05-canvas-noise-redesign-design.md`,
`measurements/2026-10-canvas-noise.md`). Approved in brainstorming on
2026-10-06. The WebGL-to-WebGL `texImage2D` GPU path and the copy-path cost
are split off to S2c and are not part of this design.

## The problem, measured

PR #27 shipped two mechanisms for 2D canvases. Text is drawn at a per-seed
sub-pixel origin. Readback noise goes on pixels that differ from all four of
their neighbours, and only on a canvas that drew anti-aliased geometry and
imported no pixels. The review and §8 of the measurements left these tells:

- **The field is keyed by position and by the whole canvas state.**
  - The seed folds in `CanvasStateHash`, so any edit reseeds the field.
    Reading one region before and after an unrelated draw elsewhere gives two
    different results, where stock gives one.
  - The same shape drawn twice at whole-pixel offsets gets two different
    fields.
  - WebGL `readPixels` of a sub-rect gets a different field from a full read,
    because the content hash and the positions are relative to the rect.
- **Eligibility is one sticky boolean per canvas.**
  - A canvas that once received `putImageData`, or drew any image, carries no
    readback noise for the rest of its life. The same arc then reads noised
    on a fresh canvas and clean on a reused one.
  - `createPattern` flips eligibility off without any draw.
- **The anti-aliasing flag is a list of operations, and the list has holes.**
  Diagonal `lineTo` polygons, round caps, a curved `clip()` with `fillRect`,
  `shadowBlur`, and rotated `drawImage` leave the flag unset. A canvas drawn
  only with them carries no noise.
- **WebGL `readPixels` and the WebGL snapshot (`toDataURL`) use different
  fields** (different seeds; `readPixels` is bottom-up).

## Principle

Unchanged from the S1/S2 design: linkable rather than detectable. Where the
design cannot tell whether a pixel's exact value is known to the page, that
pixel carries no noise. This design narrows the "cannot tell" from the whole
canvas to the pixel.

## 1. The noise field is keyed by the 3×3 source patch

For each pixel the noise decision and its value are a function of:

- `canvas:seed`;
- the pixel's 3×3 neighbourhood in the **unperturbed source**: 9 RGBA
  values, premultiplied for a 2D snapshot, hashed in **top-down row order**;
- the channel index.

The key contains nothing else. Specifically, it does **not** contain the
position, the canvas size, `CanvasStateHash`, or any whole-buffer
`ContentHash`, including the tight-copy hash `PerturbRgba` gained in PR #27
round 2. The existing domain string stays the seed's only salt, so one
profile has one field.

Consequences, each one a verify row below:

- one shape drawn at two whole-pixel offsets gets the same noise;
- drawing elsewhere does not change a region's noise, unless the new draw
  touches that region's 3×3 patches;
- a sub-rect read equals the matching part of a full read.

The eligibility rule for a pixel stays as shipped:
- it is interior;
- its alpha is at least `max(min_alpha, 1)`;
- it differs from all four neighbours in the source;
- the noise is clamped to `[0, alpha]` on premultiplied values.

`canvas:noiseDensity` keeps its meaning and its default of 0.04 as the
starting point. Content keying changes how the field is distributed over the
oracle's drawings, so calibration is a **required step**, not an assumption.
It reruns the procedure of measurements §5 and must reach S2 text ≥ 6/8
distinct and S2 shape 8/8 distinct, with stock among none. If 0.04 misses,
the smallest passing density is doubled, as before.

## 2. Per-region eligibility for 2D (coverage masks)

**State.** Each 2D context (`Canvas2DRecorderContext`, which covers
`CanvasRenderingContext2D` and `OffscreenCanvasRenderingContext2D`) owns two
A8 masks the size of the canvas:
- `aa`: the pixel's value depends on the rasteriser;
- `imported`: the pixel holds data the page supplied, or data that may
  already carry noise.

The masks are allocated lazily: only when `canvas:seed` is set, and only at
the first draw that marks a pixel. `ResetInternal()` frees them, which covers
`reset()` and a width or height change. Without a seed nothing is allocated
and nothing is replayed (rule 5).

**Where marks happen: one choke point.** Every 2D draw passes through
`Canvas2DRecorderContext::Draw` / `DrawInternal`, which hold the `draw_func`
that paints onto a `cc::PaintCanvas`. The hook lives there and not in the
public APIs. A draw through an API this spec never names must still mark.
The hook names none of C24's operations, so C24 makes that bite.

At that point the hook replays the same `draw_func` on a scratch A8 surface
covering the draw's device bounds. The replay uses:
- the same transform and clip;
- the same anti-aliasing;
- the same stroke parameters (width, caps, joins, dash);
- the same shadow pass and filter;
- with paint colour forced to opaque white, shader removed, and blend mode
  source-over.

The scratch coverage `c` of each pixel is then merged into the masks:

| draw | `c` = 255 (full coverage) | 0 < `c` < 255 (partial) |
|---|---|---|
| solid opaque colour, source-over, global alpha 1, no shadow, no filter | **clear** `aa` and `imported` (the value is now known exactly) | set `aa` |
| solid colour, otherwise (alpha below 1, other blend modes covered below) | leave both | set `aa` |
| gradient paint, or any draw with a shadow or a filter | set `aa` | set `aa` |
| pattern paint | set `imported` | set `imported` |
| `drawImage` (any source) | set `imported` | set `imported` |
| `clearRect` | **clear** both | set `aa` |

Further rules:

- **Composite ops that touch pixels outside the shape** (the ones
  `DrawInternal` already composites over the clip bounds, as Blink's
  full-canvas composite check decides, plus `copy`) mark the clip's coverage
  `imported` (no noise) instead of the shape's (amended: see F1c). They never
  clear a mark.
- **`putImageData`** (`PutByteArray`) does not pass through `Draw`. It sets
  `imported` over its dirty rect directly.
- **Text marks nothing.** `fillText` and `strokeText` are skipped by the
  replay. Text keeps its draw-time offset. Text drawn over pixels that are
  already marked gets their noise. This keeps the S1/S2 rule that a canvas
  with only text, fills, images and `putImageData` carries no readback noise.
- **`createPattern` marks nothing.** Only a fill or stroke with the pattern
  paint marks, and only over its coverage.
- **Layers** (`beginLayer` / `endLayer`): a draw inside a layer marks its
  dirty area `imported` (amended) and never clears, because the layer's alpha and filter are
  only applied at `endLayer`.
- **Precedence.** A pixel is eligible for readback noise iff `aa` is set and
  `imported` is not. `imported` wins.

**Size cap.** At most 4096 × 4096 px (two masks, 32 MB) are kept at full
resolution. A larger canvas keeps masks of 4 × 4 px cells:
- a cell is marked if any pixel in it would be;
- a cell is cleared only if all of its pixels are fully covered.

This over-marks near AA content on very large canvases and is recorded as a
known gap. A canvas above the cap does not fall back to "no noise", because
that would bring back a per-canvas tell.

**Readback.** `CamouNoised()` keeps its role as the single snapshot hook. It
now passes the `aa`-and-not-`imported` mask to the noise pass: a pixel
outside the mask is left alone, even if the rule in section 1 would perturb
it. `CamouNoiseEligible()` becomes "the masks exist and some pixel is
eligible". Without masks the snapshot is returned as is, as today. The
one-entry cache folds a mask generation counter into its key. The counter
bumps on every mark or clear, so a mask change without a raster change still
misses the cache (a transparent arc, or `clearRect` over already clear
pixels).

## 3. WebGL

**`readPixels`.**
- The noise stays on the in-buffer part of the rect, at the real pack layout,
  opaque pixels only (min_alpha 255).
- **Edge neighbours come from the buffer, not from the rect.** For a pixel
  on the edge of the in-buffer part, its neighbours outside the rect are read
  through up to four extra 1px strips: above, below, left, right, each
  clipped to the drawing buffer.
- The strips are read with a tight pack state:
  - alignment 1;
  - WebGL2 row length 0 and skips 0;
  - no `PIXEL_PACK_BUFFER` bound.

  The user's state is restored afterwards through the existing
  `DrawingBufferClientRestorePixelPackParameters` pattern (and its WebGL2
  counterpart for row length, skips and the pack buffer binding).
- A pixel on the edge of the drawing buffer itself has no neighbour there and
  is never eligible, in a sub-rect read and in a full read alike. A sub-rect
  read therefore equals the matching part of a full read, byte for byte.
- `readPixels` rows are bottom-up. The patch is hashed in top-down order,
  with "up" meaning GL's y + 1, so the same pixels hash the same way as in the
  snapshot.
- Cost: up to four extra synchronous reads, of at most 2 × (w + h) + 4 pixels,
  per `readPixels` call while a seed is set. Measured in the plan.

**Snapshot (`toDataURL`, `toBlob`, `GetSourceImageForCanvas` of a WebGL
canvas).**
- The noise is restricted to opaque pixels (min_alpha 255), as `readPixels`
  already is.
- It uses the same seed domain as `readPixels`.

With section 1 this makes `toDataURL` and `readPixels` of one WebGL canvas
agree on every pixel. The recorded gap "WebGL `readPixels` and a WebGL
canvas's `toDataURL` use different fields" is closed.

## Amended during implementation (2026-10-06)

- **Pattern-styled text marks imported.** Text still marks nothing (its
  per-seed draw offset varies it), except text whose fill or stroke style is a
  pattern: its pixels are page-supplied, so it marks `imported` over its dirty
  rect. Otherwise the gradient's `aa` under it would noise pixels that must read
  as stock. There is no verify row (the text offset makes a byte comparison with
  unconfigured impossible); it is covered by code review only.
- **The fallbacks mark `imported`, not `aa`.** A draw inside a layer, and a draw
  whose A8 coverage bitmap cannot be allocated, mark the whole box `imported`
  (no noise) instead of `aa`, so exact pixels never gain noise. Canvas2dLayers
  has no `status` in runtime_enabled_features.json5 on 154, so the layer path is
  off by default.
- **`destination-out` and `copy` clear.** `destination-out` with an opaque solid
  source leaves every fully covered pixel transparent whatever it held, so it is
  `Kind::kClear`, like `clearRect`. `copy` replaces every pixel of the clip: it
  replays a full-clip clear, then marks the shape normally (a colour falls to
  `kSolid`, since the blend is not src-over, which is right after the clear).
  Otherwise stale `aa` marks survived draws that made pixels exact.
- **`transferToImageBitmap` resets the mask.** The offscreen context discards the
  bitmap and restarts clear, so it also drops `camou_mask_`; otherwise the new
  clear canvas kept stale `aa` marks.
- **C27 redrawn.** It draws 1px pseudo-random opaque colours under a diagonal
  line, not a 2-colour checkerboard: under patch keying a checkerboard has only
  2 patch types, so the row passed vacuously on a build with the whole canvas
  eligible.
- **New rows C30-C32** (canvas wiped exact by `destination-out`,
  `transferToImageBitmap` or a `copy` fill, then drawn with translucent 1px
  random colours, reads like a fresh canvas). `EXPECTED` is 35.

Final-review fix wave (2026-10-06), rows C33a-d, `EXPECTED` 39:

- **F1a, no-op draws.** `CamouMark` returns when `flags->nothingToDraw()`: a
  fully transparent fill or `globalAlpha = 0` changes no pixel in stock.
- **F1a', transparent gradients.** `CamouReplay` keeps the paint's shader for
  kind `aa`, so a gradient's alpha is part of its coverage (all-transparent
  stops give none). Every other kind drops the shader as before, because a
  GPU-backed pattern could raster to nothing.
- **F1b, shadows.** A draw with a looper is replayed twice: with the looper as
  `aa` (the shadow is rasteriser-dependent), then without it as the shape's own
  kind, so an opaque shape's fully covered pixels are cleared again.
- **F1c, composited draws.** Filters, full-canvas composite modes and
  composited shadows may set any clip pixel unpredictably and may leave exact
  pixels as they were, so `CamouMarkClip` marks the clip `imported` for
  everything. Text still marks nothing unless its style is a pattern.
- **F3, clearRect.** The replay area is `ComputeDirtyRect(rect, clip_bounds)`
  rather than the whole clip; if that returns false nothing is marked.
- **F4, bottom-up masks.** `PerturbRgbaEdges` is a no-op when a mask is passed
  with `bottom_up` true. A mask is for top-down 2D snapshots only; no 2D
  snapshot is bottom-left on 154, so this is defensive.

## Configuration

No new keys. `canvas:seed`, `canvas:noiseDensity` and `canvas:noiseStrength`
keep their meaning. An absent seed means no masks, no replay and no change at
all (rule 5).

## Verification (RED first)

**Unit** (`components/camoucfg`, written first and seen failing):
- one 3×3 patch at two positions in one buffer gets the same output;
- changing a pixel two or more pixels away from a patch does not change that
  patch's output;
- a pixel outside the eligibility mask is unchanged at density 1;
- a bottom-up buffer, flipped, gives the same field as the top-down one;
- the existing edge, alpha and clamp tests still pass.

**Browser, new `verify_sp3a.py` rows.** Each row is run first on the current
build (PR #27, `fe1dd5c`) and must fail there. Each row guards against
vacuity: the unconfigured run of its drawing must have at least one pixel
that is interior, non-transparent and unlike all four neighbours.

| row | drawing | pass | RED today because |
|---|---|---|---|
| C21 position | one arc at (10,10) and the same arc at (40,25) | the two crops are equal byte for byte, and differ from unconfigured | field keyed by position |
| C22 edit elsewhere | read region A, draw an arc far from A, read A again | the two reads of A are equal | `CanvasStateHash` reseeds |
| C23 mixed canvas | an arc, plus a `putImageData` random pattern elsewhere | the arc differs from unconfigured, and the pattern reads back exactly | one sticky imported flag |
| C24a–d AA holes | (a) diagonal `lineTo` triangle, (b) a line stroked with round caps, (c) curved `clip()` then `fillRect`, (d) `fillRect` with `shadowBlur` 4 | each differs from unconfigured | the operation list misses them |
| C25 reuse | `putImageData` over the whole canvas, `clearRect` over the whole canvas, then an arc | equal to a fresh canvas with the same arc | sticky flag |
| C26 pattern | `createPattern` never used, plus an arc; on a second canvas, an arc plus a pattern fill in region B | the first arc differs from unconfigured; region B equals unconfigured | `createPattern` sets the flag |
| C27 coverage | a 1px `fillRect` checkerboard, then a diagonal line across it, plus an arc in a corner | checkerboard pixels 4 or more px from the line equal unconfigured | the arc makes the whole canvas eligible |
| C28 WebGL sub-rect | `readPixels(16,16,32,32)` and `readPixels(0,0,64,64)` of the C6 triangle | the sub-rect equals the crop of the full read | rect-relative field |
| C29 WebGL agreement | `toDataURL` of the C6 triangle, decoded, against `readPixels` flipped | equal on every opaque pixel | different seeds |

- **Mutation proof.** With the coverage replay replaced by "mark the draw's
  bounding box", C27 fails. Restoring it brings back all-pass.
- C17–C20 keep passing. C17 and C18 compare pack layouts, which content
  keying keeps equal. C19 asserts that the in-buffer part equals the default
  read, which now holds byte for byte.
- `EXPECTED` becomes 32: 20 rows today, plus C21, C22, C23, C24a–d, C25, C26,
  C27, C28 and C29.

**Existing evidence stays green.**
- `verify_sp3a.py` C1–C20.
- `verify_review_2026_09_24.py` 12/12.
- Host runner `scripts/measure_canvas_noise.py` 9/9 PASS headless; headed
  rows each pass in at least one attempt (host WebGL flake).
- Unit suites, `gn check`, checkdeps.

**Cost, measured** (UNMEASURED today):
- A draw-heavy page, 10 000 arcs per frame on a 1024 × 1024 canvas, timed
  under the fork with a seed against the fork without one. The ratio is
  recorded. Above 2×, it is recorded as a known gap and goes to S2c.
- `readPixels` time with the margin strips, on a 64 × 64 and a
  1024 × 1024 read.

**Step 2 re-measure after the Windows build.** Same pass criteria as PR #27
§7:
- noise reads 1 and 1;
- `canvas.text` and `canvas.shape` differ from control and are not shared
  between profiles;
- both are stable across relaunch;
- no CreepJS "rgba noise".

## Gaps this design closes

From measurements §8 and the S1/S2 spec:
- the field keyed by position;
- any edit reseeding the field;
- WebGL `readPixels` sub-rect against full read;
- WebGL `readPixels` against `toDataURL`;
- the sticky per-canvas imported flag;
- `createPattern` flipping eligibility without a draw;
- the AA operation list's holes (diagonal `lineTo`, round caps, curved clip,
  `shadowBlur`);
- a pattern created on one context and filled on another: the fill marks
  `imported` on the context that draws.

## Known gaps that remain

- **Canvases above 4096 × 4096 px** use coarse 4 × 4 cell masks, which
  over-mark near AA content.
- **Layers** mark `imported` (no noise) and never clear inside a layer.
- **Neighbour re-roll (C22 narrowed).** Noise is keyed by each pixel's 3x3 patch,
  so a draw that touches a region's 3x3 patches without covering its pixels
  re-rolls that region's noise. Stock pixels depend only on draws that cover
  them. Inherent to patch keying; documented only.
- **`drawMesh`** (experimental Canvas2dMesh): an image texture cannot be
  replayed, so it under-marks.
- **No row covers GPU-accelerated 2D raster**: every S2b 2D row uses a canvas
  of 128 px or less.
- **A `readPixels` strip-read binder failure** returns the stock render.
- `transferToImageBitmap`, captureStream's one-copy path and the
  `transferControlToOffscreen` placeholder stay as recorded in the S1/S2
  spec.
- **WebGL is still eligible everywhere** (opaque pixels unlike all four
  neighbours). An uploaded random texture read back with `readPixels` is
  perturbed. There is still no draw-time lever for WebGL.

## Builds and operation

- WSL `out/Default`: incremental (camoucfg, then Blink canvas and WebGL).
- Windows `out\Release`: through the change loop, with per-file replacement
  and hash proofs (the PR #27 procedure).
- Every build holds the build lock and is announced first.
- No merge that triggers `build-verify` while a Windows build runs.
- `patches/` is exported from `camoucrome/main`, never hand-edited.

## Out of scope (S2c)

- The WebGL-to-WebGL `texImage2D` GPU path that skips the snapshot hook.
- Copy-path cost: the GPU-to-CPU readback behind `GetSourceImageForCanvas`,
  the two full-canvas copies in the cache, and a float16 cache miss.
- Matching any real GPU's raster output.

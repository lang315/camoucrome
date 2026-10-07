# Canvas noise S2c: cost, and WebGL reads that skip the noise — design

Backlog item S2c from the roadmap, the follow-up to S2b (PR #28,
`specs/2026-10-06-canvas-noise-s2b-design.md`,
`measurements/2026-10-canvas-noise-s2b.md`). Approved in brainstorming on
2026-10-07. It takes two parts that S2b left open:
- the cost of the seeded canvas paths;
- WebGL reads that return the clean render: `readPixels` from a page's own
  framebuffer, and the WebGL-to-WebGL `texImage2D` GPU path.

## The problem, measured

The attribution spike ran on 2026-10-07. It used WSL `content_shell` at
`cd21e14` (S2b), CPU raster and SwiftShader GL. Values are medians over two
interleaved rounds, comparing the build with `canvas:seed` against the build
without it. The third arm is seeded with `canvas:noiseDensity` 0, which keeps
every copy and replay but skips the noise itself.

| case | unconfigured | seeded | seeded, density 0 |
|---|---|---|---|
| one `arc` + `fill` call | 0.375 µs | 8.98 µs (24×) | 8.83 µs |
| 10 000 arcs, no read | 2.85 ms | 85.8 ms (30×) | 91.7 ms |
| 10 000 arcs + `getImageData(0,0,1,1)` per frame | 26.7 ms | 123.5 ms (4.6×) | 117.1 ms |
| `getImageData(0,0,1,1)` after one new arc (1024²) | <0.1 ms | 10.3 ms | 4.9 ms |
| WebGL `readPixels` 1024² | 1.9 ms | 40.7 ms (21×) | 15.5 ms |
| WebGL `readPixels` 64² sub-rect | 0.3 ms | 1.0 ms (3.3×) | 0.9 ms |

What the table shows:

- **The draw cost is the per-draw replay, not the noise.** Density 0 changes
  nothing. Each draw builds a `MemoryManagedPaintCanvas`, replays the
  matrix/clip stack, records, allocates an A8 bitmap, builds an `SkCanvas`,
  plays back and merges. That is 24 times a stock draw call, which a script
  can measure by timing 1000 `fillRect` calls. It is a timing tell, not only
  a cost.
- **`getImageData(0,0,1,1)` noises the whole 1024² snapshot.** About half of
  the cost is the noise loop, and half is the copies (`readPixels` into a
  bitmap, then a full source copy).
- **`readPixels` 1024²: about 13.6 ms of copies and allocation, about 25 ms of
  loop.** The page buffer is copied to a scratch buffer and the scratch to a
  source copy, the scratch is zero-filled, and the result is copied back. The
  loop takes about 25 ns per pixel: bounds-checked spans, a 4-byte
  `std::ranges::equal` per neighbour, and a domain-string hash per channel
  draw.
- **`readPixels` 64²: four extra synchronous GPU reads** for the margin
  strips.
- **WebGL reads that skip the noise.** `readPixels` with a bound framebuffer
  skips the noise (`!framebuffer` in the hook; review triage #23, still
  OPEN). A page renders into its own framebuffer and reads the clean render.
  `texImage2D(webglCanvas)` takes `TexImageViaGPU` straight from the source
  drawing buffer, so the texture holds the clean render, and a framebuffer
  read in the second context returns it. Closing `texImage2D` alone would buy
  nothing while framebuffer reads are clean.

## Principle

Unchanged from the S1/S2 and S2b designs: linkable rather than detectable.
Where the design cannot tell whether a pixel's exact value is known to the
page, that pixel carries no noise. S2c changes **when** and **how cheaply**
the existing rules run, and on **which WebGL reads**. It keeps:
- the noise field: a 3×3 patch key, density 0.04, strength 1;
- the per-pixel eligibility rule;
- the mask's meaning.

## Success criteria (cost)

Measured by `scripts/measure_canvas_cost.py`, which this slice extends to the
spike's cases. The ratio is seeded against unconfigured on the same build, on
WSL `content_shell`.

| case | target |
|---|---|
| one draw call (10 × 2000 arcs, no read) | ≤ 1.2× |
| 10 000 arcs + `getImageData(0,0,1,1)` per frame | ≤ 2× |
| `getImageData(0,0,1,1)` after a change (1024²) | ≤ 0.5 ms absolute |
| WebGL `readPixels` 1024², flat and edge scenes | ≤ 3× |
| WebGL `readPixels` 64² sub-rect | ≤ 1.5× |

These targets are recorded in the measurement doc, not enforced as a CI gate.
- A missed target is reported with its number and its attribution, and
  the run carries on.
- A regression of any S2b verify row is never accepted.

## 1. The 2D mask is computed at flush, from the page's own recording

**Remove the draw-time hooks.** `CamouMark`, `CamouReplay`, `CamouMarkClip`
and the `copy` pre-clear in `Canvas2DRecorderContext::DrawInternal` go. A
seeded draw call then does exactly the stock work.

**One hook at the one flush point.** `BaseRenderingContext2D::FlushCanvasInternal`
releases the main recording (`recorder->ReleaseMainRecording()`) and then
calls `RasterRecord(recording)` on the shared-image or bitmap provider. Every
2D context goes through it (`CanvasRenderingContext2D`,
`OffscreenCanvasRenderingContext2D`), and every snapshot flushes first. When
`CamouMaskActive()`, the hook calls
`CamouMarkRecord(recording, clear_frame)` after the release and before
`RasterRecord`:

- **`clear_frame`.** When the provider clears the canvas before this record,
  the mask is reset first, so every pixel is exact.
- **State ops** (save, restore, concat, set-matrix, the clip ops) are applied
  to a reused coverage `SkCanvas` over a reused A8 bitmap the size of the
  canvas. That bitmap is 64 MB at 8192², so it is allocated fallibly. If the
  allocation fails, the record's area (the device clip bounds of every draw
  op) is marked `imported`, as S2b did on a failed replay allocation, and the
  context retries the allocation at the next flush. A recording is self-contained: the recorder restarts each recording
  with the current matrix/clip stack, so playing it from a fresh state gives
  the right transform and clip.
- **Each draw op is merged on its own**, in recording order:
  1. Its device area: the op's fast bounds through its flags, outset by 1 px
     for anti-aliasing, mapped by the current matrix, and intersected with the
     device clip bounds.
     - The fast bounds are `PaintOp::GetBounds` together with the flags'
       `computeFastBounds`, which covers the stroke, miter joins, a looper and
       a filter.
     - Never outset the stroke by hand: that can under-cover a miter spike.
     - When fast bounds cannot be computed, the area is the device clip
       bounds. Over-covering is free; under-covering leaves stale marks.
  2. That area of the scratch A8 bitmap is cleared. The op is rastered with
     coverage flags, through `RasterWithFlags` on a copy of its flags: opaque
     white, src-over, the shader dropped except for a gradient (whose alpha is
     its coverage), and the looper kept for the shadow pass, exactly as S2b's
     `CamouReplay` did.
  3. The scratch area is merged into the mask with the op's kind, through the
     unchanged `CanvasNoiseMask::Merge`.
- **Kinds come from the op and its flags.** These are the same rules as S2b's
  `CamouKindFor` and `CamouMark`. Each one is restated here against what the
  recording carries:

| op | kind |
|---|---|
| text (`DrawTextBlobOp`, slug ops) | nothing, unless its shader is an image or record shader: then `imported` over its area |
| image ops (`DrawImageOp`, `DrawImageRectOp`), vertices and mesh, a nested `DrawRecordOp`, Skottie | `imported` over its area |
| any op whose shader is an image or record shader (a pattern) | `imported` |
| a gradient shader, a looper (shadow), or an image filter | `aa`; with a looper, two passes as in S2b: the shadow pass as `aa`, then the shape without the looper by its own kind, and nothing at all when the shape alone draws nothing |
| opaque, `kDstOut` | `kClear` |
| `kClear` blend (`clearRect`) | `kClear` |
| a `DrawColorOp` with a transparent colour under `kSrc` or `kClear` (the `copy` pre-clear, `clear()`) | `kClear` over the device clip |
| opaque, `kSrcOver` | `kSolidOpaque` |
| anything else | `kSolid` |
| an op whose flags draw nothing (`nothingToDraw()`) | nothing |

- **Composited draws.** A `SaveLayer`, `SaveLayerAlpha` or
  `SaveLayerFilters` marks the device clip bounds at that point `imported`
  (as S2b's composited draw and layer rules do). Every op up to the matching
  restore is then skipped.
- **Every place that releases the recording is a flush point.** The plan
  confirms each one before the hook is written:
  - **`putImageData` (`imported`) and `transferToImageBitmap` (reset)** keep
    their own hooks, and each must observe the marks of every op recorded
    before it. The plan checks whether stock flushes before them. If it does
    not, the hook merges the pending recording first.
  - **The second `ReleaseMainRecording()`**, in
    `canvas_rendering_context_2d.cc` (about line 372), sits outside
    `FlushCanvasInternal`. The plan finds whether that release feeds a raster
    or drops the ops:
    - if it feeds a raster, it calls `CamouMarkRecord` too;
    - if it drops the ops, the mask must still match what the canvas holds
      afterwards: reset it if the canvas is cleared, otherwise leave it.
  - **Any other `ReleaseMainRecording` or `RasterRecord` caller** the plan
    finds on the box is handled the same way, and the plan lists them.
- **The mask generation** bumps when a merge changes a cell, as before, so
  `CamouNoised`'s cache key stays correct.
- **No seed: no hook work** (rule 5). A paint worklet has no flush and no
  host, so it never marks, as before.

Flush gets slower by one coverage pass. The coverage raster is CPU A8 over
tight op areas, so it costs less than the stock RGBA raster, and it is
measured in the "draw + read" row.

## 2. 2D readback: `getImageData` noises only what it returns

`getImageData(x, y, w, h)` computes noise only for the returned rect. The
noise of a pixel is a pure function of its 3×3 source patch, the mask cell
and the seed. So reading that rect plus a 1 px margin from the snapshot (the
margin clipped to the canvas, where edge pixels never change) gives exactly
the bytes the whole-canvas field holds there.

**The noise runs on premultiplied pixels, before the unpremultiply.**
`getImageData` returns unpremultiplied bytes, while the whole-snapshot path
noises premultiplied pixels under the `[0, alpha]` clamp. The regional path
therefore:
1. reads rect plus margin from the snapshot as premultiplied RGBA into a
   scratch buffer;
2. runs `PerturbRgbaEdges` there, with the mask window offset to the rect;
3. converts the result into the `ImageData` buffer by the same conversion
   stock `getImageData` uses.

If the regional path noised the unpremultiplied buffer instead, it would
disagree with `toDataURL` and `drawImage` on translucent pixels.
- `toDataURL`, `toBlob`, `convertToBlob` and `GetSourceImageForCanvas`
  (`drawImage`, `createPattern`, `createImageBitmap`, `texImage2D`) still
  noise the whole snapshot.
- `CamouNoised`'s cache stays as it is.
- When the cache already holds the whole noised snapshot for the current
  source and generation, `getImageData` reads from it.

## 3. The noise loop

`PerturbRgbaEdges` keeps its contract and its output, byte for byte:
- it reads through raw pointers, after one up-front size check of both
  buffers;
- it compares pixels as `uint32_t` loads;
- it hashes the six domain strings once per call, not once per pixel draw.
  `Draw(seed, domain, index)` gets an overload that takes the precomputed
  domain hash, and `derive_unittest` pins that both forms agree.

**No full source copy.** Callers stop copying the whole source into a second
buffer:
- `PerturbRgba` and `NoisedImage` keep a ring of three source rows (the row
  above, the current row and the row below, as they were before any
  write), so memory grows by three rows, not by one canvas.
- The unit tests pin byte equality against the copy-based reference on random
  and structured inputs: odd sizes, padded row bytes, bottom-up, and a mask
  with coarse cells.

## 4. WebGL `readPixels`

**Margins in one read.**
- **A read that touches no drawing-buffer edge from inside**, a sub-rect with
  room on every side, reads the expanded rect (`x-1 … x+w`, `y-1 … y+h`,
  clipped to the framebuffer) once into the scratch. That replaces the four
  strip reads, so it costs one round trip.
- **A full read**, or any read whose rect already reaches the framebuffer's
  edges on all sides, reads nothing extra and noises the page buffer in
  place through the row ring. This needs no scratch and no copy back.
- Both use the same field, so C28 (a sub-rect equals the matching part of a
  full read) still holds.

**A page's own framebuffer.**
- The `!framebuffer` condition is removed. A read with a bound
  framebuffer is noised by the same rule as the default one, but only for
  `RGBA`/`UNSIGNED_BYTE`.
- Only opaque pixels change (min alpha 255, as WebGL already uses), and only
  pixels that differ from all four neighbours.
- Float, half-float, integer and every other format/type is untouched.
- The margin reads come from the bound read framebuffer itself (no drawing-buffer
  binder), and are clipped to its read attachment's size, not to
  `drawingBufferWidth()`.

## 5. `texImage2D` from a WebGL canvas: closed by section 4, path unchanged

The GPU path (`TexImageViaGPU` straight from the source drawing buffer)
**stays as it is**. It uploads the clean render, and every way of reading that
texture back now goes through a noised read:
- the default framebuffer, as before;
- a page framebuffer, through section 4.

Because the field is a pure function of the 3×3 patch, the seed and the
opaque rule, context B's read of A's clean pixels gets exactly the field A's
own `readPixels` gets. A copy then agrees with its original, as in stock.

Routing the upload through the noised snapshot instead (`GetSourceImageForCanvas`)
was rejected, for two reasons:
- it would noise the pixels twice, so B's read would differ from A's read
  where stock gives equal reads;
- it would cost a GPU readback per upload.

## 5a. One rule binds sections 4 and 5

A WebGL read noises once, at the read. Nothing upstream of a WebGL read adds
WebGL noise.

## Verification

`scripts/verify_sp3a.py` keeps every row from C1 to C34. **They are the net
for the flush-time rewrite**: the S2b semantics rows C21–C34, especially C24a–d,
C27, C30–C34 and C33a–e, must stay PASS on the new build. A row that regresses
is fixed, never edited to pass.

New rows, each RED first on the S2b build:

- **C35. A framebuffer `readPixels` of a gradient triangle is noised.** It
  differs from the unconfigured read, and two seeded reads are identical.
  Guard: the unconfigured read has interior edge pixels (non-vacuous).
- **C36. A framebuffer `readPixels` sub-rect equals the matching part of a
  full framebuffer read**, byte for byte, with the rect away from every edge.
- **C37. A framebuffer read leaves non-opaque pixels alone**: a translucent
  scene read from a framebuffer equals the unconfigured read on every pixel
  with alpha < 255, and at least one opaque pixel differs.
- **C38. `texImage2D(webglCanvas)` and a read in a second context give the
  source's field.**
  - Context A draws the gradient triangle. Context B uploads A's canvas,
    draws it 1:1 into its own framebuffer and reads it.
  - The B read differs from the unconfigured B read. It equals A's own seeded
    `readPixels` byte for byte: noised once, not twice.
  - Guard: the unconfigured B read equals the unconfigured A read, so the
    copy is exact.
- **C39. `getImageData` of a sub-rect equals the whole-snapshot field**, byte
  for byte, on a canvas with opaque and translucent anti-aliased content whose
  noise touches the rect. The comparison is made two ways:
  - against the same rect of a full `getImageData`;
  - against the same rect read back after `drawImage(canvas)` onto a fresh
    canvas. That copy is marked imported, so it carries the whole-snapshot
    noise and no second noise.

  Guard: the rect holds at least one translucent pixel whose seeded value
  differs from the unconfigured one.
- **C40. One flush or many give one mask.** The same draws are run twice:
  once flushed by a 1×1 `getImageData` after every draw, and once flushed
  only at the end. The final `getImageData` of both canvases is identical,
  and noised.

`EXPECTED` becomes 47.

**Also required:**
- **Unit tests:** loop equality against the copy-based reference, the domain
  hash overload, and the row ring at 1, 2 and 3 rows.
- **The cost script** at the targets above, with every arm and the
  attribution if a target is missed.
- **`verify_review_2026_09_24` 12/12.**
- **On Windows**, through the host runner, in headless and headed mode:
  - the runner;
  - Windows `verify_sp3a`, where the baseline clauses are UNMEASURED as
    before;
  - calibration at density 0.04: S2 text ≥ 6/8 and S2 shape 8/8, with stock
    among neither.
- **Step 2 re-measure:** the oracle canvases still differ from control, and
  there is still no CreepJS "rgba noise".

## Builds and operation

- **S2c builds in its own trees:**
  - on the Mac, the git worktree `.claude/worktrees/s2c`, branch
    `s2c/canvas-cost`, cut from `origin/main`;
  - on the box, the gclient workdir `~/chromium-s2c`, branch `camoucrome/s2c`,
    cut from `8cf90b48`.

  `~/chromium/src` belongs to the observe slice (session camoucrome-80).
- Builds take turns through `build_lock.sh`. The box cannot hold two Chromium
  builds at once.
- The first build of the new workdir is a full one, about 59k steps.
- Export runs from the branch: `scripts/export.sh ~/chromium-s2c/src
  camoucrome/s2c`. The checkout sync check takes the workdir and branch,
  using the three-argument `check_checkout_sync.sh` from the observe branch
  once that lands, or the same comparison done by hand until then.
- Windows uses per-file replacement (W12) against the merged base, as in S2b.
  Every Windows build is announced and holds the lock.
- Timing runs are made while no build runs on the box. A parallel build
  skews them.

## Known gaps and accepted costs

- **GPU picking.** An app that renders object IDs as colours into a
  framebuffer and reads one pixel under the cursor can get a wrong ID. That
  happens on a pixel that differs from all four neighbours (an object's
  boundary) and is opaque: about 11.5% of such pixels change at density 0.04.
  Reads away from boundaries are untouched.
- **GPGPU through RGBA8.** Data packed into `RGBA`/`UNSIGNED_BYTE` render
  targets (for example TensorFlow.js's byte-packing fallback) can move by ±1
  on opaque pixels that differ from all four neighbours. Float and half-float
  targets are untouched.
- **`PIXEL_PACK_BUFFER` reads** (WebGL2) stay clean, as in SP3 §7.4.
- **A float framebuffer is a full bypass.** Section 4 noises only
  `RGBA`/`UNSIGNED_BYTE`. A page that renders into an `RGBA16F` or `RGBA32F`
  target (WebGL2, or `EXT_color_buffer_float`) and reads it with
  `readPixels(…, FLOAT)` gets the clean render. This is accepted for the same
  reason as the GPGPU bullet: float reads are mostly computation, and
  perturbing them breaks apps. It is a bypass, not only a side effect.
- **The flush gets one coverage pass more.** It is measured, and not
  hidden.
- **A flipped copy.** A WebGL canvas uploaded with `UNPACK_FLIP_Y_WEBGL`, or
  drawn mirrored, and read back has its patches hashed in the mirrored row
  order. Its noise then differs from the source's at the same pixels, so a
  page that flips the copy back and compares finds edge pixels that differ.
  Stock finds none.
- **A 2D canvas uploaded to WebGL is noised twice on readback.** The upload
  carries the 2D snapshot's noise, and then the WebGL read adds its own. That
  is true today through the default framebuffer, and section 4 extends it to
  page framebuffers. It is the S1/S2 known gap "an uploaded texture read back
  with `readPixels` is perturbed".
- **Every S2b known gap that this design does not name stays as recorded.**
  That covers coarse cells above 4096², layers, composited draws, the
  neighbour re-roll, the focus ring and `drawMesh`.

## Out of scope

- Matching any real GPU's raster output.
- A draw-time lever for WebGL. WebGL stays eligible everywhere under the
  edge rule.
- `captureStream`'s one-copy path, and the `transferControlToOffscreen`
  placeholder.

## Amended during planning (2026-10-07)

The box recon of `~/chromium-s2c` (Chromium 154) changed these points. Each
replaces the text above it, and the plan
(`plans/2026-10-07-canvas-noise-s2c.md`) implements the amended form.

- **No `clear_frame` reset.** `clear_frame` does not clear the surface: it
  only decides whether the last recording is kept for printing. A
  full-canvas `putImageData` also sets it, through `RestartRecording`, so a
  reset on it would wipe that write's `imported` marks. The mask resets only
  in `ResetInternal` (as in S2b) and through the kinds of the ops it walks:
  an overdraw's covering op is recorded and walked.
- **`putImageData` marks after `WritePixels`.**
  - A partial write flushes the pending recording inside `WritePixels`, so
    those ops are marked first, in order.
  - A full-canvas write drops the pending recording without rastering it,
    and its own `imported` mark covers the canvas.
  - The offscreen `WritePixels` always flushes first.
- **The flush walk's details.**
  - A failed allocation of the coverage bitmap marks the **whole canvas**
    `imported`, because no device clip exists without a canvas.
  - An op's area is its local bounds grown by the paint's fast bounds
    **before** the matrix. `cc::PaintOp::ComputePaintRect` grows them after
    the matrix, which under-covers a scaled stroke.
  - Layers arrive as a `DrawRecordOp` (`local_ctm` false). They are marked
    `imported` over the clip and played for their matrix.
  - Lite ops (`DrawLineLiteOp`, `DrawArcLiteOp`) are rastered through their
    `CorePaintFlags`.
- **Composited draws keep S2b's text carve-out.** The clip of a `SaveLayer*`
  is marked `imported` by the first op inside it that is not text, or by
  text whose style is a pattern. Shadowed or filtered text alone marks
  nothing, as in S2b's `CamouMarkClip`.
- **A page framebuffer's extent comes from a double read.** Blink does not
  track a framebuffer's size, and the read attachment's size is not
  available.
  - The expanded rect is read twice, into buffers filled `0x00` and `0xFF`.
    GL leaves a pixel outside the framebuffer unwritten, so the pixels where
    the two reads agree are the framebuffer's.
  - C37 checks it: the framebuffer's edge pixels must stay exact.
  - A framebuffer read with margins therefore costs two extra reads. The
    default framebuffer still uses `drawingBufferWidth()`/`Height()` and one
    read.
- **C39 and C40 are proven by mutation, not RED on S2b.** S2b already
  satisfies both: it noises the whole snapshot, and it marks at draw time.
  - C39 fails when the regional path noises unpremultiplied values.
  - C40 fails when the mask is reset at every flush.
- **C35 and C37.** C35 also requires interior edge pixels in the unconfigured
  read (a vacuity guard). C37 also requires the framebuffer's edge pixels to
  stay exact (`edgeDiff`).
- **Found by the recon, recorded as known gaps** (not in this slice's scope):
  - `transferToImageBitmap` on an `OffscreenCanvas` returns an un-noised
    image;
  - so do the offscreen `convertToBlob` paths that bypass `CamouNoised`.

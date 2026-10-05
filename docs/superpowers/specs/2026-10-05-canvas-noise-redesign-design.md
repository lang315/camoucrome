# Canvas noise redesign (backlog S1 + S2) — design

Backlog items S1 and S2 from the step 2 tables
(`measurements/2026-10-step2-baseline.md`, roadmap "Re-rank from the step 2
tables"). Approved in brainstorming on 2026-10-05. Phase 0 is a spike and
decides between the target design and the fallback below.

## The problem, measured

`sp3a-canvas-noise.patch` adds noise to pixels as they leave the canvas, at
readback (`camoucfg::PerturbRgbaAt`). Noise touches only opaque pixels
(alpha 255), at density 0.0005 per RGB channel, and moves each by ±1.

- **S1, a tell.** A 64×64 one-colour fill reads back 3 distinct colours through
  `getImageData`. A WebGL clear reads back 5 through `readPixels`. Stock Chrome
  reads 1 in both. The noise lands on exactly the pixels whose value a page
  knows.
- **S2, linkability.** The oracle's text canvas and shape canvas hash to stock's
  values (`9c3103de`, `561c139d`) on the fork in every baseline cell. Those
  canvases are mostly transparent or partially transparent pixels, so at
  density 0.0005 the noise usually touches none of them. Every profile on one
  host then shares the host's canvas hash.

Two more ways to detect it were found while designing. Both hold for any
readback noise, today's included:

- **Write, then read back.** A page writes a random pattern with
  `putImageData` and reads it back with `getImageData`. Stock returns the bytes
  unchanged. Readback noise changes them.
- **Copy paths.** `drawImage(canvas)`, `createImageBitmap(canvas)`,
  `captureStream()` and WebGL `texImage2D(canvas)` read the canvas without
  noise, because `sp3a-canvas-noise.patch` hooks none of them. A page that
  compares a copy against `getImageData` of the original sees the difference.

## Principle: linkable rather than detectable

A canvas that reads exactly like stock can at worst be linked to other profiles
on the same host. Noise that a page can detect marks the browser as modified on
every site. So when the design cannot tell whether noise is safe, it returns
stock bytes.

## Phase 0: the spike (throwaway code)

The question: can the fork vary 2D canvas output **at draw time**, so that the
variation is part of the canvas content itself? The lever to try is a per-seed
sub-pixel offset of the text origin in
`BaseRenderingContext2D::DrawTextInternal`, on the renderer side, before any
raster backend runs. If text is drawn a fraction of a pixel away, every readback
and every copy path agrees, because there is nothing to add afterwards.

Measured on the Windows build (`out\Release`), with the change applied in the
tree and not exported:

| # | measurement | needed to pass |
|---|---|---|
| P1 | distinct `toDataURL` hashes of the oracle text canvas across 8 seeds, on a GPU canvas | ≥ 6 of 8 distinct, none equal to stock |
| P2 | the same on a `willReadFrequently: true` canvas (the CPU raster path) | ≥ 6 of 8 distinct, none equal to stock |
| P3 | a solid fill, a hard pixel-aligned edge, a 1px line, and a `putImageData` random-pattern round trip | byte-identical to stock |
| P4 | `drawImage(canvas)` into a second canvas at a 1px offset, then `getImageData` of both | the two agree |
| P5 | the same text drawn at x and at x+1 | the two images differ only by the 1px shift |

Before the spike changes anything, P3 and P4 are run against the current build
and must fail. That is their RED. The spike is one Blink edit: a WSL
incremental build and a Windows rebuild of the touched object plus relink. Its
code is discarded and its numbers are recorded.

**Decision.**
- P1–P5 all pass: build the target design.
- P1 or P2 fails (Skia snaps glyphs, or there are too few distinct positions):
  build the fallback.
- P3, P4 or P5 fails with the text offset in place: the lever is itself a tell,
  so build the fallback.

## Target design (if the spike passes)

**2D canvas: variation at draw time.**
- `fillText` and `strokeText` draw at the origin plus a seed-derived offset
  `(dx, dy)`, one per `canvas:seed`, each component in `[0, 1)` px, constant for
  the profile. The spike decides the quantisation that Skia's subpixel bins
  actually resolve.
- `measureText` is unchanged, and the metric-jitter slice stays as it is.
- No readback noise on 2D canvases that only contain text, fills, images and
  `putImageData` data.

**2D canvas with anti-aliased geometry.** The text offset does not reach arcs,
bezier curves or rotated paths. On a canvas whose state includes them, readback
noise stays, but narrower than today:
- A pixel is perturbed only if it is interior (it has four neighbours), its
  alpha is not 0, **and it differs from all four of its neighbours** in the
  canvas snapshot. Pixels in a solid region, on a hard edge, or on a 1px line
  always have a same-coloured neighbour, so they never change.
- The noise works on the snapshot's **premultiplied** values: each RGB channel
  moves by up to ±strength, clamped to `[0, alpha]`. Every result is a value
  stock can store at that alpha, so the unpremultiplied readback that Skia
  makes from it stays on stock's grid. Opaque pixels behave as before; pixels
  with partial alpha (anti-aliased edges on a transparent background) become
  eligible too.
- A per-canvas flag records anti-aliased geometry draws (`arc`, `ellipse`,
  `bezierCurveTo`, `quadraticCurveTo`, and fills or strokes under a
  non-axis-aligned transform). A second flag records **imported pixels**:
  `putImageData`, and `drawImage` or `createPattern` whose source is a canvas,
  an `OffscreenCanvas` or an `ImageBitmap`. Imported pixels may already carry
  noise, and a second field on top of them would make a copy disagree with its
  original. Readback noise applies only when the first flag is set and the
  second is not. Either way, a canvas that is unsure reads as stock.
- The noise moves from the four readback APIs to the canvas **snapshot** taken
  for any consumer: `getImageData`, `toDataURL`, `toBlob`, `convertToBlob`,
  `drawImage(canvas)`, `createImageBitmap(canvas)` and WebGL
  `texImage2D(canvas)`. Every way of reading the canvas then sees one noise
  field. `captureStream` is checked in the plan, and if it cannot be hooked it
  is recorded as a known gap.

**WebGL `readPixels`.**
- Keeps readback noise under the "differs from all four neighbours" rule.
  Neighbours are read within the requested rect, so `PerturbRgba` gains `width`
  and `height`. Only opaque pixels change here: a context with
  `premultipliedAlpha: false` stores unpremultiplied values, which the
  `[0, alpha]` clamp would move off their grid.
- A clear and solid fills read as stock.
- Known gap: a `texImage2D` upload of a random pattern, read back with
  `readPixels`, is perturbed. WebGL has no draw-time lever as cheap as the text
  offset.

**Density.** `canvas:noiseDensity` keeps its key. It now means the fraction of
channels perturbed among eligible pixels, and the new default is calibrated
until the oracle's shape canvas hashes differ across 8 of 8 seeds. Strength
stays ±1.

## Fallback design (if the spike fails)

Readback noise only, with these changes:
- The "differs from all four neighbours" rule, for 2D and WebGL alike, on
  premultiplied values for 2D as in the target design.
- The imported-pixels flag: a canvas that has received `putImageData`, or a
  `drawImage` or `createPattern` from a canvas, `OffscreenCanvas` or
  `ImageBitmap`, gets no noise.
- Noise at the snapshot, covering the copy paths as in the target design.
- The density calibrated so that the oracle's text and shape canvases both vary
  across 8 of 8 seeds.

Two gaps remain and are recorded:
- A `putImageData` round trip on a canvas that also holds anti-aliased content
  would be perturbed if the flag were not set, so the flag is the defence.
- Noise is still something added at readback, not a different rasteriser.

## Amended while planning (2026-10-05)

Three changes from the approved draft, found while writing the plan:

- **Partial alpha.** The draft kept today's opaque-only rule. Measured in
  Chrome on the oracle's drawings, the shape canvas has **0** pixels that are
  opaque and unlike all four neighbours (638–656 opaque pixels, all in solid
  regions); the text canvas has 103. So the draft's "the shape canvas differs
  across 8 of 8 seeds" could not pass. Pixels with partial alpha that are
  unlike all four neighbours number 84–105 on the shape canvas and 1664 on the
  text canvas. The owner chose to make them eligible, through the
  premultiplied clamp above.
- **Imported pixels, not only `putImageData`.** `drawImage(A)` into B hands B
  pixels that already carry A's noise. B's own field would then make
  `getImageData(B)` differ from `getImageData(A)`, which is the copy-path tell
  this design removes. The flag covers every canvas-derived source.
- **C9.** `verify_sp3a.py` C9 asserts a DevTools screenshot of a scene with
  text equals stock. A draw-time text offset moves on-screen text by design,
  so under the target design C9's scene loses its text. Under the fallback C9
  stays as it is.

Known gaps recorded with them:
- `captureStream`'s one-copy path (`CopyRenderingResultsToVideoFrame`, feature
  `kOneCopyCanvasCapture`) copies from the rendering context straight to a
  video frame, past the snapshot. Its two-copy fallback is covered.
- A `VideoFrame` made from a canvas is not a canvas-derived source to the
  flag, so `drawImage(new VideoFrame(canvas))` can carry two fields.
- The placeholder of a canvas given to `transferControlToOffscreen` reads as
  stock through `toDataURL`, while the worker's own readbacks carry noise.
- WebGL `readPixels` and a WebGL canvas's `toDataURL` use different fields
  (different seeds, and `readPixels` is bottom-up). That was already so before
  this design.
- `OffscreenCanvas.transferToImageBitmap()` hands the canvas content over
  through the context's own transfer, past the snapshot hook, so it reads stock
  while `getImageData` and `convertToBlob` of the same canvas carry noise; and
  a `bitmaprenderer` canvas showing such a bitmap is not eligible. Hooking it
  needs its own design (the transfer clears the source).

## Configuration

No new keys: `canvas:seed`, `canvas:noiseDensity` and `canvas:noiseStrength`
keep their names. The text offset derives from `canvas:seed` alone, with its
own domain string (`canvas-text-offset`), so it adds no knob. An absent seed
still means no change at all (rule 5).

## Verification (RED first)

- **Unit** (`components/camoucfg`, `canvas_noise_unittest`):
  - a one-colour buffer is unchanged at density 1;
  - a pixel with one same-coloured neighbour is unchanged at density 1;
  - a pixel unlike all four neighbours changes at density 1;
  - alpha-0 pixels are unchanged, and a partial-alpha pixel stays a valid
    premultiplied value (every channel at most its alpha);
  - the text offset is deterministic per seed and lies in `[0, 1)`.

  Each test is seen failing against today's functions first.
- **Browser** (`verify_sp3a.py` grows rows; content_shell on Linux, `chrome`
  on Windows through `CAMOU_SHELL`):
  - a solid fill, a clear and a hard edge read as stock in 2D, WebGL and a
    worker's OffscreenCanvas;
  - a `putImageData` round trip is exact;
  - `drawImage(canvas)` and `createImageBitmap` agree with `getImageData`;
  - text and shape canvases differ from stock and differ across 8 seeds;
  - a re-read reproduces.

  The new rows fail on today's build first (S1 reads 3 and 5; the round trip
  and copy rows differ; S2's hash equals stock).
- **Existing rows stay green.** C6's drawing is a WebGL clear, which the new
  rule correctly leaves alone, so C6 gets a drawing with anti-aliased content
  (a gradient triangle). Any other row whose drawing has no eligible pixels is
  changed the same way. Under the target design C9's scene loses its text
  (see "Amended while planning").
- **Step 2 after the Windows build.**
  - noise reads 1 and 1;
  - the oracle's `canvas.text` and `canvas.shape` differ from stock and between
    the two linkability identities;
  - the CreepJS "rgba noise" row is absent;
  - stability keeps them across relaunch.

## Builds and operation

- WSL `out/Default`: incremental. The camoucfg target rebuilds, then Blink.
- Windows `out\Release`: rebuild through the change loop (runbook §7), with the
  revised patch applied by `git apply --include` where it qualifies.
- Every build holds the build lock and is announced first.
- No merge that triggers `build-verify` while a Windows build runs.

## Out of scope

- WebGL draw-time variation, and with it the WebGL upload round trip.
- Matching the claimed GPU's real raster output. No approach can produce it,
  and every approach yields a hash no real device has seen.
- `measureText` (the metric-jitter slice stays as it is).

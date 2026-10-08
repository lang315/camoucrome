# Canvas noise S2c — measurements

Spec: `docs/superpowers/specs/2026-10-07-canvas-noise-s2c-design.md`.
Plan: `docs/superpowers/plans/2026-10-07-canvas-noise-s2c.md`.

## §1 Attribution spike (2026-10-07)

WSL `content_shell` at `cd21e14` (S2b), CPU raster and SwiftShader GL. Medians
over two interleaved rounds; the third arm is seeded with `canvas:noiseDensity`
0, which keeps every copy and replay but skips the noise itself.

| case | unconfigured | seeded | seeded, density 0 |
|---|---|---|---|
| one `arc` + `fill` call | 0.375 µs | 8.98 µs (24×) | 8.83 µs |
| 10 000 arcs, no read | 2.85 ms | 85.8 ms (30×) | 91.7 ms |
| 10 000 arcs + `getImageData(0,0,1,1)` per frame | 26.7 ms | 123.5 ms (4.6×) | 117.1 ms |
| `getImageData(0,0,1,1)` after one new arc (1024²) | <0.1 ms | 10.3 ms | 4.9 ms |
| WebGL `readPixels` 1024² | 1.9 ms | 40.7 ms (21×) | 15.5 ms |
| WebGL `readPixels` 64² sub-rect | 0.3 ms | 1.0 ms (3.3×) | 0.9 ms |

## §2 Workdir

S2c builds in its own workdir, `~/chromium-s2c/src`, a `git worktree` of
`~/chromium/src` on branch `camoucrome/s2c` (at `8cf90b48`, the S2b state), so
`~/chromium/src` stays with the observe slice.

- A worktree carries only the top-level repo; `~/s2c-deps.txt` lists the 50
  gclient dependency paths (sub-repos, sysroots, toolchains) copied in from
  `~/chromium/src`.
- `gn gen` failed in `compute_build_timestamp` until `build/util/LASTCHANGE`
  and `LASTCHANGE.committime` were copied.
- The first build failed at once on `gpu/webgpu/DAWN_VERSION`. Ten gclient
  hook outputs, ignored by git and so absent from a fresh workdir, had to be
  copied from `~/chromium/src`: `.landmines`,
  `build/config/siso/.sisoenv`, `build/config/siso/backend_config/backend.star`,
  `buildtools/reclient_cfgs/reproxy.cfg`, `chromeos/tast_control.gni`,
  `gpu/config/gpu_lists_version.h`, `gpu/webgpu/DAWN_VERSION`,
  `gpu/webgpu/dawn_commit_hash.h`, `skia/ext/skia_commit_hash.h`,
  `testing/location_tags.json`.
- `args.gn` is the same as `~/chromium/src/out/Default`'s.
- Build (`content_shell components_unittests`): siso planned 70 812 steps;
  the total shrank as it ran. After 5 h 07 min, at 52 794/54 369, the Windows
  host rebooted and killed it. The restart rebuilt 2 538 steps in 762 s
  (`Build Succeeded`, `rc=0`). The full build took about 5 h 20 min of
  compile time on 16 cores.
- Unit tests (`PerturbRgba*:CanvasNoise*:NoisedImage*:NoisedRegion*:CanvasNoiseMask*:Derive*`):
  65 of 65 pass.

## §3 RED on the S2b build

`verify_sp3a.py` at a59ec7a against the S2b build in `~/chromium-s2c`:
47 rows, `rc=1`. C1–C34 PASS, C39 and C40 PASS (their RED comes from the
mutations in Tasks 5 and 4), C35–C38 FAIL:

```
FAIL  35 framebuffer readPixels of a gradient triangle noised and deterministic
FAIL  36 framebuffer readPixels sub-rect equals the full framebuffer read's part
FAIL  37 framebuffer read leaves translucent pixels exact, changes an opaque one
FAIL  38 texImage2D(webgl canvas) read in a second context equals the source's read
PASS  39 getImageData sub-rect equals the whole-snapshot field (full read and copy)
PASS  40 one flush or many give one mask
```

Causes, from each row's note:

- C35: seeded hash equals the unconfigured one (1133855933 both); `same` is true and `e` is 1442, so the row measured a real scene and found no noise.
- C36: seeded hash equals the unconfigured one (83219890 both), `diff` 0 in both.
- C37: `opaqueDiff` is 0 under the seed (`trans` 2048, `transDiff` 0).
- C38: `eq` is false under the seed (R noised, B clean) and true unconfigured, so the flip orientation is right.

## §4 Cost before S2c

`measure_canvas_cost.py` at a59ec7a, S2b build, two interleaved rounds, medians
(ms except `per_draw_us`). Ratios are to the unconfigured arm.

| case | none | seed | seed_d0 |
|---|---|---|---|
| per_draw_us | 0.350 | 8.300 (23.71x) | 8.250 (23.57x) |
| draw_only | 2.600 | 82.200 (31.62x) | 81.950 (31.52x) |
| draw_read | 24.900 | 113.500 (4.56x) | 109.000 (4.38x) |
| read_2d | 0.000 | 9.400 | 4.500 |
| gl_flat.large | 1.800 | 38.250 (21.25x) | 14.450 (8.03x) |
| gl_flat.small | 0.400 | 1.600 (4.00x) | 1.400 (3.50x) |
| gl_edges.large | 1.800 | 44.200 (24.56x) | 14.600 (8.11x) |
| gl_edges.small | 0.300 | 1.500 (5.00x) | 1.500 (5.00x) |
| gl_fbo.large | 1.750 | 1.800 (1.03x) | 1.800 (1.03x) |
| gl_fbo.small | 0.300 | 0.300 (1.00x) | 0.300 (1.00x) |

```
target per_draw_us ratio<=1.2: 23.71 MISS
target draw_read ratio<=2.0: 4.56 MISS
target read_2d abs<=0.5: 9.40 MISS
target gl_flat.large ratio<=3.0: 21.25 MISS
target gl_edges.large ratio<=3.0: 24.56 MISS
target gl_edges.small ratio<=1.5: 5.00 MISS
```

Reading: draw cost is the same with density 0 (23.6x), so the per-draw cost is
the copies and replays, not the noise. GL reads cost 21–25x seeded and about 8x
at density 0. The framebuffer reads show 1.0x because they are not noised yet
(C35–C38 FAIL).

## §5 Additions (Task 2)

Box workdir at 5534316, `components_unittests` + `content_shell` built, 219 steps
(non-zero).

Golden. `GoldenFieldUnchanged` was RED on the S2b build with exactly two
"Expected equality" lines: `Fnv(top)` 11153446145880503195 (0x9AC9002D1AA8339B) and
`Fnv(bottom)` 6677792667850392518 (0x5CAC490D0AEE43C6); the other 9 tests passed.
After the loop rewrite the same hashes hold (GREEN), so the field did not move.

Tests. The W5 filter ran 70 tests, all passed (rc 0), including
`PerturbRgbaEdgesTest.{GoldenFieldUnchanged,InPlaceEqualsTwoBuffer,MaskOriginSelectsTheWindow}`,
`NoisedRegionTest.EqualsTheWholeImageField`, `DeriveTest.KeyedFormsAgreeWithStringForms`.
The test build first failed on `-Wunsafe-buffer-usage` in `MixedScene`
(raw pointer indexing); fixed with spans.

verify_sp3a: 43 PASS / 4 FAIL, the FAILs are C35-C38 with the same causes as §3
(seeded hash equals unconfigured for C35 to C37; C38 `eq` false seeded).

Cost, two arms not interleaved here (one run), ratios to unconfigured:

| case | none | seed | seed_d0 |
|---|---|---|---|
| per_draw_us | 0.350 | 8.225 (23.50x) | 8.550 (24.43x) |
| draw_only | 2.700 | 83.800 (31.04x) | 84.850 (31.43x) |
| draw_read | 25.950 | 109.900 (4.24x) | 110.500 (4.26x) |
| read_2d | 0.000 | 4.700 | 3.000 |
| gl_flat.large | 1.800 | 13.500 (7.50x) | 13.000 (7.22x) |
| gl_flat.small | 0.300 | 1.500 (5.00x) | 1.400 (4.67x) |
| gl_edges.large | 1.800 | 13.800 (7.67x) | 12.900 (7.17x) |
| gl_edges.small | 0.300 | 1.500 (5.00x) | 1.400 (4.67x) |
| gl_fbo.large | 1.800 | 1.800 (1.00x) | 1.800 (1.00x) |
| gl_fbo.small | 0.300 | 0.300 (1.00x) | 0.400 (1.33x) |

```
target per_draw_us ratio<=1.2: 23.50 MISS
target draw_read ratio<=2.0: 4.24 MISS
target read_2d abs<=0.5: 4.70 MISS
target gl_flat.large ratio<=3.0: 7.50 MISS
target gl_edges.large ratio<=3.0: 7.67 MISS
target gl_edges.small ratio<=1.5: 5.00 MISS
```

Reading: the in-place pass cut `gl_*.large` from about 21-25x to about 7.5x and
`read_2d` from 9.4 to 4.7 ms; draw cost is untouched (Tasks 3 to 5).

Export (W6): 9 fixups folded, 38 commits, 0 fixup subjects, 0 dirty. The export
reproduced the pushed tree byte for byte (`diff -rq` of additions, patches and
invariants.json empty), so `patches/` is unchanged and nothing was pulled.
Sync check: "all 45 copied files are identical in repo and checkout".

## §6 WebGL (Task 3)

RED (current build, S2b + Task 2, before the code): `verify_sp3a` C35, C36, C37
and C38 FAIL (the framebuffer reads were not noised at all). C37's `edgeDiff`
clause is vacuous on that build (nothing is noised, so it is 0 by construction);
it can only fail once framebuffer reads are noised with a wrong extent, which is
what the clause guards.

Code: `readPixels` noises the page buffer in place when the read has no room for
a margin, otherwise one expanded read (rect + 1 px) is noised and the rect is
copied back. A page framebuffer's extent comes from reading the expanded rect
twice, into buffers filled 0x00 and 0xFF (a pixel is inside the framebuffer iff
the two reads agree). The service leaves out-of-framebuffer pixels unwritten, so
C37's `edgeDiff` clause passed (framebuffer edge texels stay exact).

Build: `Build Succeeded: 277 steps` (content_shell, components_unittests).

GREEN: `verify_sp3a` 47 PASS, `ALL_PASS`, rc=0; C35 to C38 PASS; C17 to C20, C28,
C29 still PASS. `verify_review_2026_09_24` 12/12 ALL_PASS. Unit filters
(PerturbRgba, CanvasNoise, NoisedImage, NoisedRegion, CanvasNoiseMask, Derive)
all PASSED. `gn check` of modules/webgl: Header dependency check OK. `checkdeps`
on modules/webgl reports `base/process/memory.h` (line 29, added by S2b, not by
this task) as an illegal include; recorded, not changed here.

Cost (`measure_canvas_cost.py`, the edges scene now uses `Math.imul`, so
`gl_edges` "before" ratios are not comparable with §4):

```
gl_edges.large     none=1.800 (1.00x)  seed=2.750 (1.53x)
gl_edges.small     none=0.300 (1.00x)  seed=0.600 (2.00x)
gl_fbo.large       none=1.800 (1.00x)  seed=52.000 (28.89x)
gl_fbo.small       none=0.300 (1.00x)  seed=1.100 (3.67x)
gl_flat.large      none=1.800 (1.00x)  seed=2.800 (1.56x)
gl_flat.small      none=0.300 (1.00x)  seed=0.600 (2.00x)
target gl_flat.large ratio<=3.0: 1.56 PASS
target gl_edges.large ratio<=3.0: 1.53 PASS
target gl_edges.small ratio<=1.5: 2.00 MISS
```

`gl_edges.small` MISS: 0.3 ms to 0.6 ms, a 0.3 ms absolute cost at 0.1 ms timer
resolution. `gl_fbo.*` is recorded without a target; the double read costs about
29x on a 1024x1024 read. The 2D targets (`per_draw_us`, `draw_read`, `read_2d`)
are Task 4 and 5 work.

Export (W6): fixups folded into `sp3a-canvas-noise`, 38 commits, 0 fixup
subjects, 0 dirty. Only `patches/sp3a-canvas-noise.patch` changed (sha256
e38297162cf8...); sync check "all 45 copied files are identical in repo and
checkout". `pytest scripts/`: 176 passed.

### §6.1 Fix round 1 (review of 1e6c61b..8d3baba)

C41 (new row, EXPECTED 47 to 48): WebGL2, `antialias:false`, default
framebuffer, `readBuffer(NONE)`, a sentinel buffer, a sub-rect and a full
`readPixels`; PASS iff the seeded buffers stay unchanged and the GL errors equal
the unseeded arm's (INVALID_OPERATION).

RED on 8d3baba (uniform sentinel): `FAIL 41`; seeded `sub` e=1282 n=256 (256
bytes of the page's array overwritten from heap), unconfigured `sub` e=1282 n=0.
The full read showed n=0 only because a uniform sentinel has no edges to noise;
the row now uses random opaque texels, so an in-place pass would show.

C37 `edgeDiff` mutation (both probes filled 0x00, so every pixel "agrees"):
`FAIL 37`, seeded `edgeDiff` 9, `opaqueDiff` 152; unconfigured 0. The clause
guards the extent. Reverted (the fix replaced the block).

Fixes: noise skipped for READ_BUFFER NONE on the default framebuffer; scratch is
zeroed and fallible (`Partitions::BufferTryAlignedZeroedMalloc`, no
`base/process/memory.h`); the default-framebuffer region read is compared with
the page's own read before it is copied back; `CamouNoiseReadPixels` is private.
`checkdeps.py` on modules/webgl: SUCCESS; `gn check`: OK.

FBO cost finding (unconfigured, 1024^2 RGBA8 FBO): `readPixels(-1,-1,1026,1026)`
1.75 to 1.90 ms against `(0,0,1024,1024)` 1.75 to 1.80 ms, so the out-of-bounds
part is not slow. With the previous code a seeded 1024^2 read took 52 ms. A timing
build (laps in the function) showed 28 ms of it in the two reads plus fills and
0.5 ms in the scan: `std::ranges::fill` over a span iterator is a byte loop, tens
of ms on 4 MB. Replacing the fill with `memset` (and dropping the 0x00 fill, the
allocator zeroes) gave 10.4 ms: two 1026^2 reads ~6.4 ms, scan 0.45 ms, noise
1.2 ms. The remaining cost is the two whole-rect reads. Review option (b) (read
0xFF only if the 0x00 read holds a zero pixel) cannot help a read at the origin:
the out-of-bounds ring reads zero, so the read is always ambiguous. Option (c)
(ring only) does not apply for the same reason. What was done instead: a page
framebuffer is always [0,W) x [0,H), so its part inside the expanded rect is found
from one row and one column starting at the rect's corner nearest the origin,
each read twice (fills 0x00 / 0xFF). Four thin reads replace two whole-rect
reads, and a margin read now reads the region once, as the default framebuffer
does. Option (a) (per-row memcmp) became unnecessary.

GREEN: `verify_sp3a` 48 PASS, ALL_PASS, rc=0 (C37 and C41 PASS; C17 to C20, C28,
C29, C35, C36, C38 PASS); `verify_review` 12/12; unit filters PASSED.

Cost (`measure_canvas_cost.py`; small GL cases now time 10 reads per sample and
report per read):

```
gl_edges.large     none=1.700 (1.00x)  seed=2.600 (1.53x)
gl_edges.small     none=0.290 (1.00x)  seed=0.580 (2.00x)
gl_fbo.large       none=1.800 (1.00x)  seed=3.500 (1.94x)
gl_fbo.small       none=0.290 (1.00x)  seed=1.700 (5.86x)
gl_flat.large      none=1.800 (1.00x)  seed=2.600 (1.44x)
gl_flat.small      none=0.290 (1.00x)  seed=0.590 (2.03x)
target gl_flat.large ratio<=3.0: 1.44 PASS
target gl_edges.large ratio<=3.0: 1.53 PASS
target gl_edges.small ratio<=1.5: 2.00 MISS
target gl_fbo.large ratio<=3.0: 1.94 PASS
```

`gl_edges.small` MISS is real, not quantization: batched, it is 0.29 ms of extra
cost per read, one GPU round trip for the margin region read (the cost of one
stock 64x64 read). It cannot be below 2x without dropping the margin read.
`gl_fbo.small` (no target) is 5.86x: four extent reads plus the region read, five
round trips.

Export: sp3a and sp3b patches both change (they patch the same file; sp3b's
context shifted). The earlier Task 3 export left `sp3b-webgl-profile.patch`
stale in the repo; it is regenerated here. All 79 exported files were compared
against the Mac tree by short hash; only those two differ. Sync check: all 45
copied files identical.

## §7 2D at flush (Task 4)

The draw-time hooks (`CamouReplay`, `CamouMark`, `CamouMarkClip`,
`CamouMergeRecord`, `CamouKindFor`) are gone. `CamouMarkRecord` walks the
released recording in `BaseRenderingContext2D::FlushCanvasInternal`, which is the
only flush point for both the onscreen and offscreen contexts. Each draw op is
rastered as coverage into a reused A8 bitmap and merged into the mask under the
recorded matrix and clip. `putImageData` now marks after `WritePixels`.

Recon held against the tree. The other `ReleaseMainRecording` callers are the
providers' `ClearAtCreation`, which marks nothing, and the recorder's own
`RestartRecording`/`RestartCurrentLayer`, which drop ops without rastering them.
`GetBounds` returns false for `DrawColor` and `DrawRecord`. The Lite ops carry
`CorePaintFlags`.

Two compile fixes to the brief's code:
- `cc::PaintRecord` iteration needs `cc/paint/paint_op_buffer_iterator.h`.
- `DrawLineLiteOp::Raster` and `DrawArcLiteOp::Raster` are static
  (`Raster(const Op*, SkCanvas*, const PlaybackParams&)`), so the coverage ops are
  built as locals and passed to them.

RED, C40 mutation (`camou_mask_.reset()` first in `CamouMarkRecord`; build 179
steps): `verify_sp3a` 46 PASS, 2 FAIL.

```
FAIL  22 a draw elsewhere does not change a region's noise
FAIL  40 one flush or many give one mask
      22 : seeded {'r1': 3989186272, 'r2': 612045226, 'e': 70}, unconfigured {'r1': 612045226, 'r2': 612045226, 'e': 70}
      40 : seeded {'h1': 1023908166, 'h2': 1371003653, 'e': 256}, unconfigured {'h1': 1860604165, 'h2': 1860604165, 'e': 256}
```

`verify_review` was not run on the mutant.

GREEN (build 23 steps; unit filters 70 tests PASSED):
- `verify_sp3a` 48 PASS, ALL_PASS, rc=0 against the 48-row script. This covers
  C21 to C27, C30 to C34, C33a to C33e and C35 to C41.
- `verify_review` 12/12 ALL_PASS.
- The leftover-symbol grep over `canvas2d/*.{h,cc}` prints nothing (rc=1).
- W5g: `gn check` on core, canvas and webgl each reports "Header dependency check
  OK", and `checkdeps.py` reports SUCCESS on each of the three directories. This
  gn takes one target per call and checkdeps one directory per call, so W5g's
  single-line form fails on usage.

Against the 49-row script (C42 was added by the Task 3 re-review), the same build
gives 48 PASS and 1 FAIL. The failure is C42, a WebGL row (RGBA16F drawing
buffer), which this task does not touch:

```
      42 : seeded {'sub': {'e': 1282, 'n': 0}, 'full': {'e': 1282, 'n': 308}}, unconfigured {'sub': {'e': 1282, 'n': 0}, 'full': {'e': 1282, 'n': 0}}
```

Shadowed-text probe (not a C-row). An arc, then `shadowBlur = 4` `fillText` away
from it, read with `getImageData`. In the arc region, 3 bytes differ seeded vs
unconfigured, and 0 bytes differ between seeded with text and seeded without.
Shadowed text marks nothing, so the arc keeps its noise exactly.

Cost (`measure_canvas_cost.py`, one run):

```
draw_only          none=2.550 (1.00x)  seed=2.650 (1.04x)  seed_d0=2.550 (1.00x)
draw_read          none=25.100 (1.00x)  seed=72.500 (2.89x)  seed_d0=71.300 (2.84x)
per_draw_us        none=0.300 (1.00x)  seed=0.325 (1.08x)  seed_d0=0.350 (1.17x)
read_2d            none=0.000  seed=4.900  seed_d0=3.200
target per_draw_us ratio<=1.2: 1.08 PASS
target draw_read ratio<=2.0: 2.89 MISS
target read_2d abs<=0.5: 4.90 MISS
```

Per-draw cost went from 23.7x to 1.08x. The `draw_read` MISS is the same at
density 0 (2.84x), so the noise does not cause it. It comes from the flush walk,
at about 4 µs per op. The seeded excess is about 47 ms per 10 000 arcs. The read
accounts for at most about 5 ms of that (`read_2d` 4.9 ms), which leaves about
42 ms for the walk, roughly 1.9x stock's own RGBA raster. A cheaper read cannot
bring `draw_read` under 2x; only a cheaper walk can.

Export (W6): 3 fixups folded into sp3a, 38 commits, 0 fixup subjects, 0 dirty
(box HEAD 8ae478f98a). Only `patches/sp3a-canvas-noise.patch` changed. None of
its changed lines mention webgl, so Task 3's hunks are kept. Sync check: all 45
copied files identical.

### §7.1 Fix round 1 (review of 1282962..f74af3f)

Changes:
- `CamouMarkOp` returns first when the op's flags draw nothing. This covers
  shapes, images and pattern text; S2b had this guard. (Flagless ops have no
  flags to test.)
- An image or pattern text drawn under a looper (an opaque image's shadow)
  rasters a rect of its bounds with the shader-free looper flags and merges it
  `imported`. The area is bounded by the looper's layers, with each layer's blur
  outset applied in local and in device space, since a canvas shadow ignores the
  transform.
- A shadowed shape's shadow pass merges `aa` over the same tight area, no longer
  over the full clip.
- `CamouLayerArea`. A layer that carries bounds is marked over those bounds,
  grown by its filter, instead of over the clip. A translucent image's shadow is
  such a layer: `drawImage` puts it in a `SaveLayer` with bounds and a
  drop-shadow filter, so it never reaches the looper path. With only the looper
  fix, C44 still failed with the same values.
- Op bounds:
  - A plain fill uses its geometry bounds and converts no paint.
  - Other paints are converted without their shader, so a pattern is no longer
    converted to a picture just for bounds.
  - Bounds are taken from the coverage flags, which drops one full flags copy.
- The heavy header includes are replaced by forward declarations of `SkCanvas`,
  `cc::PaintOp` and `cc::PlaybackParams`. The `.cc` includes `SkMaskFilter.h`
  and `SkPathEffect.h`.
- The coverage bitmap is released in `ResetInternal` (and so on context loss)
  and at offscreen `transferToImageBitmap`.
- Stale comments are fixed.

New rows: C43 (a globalAlpha 0 `drawImage` over an arc's region) and C44 (a
shadowed 10x10 `drawImage` far from an arc). Both pass iff the seeded region is
unchanged and the unconfigured one is too, with the vacuity guard that seeded A
differs from unconfigured A.

The first C43 draft drew the image over only part of the arc's edge. It passed on
the faulty build: at density 0.04, no noised pixel fell under the image. It was
rewritten to cover the whole region before any code went in.

RED, on the build before the fix (box 43bee01f87): `verify_sp3a` gives 49 PASS
and 2 FAIL.

```
FAIL  43 a globalAlpha 0 drawImage leaves a region's noise unchanged
FAIL  44 a shadowed drawImage elsewhere leaves a region's noise unchanged
      43 : seeded {'a': 1792132258, 'b': 1703964406, 'e': 78}, unconfigured {'a': 1703964406, 'b': 1703964406, 'e': 78}
      44 : seeded {'a': 2023189415, 'b': 2836762292, 'e': 78}, unconfigured {'a': 2836762292, 'b': 2836762292, 'e': 78}
```

GREEN:
- The final build reports 27 steps (non-zero), and the unit filters pass (70
  tests). Earlier builds in this round reported 332 and 37 steps.
- `verify_sp3a`: 51 PASS, ALL_PASS, rc=0. Rerun on the same build against the
  52-row script (Task 5's C45 landed meanwhile): 52 PASS, ALL_PASS, rc=0.
- `verify_review`: 12/12.
- The shadowed-text probe passes.
- The leftover-symbol grep prints nothing.
- `gn check` reports OK for core, canvas and webgl, and `checkdeps` exits 0 on
  the three directories.

Cost (`measure_canvas_cost.py`, with the new `shadow_read` arm, which is
reported only):

```
draw_only          none=2.600 (1.00x)  seed=2.250 (0.87x)  seed_d0=2.650 (1.02x)
draw_read          none=25.500 (1.00x)  seed=68.950 (2.70x)  seed_d0=69.600 (2.73x)
per_draw_us        none=0.325 (1.00x)  seed=0.300 (0.92x)  seed_d0=0.350 (1.08x)
read_2d            none=0.000  seed=0.000  seed_d0=0.000
shadow_read        none=6.050 (1.00x)  seed=18.350 (3.03x)  seed_d0=18.050 (2.98x)
target per_draw_us ratio<=1.2: 0.92 PASS
target draw_read ratio<=2.0: 2.70 MISS
target read_2d abs<=0.5: 0.00 PASS
```

The `draw_read` MISS remains: 2.70x seeded, 2.73x at density 0. The walk still
costs about 4.3 µs per arc, so the per-op cuts did not move it. The drop from
2.89x (§7) came from Task 5's regional read (`read_2d` 4.9 ms → 0), not from these
cuts. How the walk's time splits between erase, A8 raster and `Merge` was not
profiled in this round; §7.2 measures it. `shadow_read` (1000 shadowed 12x12 rects plus one read) is 3.0x, with
density 0 the same.

Export (W6): 3 fixups folded into sp3a. The branch keeps 38 commits, with 0
fixup subjects and 0 dirty files (box HEAD bf93a2cfcd). Only
`patches/sp3a-canvas-noise.patch` changed, and none of its changed lines mention
webgl. Sync check: all 45 copied files identical.

### §7.2 Fix round 2 (re-review of f74af3f..bded7a6)

Changes:
- A shadowed draw that paints nothing marks nothing. The looper-stripped
  `nothingToDraw()` test now runs before every branch of `CamouMarkOp`, so a
  shadowed `globalAlpha` 0 image or pattern text on the looper path is covered
  too. Before, only shapes were. The layer path is unchanged (parked: a canvas
  filter can paint from an empty layer).
- The looper path's foreground rect is anti-aliased. Its coverage is a superset
  of the image's own footprint on any raster.

New row C44b: C44's scene with an `{alpha:false}` source canvas. An opaque
image's shadow is a looper on the image's flags rather than a filtered layer, so
this row reaches `mark_imported`'s looper branch, which C44 does not.

RED, under a mutant that restores the clip mark in that branch (box 08cedc9fe1;
build 355 steps): `verify_sp3a` gives 52 PASS and 1 FAIL. The mutant was then
reverted.

```
FAIL  44b a shadowed opaque drawImage elsewhere leaves a region's noise unchanged
      44b: seeded {'a': 2023189415, 'b': 2836762292, 'e': 78}, unconfigured {'a': 2836762292, 'b': 2836762292, 'e': 78}
```

Profile (temporary timers around erase, A8 raster and `Merge`; build 10 steps;
reverted before the real build, never committed). The arc bench is 10 flushes
of 10 000 arcs, seeded. Each flush reports the same split:

```
merges=10000 walk_us/op=4.38 erase=6% raster=70% merge=19% other=5%
```

The walk costs about 4.4 µs per arc. About 3.1 µs of that is the A8 coverage
raster (Skia's anti-aliased path fill, through `RasterWithFlags`). `Merge` is
19%, under the ruled 40% threshold, so it was not rewritten. Erase and the
remaining per-op work (flags copy, area) together are about 11%. Reaching ≤2x
would need a cheaper coverage raster; no further optimisation was done this
round.

GREEN (build 3 steps; unit filters 70 tests PASSED):
- `verify_sp3a`: 53 PASS, ALL_PASS, rc=0.
- `verify_review`: 12/12.
- The shadowed-text probe passes, and the leftover-symbol grep prints nothing.
- `gn check` is OK for core, canvas and webgl, and `checkdeps` exits 0 on the
  three directories.

Cost:

```
draw_only          none=2.650 (1.00x)  seed=2.450 (0.92x)  seed_d0=2.550 (0.96x)
draw_read          none=25.000 (1.00x)  seed=66.450 (2.66x)  seed_d0=68.050 (2.72x)
per_draw_us        none=0.325 (1.00x)  seed=0.325 (1.00x)  seed_d0=0.325 (1.00x)
read_2d            none=0.000  seed=0.050  seed_d0=0.000
shadow_read        none=6.000 (1.00x)  seed=18.500 (3.08x)  seed_d0=18.050 (3.01x)
target per_draw_us ratio<=1.2: 1.00 PASS
target draw_read ratio<=2.0: 2.66 MISS
target read_2d abs<=0.5: 0.05 PASS
```

Export (W6): 1 fixup folded into sp3a. The branch keeps 38 commits, with 0
fixup subjects and 0 dirty files (box HEAD b19bca9763). Only
`patches/sp3a-canvas-noise.patch` changed: its sha256 on the Mac after applying
the exported diff equals the box's (99eae632…). Sync check: all 45 copied files
identical.

### §6.2 Fix round 2 (re-review of 8d3baba..1282962)

C42 (new row, EXPECTED 48 to 49): WebGL2, `drawingBufferStorage(RGBA16F, 64, 64)`
with `EXT_color_buffer_float`, random opaque sentinels, a full and a sub-rect
`readPixels`; PASS iff seeded buffers are unchanged and `getError` equals the
unseeded arm's, which must itself leave the buffers unchanged. A missing API or
extension is an error row.

RED on the build with the round-1 code: `FAIL 42`; seeded `full` e=1282 n=308
(308 bytes of the page's buffer noised although GL rejected the read), `sub`
n=0, unconfigured n=0 for both. `verify_sp3a` otherwise 48 PASS.

C37 mutation on the shipped probe (`n = len` before the agree loop, so every
probe pixel "agrees"): `FAIL 37`, seeded `edgeDiff` 7, `opaqueDiff` 150;
unconfigured 0. Reverted by the fix build.

Fixes: the default framebuffer is noised only when `DrawingBuffer::StorageFormat()`
is `GL_RGBA8` or `GL_RGB8` (an allowlist: RGBA16F and SRGB8_ALPHA8 stay stock) and
READ_BUFFER is not NONE; the FBO extent first double-reads the pixel at
(ex1-1, ey1-1) and skips the row and column probes when it is inside; the lines
changed this round are clang-formatted (line ranges only).

GREEN: `verify_sp3a` 49 PASS, ALL_PASS, rc=0 (C37, C41, C42 and C17 to C20, C28,
C29, C35, C36, C38 PASS); `verify_review` 12/12; unit filters PASSED;
`checkdeps` on modules/webgl SUCCESS; `gn check` OK.

Cost (tree includes Task 4):

```
gl_edges.large     none=1.800 (1.00x)  seed=2.900 (1.61x)
gl_edges.small     none=0.280 (1.00x)  seed=0.570 (2.04x)
gl_fbo.large       none=1.800 (1.00x)  seed=4.600 (2.56x)
gl_fbo.small       none=0.280 (1.00x)  seed=1.120 (4.00x)
gl_flat.large      none=1.800 (1.00x)  seed=2.900 (1.61x)
gl_flat.small      none=0.290 (1.00x)  seed=0.590 (2.03x)
target gl_flat.large ratio<=3.0: 1.61 PASS
target gl_edges.large ratio<=3.0: 1.61 PASS
target gl_edges.small ratio<=1.5: 2.04 MISS
target gl_fbo.large ratio<=3.0: 2.56 PASS
```

`gl_fbo.small` went from 5.86x to 4.00x with the corner shortcut. `gl_fbo.large`
went from 1.94x to 2.56x: a read at the origin always has its far corner
outside, so the shortcut costs one extra probe pair there (a read whose rect
ends at the framebuffer edge cannot benefit); still under the 3x target.
`gl_edges.small` stays a MISS for the reason in §6.1 (one round trip).

Export: sp3a and sp3b regenerated; the other 77 files match the Mac tree by
short hash. Sync check: all 45 copied files identical. 38 commits.

## §8 Regional getImageData (Task 5)

`getImageData` noises only the returned rect plus a 1 px margin, on the
premultiplied snapshot, via `CanvasRenderingContext::CamouNoisedRegion`
(`NoisedCanvasRegion`). An empty region (no noise, whole field cached, failure)
falls back to `CamouNoised(snapshot)`.

RED, C39 mutant (`NoisedRegion` reading as `kUnpremul_SkAlphaType`, the floor
of 255 leaves translucent pixels clean). Build 357 steps.

```
FAIL  39 getImageData sub-rect equals the whole-snapshot field (full read and copy)
      39 : seeded {'dF': 0, 'dC': 7, 'trans': 640, 'tH': 59552103, 'e': 211}, unconfigured {'dF': 0, 'dC': 0, 'trans': 640, 'tH': 59552103, 'e': 211}
```

`dC > 0` and `tH` equals the unconfigured hash: the translucent pixels carry no
noise. The mutant also fails rows 21-26, 24a-d and 40 (38 PASS lines, 11 FAIL),
because every `getImageData` goes through the regional path and those rows read
noise at translucent anti-aliased pixels. So "every row but C39 passes under the
mutant" does not hold; C39 is the row that names the cause (`dC`).

GREEN, real code. Build 260 steps, 0 failed.

```
verify_sp3a            49/49 ALL_PASS (rc=0)
verify_review          12/12 ALL_PASS
components_unittests   PerturbRgba/CanvasNoise/NoisedImage/NoisedRegion/CanvasNoiseMask/Derive: PASSED
gn check               core, canvas, webgl: Header dependency check OK
checkdeps              canvas2d, core/html/canvas, modules/webgl: SUCCESS
```

Cost, lock held, no build running:

```
draw_only          none=2.500 (1.00x)  seed=2.550 (1.02x)  seed_d0=2.600 (1.04x)
draw_read          none=25.600 (1.00x)  seed=67.700 (2.64x)  seed_d0=68.600 (2.68x)
per_draw_us        none=0.325 (1.00x)  seed=0.300 (0.92x)  seed_d0=0.300 (0.92x)
read_2d            none=0.000  seed=0.000  seed_d0=0.000
target per_draw_us ratio<=1.2: 0.92 PASS
target draw_read ratio<=2.0: 2.64 MISS
target read_2d abs<=0.5: 0.00 PASS
target gl_flat.large ratio<=3.0: 1.56 PASS
target gl_edges.large ratio<=3.0: 1.51 PASS
target gl_edges.small ratio<=1.5: 2.00 MISS
target gl_fbo.large ratio<=3.0: 2.36 PASS
```

`read_2d` fell from 4.900 ms (section 7) to 0.000, which meets the 0.5 ms
target: the whole-snapshot noise pass is gone from the seeded read. `draw_read`
fell from 2.89x (72.5 ms) to 2.64x and stays a MISS. `draw_only` is 1.02x and
`read_2d` is 0.000, so drawing, snapshot, region allocation and read cost
nothing; the remainder is the flush-time `CamouMarkRecord` walk over the
10 000 recorded ops, as section 7 found. The cost reads at (0,0), where the
margin makes the region 2x2 and the noise kernel never runs, so these rows show
that no whole-canvas pass remains; they do not time the region arithmetic.

GPU caveat: on a texture-backed snapshot `GetSwSkImage()` reads back the whole
texture, so spec section 2 step 1 (read only the rect plus margin) cannot hold
there. `CamouNoisedRegion` returns empty for such a snapshot and the read keeps
the cached whole-snapshot route. The harness is CPU raster (SwiftShader), so the
accelerated path is not timed here.

Export: only `sp3a-canvas-noise.patch` changed (+78/-14); 38 commits, 0 fixups;
sync check: all 45 copied files identical.

### §8.1 Review fixes (Task 5 fix round 1)

- `CamouNoisedRegion` returns empty for a texture-backed snapshot and for a rect
  that contains the whole canvas (both keep the cached whole-snapshot route);
  `getImageData` skips the whole-snapshot fallback when the rect misses the
  canvas (the zero buffer is as stock); `<algorithm>` added; one over-long line
  wrapped.
- C45 added (`EXPECTED` 52): rects that cross the canvas edge (`(-5,-7,30,30)`,
  `(50,50,30,30)` on 64x64, `(40,40,-30,-30)`, a 1x1 at `(63,63)`), each compared
  with the full read (zero outside) and with the same rect of a `drawImage`
  copy. The rects are read before the full read and the copy: a whole-canvas
  read now fills the cache, and a read after it never reaches the regional path
  (a first C45 draft passed under the mutant for that reason; C39 had the same
  order and was re-ordered too).
- RED, mutant passing `sx, sy` instead of `std::min(sx, 0), std::min(sy, 0)`
  (build 356 steps): 47 PASS, FAIL on 21, 23, 26, 39 and 45.

```
45 : seeded {'dF': 2667, 'dC': 2667, 'cnt': 10804, 'tH': 2408886152, 'e': 234}, unconfigured {'dF': 0, 'dC': 0, 'cnt': 10804, 'tH': 3628699251, 'e': 234}
```

- GREEN, real code (build 3 steps): `verify_sp3a` 52/52 ALL_PASS, `verify_review`
  12/12 ALL_PASS, unit filter PASSED, `gn check` OK for core, canvas and webgl,
  `checkdeps` SUCCESS for canvas2d, core/html/canvas and modules/webgl.
- Cost (tree includes Task 4's fix):

```
draw_only          none=2.400 (1.00x)  seed=2.500 (1.04x)  seed_d0=2.550 (1.06x)
draw_read          none=25.550 (1.00x)  seed=67.100 (2.63x)  seed_d0=69.050 (2.70x)
per_draw_us        none=0.300 (1.00x)  seed=0.350 (1.17x)  seed_d0=0.325 (1.08x)
read_2d            none=0.000  seed=0.000  seed_d0=0.000
shadow_read        none=6.000 (1.00x)  seed=18.400 (3.07x)  seed_d0=18.250 (3.04x)
target per_draw_us ratio<=1.2: 1.17 PASS
target draw_read ratio<=2.0: 2.63 MISS
target read_2d abs<=0.5: 0.00 PASS
target gl_flat.large ratio<=3.0: 1.56 PASS
target gl_edges.large ratio<=3.0: 1.68 PASS
target gl_edges.small ratio<=1.5: 2.03 MISS
target gl_fbo.large ratio<=3.0: 2.47 PASS
```

- Export: 38 commits, 0 fixups, only `sp3a-canvas-noise.patch` changed; sync
  check: all 45 copied files identical.

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
(`NoisedCanvasRegion`), for a CPU-backed snapshot. A texture-backed snapshot, a
rect that contains the whole canvas, and an empty region (no noise, whole field
cached, allocation failure) take the cached `CamouNoised(snapshot)` route; a rect
that misses the canvas skips the noise. See §8.1 for the final rules.

RED, C39 mutant (`NoisedRegion` reading as `kUnpremul_SkAlphaType`, the floor
of 255 leaves translucent pixels clean). Build 357 steps.

```
FAIL  39 getImageData sub-rect equals the whole-snapshot field (full read and copy)
      39 : seeded {'dF': 0, 'dC': 7, 'trans': 640, 'tH': 59552103, 'e': 211}, unconfigured {'dF': 0, 'dC': 0, 'trans': 640, 'tH': 59552103, 'e': 211}
```

`dC > 0` and `tH` equals the unconfigured hash: the translucent pixels carry no
noise. The mutant also fails rows 21-26, 24a-d and 40 (38 PASS lines, 11 FAIL),
because at that build every `getImageData` went through the regional path and
those rows read noise at translucent anti-aliased pixels. So "every row but C39
passes under the mutant" does not hold; C39 is the row that names the cause
(`dC`). An empty region falls back to the whole-snapshot route and is not a
failure; the later routing is in §8.1.

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

## §9 Windows (Task 6, 2026-10-08)

Tree `f8395ae` (box `FETCH_HEAD` equals the Mac HEAD). Native tree `D:\camou-win\chromium\src`,
`out\Release`. Base for the per-file copy: `8cf90b48f882`.

### §9.1 Per-file replacement (W12)

17 files. Every pre hash equals the box's hash of the same path at `8cf90b48` (no
mismatch). Every post hash equals the box's sha256 of the file at `camoucrome/s2c`.
Hashes are the first 12 hex digits.

| path | pre (= 8cf90b48) | post (= box) |
|---|---|---|
| components/camoucfg/canvas_noise.cc | 3fde66230f29 | 53a1f063920e |
| components/camoucfg/canvas_noise.h | 09df99eed862 | d9e533c41fc5 |
| components/camoucfg/canvas_noise_unittest.cc | d9ad24830ade | d7f3ff4bd105 |
| components/camoucfg/canvas_readback.cc | dcd7e0beb36d | 9e980f949c6c |
| components/camoucfg/canvas_readback.h | 0fb5e9d6233e | a52f59b91dde |
| components/camoucfg/canvas_readback_unittest.cc | 93e72828eb1c | 1ec3d5e9dc8c |
| components/camoucfg/derive.cc | 522293879052 | 8e882301a3f8 |
| components/camoucfg/derive.h | 3d274c761c2a | e71b7d30a50f |
| components/camoucfg/derive_unittest.cc | b9e7027c0a09 | fe3aaf9c2107 |
| core/html/canvas/canvas_rendering_context.cc | 15feef8cd3d2 | d00db65b46eb |
| core/html/canvas/canvas_rendering_context.h | c19792f73c7b | f3f3be187ef9 |
| modules/canvas/canvas2d/base_rendering_context_2d.cc | 4c7ee7e2cdf8 | 086fabd5fb03 |
| modules/canvas/canvas2d/canvas_2d_recorder_context.cc | 9dd8c7183fb2 | 43d382ea21a4 |
| modules/canvas/canvas2d/canvas_2d_recorder_context.h | 222b6950915d | 9c3effda82ff |
| modules/canvas/offscreencanvas2d/offscreen_canvas_rendering_context_2d.cc | 81fd661e42cc | f38a34087d1f |
| modules/webgl/webgl_rendering_context_base.cc | 413d51d2b1c4 | cff7fe9b7c24 |
| modules/webgl/webgl_rendering_context_base.h | 43956d64916b | d04a7a3a9191 |

(`third_party/blink/renderer/` is omitted from the Blink paths.)

### §9.2 Build

`s2c-1`: `Build Succeeded: 265 steps` (siso pruned the plan from 2312 to 265), `rc=0`, 361 s.

### §9.3 Calibration at density 0.04 (seeds 8)

Headless, attempt 1: S2 text 8 of 8 distinct, S2 shape 8 of 8, stock among neither. P3 and S1
were UNMEASURED ("no WebGL context in: stock", the host GPU flake) and rule 5 FAILED
(differ: shape, text, textBig) in the same attempt. Neither counts. Attempt 2 (all rows PASS):

```
S2 oracle text canvas varies (>=6 distinct)   8 distinct of 8, stock among them: False
S2 oracle shape canvas varies (all distinct)  8 distinct of 8, stock among them: False
```

Headed, attempt 1: the same lines, 9/9 PASS. The density was not moved.

### §9.4 Host runs (final)

| run | attempts | verdict |
|---|---|---|
| headless | 1 | 9/9 PASS (S2 text 8 of 8, S2 shape 8 of 8, rule 5 differ: []) |
| headed | 1 | 9/9 PASS (S2 text 8 of 8, S2 shape 8 of 8, rule 5 differ: []) |

### §9.5 Windows `verify_sp3a` on `chrome`

53 rows (C44b included): 47 PASS, 6 FAIL. The six are C2, C3, C4, C5, C10, C11, exactly the rows
that need the stock baseline. The script prints them as FAIL, not UNMEASURED, because
`baselines/content_shell-sp3a-stock-canvas.json` does not exist on the host (note:
`baseline load ... FileNotFoundError`; C11: `differ from unconfigured []`, colours `(1, 1)`,
`unconfigured clear == stock baseline False`). Read them as UNMEASURED. All other rows,
C1, C6-C9, C12-C45 including C24a-d, C33a-e and C44b, PASS.

### §9.6 Regression verifies

- `verify_windows_client.py`: `11 PASS 0 FAIL`.
- `verify_sp6b_driver.py`: `ALL_PASS`.

### §9.7 Step 2 re-measure (run `20261008-200955`, 0 errors)

- `noise.canvas2d` 1 and `noise.webgl` 1, fork and control, headed and headless.
- Oracle `canvas.text` and `canvas.shape`: fork differs from control in both modes (expected).
- Linkability: no canvas leaf among the leaves the two fork identities share, headed and headless.
- Stability: 0 differing rows, headed and headless.
- CreepJS: the word "noise" does not appear in any of the four CreepJS captures (no `rgba noise`).

### §9.8 Final code (2026-10-08, after the final review fixes)

Lock `s2c windows 2`. Tree `c50865a` (box `FETCH_HEAD` equals the Mac HEAD).
W12 base `8cf90b48`. Box branch `camoucrome/s2c` at `0ef3ff9aa1`.

- **W12: 17 files.**
  - Every pre hash equals §9.1's post hash for the same path, so the native tree
    held exactly Task 6's state.
  - Every post hash equals the box's sha256 of the file at `camoucrome/s2c`.
  - 14 files changed: the eight `canvas_noise*`, `canvas_readback*` and
    `derive.{h,cc}` additions, `canvas_rendering_context.{h,cc}`,
    `base_rendering_context_2d.cc`, `canvas_2d_recorder_context.{h,cc}` and
    `webgl_rendering_context_base.cc`.
  - 3 were already equal: `derive_unittest.cc`,
    `offscreen_canvas_rendering_context_2d.cc` and
    `webgl_rendering_context_base.h`.
  - Post hashes, first 12 hex digits: `canvas_noise.cc` 9628415fd50f,
    `canvas_noise.h` 8e2506f8ac99, `canvas_noise_unittest.cc` 852318d58e72,
    `canvas_readback.cc` 4bb1925f26c6, `canvas_readback.h` a73056b25a29,
    `canvas_readback_unittest.cc` 6a3757bf7dc4, `derive.cc` 1270acb660d0,
    `derive.h` 9403b820726c, `canvas_rendering_context.cc` a485e0903acc,
    `canvas_rendering_context.h` 9144c9092cd2, `base_rendering_context_2d.cc`
    c1a9d70ba836, `canvas_2d_recorder_context.cc` f7d2a56977af,
    `canvas_2d_recorder_context.h` 857d72226cc9 and
    `webgl_rendering_context_base.cc` 26ee3c41cc98.
- **W9 `s2c-2`.** `Build Succeeded: 265 steps`, `rc=0`, 356 s.
- **`verify_sp3a` on `chrome`.** 57 rows: 51 PASS, 6 FAIL.
  - The six are C2, C3, C4, C5, C10 and C11, the rows that need the stock
    baseline missing on the host (note: `baseline load ... FileNotFoundError`).
    Count them as UNMEASURED.
  - Every other row passes, including C36b, C46, C46b and C47.
- **Host runs (W10).**

  | run | attempts | verdict |
  |---|---|---|
  | `s2c-final2-headless` | 2 | attempt 1: P3 and S1 UNMEASURED ("no WebGL context in: stock", the host GPU flake), and rule 5 FAIL (differ: `glClear`) in the same attempt, so it does not count; attempt 2: 9/9 PASS (S2 text 8 of 8, S2 shape 8 of 8, rule 5 differ: []) |
  | `s2c-final2-headed` | 1 | 9/9 PASS (S2 text 8 of 8, S2 shape 8 of 8, rule 5 differ: []) |

Calibration and Step 2 were not re-run (controller ruling): the field is
unchanged, and the gates only narrow which reads are noised.

## §10 Gaps

### Closed by S2c

- The draw-time timing tell: `per_draw_us` 23.7x to 0.93x (final run, §12.6; 1.00x,
  1.08x and 1.17x in other runs, within the timer's quantum).
- The full-canvas noise pass behind a 1x1 `getImageData`: `read_2d` 9.4 ms to below
  the timer's resolution (§8, §12).
- The `readPixels` copies and strips: `gl_flat.large` 21.3x to 1.37x, `gl_edges.large` 24.6x to 1.44x (§6, §12.6).
- Framebuffer reads, user framebuffers included: C35 to C37 (§6).
- `texImage2D` from a WebGL canvas: C38.
- Review triage item 23 (`readPixels` skipped user framebuffers).
- Found and closed during execution: C41 (`READ_BUFFER` NONE), C42 (a non-8-bit
  drawing buffer), C43 (transparent `drawImage`), C44 and C44b (shadowed
  `drawImage`), C45 (edge-crossing `getImageData`).
- Closed by the final review fixes (§12): C46 and C46b (a non-8-bit page
  framebuffer reads as stock), C47 (an `SRGB8_ALPHA8` drawing buffer is noised),
  C36b (framebuffer reads crossing the far edge or the origin), and the GPU
  readback a float16 or `RGBA16F` snapshot paid for nothing.

### Remaining cost targets

- `draw_read` is 2.64x in the final run (§12.6) against <= 2x: a MISS. The
  flush walk costs about 4.4 us per op: coverage raster 70%, `Merge` 19%, erase
  6% (§7.2). The next lever is a cheaper A8 coverage raster.
- `gl_edges.small` is 2.00x against <= 1.5x: a MISS. Each read needs one extra
  round trip for the margin, and dropping it would break the C36 sub-rect
  equality.
- `shadow_read` is about 3x, with no target.
- `gl_fbo.large` is 4.16x against the adopted <= 3x: an **accepted MISS**
  (controller ruling, final fix round 2, §12.6). It was 2.47x before the final
  review's format gate. Cutting the gate from four queries to two (G and B)
  moved `gl_fbo.small` from 6.6x to 5.3x (no target) but left `gl_fbo.large`
  at 4.16x, so the large read's extra time does not scale with the query count;
  its cause was not isolated. No further optimisation in this slice.
- **Possible timing tell: a page-framebuffer read against a default-framebuffer
  read of the same size.** Stock reads both in about the same time
  (1.9 / 1.8 ms large, 0.29 / 0.295 ms small: about 1.0x). Seeded, the
  framebuffer read takes 7.9 ms against 2.6 ms (3.0x) large and 1.545 ms
  against 0.59 ms (2.6x) small (§12.6 run). A page that times both reads can see
  the gap.
- The GPU (texture-backed) `getImageData` is not regional and is not measurable
  on the box (CPU raster).
- The noise cache holds two full-canvas copies: the held source snapshot and
  the noised raster image (`camou_noised_source_`, `camou_noised_`).

### Remaining behaviour (from the spec's known gaps)

- GPU picking, GPGPU through RGBA8, the float framebuffer bypass and
  `PIXEL_PACK_BUFFER` reads stay as the spec records them.
- A flipped copy of a WebGL canvas hashes its patches in mirrored order.
- A 2D canvas uploaded to WebGL is noised twice on readback.
- The flush gets one coverage pass more, and a framebuffer read costs extra
  probe reads (the cost rows above).
- `transferToImageBitmap` and the offscreen `convertToBlob` return un-noised
  images (found by the recon).
- Every S2b gap this section does not name stays as S2b section 8 records it.

### Parked from the reviews

- A shadowed translucent `drawImage` at `globalAlpha` 0 still marks its layer
  area. Parked because a canvas filter can paint from an empty layer.
- Task 4 review: m1 (a layer `DrawRecordOp` has no text carve-out; it is
  flag-gated), m2 (a layer raster decodes images), m3 (`ResetAlphaIfNeeded`
  `kDstOver` marks aa).
- C41's full-read case was never RED with the random sentinel; the sub-read
  case was.
- C45's corner 1x1 is an edge pixel, so it checks geometry only.

## §11 Landing (recorded, not executed)

`build-verify` builds `~/chromium/src` on `camoucrome/main`, so that branch must
carry the S2c commits before the PR merges. Facts as of 2026-10-08:

- Observe has landed on `origin/main` (PR #29, `5e04a67`): it added
  `patches/observe.patch` and a line in `patches/series`. `s2c/canvas-cost`
  branched from `cd21e14`, before that.
- Box `camoucrome/main` is `5c80c86e19`: the "observe" commit, amended for
  fast-calls, on top of `8cf90b48`. camoucrome-80 has not yet opened a PR for
  that amendment.

**Gate (final review I2).** Landing waits until box `camoucrome/main`'s observe
commit equals `origin/main`'s `patches/observe.patch`, that is, until
camoucrome-80's observe-fastcall PR has merged. Until then the export in step
2 would regenerate `patches/observe.patch` from the amended commit and ship
the fast-call amendment inside the S2c PR, unreviewed. Check after step 2's
export and before step 3's commit: `git diff origin/main -- patches/observe.patch`
is empty.

Landing path (the observe-landed branch of the plan):

1. In `~/chromium/src`, under the build lock and with camoucrome-80's agreement:
   `git rebase --onto camoucrome/s2c 8cf90b48f882cdcb28415309e8cca4dedc55de40 camoucrome/main`.
2. Build `out/Default` (its `args.gn` now has `camou_observe = true`
   permanently), run the sync check, and export from `camoucrome/main`.
3. Merge `origin/main` into `s2c/canvas-cost` and commit that export, so the
   PR's `patches/` carries both S2c and observe and equals the export.

If S2c were to land first instead, `camoucrome/main` would be fast-forwarded to
`camoucrome/s2c` and camoucrome-80's cherry-pick rebased onto it.

Both moves rewrite a shared ref. Neither runs without the owner's explicit
go-ahead at PR time.

## §12 Final review fixes (2026-10-08)

The final whole-branch review (`cd21e14..229047f`) found C1, I1 to I3 and M1 to
M8. The rulings: C1 gates page-framebuffer noise on 8-bit RGB(A); I1 adds
`SRGB8_ALPHA8` to the default allowlist; I2 gates landing (§11); I3 checks the
colour type before readback and lists the cache's two copies (§10); M1 to M7 are
fixed below; M8 (squashing the temporary chore commits) waits for the owner's
consent at finish. Lock `s2c final fix`, box workdir `~/chromium-s2c/src`.

### §12.1 RED on the build before the fix (229047f's box state)

Run 1 (rows at `d822a6e`):
```
FAIL  36b framebuffer reads crossing the far edge or the origin equal the full read's part
FAIL  46 R8 / RG8 framebuffer reads stay stock (G and B stay 0)
FAIL  46b RGBA4 renderbuffer framebuffer read stays stock
FAIL  47 SRGB8_ALPHA8 drawing buffer readPixels noised and deterministic
      36b: seeded {'diff': [0, 0, 0], 'h': [935700742, 1762808747, 637147551], 'glerr': 0}, unconfigured {'diff': [0, 0, 0], 'h': [2282948631, 1762808747, 916232254], 'glerr': 0}
      46 : seeded {'r8': 18420777, 'rg8': 1062882497, 'rgba8': 253762718, 'stray': 59, 'glerr': 0, 'e8': 1440, 'eg': 1442}, unconfigured {'r8': 574357477, 'rg8': 3090373005, 'rgba8': 1133855933, 'stray': 0, 'glerr': 0, 'e8': 1442, 'eg': 1442}
      46b: seeded {'h': 2669758751, 'g': 253762718, 'e': 122, 'glerr': 0}, unconfigured {'h': 2215030102, 'g': 1133855933, 'e': 122, 'glerr': 0}
      47 : seeded {'h': 3750901543, 'same': True, 'e': 1503, 'glerr': 0}, unconfigured {'h': 3750901543, 'same': True, 'e': 1503, 'glerr': 0}
```
- C46: 59 pixels of the R8 and RG8 reads came back with a non-zero `G` or `B`,
  a value stock cannot return.
- C46b: the RGBA4 read differs from unconfigured.
- C47: the `SRGB8_ALPHA8` read equals unconfigured, so it is clean.
- C36b's equality held (`diff` 0 on every rect, both arms). Its guard failed
  vacuously: the far-edge rect `(40,40,40,40)` held no noised pixel (the second
  hash is equal across arms). The rect moved to `(24,24,48,48)` (`007eb32`).
  Run 2 on the same build: C36b PASS, the other three FAIL as above. C36b is a
  guard, as the ruling allowed.

### §12.2 The fix

- **C1.** `CamouNoiseReadPixels` stops a page-framebuffer read unless the read
  attachment has R, G and B of 8 bits and A of 8 or 0. In WebGL2 it asks
  `GetFramebufferAttachmentParameteriv(GL_READ_FRAMEBUFFER, <read buffer>,
  GL_FRAMEBUFFER_ATTACHMENT_*_SIZE)`. In WebGL1 it asks `GetIntegerv(GL_*_BITS)`:
  the command buffer accepts it, and it reads the bound framebuffer. The proof is
  C35 to C37 still noising an RGBA8 texture framebuffer while C46b's RGBA4 one
  stays stock. A `NONE` read buffer or a missing attachment returns before any
  query. The queries stop at the first size that fails.
- **I1.** `GL_SRGB8_ALPHA8` joins `GL_RGBA8` and `GL_RGB8` in the default
  framebuffer's allowlist.
- **I3.** `CamouNoised` and `CamouNoisedRegion` read
  `PaintImageForCurrentFrame().GetColorType()` and return before
  `GetSwSkImage()` unless it is `RGBA_8888` or `BGRA_8888`. The readback
  allocates with the same `SkImageInfo`, so the output is byte-identical. The
  saved GPU readback is not measurable on the box (CPU raster).
- **M6.** `NoisedRegionTest.EqualsTheWholeImageField` asserts that the whole
  field changed at least one pixel. The new `NoisedRegionTest.OffCanvasRectIsEmpty`
  checks four wholly off-canvas rects.
- **M7.** clang-format ran in line-range mode over the lines S2c changed against
  `8cf90b48` in 17 files. In `webgl_rendering_context_base.cc` only the hook's
  ranges were formatted: the include block there holds `sp3b-webgl-profile`'s
  lines, which clang-format would have moved. The `cells ==` line break in
  `canvas_noise.h` was reflowed by hand (W4 runner). No added line over 80
  columns remains, apart from `#include` lines and diff headers.

### §12.3 Builds and GREEN

Windows (§9) was not rebuilt or re-run for these fixes; §9 describes the build
before them. The WebGL1 query's support was established by the rows' behaviour
(C35 to C37 and C46b's RGBA8 guard noised, RGBA4 stock, `glerr` 0 in both
arms), not by reading the command-buffer client.

- Build `Build Succeeded: 354 steps` (8 m 11 s, rc 0); after the comment reflow,
  `Build Succeeded: 207 steps` (5 m 57 s, rc 0).
- `verify_sp3a` 57/57 `ALL_PASS` (rc 0), including
  `PASS 36b`, `PASS 46`, `PASS 46b`, `PASS 47`, with every `glerr` 0 in both arms.
- `verify_review_2026_09_24` 12/12 `ALL_PASS`.
- Unit filter `PerturbRgba*:CanvasNoise*:NoisedImage*:NoisedRegion*:CanvasNoiseMask*:Derive*`:
  71 tests, `SUCCESS: all tests passed`.
- `gn check out/Default <target>`: `Header dependency check OK` for
  `//third_party/blink/renderer/core:core`, `modules/canvas:canvas`,
  `modules/webgl:webgl` and `//components/camoucfg:camoucfg`.
- `checkdeps.py <dir>`: no violation reported for `modules/canvas`,
  `core/html/canvas`, `modules/webgl` and `components/camoucfg`.

### §12.4 Cost (W5c, two runs, no build running)

| case | run 1 seeded | run 2 seeded | target |
|---|---|---|---|
| per_draw_us | 1.00x | 1.08x | <=1.2 PASS |
| draw_read | 2.69x | 2.70x | <=2 MISS |
| read_2d | 0.000 ms | 0.000 ms | <=0.5 PASS (below the timer) |
| read_2d_mid | 0.000 ms | 0.000 ms | reported only |
| gl_flat.large | 1.61x | 1.53x | <=3 PASS |
| gl_edges.large | 1.67x | 1.56x | <=3 PASS |
| gl_edges.small | 2.04x | 2.07x | <=1.5 MISS |
| gl_fbo.large | 4.16x | 4.21x | <=3 MISS (adopted) |
| gl_fbo.small | 6.83x | 6.63x | none |
| shadow_read | 2.98x | 2.99x | none |

Run 2 (the four-query gate; §12.6 is the run §10 and the S2b document now cite):
```
gl_fbo.large       none=1.900 (1.00x)  seed=8.000 (4.21x)  seed_d0=6.800 (3.58x)
gl_fbo.small       none=0.300 (1.00x)  seed=1.990 (6.63x)  seed_d0=1.980 (6.60x)
per_draw_us        none=0.325 (1.00x)  seed=0.350 (1.08x)  seed_d0=0.325 (1.00x)
draw_read          none=25.050 (1.00x)  seed=67.650 (2.70x)  seed_d0=67.950 (2.71x)
```
- `gl_fbo.*` regressed from 2.47x and 4x with the four-query format gate. Round 2
  (§12.6) cut it to two queries: `gl_fbo.small` improved, `gl_fbo.large` did not.
- **Resolution (M5).** A 1x1 `getImageData` at `(0,0)` never runs the kernel: its
  region is 2x2, below the 3x3 a pixel needs. `read_2d_mid` reads `(512,512)`,
  where the kernel runs on a 3x3. Its median is also 0.000, which is below the
  timer's resolution, not free.
- `per_draw_us` medians move in steps of about 0.025 to 0.05 us (a 0.1 ms timer over
  2000 draws; the median of an even sample can fall halfway).
  Runs gave 0.92x, 1.00x, 1.08x and 1.17x, so the 1.2 target is decided within one
  quantum.

### §12.5 Export

W6 folded the edits: Blink files into `sp3a-canvas-noise`, the `canvas_noise*` and
`canvas_readback*` files into `windows-behaviour-ii`, and `derive.*` into
`d-android-touch-invariant`. The rebase ran with no conflict. The result: 38
commits, 0 fixups, 0 dirty files, HEAD `248ce530ae`.

The export changed 10 files: the eight additions above, `sp3a-canvas-noise.patch`
and `sp3b-webgl-profile.patch`. The sp3b change is its `index` line and 14 hunk
headers only, shifted by sp3a's new lines. The sync check passed: all 45 copied
files are identical in the repo and the checkout. The tarball's sha256
(`dabb2973...ee9e8`) matched on the box and the Mac.

### §12.6 Round 2: the G and B gate (controller ruling)

The ruling: the gate queries only the G and B sizes. Among the formats GL reads
as `RGBA`/`UNSIGNED_BYTE`, G and B both being 8 bits holds exactly for `RGBA8`,
`RGB8` and `SRGB8_ALPHA8`. `R8`, `RG8`, `RGBA4`, `RGB5_A1`, `RGB565` and
`RGB10_A2` all fail it. The code comment says so. Two synchronous queries remain
per seeded page-framebuffer read. The edit went through the W4 runner;
clang-format changed nothing.

- Build: `Build Succeeded: 354 steps` (7 m 39 s, rc 0). The rebase in §12.5's
  export had touched file mtimes, so this was more than the one file.
- `verify_sp3a` 57/57 `ALL_PASS`, with `PASS 36b`, `PASS 46`, `PASS 46b` and
  `PASS 47`. `verify_review_2026_09_24` 12/12 `ALL_PASS`.
- Unit filter: 71/71, `SUCCESS: all tests passed`.
- `gn check //third_party/blink/renderer/modules/webgl:webgl`: `Header dependency
  check OK`. `checkdeps` on `modules/webgl` reported nothing.
- W6: the edit was folded into `sp3a-canvas-noise`; 38 commits, 0 fixups, 0
  dirty, HEAD `0ef3ff9aa1`; sync check 45/45. The export changed
  `sp3a-canvas-noise.patch` (the gate) and `sp3b-webgl-profile.patch` (its
  `index` line only). The tarball sha256 `7a08ae78...50cef` matched on both
  sides; committed as `c50865a`.

Cost (W5c, after the verifies, no build running):
```
gl_fbo.large       none=1.900 (1.00x)  seed=7.900 (4.16x)  seed_d0=6.600 (3.47x)
gl_fbo.small       none=0.290 (1.00x)  seed=1.545 (5.33x)  seed_d0=1.545 (5.33x)
gl_edges.large     none=1.800 (1.00x)  seed=2.600 (1.44x)  seed_d0=1.900 (1.06x)
gl_edges.small     none=0.295 (1.00x)  seed=0.590 (2.00x)  seed_d0=0.580 (1.97x)
gl_flat.large      none=1.900 (1.00x)  seed=2.600 (1.37x)  seed_d0=1.800 (0.95x)
draw_read          none=25.350 (1.00x)  seed=67.000 (2.64x)  seed_d0=67.950 (2.68x)
per_draw_us        none=0.350 (1.00x)  seed=0.325 (0.93x)  seed_d0=0.325 (0.93x)
read_2d_mid        none=0.000  seed=0.050  seed_d0=0.000
shadow_read        none=6.100 (1.00x)  seed=18.150 (2.98x)  seed_d0=18.450 (3.02x)
target per_draw_us ratio<=1.2: 0.93 PASS
target draw_read ratio<=2.0: 2.64 MISS
target read_2d abs<=0.5: 0.00 PASS
target gl_flat.large ratio<=3.0: 1.37 PASS
target gl_edges.large ratio<=3.0: 1.44 PASS
target gl_edges.small ratio<=1.5: 2.00 MISS
target gl_fbo.large ratio<=3.0: 4.16 MISS
```
`gl_fbo.large` stays above 3x and is recorded as an accepted MISS in §10, with
the framebuffer-against-default-framebuffer ratio as a possible timing tell.

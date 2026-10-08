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
density 0 (2.84x), so it comes from the flush walk and the whole-snapshot read,
not from the noise. `read_2d` is Task 5's target.

Export (W6): 3 fixups folded into sp3a, 38 commits, 0 fixup subjects, 0 dirty
(box HEAD 8ae478f98a). Only `patches/sp3a-canvas-noise.patch` changed. None of
its changed lines mention webgl, so Task 3's hunks are kept. Sync check: all 45
copied files identical.

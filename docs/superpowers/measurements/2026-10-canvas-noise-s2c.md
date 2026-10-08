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

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

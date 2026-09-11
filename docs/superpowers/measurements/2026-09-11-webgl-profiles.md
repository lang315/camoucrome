# WebGL profile database (A3 #2): two real GPUs, measured on chrome

Spec: `specs/2026-09-11-open-items-design.md` §3. The block on this row
was "needs captures on real hardware on the OS they claim". Two were
found in reach on 2026-09-11: the build box's **Windows 10 host** has
stock Google Chrome **153.0.8010.36** (the pinned tag) on an Intel UHD
Graphics 630, reachable over `ssh buildpc` (PowerShell), and the Mac's
stock Chrome 151 exposes its Apple M1 Pro to WebGL when launched headed
(headless gives no context, measured in the catalogue).

## 1. Captures (`scripts/capture_webgl_profile.py`, `settings/webgl/`)

One page reads both contexts: every numeric `getParameter` pname in the
WebGL and WebGL2 IDL tables (24 + 28 names, enumerated by name in the
script, plus the anisotropy and draw-buffers extension pnames),
`getSupportedExtensions()`, the 12 `getShaderPrecisionFormat` cells and
`getContextAttributes()`. String pnames are identity, held by
vendor/renderer. A SwiftShader renderer is refused as a profile (RED kept:
the box's `out/Default` chrome is refused with its
`ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) …)` string).

| id | binary | renderer | pnames (gl/gl2) | extensions (gl/gl2) | how |
|---|---|---|---|---|---|
| `windows-intel-uhd-630-d3d11` | Google Chrome 153.0.8010.36, Windows 10 host, temp profile, `--dump-dom` | `ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00009BC5) Direct3D11 vs_5_0 ps_5_0, D3D11)` | 27 / 53 | 35 / 32 | headless; the first attempt `--headless=new --use-angle=d3d11` gave **no context** in the ssh session, `--use-gl=angle --use-angle=d3d11` gave the Intel string |
| `macos-apple-m1-pro-metal` | Google Chrome 151.0.7922.138, the Mac, headed 300×200 window closed after the read | `ANGLE (Apple, ANGLE Metal Renderer: Apple M1 Pro, Unspecified Version)` | 27 / 53 | 39 / 36 | provenance names the milestone; the string format is byte-identical to what the catalogue documents for 153 |

The Windows string's device id is `0x00009BC5` (this host's UHD 630
stepping), not the `0x00003E92` the spec guessed; the profile carries what
the GPU said.

## 2. Generator

`gen.py --gpu <id>` selects a profile; absent, the first profile whose
`os` equals the claimed OS; an OS with no profile (Linux today) gets no
`webGl:*`. Emitted: `webGl:vendor/renderer`, `webGl2:vendor/renderer`,
`webGl:parameters`/`webGl2:parameters`, `webGl:supportedExtensions`/
`webGl2:supportedExtensions`, and `webGl:shaderPrecisionFormats`/
`webGl2:shaderPrecisionFormats` (keyed `"<shadertype>:<precisiontype>"` as
the key's doc says). `contextAttributes` stay unemitted: they agreed with
the host in every cell (§3).

## 3. Verify (`scripts/verify_webgl_profile.py`, chrome through the probe)

| row | result |
|---|---|
| W1 no config: the host's SwiftShader renderer and limits | PASS (RED by construction) |
| W2 Windows profile on a Windows claim: identity, every parameter, extension set equal **and** `getExtension(name)` non-null for every claimed name, 12 precision cells, both contexts, strict, zero `camoucfg:` lines | PASS |
| W3 macOS profile on a macOS claim: same | PASS |
| W3-RED macOS profile on a Windows claim refused under strict (`webgl-renderer-backend-fits-os`) | PASS |
| W4 host vs profile: `shaderPrecisionFormats` **8 of 12 cells differ** (both profiles), `contextAttributes` 0 | why precision formats are emitted |

`4 PASS 0 FAIL` twice (before and after the precision-format emission; the
first run's W4 note is what added it). Every claimed extension name is
backed by a non-null `getExtension` on the SwiftShader host, so the two
lists as captured ship unpruned.

## 4. Open, named

A database of two. AMD/NVIDIA D3D11 and Linux Mesa rows are one capture
each away (`capture_webgl_profile.py --where winhost|mac|box`); market-share
sampling (Camoufox's `webgl_data.db`) has no source here. The macOS
profile is a 151 capture; re-capture when the Mac's Chrome reaches 153.

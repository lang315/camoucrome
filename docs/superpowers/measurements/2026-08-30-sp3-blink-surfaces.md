# SP3 Blink surface measurements

Measured 2026-08-30 against `~/chromium/src` on the Windows/WSL build box.
Checkout HEAD `a727b57805` (spec §3 pinned `0e8d4a9268`; line numbers re-verified
below rather than trusted). Read-only `git grep`; no build required.

These resolve the "unverified — locate before implementing" flags the SP3 spec
carries in §3, §4.1 and §4.2, and fix the plan's interception points.

## M1 — Canvas snapshot chokepoint (`PaintRenderingResultsToSnapshot`)

Claim under test (§4.2): every page-reachable *snapshot* readback funnels through
one virtual, so noise applied once there covers `toDataURL` / `toBlob` /
`convertToBlob` and the async blob encoder, for every context type.

Result: **holds, with a correction to where the noise goes.**

- Virtual declared `core/html/canvas/canvas_rendering_context.h:199`.
- Overridden by every context type: `CanvasRenderingContext2D`,
  `OffscreenCanvasRenderingContext2D`, `ImageBitmapRenderingContext`,
  `WebGLRenderingContextBase`, `WebGLRenderingContextWebGPUBase`,
  `GPUCanvasContext`.
- Page-reachable callers (the funnel) are only four, in two files:
  - `core/html/canvas/html_canvas_element.cc:1256`, `:1312`, `:1923`
  - `core/offscreencanvas/offscreen_canvas.cc:386`

Correction to §4.2: because the method is per-context *overridden*, noise cannot
be applied "inside the virtual" once. Apply it at the **callers**, on the
returned `StaticBitmapImage`, after the snapshot and before encode. Four sites,
two files, covers all context types (WebGPU canvas included) and the async blob
path (which receives the already-snapshotted image).

## M5 — OffscreenCanvas element-side path

Spec §3 said `core/html/canvas/offscreen_canvas.cc` "does not exist — locate it."
Located: **`core/offscreencanvas/offscreen_canvas.cc`** (its `convertToBlob` path
is the `:386` caller in M1).

## M2 — Direct pixel-read path (no snapshot)

`getImageData` and `readPixels` copy into a caller buffer without a snapshot, so
they need their own interception on the destination buffer. Both have a single
internal chokepoint:

- `getImageData` → **`BaseRenderingContext2D::getImageDataInternal`**
  (`modules/canvas/canvas2d/base_rendering_context_2d.cc:358`). Both public
  overloads (`:336`, `:346`) route through it, and it lives on
  `BaseRenderingContext2D` so OffscreenCanvas 2D shares it — patching
  `CanvasRenderingContext2D` alone would have missed OffscreenCanvas (§3 note
  confirmed).
- `readPixels` → **`WebGLRenderingContextBase::readPixels`**
  (`modules/webgl/webgl_rendering_context_base.cc:5273`) →
  `ReadPixelsHelper` (`:5284`). Single point; both namespaces inherit it.

## M3 — WebGPU `GPUAdapterInfo` (§4.1 obligation, SP3 scope)

Present and populated. `modules/webgpu/gpu_adapter_info.h` declares getters
`vendor()`, `architecture()`, `device()`, `description()` (fields `vendor_`,
`architecture_`, …), constructed in `gpu_adapter_info.cc`. So the "WebGL strings
must agree with WebGPU adapter info" invariant (§5) is a real, locatable task,
not a hoped-for absence — interception at the `GPUAdapterInfo` construction /
getters, keyed by the same `webGl:` config so the answers agree.

## M4 — WebGL interception points (drift check)

Zero drift from the spec despite the HEAD move:

- `WebGLRenderingContextBase::getParameter` at `:3990` (spec: `:3990`).
- `case WebGLDebugRendererInfo::kUnmaskedRendererWebgl` at `:4201` (spec `:4201`).
- `kUnmaskedVendorWebgl` at `:4210` (spec `:4210`).

`webgl_rendering_context_base.cc` is stable across `0e8d4a9268..a727b57805`;
the other files' line numbers above are the current ones and supersede §3.

## Consequence for the plan

Structural claims all hold. Split stands: **SP3a** = canvas noise (four snapshot
callers + two direct-read chokepoints) + the shared `DeriveDelta` primitive;
**SP3b** = WebGL profile (getParameter/extensions/precision/attributes, both
namespaces) + WebGPU adapter coherence. §7.3 decided: position-based
`DeriveDelta`, content-hash folded into the per-canvas seed at the applier so
per-drawing shift and reread-determinism both hold.

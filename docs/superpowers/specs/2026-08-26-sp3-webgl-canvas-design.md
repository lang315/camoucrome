# SP3 — WebGL and canvas fingerprints

Status: draft, not yet approved.
Shared assumptions: see [00-conventions.md](00-conventions.md).

## 1. Goal

SP3 makes the two highest-entropy graphics fingerprints controllable from config: the
WebGL profile (the unmasked vendor and renderer strings plus the numeric parameter
table, extension list, shader precision formats, and context attributes, for both the
WebGL1 and WebGL2 namespaces) and the canvas readback hash (deterministic per-session
noise applied to pixels as they leave the canvas, without altering what is drawn on
screen). These two surfaces are what commercial fingerprinting libraries weight most
heavily, and unlike the navigator identity of SP1 they cannot be faked from JavaScript
without leaving an observable trace, so they are the clearest justification for the
whole C++-level approach.

## 2. Depends on

SP0 only, for `//components/camoucfg` and the `ScopeFor(execution_context)` accessor.
SP3 is independent of SP1 and SP2 and may be built in parallel with SP2.

SP3 deliberately does **not** depend on SP5. SP3 delivers the mechanism — every knob
individually settable — and ships a handful of real captured GPU profiles for its own
tests. Generating coherent profiles at scale is SP5's job. See §7.1.

## 3. Surfaces

All Blink paths below were verified against the checkout at `~/chromium/src`
(HEAD `0e8d4a9268`). Line numbers are from that revision and will drift.

### WebGL

| Surface | Config key | Location | Process |
|---|---|---|---|
| Unmasked renderer string | `webGl:renderer` | `modules/webgl/webgl_rendering_context_base.cc:4201` (`case WebGLDebugRendererInfo::kUnmaskedRendererWebgl`) | renderer |
| Unmasked vendor string | `webGl:vendor` | same file, `:4210` (`kUnmaskedVendorWebgl`) | renderer |
| Numeric / string parameter table | `webGl:parameters`, `webGl2:parameters` | `getParameter()` at `:3990` | renderer |
| Fail-closed for unlisted params | `webGl:parameters:blockIfNotDefined`, `webGl2:…` | same | renderer |
| Extension list | `webGl:supportedExtensions`, `webGl2:…` | `getSupportedExtensions()` at `:4524` | renderer |
| Shader precision | `webGl:shaderPrecisionFormats`, `webGl2:…` | `getShaderPrecisionFormat()` at `:4487` | renderer |
| Fail-closed for precision | `webGl:shaderPrecisionFormats:blockIfNotDefined`, `webGl2:…` | same | renderer |
| Context attributes | `webGl:contextAttributes`, `webGl2:…` | `getContextAttributes()` at `:3782` | renderer |

The `kUnmaskedVendorWebgl = 0x9245` / `kUnmaskedRendererWebgl = 0x9246` enum values are
declared in `modules/webgl/webgl_debug_renderer_info.h:40-41`. WebGL2 overrides live in
`modules/webgl/webgl2_rendering_context_base.cc`; both namespaces funnel through the
same `WebGLRenderingContextBase` methods, so a single interception point serves both,
with the `isWebGL2` discriminator selecting the `webGl:` or `webGl2:` key prefix.

The true values originate in the GPU process as `gpu::GPUInfo` — `gl_vendor`,
`gl_renderer`, `gl_version` at `gpu/config/gpu_info.h:365`, `:368`, `:362` — and are
shipped to the renderer. §4.1 analyses which side to intercept.

### Canvas

| Surface | Config key | Location | Process |
|---|---|---|---|
| Noise seed | `canvas:seed` | all readback sites | renderer |
| Anti-alias offset | `canvas:aaOffset` | readback | renderer |
| Cap the AA offset | `canvas:aaCapOffset` | readback | renderer |
| Fraction of pixels perturbed | `canvas:noiseDensity` | readback | renderer |
| Per-channel magnitude | `canvas:noiseStrength` | readback | renderer |

Page-reachable readback entry points, all verified:

| API | Location |
|---|---|
| `HTMLCanvasElement.toDataURL` | `core/html/canvas/html_canvas_element.cc:1380` |
| `HTMLCanvasElement.toBlob` | `core/html/canvas/html_canvas_element.cc:1404` |
| `getImageData` (two overloads) | `modules/canvas/canvas2d/base_rendering_context_2d.cc:336`, `:346` |
| `WebGLRenderingContextBase.readPixels` | `modules/webgl/webgl_rendering_context_base.cc:5273` |
| async blob encoding | `core/html/canvas/canvas_async_blob_creator.cc` |
| OffscreenCanvas 2D | `modules/canvas/offscreencanvas2d/offscreen_canvas_rendering_context_2d.cc` |

Note the correction to a common assumption: `getImageData` is implemented on
`BaseRenderingContext2D`, not on `CanvasRenderingContext2D`. Patching the latter would
silently miss OffscreenCanvas, which shares the base. `core/html/canvas/offscreen_canvas.cc`
does not exist at that path; the OffscreenCanvas element-side implementation is
elsewhere in the tree (unverified — locate before implementing).

There is a shared virtual that covers the snapshot-based paths:
`CanvasRenderingContext::PaintRenderingResultsToSnapshot`, declared at
`core/html/canvas/canvas_rendering_context.h:199`, returning a
`scoped_refptr<StaticBitmapImage>`. §4.2 uses this.

## 4. Design

### 4.1 Where to intercept WebGL: renderer or GPU process

The real GPU identity lives in the GPU process. Two interception points are possible.

**Renderer-side** means editing the Blink accessors listed in §3. Every WebGL entry
point a page can call funnels through `WebGLRenderingContextBase`, so this is one file
and a small number of call sites. It cannot destabilise rendering, because the GPU
process continues to receive true values and continues to make correct blocklist and
driver-workaround decisions. Its weakness is that it treats the symptom: the GPU
process still knows the truth, and any *other* page-visible API that reports GPU
identity from `gpu::GPUInfo` will contradict the spoofed WebGL strings.

**GPU-process-side** means substituting values into `gpu::GPUInfo` at or near
collection, so everything downstream inherits them. That is a single source of truth,
and it closes the leak class described above by construction. Its weakness is serious:
`GPUInfo` drives real decisions. Chromium consults the vendor and device IDs to apply
driver workarounds and to gate features. Feeding it a fabricated GPU changes which
workarounds apply, which changes actual rasterisation — and a canvas that rasterises
differently from the claimed GPU is precisely the fingerprint we are trying to
control. It can also simply break the browser on the host's real hardware.

**Recommendation: intercept renderer-side in SP3, and treat the leak class as a named,
tracked obligation rather than an accepted loss.** The decisive argument is that
GPU-process spoofing trades a presentation problem for a behaviour problem, and
behaviour differences are harder to detect in testing and more damaging when missed.
Renderer-side interception is reversible, contained, and verifiable.

The obligation that comes with that choice: SP3 must enumerate every *other*
page-reachable API that reports GPU identity and close each at its own Blink entry
point, using the same config keys so the answers agree. The one known candidate is
WebGPU — `GPUAdapterInfo` exposes vendor, architecture, device, and description to the
page (unverified: locate the Blink implementation and confirm which fields are
populated on this revision). **WebGPU is in SP3's scope, not SP4's.** §5 already makes
SP3 responsible for the invariant that WebGPU adapter identity agrees with the WebGL
strings, and an invariant whose implementer sits in a different sub-project is exactly
the ownership gap this project is trying to avoid. A page that reads an NVIDIA string
from WebGL and an Intel string from WebGPU has learned more than if neither were
spoofed. Media
Capabilities hardware-decode answers are a second candidate, but those belong to SP4's
codec work and must consume the same config.

If, after SP3 ships, a page-visible GPU identity leak is found that cannot be closed at
a Blink entry point, revisit GPU-process interception as a scoped follow-up. Record it
in §7.2 rather than pre-building for it.

### 4.2 Canvas noise: chokepoints, not entry points

The naive approach patches `toDataURL`, `toBlob`, `getImageData`, and `readPixels`
independently. That is four or more sites, it misses OffscreenCanvas and the async
blob encoder, and it has no structural defence against a future Chromium adding a
fifth readback path. The failure mode is silent: one unpatched path returns clean
pixels and the entire spoof is void.

Instead, apply noise at the narrowest set of chokepoints that provably covers every
page-reachable readback, and back that claim with a test that enumerates the APIs
rather than trusting the reading of the code.

Two chokepoints are needed, because readback splits into two mechanisms:

*Snapshot path.* `toDataURL`, `toBlob`, and the async blob creator all obtain a
`StaticBitmapImage` before encoding. `CanvasRenderingContext::PaintRenderingResultsToSnapshot`
(`canvas_rendering_context.h:199`) is a virtual shared by the 2D, WebGL, and
OffscreenCanvas contexts, which makes it the correct single point for this family
(unverified: confirm all three override or inherit it, and that no encode path bypasses
it).

*Direct pixel-read path.* `getImageData` on `BaseRenderingContext2D` and `readPixels`
on `WebGLRenderingContextBase` copy pixels into a caller-supplied buffer without
producing a snapshot. These need their own interception, applied to the destination
buffer after the copy completes.

Noise is applied **on readback only, never at draw time**. What is composited to the
screen stays byte-identical to a stock build. This matters for two reasons: it keeps
the visual result correct, and it prevents the noise from feeding back into subsequent
draws and compounding.

### 4.3 Determinism

The noise function is a pure function of the seed and the pixel's position, not a
draw-order-dependent or call-count-dependent value:

```
noise(seed, width, height, x, y, channel) -> int8 delta
```

That signature is canvas-specific. Underneath it sits a smaller, surface-agnostic
primitive that SP3 also ships and that other sub-projects consume:

```
derive_delta(seed, domain, index, bound) -> int32 delta in [-bound, +bound]
```

`domain` is a short constant string naming the caller (`"canvas"`, `"audio"`,
`"fontmetric"`) so that two surfaces sharing a seed still produce uncorrelated
sequences; `index` is any stable integer the caller can reproduce — a flattened pixel
offset, an audio sample number, a glyph id. `noise()` is a thin wrapper over it.

The split exists because SP4 needs the same determinism guarantee for data of a
different shape: audio readback is a one-dimensional sample stream and font metric
jitter is a per-glyph scalar, and neither fits a two-dimensional pixel signature. SP4
consumes `derive_delta` by that name and does not grow a second implementation. Both
live in `//components/camoucfg/`, so the dependency is on a shared utility rather than
on SP3's canvas code.

Reading the same canvas twice must yield identical bytes. A fingerprinting script that
hashes a canvas twice and gets two different hashes has learned that the browser is
lying, which is a stronger signal than the true hash would have been. This is the
single most important property in SP3 and every verification item in §6 that touches
canvas exists to defend it.

`canvas:noiseDensity` selects which pixels are perturbed (also derived from the seed
and position, so the selection is stable), `canvas:noiseStrength` bounds the per-channel
delta, and `canvas:aaOffset` with `canvas:aaCapOffset` carry over Camoufox's
anti-aliasing adjustment. When `canvas:seed` is absent, no noise is applied at all and
readback is byte-identical to stock, per conventions rule 5.

### 4.4 Worker parity comes free, for now

Conventions rule 3 requires a worker to report the same values as its window. Camoufox
needed a dedicated patch for this (`cross-process-storage.patch`, synchronous IPC for
`roverfox.*` prefs) because its per-BrowsingContext managers did not span processes.

Camoucrome gets parity structurally instead: the config arrives as environment
variables, and every child process inherits its parent's environment, so a dedicated
worker, a shared worker in its own process, and the document all parse the same
`CAMOU_CONFIG` and derive the same seed. No IPC is required.

This is a property of the SP0 transport, not of SP3, and it expires the moment a
per-context override channel is introduced. When that happens, worker parity becomes an
explicit obligation of that channel and the verification in §6.7 must be re-run. Record
the dependency here so it is not rediscovered the hard way.

### 4.5 `blockIfNotDefined` is a deliberate exception to conventions rule 5

Conventions rule 5 says a surface falls back to its real value when config is absent.
The WebGL parameter table is an explicit, opt-in exception, carried over from
Camoufox's `blockIfNotDefined` flag.

The reasoning: a *partial* GL profile is more detectable than either a complete one or
none at all. If `webGl:renderer` claims an Apple M2 while `MAX_TEXTURE_SIZE`,
`MAX_VIEWPORT_DIMS`, and the extension list still report the host's Intel UHD 630, the
contradiction is trivial to detect and proves deliberate spoofing. Blocking unlisted
parameters — returning the same error a real context returns for an unsupported enum —
is the lesser evil.

The flag is per-namespace and defaults to false, so the shared rule holds unless the
operator opts out. Conventions rule 5 sanctions exactly this exception and cites
`blockIfNotDefined` by name; what is specific to SP3, and the reason it is argued here,
is that the GL parameter table is a *set* whose members are only meaningful together.
Do not read the exception as licence to fail closed on surfaces where a real value is
merely inconvenient.

## 5. Coherence constraints

> **Enforced obligation (added from SP3b-ii Task 2 review):** the configured
> `webGl:supportedExtensions` / `webGl2:supportedExtensions` list MUST be a
> subset of the host's tracker-backed extensions. The Blink hook makes
> `getExtension(X)` non-null ⟹ X advertised (closed by construction), but it
> CANNOT make advertised ⟹ gettable — Blink cannot fabricate a WebGLExtension
> object without a real tracker. So a scraped profile advertising an extension
> the spoofing host lacks yields an advertised-but-ungettable tell in normal
> operation. This is not an operator typo; the profile generator / SP3b-iii
> coherence validator owns the `list ⊆ host-backed` constraint.

> **Deferred obligations for SP3b-iii (consolidated from the SP3b whole-branch
> reviews) — logged so nothing ships as a silent overclaim:**
> 1. `webGl:renderer` ↔ `webGl:vendor` all-or-nothing (a renderer without its
>    vendor is invalid) — parse-time rejection. SP3b-i exposes the knobs; the
>    validator enforces the pairing.
> 2. **Parameter-table array/type sanity** — `webGl:parameters` values are
>    returned as-typed with no arity/type check, so a garbage entry (a 3-element
>    MAX_VIEWPORT_DIMS, a string for MAX_TEXTURE_SIZE) yields a wrong-shaped
>    result. SP3b-i's plan promised this to "SP3b-ii's coherence validator";
>    SP3b-ii did not implement it (it only added exact-arity checks for its own
>    shaderPrecisionFormats surface), so it is re-deferred here explicitly.
> 3. `webGl:supportedExtensions` ⊆ host tracker-backed extensions (the
>    advertised⟹gettable ceiling above). Tighten "tracker-backed" to mean a
>    tracker whose own capability check also passes.
> 4. WebGPU (`GPUAdapterInfo`) adapter identity must agree with the WebGL
>    strings (spec §4.1 obligation) — the WebGPU hook + its coherence.
> 5. **WebGL-in-Worker (OffscreenCanvas) parity — VERIFIED (verify_sp3b V9).**
>    A dedicated-worker OffscreenCanvas `getParameter` returns the spoofed value
>    identically to the main thread (empirically: `webGl:parameters`
>    MAX_TEXTURE_SIZE reads 16384 in both, vs host 8192), confirming the six
>    hooks reach worker scope via `Host()->GetTopExecutionContext()` and the
>    context-agnostic `ScopeFor()` passthrough — NOT `GetDocument()`, the
>    pattern behind the font-spoofing worker bug. Remaining (SP3b-iii, minor): a
>    SHARED worker (own process) exercises the cross-process env-inheritance a
>    same-process dedicated worker does not — a fast-follow, not a blocker; it is
>    the same mechanism SP3a's canvas worker-parity (§6 item 7 / C8) proved.


| This surface | Must agree with | Invariant |
|---|---|---|
| `webGl:renderer` | `webGl:vendor` | Bound all-or-nothing, as Camoufox's `$__WEBGL` group does. A renderer string without its matching vendor is invalid config and must be rejected at parse time, not silently half-applied. |
| WebGL strings | `webGl:parameters` | Numeric limits must be those the claimed GPU actually reports. A mobile Mali renderer with desktop-class `MAX_TEXTURE_SIZE` is a dead giveaway. Enforced by shipping whole captured profiles, never hand-edited fields — see §7.1. |
| WebGL strings | `webGl:supportedExtensions` | The extension list is GPU- and driver-specific and must come from the same capture as the strings. |
| WebGL strings | WebGPU adapter info | Both report GPU identity to the page and must not contradict. See §4.1. |
| WebGL strings | `navigator.platform` / UA (SP1) | An Apple GPU on a claimed Windows platform is incoherent. SP3 cannot enforce this alone; it is SP5's cross-surface job. SP3's obligation is to expose the strings as config so SP5 *can* enforce it. |
| WebGL strings | Media Capabilities (SP4) | Hardware-decode answers should match the claimed GPU's real capabilities. |
| Canvas noise | WebGL `readPixels` noise | Both must derive from the same `canvas:seed`. Camoufox's canvas patch carries the same note. A 2D canvas and a WebGL canvas that disagree about how much noise the session applies is a tell. |
| Canvas noise | Worker canvas noise | Identical seed and identical output. See §4.4. |

## 6. Verification

Every item below runs against `content_shell` built from `out/Default`. Because the
WSL2 GPU stack is a virtualised D3D12 passthrough and reports values no normal Linux
machine would, all WebGL verification uses a forced software baseline so results are
reproducible and independent of the host GPU:

```
--use-angle=swiftshader --enable-unsafe-swiftshader
```

Both switch names are verified: `kUseANGLE` at `ui/gl/gl_switches.cc:93`,
`kANGLEImplementationSwiftShaderName` at `:46`, and `kEnableUnsafeSwiftShader` at
`:159`. The second is required on current Chromium to permit the SwiftShader fallback
at all; without it the first silently does nothing.

1. **Baseline is stable.** Launch with the SwiftShader switches and no `CAMOU_CONFIG`.
   Record `getParameter(0x9246)` and `getParameter(0x9245)`. Relaunch. The two runs
   must produce identical strings. If the baseline is not stable, no later assertion
   about spoofing means anything.
2. **Vendor and renderer substitute.** With `webGl:vendor` and `webGl:renderer` set,
   both `getParameter` calls return exactly the configured strings, and neither the
   SwiftShader baseline strings nor `UHD Graphics 630` appear anywhere in
   `JSON.stringify` of a full parameter sweep.
3. **Both namespaces.** Repeat item 2 against a `webgl2` context with `webGl2:` keys,
   and confirm a `webgl` context is unaffected by `webGl2:` keys and vice versa.
4. **Parameter table.** Set three parameters of different types (an integer such as
   `MAX_TEXTURE_SIZE`, a two-element array such as `MAX_VIEWPORT_DIMS`, and a string).
   Each returns the configured value with the correct JavaScript type — an array must
   arrive as a typed array, not as a plain array.
5. **Fail-closed.** With `webGl:parameters:blockIfNotDefined` true and a parameter
   deliberately omitted, `getParameter` for that enum returns the same value and raises
   the same GL error a real context raises for an unsupported enum. With the flag false,
   the same call returns the host's real value.
6. **Canvas determinism.** Draw a fixed scene, call `toDataURL()` twice in the same
   document, and assert the two strings are byte-identical. Then assert the same for
   `getImageData` called twice over the same rectangle. This is the highest-priority
   canvas test.
7. **Worker parity.** Render an identical scene on an `OffscreenCanvas` inside a
   dedicated worker and on an `HTMLCanvasElement` in the document, read both back, and
   assert identical bytes. Repeat with a shared worker, which runs in its own process
   and therefore actually exercises the environment-inheritance claim in §4.4.
8. **Every readback path is covered.** A single test page that exercises `toDataURL`,
   `toBlob`, `getImageData`, `readPixels`, the OffscreenCanvas equivalents, and
   `convertToBlob`, asserting that each differs from the stock build's output for the
   same scene. This test is the structural defence described in §4.2 and must be
   updated whenever Chromium is rebased.
9. **Noise is off by default.** With no `canvas:seed`, all readback output is
   byte-identical to a stock `content_shell` build rendering the same scene. Diff the
   two directly.
10. **Screen output unchanged.** A screenshot of the rendered canvas, captured through
    the DevTools protocol rather than through a canvas readback API, is identical
    between the spoofed and stock builds. This proves noise is applied at readback and
    not at draw time.
11. **Accessors stay native.** For `HTMLCanvasElement.prototype.toDataURL` and
    `WebGLRenderingContext.prototype.getParameter`,
    `Object.getOwnPropertyDescriptor(...).value.toString()` still contains
    `[native code]`, and `Object.keys(window)` is unchanged against stock. Conventions
    rule 2.
12. **No contradicting GPU identity.** Query `GPUAdapterInfo` on the same page and assert
    every populated field is consistent with the configured WebGL vendor and renderer —
    not merely that it fails to name the host GPU. Because §4.1 places WebGPU in SP3's
    scope, this item asserts a spoof SP3 implements, not an absence it hopes for. If
    WebGPU is unavailable in `content_shell` under SwiftShader, record that as a gap to
    be closed on the Windows host build rather than declaring the item passed.
13. **Seed domains are independent.** For one seed, assert that `derive_delta` produces
    uncorrelated sequences across the `"canvas"`, `"audio"` and `"fontmetric"` domains,
    and that each is reproducible across processes. A unit test suffices. SP4 depends on
    both properties, so they are established here rather than discovered there.

Items 1, 6, and 9 must pass before any other item is meaningful.

## 7. Open decisions

### 7.1 Where do real GPU profiles come from, and does SP3 need them?

Camoufox does not let an operator invent a GPU. It samples real vendor and renderer
pairs from a bundled database (`pythonlib/camoufox/webgl/sample.py`) so the strings are
always ones that some real device actually reports.

Camoucrome needs the same discipline, and needs it to extend further than Camoufox's
does: because §5 requires the parameter table, extension list, and shader precision
formats to match the claimed GPU, the unit of configuration should be a whole captured
GL profile, not a set of independently editable fields.

Options:

- **(a)** SP3 ships the mechanism plus three or four real captured profiles used only by
  its own tests. SP5 builds the profile database and the sampling logic.
  *Recommended.* It keeps SP3 testable without absorbing SP5's scope, and it avoids
  building a database before the coherence rules that consume it exist.
- **(b)** SP3 owns the profile database from the start. Larger SP3, and the capture
  tooling would likely be rewritten once SP5's coherence requirements are known.
- **(c)** No bundled profiles; operators supply raw values. Rejected — it guarantees
  incoherent configurations in practice.

Not yet decided: how profiles are captured. A capture harness that runs on real
hardware and dumps the full GL profile to JSON is the obvious approach, but whose
hardware, and how many profiles constitute useful coverage, is an SP5 question.

### 7.2 GPU-process interception as a follow-up

§4.1 defers this. The decision to revisit should be triggered by evidence — a specific
page-visible leak that cannot be closed at a Blink entry point — not by principle.
Record any such leak here.

### 7.3 Noise algorithm details

The specific PRNG, the mapping from `noiseDensity` to a pixel-selection predicate, and
the exact role of `aaOffset` are not specified here beyond the determinism requirement
in §4.3. Camoufox's implementation in `patches/canvas-spoofing.patch` is the reference
to study before choosing. Whether Camoucrome should match Camoufox's output exactly —
which would let one fingerprint generator serve both forks — or choose independently,
is open. Matching is attractive and should be evaluated once SP0 lands.

### 7.4 Known readback gap: WebGL2 PIXEL_PACK_BUFFER

The whole-branch review of SP3a found a page-reachable readback of the default
framebuffer that the canvas-noise hooks do not cover. The WebGL2 `readPixels`
overload that targets a bound `PIXEL_PACK_BUFFER` writes pixels into GPU buffer
memory rather than a CPU `ArrayBufferView`, so the `ReadPixelsHelper` noise hook
(which perturbs only a CPU destination) does not fire; a subsequent
`getBufferSubData()` then copies those un-noised default-framebuffer pixels to a
CPU array. An anti-detect-aware fingerprinter who knows the ArrayBufferView path
is noised can switch to the PACK path to recover clean pixels.

SP3a documents this rather than covering it: perturbing at `getBufferSubData`
correctly requires tracking whether the source buffer was filled from the
default framebuffer (perturbing every `getBufferSubData` would corrupt vertex,
index, and uniform-buffer reads that are app data, not fingerprints). That
buffer-provenance tracking is a self-contained follow-up. Until it lands,
"canvas readback covered" excludes the WebGL2 PACK-buffer path.

## 8. Explicitly out of scope

Font rendering and text metrics, which also affect canvas hashes, belong to SP4 —
Camoufox needed a 55KB `anti-font-fingerprinting.patch` for text-metric jitter alone,
and mixing it into SP3 would double this spec. SP3 ships the shared `derive_delta`
primitive those surfaces build on (§4.3), but not their call sites. Audio fingerprints,
media codec capability answers, and WebRTC belong to SP4. WebGPU adapter identity does
**not** — §4.1 places it in SP3. Cross-surface coherence enforcement and
the fingerprint preset database belong to SP5, per §7.1. The navigator identity and
UA Client Hints that a GPU profile must ultimately agree with belong to SP1. Verifying
against real GPU hardware requires the Windows host build and belongs to SP6.

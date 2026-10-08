// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_CANVAS_READBACK_H_
#define COMPONENTS_CAMOUCFG_CANVAS_READBACK_H_

#include <cstdint>

#include "components/camoucfg/canvas_noise.h"
#include "components/camoucfg/mask_config.h"
#include "third_party/skia/include/core/SkBitmap.h"
#include "third_party/skia/include/core/SkRect.h"
#include "third_party/skia/include/core/SkRefCnt.h"

class SkImage;

namespace camoucfg {

// The Blink canvas snapshot hook is NoisedCanvasImage (CanvasRenderingContext::
// CamouNoised): every readback API noises the snapshot it takes, so they all
// read one field per canvas state.

// A raster copy of `canvas` with PerturbRgbaEdges applied to its
// premultiplied RGBA8 pixels, keyed by `seed` and each pixel's 3x3 patch (canvas
// noise S2b), with `min_alpha` as the eligibility floor (255 for WebGL), `mask`
// gating each pixel, and `bottom_up` for a raster stored bottom-up (a
// kOriginBottomLeft snapshot). nullptr when nothing would change: seed 0, a colour type other
// than 8-bit RGBA/BGRA (a float canvas stays stock), or a failed read.
sk_sp<SkImage> NoisedImage(const SkImage& canvas, uint64_t seed,
                           double density, int32_t strength, uint8_t min_alpha,
                           const NoiseMask& mask, bool bottom_up);

// NoisedImage with canvas:seed / canvas:noiseDensity / canvas:noiseStrength
// from `scope`. The Blink snapshot hook (CanvasRenderingContext::CamouNoised).
sk_sp<SkImage> NoisedCanvasImage(const SkImage& canvas,
                                 const ConfigScope& scope, uint8_t min_alpha,
                                 const NoiseMask& mask, bool bottom_up);

// The pixels of `rect` (clipped to the canvas) exactly as NoisedImage(canvas,
// ..., bottom_up=false) holds them, in the canvas's alpha type as RGBA8,
// computing noise only over `rect` plus a 1 px margin. getImageData's path:
// the noise runs on the snapshot's (premultiplied) pixels, before any
// unpremultiply. Empty (drawsNothing()) on failure or seed 0; the caller then
// takes the whole-snapshot path.
SkBitmap NoisedRegion(const SkImage& canvas, const SkIRect& rect,
                      uint64_t seed, double density, int32_t strength,
                      uint8_t min_alpha, const NoiseMask& mask);
// NoisedRegion with canvas:seed / noiseDensity / noiseStrength from `scope`.
SkBitmap NoisedCanvasRegion(const SkImage& canvas, const SkIRect& rect,
                            const ConfigScope& scope, uint8_t min_alpha,
                            const NoiseMask& mask);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_CANVAS_READBACK_H_

// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_CANVAS_READBACK_H_
#define COMPONENTS_CAMOUCFG_CANVAS_READBACK_H_

#include <cstdint>

#include "base/functional/function_ref.h"
#include "components/camoucfg/canvas_noise.h"
#include "components/camoucfg/mask_config.h"
#include "third_party/skia/include/core/SkBitmap.h"
#include "third_party/skia/include/core/SkImageInfo.h"
#include "third_party/skia/include/core/SkRect.h"
#include "third_party/skia/include/core/SkRefCnt.h"

class SkImage;
class SkPixmap;

namespace camoucfg {

// The Blink canvas snapshot hook is NoisedCanvasImage (CanvasRenderingContext::
// CamouNoised): every readback API noises the snapshot it takes, so they all
// read one field per canvas state.

// A raster copy of `canvas` with PerturbRgbaEdgesInPlace applied to its
// premultiplied RGBA8 pixels, keyed by `seed` and each pixel's 3x3 patch (canvas
// noise S2b), with `min_alpha` as the eligibility floor (255 for WebGL), `mask`
// gating each pixel, and `bottom_up` for a raster stored bottom-up (a
// kOriginBottomLeft snapshot). nullptr when nothing would change: seed 0, a colour type other
// than 8-bit RGBA/BGRA (a float canvas stays stock), a mask of another size
// than the image or with an origin (a stale mask never gates the wrong
// pixels), or a failed read.
sk_sp<SkImage> NoisedImage(const SkImage& canvas, uint64_t seed,
                           double density, int32_t strength, uint8_t min_alpha,
                           const NoiseMask& mask, bool bottom_up);

// NoisedImage with canvas:seed / canvas:noiseDensity / canvas:noiseStrength
// from `scope`. The Blink snapshot hook (CanvasRenderingContext::CamouNoised).
sk_sp<SkImage> NoisedCanvasImage(const SkImage& canvas,
                                 const ConfigScope& scope, uint8_t min_alpha,
                                 const NoiseMask& mask, bool bottom_up);

// Reads the `dst.width()` x `dst.height()` pixels at (`src_x`, `src_y`) of a
// canvas into `dst`, converting to its colour type; false on failure. Blink
// passes cc::PaintImage::readPixels, which reads a texture-backed snapshot
// too.
using PixelReader =
    base::FunctionRef<bool(const SkPixmap& dst, int src_x, int src_y)>;

// The pixels of `rect` (clipped to the canvas) exactly as NoisedImage(canvas,
// ..., bottom_up=false) holds them, in the canvas's alpha type as RGBA8,
// reading (through `read`) and noising only `rect` plus a 1 px margin.
// `canvas` describes the whole canvas. getImageData's path: the noise runs on
// the snapshot's (premultiplied) pixels, before any unpremultiply. Empty
// (drawsNothing()) on failure, seed 0, or a mask of another size than the
// canvas; the caller then takes the whole-snapshot path.
SkBitmap NoisedRegion(const SkImageInfo& canvas,
                      PixelReader read,
                      const SkIRect& rect,
                      uint64_t seed,
                      double density,
                      int32_t strength,
                      uint8_t min_alpha,
                      const NoiseMask& mask);
// NoisedRegion with canvas:seed / noiseDensity / noiseStrength from `scope`.
SkBitmap NoisedCanvasRegion(const SkImageInfo& canvas,
                            PixelReader read,
                            const SkIRect& rect,
                            const ConfigScope& scope,
                            uint8_t min_alpha,
                            const NoiseMask& mask);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_CANVAS_READBACK_H_

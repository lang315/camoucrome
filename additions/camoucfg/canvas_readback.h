// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_CANVAS_READBACK_H_
#define COMPONENTS_CAMOUCFG_CANVAS_READBACK_H_

#include <cstddef>
#include <cstdint>

#include "components/camoucfg/mask_config.h"
#include "third_party/skia/include/core/SkRefCnt.h"

class SkImage;

namespace camoucfg {

// The Blink canvas snapshot hook is NoisedCanvasImage (CanvasRenderingContext::
// CamouNoised): every readback API noises the snapshot it takes, so they all
// read one field per canvas state.

// A raster copy of `canvas` with PerturbRgbaEdges applied to its
// premultiplied RGBA8 pixels, keyed by `seed` folded with CanvasStateHash of
// the canvas. nullptr when nothing would change: seed 0, a colour type other
// than 8-bit RGBA/BGRA (a float canvas stays stock), or a failed read.
sk_sp<SkImage> NoisedImage(const SkImage& canvas, uint64_t seed,
                           double density, int32_t strength);

// NoisedImage with canvas:seed / canvas:noiseDensity / canvas:noiseStrength
// from `scope`. The Blink snapshot hook (CanvasRenderingContext::CamouNoised).
sk_sp<SkImage> NoisedCanvasImage(const SkImage& canvas,
                                 const ConfigScope& scope);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_CANVAS_READBACK_H_

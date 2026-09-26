// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_CANVAS_READBACK_H_
#define COMPONENTS_CAMOUCFG_CANVAS_READBACK_H_

#include <cstddef>
#include <cstdint>

#include "components/camoucfg/mask_config.h"

class SkImage;

namespace camoucfg {

// The Blink canvas readback hook (getImageData, toDataURL, toBlob,
// convertToBlob). `pixels` is a `width` x `height` RGBA8 rect, rows
// `row_bytes` apart, read out of `canvas` -- a raster image of the canvas's
// whole current contents -- at (x0, y0). Applies PerturbRgbaAt keyed by
// canvas:seed and a hash of `canvas`, so every rect and every API reading
// one canvas state sees the same noise on the same pixel.
//
// Callers check CanvasSeed(scope) first: with no seed this is a no-op, and
// the snapshot a caller would make just to pass it here is skipped too.
void PerturbCanvasPixels(const SkImage& canvas, uint8_t* pixels, size_t width,
                         size_t height, size_t row_bytes, int x0, int y0,
                         const ConfigScope& scope);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_CANVAS_READBACK_H_

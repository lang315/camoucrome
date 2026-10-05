// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/canvas_readback.h"

#include <vector>

#include "base/containers/span.h"
#include "components/camoucfg/canvas_noise.h"
#include "third_party/skia/include/core/SkBitmap.h"
#include "third_party/skia/include/core/SkImage.h"
#include "third_party/skia/include/core/SkImageInfo.h"

namespace camoucfg {

sk_sp<SkImage> NoisedImage(const SkImage& canvas, uint64_t seed,
                           double density, int32_t strength) {
  const SkColorType ct = canvas.colorType();
  if (seed == 0 ||
      (ct != kRGBA_8888_SkColorType && ct != kBGRA_8888_SkColorType)) {
    return nullptr;
  }
  // RGBA whatever the backing order (BGRA on macOS and Windows), alpha type
  // kept: premultiplied data stays premultiplied, which the [0, alpha] clamp
  // of PerturbRgbaEdges relies on.
  const SkImageInfo info =
      canvas.imageInfo().makeColorType(kRGBA_8888_SkColorType);
  SkBitmap bitmap;
  if (!bitmap.tryAllocPixels(info) ||
      !canvas.readPixels(nullptr, bitmap.pixmap(), 0, 0)) {
    return nullptr;
  }
  uint8_t* pixels = static_cast<uint8_t*>(bitmap.getPixels());
  // SAFETY: the bitmap owns computeByteSize() bytes at getPixels().
  const base::span<const uint8_t> all = UNSAFE_BUFFERS(
      base::span<const uint8_t>(pixels, bitmap.computeByteSize()));
  const std::vector<uint8_t> source(all.begin(), all.end());
  const size_t w = info.width(), h = info.height(), row = bitmap.rowBytes();
  PerturbRgbaEdges(pixels, source.data(), w, h, row,
                   seed ^ CanvasStateHash(source.data(), w, h, row), density,
                   strength,
                   info.alphaType() == kUnpremul_SkAlphaType ? 255 : 1);
  bitmap.setImmutable();
  return SkImages::RasterFromBitmap(bitmap);
}

sk_sp<SkImage> NoisedCanvasImage(const SkImage& canvas,
                                 const ConfigScope& scope) {
  double density;
  int32_t strength;
  CanvasNoiseParams(scope, density, strength);
  return NoisedImage(canvas, CanvasSeed(scope), density, strength);
}

}  // namespace camoucfg

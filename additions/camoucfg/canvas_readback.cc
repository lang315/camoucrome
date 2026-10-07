// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/canvas_readback.h"

#include <algorithm>
#include <memory>

#include "base/containers/span.h"
#include "base/process/memory.h"
#include "components/camoucfg/canvas_noise.h"
#include "third_party/skia/include/core/SkBitmap.h"
#include "third_party/skia/include/core/SkImage.h"
#include "third_party/skia/include/core/SkImageInfo.h"

namespace camoucfg {

sk_sp<SkImage> NoisedImage(const SkImage& canvas, uint64_t seed,
                           double density, int32_t strength, uint8_t min_alpha,
                           const NoiseMask& mask, bool bottom_up) {
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
  // A fallible copy: on failure the snapshot stays stock rather than crash.
  void* raw = nullptr;
  if (!base::UncheckedMalloc(all.size(), &raw) || raw == nullptr) {
    return nullptr;
  }
  std::unique_ptr<uint8_t, void (*)(void*)> source(static_cast<uint8_t*>(raw),
                                                   &base::UncheckedFree);
  std::copy(all.begin(), all.end(), source.get());
  const size_t w = info.width(), h = info.height(), row = bitmap.rowBytes();
  const uint8_t floor =
      info.alphaType() == kUnpremul_SkAlphaType ? 255 : 1;
  PerturbRgbaEdges(pixels, source.get(), w, h, row, seed, density, strength,
                   std::max(min_alpha, floor), mask, bottom_up);
  bitmap.setImmutable();
  return SkImages::RasterFromBitmap(bitmap);
}

sk_sp<SkImage> NoisedCanvasImage(const SkImage& canvas,
                                 const ConfigScope& scope, uint8_t min_alpha,
                                 const NoiseMask& mask, bool bottom_up) {
  double density;
  int32_t strength;
  CanvasNoiseParams(scope, density, strength);
  return NoisedImage(canvas, CanvasSeed(scope), density, strength, min_alpha,
                     mask, bottom_up);
}

}  // namespace camoucfg

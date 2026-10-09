// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/canvas_readback.h"

#include <algorithm>

#include "components/camoucfg/canvas_noise.h"
#include "third_party/skia/include/core/SkBitmap.h"
#include "third_party/skia/include/core/SkImage.h"
#include "third_party/skia/include/core/SkImageInfo.h"
#include "third_party/skia/include/core/SkPixmap.h"

namespace camoucfg {
namespace {

// A whole-canvas mask is exactly the canvas's size, at origin 0: anything
// else is stale, and would gate pixels by the wrong cells. No mask is fine.
bool MaskFits(const NoiseMask& mask, int width, int height) {
  return mask.cells == nullptr ||
         (mask.width == static_cast<size_t>(width) &&
          mask.height == static_cast<size_t>(height) && mask.x0 == 0 &&
          mask.y0 == 0);
}

}  // namespace

sk_sp<SkImage> NoisedImage(const SkImage& canvas, uint64_t seed,
                           double density, int32_t strength, uint8_t min_alpha,
                           const NoiseMask& mask, bool bottom_up) {
  const SkColorType ct = canvas.colorType();
  if (seed == 0 ||
      (ct != kRGBA_8888_SkColorType && ct != kBGRA_8888_SkColorType) ||
      !MaskFits(mask, canvas.width(), canvas.height())) {
    return nullptr;
  }
  // RGBA whatever the backing order (BGRA on macOS and Windows), alpha type
  // kept: premultiplied data stays premultiplied, which the [0, alpha] clamp
  // of PerturbRgbaEdgesInPlace relies on.
  const SkImageInfo info =
      canvas.imageInfo().makeColorType(kRGBA_8888_SkColorType);
  SkBitmap bitmap;
  if (!bitmap.tryAllocPixels(info) ||
      !canvas.readPixels(nullptr, bitmap.pixmap(), 0, 0)) {
    return nullptr;
  }
  const size_t w = info.width(), h = info.height(), row = bitmap.rowBytes();
  const uint8_t floor =
      info.alphaType() == kUnpremul_SkAlphaType ? 255 : 1;
  // In place: a failed ring allocation leaves the snapshot stock, never a
  // crash.
  if (!PerturbRgbaEdgesInPlace(static_cast<uint8_t*>(bitmap.getPixels()), w, h,
                               row, seed, density, strength,
                               std::max(min_alpha, floor), mask, bottom_up)) {
    return nullptr;
  }
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

SkBitmap NoisedRegion(const SkImageInfo& canvas,
                      PixelReader read,
                      const SkIRect& rect,
                      uint64_t seed,
                      double density,
                      int32_t strength,
                      uint8_t min_alpha,
                      const NoiseMask& mask) {
  const SkColorType ct = canvas.colorType();
  if (seed == 0 ||
      (ct != kRGBA_8888_SkColorType && ct != kBGRA_8888_SkColorType) ||
      !MaskFits(mask, canvas.width(), canvas.height())) {
    return SkBitmap();
  }
  const SkIRect bounds = SkIRect::MakeWH(canvas.width(), canvas.height());
  SkIRect r = rect;
  if (!r.intersect(bounds)) {
    return SkBitmap();
  }
  // The margin gives every pixel of `r` its four neighbours; a pixel on the
  // canvas edge has none there and never changes, here or in NoisedImage.
  SkIRect m = r.makeOutset(1, 1);
  (void)m.intersect(bounds);  // r is inside bounds, so m is never empty
  const SkImageInfo info =
      canvas.makeColorType(kRGBA_8888_SkColorType).makeWH(m.width(), m.height());
  SkBitmap bitmap;
  if (!bitmap.tryAllocPixels(info) || !read(bitmap.pixmap(), m.x(), m.y())) {
    return SkBitmap();
  }
  NoiseMask at = mask;
  at.x0 = static_cast<size_t>(m.x());
  at.y0 = static_cast<size_t>(m.y());
  const uint8_t floor = info.alphaType() == kUnpremul_SkAlphaType ? 255 : 1;
  if (!PerturbRgbaEdgesInPlace(static_cast<uint8_t*>(bitmap.getPixels()),
                               info.width(), info.height(), bitmap.rowBytes(),
                               seed, density, strength,
                               std::max(min_alpha, floor), at,
                               /*bottom_up=*/false)) {
    return SkBitmap();
  }
  SkBitmap out;
  if (!bitmap.extractSubset(&out, r.makeOffset(-m.x(), -m.y()))) {
    return SkBitmap();
  }
  out.setImmutable();
  return out;
}

SkBitmap NoisedCanvasRegion(const SkImageInfo& canvas,
                            PixelReader read,
                            const SkIRect& rect,
                            const ConfigScope& scope,
                            uint8_t min_alpha,
                            const NoiseMask& mask) {
  double density;
  int32_t strength;
  CanvasNoiseParams(scope, density, strength);
  return NoisedRegion(canvas, read, rect, CanvasSeed(scope), density,
                      strength, min_alpha, mask);
}

}  // namespace camoucfg

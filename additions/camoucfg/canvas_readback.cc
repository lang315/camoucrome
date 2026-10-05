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
namespace {

// The last hashed canvas state on this thread. A page reading one canvas
// pixel by pixel (getImageData(x, y, 1, 1) in a loop) would otherwise pay a
// full-canvas readback per call, and that cost is itself observable.
// SkImage ids are process-unique, and a snapshot of an unchanged canvas is
// the same image.
// ponytail: one entry, so two canvases read alternately re-hash each time;
// grow it if that pattern shows up.
struct StateHashCache {
  uint32_t image_id = 0;
  uint64_t hash = 0;
};
constinit thread_local StateHashCache g_state_hash_cache;

uint64_t StateHashOf(const SkImage& canvas) {
  if (canvas.uniqueID() == g_state_hash_cache.image_id) {
    return g_state_hash_cache.hash;
  }
  // One canonical form whatever the backing store's order and alpha type,
  // so every readback site hashes the same bytes for the same state.
  const SkImageInfo info =
      SkImageInfo::Make(canvas.width(), canvas.height(),
                        kRGBA_8888_SkColorType, kUnpremul_SkAlphaType);
  std::vector<uint8_t> rgba(info.computeMinByteSize());
  uint64_t hash = 0;
  if (!rgba.empty() && canvas.readPixels(nullptr, info, rgba.data(),
                                         info.minRowBytes(), 0, 0)) {
    hash = CanvasStateHash(rgba.data(), info.width(), info.height(),
                           info.minRowBytes());
  }
  g_state_hash_cache = {canvas.uniqueID(), hash};
  return hash;
}

}  // namespace

void PerturbCanvasPixels(const SkImage& canvas, uint8_t* pixels, size_t width,
                         size_t height, size_t row_bytes, int x0, int y0,
                         const ConfigScope& scope) {
  if (CanvasSeed(scope) == 0) {
    return;
  }
  PerturbRgbaAtFromConfig(pixels, width, height, row_bytes, x0, y0,
                          StateHashOf(canvas), scope);
}


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

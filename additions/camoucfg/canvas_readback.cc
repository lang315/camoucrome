// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/canvas_readback.h"

#include <vector>

#include "components/camoucfg/canvas_noise.h"
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

}  // namespace camoucfg

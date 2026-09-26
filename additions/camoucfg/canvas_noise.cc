// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/canvas_noise.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <optional>
#include <string>

#include "base/containers/span.h"
#include "components/camoucfg/derive.h"
#include "components/camoucfg/keys.h"

namespace camoucfg {
namespace {

// FNV-1a 64 over the first min(length, 1024) bytes. The 1024-byte window is
// Camoufox's (HashContent), chosen so the hash is cheap yet content-sensitive:
// enough to distinguish drawings without walking a multi-megabyte buffer.
uint64_t ContentHash(base::span<const uint8_t> data) {
  constexpr size_t kMaxBytes = 1024;
  const size_t n = std::min(data.size(), kMaxBytes);
  uint64_t h = 0xCBF29CE484222325ULL;
  for (size_t i = 0; i < n; ++i) {
    h ^= data[i];
    h *= 0x100000001B3ULL;
  }
  return h;
}

}  // namespace

void PerturbRgbaAt(uint8_t* data, size_t width, size_t height,
                   size_t row_bytes, int64_t x0, int64_t y0, uint64_t seed,
                   double density, int32_t strength) {
  // NaN-safe: !(density > 0) catches it.
  if (seed == 0 || data == nullptr || !(density > 0.0) || strength <= 0) {
    return;
  }
  density = std::min(density, 1.0);
  strength = std::min(strength, 255);
  static constexpr std::array<std::string_view, 3> kGate = {
      "canvas-gate-r", "canvas-gate-g", "canvas-gate-b"};
  static constexpr std::array<std::string_view, 3> kDelta = {
      "canvas-r", "canvas-g", "canvas-b"};
  for (size_t r = 0; r < height; ++r) {
    // SAFETY: the caller's buffer holds `height` rows of `row_bytes`, each at
    // least `width` * 4 bytes.
    base::span<uint8_t> row =
        UNSAFE_BUFFERS(base::span(data + r * row_bytes, width * 4));
    const uint32_t y = static_cast<uint32_t>(y0 + static_cast<int64_t>(r));
    for (size_t c = 0; c < width; ++c) {
      base::span<uint8_t> px = row.subspan(c * 4, 4u);
      // Only opaque pixels: stock never shows RGB under alpha 0, and an
      // unpremultiplied value under a partial alpha sits on a grid that a
      // +-1 step would leave.
      if (px[3] != 255) {
        continue;
      }
      const uint32_t x = static_cast<uint32_t>(x0 + static_cast<int64_t>(c));
      // The canvas position, not the index in this buffer: any rect of the
      // same canvas state reads the same noise for the same pixel.
      const uint64_t index = (uint64_t{x} << 32) | y;
      for (size_t ch = 0; ch < 3; ++ch) {
        if (DeriveUnit(seed, kGate[ch], index) >= density) {
          continue;
        }
        const int32_t v = int32_t{px[ch]} + DeriveDelta(seed, kDelta[ch], index,
                                                        strength);
        px[ch] = static_cast<uint8_t>(std::clamp(v, 0, 255));
      }
    }
  }
}

void PerturbRgba(uint8_t* data, size_t length, uint64_t seed, double density,
                 int32_t strength) {
  if (seed == 0 || data == nullptr || length < 4) {
    return;
  }
  // Fold content into the seed: same drawing reproduces, different drawings
  // diverge.
  const uint64_t eseed =
      seed ^ ContentHash(UNSAFE_BUFFERS(base::span<const uint8_t>(data, length)));
  PerturbRgbaAt(data, length / 4, 1, length, 0, 0, eseed, density, strength);
}

uint64_t CanvasStateHash(const uint8_t* rgba, size_t width, size_t height,
                         size_t row_bytes) {
  // FNV-1a 64 over at most kSamples pixels spread evenly over the whole
  // canvas, plus its size.
  // ponytail: strided sample, so a change confined to unsampled pixels of a
  // canvas above kSamples pixels keeps its hash; hash every pixel if that
  // ever matters more than readback cost.
  constexpr size_t kSamples = 1 << 16;
  uint64_t h = 0xCBF29CE484222325ULL;
  auto mix = [&h](uint64_t b) {
    h ^= b;
    h *= 0x100000001B3ULL;
  };
  mix(width);
  mix(height);
  const size_t total = width * height;
  const size_t step = std::max<size_t>(1, total / kSamples);
  for (size_t k = 0; k < total; k += step) {
    // SAFETY: k < width * height, so the pixel lies inside the caller's
    // `height` rows of `row_bytes`.
    const uint8_t* px =
        UNSAFE_BUFFERS(rgba + (k / width) * row_bytes + (k % width) * 4);
    for (size_t b = 0; b < 4; ++b) {
      mix(UNSAFE_BUFFERS(px[b]));
    }
  }
  return h;
}

namespace {

// canvas:noiseDensity / canvas:noiseStrength with their defaults. The ONE
// place the canvas noise keys are read.
void NoiseParams(const ConfigScope& scope, double& density, int32_t& strength) {
  density = GetDouble(scope, keys::kCanvasNoiseDensity).value_or(0.0005);
  strength = GetInt32(scope, keys::kCanvasNoiseStrength).value_or(1);
}

}  // namespace

void PerturbRgbaFromConfig(uint8_t* data, size_t length,
                           const ConfigScope& scope) {
  const uint64_t seed = CanvasSeed(scope);
  if (seed == 0) {
    return;  // spoof off -> byte-identical to stock (rule 5)
  }
  double density;
  int32_t strength;
  NoiseParams(scope, density, strength);
  PerturbRgba(data, length, seed, density, strength);
}

void PerturbRgbaAtFromConfig(uint8_t* data, size_t width, size_t height,
                             size_t row_bytes, int64_t x0, int64_t y0,
                             uint64_t state_hash, const ConfigScope& scope) {
  const uint64_t seed = CanvasSeed(scope);
  if (seed == 0) {
    return;  // spoof off -> byte-identical to stock (rule 5)
  }
  double density;
  int32_t strength;
  NoiseParams(scope, density, strength);
  PerturbRgbaAt(data, width, height, row_bytes, x0, y0, seed ^ state_hash,
                density, strength);
}

double PerturbMetric(double stock, uint64_t seed, uint64_t index,
                     std::string_view domain) {
  if (seed == 0 || stock == 0.0) {
    return stock;
  }
  if (stock == std::trunc(stock)) {  // integer field -> integer delta, on-grid
    return stock + DeriveDelta(seed, domain, index, /*bound=*/1);
  }
  // dyadic-fractional field -> sub-pixel delta on a 1/64 grid (a multiple of any
  // finer dyadic grid the stock already sits on), bounded to +-8/64 = 0.125 px.
  return stock + DeriveDelta(seed, domain, index, /*bound=*/8) / 64.0;
}

uint64_t CanvasSeed(const ConfigScope& scope) {
  return GetUint32(scope, keys::kCanvasSeed).value_or(0);
}

}  // namespace camoucfg

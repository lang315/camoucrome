// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/canvas_noise.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <optional>
#include <string>
#include <vector>

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

void PerturbRgba(uint8_t* data, size_t width, size_t height, uint64_t seed,
                 double density, int32_t strength) {
  if (seed == 0 || data == nullptr || width == 0 || height == 0) {
    return;
  }
  // SAFETY: the caller's buffer holds width * height RGBA8 pixels.
  const base::span<const uint8_t> in = UNSAFE_BUFFERS(
      base::span<const uint8_t>(data, width * height * 4));
  const std::vector<uint8_t> source(in.begin(), in.end());
  // Fold content into the seed: same drawing reproduces, different drawings
  // diverge.
  PerturbRgbaEdges(data, source.data(), width, height, width * 4,
                   seed ^ ContentHash(source), density, strength,
                   /*min_alpha=*/255);
}

void PerturbRgbaEdges(uint8_t* data, const uint8_t* source, size_t width,
                      size_t height, size_t row_bytes, uint64_t seed,
                      double density, int32_t strength, uint8_t min_alpha) {
  // NaN-safe: !(density > 0) catches it.
  if (seed == 0 || data == nullptr || source == nullptr || !(density > 0.0) ||
      strength <= 0 || width < 3 || height < 3) {
    return;
  }
  density = std::min(density, 1.0);
  strength = std::min(strength, 255);
  min_alpha = std::max<uint8_t>(min_alpha, 1);
  static constexpr std::array<std::string_view, 3> kGate = {
      "canvas-gate-r", "canvas-gate-g", "canvas-gate-b"};
  static constexpr std::array<std::string_view, 3> kDelta = {
      "canvas-r", "canvas-g", "canvas-b"};
  const size_t size = (height - 1) * row_bytes + width * 4;
  // SAFETY: both buffers hold `height` rows of `row_bytes`, each at least
  // `width` * 4 bytes.
  const base::span<const uint8_t> src =
      UNSAFE_BUFFERS(base::span<const uint8_t>(source, size));
  const base::span<uint8_t> dst = UNSAFE_BUFFERS(base::span(data, size));
  auto at = [&](size_t x, size_t y) {
    return src.subspan(y * row_bytes + x * 4, 4u);
  };
  for (size_t y = 1; y + 1 < height; ++y) {
    for (size_t x = 1; x + 1 < width; ++x) {
      const base::span<const uint8_t> px = at(x, y);
      const uint8_t alpha = px[3];
      if (alpha < min_alpha || std::ranges::equal(px, at(x - 1, y)) ||
          std::ranges::equal(px, at(x + 1, y)) ||
          std::ranges::equal(px, at(x, y - 1)) ||
          std::ranges::equal(px, at(x, y + 1))) {
        continue;
      }
      // The position, not the index in the buffer: every reader of one
      // canvas state gets the same noise on the same pixel.
      const uint64_t index =
          (uint64_t{static_cast<uint32_t>(x)} << 32) | static_cast<uint32_t>(y);
      base::span<uint8_t> out = dst.subspan(y * row_bytes + x * 4, 4u);
      for (size_t ch = 0; ch < 3; ++ch) {
        if (DeriveUnit(seed, kGate[ch], index) >= density) {
          continue;
        }
        const int32_t v =
            int32_t{px[ch]} + DeriveDelta(seed, kDelta[ch], index, strength);
        out[ch] = static_cast<uint8_t>(std::clamp(v, 0, int32_t{alpha}));
      }
    }
  }
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

// canvas:noiseDensity / canvas:noiseStrength with their defaults. The ONE
// place the canvas noise keys are read.
void CanvasNoiseParams(const ConfigScope& scope, double& density,
                       int32_t& strength) {
  density = GetDouble(scope, keys::kCanvasNoiseDensity).value_or(0.0005);
  strength = GetInt32(scope, keys::kCanvasNoiseStrength).value_or(1);
}

void PerturbRgbaFromConfig(uint8_t* data, size_t width, size_t height,
                           const ConfigScope& scope) {
  const uint64_t seed = CanvasSeed(scope);
  if (seed == 0) {
    return;  // spoof off -> byte-identical to stock (rule 5)
  }
  double density;
  int32_t strength;
  CanvasNoiseParams(scope, density, strength);
  PerturbRgba(data, width, height, seed, density, strength);
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

std::array<float, 2> TextOffset(uint64_t seed) {
  if (seed == 0) {
    return {0.0f, 0.0f};
  }
  // A double just below 1 rounds to 1.0f; keep the result in [0, 1).
  auto unit = [seed](std::string_view domain) {
    return std::min(static_cast<float>(DeriveUnit(seed, domain, 0)),
                    std::nextafter(1.0f, 0.0f));
  };
  return {unit("canvas-text-offset-x"), unit("canvas-text-offset-y")};
}

}  // namespace camoucfg

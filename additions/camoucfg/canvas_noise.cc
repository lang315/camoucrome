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

// FNV-1a 64 over the 3x3 neighbourhood of interior pixel (x, y): 9 RGBA
// pixels, 36 bytes, in top-down row order. For a bottom-up buffer the row
// above is y + 1.
uint64_t PatchHash(base::span<const uint8_t> src, size_t row_bytes, size_t x,
                   size_t y, bool bottom_up) {
  uint64_t h = 0xCBF29CE484222325ULL;
  for (int dy = -1; dy <= 1; ++dy) {
    const size_t row = bottom_up ? y - dy : y + dy;
    for (uint8_t b : src.subspan(row * row_bytes + (x - 1) * 4, 12u)) {
      h ^= b;
      h *= 0x100000001B3ULL;
    }
  }
  return h;
}

}  // namespace

void PerturbRgba(uint8_t* data, size_t width, size_t height, size_t row_bytes,
                 uint64_t seed, double density, int32_t strength,
                 bool bottom_up) {
  if (seed == 0 || data == nullptr || width == 0 || height == 0 ||
      row_bytes < width * 4) {
    return;
  }
  // SAFETY: the caller's buffer holds `height` rows of `row_bytes`, the last
  // one at least width * 4 bytes long.
  const base::span<const uint8_t> in = UNSAFE_BUFFERS(base::span<const uint8_t>(
      data, (height - 1) * row_bytes + width * 4));
  const std::vector<uint8_t> source(in.begin(), in.end());
  PerturbRgbaEdges(data, source.data(), width, height, row_bytes, seed,
                   density, strength, /*min_alpha=*/255, NoiseMask(),
                   bottom_up);
}

void PerturbRgbaEdges(uint8_t* data, const uint8_t* source, size_t width,
                      size_t height, size_t row_bytes, uint64_t seed,
                      double density, int32_t strength, uint8_t min_alpha,
                      const NoiseMask& mask, bool bottom_up) {
  // NaN-safe: !(density > 0) catches it.
  if (seed == 0 || data == nullptr || source == nullptr || !(density > 0.0) ||
      strength <= 0 || width < 3 || height < 3 ||
      (mask.cells != nullptr &&
       (bottom_up || mask.width != width || mask.height != height))) {
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
  const size_t cell = size_t{1} << mask.shift;
  // SAFETY: a mask for this size holds stride * ceil(height / cell) cells.
  const base::span<const uint8_t> cells =
      mask.cells == nullptr
          ? base::span<const uint8_t>()
          : UNSAFE_BUFFERS(base::span<const uint8_t>(
                mask.cells, mask.stride * ((height + cell - 1) / cell)));
  auto at = [&](size_t x, size_t y) {
    return src.subspan(y * row_bytes + x * 4, 4u);
  };
  for (size_t y = 1; y + 1 < height; ++y) {
    for (size_t x = 1; x + 1 < width; ++x) {
      if (!cells.empty() &&
          cells[(y >> mask.shift) * mask.stride + (x >> mask.shift)] !=
              kNoiseMaskAa) {
        continue;
      }
      const base::span<const uint8_t> px = at(x, y);
      const uint8_t alpha = px[3];
      if (alpha < min_alpha || std::ranges::equal(px, at(x - 1, y)) ||
          std::ranges::equal(px, at(x + 1, y)) ||
          std::ranges::equal(px, at(x, y - 1)) ||
          std::ranges::equal(px, at(x, y + 1))) {
        continue;
      }
      // The 3x3 source patch, not the position (canvas noise S2b): one patch
      // gets one noise wherever it is.
      const uint64_t index = PatchHash(src, row_bytes, x, y, bottom_up);
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

// canvas:noiseDensity / canvas:noiseStrength with their defaults. The ONE
// place the canvas noise keys are read.
void CanvasNoiseParams(const ConfigScope& scope, double& density,
                       int32_t& strength) {
  density = GetDouble(scope, keys::kCanvasNoiseDensity).value_or(0.04);
  strength = GetInt32(scope, keys::kCanvasNoiseStrength).value_or(1);
}

void PerturbRgbaFromConfig(uint8_t* data, size_t width, size_t height,
                           size_t row_bytes, const ConfigScope& scope) {
  const uint64_t seed = CanvasSeed(scope);
  if (seed == 0) {
    return;  // spoof off -> byte-identical to stock (rule 5)
  }
  double density;
  int32_t strength;
  CanvasNoiseParams(scope, density, strength);
  PerturbRgba(data, width, height, row_bytes, seed, density, strength,
              /*bottom_up=*/true);
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

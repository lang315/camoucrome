// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifdef UNSAFE_BUFFERS_BUILD
// The noise pass reads through raw pointers after one size check per call
// (canvas noise S2c: the bounds-checked span loop cost ~25 ns per pixel).
#pragma allow_unsafe_buffers
#endif

#include "components/camoucfg/canvas_noise.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <memory>

#include "base/process/memory.h"
#include "components/camoucfg/derive.h"
#include "components/camoucfg/keys.h"

namespace camoucfg {
namespace {

uint32_t Load32(const uint8_t* p) {
  uint32_t v;
  std::memcpy(&v, p, sizeof(v));
  return v;
}

struct NoiseKeys {
  std::array<uint64_t, 3> gate;
  std::array<uint64_t, 3> delta;
};

const NoiseKeys& Keys() {
  static const NoiseKeys keys = {
      {DomainKey("canvas-gate-r"), DomainKey("canvas-gate-g"),
       DomainKey("canvas-gate-b")},
      {DomainKey("canvas-r"), DomainKey("canvas-g"), DomainKey("canvas-b")}};
  return keys;
}

// FNV-1a 64 over the 3x3 neighbourhood of interior pixel x: 12 bytes of each
// row, in top-down order (canvas noise S2b).
uint64_t PatchHash(const uint8_t* top,
                   const uint8_t* mid,
                   const uint8_t* bottom,
                   size_t x) {
  uint64_t h = 0xCBF29CE484222325ULL;
  for (const uint8_t* row : {top, mid, bottom}) {
    for (const uint8_t* b = row + (x - 1) * 4; b != row + (x + 2) * 4; ++b) {
      h ^= *b;
      h *= 0x100000001B3ULL;
    }
  }
  return h;
}

// Whether a call with these arguments does anything.
bool Active(const uint8_t* data,
            size_t width,
            size_t height,
            size_t row_bytes,
            uint64_t seed,
            double density,
            int32_t strength,
            const NoiseMask& mask,
            bool bottom_up) {
  // NaN-safe: !(density > 0) catches it.
  return seed != 0 && data != nullptr && density > 0.0 && strength > 0 &&
         width >= 3 && height >= 3 && row_bytes >= width * 4 &&
         (mask.cells == nullptr ||
          (!bottom_up && mask.x0 + width <= mask.width &&
           mask.y0 + height <= mask.height));
}

// Noises the interior pixels of one row into `out` from unperturbed source
// rows: `src` is the row, `mem_above` / `mem_below` the rows before / after
// it in memory. `cells` is this row's mask cells, or null.
void NoiseRow(uint8_t* out,
              const uint8_t* mem_above,
              const uint8_t* src,
              const uint8_t* mem_below,
              size_t width,
              uint64_t seed,
              double density,
              int32_t strength,
              uint8_t min_alpha,
              const uint8_t* cells,
              const NoiseMask& mask,
              bool bottom_up) {
  const NoiseKeys& keys = Keys();
  const uint8_t* top = bottom_up ? mem_below : mem_above;
  const uint8_t* bottom = bottom_up ? mem_above : mem_below;
  for (size_t x = 1; x + 1 < width; ++x) {
    if (cells != nullptr &&
        cells[(x + mask.x0) >> mask.shift] != kNoiseMaskAa) {
      continue;
    }
    const uint8_t* px = src + x * 4;
    const uint8_t alpha = px[3];
    const uint32_t v = Load32(px);
    if (alpha < min_alpha || v == Load32(px - 4) || v == Load32(px + 4) ||
        v == Load32(mem_above + x * 4) || v == Load32(mem_below + x * 4)) {
      continue;
    }
    // The 3x3 source patch, not the position (canvas noise S2b): one patch
    // gets one noise wherever it is.
    const uint64_t index = PatchHash(top, src, bottom, x);
    uint8_t* o = out + x * 4;
    for (size_t ch = 0; ch < 3; ++ch) {
      if (DeriveUnitKeyed(seed, keys.gate[ch], index) >= density) {
        continue;
      }
      const int32_t d = int32_t{px[ch]} +
                        DeriveDeltaKeyed(seed, keys.delta[ch], index, strength);
      o[ch] = static_cast<uint8_t>(std::clamp(d, 0, int32_t{alpha}));
    }
  }
}

// This row's mask cells, or null for no mask.
const uint8_t* CellRow(const NoiseMask& mask, size_t y) {
  return mask.cells == nullptr
             ? nullptr
             : mask.cells + ((y + mask.y0) >> mask.shift) * mask.stride;
}

}  // namespace

void PerturbRgba(uint8_t* data, size_t width, size_t height, size_t row_bytes,
                 uint64_t seed, double density, int32_t strength,
                 bool bottom_up) {
  if (seed == 0 || data == nullptr || width == 0 || height == 0 ||
      row_bytes < width * 4) {
    return;
  }
  // In place: a failed ring allocation leaves the read stock, never a crash.
  PerturbRgbaEdgesInPlace(data, width, height, row_bytes, seed, density,
                          strength, /*min_alpha=*/255, NoiseMask(), bottom_up);
}

bool PerturbRgbaEdgesInPlace(uint8_t* data,
                             size_t width,
                             size_t height,
                             size_t row_bytes,
                             uint64_t seed,
                             double density,
                             int32_t strength,
                             uint8_t min_alpha,
                             const NoiseMask& mask,
                             bool bottom_up) {
  if (!Active(data, width, height, row_bytes, seed, density, strength, mask,
              bottom_up)) {
    return true;
  }
  density = std::min(density, 1.0);
  strength = std::min(strength, 255);
  min_alpha = std::max<uint8_t>(min_alpha, 1);
  const size_t tight = width * 4;
  void* raw = nullptr;
  if (!base::UncheckedMalloc(2 * tight, &raw) || raw == nullptr) {
    return false;
  }
  std::unique_ptr<uint8_t, void (*)(void*)> ring(static_cast<uint8_t*>(raw),
                                                 &base::UncheckedFree);
  uint8_t* above = ring.get();        // row y - 1, unperturbed
  uint8_t* row = ring.get() + tight;  // row y, unperturbed
  std::memcpy(above, data, tight);    // row 0 is never written
  for (size_t y = 1; y + 1 < height; ++y) {
    uint8_t* out = data + y * row_bytes;
    std::memcpy(row, out, tight);
    NoiseRow(out, above, row, data + (y + 1) * row_bytes, width, seed, density,
             strength, min_alpha, CellRow(mask, y), mask, bottom_up);
    std::swap(above, row);
  }
  return true;
}

bool PerturbRgbaFramed(uint8_t* data,
                       size_t width,
                       size_t height,
                       size_t row_bytes,
                       const RgbaFrame& frame,
                       uint64_t seed,
                       double density,
                       int32_t strength,
                       bool bottom_up) {
  // A ring row holds the rect's row plus its frame pixels: `lo` of them
  // before the row's first pixel, `ext` in all.
  const size_t lo = frame.left ? 1 : 0;
  const size_t ext = width + lo + (frame.right ? 1 : 0);
  // The rows that have both vertical neighbours.
  const size_t first = frame.before ? 0 : 1;
  const size_t end = frame.after ? height : height - 1;
  if (seed == 0 || data == nullptr || !(density > 0.0) || strength <= 0 ||
      width == 0 || height == 0 || row_bytes < width * 4 || ext < 3 ||
      first >= end) {
    return true;
  }
  density = std::min(density, 1.0);
  strength = std::min(strength, 255);
  const size_t tight = ext * 4;
  void* raw = nullptr;
  if (!base::UncheckedMalloc(4 * tight, &raw) || raw == nullptr) {
    return false;
  }
  std::unique_ptr<uint8_t, void (*)(void*)> ring(static_cast<uint8_t*>(raw),
                                                 &base::UncheckedFree);
  uint8_t* above = ring.get();      // row y - 1, unperturbed
  uint8_t* row = above + tight;     // row y, unperturbed
  uint8_t* below = row + tight;     // row y + 1, unperturbed
  uint8_t* out = below + tight;     // row y, noised
  // Row y of the rect with its frame pixels, unperturbed: rows after y are
  // still as read.
  auto load = [&](size_t y, uint8_t* dst) {
    if (frame.left) {
      std::memcpy(dst, frame.left + y * frame.side_stride, 4);
    }
    std::memcpy(dst + lo * 4, data + y * row_bytes, width * 4);
    if (frame.right) {
      std::memcpy(dst + (lo + width) * 4, frame.right + y * frame.side_stride,
                  4);
    }
  };
  if (first == 0) {
    std::memcpy(above, frame.before, tight);
  } else {
    load(first - 1, above);
  }
  load(first, row);
  for (size_t y = first; y < end; ++y) {
    const uint8_t* next = frame.after;
    if (y + 1 < height) {
      load(y + 1, below);
      next = below;
    }
    std::memcpy(out, row, tight);
    NoiseRow(out, above, row, next, ext, seed, density, strength,
             /*min_alpha=*/255, nullptr, NoiseMask(), bottom_up);
    std::memcpy(data + y * row_bytes, out + lo * 4, width * 4);
    std::swap(above, row);
    std::swap(row, below);
  }
  return true;
}

// canvas:noiseDensity / canvas:noiseStrength with their defaults. The ONE
// place the canvas noise keys are read.
void CanvasNoiseParams(const ConfigScope& scope, double& density,
                       int32_t& strength) {
  density = GetDouble(scope, keys::kCanvasNoiseDensity).value_or(0.04);
  strength = GetInt32(scope, keys::kCanvasNoiseStrength).value_or(1);
}

void PerturbRgbaFromConfig(uint8_t* data, size_t width, size_t height,
                           size_t row_bytes, const ConfigScope& scope,
                           const RgbaFrame& frame) {
  const uint64_t seed = CanvasSeed(scope);
  if (seed == 0) {
    return;  // spoof off -> byte-identical to stock (rule 5)
  }
  double density;
  int32_t strength;
  CanvasNoiseParams(scope, density, strength);
  if (frame.before || frame.after || frame.left || frame.right) {
    // A failed ring allocation leaves the read stock.
    PerturbRgbaFramed(data, width, height, row_bytes, frame, seed, density,
                      strength, /*bottom_up=*/true);
    return;
  }
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

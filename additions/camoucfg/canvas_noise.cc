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
#include <cstdlib>
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
  uint64_t gate;
  uint64_t dir;
  uint64_t step;
};

const NoiseKeys& Keys(NoiseDomain domain) {
  static const NoiseKeys k2d = {DomainKey("canvas-jitter-gate"),
                                DomainKey("canvas-jitter-dir"),
                                DomainKey("canvas-jitter-step")};
  static const NoiseKeys webgl = {DomainKey("webgl-jitter-gate"),
                                  DomainKey("webgl-jitter-dir"),
                                  DomainKey("webgl-jitter-step")};
  return domain == NoiseDomain::kWebGl ? webgl : k2d;
}

// A draw in [0, k) for k >= 1, from DeriveDeltaKeyed's integer output (span
// 2^21 + 1): no float rounding, so every platform draws the same value. The
// modulo bias is below k / 2^21, and k <= 255.
uint32_t DrawBelow(uint64_t seed, uint64_t key, uint64_t index, uint32_t k) {
  constexpr int32_t kBound = 1 << 20;
  return static_cast<uint32_t>(DeriveDeltaKeyed(seed, key, index, kBound) +
                               kBound) %
         k;
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
              bool bottom_up,
              NoiseDomain domain) {
  const NoiseKeys& keys = Keys(domain);
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
    if (DeriveUnitKeyed(seed, keys.gate, index) >= density) {
      continue;
    }
    // The 4 neighbours with enough alpha, left, right, top, bottom, where top
    // and bottom are the logical rows (never memory order).
    const uint8_t* cand[4];
    uint32_t count = 0;
    for (const uint8_t* n :
         {px - 4, px + 4, top + x * 4, bottom + x * 4}) {
      if (n[3] >= min_alpha) {
        cand[count++] = n;
      }
    }
    if (count == 0) {
      continue;
    }
    const uint8_t* n = cand[DrawBelow(seed, keys.dir, index, count)];
    int32_t m = 0;
    for (size_t ch = 0; ch < 4; ++ch) {
      m = std::max(m, std::abs(int32_t{n[ch]} - int32_t{px[ch]}));
    }
    // m >= 1: the eligibility test made n differ from p.
    const int32_t step = std::min<int32_t>(
        1 + static_cast<int32_t>(
                DrawBelow(seed, keys.step, index, static_cast<uint32_t>(strength))),
        m);
    uint8_t* o = out + x * 4;
    // p' = p + RoundHalfAway(step * (n - p) / m), in integers, on all four
    // premultiplied channels: a convex mix of two colours already present.
    int32_t moved[4];
    for (size_t ch = 0; ch < 4; ++ch) {
      const int32_t diff = int32_t{n[ch]} - int32_t{px[ch]};
      const int32_t mag = (2 * step * std::abs(diff) + m) / (2 * m);
      moved[ch] = int32_t{px[ch]} + (diff < 0 ? -mag : mag);
    }
    for (size_t ch = 0; ch < 3; ++ch) {
      o[ch] = static_cast<uint8_t>(std::clamp(moved[ch], 0, moved[3]));
    }
    o[3] = static_cast<uint8_t>(moved[3]);
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
                          strength, /*min_alpha=*/255, NoiseMask(), bottom_up,
                          NoiseDomain::kWebGl);
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
                             bool bottom_up,
                             NoiseDomain domain) {
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
             strength, min_alpha, CellRow(mask, y), mask, bottom_up, domain);
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
  uint8_t* above = ring.get();   // row y - 1, unperturbed
  uint8_t* row = above + tight;  // row y, unperturbed
  uint8_t* below = row + tight;  // row y + 1, unperturbed
  uint8_t* out = below + tight;  // row y, noised
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
             /*min_alpha=*/255, nullptr, NoiseMask(), bottom_up,
             NoiseDomain::kWebGl);
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
  // Per pixel: one gate per pixel since the coverage jitter. The old default,
  // 0.04 per channel, noised 1 - 0.96^3 = 11.5% of eligible pixels, and the
  // calibrated minimum was 0.02 per channel (5.9% per pixel); 0.12 keeps the
  // same 2x margin over it.
  density = GetDouble(scope, keys::kCanvasNoiseDensity).value_or(0.12);
  strength = GetInt32(scope, keys::kCanvasNoiseStrength).value_or(1);
}

void PerturbRgbaFromConfig(uint8_t* data,
                           size_t width,
                           size_t height,
                           size_t row_bytes,
                           const ConfigScope& scope,
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

uint64_t TextMetricsSeed(const ConfigScope& scope) {
  return GetUint32(scope, keys::kTextMetricsSeed).value_or(0);
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

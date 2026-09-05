// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/canvas_noise.h"

#include <algorithm>
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

void PerturbRgba(uint8_t* data, size_t length, uint64_t seed, double density,
                 int32_t strength) {
  if (seed == 0 || data == nullptr || length < 4 || density <= 0.0) {
    return;
  }
  // SAFETY: `data` and `length` are the caller's buffer bounds.
  base::span<uint8_t> pixels = UNSAFE_BUFFERS(base::span(data, length));
  // Fold content into the seed: same drawing reproduces, different drawings
  // diverge. seed != 0 is already guaranteed; if the XOR lands on 0 the mixer
  // still behaves, so no special case is needed.
  const uint64_t eseed = seed ^ ContentHash(pixels);
  for (size_t i = 0; i < length; ++i) {
    if ((i & 3u) == 3u) {
      continue;  // skip alpha
    }
    if (DeriveUnit(eseed, "canvas-gate", i) >= density) {
      continue;  // channel not selected this session
    }
    const int32_t delta = DeriveDelta(eseed, "canvas", i, strength);
    int32_t v = static_cast<int32_t>(pixels[i]) + delta;
    pixels[i] = static_cast<uint8_t>(v < 0 ? 0 : (v > 255 ? 255 : v));
  }
}

void PerturbRgbaFromConfig(uint8_t* data, size_t length,
                           const ConfigScope& scope) {
  const std::optional<uint32_t> seed = GetUint32(scope, keys::kCanvasSeed);
  if (!seed || *seed == 0) {
    return;  // spoof off -> byte-identical to stock (rule 5)
  }
  const double density =
      GetDouble(scope, keys::kCanvasNoiseDensity).value_or(0.0005);
  const int32_t strength =
      GetInt32(scope, keys::kCanvasNoiseStrength).value_or(1);
  PerturbRgba(data, length, static_cast<uint64_t>(*seed), density, strength);
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

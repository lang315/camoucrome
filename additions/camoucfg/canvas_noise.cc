// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifdef UNSAFE_BUFFERS_BUILD
// This file indexes a raw (uint8_t*, size_t) buffer -- the contract shared
// with the Blink readback call sites that will pass canvas pixel storage
// directly. Every index is bounds-checked against `length` before use.
// TODO(camoucrome): convert to base::span when those call sites are wired up.
#pragma allow_unsafe_buffers
#endif

#include "components/camoucfg/canvas_noise.h"

#include <algorithm>
#include <optional>
#include <string>

#include "components/camoucfg/derive.h"
#include "components/camoucfg/keys.h"

namespace camoucfg {
namespace {

// FNV-1a 64 over the first min(length, 1024) bytes. The 1024-byte window is
// Camoufox's (HashContent), chosen so the hash is cheap yet content-sensitive:
// enough to distinguish drawings without walking a multi-megabyte buffer.
uint64_t ContentHash(const uint8_t* data, size_t length) {
  constexpr size_t kMaxBytes = 1024;
  const size_t n = std::min(length, kMaxBytes);
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
  // Fold content into the seed: same drawing reproduces, different drawings
  // diverge. seed != 0 is already guaranteed; if the XOR lands on 0 the mixer
  // still behaves, so no special case is needed.
  const uint64_t eseed = seed ^ ContentHash(data, length);
  for (size_t i = 0; i < length; ++i) {
    if ((i & 3u) == 3u) {
      continue;  // skip alpha
    }
    if (DeriveUnit(eseed, "canvas-gate", i) >= density) {
      continue;  // channel not selected this session
    }
    const int32_t delta = DeriveDelta(eseed, "canvas", i, strength);
    int32_t v = static_cast<int32_t>(data[i]) + delta;
    data[i] = static_cast<uint8_t>(v < 0 ? 0 : (v > 255 ? 255 : v));
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

}  // namespace camoucfg

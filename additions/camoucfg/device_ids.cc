// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/device_ids.h"

#include <cstdint>
#include <string>
#include <string_view>

namespace camoucfg {
namespace {

// FNV-1a-64, folded byte-by-byte -- same construction as canvas_noise.cc's
// ContentHash and audio_noise.cc's ContentHash.
uint64_t FnvMixByte(uint64_t h, uint8_t b) {
  h ^= b;
  h *= 0x100000001B3ULL;
  return h;
}

uint64_t FnvMixBytes(uint64_t h, std::string_view s) {
  for (char c : s) {
    h = FnvMixByte(h, static_cast<uint8_t>(c));
  }
  return h;
}

uint64_t FnvMixU64(uint64_t h, uint64_t v) {
  for (int i = 0; i < 8; ++i) {
    h = FnvMixByte(h, static_cast<uint8_t>(v >> (i * 8)));
  }
  return h;
}

// One 64-bit draw over (seed, kind, real_id, origin, round). NUL-byte
// separators between the variable-length fields stop "a"+"bc" from hashing
// the same as "ab"+"c". `round` is folded FIRST, before any of the other
// fields, so the 4 rounds' hash states diverge immediately and that
// divergence is scrambled by every subsequent XOR/multiply step. Folding
// `round` last instead would leave the 4 output words related by a fixed,
// precomputable delta (mod 2^64) -- the low byte of `round` is the only
// thing that differs between rounds, so XOR-then-multiply-by-a-constant
// (with nothing after it) preserves that difference as an exact constant,
// which is a perfect "is this camoucrome" oracle from a single id and
// exactly the shape indistinguishability this helper exists to provide.
uint64_t HashRound(uint64_t seed, std::string_view kind,
                   std::string_view real_id, std::string_view origin,
                   uint32_t round) {
  uint64_t h = 0xCBF29CE484222325ULL;  // FNV-1a-64 offset basis
  h = FnvMixU64(h, round);
  h = FnvMixByte(h, 0);
  h = FnvMixU64(h, seed);
  h = FnvMixByte(h, 0);
  h = FnvMixBytes(h, kind);
  h = FnvMixByte(h, 0);
  h = FnvMixBytes(h, real_id);
  h = FnvMixByte(h, 0);
  h = FnvMixBytes(h, origin);
  return h;
}

}  // namespace

std::string SyntheticDeviceId(uint64_t seed, std::string_view kind,
                              std::string_view real_id,
                              std::string_view origin) {
  if (seed == 0 || real_id.empty()) {
    return std::string(real_id);
  }
  if (real_id == "default") {
    return std::string(real_id);
  }
  static constexpr char kHex[] = "0123456789abcdef";
  std::string out;
  out.reserve(64);
  for (uint32_t round = 0; round < 4; ++round) {
    const uint64_t h = HashRound(seed, kind, real_id, origin, round);
    for (int nibble = 15; nibble >= 0; --nibble) {
      out.push_back(kHex[(h >> (nibble * 4)) & 0xF]);
    }
  }
  return out;
}

}  // namespace camoucfg

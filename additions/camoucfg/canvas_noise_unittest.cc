// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/canvas_noise.h"

#include <cstdint>
#include <vector>

#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg {
namespace {

// A deterministic non-uniform RGBA buffer to perturb. Uniform buffers hash to
// the same content and hide content-dependence bugs, so vary the bytes.
std::vector<uint8_t> Scene(size_t pixels) {
  std::vector<uint8_t> v(pixels * 4);
  for (size_t i = 0; i < v.size(); ++i)
    v[i] = static_cast<uint8_t>((i * 37 + 11) & 0xFF);
  return v;
}

TEST(PerturbRgbaTest, SameInputsGiveSameOutput) {
  // The determinism guarantee: two readbacks of one canvas are byte-identical.
  auto a = Scene(64), b = Scene(64);
  PerturbRgba(a.data(), a.size(), /*seed=*/12345, /*density=*/0.5, /*strength=*/2);
  PerturbRgba(b.data(), b.size(), 12345, 0.5, 2);
  EXPECT_EQ(a, b);
}

TEST(PerturbRgbaTest, SeedZeroIsNoOp) {
  auto a = Scene(64), orig = Scene(64);
  PerturbRgba(a.data(), a.size(), /*seed=*/0, 0.5, 2);
  EXPECT_EQ(a, orig);  // byte-identical to stock when spoof is off
}

TEST(PerturbRgbaTest, DensityZeroIsNoOp) {
  auto a = Scene(64), orig = Scene(64);
  PerturbRgba(a.data(), a.size(), 12345, /*density=*/0.0, 2);
  EXPECT_EQ(a, orig);
}

TEST(PerturbRgbaTest, ActuallyChangesSomePixels) {
  auto a = Scene(256), orig = Scene(256);
  PerturbRgba(a.data(), a.size(), 12345, /*density=*/0.5, 2);
  EXPECT_NE(a, orig) << "high density left every pixel untouched";
}

TEST(PerturbRgbaTest, AlphaChannelNeverChanges) {
  auto a = Scene(256), orig = Scene(256);
  PerturbRgba(a.data(), a.size(), 12345, /*density=*/1.0, 4);
  for (size_t i = 3; i < a.size(); i += 4)
    EXPECT_EQ(a[i], orig[i]) << "alpha byte " << i << " was perturbed";
}

TEST(PerturbRgbaTest, DeltaStaysWithinStrength) {
  auto a = Scene(256), orig = Scene(256);
  PerturbRgba(a.data(), a.size(), 12345, /*density=*/1.0, /*strength=*/3);
  for (size_t i = 0; i < a.size(); ++i) {
    if ((i & 3u) == 3u) continue;  // alpha untouched
    int d = static_cast<int>(a[i]) - static_cast<int>(orig[i]);
    EXPECT_GE(d, -3);
    EXPECT_LE(d, 3);
  }
}

TEST(PerturbRgbaTest, DifferentDrawingsGetDifferentNoiseFields) {
  // Content-hash fold (§7.3 decision A): the SAME seed on two DIFFERENT
  // drawings must diverge, so an attacker cannot map the field once and
  // subtract it from every later readback. Build two scenes differing in one
  // early byte (inside the 1024-byte content-hash window) and perturb both
  // with one seed; the noise fields must differ somewhere.
  auto a = Scene(256);
  auto b = Scene(256);
  b[0] ^= 0xFF;  // change content within the hashed prefix
  auto a_orig = a, b_orig = b;
  PerturbRgba(a.data(), a.size(), 777, 0.5, 2);
  PerturbRgba(b.data(), b.size(), 777, 0.5, 2);
  // Compare the deltas, not the pixels (b started one byte different).
  bool fields_differ = false;
  for (size_t i = 1; i < a.size(); ++i) {  // skip the byte we changed
    int da = static_cast<int>(a[i]) - static_cast<int>(a_orig[i]);
    int db = static_cast<int>(b[i]) - static_cast<int>(b_orig[i]);
    if (da != db) { fields_differ = true; break; }
  }
  EXPECT_TRUE(fields_differ) << "noise field ignores content; map-and-subtract "
                               "would defeat it";
}

TEST(PerturbRgbaTest, ShortBufferIsNoOp) {
  std::vector<uint8_t> tiny = {1, 2, 3};  // length < 4
  auto orig = tiny;
  PerturbRgba(tiny.data(), tiny.size(), 12345, 1.0, 2);
  EXPECT_EQ(tiny, orig);
}

}  // namespace
}  // namespace camoucfg

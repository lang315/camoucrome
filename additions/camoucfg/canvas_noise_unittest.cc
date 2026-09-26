// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/canvas_noise.h"

#include <cmath>
#include <cstdint>
#include <limits>
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
  // Opaque: only alpha == 255 pixels are ever perturbed.
  for (size_t i = 3; i < v.size(); i += 4)
    v[i] = 255;
  return v;
}

// Copies the w x h rect at (x, y) out of a `full_w`-wide RGBA buffer.
std::vector<uint8_t> Crop(const std::vector<uint8_t>& full, size_t full_w,
                          size_t x, size_t y, size_t w, size_t h) {
  std::vector<uint8_t> out;
  for (size_t r = 0; r < h; ++r) {
    const size_t start = ((y + r) * full_w + x) * 4;
    out.insert(out.end(), full.begin() + start, full.begin() + start + w * 4);
  }
  return out;
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

// Review 2026-09-24 #2: the noise of a pixel is a function of its canvas
// position, so a sub-rectangle read agrees with a full read of the same state.
TEST(PerturbRgbaAtTest, SubRectAgreesWithFullRead) {
  auto full = Scene(16 * 16);
  const auto orig = full;
  PerturbRgbaAt(full.data(), 16, 16, 16 * 4, 0, 0, /*seed=*/99, 1.0, 2);
  auto part = Crop(orig, 16, 5, 7, 3, 4);
  PerturbRgbaAt(part.data(), 3, 4, 3 * 4, 5, 7, /*seed=*/99, 1.0, 2);
  EXPECT_EQ(part, Crop(full, 16, 5, 7, 3, 4));
  EXPECT_NE(full, orig);
}

// Review #3: stock never produces RGB != 0 under alpha 0, nor unpremultiplied
// values off the grid a partial alpha implies. Only opaque pixels move.
TEST(PerturbRgbaAtTest, NonOpaquePixelsAreUntouched) {
  std::vector<uint8_t> px = {0, 0, 0, 0,  10, 20, 30, 128,  40, 50, 60, 255};
  const auto orig = px;
  bool opaque_moved = false;
  for (uint64_t seed = 1; seed < 64 && !opaque_moved; ++seed) {
    px = orig;
    PerturbRgbaAt(px.data(), 3, 1, 12, 0, 0, seed, 1.0, 3);
    EXPECT_EQ(std::vector<uint8_t>(px.begin(), px.begin() + 8),
              std::vector<uint8_t>(orig.begin(), orig.begin() + 8));
    opaque_moved = px != orig;
  }
  EXPECT_TRUE(opaque_moved);
}

// Review #9: out-of-range strength/density are clamped, never overflow.
TEST(PerturbRgbaAtTest, ExtremeParametersAreClamped) {
  // A negative strength clamps to 0: no noise (unclamped, |INT_MIN| = 2^31
  // was a live bound and pixel + delta overflowed int32).
  auto a = Scene(64);
  const auto orig = a;
  PerturbRgbaAt(a.data(), 8, 8, 32, 0, 0, 7, 1.0,
                std::numeric_limits<int32_t>::min());
  EXPECT_EQ(a, orig);
  // Density above 1 is density 1.
  auto b = Scene(64), c = Scene(64);
  PerturbRgbaAt(b.data(), 8, 8, 32, 0, 0, 7, /*density=*/50.0, 2);
  PerturbRgbaAt(c.data(), 8, 8, 32, 0, 0, 7, /*density=*/1.0, 2);
  EXPECT_EQ(b, c);
}

// Review #4: the state hash covers the whole canvas, not its first 1 KB.
TEST(CanvasStateHashTest, SeesLateContentAndIsDeterministic) {
  auto a = Scene(64 * 64), b = a;
  b[b.size() - 8] ^= 0x55;  // last row
  EXPECT_EQ(CanvasStateHash(a.data(), 64, 64, 64 * 4),
            CanvasStateHash(a.data(), 64, 64, 64 * 4));
  EXPECT_NE(CanvasStateHash(a.data(), 64, 64, 64 * 4),
            CanvasStateHash(b.data(), 64, 64, 64 * 4));
}

TEST(PerturbRgbaTest, ShortBufferIsNoOp) {
  std::vector<uint8_t> tiny = {1, 2, 3};  // length < 4
  auto orig = tiny;
  PerturbRgba(tiny.data(), tiny.size(), 12345, 1.0, 2);
  EXPECT_EQ(tiny, orig);
}

TEST(CanvasNoiseTest, NoOpWhenSeedZero) {
  // seed == 0 -> stock unchanged, for both a fractional and an integer field
  // (rule 5: no canvas:seed -> real value).
  EXPECT_EQ(PerturbMetric(148.04, 0, 99, "tm.w"), 148.04);
  EXPECT_EQ(PerturbMetric(45.0, 0, 99, "tm.fa"), 45.0);
}

TEST(CanvasNoiseTest, ZeroGuard) {
  // A real Chrome returns exact 0 for empty ink / empty string / zero
  // baseline; jittering it would be a tell, not a spoof.
  EXPECT_EQ(PerturbMetric(0.0, 1234, 99, "tm.d"), 0.0);
}

TEST(CanvasNoiseTest, IntegerStaysInteger) {
  // Integer fields land on the integer grid: DeriveDelta(..., bound=1) is
  // whole, so stock + delta stays whole and within +-1.
  for (uint64_t seed : {1ULL, 2ULL, 1234ULL, 0xDEADBEEFULL}) {
    for (uint64_t i = 0; i < 20; ++i) {
      const double result = PerturbMetric(45.0, seed, i, "tm.fa");
      EXPECT_EQ(result, std::trunc(result))
          << "seed=" << seed << " index=" << i;
      EXPECT_LE(std::abs(result - 45.0), 1.0) << "seed=" << seed << " index=" << i;
    }
  }
}

TEST(CanvasNoiseTest, FractionalStaysDyadicAndBounded) {
  // Fractional fields land on a 1/64 grid, bounded to +-8/64 = 0.125 px.
  constexpr double kStock = 148.0458984375;
  for (uint64_t seed : {1ULL, 2ULL, 1234ULL, 0xDEADBEEFULL}) {
    for (uint64_t i = 0; i < 20; ++i) {
      const double r = PerturbMetric(kStock, seed, i, "tm.w");
      EXPECT_LE(std::abs(r - kStock), 0.125 + 1e-9)
          << "seed=" << seed << " index=" << i;
      const double scaled_delta = (r - kStock) * 64.0;
      EXPECT_LT(std::abs(scaled_delta - std::round(scaled_delta)), 1e-9)
          << "delta is not a multiple of 1/64 at seed=" << seed
          << " index=" << i;
    }
  }
}

TEST(CanvasNoiseTest, Deterministic) {
  // Same (stock, seed, index, domain) yields the same output: a page
  // re-measuring the same (text, font) sees identical metrics.
  EXPECT_EQ(PerturbMetric(148.0458984375, 777, 42, "tm.w"),
            PerturbMetric(148.0458984375, 777, 42, "tm.w"));
  EXPECT_EQ(PerturbMetric(45.0, 777, 42, "tm.fa"),
            PerturbMetric(45.0, 777, 42, "tm.fa"));
}

TEST(CanvasNoiseTest, DomainSeparationAndSpread) {
  // Spread: across many indices with one fixed seed, the deltas must not all
  // be identical -- a constant-delta mutant (sp3a ledger M2) would pass every
  // other test here but fail this one.
  constexpr double kStock = 148.0458984375;
  constexpr uint64_t kSeed = 555;
  double first = PerturbMetric(kStock, kSeed, 0, "tm.w");
  bool spread = false;
  for (uint64_t i = 1; i < 30; ++i) {
    if (PerturbMetric(kStock, kSeed, i, "tm.w") != first) {
      spread = true;
      break;
    }
  }
  EXPECT_TRUE(spread) << "deltas are constant across indices";

  // Domain separation: two different domains must diverge for at least some
  // (seed, index) samples, since each field derives its delta independently.
  bool domains_differ = false;
  for (uint64_t i = 0; i < 30; ++i) {
    const double a = PerturbMetric(kStock, kSeed, i, "tm.w");
    const double b = PerturbMetric(kStock, kSeed, i, "tm.fda");
    if (a != b) {
      domains_differ = true;
      break;
    }
  }
  EXPECT_TRUE(domains_differ) << "domain has no effect on the derived delta";

  // Seed separation: two different seeds must diverge for at least some
  // indices, since the delta is keyed on seed -- guards a mutant that derives
  // the delta from (domain, index) alone and ignores `seed`.
  bool seeds_differ = false;
  for (uint64_t i = 0; i < 30; ++i) {
    const double a = PerturbMetric(kStock, kSeed, i, "tm.w");
    const double b = PerturbMetric(kStock, kSeed + 1, i, "tm.w");
    if (a != b) {
      seeds_differ = true;
      break;
    }
  }
  EXPECT_TRUE(seeds_differ) << "seed has no effect on the derived delta";
}

}  // namespace
}  // namespace camoucfg

// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/canvas_noise.h"

#include <algorithm>
#include <array>
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

TEST(PerturbRgbaTest, SameInputsGiveSameOutput) {
  // The determinism guarantee: two readbacks of one canvas are byte-identical.
  auto a = Scene(64), b = Scene(64);
  PerturbRgba(a.data(), 8, 8, 8 * 4, /*seed=*/12345, /*density=*/0.5, /*strength=*/2, /*bottom_up=*/false);
  PerturbRgba(b.data(), 8, 8, 8 * 4, 12345, 0.5, 2, /*bottom_up=*/false);
  EXPECT_EQ(a, b);
}

TEST(PerturbRgbaTest, SeedZeroIsNoOp) {
  auto a = Scene(64), orig = Scene(64);
  PerturbRgba(a.data(), 8, 8, 8 * 4, /*seed=*/0, 0.5, 2, /*bottom_up=*/false);
  EXPECT_EQ(a, orig);  // byte-identical to stock when spoof is off
}

TEST(PerturbRgbaTest, DensityZeroIsNoOp) {
  auto a = Scene(64), orig = Scene(64);
  PerturbRgba(a.data(), 8, 8, 8 * 4, 12345, /*density=*/0.0, 2, /*bottom_up=*/false);
  EXPECT_EQ(a, orig);
}

TEST(PerturbRgbaTest, ActuallyChangesSomePixels) {
  auto a = Scene(256), orig = Scene(256);
  PerturbRgba(a.data(), 16, 16, 16 * 4, 12345, /*density=*/0.5, 2, /*bottom_up=*/false);
  EXPECT_NE(a, orig) << "high density left every pixel untouched";
}

TEST(PerturbRgbaTest, AlphaChannelNeverChanges) {
  auto a = Scene(256), orig = Scene(256);
  PerturbRgba(a.data(), 16, 16, 16 * 4, 12345, /*density=*/1.0, 4, /*bottom_up=*/false);
  for (size_t i = 3; i < a.size(); i += 4)
    EXPECT_EQ(a[i], orig[i]) << "alpha byte " << i << " was perturbed";
}

TEST(PerturbRgbaTest, DeltaStaysWithinStrength) {
  auto a = Scene(256), orig = Scene(256);
  PerturbRgba(a.data(), 16, 16, 16 * 4, 12345, /*density=*/1.0, /*strength=*/3, /*bottom_up=*/false);
  for (size_t i = 0; i < a.size(); ++i) {
    if ((i & 3u) == 3u) continue;  // alpha untouched
    int d = static_cast<int>(a[i]) - static_cast<int>(orig[i]);
    EXPECT_GE(d, -3);
    EXPECT_LE(d, 3);
  }
}

TEST(PerturbRgbaTest, PaddedRowsGetTheTightField) {
  // One pixel content gets one field whatever the row padding: a padded
  // readPixels (PACK_ALIGNMENT 8, odd width) matches the tight read, and the
  // padding bytes are never touched.
  constexpr size_t kW = 7, kH = 5;
  auto tight = Scene(kW * kH);
  std::vector<uint8_t> padded(kH * 32, 0xAB);
  for (size_t y = 0; y < kH; ++y)
    std::copy_n(tight.begin() + y * kW * 4, kW * 4, padded.begin() + y * 32);
  PerturbRgba(tight.data(), kW, kH, kW * 4, 12345, 1.0, 3, /*bottom_up=*/false);
  PerturbRgba(padded.data(), kW, kH, 32, 12345, 1.0, 3, /*bottom_up=*/false);
  EXPECT_NE(tight, Scene(kW * kH));  // not vacuous
  for (size_t y = 0; y < kH; ++y) {
    EXPECT_TRUE(std::equal(tight.begin() + y * kW * 4,
                           tight.begin() + (y + 1) * kW * 4,
                           padded.begin() + y * 32));
    for (size_t i = kW * 4; i < 32; ++i)
      EXPECT_EQ(padded[y * 32 + i], 0xAB);
  }
}

TEST(PerturbRgbaTest, RowBytesBelowWidthIsNoOp) {
  auto a = Scene(64), orig = Scene(64);
  PerturbRgba(a.data(), 8, 8, 8 * 4 - 1, 12345, 1.0, 3, /*bottom_up=*/false);
  EXPECT_EQ(a, orig);
}

TEST(PerturbRgbaTest, ZeroSizeIsNoOp) {
  std::vector<uint8_t> tiny = {1, 2, 3};
  auto orig = tiny;
  PerturbRgba(tiny.data(), 0, 0, 0 * 4, 12345, 1.0, 2, /*bottom_up=*/false);
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

using Px = std::array<uint8_t, 4>;

std::vector<uint8_t> Fill(size_t w, size_t h, Px px) {
  std::vector<uint8_t> v;
  for (size_t i = 0; i < w * h; ++i)
    v.insert(v.end(), px.begin(), px.end());
  return v;
}

void Set(std::vector<uint8_t>& v, size_t w, size_t x, size_t y, Px px) {
  std::copy(px.begin(), px.end(), v.begin() + (y * w + x) * 4);
}

Px Get(const std::vector<uint8_t>& v, size_t w, size_t x, size_t y) {
  Px px;
  std::copy_n(v.begin() + (y * w + x) * 4, 4, px.begin());
  return px;
}

// PerturbRgbaEdges on `v`, with an unperturbed copy of it as the source.
void Edges(std::vector<uint8_t>& v, size_t w, size_t h, uint64_t seed,
           double density, int32_t strength, uint8_t min_alpha = 1) {
  const std::vector<uint8_t> source = v;
  PerturbRgbaEdges(v.data(), source.data(), w, h, w * 4, seed, density,
                   strength, min_alpha, NoiseMask(), /*bottom_up=*/false);
}

// A buffer whose every pixel differs from its neighbours, with partial alpha
// (premultiplied: each channel at most alpha) and alpha 0 on (x + y) % 3 == 0.
std::vector<uint8_t> PartialAlphaScene(size_t w, size_t h) {
  std::vector<uint8_t> v(w * h * 4);
  for (size_t y = 0; y < h; ++y) {
    for (size_t x = 0; x < w; ++x) {
      const uint8_t a =
          (x + y) % 3 == 0 ? 0 : static_cast<uint8_t>(1 + (x * 37 + y * 11) % 254);
      Set(v, w, x, y,
          {static_cast<uint8_t>((x * 13 + y * 7) % (a + 1)),
           static_cast<uint8_t>((x * 5 + y * 17 + 3) % (a + 1)),
           static_cast<uint8_t>((x * 11 + y * 3 + 9) % (a + 1)), a});
    }
  }
  return v;
}

// S1: a one-colour fill has no pixel unlike its neighbours.
TEST(PerturbRgbaEdgesTest, OneColourBufferIsUnchanged) {
  auto v = Fill(16, 16, {10, 20, 30, 255});
  const auto orig = v;
  for (uint64_t seed = 1; seed < 32; ++seed)
    Edges(v, 16, 16, seed, 1.0, 3);
  EXPECT_EQ(v, orig);
}

// A 2-pixel pair: each of its pixels has one same-coloured neighbour, as on a
// hard edge or a 1px line.
TEST(PerturbRgbaEdgesTest, PixelWithOneSameNeighbourIsUnchanged) {
  auto v = Fill(8, 8, {0, 0, 0, 255});
  Set(v, 8, 3, 4, {200, 100, 50, 255});
  Set(v, 8, 4, 4, {200, 100, 50, 255});
  const auto orig = v;
  for (uint64_t seed = 1; seed < 32; ++seed)
    Edges(v, 8, 8, seed, 1.0, 3);
  EXPECT_EQ(v, orig);
}

TEST(PerturbRgbaEdgesTest, PixelUnlikeAllFourNeighboursChanges) {
  auto v = Fill(8, 8, {0, 0, 0, 255});
  Set(v, 8, 4, 4, {200, 100, 50, 255});
  const auto orig = v;
  bool changed = false;
  for (uint64_t seed = 1; seed < 32 && !changed; ++seed) {
    v = orig;
    Edges(v, 8, 8, seed, 1.0, 3);
    auto rest = v;
    Set(rest, 8, 4, 4, {200, 100, 50, 255});
    EXPECT_EQ(rest, orig) << "a pixel other than the lone one moved";
    changed = v != orig;
  }
  EXPECT_TRUE(changed);
}

// A pixel on the buffer's border has fewer than four neighbours: never touched.
TEST(PerturbRgbaEdgesTest, BorderPixelsAreUntouched) {
  std::vector<uint8_t> v(6 * 6 * 4);
  for (size_t y = 0; y < 6; ++y)
    for (size_t x = 0; x < 6; ++x)
      Set(v, 6, x, y, (x + y) % 2 ? Px{200, 100, 50, 255} : Px{10, 20, 30, 255});
  const auto orig = v;
  Edges(v, 6, 6, 7, 1.0, 3);
  for (size_t y = 0; y < 6; ++y)
    for (size_t x = 0; x < 6; ++x)
      if (x == 0 || y == 0 || x == 5 || y == 5)
        EXPECT_EQ(Get(v, 6, x, y), Get(orig, 6, x, y)) << x << "," << y;
  EXPECT_NE(v, orig) << "the checkerboard's interior did not move";
}

// Alpha 0 never changes; a partial-alpha pixel moves but stays a valid
// premultiplied value, which Skia unpremultiplies onto stock's grid.
TEST(PerturbRgbaEdgesTest, PartialAlphaStaysPremultiplied) {
  auto v = PartialAlphaScene(16, 16);
  const auto orig = v;
  Edges(v, 16, 16, 99, 1.0, 3);
  bool partial_moved = false;
  for (size_t y = 0; y < 16; ++y) {
    for (size_t x = 0; x < 16; ++x) {
      const Px got = Get(v, 16, x, y), was = Get(orig, 16, x, y);
      EXPECT_EQ(got[3], was[3]);
      if (was[3] == 0) {
        EXPECT_EQ(got, was);
        continue;
      }
      for (size_t ch = 0; ch < 3; ++ch)
        EXPECT_LE(got[ch], got[3]) << x << "," << y << " ch " << ch;
      partial_moved |= was[3] < 255 && got != was;
    }
  }
  EXPECT_TRUE(partial_moved);
}

// min_alpha 255 (the WebGL path, whose data may be unpremultiplied): only
// opaque pixels move.
TEST(PerturbRgbaEdgesTest, MinAlpha255LeavesPartialAlphaAlone) {
  auto v = PartialAlphaScene(16, 16);
  const auto orig = v;
  Edges(v, 16, 16, 99, 1.0, 3, /*min_alpha=*/255);
  EXPECT_EQ(v, orig);
}

TEST(PerturbRgbaEdgesTest, NoOpWithoutSeedDensityOrStrength) {
  auto v = PartialAlphaScene(16, 16);
  const auto orig = v;
  Edges(v, 16, 16, /*seed=*/0, 1.0, 3);
  Edges(v, 16, 16, 99, /*density=*/0.0, 3);
  Edges(v, 16, 16, 99, std::numeric_limits<double>::quiet_NaN(), 3);
  Edges(v, 16, 16, 99, 1.0, /*strength=*/0);
  EXPECT_EQ(v, orig);
}

// Review #9: out-of-range strength/density are clamped, never overflow.
TEST(PerturbRgbaEdgesTest, ExtremeParametersAreClamped) {
  // A negative strength clamps to 0: no noise (unclamped, |INT_MIN| = 2^31
  // was a live bound and pixel + delta overflowed int32).
  auto a = Scene(64);
  const auto orig = a;
  Edges(a, 8, 8, 7, 1.0, std::numeric_limits<int32_t>::min());
  EXPECT_EQ(a, orig);
  // Density above 1 is density 1.
  auto b = Scene(64), c = Scene(64);
  Edges(b, 8, 8, 7, 50.0, 2);
  Edges(c, 8, 8, 7, 1.0, 2);
  EXPECT_EQ(b, c);
}

TEST(CanvasNoiseTest, TextOffsetIsPerSeedAndSubPixel) {
  EXPECT_EQ(TextOffset(0), (std::array<float, 2>{0.0f, 0.0f}));
  bool varies = false;
  for (uint64_t seed = 1; seed < 64; ++seed) {
    const std::array<float, 2> o = TextOffset(seed);
    EXPECT_EQ(o, TextOffset(seed));
    for (float v : o) {
      EXPECT_GE(v, 0.0f);
      EXPECT_LT(v, 1.0f);
    }
    varies |= o != TextOffset(1);
  }
  EXPECT_TRUE(varies);
}

// S2b: the noise is keyed by the 3x3 source patch, not by position. One
// lone pixel at two places gets the same delta.
TEST(PerturbRgbaEdgesTest, SamePatchGetsSameNoiseAnywhere) {
  for (uint64_t seed = 1; seed <= 8; ++seed) {
    auto v = Fill(16, 8, {0, 0, 0, 255});
    Set(v, 16, 3, 3, {200, 100, 50, 255});
    Set(v, 16, 11, 4, {200, 100, 50, 255});
    Edges(v, 16, 8, seed, 1.0, 3);
    EXPECT_EQ(Get(v, 16, 3, 3), Get(v, 16, 11, 4)) << "seed " << seed;
  }
}

// A bottom-up buffer (WebGL readPixels) gets the field of the same image
// stored top-down.
TEST(PerturbRgbaEdgesTest, BottomUpMatchesTopDown) {
  auto flip = [](const std::vector<uint8_t>& v, size_t w, size_t h) {
    std::vector<uint8_t> o(v.size());
    for (size_t y = 0; y < h; ++y)
      std::copy_n(v.begin() + y * w * 4, w * 4, o.begin() + (h - 1 - y) * w * 4);
    return o;
  };
  const auto top = PartialAlphaScene(9, 7);
  auto a = top;
  auto b = flip(top, 9, 7);
  const auto sa = a, sb = b;
  PerturbRgbaEdges(a.data(), sa.data(), 9, 7, 36, 77, 1.0, 3, 1, NoiseMask(),
                   /*bottom_up=*/false);
  PerturbRgbaEdges(b.data(), sb.data(), 9, 7, 36, 77, 1.0, 3, 1, NoiseMask(),
                   /*bottom_up=*/true);
  EXPECT_NE(a, top);
  EXPECT_EQ(flip(b, 9, 7), a);
}

// Only cells holding exactly kNoiseMaskAa may change; imported wins.
TEST(PerturbRgbaEdgesTest, MaskGatesEachPixel) {
  auto v = Fill(8, 8, {0, 0, 0, 255});
  Set(v, 8, 2, 2, {200, 100, 50, 255});
  Set(v, 8, 5, 5, {200, 100, 50, 255});
  std::vector<uint8_t> cells(64, 0);
  cells[2 * 8 + 2] = kNoiseMaskAa;
  cells[5 * 8 + 5] = kNoiseMaskAa | kNoiseMaskImported;
  const NoiseMask mask{cells.data(), 8, 0, 8, 8};
  bool moved = false;
  for (uint64_t seed = 1; seed < 32; ++seed) {
    auto w = v;
    PerturbRgbaEdges(w.data(), v.data(), 8, 8, 32, seed, 1.0, 3, 1, mask, false);
    auto rest = w;
    Set(rest, 8, 2, 2, {200, 100, 50, 255});
    EXPECT_EQ(rest, v) << "a pixel outside the aa cell moved, seed " << seed;
    moved |= w != v;
  }
  EXPECT_TRUE(moved);
}

// Above the full-resolution cap one cell covers 4 x 4 pixels.
TEST(PerturbRgbaEdgesTest, CoarseMaskCellCoversItsPixels) {
  auto v = Fill(8, 8, {0, 0, 0, 255});
  Set(v, 8, 2, 2, {200, 100, 50, 255});
  Set(v, 8, 6, 6, {200, 100, 50, 255});
  const std::vector<uint8_t> cells = {kNoiseMaskAa, 0, 0, 0};
  const NoiseMask mask{cells.data(), 2, 2, 8, 8};
  bool moved = false;
  for (uint64_t seed = 1; seed < 32; ++seed) {
    auto w = v;
    PerturbRgbaEdges(w.data(), v.data(), 8, 8, 32, seed, 1.0, 3, 1, mask, false);
    EXPECT_EQ(Get(w, 8, 6, 6), Get(v, 8, 6, 6)) << "seed " << seed;
    moved |= w != v;
  }
  EXPECT_TRUE(moved);
}

// A mask for another size never applies: no pixel changes.
TEST(PerturbRgbaEdgesTest, MaskOfAnotherSizeIsNoOp) {
  auto v = Fill(8, 8, {0, 0, 0, 255});
  Set(v, 8, 4, 4, {200, 100, 50, 255});
  const std::vector<uint8_t> cells(7 * 8, kNoiseMaskAa);
  const NoiseMask mask{cells.data(), 7, 0, 7, 8};
  auto w = v;
  PerturbRgbaEdges(w.data(), v.data(), 8, 8, 32, 7, 1.0, 3, 1, mask, false);
  EXPECT_EQ(w, v);
}

// S2b: a sub-rect read gets the matching part of a full read, away from
// the sub-rect's own border (Blink supplies that border from the buffer).
TEST(PerturbRgbaTest, SubRectInteriorMatchesFullRead) {
  auto full = Scene(16 * 16);
  std::vector<uint8_t> sub(8 * 8 * 4);
  for (size_t y = 0; y < 8; ++y)
    std::copy_n(full.begin() + ((y + 4) * 16 + 4) * 4, 32, sub.begin() + y * 32);
  PerturbRgba(full.data(), 16, 16, 64, 12345, 1.0, 3, /*bottom_up=*/true);
  PerturbRgba(sub.data(), 8, 8, 32, 12345, 1.0, 3, /*bottom_up=*/true);
  EXPECT_NE(full, Scene(16 * 16));
  for (size_t y = 1; y < 7; ++y)
    for (size_t x = 1; x < 7; ++x)
      EXPECT_EQ(Get(sub, 8, x, y), Get(full, 16, x + 4, y + 4)) << x << "," << y;
}

// A mask is for top-down 2D snapshots; with bottom_up it never applies.
TEST(PerturbRgbaEdgesTest, MaskWithBottomUpIsNoOp) {
  auto v = Fill(8, 8, {0, 0, 0, 255});
  Set(v, 8, 4, 4, {200, 100, 50, 255});
  const std::vector<uint8_t> cells(64, kNoiseMaskAa);
  const NoiseMask mask{cells.data(), 8, 0, 8, 8};
  auto w = v;
  PerturbRgbaEdges(w.data(), v.data(), 8, 8, 32, 7, 1.0, 3, 1, mask,
                   /*bottom_up=*/true);
  EXPECT_EQ(w, v);
}

}  // namespace
}  // namespace camoucfg

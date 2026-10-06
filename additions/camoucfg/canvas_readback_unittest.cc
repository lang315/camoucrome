// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/canvas_readback.h"

#include <cstdint>

#include "testing/gtest/include/gtest/gtest.h"
#include "third_party/skia/include/core/SkBitmap.h"
#include "third_party/skia/include/core/SkImage.h"

namespace camoucfg {
namespace {

// RGBA8 bytes as kRGBA_8888's in-memory order, packed for getAddr32.
uint32_t Pack(uint8_t r, uint8_t g, uint8_t b, uint8_t a) {
  return uint32_t{r} | uint32_t{g} << 8 | uint32_t{b} << 16 | uint32_t{a} << 24;
}

// A premultiplied RGBA8 raster image, pixel (x, y) = fn(x, y).
template <typename Fn>
sk_sp<SkImage> Image(int w, int h, Fn fn) {
  SkBitmap bm;
  bm.allocPixels(
      SkImageInfo::Make(w, h, kRGBA_8888_SkColorType, kPremul_SkAlphaType));
  for (int y = 0; y < h; ++y)
    for (int x = 0; x < w; ++x)
      *bm.getAddr32(x, y) = fn(x, y);
  bm.setImmutable();
  return SkImages::RasterFromBitmap(bm);
}

SkBitmap Read(const SkImage& image) {
  SkBitmap bm;
  bm.allocPixels(image.imageInfo());
  EXPECT_TRUE(image.readPixels(nullptr, bm.pixmap(), 0, 0));
  return bm;
}

uint32_t Partial(int x, int y) {
  const int a = 1 + (x * 37 + y * 11) % 254;
  return Pack(static_cast<uint8_t>((x * 13 + y * 7) % (a + 1)),
              static_cast<uint8_t>((x * 5 + y * 17 + 3) % (a + 1)),
              static_cast<uint8_t>((x * 11 + y * 3 + 9) % (a + 1)),
              static_cast<uint8_t>(a));
}

TEST(NoisedImageTest, SeedZeroIsNull) {
  EXPECT_EQ(NoisedImage(*Image(8, 8, Partial), 0, 1.0, 2, 1, NoiseMask(), false), nullptr);
}

TEST(NoisedImageTest, FloatImageIsNull) {
  SkBitmap bm;
  bm.allocPixels(SkImageInfo::Make(8, 8, kRGBA_F16_SkColorType,
                                   kPremul_SkAlphaType));
  bm.eraseColor(SK_ColorRED);
  bm.setImmutable();
  EXPECT_EQ(NoisedImage(*SkImages::RasterFromBitmap(bm), 7, 1.0, 2, 1, NoiseMask(),
                         false), nullptr);
}

// S1 through the whole Skia path: a one-colour canvas reads back unchanged.
TEST(NoisedImageTest, OneColourImageReadsAsStock) {
  const sk_sp<SkImage> noised =
      NoisedImage(*Image(16, 16, [](int, int) { return Pack(10, 20, 30, 255); }),
                  7, 1.0, 3, /*min_alpha=*/1, NoiseMask(), /*bottom_up=*/false);
  ASSERT_NE(noised, nullptr);
  const SkBitmap got = Read(*noised);
  for (int y = 0; y < 16; ++y)
    for (int x = 0; x < 16; ++x)
      EXPECT_EQ(*got.getAddr32(x, y), Pack(10, 20, 30, 255));
}

// Partial alpha moves and stays premultiplied: alpha kept, channels <= alpha.
TEST(NoisedImageTest, PartialAlphaStaysPremultiplied) {
  const sk_sp<SkImage> noised = NoisedImage(*Image(16, 16, Partial), 7, 1.0, 3, /*min_alpha=*/1,
                  NoiseMask(), /*bottom_up=*/false);
  ASSERT_NE(noised, nullptr);
  const SkBitmap got = Read(*noised);
  bool moved = false;
  for (int y = 0; y < 16; ++y) {
    for (int x = 0; x < 16; ++x) {
      const uint32_t p = *got.getAddr32(x, y), was = Partial(x, y);
      const uint32_t a = p >> 24;
      EXPECT_EQ(a, was >> 24);
      for (int sh = 0; sh < 24; sh += 8)
        EXPECT_LE((p >> sh) & 0xFF, a) << x << "," << y;
      moved |= p != was;
    }
  }
  EXPECT_TRUE(moved);
}

// S2b: drawing elsewhere does not change a pixel's noise; there is no
// whole-canvas state in the key.
TEST(NoisedImageTest, EditElsewhereKeepsAPixelsNoise) {
  auto lone = [](int x, int y) {
    return x == 3 && y == 3 ? Pack(200, 100, 50, 255) : Pack(0, 0, 0, 255);
  };
  auto lone_plus = [](int x, int y) {
    return (x == 3 && y == 3) || (x == 12 && y == 12) ? Pack(200, 100, 50, 255)
                                                      : Pack(0, 0, 0, 255);
  };
  bool moved = false;
  for (uint64_t seed = 1; seed <= 8; ++seed) {
    const SkBitmap a =
        Read(*NoisedImage(*Image(16, 16, lone), seed, 1.0, 3, 1, NoiseMask(), false));
    const SkBitmap b =
        Read(*NoisedImage(*Image(16, 16, lone_plus), seed, 1.0, 3, 1, NoiseMask(),
                          false));
    EXPECT_EQ(*a.getAddr32(3, 3), *b.getAddr32(3, 3)) << "seed " << seed;
    moved |= *a.getAddr32(3, 3) != Pack(200, 100, 50, 255);
  }
  EXPECT_TRUE(moved);
}

// The WebGL snapshot passes min_alpha 255: partial alpha stays as is.
TEST(NoisedImageTest, MinAlpha255LeavesPartialAlpha) {
  const sk_sp<SkImage> noised =
      NoisedImage(*Image(16, 16, Partial), 7, 1.0, 3, 255, NoiseMask(), false);
  ASSERT_NE(noised, nullptr);
  const SkBitmap got = Read(*noised);
  for (int y = 0; y < 16; ++y)
    for (int x = 0; x < 16; ++x)
      EXPECT_EQ(*got.getAddr32(x, y), Partial(x, y)) << x << "," << y;
}

}  // namespace
}  // namespace camoucfg

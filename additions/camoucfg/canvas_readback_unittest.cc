// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/canvas_readback.h"

#include <algorithm>
#include <cstdint>
#include <vector>

#include "base/containers/span.h"
#include "testing/gtest/include/gtest/gtest.h"
#include "third_party/skia/include/core/SkBitmap.h"
#include "third_party/skia/include/core/SkImage.h"
#include "third_party/skia/include/core/SkPixmap.h"

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

// NoisedRegion over a raster image.
SkBitmap Region(const SkImage& image, const SkIRect& r, uint64_t seed,
                double density, int32_t strength, uint8_t min_alpha,
                const NoiseMask& mask) {
  return NoisedRegion(
      image.imageInfo(),
      [&image](const SkPixmap& dst, int x, int y) {
        return image.readPixels(nullptr, dst, x, y);
      },
      r, seed, density, strength, min_alpha, mask);
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

// NoisedRegion returns exactly NoisedImage's bytes over any rect: interior,
// touching each edge, 1x1, and the whole canvas, premultiplied and
// unpremultiplied, with no mask, a fine mask and a coarse mask.
TEST(NoisedRegionTest, EqualsTheWholeImageField) {
  constexpr int kW = 37, kH = 29;
  for (SkAlphaType at : {kPremul_SkAlphaType, kUnpremul_SkAlphaType}) {
    for (int shift : {-1, 0, 2}) {
      SkBitmap bm;
      ASSERT_TRUE(bm.tryAllocPixels(
          SkImageInfo::Make(kW, kH, kRGBA_8888_SkColorType, at)));
      uint32_t s = 4242;
      // SAFETY: the bitmap owns computeByteSize() bytes at getPixels().
      const base::span<uint8_t> px = UNSAFE_BUFFERS(base::span<uint8_t>(
          static_cast<uint8_t*>(bm.getPixels()), bm.computeByteSize()));
      for (int y = 0; y < kH; ++y) {
        for (int x = 0; x < kW; ++x) {
          const base::span<uint8_t> p =
              px.subspan(static_cast<size_t>(y) * bm.rowBytes() +
                             static_cast<size_t>(x) * 4,
                         4u);
          for (int k = 0; k < 4; ++k) {
            s = s * 1103515245u + 12345u;
            p[k] = static_cast<uint8_t>(s >> 24);
          }
          p[3] = (x + y) % 5 == 0 ? static_cast<uint8_t>(p[3] | 1) : 255;
          if (at == kPremul_SkAlphaType) {
            for (int k = 0; k < 3; ++k) {
              p[k] = std::min(p[k], p[3]);
            }
          }
        }
      }
      bm.setImmutable();
      const sk_sp<SkImage> image = SkImages::RasterFromBitmap(bm);
      const int sh = std::max(shift, 0);
      const size_t cell = size_t{1} << sh;
      const size_t stride = (kW + cell - 1) / cell;
      std::vector<uint8_t> cells(stride * ((kH + cell - 1) / cell));
      for (size_t i = 0; i < cells.size(); ++i) {
        cells[i] = i % 3 == 2 ? kNoiseMaskImported : kNoiseMaskAa;
      }
      NoiseMask mask;
      if (shift >= 0) {
        mask = NoiseMask{cells.data(), stride, sh, kW, kH};
      }
      const sk_sp<SkImage> whole =
          NoisedImage(*image, 77, 0.5, 2, 1, mask, /*bottom_up=*/false);
      ASSERT_TRUE(whole);
      SkBitmap wb;
      ASSERT_TRUE(wb.tryAllocPixels(whole->imageInfo()));
      ASSERT_TRUE(whole->readPixels(nullptr, wb.pixmap(), 0, 0));
      // The vacuity guard: a no-op field would make every region "equal".
      int changed = 0;
      for (int y = 0; y < kH; ++y) {
        for (int x = 0; x < kW; ++x) {
          changed += *wb.getAddr32(x, y) != *bm.getAddr32(x, y);
        }
      }
      EXPECT_GT(changed, 0) << "shift " << shift;
      for (const SkIRect& r :
           {SkIRect::MakeXYWH(5, 4, 20, 15), SkIRect::MakeXYWH(0, 0, 9, 9),
            SkIRect::MakeXYWH(kW - 6, kH - 5, 6, 5),
            SkIRect::MakeXYWH(11, 0, 1, 1), SkIRect::MakeXYWH(17, 13, 1, 1),
            SkIRect::MakeWH(kW, kH)}) {
        const SkBitmap region = Region(*image, r, 77, 0.5, 2, 1, mask);
        ASSERT_FALSE(region.drawsNothing());
        ASSERT_EQ(region.width(), r.width());
        ASSERT_EQ(region.height(), r.height());
        for (int y = 0; y < r.height(); ++y) {
          for (int x = 0; x < r.width(); ++x) {
            EXPECT_EQ(*region.getAddr32(x, y),
                      *wb.getAddr32(x + r.x(), y + r.y()))
                << "rect " << r.x() << "," << r.y() << " " << r.width() << "x"
                << r.height() << " at " << x << "," << y << " shift " << shift;
          }
        }
      }
      EXPECT_TRUE(Region(*image, SkIRect::MakeXYWH(5, 4, 3, 3), 0, 0.5, 2, 1,
                         mask)
                      .drawsNothing());  // seed 0: nothing, caller stays stock
    }
  }
}

// A rect wholly off the canvas has no pixels to noise: nothing comes back.
TEST(NoisedRegionTest, OffCanvasRectIsEmpty) {
  const sk_sp<SkImage> image = Image(8, 8, Partial);
  for (const SkIRect& r :
       {SkIRect::MakeXYWH(8, 0, 4, 4), SkIRect::MakeXYWH(-5, -5, 5, 5),
        SkIRect::MakeXYWH(2, 8, 3, 3), SkIRect::MakeXYWH(-3, 2, 3, 3)}) {
    EXPECT_TRUE(Region(*image, r, 77, 0.5, 2, 1, NoiseMask()).drawsNothing())
        << r.x() << "," << r.y();
  }
}

// Review #5: a mask of another size than the canvas (a stale one, larger
// than the snapshot, or one with an origin) never gates the canvas by the
// wrong cells: neither the whole image nor a region changes, whatever the
// seed. With the canvas's own mask the same pixel does move.
TEST(NoisedImageTest, MaskOfAnotherSizeChangesNothing) {
  const sk_sp<SkImage> image = Image(8, 8, [](int x, int y) {
    return x == 4 && y == 4 ? Pack(200, 100, 50, 255) : Pack(0, 0, 0, 255);
  });
  const uint32_t lone = Pack(200, 100, 50, 255);
  const std::vector<uint8_t> cells(10 * 10, kNoiseMaskAa);
  const NoiseMask larger{cells.data(), 10, 0, 10, 10};
  NoiseMask offset = larger;
  offset.x0 = 1;
  offset.y0 = 1;
  bool moved = false;
  for (uint64_t seed = 1; seed < 32; ++seed) {
    for (const NoiseMask& mask : {larger, offset}) {
      const sk_sp<SkImage> noised =
          NoisedImage(*image, seed, 1.0, 3, 1, mask, /*bottom_up=*/false);
      if (noised) {
        EXPECT_EQ(*Read(*noised).getAddr32(4, 4), lone) << "seed " << seed;
      }
      const SkBitmap region =
          Region(*image, SkIRect::MakeXYWH(2, 2, 5, 5), seed, 1.0, 3, 1, mask);
      if (!region.drawsNothing()) {
        EXPECT_EQ(*region.getAddr32(2, 2), lone) << "seed " << seed;
      }
    }
    const NoiseMask own{cells.data(), 8, 0, 8, 8};
    moved |= *Read(*NoisedImage(*image, seed, 1.0, 3, 1, own, false))
                  .getAddr32(4, 4) != lone;
  }
  EXPECT_TRUE(moved) << "the canvas's own mask moved nothing: vacuous";
}

}  // namespace
}  // namespace camoucfg

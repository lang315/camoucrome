// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/canvas_mask.h"

#include <cstdint>
#include <vector>

#include "base/compiler_specific.h"
#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg {
namespace {

using Kind = CanvasNoiseMask::Kind;

uint8_t Cell(const CanvasNoiseMask& m, size_t x, size_t y) {
  const NoiseMask v = m.view();
  return UNSAFE_BUFFERS(v.cells[(y >> v.shift) * v.stride + (x >> v.shift)]);
}

// Coverage of a w x h area: 255 inside, `edge` on its border ring.
std::vector<uint8_t> Coverage(size_t w, size_t h, uint8_t edge) {
  std::vector<uint8_t> c(w * h, 255);
  for (size_t y = 0; y < h; ++y)
    for (size_t x = 0; x < w; ++x)
      if (x == 0 || y == 0 || x + 1 == w || y + 1 == h)
        c[y * w + x] = edge;
  return c;
}

TEST(CanvasNoiseMaskTest, StartsEmptyAndFullOpaqueCoverMarksNothing) {
  CanvasNoiseMask m(16, 16);
  EXPECT_TRUE(m.empty());
  const auto c = Coverage(4, 4, 255);
  m.Merge(c.data(), 4, 2, 2, 4, 4, Kind::kSolidOpaque);
  EXPECT_TRUE(m.empty());
  EXPECT_EQ(m.generation(), 0u);
}

TEST(CanvasNoiseMaskTest, PartialCoverageMarksAaFullDoesNot) {
  CanvasNoiseMask m(16, 16);
  const auto c = Coverage(6, 6, 128);
  m.Merge(c.data(), 6, 4, 4, 6, 6, Kind::kSolidOpaque);
  ASSERT_FALSE(m.empty());
  EXPECT_EQ(Cell(m, 4, 4), kNoiseMaskAa);   // partial ring
  EXPECT_EQ(Cell(m, 6, 6), 0);              // fully covered interior
  EXPECT_EQ(Cell(m, 0, 0), 0);              // not covered
}

TEST(CanvasNoiseMaskTest, FullSolidOpaqueCoverClearsBothMarks) {
  CanvasNoiseMask m(16, 16);
  m.MarkRect(0, 0, 16, 16, Kind::kAa);
  m.MarkRect(0, 0, 8, 8, Kind::kImported);
  m.MarkRect(2, 2, 4, 4, Kind::kSolidOpaque);
  EXPECT_EQ(Cell(m, 3, 3), 0);
  EXPECT_EQ(Cell(m, 7, 7), kNoiseMaskAa | kNoiseMaskImported);
  EXPECT_EQ(Cell(m, 12, 12), kNoiseMaskAa);
}

TEST(CanvasNoiseMaskTest, SolidNotOpaqueLeavesMarksOnFullCoverage) {
  CanvasNoiseMask m(16, 16);
  m.MarkRect(0, 0, 16, 16, Kind::kAa);
  m.MarkRect(2, 2, 4, 4, Kind::kSolid);
  EXPECT_EQ(Cell(m, 3, 3), kNoiseMaskAa);
}

TEST(CanvasNoiseMaskTest, ImportedWinsAndClearRectResets) {
  CanvasNoiseMask m(16, 16);
  m.MarkRect(0, 0, 16, 16, Kind::kImported);
  m.MarkRect(0, 0, 16, 16, Kind::kAa);
  EXPECT_EQ(Cell(m, 5, 5), kNoiseMaskAa | kNoiseMaskImported);
  m.MarkRect(0, 0, 16, 16, Kind::kClear);
  EXPECT_EQ(Cell(m, 5, 5), 0);
}

TEST(CanvasNoiseMaskTest, GradientAndPatternKindsMarkEveryCoveredPixel) {
  CanvasNoiseMask m(16, 16);
  const auto c = Coverage(4, 4, 255);
  m.Merge(c.data(), 4, 0, 0, 4, 4, Kind::kAa);
  m.Merge(c.data(), 4, 8, 8, 4, 4, Kind::kImported);
  EXPECT_EQ(Cell(m, 1, 1), kNoiseMaskAa);
  EXPECT_EQ(Cell(m, 9, 9), kNoiseMaskImported);
  EXPECT_EQ(Cell(m, 5, 5), 0);
}

TEST(CanvasNoiseMaskTest, CoverageOutsideTheCanvasIsIgnored) {
  CanvasNoiseMask m(8, 8);
  const auto c = Coverage(6, 6, 128);
  m.Merge(c.data(), 6, -3, 5, 6, 6, Kind::kAa);
  EXPECT_EQ(Cell(m, 0, 7), kNoiseMaskAa);
  EXPECT_EQ(Cell(m, 2, 5), kNoiseMaskAa);
  EXPECT_EQ(Cell(m, 3, 5), 0);
}

TEST(CanvasNoiseMaskTest, GenerationBumpsOnlyOnChange) {
  CanvasNoiseMask m(8, 8);
  m.MarkRect(0, 0, 4, 4, Kind::kAa);
  const uint64_t g = m.generation();
  EXPECT_GT(g, 0u);
  m.MarkRect(0, 0, 4, 4, Kind::kAa);
  EXPECT_EQ(m.generation(), g);
  m.MarkRect(0, 0, 4, 4, Kind::kClear);
  EXPECT_GT(m.generation(), g);
}

// Above the cap one cell covers 4 x 4 px: marked if any pixel is, cleared
// only when every pixel is fully covered.
TEST(CanvasNoiseMaskTest, CoarseCellsAboveTheCap) {
  CanvasNoiseMask m(4097, 4096);
  EXPECT_EQ(m.view().shift, 2);  // fixed at construction, even while empty
  m.MarkRect(0, 0, 1, 1, Kind::kAa);
  ASSERT_FALSE(m.empty());
  EXPECT_EQ(m.view().shift, 2);
  EXPECT_EQ(Cell(m, 3, 3), kNoiseMaskAa);
  m.MarkRect(0, 0, 3, 4, Kind::kSolidOpaque);  // misses column 3
  EXPECT_EQ(Cell(m, 0, 0), kNoiseMaskAa);
  m.MarkRect(0, 0, 4, 4, Kind::kSolidOpaque);
  EXPECT_EQ(Cell(m, 0, 0), 0);
}

// has_aa() is true iff some cell is exactly kNoiseMaskAa; aa plus imported
// does not count.
void ExpectHasAaBehaviour(CanvasNoiseMask& m) {
  EXPECT_FALSE(m.has_aa());
  m.MarkRect(8, 8, 8, 8, Kind::kImported);
  EXPECT_FALSE(m.has_aa());  // imported-only
  m.MarkRect(0, 0, 8, 8, Kind::kAa);
  EXPECT_TRUE(m.has_aa());
  m.MarkRect(0, 0, 8, 8, Kind::kImported);
  EXPECT_FALSE(m.has_aa());  // aa + imported is not counted
}

TEST(CanvasNoiseMaskTest, HasAaCountsAaOnlyCells) {
  CanvasNoiseMask m(16, 16);
  ExpectHasAaBehaviour(m);
  CanvasNoiseMask c(16, 16);
  c.MarkRect(0, 0, 4, 4, Kind::kAa);
  EXPECT_TRUE(c.has_aa());
  c.MarkRect(0, 0, 16, 16, Kind::kClear);
  EXPECT_FALSE(c.has_aa());
}

TEST(CanvasNoiseMaskTest, HasAaOnCoarseCells) {
  CanvasNoiseMask m(4097, 4096);
  ExpectHasAaBehaviour(m);
  CanvasNoiseMask c(4097, 4096);
  c.MarkRect(0, 0, 4, 4, Kind::kAa);
  EXPECT_TRUE(c.has_aa());
  c.MarkRect(0, 0, 4, 4, Kind::kClear);
  EXPECT_FALSE(c.has_aa());
}

}  // namespace
}  // namespace camoucfg

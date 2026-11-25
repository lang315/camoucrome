// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifdef UNSAFE_BUFFERS_BUILD
// The reference and the random coverage index plain vectors.
#pragma allow_unsafe_buffers
#endif

#include "components/camoucfg/canvas_mask.h"

#include <algorithm>
#include <cstdint>
#include <memory>
#include <utility>
#include <vector>

#include "base/compiler_specific.h"
#include "base/functional/bind.h"
#include "base/memory/raw_ptr.h"
#include "base/time/time.h"
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

// Merge() against the per-pixel rule, written out here: 255 clears for the
// clear kinds and keeps for kSolid, a partial value sets aa for the solid
// kinds, any value sets the kind's bit for kAa and kImported. Random rects
// (some past the canvas) and values, every kind, the aa count checked too.
TEST(CanvasNoiseMaskTest, MergeFollowsThePerPixelRule) {
  constexpr size_t kW = 61, kH = 47;
  CanvasNoiseMask m(kW, kH);
  m.MarkRect(0, 0, kW, kH, Kind::kAa);
  std::vector<uint8_t> ref(kW * kH, kNoiseMaskAa);
  uint64_t s = 12345;
  auto next = [&s](uint64_t n) {
    s ^= s << 13;
    s ^= s >> 7;
    s ^= s << 17;
    return s % n;
  };
  const Kind kinds[] = {Kind::kSolidOpaque, Kind::kSolid, Kind::kClear,
                        Kind::kAa, Kind::kImported};
  for (int op = 0; op < 400; ++op) {
    const Kind kind = kinds[next(5)];
    const int64_t left = static_cast<int64_t>(next(kW + 10)) - 5;
    const int64_t top = static_cast<int64_t>(next(kH + 10)) - 5;
    const size_t w = 1 + next(30), h = 1 + next(30);
    std::vector<uint8_t> cov(w * h);
    // Every other op is sparse (mostly zero runs, as a shape's bounds are).
    const uint64_t zero_odds = op % 2 ? 12 : 1;
    for (uint8_t& v : cov) {
      const uint64_t r = next(3 + zero_odds);
      v = r >= 2 ? 0 : r == 1 ? 255 : static_cast<uint8_t>(1 + next(254));
    }
    m.Merge(cov.data(), w, left, top, w, h, kind);
    for (size_t y = 0; y < h; ++y) {
      for (size_t x = 0; x < w; ++x) {
        const int64_t px = left + static_cast<int64_t>(x);
        const int64_t py = top + static_cast<int64_t>(y);
        if (px < 0 || py < 0 || px >= static_cast<int64_t>(kW) ||
            py >= static_cast<int64_t>(kH)) {
          continue;
        }
        uint8_t& cell =
            ref[static_cast<size_t>(py) * kW + static_cast<size_t>(px)];
        const uint8_t v = cov[y * w + x];
        if (v == 0) {
          continue;
        }
        if (kind == Kind::kAa) {
          cell |= kNoiseMaskAa;
        } else if (kind == Kind::kImported) {
          cell |= kNoiseMaskImported;
        } else if (v < 255) {
          cell |= kNoiseMaskAa;
        } else if (kind != Kind::kSolid) {
          cell = 0;
        }
      }
    }
    bool any_aa = false;
    for (size_t y = 0; y < kH; ++y) {
      for (size_t x = 0; x < kW; ++x) {
        ASSERT_EQ(Cell(m, x, y), ref[y * kW + x])
            << "op " << op << " at " << x << "," << y;
        any_aa |= ref[y * kW + x] == kNoiseMaskAa;
      }
    }
    ASSERT_EQ(m.has_aa(), any_aa) << "op " << op;
  }
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

// The cells exactly kNoiseMaskAa, counted from the mask's own view.
size_t CountAa(const CanvasNoiseMask& m, size_t dim) {
  const NoiseMask v = m.view();
  if (!v.cells) {
    return 0;
  }
  const size_t n = v.stride * ((dim + (size_t{1} << v.shift) - 1) >> v.shift);
  size_t count = 0;
  for (size_t i = 0; i < n; ++i) {
    if (v.cells[i] == kNoiseMaskAa) {
      ++count;
    }
  }
  return count;
}

// The mask rule restated naively (the reference of the Apply loop): the same
// cells, aa count and generation as CanvasNoiseMask for any coverage.
struct RefMask {
  size_t w, h, shift, stride, rows;
  std::vector<uint8_t> cells;
  size_t aa = 0;
  uint64_t gen = 0;
  RefMask(size_t w_, size_t h_)
      : w(w_), h(h_), shift(w_ * h_ > CanvasNoiseMask::kMaxFullResPixels ? 2 : 0),
        stride((w_ + (size_t{1} << shift) - 1) >> shift),
        rows((h_ + (size_t{1} << shift) - 1) >> shift) {}
  void Apply(const std::vector<uint8_t>* cov, size_t cs, int64_t left, int64_t top,
             int64_t right, int64_t bottom, Kind kind) {
    const int64_t x0 = std::max<int64_t>(left, 0), y0 = std::max<int64_t>(top, 0);
    const int64_t x1 = std::min<int64_t>(right, static_cast<int64_t>(w));
    const int64_t y1 = std::min<int64_t>(bottom, static_cast<int64_t>(h));
    if (x0 >= x1 || y0 >= y1) return;
    auto at = [&](int64_t x, int64_t y) -> uint8_t {
      return cov ? (*cov)[static_cast<size_t>(y - top) * cs + static_cast<size_t>(x - left)] : 255;
    };
    bool changed = false;
    const bool clearing = kind == Kind::kSolidOpaque || kind == Kind::kClear;
    if (clearing && !cells.empty()) {
      const int64_t s = int64_t{1} << shift;
      for (int64_t cy = y0 >> shift; cy <= (y1 - 1) >> shift; ++cy)
        for (int64_t cx = x0 >> shift; cx <= (x1 - 1) >> shift; ++cx) {
          uint8_t& cell = cells[static_cast<size_t>(cy) * stride + static_cast<size_t>(cx)];
          if (cell == 0) continue;
          const int64_t px1 = std::min<int64_t>((cx + 1) * s, static_cast<int64_t>(w));
          const int64_t py1 = std::min<int64_t>((cy + 1) * s, static_cast<int64_t>(h));
          bool full = true;
          for (int64_t py = cy * s; py < py1 && full; ++py)
            for (int64_t px = cx * s; px < px1 && full; ++px)
              full = px >= x0 && px < x1 && py >= y0 && py < y1 && at(px, py) == 255;
          if (full) {
            if (cell == kNoiseMaskAa) --aa;
            cell = 0;
            changed = true;
          }
        }
    }
    for (int64_t y = y0; y < y1; ++y)
      for (int64_t x = x0; x < x1; ++x) {
        const uint8_t c = at(x, y);
        if (c == 0) continue;
        uint8_t bit = 0;
        if (kind == Kind::kImported) bit = kNoiseMaskImported;
        else if (kind == Kind::kAa) bit = kNoiseMaskAa;
        else bit = c == 255 ? 0 : kNoiseMaskAa;
        if (bit == 0) continue;
        if (cells.empty()) cells.assign(stride * rows, 0);
        uint8_t& cell = cells[static_cast<size_t>(y >> shift) * stride + static_cast<size_t>(x >> shift)];
        if ((cell & bit) != bit) {
          if (cell == kNoiseMaskAa) --aa;
          cell |= bit;
          if (cell == kNoiseMaskAa) ++aa;
          changed = true;
        }
      }
    if (changed) ++gen;
  }
};

TEST(CanvasNoiseMaskTest, ApplyEqualsTheNaiveReferenceForAnyCoverage) {
  uint32_t seed = 12345;
  auto next = [&] { seed = seed * 1664525u + 1013904223u; return seed >> 8; };
  const Kind kinds[] = {Kind::kSolidOpaque, Kind::kSolid, Kind::kClear, Kind::kAa, Kind::kImported};
  for (const size_t dim : {size_t{16}, size_t{40}, size_t{4100}}) {  // 4100 x 4100 is above the full-resolution cap
    CanvasNoiseMask m(dim, dim);
    RefMask ref(dim, dim);
    for (int i = 0; i < 400; ++i) {
      const Kind kind = kinds[next() % 5];
      const int64_t left = static_cast<int64_t>(next() % 60) - 10, top = static_cast<int64_t>(next() % 60) - 10;
      const size_t w = 1 + next() % 14, h = 1 + next() % 14, cs = w + next() % 3;
      std::vector<uint8_t> cov(cs * h);
      const uint32_t mode = next() % 4;  // empty, full, partial, sparse
      for (auto& v : cov) {
        const uint32_t r = next() % 8;
        v = mode == 0 ? 0 : mode == 1 ? 255 : mode == 2 ? (r < 5 ? 255 : r < 7 ? 128 : 0) : (r == 0 ? 255 : 0);
      }
      const bool use_cov = next() % 5 != 0;
      if (use_cov) {
        m.Merge(cov.data(), cs, left, top, w, h, kind);
        ref.Apply(&cov, cs, left, top, left + static_cast<int64_t>(w), top + static_cast<int64_t>(h), kind);
      } else {
        m.MarkRect(left, top, static_cast<int64_t>(w), static_cast<int64_t>(h), kind);
        ref.Apply(nullptr, 0, left, top, left + static_cast<int64_t>(w), top + static_cast<int64_t>(h), kind);
      }
      ASSERT_EQ(m.generation(), ref.gen) << "dim " << dim << " step " << i;
      ASSERT_EQ(m.has_aa(), ref.aa > 0) << "dim " << dim << " step " << i;
      ASSERT_EQ(CountAa(m, dim), ref.aa) << "dim " << dim << " step " << i;
    }
    for (size_t y = 0; y < std::min<size_t>(dim, 64); ++y)
      for (size_t x = 0; x < std::min<size_t>(dim, 64); ++x)
        ASSERT_EQ(Cell(m, x, y),
                  ref.cells.empty() ? 0 : ref.cells[(y >> ref.shift) * ref.stride + (x >> ref.shift)])
            << "dim " << dim << " at " << x << "," << y;
  }
}

// The walk's fast path for a pixel-aligned rect marks its exact area instead of
// rastering it: the cells must be those of Merge() of the full-coverage raster
// (255 inside, 0 on the outset ring) for every kind that path takes, over
// prior aa and imported marks, at the canvas edge, on a full-resolution mask
// and on a coarse one.
TEST(CanvasNoiseMaskTest, ExactAreaMarkEqualsMergeOfFullCoverage) {
  struct Area { int64_t x, y, w, h; };
  const Area areas[] = {{2, 2, 4, 4}, {0, 0, 16, 16}, {0, 3, 5, 1}, {7, 7, 1, 1}, {5, 9, 11, 7}, {3, 0, 2, 40}};
  const Kind kinds[] = {Kind::kSolidOpaque, Kind::kSolid, Kind::kClear};
  for (const size_t dim : {size_t{16}, size_t{4100}}) {  // 4100 x 4100 is above the full-resolution cap
    for (const Kind kind : kinds) {
      for (const Area& a : areas) {
        auto prime = [&](CanvasNoiseMask& m) {
          m.MarkRect(0, 0, 40, 40, Kind::kAa);
          m.MarkRect(1, 1, 9, 9, Kind::kImported);
        };
        CanvasNoiseMask by_merge(dim, dim);
        CanvasNoiseMask by_mark(dim, dim);
        prime(by_merge);
        prime(by_mark);
        // The op's area is the rect outset by one pixel, with 0 on the ring.
        const size_t w = static_cast<size_t>(a.w) + 2;
        const size_t h = static_cast<size_t>(a.h) + 2;
        std::vector<uint8_t> cover(w * h, 0);
        for (size_t y = 1; y + 1 < h; ++y)
          for (size_t x = 1; x + 1 < w; ++x)
            cover[y * w + x] = 255;
        by_merge.Merge(cover.data(), w, a.x - 1, a.y - 1, w, h, kind);
        by_mark.MarkRect(a.x, a.y, a.w, a.h, kind);
        EXPECT_EQ(by_merge.generation(), by_mark.generation());
        EXPECT_EQ(by_merge.has_aa(), by_mark.has_aa());
        for (size_t y = 0; y < std::min<size_t>(dim, 48); ++y)
          for (size_t x = 0; x < std::min<size_t>(dim, 48); ++x)
            ASSERT_EQ(Cell(by_merge, x, y), Cell(by_mark, x, y))
                << "dim " << dim << " kind " << static_cast<int>(kind)
                << " area " << a.x << "," << a.y << " " << a.w << "x" << a.h << " at " << x << "," << y;
      }
    }
  }
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

// ---- LazyCanvasNoiseMask: the queue builds the mask the eager calls build ----

// One scripted change: a coverage merge or a rect mark on a canvas of a size.
struct ScriptStep {
  size_t w, h;
  int64_t x, y;
  size_t cw, ch;
  uint8_t edge;
  Kind kind;
  bool rect;
};

void Apply(const ScriptStep& s, CanvasNoiseMask& m) {
  if (s.rect) {
    m.MarkRect(s.x, s.y, static_cast<int64_t>(s.cw), static_cast<int64_t>(s.ch), s.kind);
  } else {
    const auto c = Coverage(s.cw, s.ch, s.edge);
    m.Merge(c.data(), s.cw, s.x, s.y, s.cw, s.ch, s.kind);
  }
}

// The cells of a view, as bytes; empty for a mask that holds none.
std::vector<uint8_t> Cells(const NoiseMask& v) {
  std::vector<uint8_t> out;
  if (!v.cells) {
    return out;
  }
  const size_t rows = (v.height + (size_t{1} << v.shift) - 1) >> v.shift;
  for (size_t i = 0; i < rows * v.stride; ++i) {
    out.push_back(UNSAFE_BUFFERS(v.cells[i]));
  }
  return out;
}

std::vector<ScriptStep> Script() {
  return {
      {32, 32, 2, 2, 8, 8, 100, Kind::kAa, false},
      {32, 32, 4, 4, 4, 4, 255, Kind::kSolidOpaque, false},
      {32, 32, 10, 10, 6, 6, 0, Kind::kImported, true},
      {32, 32, 0, 0, 12, 12, 128, Kind::kSolid, false},
      {32, 32, 20, 20, 8, 8, 0, Kind::kClear, true},
      {48, 40, 5, 5, 9, 9, 90, Kind::kAa, false},   // a resize: a fresh mask
      {48, 40, 6, 6, 3, 3, 0, Kind::kSolidOpaque, true},
      {48, 40, 30, 20, 10, 10, 77, Kind::kAa, false},
  };
}

// The eager mask after steps [0, n) of the script, resets at `reset_at` (-1: none).
std::vector<uint8_t> EagerCells(const std::vector<ScriptStep>& steps, size_t n, int reset_at, uint64_t* aa) {
  std::unique_ptr<CanvasNoiseMask> m;
  for (size_t i = 0; i < n; ++i) {
    if (static_cast<int>(i) == reset_at) {
      m.reset();
    }
    if (!m || m->width() != steps[i].w || m->height() != steps[i].h) {
      m = std::make_unique<CanvasNoiseMask>(steps[i].w, steps[i].h);
    }
    Apply(steps[i], *m);
  }
  if (aa) {
    *aa = m && m->has_aa();
  }
  return m ? Cells(m->view()) : std::vector<uint8_t>();
}

LazyCanvasNoiseMask::Event Ev(const ScriptStep& s) {
  return base::BindOnce([](ScriptStep s, CanvasNoiseMask& m) { Apply(s, m); }, s);
}

TEST(LazyCanvasNoiseMaskTest, ReadAtEveryPointEqualsTheEagerMaskByteForByte) {
  const auto steps = Script();
  for (size_t read_after = 1; read_after <= steps.size(); ++read_after) {
    LazyCanvasNoiseMask lazy;
    for (size_t i = 0; i < steps.size(); ++i) {
      lazy.Add(steps[i].w, steps[i].h, 1, Ev(steps[i]));
      if (i + 1 == read_after) {
        uint64_t aa = 0;
        const auto want = EagerCells(steps, i + 1, -1, &aa);
        EXPECT_EQ(Cells(lazy.view()), want) << "read after step " << i;
        EXPECT_EQ(lazy.has_aa(), aa != 0);
      }
    }
    uint64_t aa = 0;
    EXPECT_EQ(Cells(lazy.view()), EagerCells(steps, steps.size(), -1, &aa));
  }
}

TEST(LazyCanvasNoiseMaskTest, ResetBetweenRetainedEventsAndTheReadDropsTheEarlierOnes) {
  const auto steps = Script();
  for (size_t reset_at = 1; reset_at < steps.size(); ++reset_at) {
    LazyCanvasNoiseMask lazy;
    int ran = 0;
    for (size_t i = 0; i < steps.size(); ++i) {
      if (i == reset_at) {
        lazy.Reset();
        EXPECT_EQ(lazy.pending_events(), 0u);
      }
      lazy.Add(steps[i].w, steps[i].h, 1, base::BindOnce([](int* ran, ScriptStep s, CanvasNoiseMask& m) {
        ++*ran;
        Apply(s, m);
      }, &ran, steps[i]));
    }
    uint64_t aa = 0;
    EXPECT_EQ(Cells(lazy.view()), EagerCells(steps, steps.size(), static_cast<int>(reset_at), &aa))
        << "reset before step " << reset_at;
    EXPECT_EQ(static_cast<size_t>(ran), steps.size() - reset_at);  // the dropped events never ran
  }
}

TEST(LazyCanvasNoiseMaskTest, ResizeBetweenEventsBuildsAFreshMask) {
  LazyCanvasNoiseMask lazy;
  lazy.Add(16, 16, 1, base::BindOnce([](CanvasNoiseMask& m) { m.MarkRect(0, 0, 16, 16, Kind::kImported); }));
  lazy.Add(8, 8, 1, base::BindOnce([](CanvasNoiseMask& m) { m.MarkRect(0, 0, 2, 2, Kind::kAa); }));
  const NoiseMask v = lazy.view();
  EXPECT_EQ(v.width, 8u);
  EXPECT_EQ(v.height, 8u);
  EXPECT_TRUE(lazy.has_aa());
}

TEST(LazyCanvasNoiseMaskTest, GenerationNeverRepeatsAcrossResizeAndReset) {
  LazyCanvasNoiseMask lazy;
  EXPECT_EQ(lazy.generation(), 0u);
  std::vector<uint64_t> seen;
  for (size_t size : {16u, 16u, 8u, 8u}) {
    lazy.Add(size, size, 1, base::BindOnce([](CanvasNoiseMask& m) { m.MarkRect(0, 0, 2, 2, Kind::kAa); }));
    seen.push_back(lazy.generation());
    lazy.Add(size, size, 1, base::BindOnce([](CanvasNoiseMask& m) { m.MarkRect(4, 4, 2, 2, Kind::kAa); }));
    seen.push_back(lazy.generation());
    lazy.Reset();
  }
  for (size_t i = 0; i < seen.size(); ++i) {
    for (size_t j = i + 1; j < seen.size(); ++j) {
      EXPECT_NE(seen[i], seen[j]) << i << " vs " << j;
    }
  }
}

TEST(LazyCanvasNoiseMaskTest, PastTheCountCapTheOldestJobsAreMergedNeverDropped) {
  std::vector<int> order;
  auto note = [&](int id) {
    return base::BindOnce([](std::vector<int>* order, int id, CanvasNoiseMask&) { order->push_back(id); }, &order, id);
  };
  LazyCanvasNoiseMask lazy;
  for (size_t i = 0; i < LazyCanvasNoiseMask::kMaxPendingEvents; ++i) {
    lazy.Add(8, 8, 1, note(static_cast<int>(i)));
  }
  EXPECT_EQ(lazy.pending_events(), LazyCanvasNoiseMask::kMaxPendingEvents);
  lazy.Add(8, 8, 1, note(100));  // over the cap: the two oldest are merged, nothing is walked
  lazy.Add(8, 8, 1, note(101));
  EXPECT_TRUE(order.empty());
  EXPECT_EQ(lazy.pending_events(), LazyCanvasNoiseMask::kMaxPendingEvents);
  EXPECT_EQ(lazy.counters().merged_total, 2u);  // the trace's CamouMerged
  EXPECT_EQ(lazy.counters().parked_total, 0u);
  // A read walks every event, in order.
  EXPECT_FALSE(lazy.has_aa());
  ASSERT_EQ(order.size(), LazyCanvasNoiseMask::kMaxPendingEvents + 2);
  EXPECT_EQ(order.front(), 0);
  EXPECT_EQ(order.back(), 101);
  for (size_t i = 1; i < order.size(); ++i) {
    EXPECT_LT(order[i - 1], order[i]);
  }
  EXPECT_EQ(lazy.pending_events(), 0u);
}

TEST(LazyCanvasNoiseMaskTest, TheMaskPastTheCountCapEqualsTheEagerMaskOfEveryEvent) {
  // Marks of distinct 4 x 4 blocks on a 100 x 8 canvas, more events than the cap holds.
  const size_t n = LazyCanvasNoiseMask::kMaxPendingEvents + 5;
  std::vector<ScriptStep> steps;
  for (size_t i = 0; i < n; ++i) {
    steps.push_back({100, 8, static_cast<int64_t>(4 * i), 0, 4, 4, 0, Kind::kAa, true});
  }
  LazyCanvasNoiseMask lazy;
  for (const ScriptStep& s : steps) {
    lazy.Add(s.w, s.h, 1, Ev(s));
  }
  EXPECT_EQ(lazy.pending_events(), LazyCanvasNoiseMask::kMaxPendingEvents);
  uint64_t aa = 0;
  EXPECT_EQ(Cells(lazy.view()), EagerCells(steps, steps.size(), -1, &aa));  // the oldest five are merged, not dropped
  EXPECT_TRUE(lazy.has_aa());
}

TEST(LazyCanvasNoiseMaskTest, TheByteCapWalksTheOldestEventUntilUnderIt) {
  int ran = 0;
  auto count = [&] { return base::BindOnce([](int* ran, CanvasNoiseMask&) { ++*ran; }, &ran); };
  LazyCanvasNoiseMask lazy;
  lazy.Add(8, 8, LazyCanvasNoiseMask::kMaxPendingBytes - 1, count());
  EXPECT_EQ(ran, 0);
  lazy.Add(8, 8, 2, count());  // over the cap with two events: the oldest is walked (an event is never dropped)
  EXPECT_EQ(ran, 1);
  EXPECT_EQ(lazy.pending_events(), 1u);
  EXPECT_EQ(lazy.pending_bytes(), LazyCanvasNoiseMask::kMinPartBytes);  // a small job is accounted at least this much
  lazy.view();
  EXPECT_EQ(ran, 2);
}

TEST(LazyCanvasNoiseMaskTest, OneAaPlusManyImportedKeepsAa) {
  constexpr size_t kW = 32, kH = 16;
  for (const size_t imported : {LazyCanvasNoiseMask::kMaxPendingEvents, size_t{1000}}) {
    LazyCanvasNoiseMask lazy;
    lazy.Add(kW, kH, 1, Ev({kW, kH, 0, 0, kW, kH, 0, Kind::kAa, true}));  // the whole canvas aa
    for (size_t i = 0; i < imported; ++i) {
      lazy.Add(kW, kH, 1, Ev({kW, kH, 0, 0, 1, 1, 0, Kind::kImported, true}));
    }
    EXPECT_LE(lazy.pending_events(), LazyCanvasNoiseMask::kMaxPendingEvents);
    EXPECT_TRUE(lazy.has_aa()) << imported;  // the aa event was merged, never dropped
    EXPECT_EQ(UNSAFE_BUFFERS(lazy.view().cells[0]), kNoiseMaskAa | kNoiseMaskImported);
    EXPECT_EQ(UNSAFE_BUFFERS(lazy.view().cells[5]), kNoiseMaskAa);
  }
}

TEST(LazyCanvasNoiseMaskTest, ApplyNowAppliesTheWholeQueueThisEventLast) {
  std::vector<int> order;
  auto note = [&](int id) {
    return base::BindOnce([](std::vector<int>* order, int id, CanvasNoiseMask&) { order->push_back(id); }, &order, id);
  };
  LazyCanvasNoiseMask lazy;
  lazy.Add(8, 8, 1, note(1));
  lazy.Add(8, 8, 1, note(2));
  lazy.Add(8, 8, 1, note(3), /*apply_now=*/true);
  EXPECT_EQ(order, std::vector<int>({1, 2, 3}));
  EXPECT_EQ(lazy.pending_events(), 0u);
}

TEST(LazyCanvasNoiseMaskTest, ApplyOldestOneByOneThenReadEqualsTheEagerMask) {
  const auto steps = Script();
  for (size_t idle_steps = 0; idle_steps <= steps.size(); ++idle_steps) {
    LazyCanvasNoiseMask lazy;
    for (const ScriptStep& s : steps) {
      lazy.Add(s.w, s.h, 1, Ev(s));
    }
    for (size_t i = 0; i < idle_steps; ++i) {
      EXPECT_TRUE(lazy.ApplyOldest());  // the idle task
    }
    uint64_t aa = 0;
    EXPECT_EQ(Cells(lazy.view()), EagerCells(steps, steps.size(), -1, &aa)) << idle_steps << " idle steps";
  }
  LazyCanvasNoiseMask empty;
  EXPECT_FALSE(empty.ApplyOldest());
}

// A job that works one scripted step per allowed slice: the idle deadline stops it between steps.
class SliceJob final : public LazyCanvasNoiseMask::Job {
 public:
  SliceJob(std::vector<ScriptStep> steps, int* allowed) : steps_(std::move(steps)), allowed_(allowed) {}
  bool Step(CanvasNoiseMask& m, base::TimeTicks deadline) override {
    while (next_ < steps_.size()) {
      if (!deadline.is_max() && (*allowed_)-- <= 0) {
        return false;  // the clock is checked before every slice, the first one too
      }
      Apply(steps_[next_++], m);
    }
    return true;
  }

 private:
  std::vector<ScriptStep> steps_;
  size_t next_ = 0;
  raw_ptr<int> allowed_;
};

TEST(LazyCanvasNoiseMaskTest, AJobStoppedByTheDeadlineStaysAtTheFrontAndFinishesToTheEagerMask) {
  const auto steps = Script();
  const base::TimeTicks later = base::TimeTicks::Now() + base::Hours(1);
  for (int per_idle_task = 1; per_idle_task <= 3; ++per_idle_task) {
    LazyCanvasNoiseMask lazy;
    int allowed = 0;
    // one job per run of steps of one canvas size, as one flush is one job
    std::vector<ScriptStep> run;
    size_t jobs = 0;
    auto flush = [&] {
      if (run.empty()) return;
      lazy.Add(run[0].w, run[0].h, 1, std::make_unique<SliceJob>(run, &allowed));
      run.clear();
      ++jobs;
    };
    for (const ScriptStep& s : steps) {
      if (!run.empty() && (run[0].w != s.w || run[0].h != s.h)) flush();
      run.push_back(s);
    }
    flush();
    // no slice allowed: the first slice is not worked either, and the job stays queued
    allowed = 0;
    EXPECT_TRUE(lazy.ApplyOldest(later));
    EXPECT_EQ(lazy.pending_events(), jobs);
    size_t idle_tasks = 0;
    while (lazy.pending_events() > 0) {
      allowed = per_idle_task;
      EXPECT_TRUE(lazy.ApplyOldest(later));
      ASSERT_LT(++idle_tasks, 100u);
    }
    uint64_t aa = 0;
    EXPECT_EQ(Cells(lazy.view()), EagerCells(steps, steps.size(), -1, &aa)) << per_idle_task << " slices per idle task";
  }
}

TEST(LazyCanvasNoiseMaskTest, AReadFinishesAPartlyWorkedJobAndLaterEventsInOrder) {
  const auto steps = Script();
  LazyCanvasNoiseMask lazy;
  int allowed = 1;
  std::vector<ScriptStep> first(steps.begin(), steps.begin() + 5);   // the 32 x 32 steps
  lazy.Add(32, 32, 1, std::make_unique<SliceJob>(first, &allowed));
  EXPECT_TRUE(lazy.ApplyOldest(base::TimeTicks::Now() + base::Hours(1)));   // one slice
  EXPECT_EQ(lazy.pending_events(), 1u);
  for (size_t i = 5; i < steps.size(); ++i) {
    lazy.Add(steps[i].w, steps[i].h, 1, Ev(steps[i]));
  }
  uint64_t aa = 0;
  EXPECT_EQ(Cells(lazy.view()), EagerCells(steps, steps.size(), -1, &aa));
}

TEST(LazyCanvasNoiseMaskTest, NothingQueuedReadsAsNoMask) {
  LazyCanvasNoiseMask lazy;
  EXPECT_FALSE(lazy.has_aa());
  EXPECT_EQ(lazy.view().cells, nullptr);
  EXPECT_EQ(lazy.generation(), 0u);
}


// ---- MaskSnapshot: chunked snapshots that share untouched rows ----

// 100 x 300 cells (shift 0): five chunks of 64 rows, the last of 44.
constexpr size_t kW = 100;
constexpr size_t kH = 300;

void ExpectEqualsLive(const CanvasNoiseMask& m, const MaskSnapshot& s) {
  const std::vector<uint8_t> flat = s.Flatten();
  const NoiseMask v = m.view();
  ASSERT_EQ(flat.size(), v.stride * ((v.height + (size_t{1} << v.shift) - 1) >> v.shift));
  for (size_t i = 0; i < flat.size(); ++i) {
    ASSERT_EQ(flat[i], UNSAFE_BUFFERS(v.cells[i])) << "cell " << i;
  }
}

// Which chunks of `b` are not the very objects of `a`.
std::vector<size_t> Replaced(const MaskSnapshot& a, const MaskSnapshot& b) {
  std::vector<size_t> r;
  for (size_t i = 0; i < b.chunks.size(); ++i) {
    if (a.chunks[i] != b.chunks[i]) {
      r.push_back(i);
    }
  }
  return r;
}

TEST(MaskSnapshotTest, AnEmptyMaskHasNoSnapshotAndTheFirstMarkMakesOne) {
  CanvasNoiseMask m(kW, kH);
  EXPECT_EQ(m.Snapshot(nullptr), nullptr);
  m.MarkRect(10, 10, 5, 5, Kind::kAa);
  auto s = m.Snapshot(nullptr);
  ASSERT_NE(s, nullptr);
  EXPECT_EQ(s->chunks.size(), 5u);
  ExpectEqualsLive(m, *s);
}

TEST(MaskSnapshotTest, TheMarkWriterReplacesOnlyTheChunkItTouched) {
  CanvasNoiseMask m(kW, kH);
  m.MarkRect(10, 10, 5, 5, Kind::kAa);
  auto s1 = m.Snapshot(nullptr);
  m.MarkRect(10, 200, 5, 5, Kind::kAa);  // row 200: chunk 3
  auto s2 = m.Snapshot(s1.get());
  ExpectEqualsLive(m, *s2);
  EXPECT_EQ(Replaced(*s1, *s2), (std::vector<size_t>{3}));
}

TEST(MaskSnapshotTest, TheImportedMarkIsAWriterToo) {
  CanvasNoiseMask m(kW, kH);
  m.MarkRect(10, 10, 5, 5, Kind::kAa);
  auto s1 = m.Snapshot(nullptr);
  m.MarkRect(10, 100, 5, 5, Kind::kImported);  // chunk 1
  auto s2 = m.Snapshot(s1.get());
  ExpectEqualsLive(m, *s2);
  EXPECT_EQ(Replaced(*s1, *s2), (std::vector<size_t>{1}));
}

TEST(MaskSnapshotTest, TheMergeWriterReplacesOnlyTheChunkItTouched) {
  CanvasNoiseMask m(kW, kH);
  m.MarkRect(10, 10, 5, 5, Kind::kAa);
  auto s1 = m.Snapshot(nullptr);
  const std::vector<uint8_t> cov = Coverage(8, 8, 128);
  m.Merge(cov.data(), 8, 20, 130, 8, 8, Kind::kSolidOpaque);  // partial edge: aa, chunk 2
  auto s2 = m.Snapshot(s1.get());
  ExpectEqualsLive(m, *s2);
  EXPECT_EQ(Replaced(*s1, *s2), (std::vector<size_t>{2}));
}

TEST(MaskSnapshotTest, TheClearWriterReplacesOnlyTheChunkItClears) {
  CanvasNoiseMask m(kW, kH);
  m.MarkRect(10, 10, 5, 5, Kind::kAa);     // chunk 0
  m.MarkRect(10, 200, 5, 5, Kind::kAa);    // chunk 3
  auto s1 = m.Snapshot(nullptr);
  m.MarkRect(0, 0, kW, 64, Kind::kSolidOpaque);  // clears chunk 0's cells only
  auto s2 = m.Snapshot(s1.get());
  ExpectEqualsLive(m, *s2);
  EXPECT_EQ(Replaced(*s1, *s2), (std::vector<size_t>{0}));
  EXPECT_EQ(Cell(m, 12, 12), 0);
  EXPECT_EQ(Cell(m, 12, 202), kNoiseMaskAa);
}

TEST(MaskSnapshotTest, NothingWrittenSharesEveryChunk) {
  CanvasNoiseMask m(kW, kH);
  m.MarkRect(10, 10, 5, 5, Kind::kAa);
  auto s1 = m.Snapshot(nullptr);
  auto s2 = m.Snapshot(s1.get());
  EXPECT_TRUE(Replaced(*s1, *s2).empty());
  ExpectEqualsLive(m, *s2);
}

TEST(MaskSnapshotTest, AFreshMaskSharesNothingWithAnOlderSnapshot) {
  CanvasNoiseMask a(kW, kH);
  a.MarkRect(10, 10, 5, 5, Kind::kAa);
  auto sa = a.Snapshot(nullptr);
  CanvasNoiseMask b(kW, kH);
  b.MarkRect(10, 10, 5, 5, Kind::kAa);
  auto sb = b.Snapshot(sa.get());
  ExpectEqualsLive(b, *sb);
  EXPECT_EQ(Replaced(*sa, *sb).size(), 5u);
}

TEST(MaskSnapshotTest, CoarseCellsAboveTheCapFlattenToTheLiveCells) {
  CanvasNoiseMask m(4097, 4097);  // over kMaxFullResPixels: 4 x 4 pixel cells
  m.MarkRect(1, 1, 10, 10, Kind::kAa);
  auto s1 = m.Snapshot(nullptr);
  ExpectEqualsLive(m, *s1);
  m.MarkRect(2000, 3000, 10, 10, Kind::kAa);
  auto s2 = m.Snapshot(s1.get());
  ExpectEqualsLive(m, *s2);
  EXPECT_EQ(Replaced(*s1, *s2).size(), 1u);
}

TEST(MaskSnapshotTest, TheLazyMaskSnapshotEqualsItsView) {
  LazyCanvasNoiseMask lazy;
  lazy.Add(kW, kH, 0, base::BindOnce([](CanvasNoiseMask& m) { m.MarkRect(10, 10, 5, 5, Kind::kAa); }));
  auto s = lazy.Snapshot(nullptr);
  ASSERT_NE(s, nullptr);
  const std::vector<uint8_t> flat = s->Flatten();
  const NoiseMask v = lazy.view();
  ASSERT_EQ(flat.size(), v.stride * ((v.height + (size_t{1} << v.shift) - 1) >> v.shift));
  for (size_t i = 0; i < flat.size(); ++i) {
    ASSERT_EQ(flat[i], UNSAFE_BUFFERS(v.cells[i]));
  }
}

// ---- DeferredMask: the unapplied queue, finished on another thread ----

// A clonable job: one scripted step per allowed slice, as SliceJob, that
// resumes where it stopped when cloned.
class CloneJob final : public LazyCanvasNoiseMask::Job {
 public:
  CloneJob(std::vector<ScriptStep> steps, int* allowed, size_t next = 0)
      : steps_(std::move(steps)), allowed_(allowed), next_(next) {}
  bool Step(CanvasNoiseMask& m, base::TimeTicks deadline) override {
    while (next_ < steps_.size()) {
      if (!deadline.is_max() && (*allowed_)-- <= 0) {
        return false;
      }
      Apply(steps_[next_++], m);
    }
    return true;
  }
  std::unique_ptr<Job> Clone() const override {
    return std::make_unique<CloneJob>(steps_, allowed_, next_);
  }

 private:
  std::vector<ScriptStep> steps_;
  raw_ptr<int> allowed_;
  size_t next_;
};

// Every kind, a merge and a rect each, on one canvas size.
std::vector<ScriptStep> Script32() {
  auto steps = Script();
  steps.resize(5);
  steps.push_back({32, 32, 1, 1, 30, 30, 200, Kind::kAa, false});
  steps.push_back({32, 32, 16, 0, 8, 32, 255, Kind::kSolid, false});
  return steps;
}

std::vector<ScriptStep> Slice(const std::vector<ScriptStep>& s, size_t a, size_t b) {
  return std::vector<ScriptStep>(s.begin() + a, s.begin() + b);
}

TEST(DeferredMaskTest, ReplayEqualsTheEagerMaskWhateverTheJobsHaveWalked) {
  const auto steps = Script32();
  const base::TimeTicks later = base::TimeTicks::Now() + base::Hours(1);
  uint64_t aa = 0;
  const auto want = EagerCells(steps, steps.size(), -1, &aa);
  // k slices of the first job walked when the frame is taken: 0 (nothing), 1 and
  // 2 (partly), 3 (all of it: the job is gone from the queue).
  for (int k = 0; k <= 3; ++k) {
    LazyCanvasNoiseMask lazy;
    int allowed = 0;
    lazy.Add(32, 32, 1, Ev(steps[0]));
    lazy.Add(32, 32, 1, Ev(steps[1]));
    lazy.view();  // the first two applied: the base
    lazy.Add(32, 32, 1, std::make_unique<CloneJob>(Slice(steps, 2, 5), &allowed));
    allowed = k;
    EXPECT_TRUE(lazy.ApplyOldest(later));
    lazy.Add(32, 32, 1, std::make_unique<CloneJob>(Slice(steps, 5, 7), &allowed));
    scoped_refptr<const DeferredMask> d;
    ASSERT_EQ(lazy.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kDeferred) << k;
    ASSERT_TRUE(d->base());
    EXPECT_EQ(d->jobs(), k == 3 ? 1u : 2u);
    auto replayed = d->Replay();
    EXPECT_EQ(Cells(replayed->view()), want) << "k=" << k;
    EXPECT_EQ(replayed->has_aa(), aa != 0);
    // The worker walks on, one slice, while a copy of the frame is replayed...
    allowed = 1;
    EXPECT_TRUE(lazy.ApplyOldest(later));
    EXPECT_EQ(Cells(d->Replay()->view()), want) << "k=" << k;
    // ...and its own mask ends as the eager one.
    EXPECT_EQ(Cells(lazy.view()), want) << "k=" << k;
    EXPECT_EQ(Cells(d->Replay()->view()), want) << "k=" << k;
  }
}

TEST(DeferredMaskTest, NoBaseYetReplaysFromAFreshMask) {
  const auto steps = Script32();
  LazyCanvasNoiseMask lazy;
  int allowed = 0;
  lazy.Add(32, 32, 1, std::make_unique<CloneJob>(Slice(steps, 0, 7), &allowed));
  scoped_refptr<const DeferredMask> d;
  ASSERT_EQ(lazy.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kDeferred);
  EXPECT_FALSE(d->base());
  uint64_t aa = 0;
  EXPECT_EQ(Cells(d->Replay()->view()), EagerCells(steps, 7, -1, &aa));
}

TEST(DeferredMaskTest, ACanvasResizedUnderTheBaseReplaysFromAFreshMask) {
  const auto steps = Script();
  LazyCanvasNoiseMask lazy;
  int allowed = 0;
  lazy.Add(32, 32, 1, Ev(steps[0]));
  lazy.view();  // a 32 x 32 mask applied...
  lazy.Add(48, 40, 1, std::make_unique<CloneJob>(Slice(steps, 5, 8), &allowed));
  scoped_refptr<const DeferredMask> d;
  ASSERT_EQ(lazy.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kDeferred);
  EXPECT_FALSE(d->base());  // ...is not the base of a 48 x 40 queue
  EXPECT_EQ(Cells(d->Replay()->view()), Cells(lazy.view()));
}

TEST(DeferredMaskTest, TheCapsAreTheQueuesAndTheNotClonableLeaveTheMaskAndTheChainAlone) {
  const auto steps = Script32();
  int allowed = 0;
  auto job = [&](size_t i) {
    return std::make_unique<CloneJob>(Slice(steps, i, i + 1), &allowed);
  };
  scoped_refptr<const DeferredMask> d;
  {  // nothing queued
    LazyCanvasNoiseMask lazy;
    EXPECT_EQ(lazy.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kNone);
  }
  {  // a queue at the job cap defers whole; the Add past it merges the two oldest jobs (no frame splits them), and the
    // replay is the mask of every job, as the worker's own read of that queue is
    LazyCanvasNoiseMask lazy;
    std::vector<ScriptStep> all;
    const size_t cap = LazyCanvasNoiseMask::kMaxDeferredJobs;
    ASSERT_EQ(cap, LazyCanvasNoiseMask::kMaxPendingEvents);
    auto add = [&](size_t i) {
      // the first job marks a cell no other job touches: its loss would show
      const ScriptStep s = i == 0 ? ScriptStep{32, 32, 0, 0, 1, 1, 0, Kind::kAa, true}
                                  : ScriptStep{32, 32, static_cast<int64_t>(2 + i), 20, 1, 1, 0, Kind::kAa, true};
      all.push_back(s);
      lazy.Add(32, 32, 1, std::make_unique<CloneJob>(std::vector<ScriptStep>{s}, &allowed));
    };
    for (size_t i = 0; i < cap; ++i) {
      add(i);
    }
    ASSERT_EQ(lazy.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kDeferred);
    EXPECT_EQ(d->jobs(), cap);
    uint64_t aa = 0;
    EXPECT_EQ(Cells(d->Replay()->view()), EagerCells(all, cap, -1, &aa));
    add(cap);  // the 17th job: the first two merge (the frame above carries both): nothing is parked
    d.reset();
    ASSERT_EQ(lazy.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kDeferred);
    EXPECT_EQ(d->jobs(), cap);  // the merge, then 15 queued
    EXPECT_EQ(lazy.pending_events(), cap);
    EXPECT_EQ(lazy.parked_events(), 0u);
    const auto replayed = Cells(d->Replay()->view());
    EXPECT_EQ(replayed, EagerCells(all, cap + 1, -1, &aa));  // nothing is lost
    EXPECT_EQ(replayed, Cells(lazy.view()));                 // and it is what the worker's own read gives
  }
  {  // a canvas no frame was taken from merges the oldest jobs too (no parking, no signal), and loses nothing
    LazyCanvasNoiseMask lazy;
    std::vector<ScriptStep> all;
    for (size_t i = 0; i <= LazyCanvasNoiseMask::kMaxPendingEvents; ++i) {
      const ScriptStep s = i == 0 ? ScriptStep{32, 32, 0, 0, 1, 1, 0, Kind::kAa, true}
                                  : ScriptStep{32, 32, static_cast<int64_t>(2 + i), 20, 1, 1, 0, Kind::kAa, true};
      all.push_back(s);
      lazy.Add(32, 32, 1, std::make_unique<CloneJob>(std::vector<ScriptStep>{s}, &allowed));
    }
    EXPECT_EQ(lazy.parked_events(), 0u);
    EXPECT_EQ(lazy.pending_events(), LazyCanvasNoiseMask::kMaxPendingEvents);
    uint64_t aa = 0;
    EXPECT_EQ(Cells(lazy.view()), EagerCells(all, all.size(), -1, &aa));
  }
  {  // one recording past the byte cap is not deferred (the queue keeps it, as its only entry)
    LazyCanvasNoiseMask lazy;
    lazy.Add(32, 32, LazyCanvasNoiseMask::kMaxDeferredBytes, job(0));
    EXPECT_EQ(lazy.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kDeferred);
    LazyCanvasNoiseMask big;
    big.Add(32, 32, LazyCanvasNoiseMask::kMaxDeferredBytes + 1, job(0));
    d.reset();
    EXPECT_EQ(big.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kOverCap);
    EXPECT_FALSE(d);
  }
  {  // past the byte cap the Add walks oldest jobs until under it: what is left defers
    LazyCanvasNoiseMask lazy;
    const size_t nine_sixteenths = LazyCanvasNoiseMask::kMaxDeferredBytes * 9 / 16;
    lazy.Add(32, 32, nine_sixteenths, job(0));
    lazy.Add(32, 32, nine_sixteenths, job(1));
    d.reset();
    ASSERT_EQ(lazy.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kDeferred);
    EXPECT_EQ(d->jobs(), 1u);
    EXPECT_LE(d->bytes(), LazyCanvasNoiseMask::kMaxDeferredBytes);
  }
  {  // an event cannot be copied
    LazyCanvasNoiseMask lazy;
    lazy.Add(32, 32, 1, job(0));
    lazy.Add(32, 32, 1, Ev(steps[1]));
    d.reset();
    EXPECT_EQ(lazy.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kNotClonable);
    uint64_t aa = 0;
    EXPECT_EQ(Cells(lazy.view()), EagerCells(steps, 2, -1, &aa));  // applied as before
  }
  {  // a resize inside the queue
    LazyCanvasNoiseMask lazy;
    lazy.Add(32, 32, 1, job(0));
    lazy.Add(48, 40, 1, job(1));
    d.reset();
    EXPECT_EQ(lazy.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kNotClonable);
  }
}

TEST(DeferredMaskTest, ADeferThatFailsDoesNotConsumeTheSnapshotChain) {
  const auto steps = Script32();
  LazyCanvasNoiseMask lazy;
  lazy.Add(32, 32, 1, Ev(steps[0]));
  scoped_refptr<const MaskSnapshot> prev = lazy.Snapshot(nullptr);
  ASSERT_TRUE(prev);
  lazy.Add(32, 32, 1, Ev(steps[1]));  // an event: Defer fails
  scoped_refptr<const DeferredMask> d;
  ASSERT_EQ(lazy.Defer(prev.get(), &d), LazyCanvasNoiseMask::DeferStatus::kNotClonable);
  // The chain still works: the next snapshot of `prev` is the live mask.
  scoped_refptr<const MaskSnapshot> next = lazy.Snapshot(prev.get());
  ASSERT_TRUE(next);
  EXPECT_EQ(next->Flatten(), Cells(lazy.view()));
}

TEST(DeferredMaskTest, ABaseTakenAlongTheChainSharesItsUntouchedChunks) {
  const auto steps = Script32();
  LazyCanvasNoiseMask lazy;
  int allowed = 0;
  lazy.Add(32, 32, 1, Ev(steps[0]));
  scoped_refptr<const MaskSnapshot> prev = lazy.Snapshot(nullptr);
  lazy.Add(32, 32, 1, std::make_unique<CloneJob>(Slice(steps, 1, 2), &allowed));
  scoped_refptr<const DeferredMask> d;
  ASSERT_EQ(lazy.Defer(prev.get(), &d), LazyCanvasNoiseMask::DeferStatus::kDeferred);
  ASSERT_TRUE(d->base());
  ASSERT_EQ(d->base()->chunks.size(), prev->chunks.size());
  for (size_t i = 0; i < prev->chunks.size(); ++i) {
    EXPECT_EQ(d->base()->chunks[i], prev->chunks[i]) << i;  // nothing applied: nothing replaced
  }
}

TEST(DeferredMaskTest, AMaskFromASnapshotHoldsItsCellsAndItsAaCount) {
  for (const size_t dim : {size_t{32}, size_t{4100}}) {  // 4100: coarse cells
    CanvasNoiseMask m(dim, dim);
    m.MarkRect(2, 2, 8, 8, Kind::kAa);
    m.MarkRect(5, 5, 2, 2, Kind::kImported);
    auto snap = m.Snapshot(nullptr);
    ASSERT_TRUE(snap);
    CanvasNoiseMask from(*snap);
    EXPECT_EQ(Cells(from.view()), Cells(m.view())) << dim;
    EXPECT_EQ(from.has_aa(), m.has_aa()) << dim;
    // and it goes on as the original does: a clear takes the last aa cell away
    m.MarkRect(0, 0, static_cast<int64_t>(dim), static_cast<int64_t>(dim), Kind::kImported);
    from.MarkRect(0, 0, static_cast<int64_t>(dim), static_cast<int64_t>(dim), Kind::kImported);
    EXPECT_EQ(Cells(from.view()), Cells(m.view())) << dim;
    EXPECT_FALSE(from.has_aa());
  }
  auto none = base::MakeRefCounted<MaskSnapshot>();  // no cell ever written
  none->width = 32;
  none->height = 32;
  EXPECT_TRUE(CanvasNoiseMask(*none).empty());
}

TEST(DeferredMaskTest, TheRevisionBumpsOnAddSliceAndResetButNotOnDeferOrAnIdleRead) {
  const auto steps = Script32();
  LazyCanvasNoiseMask lazy;
  int allowed = 0;
  const uint64_t r0 = lazy.revision();
  lazy.Add(32, 32, 1, std::make_unique<CloneJob>(Slice(steps, 0, 2), &allowed));
  const uint64_t r1 = lazy.revision();
  EXPECT_NE(r1, r0);
  scoped_refptr<const DeferredMask> d;
  ASSERT_EQ(lazy.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kDeferred);
  EXPECT_EQ(lazy.revision(), r1);
  lazy.view();  // applies the queue: slices worked
  const uint64_t r2 = lazy.revision();
  EXPECT_NE(r2, r1);
  lazy.view();  // nothing queued: nothing worked
  EXPECT_EQ(lazy.revision(), r2);
  lazy.Reset();
  EXPECT_NE(lazy.revision(), r2);
}

// ---- Parked jobs: what the page has read stays marked ----

// Job `i` of a long run: one aa cell no other job touches (30 columns x 2 rows
// apart on a 32 x 32 canvas, 60 jobs), so a lost job shows as one missing mark.
ScriptStep Unique(size_t i) {
  return {32, 32, static_cast<int64_t>(i % 30), static_cast<int64_t>(2 * (i / 30)), 1, 1, 0, Kind::kAa, true};
}

std::unique_ptr<LazyCanvasNoiseMask::Job> UniqueJob(size_t i, int* allowed) {
  return std::make_unique<CloneJob>(std::vector<ScriptStep>{Unique(i)}, allowed);
}

// The eager mask of the jobs `first` through `last` (job numbers, inclusive).
std::vector<uint8_t> EagerRange(size_t first, size_t last) {
  CanvasNoiseMask m(32, 32);
  for (size_t i = first; i <= last; ++i) {
    Apply(Unique(i), m);
  }
  return Cells(m.view());
}

// A worker that flushes jobs 1..n, committing a frame after each (as a rAF
// loop does) and telling the queue the page read the frame of job `read_at`
// as soon as it is committed (`read_at` 0: the page never reads).
struct Worker {
  LazyCanvasNoiseMask lazy;
  int allowed = 0;
  scoped_refptr<const DeferredMask> frame;       // the newest frame
  scoped_refptr<const DeferredMask> read_frame;  // the one the page read
  void Flush(size_t i, size_t read_at) {
    lazy.Add(32, 32, 1, UniqueJob(i, &allowed));
    ASSERT_EQ(lazy.Defer(nullptr, &frame), LazyCanvasNoiseMask::DeferStatus::kDeferred);
    if (i == read_at) {
      read_frame = frame;
      lazy.NoteSeen(frame->last_id());
    }
  }
};

TEST(ParkedJobsTest, JobsPastTheCountCapAreMergedEvenWhenTheLastFrameCarriesThemAndEveryReadWalksThem) {
  Worker w;
  for (size_t i = 1; i <= 20; ++i) {
    w.Flush(i, 0);
  }
  EXPECT_EQ(w.lazy.pending_events(), 16u);
  EXPECT_EQ(w.lazy.parked_events(), 0u);  // the two oldest of one size merge: nothing needs parking
  EXPECT_EQ(w.frame->jobs(), 16u);
  // what the frame pins is all 20 jobs, as the lazy mask's own accounting says
  const size_t floor = LazyCanvasNoiseMask::kMinPartBytes;
  EXPECT_EQ(w.frame->bytes(), 20 * floor);
  EXPECT_EQ(w.lazy.pending_bytes(), 20 * floor);
  EXPECT_EQ(Cells(w.frame->Replay()->view()), EagerRange(1, 20));
  EXPECT_EQ(Cells(w.lazy.view()), EagerRange(1, 20));  // the worker's own read agrees
  EXPECT_EQ(w.lazy.counters().parked_walked, 0u);
}

// The job the last frame carried cannot merge with its neighbour (another canvas size): the count route walks it at the
// 17th job, carried or not, so the count of flushes never loses a mark (only the byte cap parks).
TEST(ParkedJobsTest, AJobNothingCanMergeWithIsWalkedAtTheCountCapEvenWhenTheLastFrameCarriedIt) {
  LazyCanvasNoiseMask lazy;
  int allowed = 0;
  scoped_refptr<const DeferredMask> d;
  lazy.Add(32, 32, 1, UniqueJob(0, &allowed));
  ASSERT_EQ(lazy.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kDeferred);
  for (size_t i = 1; i <= 16; ++i) {  // alternate sizes: no two neighbours merge
    const size_t w = i % 2 ? 48 : 32, h = i % 2 ? 40 : 32;
    lazy.Add(w, h, 1, std::make_unique<CloneJob>(std::vector<ScriptStep>{{w, h, 1, 1, 1, 1, 0, Kind::kAa, true}}, &allowed));
  }
  EXPECT_EQ(lazy.pending_events(), 16u);
  EXPECT_EQ(lazy.parked_events(), 0u);  // job 0: carried by the frame, walked all the same
  EXPECT_EQ(lazy.counters().parked_total, 0u);
  EXPECT_EQ(lazy.counters().dropped_total, 0u);  // gone from the queue, not parked, not dropped: walked
}

TEST(ParkedJobsTest, TheIdleWalkWalksTheMergedFrontBeforeTheRest) {
  Worker w;
  for (size_t i = 1; i <= 18; ++i) {
    w.Flush(i, 0);
  }
  ASSERT_EQ(w.lazy.parked_events(), 0u);
  ASSERT_EQ(w.lazy.pending_events(), 16u);  // jobs 1..3 are one merged job at the front
  w.allowed = 100;
  const base::TimeTicks later = base::TimeTicks::Now() + base::Hours(1);
  EXPECT_TRUE(w.lazy.ApplyOldest(later));  // the merge, all three parts
  EXPECT_EQ(w.lazy.pending_events(), 15u);
  EXPECT_TRUE(w.lazy.ApplyOldest(later));  // job 4
  EXPECT_EQ(w.lazy.pending_events(), 14u);
  EXPECT_EQ(Cells(w.lazy.view()), EagerRange(1, 18));
}

TEST(ParkedJobsTest, WhatThePageReadStaysMarkedAfterManyUnreadFlushes) {
  // The page reads the frame of job 16 (the signal arrives at once); the worker
  // flushes on to 60 with no worker read. The frame of 60 carries every job
  // (merged past 16), so it shows what the first read did and the rest too.
  Worker w;
  for (size_t i = 1; i <= 60; ++i) {
    w.Flush(i, 16);
  }
  const auto first_read = Cells(w.read_frame->Replay()->view());
  EXPECT_EQ(first_read, EagerRange(1, 16));
  const auto second = Cells(w.frame->Replay()->view());
  EXPECT_EQ(second, EagerRange(1, 60));
  for (size_t i = 1; i <= 16; ++i) {  // the re-read: every cell the first read marked is marked
    CanvasNoiseMask one(32, 32);
    Apply(Unique(i), one);
    const auto cell = Cells(one.view());
    for (size_t k = 0; k < cell.size(); ++k) {
      if (cell[k]) {
        EXPECT_EQ(second[k], cell[k]) << "job " << i;
      }
    }
  }
  EXPECT_EQ(Cells(w.lazy.view()), EagerRange(1, 60));  // the worker's own read, the same
  EXPECT_EQ(w.lazy.counters().seen_walked, 0u);
  EXPECT_EQ(w.lazy.counters().parked_evicted, 0u);
  EXPECT_EQ(w.lazy.counters().signals, 1u);
}

TEST(ParkedJobsTest, WithoutTheSignalTheSameRunLosesNothing) {
  Worker w;
  for (size_t i = 1; i <= 60; ++i) {
    w.Flush(i, 0);
  }
  const auto second = Cells(w.frame->Replay()->view());
  EXPECT_EQ(second, EagerRange(1, 60));  // merged, not dropped: a second read shows every job
}

TEST(ParkedJobsTest, ASignalThatArrivesAfterTheJobsWereMergedChangesNothing) {
  Worker w;
  for (size_t i = 1; i <= 16; ++i) {
    w.Flush(i, 0);
  }
  const auto read = w.frame;  // the page reads this frame...
  for (size_t i = 17; i <= 30; ++i) {
    w.Flush(i, 0);  // ...the worker merges jobs 1..15 before the signal arrives
  }
  ASSERT_EQ(w.lazy.parked_events(), 0u);
  w.lazy.NoteSeen(read->last_id());  // a task late
  for (size_t i = 31; i <= 50; ++i) {
    w.Flush(i, 0);
  }
  EXPECT_EQ(Cells(w.frame->Replay()->view()), EagerRange(1, 50));
  EXPECT_EQ(w.lazy.counters().parked_evicted, 0u);
}

TEST(ParkedJobsTest, ParkedJobsAreBoundedByCountAndBytesAndFreedByReset) {
  Worker w;
  for (size_t i = 1; i <= 100; ++i) {
    w.Flush(i % 60 + 1, 0);
  }
  EXPECT_LE(w.lazy.parked_events(), LazyCanvasNoiseMask::kMaxParkedJobs);
  EXPECT_LE(w.lazy.pending_events(), LazyCanvasNoiseMask::kMaxPendingEvents);
  LazyCanvasNoiseMask big;
  int allowed = 0;
  scoped_refptr<const DeferredMask> d;
  const size_t half = LazyCanvasNoiseMask::kMaxParkedBytes * 3 / 4;
  big.Add(32, 32, 1, UniqueJob(1, &allowed));
  ASSERT_EQ(big.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kDeferred);
  for (size_t i = 2; i <= 40; ++i) {
    big.Add(32, 32, i % 2 ? half : 1, UniqueJob(i, &allowed));  // parks while over the byte cap
    d.reset();
    big.Defer(nullptr, &d);
    EXPECT_LE(big.parked_bytes(), LazyCanvasNoiseMask::kMaxParkedBytes);
  }
  EXPECT_LE(w.lazy.parked_bytes(), LazyCanvasNoiseMask::kMaxParkedBytes);
  w.lazy.Reset();
  EXPECT_EQ(w.lazy.parked_events(), 0u);
  EXPECT_EQ(w.lazy.parked_bytes(), 0u);
  EXPECT_FALSE(w.lazy.has_work());
}

TEST(ParkedJobsTest, ACanvasNobodyDefersNeverParksNorCountsASignal) {
  LazyCanvasNoiseMask lazy;
  int allowed = 0;
  for (size_t i = 0; i < 40; ++i) {
    lazy.Add(32, 32, 1, UniqueJob(i, &allowed));
  }
  EXPECT_EQ(lazy.parked_events(), 0u);
  EXPECT_EQ(lazy.counters().parked_total, 0u);
  EXPECT_EQ(lazy.counters().signals, 0u);
  EXPECT_EQ(lazy.pending_events(), LazyCanvasNoiseMask::kMaxPendingEvents);
}

// A job that cannot be copied once it has started (a recording walked up to the
// middle of a layer): Defer() must hand the queue back to be applied.
class StartedJob final : public LazyCanvasNoiseMask::Job {
 public:
  StartedJob(std::vector<ScriptStep> steps, int* allowed)
      : steps_(std::move(steps)), allowed_(allowed) {}
  bool Step(CanvasNoiseMask& m, base::TimeTicks deadline) override {
    while (next_ < steps_.size()) {
      if (!deadline.is_max() && (*allowed_)-- <= 0) {
        return false;
      }
      Apply(steps_[next_++], m);
    }
    return true;
  }
  std::unique_ptr<Job> Clone() const override {
    if (next_ != 0) {
      return nullptr;
    }
    return std::make_unique<StartedJob>(steps_, allowed_);
  }

 private:
  std::vector<ScriptStep> steps_;
  raw_ptr<int> allowed_;
  size_t next_ = 0;
};

TEST(DeferredMaskTest, AJobThatCannotBeCopiedMidWalkIsAppliedByTheWorkerAndTheMaskIsTheEagerOne) {
  const auto steps = Script32();
  const base::TimeTicks later = base::TimeTicks::Now() + base::Hours(1);
  uint64_t aa = 0;
  const auto want = EagerCells(steps, 7, -1, &aa);
  LazyCanvasNoiseMask lazy;
  int allowed = 1;
  lazy.Add(32, 32, 1, std::make_unique<StartedJob>(Slice(steps, 0, 7), &allowed));
  scoped_refptr<const DeferredMask> d;
  // not started: a copy is made
  ASSERT_EQ(lazy.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kDeferred);
  EXPECT_TRUE(lazy.ApplyOldest(later));  // one slice: now it is mid-walk
  d.reset();
  EXPECT_EQ(lazy.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kNotClonable);
  EXPECT_FALSE(d);
  EXPECT_EQ(Cells(lazy.view()), want);  // applied, in order, as before
}

TEST(DeferredMaskTest, AnEventQueuedAfterAMergeStillMakesTheFrameApplyOnTheWorker) {
  const auto steps = Script32();
  LazyCanvasNoiseMask lazy;
  int allowed = 0;
  scoped_refptr<const DeferredMask> d;
  lazy.Add(32, 32, 1, std::make_unique<CloneJob>(Slice(steps, 0, 1), &allowed));
  for (size_t i = 1; i < LazyCanvasNoiseMask::kMaxPendingEvents; ++i) {
    lazy.Add(32, 32, 1, UniqueJob(i, &allowed));
  }
  ASSERT_EQ(lazy.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kDeferred);
  lazy.Add(32, 32, 1, UniqueJob(40, &allowed));  // the first two jobs merge
  ASSERT_EQ(lazy.parked_events(), 0u);
  lazy.Add(32, 32, 1, Ev(steps[1]));  // an event in the queue
  d.reset();
  EXPECT_EQ(lazy.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kNotClonable);
  lazy.view();
  EXPECT_FALSE(lazy.has_work());
  EXPECT_EQ(lazy.parked_events(), 0u);
}

// A job whose copies run out: each Clone() takes one from `left` and fails when none is left.
class FlakyCloneJob final : public LazyCanvasNoiseMask::Job {
 public:
  FlakyCloneJob(std::vector<ScriptStep> steps, int* left) : steps_(std::move(steps)), left_(left) {}
  bool Step(CanvasNoiseMask& m, base::TimeTicks) override {
    for (const ScriptStep& s : steps_) {
      Apply(s, m);
    }
    return true;
  }
  std::unique_ptr<Job> Clone() const override {
    if ((*left_)-- <= 0) {
      return nullptr;
    }
    return std::make_unique<FlakyCloneJob>(steps_, left_);
  }

 private:
  std::vector<ScriptStep> steps_;
  raw_ptr<int> left_;
};

TEST(DeferredMaskTest, ACopyThatFailsAtReplayIsNotSkippedAndLeavesTheMemoAlone) {
  const auto steps = Script32();
  LazyCanvasNoiseMask lazy;
  int left = 2;  // Defer() copies both jobs
  lazy.Add(32, 32, 1, std::make_unique<FlakyCloneJob>(Slice(steps, 0, 3), &left));
  lazy.Add(32, 32, 1, std::make_unique<FlakyCloneJob>(Slice(steps, 3, 5), &left));
  scoped_refptr<const DeferredMask> d;
  ASSERT_EQ(lazy.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kDeferred);
  EXPECT_EQ(left, 0);
  // no copy left: no mask (a mask without the jobs would be a wrong one)
  EXPECT_EQ(d->Replay(), nullptr);
  CanvasNoiseMask memo(32, 32);
  size_t stepped = 77;
  EXPECT_FALSE(d->Continue(memo, d->epoch(), 0, &stepped));
  EXPECT_TRUE(memo.empty());
  EXPECT_EQ(stepped, 77u);
  // one copy left: the first job's copy is made, the second's is not: nothing is walked
  left = 1;
  EXPECT_EQ(d->Replay(), nullptr);
  left = 1;
  EXPECT_FALSE(d->Continue(memo, d->epoch(), 0, &stepped));
  EXPECT_TRUE(memo.empty());
  EXPECT_EQ(stepped, 77u);
  // copies enough: both agree with the eager mask
  left = 100;
  uint64_t aa = 0;
  auto replayed = d->Replay();
  ASSERT_NE(replayed, nullptr);
  EXPECT_EQ(Cells(replayed->view()), EagerCells(steps, 5, -1, &aa));
  EXPECT_TRUE(d->Continue(memo, d->epoch(), 0, &stepped));
  EXPECT_EQ(stepped, 2u);
  EXPECT_EQ(Cells(memo.view()), Cells(replayed->view()));
}

TEST(DeferredMaskContinueTest, ContinuingAMemoEqualsAFullReplay) {
  const auto steps = Script32();
  LazyCanvasNoiseMask lazy;
  int allowed = 0;
  lazy.Add(32, 32, 1, std::make_unique<CloneJob>(Slice(steps, 0, 2), &allowed));
  lazy.Add(32, 32, 1, std::make_unique<CloneJob>(Slice(steps, 2, 4), &allowed));
  scoped_refptr<const DeferredMask> d1;
  ASSERT_EQ(lazy.Defer(nullptr, &d1), LazyCanvasNoiseMask::DeferStatus::kDeferred);
  auto memo = d1->Replay();
  const uint64_t memo_id = d1->last_id();
  lazy.Add(32, 32, 1, std::make_unique<CloneJob>(Slice(steps, 4, 6), &allowed));
  lazy.Add(32, 32, 1, std::make_unique<CloneJob>(Slice(steps, 6, 7), &allowed));
  scoped_refptr<const DeferredMask> d2;
  ASSERT_EQ(lazy.Defer(nullptr, &d2), LazyCanvasNoiseMask::DeferStatus::kDeferred);
  size_t stepped = 99;
  ASSERT_TRUE(d2->Continue(*memo, d1->epoch(), memo_id, &stepped));
  EXPECT_EQ(stepped, 2u);  // only the two new jobs
  EXPECT_EQ(Cells(memo->view()), Cells(d2->Replay()->view()));
  uint64_t aa = 0;
  EXPECT_EQ(Cells(memo->view()), EagerCells(steps, 7, -1, &aa));
}

TEST(DeferredMaskContinueTest, AWalkedJobPastTheMemoOrAnotherEpochOrAnOlderFrameStartsOver) {
  const auto steps = Script32();
  LazyCanvasNoiseMask lazy;
  int allowed = 0;
  lazy.Add(32, 32, 1, std::make_unique<CloneJob>(Slice(steps, 0, 3), &allowed));
  scoped_refptr<const DeferredMask> d1;
  ASSERT_EQ(lazy.Defer(nullptr, &d1), LazyCanvasNoiseMask::DeferStatus::kDeferred);
  auto memo = d1->Replay();
  const auto before = Cells(memo->view());
  const uint64_t memo_id = d1->last_id();
  const base::TimeTicks later = base::TimeTicks::Now() + base::Hours(1);
  lazy.Add(32, 32, 1, std::make_unique<CloneJob>(Slice(steps, 3, 5), &allowed));
  lazy.Add(32, 32, 1, std::make_unique<CloneJob>(Slice(steps, 5, 7), &allowed));
  // the worker walks job 1, then job 2 (past the memo: part of it is in the base now)
  allowed = 100;
  EXPECT_TRUE(lazy.ApplyOldest(later));
  EXPECT_TRUE(lazy.ApplyOldest(later));
  scoped_refptr<const DeferredMask> d2;
  ASSERT_EQ(lazy.Defer(nullptr, &d2), LazyCanvasNoiseMask::DeferStatus::kDeferred);
  size_t stepped = 0;
  EXPECT_FALSE(d2->Continue(*memo, d1->epoch(), memo_id, &stepped));
  EXPECT_EQ(Cells(memo->view()), before);  // untouched
  uint64_t aa = 0;
  EXPECT_EQ(Cells(d2->Replay()->view()), EagerCells(steps, 7, -1, &aa));
  // another epoch
  EXPECT_FALSE(d2->Continue(*memo, d1->epoch() + 1, memo_id, &stepped));
  // a memo newer than the frame
  EXPECT_FALSE(d1->Continue(*memo, d1->epoch(), d1->last_id() + 5, &stepped));
}

TEST(DeferredMaskContinueTest, AMemoOfAnotherEpochIsNotContinuedWhateverElseHolds) {
  const auto steps = Script32();
  LazyCanvasNoiseMask lazy;
  int allowed = 0;
  lazy.Add(32, 32, 1, std::make_unique<CloneJob>(Slice(steps, 0, 3), &allowed));
  scoped_refptr<const DeferredMask> d;
  ASSERT_EQ(lazy.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kDeferred);
  // nothing walked (touched 0), a memo of "no job yet": only the epoch can say no
  CanvasNoiseMask memo(32, 32);
  size_t stepped = 0;
  EXPECT_FALSE(d->Continue(memo, d->epoch() + 1, 0, &stepped));
  EXPECT_TRUE(memo.empty());
  EXPECT_TRUE(d->Continue(memo, d->epoch(), 0, &stepped));
  EXPECT_EQ(stepped, 1u);
  uint64_t aa = 0;
  EXPECT_EQ(Cells(memo.view()), EagerCells(steps, 3, -1, &aa));
}

TEST(DeferredMaskContinueTest, AResetOrAResizeIsANewEpoch) {
  LazyCanvasNoiseMask lazy;
  int allowed = 0;
  const auto steps = Script();
  lazy.Add(32, 32, 1, std::make_unique<CloneJob>(Slice(steps, 0, 1), &allowed));
  lazy.view();
  const uint64_t e0 = lazy.epoch();
  lazy.Reset();
  EXPECT_NE(lazy.epoch(), e0);
  lazy.Add(32, 32, 1, std::make_unique<CloneJob>(Slice(steps, 0, 1), &allowed));
  lazy.view();
  const uint64_t e1 = lazy.epoch();
  lazy.Add(48, 40, 1, std::make_unique<CloneJob>(Slice(steps, 5, 6), &allowed));
  lazy.view();
  EXPECT_NE(lazy.epoch(), e1);
}

// ---- Merging past the count cap, walking past the byte cap ----

// `n` clonable jobs of two scripted steps each (Script32, shifted), in `lazy`; their steps in order in `*all`.
void AddTwoStepJobs(LazyCanvasNoiseMask& lazy, size_t n, int* allowed, std::vector<ScriptStep>* all) {
  const auto steps = Script32();
  for (size_t i = 0; i < n; ++i) {
    const std::vector<ScriptStep> two = {steps[i % 7], steps[(i + 3) % 7]};
    all->insert(all->end(), two.begin(), two.end());
    lazy.Add(32, 32, 1, std::make_unique<CloneJob>(two, allowed));
  }
}

TEST(LazyCanvasNoiseMaskTest, MergedJobResumesMidPart) {
  LazyCanvasNoiseMask lazy;
  int allowed = 0;
  std::vector<ScriptStep> all;
  AddTwoStepJobs(lazy, 20, &allowed, &all);
  EXPECT_EQ(lazy.pending_events(), LazyCanvasNoiseMask::kMaxPendingEvents);
  const base::TimeTicks later = base::TimeTicks::Now() + base::Hours(1);
  size_t calls = 0;
  while (lazy.has_work()) {
    allowed = 0;  // an expired deadline: no slice runs, between parts or inside one
    lazy.ApplyOldest(later);
    allowed = 1;  // one slice: stops inside a part
    lazy.ApplyOldest(later);
    ASSERT_LT(++calls, 1000u);
  }
  uint64_t aa = 0;
  EXPECT_EQ(Cells(lazy.view()), EagerCells(all, all.size(), -1, &aa));
}

TEST(LazyCanvasNoiseMaskTest, MergedCloneIsIndependent) {
  LazyCanvasNoiseMask lazy;
  int allowed = 0;
  std::vector<ScriptStep> all;
  AddTwoStepJobs(lazy, 20, &allowed, &all);
  scoped_refptr<const DeferredMask> d;
  ASSERT_EQ(lazy.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kDeferred);
  uint64_t aa = 0;
  const auto want = EagerCells(all, all.size(), -1, &aa);
  EXPECT_EQ(Cells(d->Replay()->view()), want);  // a clone stepped to its end
  EXPECT_EQ(Cells(d->Replay()->view()), want);  // and again
  EXPECT_EQ(lazy.pending_events(), LazyCanvasNoiseMask::kMaxPendingEvents);  // the original is untouched
  EXPECT_EQ(Cells(lazy.view()), want);
}

TEST(LazyCanvasNoiseMaskTest, ResizeErasesMergedFront) {
  const auto steps = Script32();
  LazyCanvasNoiseMask lazy;
  for (size_t i = 0; i < 17; ++i) {  // the first two merge
    lazy.Add(32, 32, 1, Ev(steps[i % 5]));
  }
  const ScriptStep resized = {48, 40, 5, 5, 9, 9, 90, Kind::kAa, false};
  lazy.Add(48, 40, 1, Ev(resized));
  const NoiseMask v = lazy.view();
  EXPECT_EQ(v.width, 48u);
  EXPECT_EQ(v.height, 40u);
  uint64_t aa = 0;
  EXPECT_EQ(Cells(v), EagerCells({resized}, 1, -1, &aa));  // the older jobs were erased by the resize, as today
}

TEST(LazyCanvasNoiseMaskTest, MergeNeverStraddlesDeferred) {
  LazyCanvasNoiseMask lazy;
  int allowed = 0;
  for (size_t i = 1; i <= 8; ++i) {
    lazy.Add(32, 32, 1, UniqueJob(i, &allowed));
  }
  scoped_refptr<const DeferredMask> d1;
  ASSERT_EQ(lazy.Defer(nullptr, &d1), LazyCanvasNoiseMask::DeferStatus::kDeferred);  // carries jobs 1..8
  auto memo = d1->Replay();
  const uint64_t memo_id = d1->last_id();
  for (size_t i = 9; i <= 30; ++i) {
    lazy.Add(32, 32, 1, UniqueJob(i, &allowed));
  }
  EXPECT_EQ(lazy.pending_events(), LazyCanvasNoiseMask::kMaxPendingEvents);
  scoped_refptr<const DeferredMask> d2;
  ASSERT_EQ(lazy.Defer(nullptr, &d2), LazyCanvasNoiseMask::DeferStatus::kDeferred);
  // Jobs 1..8 are one merge (its id is 8, not past the memo), and 9..30 are 15 more: a merge across 8 would count 16.
  size_t stepped = 0;
  ASSERT_TRUE(d2->Continue(*memo, d1->epoch(), memo_id, &stepped));
  EXPECT_EQ(stepped, 15u);
  EXPECT_EQ(Cells(memo->view()), EagerRange(1, 30));
}

TEST(LazyCanvasNoiseMaskTest, MergedWithEventIsNotClonable) {
  LazyCanvasNoiseMask lazy;
  int allowed = 0;
  lazy.Add(32, 32, 1, Ev(Unique(0)));  // an event first: the 17th job merges it into the front
  for (size_t i = 1; i <= 16; ++i) {
    lazy.Add(32, 32, 1, UniqueJob(i, &allowed));
  }
  EXPECT_EQ(lazy.pending_events(), LazyCanvasNoiseMask::kMaxPendingEvents);
  scoped_refptr<const DeferredMask> d;
  EXPECT_EQ(lazy.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kNotClonable);
  EXPECT_FALSE(d);
  EXPECT_EQ(Cells(lazy.view()), EagerRange(0, 16));  // applied as before
}

TEST(LazyCanvasNoiseMaskTest, TheByteCapWalksEventsNeverDropsThem) {
  LazyCanvasNoiseMask lazy;
  for (size_t i = 0; i < 40; ++i) {  // 40 MB of events, each marking a cell of its own
    lazy.Add(32, 32, size_t{1} << 20, Ev(Unique(i)));
    EXPECT_LE(lazy.pending_bytes(), LazyCanvasNoiseMask::kMaxPendingBytes) << i;
  }
  EXPECT_EQ(Cells(lazy.view()), EagerRange(0, 39));  // every mark is there
  EXPECT_EQ(lazy.counters().dropped_total, 0u);
}

// Past 16 MB the oldest recordings are released unwalked, part by part out of a merge.
TEST(LazyCanvasNoiseMaskTest, TheByteCapDropsTheOldestRecordingsUnwalked) {
  LazyCanvasNoiseMask lazy;
  int allowed = 0;
  for (size_t i = 0; i < 40; ++i) {  // 40 MB of recordings, each marking a cell of its own
    lazy.Add(32, 32, size_t{1} << 20, UniqueJob(i, &allowed));
    EXPECT_LE(lazy.pending_bytes(), LazyCanvasNoiseMask::kMaxPendingBytes) << i;
  }
  EXPECT_EQ(lazy.pending_events(), LazyCanvasNoiseMask::kMaxPendingEvents);
  EXPECT_EQ(lazy.counters().merged_total, 24u);
  EXPECT_EQ(lazy.counters().dropped_total, 24u);  // jobs 0..23, one part each, never walked
  EXPECT_EQ(lazy.parked_events(), 0u);
  EXPECT_EQ(Cells(lazy.view()), EagerRange(24, 39));
}

TEST(LazyCanvasNoiseMaskTest, TheByteCapDropsOnlyRecordingsOutOfAMixedMerge) {
  LazyCanvasNoiseMask lazy;
  int allowed = 0;
  for (size_t i = 0; i < 40; ++i) {  // even: a 1 MB recording; odd: a put (a zero-byte event)
    if (i % 2 == 0) {
      lazy.Add(32, 32, size_t{1} << 20, UniqueJob(i, &allowed));
    } else {
      lazy.Add(32, 32, 0, Ev(Unique(i)));
    }
  }
  const auto cells = Cells(lazy.view());
  auto marked = [&](size_t i) {
    CanvasNoiseMask one(32, 32);
    Apply(Unique(i), one);
    const auto c = Cells(one.view());
    for (size_t k = 0; k < c.size(); ++k) {
      if (c[k]) {
        return cells[k] != 0;
      }
    }
    return false;
  };
  size_t first_kept = 40;
  for (size_t i = 0; i < 40; i += 2) {
    if (marked(i)) {
      first_kept = std::min(first_kept, i);
    }
  }
  ASSERT_GT(first_kept, 0u);  // some recordings were dropped
  for (size_t i = 0; i < 40; ++i) {
    EXPECT_EQ(marked(i), i % 2 == 1 || i >= first_kept) << i;  // every put is there; the dropped are the oldest
  }
  EXPECT_EQ(lazy.counters().dropped_total, first_kept / 2);
}

// A job the last frame carries is parked at the byte cap, not dropped, and its eviction drops it unless the page read a
// frame that carried it.
TEST(ParkedJobsTest, AtTheByteCapACarriedJobIsParkedAndItsEvictionDropsItUnlessSeen) {
  for (const bool seen : {false, true}) {
    LazyCanvasNoiseMask lazy;
    int allowed = 0;
    scoped_refptr<const DeferredMask> d;
    for (size_t i = 0; i < 40; ++i) {  // 4 MB per flush, each committed as a frame
      lazy.Add(32, 32, size_t{4} << 20, UniqueJob(i, &allowed));
      d.reset();
      ASSERT_EQ(lazy.Defer(nullptr, &d), LazyCanvasNoiseMask::DeferStatus::kDeferred) << i;
      if (seen) {
        lazy.NoteSeen(d->last_id());
      }
    }
    EXPECT_EQ(lazy.counters().dropped_total, 0u) << seen;  // every front was carried: parked, not dropped
    EXPECT_GT(lazy.counters().parked_total, 0u) << seen;
    EXPECT_LE(lazy.parked_bytes(), LazyCanvasNoiseMask::kMaxParkedBytes) << seen;
    if (seen) {
      EXPECT_EQ(lazy.counters().parked_evicted, 0u);
      EXPECT_GT(lazy.counters().seen_walked, 0u);
      EXPECT_EQ(Cells(lazy.view()), EagerRange(0, 39));
    } else {
      EXPECT_GT(lazy.counters().parked_evicted, 0u);
      EXPECT_EQ(lazy.counters().seen_walked, 0u);
      EXPECT_EQ(Cells(lazy.view()), EagerRange(lazy.counters().parked_evicted, 39));
    }
  }
}

// Overdraw elision: Blink resets the queue when it records a clearRect that covers every pixel (CheckOverdraw). Such a
// clear sets every cell to nothing whatever it held, so the mask after it is the mask of walking every older job and
// then the clear, byte for byte: nothing visible is dropped.
TEST(LazyCanvasNoiseMaskTest, AResetBeforeAFullCanvasClearEqualsWalkingEveryOlderJobThenTheClear) {
  for (const size_t n : {size_t{32}, size_t{4100}}) {  // one cell per pixel; 4 x 4 px cells
    const std::vector<ScriptStep> before = {
        {n, n, 2, 2, 8, 8, 100, Kind::kAa, false},
        {n, n, 10, 10, 6, 6, 0, Kind::kImported, true},
        {n, n, 0, 0, 12, 12, 128, Kind::kSolid, false},
    };
    const std::vector<ScriptStep> after = {
        {n, n, 4, 4, 8, 8, 90, Kind::kAa, false},
        {n, n, 20, 0, 3, 3, 0, Kind::kImported, true},
    };
    const ScriptStep clear = {n, n, 0, 0, n, n, 0, Kind::kClear, true};
    LazyCanvasNoiseMask walked, elided;
    for (const ScriptStep& s : before) {
      walked.Add(n, n, 1, Ev(s));
      elided.Add(n, n, 1, Ev(s));
    }
    elided.Reset();
    EXPECT_FALSE(elided.has_work());
    walked.Add(n, n, 1, Ev(clear));
    elided.Add(n, n, 1, Ev(clear));
    for (const ScriptStep& s : after) {
      walked.Add(n, n, 1, Ev(s));
      elided.Add(n, n, 1, Ev(s));
    }
    EXPECT_EQ(Cells(walked.view()), Cells(elided.view())) << n;
    EXPECT_EQ(walked.has_aa(), elided.has_aa()) << n;
  }
}

TEST(LazyCanvasNoiseMaskTest, ZeroByteEventsBounded) {
  constexpr size_t kN = 200000;
  LazyCanvasNoiseMask lazy;
  CanvasNoiseMask eager(512, 512);
  for (size_t i = 0; i < kN; ++i) {
    const int64_t x = static_cast<int64_t>(i % 512), y = static_cast<int64_t>(i / 512);
    eager.MarkRect(x, y, 1, 1, Kind::kAa);
    lazy.Add(512, 512, 0, base::BindOnce([](int64_t x, int64_t y, CanvasNoiseMask& m) { m.MarkRect(x, y, 1, 1, Kind::kAa); }, x, y));
  }
  EXPECT_LE(lazy.pending_bytes(), LazyCanvasNoiseMask::kMaxPendingBytes);
  EXPECT_LE(lazy.pending_events(), LazyCanvasNoiseMask::kMaxPendingEvents);
  EXPECT_EQ(Cells(lazy.view()), Cells(eager.view()));
}

}  // namespace
}  // namespace camoucfg

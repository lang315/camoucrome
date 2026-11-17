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

TEST(LazyCanvasNoiseMaskTest, PastTheCapsTheOldestEventIsDroppedUnwalkedPerAdd) {
  std::vector<int> order;
  auto note = [&](int id) {
    return base::BindOnce([](std::vector<int>* order, int id, CanvasNoiseMask&) { order->push_back(id); }, &order, id);
  };
  LazyCanvasNoiseMask lazy;
  for (size_t i = 0; i < LazyCanvasNoiseMask::kMaxPendingEvents; ++i) {
    lazy.Add(8, 8, 1, note(static_cast<int>(i)));
  }
  EXPECT_EQ(lazy.pending_events(), LazyCanvasNoiseMask::kMaxPendingEvents);
  lazy.Add(8, 8, 1, note(100));  // over the cap: the oldest goes, never walked
  lazy.Add(8, 8, 1, note(101));
  EXPECT_TRUE(order.empty());
  EXPECT_EQ(lazy.pending_events(), LazyCanvasNoiseMask::kMaxPendingEvents);
  // A read walks the rest, in order: events 0 and 1 are gone.
  EXPECT_FALSE(lazy.has_aa());
  EXPECT_EQ(order.size(), LazyCanvasNoiseMask::kMaxPendingEvents);
  EXPECT_EQ(order.front(), 2);
  EXPECT_EQ(order.back(), 101);
  for (size_t i = 1; i < order.size(); ++i) {
    EXPECT_LT(order[i - 1], order[i]);
  }
  EXPECT_EQ(lazy.pending_events(), 0u);
}

TEST(LazyCanvasNoiseMaskTest, TheMaskAfterADropEqualsTheEagerMaskOfTheRetainedEvents) {
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
  const std::vector<ScriptStep> kept(steps.begin() + 5, steps.end());   // the oldest five were dropped
  uint64_t aa = 0;
  EXPECT_EQ(Cells(lazy.view()), EagerCells(kept, kept.size(), -1, &aa));
  EXPECT_TRUE(lazy.has_aa());
}

TEST(LazyCanvasNoiseMaskTest, TheByteCapDropsOldestEventsUntilUnderIt) {
  int ran = 0;
  auto count = [&] { return base::BindOnce([](int* ran, CanvasNoiseMask&) { ++*ran; }, &ran); };
  LazyCanvasNoiseMask lazy;
  lazy.Add(8, 8, LazyCanvasNoiseMask::kMaxPendingBytes - 1, count());
  lazy.Add(8, 8, 2, count());  // over the cap with two events: the oldest is dropped
  EXPECT_EQ(ran, 0);
  EXPECT_EQ(lazy.pending_events(), 1u);
  EXPECT_EQ(lazy.pending_bytes(), 2u);
  lazy.view();
  EXPECT_EQ(ran, 1);
}

// A dropped opaque fill or clearRect leaves the aa marks of earlier events in
// place. Those cells sit on uniform opaque or fully transparent pixels, which
// the noise leaves alone (it moves a pixel toward a differing neighbour with
// alpha >= 1), so a stale mark there changes nothing a page can see.
TEST(LazyCanvasNoiseMaskTest, StaleAaMarksOnUniformOrTransparentPixelsStayUnnoised) {
  constexpr size_t kW = 32, kH = 16;
  LazyCanvasNoiseMask lazy;
  lazy.Add(kW, kH, 1, Ev({kW, kH, 0, 0, kW, kH, 0, Kind::kAa, true}));  // the event that is dropped
  for (size_t i = 0; i < LazyCanvasNoiseMask::kMaxPendingEvents; ++i) {
    lazy.Add(kW, kH, 1, Ev({kW, kH, 0, 0, 1, 1, 0, Kind::kImported, true}));
  }
  EXPECT_FALSE(lazy.has_aa());  // the read walks the retained events: the dropped aa never lands
  // The dropped event marked the whole canvas aa: make the same stale mask by hand.
  CanvasNoiseMask stale(kW, kH);
  stale.MarkRect(0, 0, kW, kH, Kind::kAa);
  // Left half: an opaque fill; right half: cleared (alpha 0).
  std::vector<uint8_t> px(kW * kH * 4, 0);
  for (size_t y = 0; y < kH; ++y) {
    for (size_t x = 0; x < kW / 2; ++x) {
      const size_t i = (y * kW + x) * 4;
      px[i] = 200;
      px[i + 1] = 30;
      px[i + 2] = 90;
      px[i + 3] = 255;
    }
  }
  const std::vector<uint8_t> before = px;
  ASSERT_TRUE(PerturbRgbaEdgesInPlace(px.data(), kW, kH, kW * 4, 7, 1.0, 3, 1, stale.view(), false));
  // The fill's own border against the cleared half is eligible only when the
  // neighbour has alpha >= 1: it has 0, so nothing moves anywhere.
  EXPECT_EQ(px, before);
  // Control: a pixel that really differs from an opaque neighbour does change.
  px = before;
  px[(4 * kW + 3) * 4] = 10;
  const std::vector<uint8_t> edge = px;
  ASSERT_TRUE(PerturbRgbaEdgesInPlace(px.data(), kW, kH, kW * 4, 7, 1.0, 3, 1, stale.view(), false));
  EXPECT_NE(px, edge);
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

}  // namespace
}  // namespace camoucfg

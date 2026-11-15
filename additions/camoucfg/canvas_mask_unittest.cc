// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/canvas_mask.h"

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

TEST(LazyCanvasNoiseMaskTest, PastTheCapsOnlyTheOldestEventIsAppliedPerAdd) {
  std::vector<int> order;
  auto note = [&](int id) {
    return base::BindOnce([](std::vector<int>* order, int id, CanvasNoiseMask&) { order->push_back(id); }, &order, id);
  };
  LazyCanvasNoiseMask lazy;
  for (size_t i = 0; i < LazyCanvasNoiseMask::kMaxPendingEvents; ++i) {
    lazy.Add(8, 8, 1, note(static_cast<int>(i)));
  }
  EXPECT_TRUE(order.empty());  // at the cap nothing was built
  EXPECT_EQ(lazy.pending_events(), LazyCanvasNoiseMask::kMaxPendingEvents);
  lazy.Add(8, 8, 1, note(100));  // over it: the oldest, only the oldest
  EXPECT_EQ(order, std::vector<int>({0}));
  lazy.Add(8, 8, 1, note(101));
  EXPECT_EQ(order, std::vector<int>({0, 1}));
  EXPECT_EQ(lazy.pending_events(), LazyCanvasNoiseMask::kMaxPendingEvents);
  // A read applies the rest, in order.
  EXPECT_FALSE(lazy.has_aa());
  EXPECT_EQ(order.size(), LazyCanvasNoiseMask::kMaxPendingEvents + 2);
  for (size_t i = 1; i < order.size(); ++i) {
    EXPECT_LT(order[i - 1], order[i]);
  }
  EXPECT_EQ(lazy.pending_events(), 0u);
}

TEST(LazyCanvasNoiseMaskTest, TheByteCapAppliesOldestEventsUntilUnderIt) {
  int ran = 0;
  auto count = [&] { return base::BindOnce([](int* ran, CanvasNoiseMask&) { ++*ran; }, &ran); };
  LazyCanvasNoiseMask lazy;
  lazy.Add(8, 8, LazyCanvasNoiseMask::kMaxPendingBytes - 1, count());
  EXPECT_EQ(ran, 0);
  lazy.Add(8, 8, 2, count());  // over the cap with two events: the oldest goes
  EXPECT_EQ(ran, 1);
  EXPECT_EQ(lazy.pending_events(), 1u);
  EXPECT_EQ(lazy.pending_bytes(), 2u);
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

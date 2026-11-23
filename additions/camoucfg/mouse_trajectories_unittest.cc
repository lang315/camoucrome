// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/mouse_trajectories.h"

#include <algorithm>
#include <bit>
#include <cmath>
#include <limits>
#include <tuple>
#include <utility>
#include <vector>

#include "base/time/time.h"
#include "testing/gtest/include/gtest/gtest.h"
#include "ui/gfx/geometry/point_f.h"
#include "ui/gfx/geometry/size_f.h"

namespace camoucfg {
namespace {

TEST(MouseTrajectoriesTest, EndpointsAreExact) {
  auto path = camoucfg::HumanizeTrajectory(
      {10, 20}, {300, 400}, /*steps=*/24, /*min_ms=*/40, /*max_ms=*/120,
      /*seed=*/1234);
  ASSERT_GE(path.size(), 2u);
  EXPECT_EQ(path.front().x, 10.0);
  EXPECT_EQ(path.front().y, 20.0);
  EXPECT_EQ(path.back().x, 300.0);
  EXPECT_EQ(path.back().y, 400.0);
}

TEST(MouseTrajectoriesTest, StepCountAndMonotonicTiming) {
  auto path = camoucfg::HumanizeTrajectory(
      {0, 0}, {100, 100}, 24, 40, 120, 1234);
  EXPECT_EQ(path.size(), 25u);  // steps + 1
  for (size_t i = 1; i < path.size(); ++i)
    EXPECT_GT(path[i].offset, path[i - 1].offset);
  EXPECT_GE(path.back().offset, base::Milliseconds(40));
  EXPECT_LE(path.back().offset, base::Milliseconds(120));
}

TEST(MouseTrajectoriesTest, DeterministicGivenSeed) {
  auto a = camoucfg::HumanizeTrajectory({0, 0}, {100, 100}, 24, 40, 120, 7);
  auto b = camoucfg::HumanizeTrajectory({0, 0}, {100, 100}, 24, 40, 120, 7);
  ASSERT_EQ(a.size(), b.size());
  for (size_t i = 0; i < a.size(); ++i) {
    EXPECT_EQ(a[i].x, b[i].x);
    EXPECT_EQ(a[i].y, b[i].y);
    EXPECT_EQ(a[i].offset, b[i].offset);
  }
}

TEST(MouseTrajectoriesTest, PathStaysWithinBoundingBoxSlack) {
  // A human curve bows off the straight line but not wildly. Assert the path
  // stays within a generous bounding box around the segment, so a bug that
  // sends the cursor across the screen is caught.
  auto path = camoucfg::HumanizeTrajectory({0, 0}, {100, 0}, 24, 40, 120, 9);
  for (const auto& p : path) {
    EXPECT_GE(p.x, -50);
    EXPECT_LE(p.x, 150);
    EXPECT_GE(p.y, -80);
    EXPECT_LE(p.y, 80);
  }
}

// The four tests above only prove HumanizeTrajectory returns steps+1 points
// from start to end within a slack box -- a degenerate straight-line, even-
// timing, seed-ignoring implementation passes all of them. These three close
// that gap by asserting the humanization itself: seed-dependence, spatial
// bow, and timing jitter.

TEST(MouseTrajectoriesTest, DifferentSeedsGiveDifferentPaths) {
  auto a = camoucfg::HumanizeTrajectory({0, 0}, {200, 200}, 24, 40, 120, 1);
  auto b = camoucfg::HumanizeTrajectory({0, 0}, {200, 200}, 24, 40, 120, 2);
  ASSERT_EQ(a.size(), b.size());
  bool any_differs = false;
  for (size_t i = 0; i < a.size(); ++i)
    if (a[i].x != b[i].x || a[i].y != b[i].y) any_differs = true;
  EXPECT_TRUE(any_differs) << "seed is ignored: two seeds gave one path";
}

TEST(MouseTrajectoriesTest, PathBowsOffTheStraightLine) {
  // {0,0}->{100,0} is horizontal, so a straight interpolation has y==0
  // everywhere. A humanized curve bows off it.
  auto path = camoucfg::HumanizeTrajectory({0, 0}, {100, 0}, 24, 40, 120, 9);
  double max_abs_y = 0;
  for (size_t i = 1; i + 1 < path.size(); ++i)
    max_abs_y = std::max(max_abs_y, std::abs(path[i].y));
  EXPECT_GT(max_abs_y, 1.0) << "path is a straight line; no spatial humanization";
}

TEST(MouseTrajectoriesTest, InterPointTimingIsNotUniform) {
  auto path = camoucfg::HumanizeTrajectory({0, 0}, {100, 100}, 24, 40, 120, 9);
  ASSERT_GE(path.size(), 3u);
  base::TimeDelta first = path[1].offset - path[0].offset;
  bool any_differs = false;
  for (size_t i = 2; i < path.size(); ++i)
    if ((path[i].offset - path[i - 1].offset) != first) any_differs = true;
  EXPECT_TRUE(any_differs) << "intervals uniform; timing not humanized";
}

// Config values are untrusted (humanize:minTime/maxTime, no schema clamps
// them), so an inverted or negative range must be sanitized here rather than
// being fatal at the old CHECK_LE or producing negative delays. Whole-branch
// review found the crash: {minTime:200, maxTime:100} killed the browser on the
// first humanized move.
TEST(MouseTrajectoriesTest, InvertedOrNegativeRangeIsSanitizedNotFatal) {
  // Inverted 200/100 sanitizes to a valid [100, 200] duration -- no CHECK,
  // strictly increasing (hence positive) offsets, endpoints exact.
  auto a = camoucfg::HumanizeTrajectory({0, 0}, {100, 100}, 24, 200, 100, 3);
  ASSERT_EQ(a.size(), 25u);
  EXPECT_EQ(a.front().x, 0.0);
  EXPECT_EQ(a.back().x, 100.0);
  for (size_t i = 1; i < a.size(); ++i)
    EXPECT_GT(a[i].offset, a[i - 1].offset);
  EXPECT_GE(a.back().offset, base::Milliseconds(100));
  EXPECT_LE(a.back().offset, base::Milliseconds(200));

  // A negative min floors to 1ms, so the first interval is still positive.
  auto b = camoucfg::HumanizeTrajectory({0, 0}, {50, 50}, 10, -5, 30, 3);
  ASSERT_GE(b.size(), 2u);
  EXPECT_GT(b[1].offset, base::TimeDelta());
}

TEST(MouseTrajectoriesTest, QuantizeWheelRoundsToWholeNotches) {
  struct Case {
    double dx, dy;
    int x, y;
  } cases[] = {
      {0, 0, 0, 0},       {0, 40, 0, 1},      {0, 50, 0, 1},
      {0, 100, 0, 1},     {0, 149, 0, 1},     {0, 150, 0, 2},
      {0, 250, 0, 3},     {0, -250, 0, -3},   {-300, 100, -3, 1},
      {-250, 0, -3, 0},
  };
  for (const Case& c : cases) {
    WheelNotches n = QuantizeWheel(c.dx, c.dy);
    EXPECT_EQ(n.x, c.x) << c.dx << "," << c.dy;
    EXPECT_EQ(n.y, c.y) << c.dx << "," << c.dy;
  }
}

TEST(MouseTrajectoriesTest, QuantizeWheelClampsAndRejectsNonFinite) {
  EXPECT_EQ(QuantizeWheel(0, 1e9).y, kMaxWheelNotches);
  EXPECT_EQ(QuantizeWheel(-1e9, 0).x, -kMaxWheelNotches);
  constexpr double kInf = std::numeric_limits<double>::infinity();
  for (double bad : {std::nan(""), kInf, -kInf}) {
    WheelNotches n = QuantizeWheel(bad, 100);
    EXPECT_EQ(n.x, 0);
    EXPECT_EQ(n.y, 0) << "non-finite input must take the stock path";
  }
}

TEST(MouseTrajectoriesTest, HumanizePathDefaultsConstants) {
  EXPECT_EQ(kDefaultHumanizeMinMs, 80);
  EXPECT_EQ(kDefaultHumanizeMaxMs, 1200);
}

TEST(MouseTrajectoriesTest, HumanizePathEndpointsAndOffsets) {
  auto path = HumanizePath({10, 20}, {300, 400}, 80, 1200, /*seed=*/7);
  ASSERT_GE(path.size(), 2u);
  EXPECT_EQ(path.front().x, 10.0);
  EXPECT_EQ(path.front().y, 20.0);
  EXPECT_EQ(path.front().offset, base::TimeDelta());
  EXPECT_EQ(path.back().x, 300.0);
  EXPECT_EQ(path.back().y, 400.0);
  for (size_t i = 1; i < path.size(); ++i) {
    EXPECT_GT(path[i].offset, path[i - 1].offset);
  }
}

TEST(MouseTrajectoriesTest, HumanizePathReturnsEmptyWhenNotAMove) {
  // Not a move: the caller takes stock's path. (The Bezier fallback for a
  // valid move needs an empty recording table, which no test can arrange.)
  EXPECT_TRUE(HumanizePath({50, 50}, {50, 50}, 80, 1200, 7).empty());
  constexpr float kNan = std::numeric_limits<float>::quiet_NaN();
  constexpr float kInf = std::numeric_limits<float>::infinity();
  EXPECT_TRUE(HumanizePath({kNan, 0}, {10, 10}, 80, 1200, 1).empty());
  EXPECT_TRUE(HumanizePath({0, 0}, {10, kInf}, 80, 1200, 1).empty());
}

TEST(MouseTrajectoriesTest, HumanizePathUsesRecordedTimings) {
  // A recorded 600 px move is sampled at ~60 Hz, so it has well over the
  // Bezier fallback's 25 points (gap-variety does not distinguish them: the
  // Bezier's gaps are jittered too).
  for (uint64_t seed : {3, 4, 5}) {
    auto path = HumanizePath({0, 0}, {900, 0}, 80, 1200, seed);
    EXPECT_GT(path.size(), 25u) << "seed " << seed;
  }
}

TEST(MouseTrajectoriesTest, HumanizePathDurationWithinBounds) {
  for (float dist : {3.0f, 50.0f, 400.0f, 4000.0f}) {
    auto path = HumanizePath({0, 0}, {dist, 0}, 80, 1200, /*seed=*/11);
    ASSERT_GE(path.size(), 2u);
    EXPECT_GE(path.back().offset, base::Milliseconds(80));
    EXPECT_LE(path.back().offset, base::Milliseconds(1200));
  }
}

TEST(MouseTrajectoriesTest, HumanizePathSanitizesBounds) {
  const base::TimeDelta kCap = base::Milliseconds(10000);  // cursory::kMaxDurationMs
  for (auto [lo, hi] : {std::pair{900, 100}, std::pair{-5, 0},
                        std::pair{0, 1'000'000'000}}) {
    auto path = HumanizePath({0, 0}, {300, 200}, lo, hi, /*seed=*/5);
    ASSERT_GE(path.size(), 2u);
    EXPECT_GT(path.back().offset, base::TimeDelta());
    EXPECT_LE(path.back().offset, kCap);
  }
}

TEST(MouseTrajectoriesTest, SnapToDeviceGridLandsOnTheLattice) {
  // origin 0: k / dsf.
  EXPECT_DOUBLE_EQ(SnapToDeviceGrid(100.37, 1.25f, 0), 100.0);
  EXPECT_DOUBLE_EQ(SnapToDeviceGrid(-3.7, 1.25f, 0), -4.0);  // half away
  EXPECT_EQ(SnapToDeviceGrid(7.4, 1.0f, 0), 7.0);
  // origin o: k / dsf - o, so (snap + o) * dsf is a whole number. At dsf 1.25
  // an origin of 1 DIP puts the page's own grid at a fraction of .25.
  for (double origin : {0.0, 1.0, 3.0, 85.0}) {
    for (int i = 0; i < 1000; ++i) {
      double v = i * 0.7319 + 0.37;
      double s = SnapToDeviceGrid(v, 1.25f, origin);
      EXPECT_NEAR((s + origin) * 1.25, std::round((s + origin) * 1.25), 1e-9)
          << v << " o=" << origin;
      EXPECT_LE(std::abs(s - v), 0.4 + 1e-9);
    }
  }
  // The measured host layout (H2 control, 2026-11-21): the view sits at
  // (8, 87) DIP in its window, dsf 1.25. clientX * dpr is integral (8 % 4 == 0)
  // and clientY * dpr has the fraction .25, frac(-1.25 * 87).
  EXPECT_NEAR(std::remainder(SnapToDeviceGrid(300.4, 1.25f, 8) * 1.25, 1.0), 0.0,
              1e-9);
  EXPECT_NEAR(std::remainder(SnapToDeviceGrid(300.4, 1.25f, 87) * 1.25, 1.0), 0.25,
              1e-9);
}

TEST(MouseTrajectoriesTest, SnapToDeviceGridKeepsAnInsidePointInside) {
  // 800 DIP at 1.25 is 1000 device px: 799.7 rounds to 800, outside [0, 800).
  EXPECT_DOUBLE_EQ(SnapToDeviceGrid(799.7, 1.25f, 0, 0), 800.0);  // no extent
  EXPECT_NEAR(SnapToDeviceGrid(799.7, 1.25f, 0, 800), 799.2, 1e-9);
  // The low edge: with origin -2 the lattice has -0.4 and 0.4; 0 rounds down
  // (half away from zero, on a negative product) to -0.4, outside.
  EXPECT_NEAR(SnapToDeviceGrid(0.0, 1.25f, -2, 800), 0.4, 1e-9);
  // A point that was outside stays where the plain snap puts it.
  EXPECT_DOUBLE_EQ(SnapToDeviceGrid(-3.7, 1.25f, 0, 800), -4.0);
  EXPECT_DOUBLE_EQ(SnapToDeviceGrid(803.7, 1.25f, 0, 800), 804.0);
  // Every inside input gives an inside lattice point, whatever the origin.
  for (double origin : {0.0, 3.0, -2.0, 87.0}) {
    for (int i = 0; i < 4000; ++i) {
      double v = i * 0.2 + 0.01;
      if (v >= 800) {
        break;
      }
      double s = SnapToDeviceGrid(v, 1.25f, origin, 800);
      EXPECT_GE(s, 0) << v << " o=" << origin;
      EXPECT_LT(s, 800) << v << " o=" << origin;
      EXPECT_NEAR((s + origin) * 1.25, std::round((s + origin) * 1.25), 1e-9)
          << v << " o=" << origin;
    }
  }
}

TEST(MouseTrajectoriesTest, SnapToDeviceGridLeavesUnusableInputAlone) {
  const float nan = std::numeric_limits<float>::quiet_NaN();
  EXPECT_EQ(SnapToDeviceGrid(10.3, 0.0f, 0), 10.3);
  EXPECT_EQ(SnapToDeviceGrid(10.3, -1.0f, 0), 10.3);
  EXPECT_EQ(SnapToDeviceGrid(10.3, nan, 0), 10.3);
  EXPECT_EQ(SnapToDeviceGrid(10.3, 1.25f, nan), 10.3);
  EXPECT_TRUE(std::isnan(SnapToDeviceGrid(nan, 1.25f, 0)));
}

TEST(MouseTrajectoriesTest, OnlyAMoveInsideTheViewCanBeARepeat) {
  const gfx::SizeF size(800, 600);
  EXPECT_TRUE(IsRepeatedPosition({10, 20}, {10, 20}, size));
  EXPECT_FALSE(IsRepeatedPosition({10, 20}, {10, 21}, size));
  // The same point outside the view is the pointer's exit, never a repeat: its
  // event is how the page learns the pointer left.
  EXPECT_FALSE(IsRepeatedPosition({-3, 300}, {-3, 300}, size));
  EXPECT_FALSE(IsRepeatedPosition({800, 20}, {800, 20}, size));
  EXPECT_FALSE(IsRepeatedPosition({std::numeric_limits<float>::quiet_NaN(), 5},
                                  {std::numeric_limits<float>::quiet_NaN(), 5},
                                  size));
}

TEST(MouseTrajectoriesTest, PointInViewIsAHalfOpenFloatTest) {
  const gfx::SizeF size(800, 600);
  // x or y in (-1, 0): the integer Rect::Contains truncates these to 0 and
  // accepts them.
  EXPECT_FALSE(PointInView({-0.5f, 10}, size));
  EXPECT_FALSE(PointInView({10, -0.5f}, size));
  EXPECT_FALSE(PointInView({-0.8f, 10}, size));
  EXPECT_FALSE(PointInView({800, 0}, size));
  EXPECT_FALSE(PointInView({0, 600}, size));
  EXPECT_FALSE(PointInView({std::numeric_limits<float>::quiet_NaN(), 5}, size));
  EXPECT_TRUE(PointInView({0, 0}, size));
  EXPECT_TRUE(PointInView({799.2f, 599.2f}, size));
}

// A Cursory-like path: one point per 16.7 ms along a curve (x quadratic in t).
std::vector<TrajectoryPoint> CursoryLike(int points) {
  std::vector<TrajectoryPoint> path;
  for (int i = 0; i < points; ++i) {
    double t = i * 16.7;
    path.push_back({t * 0.3 + t * t * 0.0004, 50 + t * 0.1,
                    base::Milliseconds(t)});
  }
  return path;
}

std::vector<double> Gaps(const std::vector<TrajectoryPoint>& path) {
  std::vector<double> gaps;
  for (size_t i = 1; i < path.size(); ++i) {
    gaps.push_back((path[i].offset - path[i - 1].offset).InMillisecondsF());
  }
  return gaps;
}

TEST(MouseTrajectoriesTest, ResampleSpacingMatchesTheRate) {
  const auto in = CursoryLike(60);
  for (auto [hz, period, tol] :
       {std::tuple{125u, 8.0, 1.0}, std::tuple{1000u, 1.0, 0.1}}) {
    auto out = ResampleToPollRate(in, hz, 42);
    ASSERT_GT(out.size(), in.size()) << hz;
    std::vector<double> gaps = Gaps(out);
    // every gap but the last (the end takes the place of a grid sample)
    for (size_t i = 0; i + 1 < gaps.size(); ++i) {
      EXPECT_GT(gaps[i], period - tol - 1e-6) << hz << " " << i;
      EXPECT_LT(gaps[i], period + tol + 1e-6) << hz << " " << i;
    }
    EXPECT_GT(gaps.back(), period / 2 - tol - 1e-6) << hz;
    EXPECT_LT(gaps.back(), period * 1.5 + tol) << hz;
  }
}

// Blink's TimeClamper (core/timing/time_clamper.cc) for event.timeStamp: the
// time is cut to its 100 us interval, and rounded up to the next one when it is
// past a pseudorandom threshold of that interval (a murmur hash of the interval
// and a per-process secret).
double ClampedMs(int64_t us, uint64_t secret) {
  auto murmur = [](uint64_t v) {
    v ^= v >> 33;
    v *= uint64_t{0xFF51AFD7ED558CCD};
    v ^= v >> 33;
    v *= uint64_t{0xC4CEB9FE1A85EC53};
    v ^= v >> 33;
    return v;
  };
  const int64_t clamped = us - us % 100;
  const uint64_t bits =
      (murmur(static_cast<uint64_t>(clamped) ^ secret) &
       uint64_t{0x000FFFFFFFFFFFFF}) |
      uint64_t{0x3FF0000000000000};
  double u = std::bit_cast<double>(bits) - 1;
  return static_cast<double>(us >= clamped + 100 * u ? clamped + 100
                                                     : clamped) /
         1000.0;
}

// I2b core_share and I2c whole_share as the page reads them, through the
// TimeClamper, from an arbitrary time origin. The control's pooled values are
// .602 (+-.037) and .258 (+-.060); the band here is half of each tolerance. The
// old +-0.2 ms jitter gave 1.00 and .10, and +-0.4 ms with 16 % repeats gave
// .60 and .21.
TEST(MouseTrajectoriesTest, Resample125HzCoreAndWholeShareMatchAMouseStream) {
  const auto in = CursoryLike(60);
  int core = 0;
  int whole = 0;
  int total = 0;
  for (uint64_t seed = 1; seed <= 300; ++seed) {
    const int64_t origin_us = 1'000'000'000 + static_cast<int64_t>(seed * 7919);
    std::vector<double> stamps_ms;
    auto out = ResampleToPollRate(in, 125, seed);
    for (size_t i = 1; i + 1 < out.size(); ++i) {  // interior samples only
      stamps_ms.push_back(ClampedMs(
          origin_us + out[i].offset.InMicroseconds(), seed * 0x9E3779B97F4A7C15));
    }
    for (size_t i = 1; i < stamps_ms.size(); ++i) {
      const double gap = stamps_ms[i] - stamps_ms[i - 1];
      ++total;
      core += std::abs(gap - 8.0) <= 0.25 + 1e-9;
      whole += std::abs(gap - std::round(gap)) < 0.05;
    }
  }
  const double core_share = static_cast<double>(core) / total;
  const double whole_share = static_cast<double>(whole) / total;
  EXPECT_GT(core_share, 0.583) << core_share;
  EXPECT_LT(core_share, 0.621) << core_share;
  EXPECT_GT(whole_share, 0.228) << whole_share;
  EXPECT_LT(whole_share, 0.288) << whole_share;
}

TEST(MouseTrajectoriesTest, ResampleIsMonotonicAndKeepsTheEnds) {
  const auto in = CursoryLike(40);
  for (uint32_t hz : {125u, 1000u}) {
    auto out = ResampleToPollRate(in, hz, 7);
    for (size_t i = 1; i < out.size(); ++i) {
      EXPECT_GT(out[i].offset, out[i - 1].offset);
    }
    EXPECT_EQ(out.front().x, in.front().x);
    EXPECT_EQ(out.front().offset, in.front().offset);
    EXPECT_EQ(out.back().x, in.back().x);
    EXPECT_EQ(out.back().y, in.back().y);
    EXPECT_EQ(out.back().offset, in.back().offset);  // duration unchanged
  }
}

TEST(MouseTrajectoriesTest, ResampleStaysOnTheCurveThroughTheInputPoints) {
  // Constant-speed straight motion: the interpolant is exact, so every sample
  // lies on the line, which every input point lies on (up to the microsecond
  // the offsets are stored in: 1 us at 0.5 px/ms is 5e-4 px).
  std::vector<TrajectoryPoint> in;
  for (int i = 0; i < 30; ++i) {
    double t = i * 16.7;
    in.push_back({100 + 0.5 * t, 200 - 0.25 * t, base::Milliseconds(t)});
  }
  for (uint32_t hz : {125u, 1000u}) {
    for (const auto& p : ResampleToPollRate(in, hz, 3)) {
      double t = p.offset.InMillisecondsF();
      EXPECT_NEAR(p.x, 100 + 0.5 * t, 1e-3);
      EXPECT_NEAR(p.y, 200 - 0.25 * t, 1e-3);
    }
  }
  // Curved input: a sample that lands within a millisecond of an input point
  // is within the curve's slope of it.
  const auto curved = CursoryLike(30);
  for (const auto& p : ResampleToPollRate(curved, 1000, 5)) {
    for (const auto& q : curved) {
      if (std::abs((p.offset - q.offset).InMillisecondsF()) < 0.05) {
        EXPECT_NEAR(p.x, q.x, 0.05);
        EXPECT_NEAR(p.y, q.y, 0.05);
      }
    }
  }
}

TEST(MouseTrajectoriesTest, ResampleIsDeterministicPerSeedAndVariesWithIt) {
  const auto in = CursoryLike(20);
  auto a = ResampleToPollRate(in, 125, 9);
  auto b = ResampleToPollRate(in, 125, 9);
  auto c = ResampleToPollRate(in, 125, 10);
  ASSERT_EQ(a.size(), b.size());
  bool differs = false;
  for (size_t i = 1; i + 1 < a.size() && i + 1 < c.size(); ++i) {
    EXPECT_EQ(a[i].offset, b[i].offset);
    differs |= a[i].offset != c[i].offset;
  }
  EXPECT_TRUE(differs);
}

TEST(MouseTrajectoriesTest, ResampleReturnsUnusableInputUnchanged) {
  const auto in = CursoryLike(5);
  EXPECT_EQ(ResampleToPollRate(in, 0, 1).size(), in.size());
  EXPECT_EQ(ResampleToPollRate({in[0]}, 125, 1).size(), 1u);
  auto flat = in;
  flat[2].offset = flat[1].offset;  // not increasing
  EXPECT_EQ(ResampleToPollRate(flat, 125, 1).size(), flat.size());
}

}  // namespace
}  // namespace camoucfg

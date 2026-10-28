// Copyright 2026 The Camoucrome Authors. Derived from cursory 2.1.0
// (Vinyzu), LGPL-3.0-or-later; see NOTICE and LICENSE.

#include "components/camoucfg_lgpl/cursory.h"

#ifdef UNSAFE_BUFFERS_BUILD
// The generated table is indexed as raw extern arrays (kRecordings, kX, kY, kT)
// within bounds the pinned table test checks; spans would need a copy of 113k points.
#pragma allow_unsafe_buffers
#endif

#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

#include "components/camoucfg_lgpl/cursory_data.h"
#include "testing/gtest/include/gtest/gtest.h"

namespace cursory {
namespace {

// Small deterministic generator for test inputs (not the code under test).
struct Lcg {
  uint64_t s;
  double Next(double lo, double hi) {
    s = s * 6364136223846793005ull + 1442695040888963407ull;
    return lo + (hi - lo) * static_cast<double>(s >> 11) / 9007199254740992.0;
  }
};

bool AllFinite(const std::vector<Sample>& v) {
  for (const Sample& s : v) {
    if (!std::isfinite(s.x) || !std::isfinite(s.y))
      return false;
  }
  return true;
}

double Median(std::vector<int64_t> v) {
  std::sort(v.begin(), v.end());
  return double(v[v.size() / 2]);
}

TEST(CursoryTest, EndpointsExact) {
  auto v = GenerateTrajectory(10, 20, 900, 500, 1);
  ASSERT_GE(v.size(), 2u);
  EXPECT_EQ(v.front().x, 10.0);
  EXPECT_EQ(v.front().y, 20.0);
  EXPECT_EQ(v.front().t_ms, 0);
  EXPECT_EQ(v.back().x, 900.0);
  EXPECT_EQ(v.back().y, 500.0);
}

TEST(CursoryTest, DeterministicPerSeed) {
  auto a = GenerateTrajectory(10, 20, 900, 500, 7);
  auto b = GenerateTrajectory(10, 20, 900, 500, 7);
  ASSERT_FALSE(a.empty());
  ASSERT_EQ(a.size(), b.size());
  for (size_t i = 0; i < a.size(); ++i) {
    EXPECT_EQ(a[i].x, b[i].x);
    EXPECT_EQ(a[i].y, b[i].y);
    EXPECT_EQ(a[i].t_ms, b[i].t_ms);
  }
}

TEST(CursoryTest, DifferentSeedsDiffer) {
  auto a = GenerateTrajectory(10, 20, 900, 500, 1);
  auto b = GenerateTrajectory(10, 20, 900, 500, 2);
  bool differ = a.size() != b.size();
  for (size_t i = 0; !differ && i < a.size(); ++i)
    differ = a[i].x != b[i].x || a[i].y != b[i].y || a[i].t_ms != b[i].t_ms;
  EXPECT_TRUE(differ);
}

TEST(CursoryTest, TimesStrictlyIncreasing) {
  Lcg rng{99};
  for (int i = 0; i < 200; ++i) {
    // Odd cases use 240 Hz with 5 ms jitter, which rounds many intervals to
    // the same millisecond unless duplicates are dropped.
    Params p;
    if (i % 2) {
      p.frequency_hz = 240;
      p.frequency_jitter_ms = 5;
    }
    auto v = GenerateTrajectory(rng.Next(0, 1900), rng.Next(0, 1000),
                                rng.Next(0, 1900), rng.Next(0, 1000), i, p);
    ASSERT_GE(v.size(), 2u);
    for (size_t k = 1; k < v.size(); ++k)
      ASSERT_GT(v[k].t_ms, v[k - 1].t_ms) << "seed " << i << " index " << k;
  }
}

TEST(CursoryTest, DurationWithinBounds) {
  Params p;
  p.min_ms = 80;
  p.max_ms = 1200;
  for (double d : {3.0, 50.0, 400.0, 4000.0, 10000.0}) {
    for (uint64_t seed = 0; seed < 20; ++seed) {
      auto v = GenerateTrajectory(100, 100, 100 + d, 100, seed, p);
      ASSERT_FALSE(v.empty());
      EXPECT_GE(v.back().t_ms, 80) << "d=" << d << " seed=" << seed;
      EXPECT_LE(v.back().t_ms, 1200) << "d=" << d << " seed=" << seed;
    }
  }
}

TEST(CursoryTest, ZeroAndNonFiniteReturnEmpty) {
  const double nan = std::numeric_limits<double>::quiet_NaN();
  const double inf = std::numeric_limits<double>::infinity();
  EXPECT_TRUE(GenerateTrajectory(5, 5, 5, 5, 1).empty());
  EXPECT_TRUE(GenerateTrajectory(nan, 0, 10, 10, 1).empty());
  EXPECT_TRUE(GenerateTrajectory(0, 0, 10, nan, 1).empty());
  EXPECT_TRUE(GenerateTrajectory(0, 0, inf, 10, 1).empty());
  EXPECT_TRUE(GenerateTrajectory(-inf, 0, 10, 10, 1).empty());
}

TEST(CursoryTest, AllFinite) {
  for (uint64_t seed = 0; seed < 50; ++seed) {
    auto l = GenerateTrajectory(0, 0, 1500, 800, seed);
    auto s = GenerateTrajectory(0, 0, 2, 1, seed);
    ASSERT_FALSE(l.empty());
    ASSERT_FALSE(s.empty());
    EXPECT_TRUE(AllFinite(l));
    EXPECT_TRUE(AllFinite(s));
    auto h1 = GenerateTrajectory(0, 0, 1e9, 1e9, seed);
    auto h2 = GenerateTrajectory(0, 0, 1e9, 0, seed);
    ASSERT_FALSE(h1.empty());
    ASSERT_FALSE(h2.empty());
    EXPECT_TRUE(AllFinite(h1));
    EXPECT_TRUE(AllFinite(h2));
  }
}

// Direction choice is guarded by SelectionPrefersMatchingDirection below: a
// path-excursion check here cannot tell it apart, because Morph rotates any
// recording onto the target.

TEST(CursoryTest, InvertedBoundsSanitized) {
  Params a;
  a.min_ms = 900;
  a.max_ms = 100;
  auto va = GenerateTrajectory(0, 0, 300, 200, 3, a);
  ASSERT_FALSE(va.empty());
  EXPECT_GE(va.back().t_ms, 100);
  EXPECT_LE(va.back().t_ms, 900);

  Params b;
  b.min_ms = -5;
  b.max_ms = 0;
  auto vb = GenerateTrajectory(0, 0, 300, 200, 3, b);
  ASSERT_FALSE(vb.empty());
  // min -> 1, max -> max(1, 0) = 1: the total is exactly 1 ms.
  EXPECT_EQ(vb.back().t_ms, 1);
  for (size_t i = 1; i < vb.size(); ++i)
    EXPECT_GE(vb[i].t_ms, 1);
}

TEST(CursoryTest, TableMatchesPinned) {
  EXPECT_EQ(data::kRecordingCount, 2356u);
  EXPECT_EQ(data::kPointCount, 112984u);
  for (size_t i = 0; i < data::kRecordingCount; ++i) {
    const auto& r = data::kRecordings[i];
    ASSERT_LE(size_t{r.first_point} + r.point_count, data::kPointCount);
  }
}

TEST(CursoryTest, HugeBoundsAreCapped) {
  Params p;
  p.min_ms = 2000000000;
  p.max_ms = 2000000000;
  auto v = GenerateTrajectory(0, 0, 300, 200, 5, p);
  ASSERT_FALSE(v.empty());
  EXPECT_LT(v.size(), 20000u);
  EXPECT_LE(v.back().t_ms, 60000);
}

TEST(CursoryTest, DirectnessShiftsSelection) {
  auto efficiency = [](size_t i) {
    const auto& r = data::kRecordings[i];
    size_t a = r.first_point, b = a + r.point_count - 1;
    double dx = static_cast<double>(data::kX[b]) - data::kX[a];
    double dy = static_cast<double>(data::kY[b]) - data::kY[a];
    return std::hypot(dx, dy) / r.length;
  };
  double lo = 0, hi = 0;
  const int kSeeds = 200;
  for (int seed = 0; seed < kSeeds; ++seed) {
    lo += efficiency(internal::SelectRecordingForTesting(500, 0, 0.0, seed));
    hi += efficiency(internal::SelectRecordingForTesting(500, 0, 1.0, seed));
  }
  EXPECT_GT(hi / kSeeds, lo / kSeeds);
}

// Guards the port against silent drift: the recording chosen for a rightward
// move must itself head roughly right, before any morph rotates it.
TEST(CursoryTest, SelectionPrefersMatchingDirection) {
  double sum_deg = 0;
  const int kSeeds = 200;
  for (int seed = 0; seed < kSeeds; ++seed) {
    size_t i = internal::SelectRecordingForTesting(500, 0, 0.65, seed);
    ASSERT_LT(i, data::kRecordingCount);
    const auto& r = data::kRecordings[i];
    size_t a = r.first_point, b = a + r.point_count - 1;
    double dx = static_cast<double>(data::kX[b]) - data::kX[a];
    double dy = static_cast<double>(data::kY[b]) - data::kY[a];
    sum_deg += std::fabs(std::atan2(dy, dx)) * 180.0 / 3.14159265358979323846;
  }
  EXPECT_LT(sum_deg / kSeeds, 25.0);
}

// Humans take longer for longer moves; the sqrt scaling plus the min/max clamp
// must preserve that order for the default bounds.
TEST(CursoryTest, TimingScalesWithDistance) {
  std::vector<int64_t> shortm, longm;
  for (uint64_t seed = 0; seed < 100; ++seed) {
    auto s = GenerateTrajectory(100, 100, 150, 100, seed);
    auto l = GenerateTrajectory(100, 100, 900, 100, seed);
    ASSERT_FALSE(s.empty());
    ASSERT_FALSE(l.empty());
    shortm.push_back(s.back().t_ms);
    longm.push_back(l.back().t_ms);
  }
  EXPECT_LT(Median(shortm), Median(longm));
}

}  // namespace
}  // namespace cursory

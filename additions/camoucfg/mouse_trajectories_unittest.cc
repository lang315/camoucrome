// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/mouse_trajectories.h"

#include <algorithm>
#include <cmath>

#include "base/time/time.h"
#include "testing/gtest/include/gtest/gtest.h"
#include "ui/gfx/geometry/point_f.h"

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

}  // namespace
}  // namespace camoucfg

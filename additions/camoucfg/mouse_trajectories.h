// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_MOUSE_TRAJECTORIES_H_
#define COMPONENTS_CAMOUCFG_MOUSE_TRAJECTORIES_H_

#include <cstdint>
#include <vector>

#include "base/time/time.h"
#include "ui/gfx/geometry/point_f.h"

// Human-like mouse movement generator. Ported from the camoufox project's
// additions/camoucfg/MouseTrajectories.hpp, itself adapted from:
// https://github.com/riflosnake/HumanCursor/blob/main/humancursor/utilities/human_curve_generator.py
//
// The curve math (a cubic Bezier through two randomized control points,
// evaluated via the Bernstein-polynomial form) is kept from that port. Two
// things are not: this file has no process-global config to read, so timing
// bounds and the random seed are ordinary arguments (the caller, Task 3,
// owns reading camoucfg for those); and this tree bans <random> (see
// GetRandomOrder in components/embedder_support/user_agent_utils.cc for the
// precedent), so mouse_trajectories.cc hand-rolls a small seeded PRNG rather
// than using an STL engine.

namespace camoucfg {

struct TrajectoryPoint {
  double x;
  double y;
  base::TimeDelta offset;
};

// Returns `steps` + 1 points from `start` to `end` inclusive along a
// human-like Bezier curve, with monotonically increasing offsets summing to
// a duration drawn uniformly from [min_ms, max_ms]. Deterministic given
// `seed`: the same arguments always produce the same path, which is what
// makes this testable without flakiness. Production callers should pass a
// fresh `base::RandUint64()` per move so different moves are not identical.
std::vector<TrajectoryPoint> HumanizeTrajectory(
    gfx::PointF start, gfx::PointF end, int steps,
    int min_ms, int max_ms, uint64_t seed);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_MOUSE_TRAJECTORIES_H_

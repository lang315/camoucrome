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

// Movement-time bounds used when humanize:minTime / humanize:maxTime are absent.
inline constexpr int kDefaultHumanizeMinMs = 80;
inline constexpr int kDefaultHumanizeMaxMs = 1200;

// A recorded-human path from `start` to `end` (the cursory generator), with
// the movement time in [min_ms, max_ms] (sanitized by the generator). Falls
// back to HumanizeTrajectory (24 steps, same bounds) when the generator
// returns nothing, so the result always has >= 2 points, strictly increasing
// offsets, front == start at offset 0 and back == end. Deterministic per seed.
std::vector<TrajectoryPoint> HumanizePath(gfx::PointF start,
                                          gfx::PointF end,
                                          int min_ms,
                                          int max_ms,
                                          uint64_t seed);

// A wheel turns in whole notches. Signed notch counts per axis for a CDP
// wheel delta: |d| / 100 rounded half away from zero, at least 1 for a
// non-zero delta (Camoufox's rule), clamped to kMaxWheelNotches. A zero or
// non-finite delta on both axes gives {0, 0}: the caller then takes stock's
// path. The event count a caller sends is max(|x|, |y|).
struct WheelNotches {
  int x;
  int y;
};
inline constexpr int kMaxWheelNotches = 60;
WheelNotches QuantizeWheel(double delta_x, double delta_y);

// The page-visible deltaY of one notch on Windows at DPR 1, measured on stock
// Chrome 154 (docs/superpowers/measurements/2026-10-sp2c-wheel.md).
inline constexpr float kWindowsNotchCssPx = 100.0f;

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_MOUSE_TRAJECTORIES_H_

// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/mouse_trajectories.h"

#include <algorithm>
#include <cmath>
#include <vector>

#include "base/check_op.h"
#include "base/time/time.h"
#include "ui/gfx/geometry/point_f.h"

namespace camoucfg {
namespace {

// A small, deterministic pseudo-random generator (SplitMix64, Vigna 2015).
//
// <random> is banned in this tree, and base::RandUint64()/RandGenerator()
// read from the OS's entropy source, so neither is seedable -- and this
// generator's whole reason to exist is that DeterministicGivenSeed must be
// reproducible. GetRandomOrder() in
// components/embedder_support/user_agent_utils.cc is this tree's existing
// precedent for hand-rolling a generator rather than using <random>, though
// its problem (a stable permutation of at most 4 items) is small enough to
// solve with a lookup table; a jittered curve needs an actual stream of
// pseudo-random doubles, hence this instead.
class SplitMix64 {
 public:
  explicit SplitMix64(uint64_t seed) : state_(seed) {}

  uint64_t NextUint64() {
    uint64_t z = (state_ += 0x9E3779B97F4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
  }

  // Uniform in [0, 1): the top 53 bits map exactly onto a double's mantissa.
  double NextDouble() { return (NextUint64() >> 11) * 0x1.0p-53; }

  double NextUniform(double lo, double hi) {
    return lo + (hi - lo) * NextDouble();
  }

 private:
  uint64_t state_;
};

// Binomial coefficient C(n, k), computed iteratively rather than via
// factorials so it does not overflow for the small n this file ever calls it
// with (n == 3, a cubic Bezier).
double BinomialCoefficient(int n, int k) {
  double result = 1.0;
  for (int i = 0; i < k; ++i) {
    result *= static_cast<double>(n - i) / static_cast<double>(i + 1);
  }
  return result;
}

double BernsteinBasis(double t, int i, int n) {
  return BinomialCoefficient(n, i) * std::pow(t, i) * std::pow(1 - t, n - i);
}

// Evaluates the Bezier curve through `control` at parameter t in [0, 1].
//
// At t == 0 and t == 1 exactly, every term but one vanishes to precisely
// zero (0^i for i > 0, or (1-t)^(n-i) for i < n), so this returns
// control.front()/control.back() bit-for-bit -- but HumanizeTrajectory still
// forces the path's endpoints explicitly afterward rather than relying on
// that; see the comment there.
gfx::PointF EvaluateBezier(
    const std::vector<gfx::PointF>& control, double t) {
  int n = static_cast<int>(control.size()) - 1;
  double x = 0.0;
  double y = 0.0;
  for (int i = 0; i <= n; ++i) {
    double basis = BernsteinBasis(t, i, n);
    x += control[i].x() * basis;
    y += control[i].y() * basis;
  }
  return gfx::PointF(static_cast<float>(x), static_cast<float>(y));
}

// A human hand accelerates fast and coasts into the target rather than
// moving at constant speed; this is the same easing the camoufox original
// uses to warp the sampling parameter.
double EaseOutQuad(double n) {
  return -n * (n - 2);
}

}  // namespace

std::vector<TrajectoryPoint> HumanizeTrajectory(
    gfx::PointF start, gfx::PointF end, int steps,
    int min_ms, int max_ms, uint64_t seed) {
  CHECK_GE(steps, 1);
  CHECK_LE(min_ms, max_ms);

  SplitMix64 rng(seed);

  // Two randomized control points bow the path off the straight line, the
  // way camoufox's generateInternalKnots() does. The 80-unit margin around
  // the start/end bounding box is that function's own margin, carried over
  // unchanged.
  double left = std::min(start.x(), end.x()) - 80.0;
  double right = std::max(start.x(), end.x()) + 80.0;
  double down = std::min(start.y(), end.y()) - 80.0;
  double up = std::max(start.y(), end.y()) + 80.0;

  std::vector<gfx::PointF> control = {
      start,
      gfx::PointF(static_cast<float>(rng.NextUniform(left, right)),
                  static_cast<float>(rng.NextUniform(down, up))),
      gfx::PointF(static_cast<float>(rng.NextUniform(left, right)),
                  static_cast<float>(rng.NextUniform(down, up))),
      end,
  };

  std::vector<TrajectoryPoint> path;
  path.reserve(steps + 1);
  for (int i = 0; i <= steps; ++i) {
    double t = EaseOutQuad(static_cast<double>(i) / steps);
    gfx::PointF p = EvaluateBezier(control, t);
    path.push_back({p.x(), p.y(), base::TimeDelta()});
  }

  // Exact endpoints: a Bezier through jittered control points is not trusted
  // to land on `start`/`end` to the ULP, so they are pinned directly.
  path.front().x = start.x();
  path.front().y = start.y();
  path.back().x = end.x();
  path.back().y = end.y();

  // Total duration drawn uniformly from [min_ms, max_ms), then split across
  // the `steps` intervals with per-step jitter (weights in [0.5, 1.5)) so
  // consecutive offsets are not evenly spaced.
  double duration_ms = rng.NextUniform(min_ms, max_ms);
  std::vector<double> weights(steps);
  double total_weight = 0.0;
  for (int i = 0; i < steps; ++i) {
    weights[i] = rng.NextUniform(0.5, 1.5);
    total_weight += weights[i];
  }

  double cumulative_ms = 0.0;
  for (int i = 1; i <= steps; ++i) {
    cumulative_ms += weights[i - 1] / total_weight * duration_ms;
    path[i].offset = base::Milliseconds(cumulative_ms);
  }
  // As with the spatial endpoints, pin the final offset to the drawn
  // duration directly rather than trusting the accumulated sum to land on it
  // exactly.
  path.back().offset = base::Milliseconds(duration_ms);

  return path;
}

}  // namespace camoucfg

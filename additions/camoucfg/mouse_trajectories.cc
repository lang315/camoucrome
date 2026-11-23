// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/mouse_trajectories.h"

#include <algorithm>
#include <cmath>
#include <optional>
#include <vector>

#include "base/check_op.h"
#include "base/time/time.h"
#include "components/camoucfg_lgpl/cursory.h"
#include "ui/gfx/geometry/point_f.h"
#include "ui/gfx/geometry/rect_f.h"

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

  // min_ms/max_ms flow from untrusted config (humanize:minTime/maxTime), and
  // there is no schema layer that clamps them. A hand-written or mis-generated
  // config can invert the range or send a negative -- an inverted range would
  // be fatal at the old CHECK_LE, and a negative min yields negative delays
  // that fire immediately and coalesce to nothing. Sanitize here, at the one
  // place every caller funnels through, rather than trusting each call site:
  // swap an inverted pair, then floor the low end at 1ms so every offset stays
  // positive. steps and seed are programmatic, not config, so their contract
  // stays a CHECK.
  if (min_ms > max_ms) {
    std::swap(min_ms, max_ms);
  }
  min_ms = std::max(1, min_ms);
  max_ms = std::max(min_ms, max_ms);

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

std::vector<TrajectoryPoint> HumanizePath(gfx::PointF start,
                                          gfx::PointF end,
                                          int min_ms,
                                          int max_ms,
                                          uint64_t seed) {
  if (!std::isfinite(start.x()) || !std::isfinite(start.y()) ||
      !std::isfinite(end.x()) || !std::isfinite(end.y()) || start == end) {
    return {};  // Not a move: the caller takes stock's path.
  }
  cursory::Params params;
  params.min_ms = min_ms;
  params.max_ms = max_ms;
  std::vector<cursory::Sample> samples = cursory::GenerateTrajectory(
      start.x(), start.y(), end.x(), end.y(), seed, params);
  if (samples.size() < 2) {
    // A valid move but no generator output (empty table): the Bezier path.
    // Same cap the generator applies, so a hostile bound cannot stretch it.
    return HumanizeTrajectory(
        start, end, /*steps=*/24,
        std::clamp(min_ms, -cursory::kMaxDurationMs, cursory::kMaxDurationMs),
        std::clamp(max_ms, -cursory::kMaxDurationMs, cursory::kMaxDurationMs),
        seed);
  }
  std::vector<TrajectoryPoint> path;
  path.reserve(samples.size());
  for (const cursory::Sample& s : samples) {
    path.push_back({s.x, s.y, base::Milliseconds(s.t_ms)});
  }
  return path;
}

std::vector<TrajectoryPoint> ResampleToPollRate(
    const std::vector<TrajectoryPoint>& path, uint32_t hz, uint64_t seed) {
  if (path.size() < 2 || hz == 0) {
    return path;
  }
  for (size_t i = 1; i < path.size(); ++i) {
    if (path[i].offset <= path[i - 1].offset) {
      return path;
    }
  }
  const double period = 1000.0 / hz;
  // Spacing tolerance: the jitter of a point is half of it, so two neighbours
  // differ by at most the whole. The caller forwards each sample within about
  // 0.1 ms of its time here (a pacer thread, not the UI thread's whole-ms wait)
  // and stamps Now(), as stock does, so the gaps a page reads are these plus
  // that small wake noise. At 125 Hz two neighbours differ by at most 1.1 ms
  // (the jitter of a point is +-0.55 ms), and kWholeShare of the samples take
  // the jitter of the one before: their gap is exactly 8 ms. The page reads a
  // stamp through Blink's TimeClamper (a random rounding threshold per 100 us),
  // under which an exact 8 ms gap is a whole ms two times in three, less the
  // wake noise. The shape is fitted, with the wake noise measured on the host
  // (2026-11-23), so that 59-66 % of the gaps lie within 8 +-0.25 ms (I2b
  // core_share) and 21-29 % are whole ms (I2c whole_share), as in stock's own
  // 125 Hz stream, pooled over the host sessions with SendInput. The unit test
  // repeats the fit under the TimeClamper's rule. The stream's tail (a gap of
  // 10 ms then one of 5) is the harness's own and is not imitated. 1000 Hz
  // keeps +-0.1 ms: no true 1 kHz control exists, unverified.
  constexpr double kWholeShare = 0.40;
  const double tol = hz >= 1000 ? 0.1 : hz == 125 ? 1.1 : period / 16;
  const double jitter = tol / 2;
  const size_t n = path.size();
  std::vector<double> t(n);
  for (size_t i = 0; i < n; ++i) {
    t[i] = path[i].offset.InMillisecondsF();
  }
  // Tangent of the curve in time at each knot (finite differences; one-sided
  // at the ends).
  std::vector<double> mx(n), my(n);
  for (size_t i = 0; i < n; ++i) {
    size_t a = i == 0 ? 0 : i - 1;
    size_t b = i + 1 == n ? n - 1 : i + 1;
    mx[i] = (path[b].x - path[a].x) / (t[b] - t[a]);
    my[i] = (path[b].y - path[a].y) / (t[b] - t[a]);
  }
  auto at = [&](size_t seg, double ms) {
    // The offset is whole microseconds: evaluate where it will be read.
    ms = base::Microseconds(std::llround(ms * 1000.0)).InMillisecondsF();
    double h = t[seg + 1] - t[seg];
    double u = (ms - t[seg]) / h;
    double u2 = u * u, u3 = u2 * u;
    double h00 = 2 * u3 - 3 * u2 + 1, h10 = u3 - 2 * u2 + u;
    double h01 = -2 * u3 + 3 * u2, h11 = u3 - u2;
    return TrajectoryPoint{
        h00 * path[seg].x + h10 * h * mx[seg] + h01 * path[seg + 1].x +
            h11 * h * mx[seg + 1],
        h00 * path[seg].y + h10 * h * my[seg] + h01 * path[seg + 1].y +
            h11 * h * my[seg + 1],
        base::Microseconds(std::llround(ms * 1000.0))};
  };

  SplitMix64 rng(seed);
  std::vector<TrajectoryPoint> out;
  out.push_back(path.front());
  const double end = t.back();
  size_t seg = 0;
  double prev = t.front();
  double prev_j = 0.0;
  for (int k = 1;; ++k) {
    double nominal = t.front() + k * period;
    if (end - nominal < period / 2) {
      break;  // too close to the end: the end itself takes its place
    }
    double j = rng.NextUniform(-jitter, jitter);
    if (hz == 125 && k > 1 && rng.NextUniform(0.0, 1.0) < kWholeShare) {
      j = prev_j;  // a gap of exactly one period
    }
    prev_j = j;
    double ms = nominal + j;
    ms = std::max(ms, prev + period / 4);  // strictly increasing
    prev = ms;
    while (seg + 2 < n && ms >= t[seg + 1]) {
      ++seg;
    }
    out.push_back(at(seg, ms));
  }
  out.push_back(path.back());
  return out;
}

WheelNotches QuantizeWheel(double delta_x, double delta_y) {
  if (!std::isfinite(delta_x) || !std::isfinite(delta_y)) {
    return {0, 0};
  }
  auto axis = [](double d) {
    if (d == 0) {
      return 0;
    }
    long n = std::max(1L, std::lround(std::min(std::abs(d) / 100.0,
                                               double{kMaxWheelNotches})));
    return static_cast<int>(d > 0 ? n : -n);
  };
  return {axis(delta_x), axis(delta_y)};
}

double SnapToDeviceGrid(double v,
                        float dsf,
                        double origin,
                        double extent) {
  if (!std::isfinite(v) || !std::isfinite(dsf) || dsf <= 0.0f ||
      !std::isfinite(origin)) {
    return v;
  }
  double snapped = std::round((v + origin) * dsf) / dsf - origin;
  if (std::isfinite(extent) && extent > 0 && v >= 0 && v < extent) {
    if (snapped < 0) {
      snapped += 1.0 / dsf;
    } else if (snapped >= extent) {
      snapped -= 1.0 / dsf;
    }
  }
  return snapped;
}

bool IsRepeatedPosition(gfx::PointF last, gfx::PointF p, gfx::SizeF size) {
  return p == last && PointInView(p, size);
}

bool PointInView(gfx::PointF p, gfx::SizeF size) {
  return gfx::RectF(size).Contains(p);
}

std::optional<base::TimeDelta> PacerSleepBefore(base::TimeDelta remaining,
                                                base::TimeDelta lead) {
  if (remaining <= lead) {
    return std::nullopt;
  }
  return remaining - lead;
}

}  // namespace camoucfg

// Copyright 2026 The Camoucrome Authors. Derived from cursory 2.1.0 (Vinyzu),
// LGPL-3.0-or-later; see NOTICE. A C++ port: the numpy generator is replaced
// by SplitMix64, so outputs match upstream in distribution, not bit for bit.

#ifdef UNSAFE_BUFFERS_BUILD
// The generated table is indexed as raw extern arrays (kRecordings, kX, kY, kT)
// within bounds the pinned table test checks; spans would need a copy of 113k points.
#pragma allow_unsafe_buffers
#endif

#include "components/camoucfg_lgpl/cursory.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <utility>
#include <vector>

#include "base/no_destructor.h"
#include "components/camoucfg_lgpl/cursory_data.h"

namespace cursory {
namespace {

class Rng {
 public:
  explicit Rng(uint64_t seed) : s_(seed) {}
  uint64_t Next() {
    uint64_t z = (s_ += 0x9E3779B97F4A7C15ull);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    return z ^ (z >> 31);
  }
  double Uniform01() { return (Next() >> 11) * (1.0 / 9007199254740992.0); }
  double Uniform(double lo, double hi) { return lo + (hi - lo) * Uniform01(); }
  double Normal(double mean, double sd) {  // Box-Muller
    double u1 = std::max(Uniform01(), 1e-12), u2 = Uniform01();
    return mean + sd * std::sqrt(-2.0 * std::log(u1)) * std::cos(6.283185307179586 * u2);
  }
  size_t Choice(const std::vector<double>& p) {  // p sums to 1
    double r = Uniform01(), acc = 0;
    for (size_t i = 0; i < p.size(); ++i) { acc += p[i]; if (r < acc) return i; }
    return p.size() - 1;
  }
 private:
  uint64_t s_;
};

struct Pt { double x, y; };

double Displacement(const data::Recording& r) {
  const size_t a = r.first_point, b = a + r.point_count - 1;
  return std::hypot(static_cast<double>(data::kX[b]) - data::kX[a], static_cast<double>(data::kY[b]) - data::kY[a]);
}

// Sorted efficiencies (displacement / path length) of every recording, for the
// rank-based weighting in SelectRecording. Built once.
const std::vector<double>& SortedEfficiencies() {
  static const base::NoDestructor<std::vector<double>> v([] {
    std::vector<double> e;
    for (size_t i = 0; i < data::kRecordingCount; ++i) {
      const auto& r = data::kRecordings[i];
      e.push_back(r.length > 0 ? Displacement(r) / r.length : 1.0);
    }
    std::sort(e.begin(), e.end());
    return e;
  }());
  return *v;
}

// Upstream find_nearest_trajectory: the `top_n` recordings with the lowest
// 0.8 * (1 - cos(direction)) + 0.2 * |len - len_tar| / max(len_tar, 1).
std::vector<size_t> Nearest(double dx, double dy, size_t top_n) {
  const double len = std::hypot(dx, dy);
  std::vector<std::pair<double, size_t>> score;
  score.reserve(data::kRecordingCount);
  for (size_t i = 0; i < data::kRecordingCount; ++i) {
    const auto& r = data::kRecordings[i];
    const size_t a = r.first_point, b = a + r.point_count - 1;
    const double rdx = static_cast<double>(data::kX[b]) - data::kX[a], rdy = static_cast<double>(data::kY[b]) - data::kY[a];
    const double disp = std::hypot(rdx, rdy);
    double s;
    if (len == 0) {
      s = r.length;  // zero-length target: shortest recordings
    } else {
      const double cos = disp != 0 ? (rdx / disp) * (dx / len) + (rdy / disp) * (dy / len) : 0.0;
      s = 0.8 * (1 - cos) + 0.2 * std::abs(disp - len) / std::max(len, 1.0);
    }
    score.emplace_back(s, i);
  }
  top_n = std::min(top_n, score.size());
  std::partial_sort(score.begin(), score.begin() + top_n, score.end());
  std::vector<size_t> out;
  for (size_t i = 0; i < top_n; ++i) out.push_back(score[i].second);
  return out;
}

// Upstream find_closest_trajectory (num_nearest=5, 20 perturbed re-queries).
size_t SelectRecording(double dx, double dy, double directness, Rng& rng) {
  const double len = std::hypot(dx, dy);
  std::vector<size_t> top = Nearest(dx, dy, 5);
  for (int k = 0; k < 20; ++k) {
    const double px = dx + rng.Uniform(-len * 0.1, len * 0.1);
    const double py = dy + rng.Uniform(-len * 0.1, len * 0.1);
    for (size_t i : Nearest(px, py, 5)) top.push_back(i);
  }
  const auto& sorted = SortedEfficiencies();
  const double preferred = 0.2 + 0.75 * directness;
  std::vector<double> w;
  double sum = 0;
  for (size_t i : top) {
    const auto& r = data::kRecordings[i];
    const double eff = r.length > 0 ? Displacement(r) / r.length : 1.0;
    const double rank = double(std::upper_bound(sorted.begin(), sorted.end(), eff) - sorted.begin()) / sorted.size();
    const double core = std::exp(-0.5 * std::pow((rank - preferred) / 0.2, 2));
    const double c = 2 * rank - 1;
    const double tail = 0.05 * (1 + 0.1 * std::pow(std::abs(c), 3));
    w.push_back(core + tail);
    sum += core + tail;
  }
  for (double& v : w) v /= sum;
  return top[rng.Choice(w)];
}

// (4 p (1-p))^2 fade: zero value and slope at both ends (upstream _endpoint_weights).
std::vector<double> EndpointWeights(const std::vector<Pt>& p) {
  std::vector<double> prog(p.size(), 0.0);
  for (size_t i = 1; i < p.size(); ++i)
    prog[i] = prog[i - 1] + std::hypot(p[i].x - p[i - 1].x, p[i].y - p[i - 1].y);
  std::vector<double> w(p.size(), 0.0);
  if (prog.back() == 0) return w;
  for (size_t i = 0; i < p.size(); ++i) {
    const double t = prog[i] / prog.back();
    w[i] = std::pow(4 * t * (1 - t), 2);
  }
  return w;
}

// Upstream morph_trajectory: scale, rotate, translate onto start/end; exact endpoints.
std::vector<Pt> Morph(const std::vector<Pt>& in, Pt s, Pt e) {
  const Pt a = in.front(), b = in.back();
  const double odx = b.x - a.x, ody = b.y - a.y, olen = std::hypot(odx, ody);
  const double tdx = e.x - s.x, tdy = e.y - s.y, tlen = std::hypot(tdx, tdy);
  const double scale = olen != 0 ? tlen / olen : 1.0;
  const double rot = std::atan2(tdy, tdx) - std::atan2(ody, odx);
  const double c = std::cos(rot), sn = std::sin(rot);
  std::vector<Pt> out;
  for (const Pt& p : in) {
    const double x = (p.x - a.x) * scale, y = (p.y - a.y) * scale;
    out.push_back({x * c - y * sn + s.x, x * sn + y * c + s.y});
  }
  out.front() = s;
  out.back() = e;
  return out;
}

// Upstream jitter_trajectory: AR(1) lateral drift (rho .75) along the normal,
// scale 0.01 * min(1, len/400), faded at the ends.
std::vector<Pt> Jitter(const std::vector<Pt>& in, double length, Rng& rng) {
  const size_t n = in.size();
  if (n < 2) return in;
  std::vector<double> prev(n, 0.0), next(n, 0.0);
  for (size_t i = 1; i < n; ++i) {
    const double d = std::hypot(in[i].x - in[i - 1].x, in[i].y - in[i - 1].y);
    prev[i] = d; next[i - 1] = d;
  }
  const std::vector<double> ew = EndpointWeights(in);
  const double length_scale = std::min(1.0, length / 400);
  std::vector<double> lat(n);
  const double rho = 0.75, inno = std::sqrt(1 - rho * rho);
  lat[0] = rng.Normal(0, 1);
  for (size_t i = 1; i < n; ++i) lat[i] = rho * lat[i - 1] + inno * rng.Normal(0, 1);
  std::vector<Pt> out = in;
  for (size_t i = 0; i < n; ++i) {
    // Tangent: central difference inside, one-sided at the ends.
    const Pt lo = in[i == 0 ? 0 : i - 1], hi = in[i + 1 < n ? i + 1 : n - 1];
    const double tx = hi.x - lo.x, ty = hi.y - lo.y;
    const double tl = std::hypot(tx, ty);
    if (tl <= 2.220446049250313e-16) continue;
    const double avg = (prev[i] + next[i]) / 2;
    const double scale = 0.01 * (avg / std::max(avg, 1.0)) * length_scale * ew[i];
    out[i].x += (-ty / tl) * lat[i] * scale;
    out[i].y += (tx / tl) * lat[i] * scale;
  }
  return out;
}

// Gaussian-biased random point inside the start/end bounding box (upstream generate_middle_biased_point).
Pt MiddleBiased(Pt s, Pt e, Rng& rng) {
  const double minx = std::min(s.x, e.x), maxx = std::max(s.x, e.x);
  const double miny = std::min(s.y, e.y), maxy = std::max(s.y, e.y);
  const double bias = 2.0;
  const double x = (minx + maxx) / 2 + rng.Normal(0, (maxx - minx) / (2 * bias));
  const double y = (miny + maxy) / 2 + rng.Normal(0, (maxy - miny) / (2 * bias));
  return {std::clamp(x, minx, maxx), std::clamp(y, miny, maxy)};
}

// Upstream knot_trajectory (5 knots, strength .15, sqrt-compressed, faded ends).
std::vector<Pt> Knot(const std::vector<Pt>& in, Pt s, Pt e, Rng& rng) {
  std::vector<Pt> off(in.size(), {0, 0});
  for (int k = 0; k < 5; ++k) {
    const Pt knot = MiddleBiased(s, e, rng);
    double maxd = 0;
    std::vector<double> d(in.size());
    for (size_t i = 0; i < in.size(); ++i) { d[i] = std::hypot(knot.x - in[i].x, knot.y - in[i].y); maxd = std::max(maxd, d[i]); }
    if (maxd < 1e-6) continue;
    for (size_t i = 0; i < in.size(); ++i) {
      const double f = (1.0 - d[i] / maxd) * 0.15;
      off[i].x += (knot.x - in[i].x) * f;
      off[i].y += (knot.y - in[i].y) * f;
    }
  }
  const std::vector<double> ew = EndpointWeights(in);
  std::vector<Pt> out = in;
  for (size_t i = 0; i < in.size(); ++i) {
    out[i].x += std::copysign(std::sqrt(std::abs(off[i].x)), off[i].x) * ew[i];
    out[i].y += std::copysign(std::sqrt(std::abs(off[i].y)), off[i].y) * ew[i];
  }
  return out;
}


// Caps min_ms/max_ms so a hostile value cannot ask for billions of samples.
constexpr int kMaxDurationMs = 60000;

double Clamp(double v, double lo, double hi, double fallback) {
  return std::isfinite(v) ? std::clamp(v, lo, hi) : fallback;
}

}  // namespace

namespace internal {
size_t SelectRecordingForTesting(double dx, double dy, double directness, uint64_t seed) {
  Rng rng(seed);
  return SelectRecording(dx, dy, directness, rng);
}
}  // namespace internal

std::vector<Sample> GenerateTrajectory(double sx, double sy, double ex, double ey,
                                       uint64_t seed, const Params& params) {
  if (!std::isfinite(sx) || !std::isfinite(sy) || !std::isfinite(ex) || !std::isfinite(ey) ||
      (sx == ex && sy == ey) || data::kRecordingCount == 0)
    return {};
  const int hz = std::clamp(params.frequency_hz, 10, 240);
  const int jitter_ms = std::clamp(params.frequency_jitter_ms, 0, 5);
  const double directness = Clamp(params.directness, 0.0, 1.0, 0.65);
  int min_ms = params.min_ms, max_ms = params.max_ms;
  min_ms = std::clamp(min_ms, -kMaxDurationMs, kMaxDurationMs);
  max_ms = std::clamp(max_ms, -kMaxDurationMs, kMaxDurationMs);
  if (min_ms > max_ms) std::swap(min_ms, max_ms);
  min_ms = std::max(1, min_ms);
  max_ms = std::max(min_ms, max_ms);

  const Pt s{sx, sy}, e{ex, ey};
  const double dx = ex - sx, dy = ey - sy, len = std::hypot(dx, dy);
  if (!std::isfinite(len)) return {};
  Rng rng(seed);

  // The recording: points, and times in ms from 0.
  const auto& rec = data::kRecordings[SelectRecording(dx, dy, directness, rng)];
  const size_t n = rec.point_count;
  std::vector<Pt> pts(n);
  std::vector<double> t(n);
  for (size_t i = 0; i < n; ++i) {
    pts[i] = {static_cast<double>(data::kX[rec.first_point + i]), static_cast<double>(data::kY[rec.first_point + i])};
    t[i] = static_cast<double>(data::kT[rec.first_point + i]) - static_cast<double>(data::kT[rec.first_point]);
  }
  std::vector<double> intervals;  // the recording's own positive inter-sample gaps
  for (size_t i = 1; i < n; ++i)
    if (t[i] > t[i - 1]) intervals.push_back(t[i] - t[i - 1]);

  // Shorter moves than the recording take proportionally less time (upstream).
  if (len > 0 && len < rec.length) {
    const double f = std::sqrt(len / rec.length);
    for (double& v : t) v *= f;
    for (double& v : intervals) v *= f;
  }
  // Total duration into [min_ms, max_ms] (not upstream).
  double total_t = t.back();
  if (total_t <= 0) {  // degenerate recording: spread evenly over min_ms
    for (size_t i = 0; i < n; ++i) t[i] = min_ms * static_cast<double>(i) / static_cast<double>(n - 1);
    total_t = min_ms;
    intervals.assign(1, static_cast<double>(min_ms));
  } else if (total_t < min_ms || total_t > max_ms) {
    const double f = (total_t < min_ms ? static_cast<double>(min_ms) : static_cast<double>(max_ms)) / total_t;
    for (double& v : t) v *= f;
    for (double& v : intervals) v *= f;
    total_t *= f;
  }

  std::vector<Pt> path = Morph(pts, s, e);
  path = Jitter(path, len, rng);
  path = Knot(path, s, e, rng);

  // Sample timings (upstream _sample_timings).
  const int64_t total = std::max<int64_t>(1, std::llround(total_t));
  const size_t count = size_t(std::max<int64_t>(1, std::llround(static_cast<double>(total) * hz / 1000.0)));
  const size_t m = intervals.size();
  const size_t offset = size_t(rng.Next() % m);
  std::vector<double> gaps(count);
  double gap_sum = 0;
  for (size_t k = 0; k < count; ++k) {
    gaps[k] = intervals[(offset + size_t((static_cast<double>(k) + 0.5) * static_cast<double>(m) / static_cast<double>(count))) % m];
    gap_sum += gaps[k];
  }
  for (double& g : gaps) g *= static_cast<double>(total) / gap_sum;
  if (jitter_ms > 0) {
    constexpr double kEps = 1e-3;
    gap_sum = 0;
    for (double& g : gaps) {
      g = std::max(kEps, g + rng.Uniform(-jitter_ms, jitter_ms));
      gap_sum += g;
    }
    for (double& g : gaps) g *= static_cast<double>(total) / gap_sum;
  }
  std::vector<int64_t> times{0};
  double acc = 0;
  for (size_t k = 0; k < count; ++k) {
    acc += gaps[k];
    times.push_back(k + 1 == count ? total : std::llround(acc));
  }
  // Strictly increasing: upstream can repeat a millisecond, which would post
  // two tasks at one instant. The last time (== total) survives.
  times.erase(std::unique(times.begin(), times.end()), times.end());

  // Linear interpolation of positions over the keyframes.
  std::vector<Pt> sampled;
  size_t seg = 1;
  for (int64_t ms : times) {
    const double u = std::min(static_cast<double>(ms) * total_t / static_cast<double>(total), total_t);
    while (seg + 1 < n && t[seg] < u) ++seg;
    const double span = t[seg] - t[seg - 1];
    const double f = span > 0 ? std::clamp((u - t[seg - 1]) / span, 0.0, 1.0) : 1.0;
    sampled.push_back({path[seg - 1].x + (path[seg].x - path[seg - 1].x) * f,
                       path[seg - 1].y + (path[seg].y - path[seg - 1].y) * f});
  }
  sampled = Knot(sampled, s, e, rng);
  sampled = Jitter(sampled, len, rng);
  sampled = Morph(sampled, s, e);

  std::vector<Sample> out;
  out.reserve(times.size());
  for (size_t i = 0; i < times.size(); ++i) out.push_back({sampled[i].x, sampled[i].y, times[i]});
  return out;
}

}  // namespace cursory

// Copyright 2026 The Camoucrome Authors. Derived from cursory 2.1.0
// (Vinyzu), LGPL-3.0-or-later; see NOTICE and LICENSE.

#ifndef COMPONENTS_CAMOUCFG_LGPL_CURSORY_H_
#define COMPONENTS_CAMOUCFG_LGPL_CURSORY_H_

#include <cstddef>
#include <cstdint>
#include <vector>

namespace cursory {

struct Sample {
  double x;
  double y;
  int64_t t_ms;  // from 0
};

struct Params {
  int frequency_hz = 60;        // clamped to [10, 240]
  int frequency_jitter_ms = 1;  // clamped to [0, 5]
  double directness = 0.65;     // clamped to [0, 1]
  int min_ms = 80;              // total duration bounds; sanitized (swap, >=1, max >= min)
  int max_ms = 1200;
};

// Empty vector when start == end, either is non-finite, or the table is
// empty. Otherwise the first sample is `start` at t=0, the last is `end`;
// t_ms is strictly increasing; the total is in [min_ms, max_ms].
// Deterministic per seed.
std::vector<Sample> GenerateTrajectory(double sx,
                                       double sy,
                                       double ex,
                                       double ey,
                                       uint64_t seed,
                                       const Params& params = {});

// Test-only section: not for production callers.
namespace internal {
// Index into data::kRecordings that GenerateTrajectory would pick for the
// displacement (dx, dy) and seed.
size_t SelectRecordingForTest(double dx,
                              double dy,
                              double directness,
                              uint64_t seed);
}  // namespace internal

}  // namespace cursory

#endif  // COMPONENTS_CAMOUCFG_LGPL_CURSORY_H_

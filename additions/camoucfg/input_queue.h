// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_INPUT_QUEUE_H_
#define COMPONENTS_CAMOUCFG_INPUT_QUEUE_H_

#include <optional>

#include "base/time/time.h"

namespace camoucfg {

// The queue clock of the shared input scheduler: items run one after another,
// never overlapping. Pure arithmetic on caller-supplied times, so it is
// testable without a message loop.
class QueueClock {
 public:
  // An item whose end would fall more than this after `now` is refused.
  static constexpr base::TimeDelta kMaxBacklog = base::Seconds(10);

  // Books `duration` after everything already booked. The item starts at
  // `now` when the queue is idle, otherwise 1 ms after the previous item's
  // end. Returns the delay from `now` to that start, or nullopt if the end
  // would be more than kMaxBacklog after `now` (state is left unchanged; the
  // caller takes the stock path). A non-positive duration NEVER refuses and
  // books nothing: it returns DelayBehind(now), so an item that is not
  // scheduled itself (over the cap, not a move) still cannot overtake the
  // queue. Never negative.
  std::optional<base::TimeDelta> Reserve(base::TimeTicks now,
                                         base::TimeDelta duration);

  // The delay from `now` to where the queue currently ends: 0 when idle
  // (free_at_ <= now), otherwise the end plus the 1 ms gap, minus `now`.
  // Books nothing; the same value as Reserve(now, 0).
  base::TimeDelta DelayBehind(base::TimeTicks now) const;

 private:
  base::TimeTicks free_at_;
};

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_INPUT_QUEUE_H_

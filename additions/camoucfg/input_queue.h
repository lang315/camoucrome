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
// One 60 Hz frame: the page dispatches at most one mousemove per frame, so
// deferred stock events posted at the same instant would coalesce into one.
inline constexpr base::TimeDelta kStockSlot = base::Milliseconds(17);

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

  // For a stock event that must wait behind the queue. Returns DelayBehind(now)
  // and, only when that is > 0 (queue busy), books kStockSlot (the 1 ms gap
  // included) from that start, so consecutive deferred events start kStockSlot
  // apart instead of at one instant. Ignores kMaxBacklog: a deferred stock
  // event is never refused; the overshoot is at most kStockSlot per call.
  // Idle: returns 0 and books nothing (the caller forwards immediately).
  base::TimeDelta BookStockSlot(base::TimeTicks now);

 private:
  base::TimeTicks free_at_;
};

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_INPUT_QUEUE_H_

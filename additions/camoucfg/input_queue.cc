// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/input_queue.h"

namespace camoucfg {

std::optional<base::TimeDelta> QueueClock::Reserve(base::TimeTicks now,
                                                   base::TimeDelta duration) {
  // Strictly after the previous item's end, so e.g. a wheel's first notch
  // cannot run before the previous move's final event (posted at that end).
  base::TimeTicks start =
      free_at_ > now ? free_at_ + base::Milliseconds(1) : now;
  if (duration <= base::TimeDelta()) {
    return start - now;
  }
  base::TimeTicks end = start + duration;
  if (end - now > kMaxBacklog) {
    return std::nullopt;
  }
  free_at_ = end;
  return start - now;
}

}  // namespace camoucfg

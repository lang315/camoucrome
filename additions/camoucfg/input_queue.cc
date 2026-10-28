// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/input_queue.h"

#include <algorithm>

namespace camoucfg {

std::optional<base::TimeDelta> QueueClock::Reserve(base::TimeTicks now,
                                                   base::TimeDelta duration) {
  base::TimeTicks start = std::max(now, free_at_);
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

void QueueClock::Reset() {
  free_at_ = base::TimeTicks();
}

}  // namespace camoucfg

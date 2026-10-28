// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/input_queue.h"

#include "base/time/time.h"
#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg {
namespace {

TEST(InputQueueTest, FifoOrdering) {
  QueueClock q;
  base::TimeTicks now;
  EXPECT_EQ(q.Reserve(now, base::Milliseconds(100)), base::Milliseconds(0));
  EXPECT_EQ(q.Reserve(now, base::Milliseconds(200)), base::Milliseconds(100));
  EXPECT_EQ(q.Reserve(now, base::Milliseconds(300)), base::Milliseconds(300));
}

TEST(InputQueueTest, IdleClockStartsNow) {
  QueueClock q;
  base::TimeTicks now;
  ASSERT_TRUE(q.Reserve(now, base::Milliseconds(100)).has_value());
  EXPECT_EQ(q.Reserve(now + base::Milliseconds(500), base::Milliseconds(10)),
            base::Milliseconds(0));
}

TEST(InputQueueTest, BacklogCapRefusesWithoutChangingState) {
  QueueClock q;
  base::TimeTicks now;
  ASSERT_TRUE(q.Reserve(now, base::Seconds(9)).has_value());
  EXPECT_FALSE(q.Reserve(now, base::Seconds(2)).has_value());
  // free_at_ is still 9 s: a small item starts there.
  EXPECT_EQ(q.Reserve(now, base::Milliseconds(100)), base::Seconds(9));
}

TEST(InputQueueTest, ExactlyAtCapSucceedsOneMicrosecondMoreFails) {
  QueueClock q;
  base::TimeTicks now;
  EXPECT_TRUE(q.Reserve(now, base::Seconds(10)).has_value());
  q.Reset();
  EXPECT_FALSE(q.Reserve(now, base::Seconds(10) + base::Microseconds(1))
                   .has_value());
}

TEST(InputQueueTest, ResetClearsBooking) {
  QueueClock q;
  base::TimeTicks now;
  ASSERT_TRUE(q.Reserve(now, base::Seconds(5)).has_value());
  q.Reset();
  EXPECT_EQ(q.Reserve(now, base::Milliseconds(1)), base::Milliseconds(0));
}

TEST(InputQueueTest, NonPositiveDurationBooksNothing) {
  QueueClock q;
  base::TimeTicks now;
  ASSERT_TRUE(q.Reserve(now, base::Milliseconds(100)).has_value());
  EXPECT_EQ(q.Reserve(now, base::TimeDelta()), base::Milliseconds(100));
  EXPECT_EQ(q.Reserve(now, base::Milliseconds(-50)), base::Milliseconds(100));
  // Past free_at_ the delay is 0, never negative.
  EXPECT_EQ(q.Reserve(now + base::Seconds(1), base::Milliseconds(-1)),
            base::Milliseconds(0));
  EXPECT_EQ(q.Reserve(now, base::Milliseconds(1)), base::Milliseconds(100));
}

TEST(InputQueueTest, TenThousandMillisecondItemsFillTheCapExactly) {
  QueueClock q;
  base::TimeTicks now;
  for (int i = 0; i < 10000; ++i) {
    ASSERT_TRUE(q.Reserve(now, base::Milliseconds(1)).has_value()) << i;
  }
  EXPECT_FALSE(q.Reserve(now, base::Milliseconds(1)).has_value());
}

}  // namespace
}  // namespace camoucfg

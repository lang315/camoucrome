// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/input_queue.h"

#include "base/time/time.h"
#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg {
namespace {

TEST(InputQueueTest, FifoOrderingWithOneMillisecondGap) {
  QueueClock q;
  base::TimeTicks now;
  // Item 1: 0..100. Item 2: 101..301. Item 3: 302..602.
  EXPECT_EQ(q.Reserve(now, base::Milliseconds(100)), base::Milliseconds(0));
  EXPECT_EQ(q.Reserve(now, base::Milliseconds(200)), base::Milliseconds(101));
  EXPECT_EQ(q.Reserve(now, base::Milliseconds(300)), base::Milliseconds(302));
}

TEST(InputQueueTest, IdleClockStartsNow) {
  QueueClock q;
  base::TimeTicks now;
  ASSERT_TRUE(q.Reserve(now, base::Milliseconds(100)).has_value());
  EXPECT_EQ(q.Reserve(now + base::Milliseconds(500), base::Milliseconds(10)),
            base::Milliseconds(0));
  // Exactly at the previous end counts as idle.
  EXPECT_EQ(q.Reserve(now + base::Milliseconds(510), base::Milliseconds(10)),
            base::Milliseconds(0));
}

TEST(InputQueueTest, BacklogCapRefusesWithoutChangingState) {
  QueueClock q;
  base::TimeTicks now;
  ASSERT_TRUE(q.Reserve(now, base::Seconds(9)).has_value());
  EXPECT_FALSE(q.Reserve(now, base::Seconds(2)).has_value());
  // free_at_ is still 9 s: a small item starts 1 ms after it.
  EXPECT_EQ(q.Reserve(now, base::Milliseconds(100)),
            base::Seconds(9) + base::Milliseconds(1));
}

TEST(InputQueueTest, ExactlyAtCapSucceedsOneMicrosecondMoreFails) {
  base::TimeTicks now;
  QueueClock a;
  EXPECT_TRUE(a.Reserve(now, base::Seconds(10)).has_value());
  QueueClock b;
  EXPECT_FALSE(b.Reserve(now, base::Seconds(10) + base::Microseconds(1))
                   .has_value());
  // With a booking the 1 ms gap counts: after 5 s, the item starts at 5.001 s
  // so 4.999 s fits exactly and one microsecond more does not.
  QueueClock c;
  ASSERT_TRUE(c.Reserve(now, base::Seconds(5)).has_value());
  EXPECT_TRUE(c.Reserve(now, base::Milliseconds(4999)).has_value());
  QueueClock d;
  ASSERT_TRUE(d.Reserve(now, base::Seconds(5)).has_value());
  EXPECT_FALSE(d.Reserve(now, base::Milliseconds(4999) + base::Microseconds(1))
                   .has_value());
}

TEST(InputQueueTest, NonPositiveDurationBooksNothing) {
  QueueClock q;
  base::TimeTicks now;
  ASSERT_TRUE(q.Reserve(now, base::Milliseconds(100)).has_value());
  EXPECT_EQ(q.Reserve(now, base::TimeDelta()), base::Milliseconds(101));
  EXPECT_EQ(q.Reserve(now, base::Milliseconds(-50)), base::Milliseconds(101));
  // Past the end the delay is 0, never negative.
  EXPECT_EQ(q.Reserve(now + base::Seconds(1), base::Milliseconds(-1)),
            base::Milliseconds(0));
  EXPECT_EQ(q.Reserve(now, base::Milliseconds(1)), base::Milliseconds(101));
}

TEST(InputQueueTest, OneMillisecondItemsFillTheCapWithGaps) {
  // Item k starts at 2k ms and ends at 2k+1 ms: the last that fits in 10 s is
  // k = 4999 (ends at 9999 ms), so 5000 succeed and the 5001st (ends at 10001
  // ms) is refused.
  QueueClock q;
  base::TimeTicks now;
  for (int k = 0; k < 5000; ++k) {
    auto delay = q.Reserve(now, base::Milliseconds(1));
    ASSERT_TRUE(delay.has_value()) << k;
    EXPECT_EQ(*delay, base::Milliseconds(2 * k));
  }
  EXPECT_FALSE(q.Reserve(now, base::Milliseconds(1)).has_value());
}

TEST(InputQueueTest, DelayBehindIdleIsZero) {
  QueueClock q;
  EXPECT_EQ(q.DelayBehind(base::TimeTicks()), base::TimeDelta());
}

TEST(InputQueueTest, DelayBehindBusyAddsTheGap) {
  QueueClock q;
  base::TimeTicks now;
  ASSERT_TRUE(q.Reserve(now, base::Seconds(5)).has_value());
  // End 5000 ms + 1 ms gap - now 1000 ms.
  EXPECT_EQ(q.DelayBehind(now + base::Seconds(1)), base::Milliseconds(4001));
  // The end has passed: idle again.
  EXPECT_EQ(q.DelayBehind(now + base::Seconds(5)), base::TimeDelta());
  EXPECT_EQ(q.DelayBehind(now + base::Seconds(6)), base::TimeDelta());
}

TEST(InputQueueTest, DelayBehindAgreesWithZeroDurationReserve) {
  QueueClock q;
  base::TimeTicks now;
  ASSERT_TRUE(q.Reserve(now, base::Seconds(5)).has_value());
  for (int ms : {0, 1000, 4999, 5000, 7000}) {
    base::TimeTicks t = now + base::Milliseconds(ms);
    EXPECT_EQ(q.Reserve(t, base::TimeDelta()), q.DelayBehind(t)) << ms;
  }
}

TEST(InputQueueTest, DelayBehindDoesNotBook) {
  QueueClock q;
  base::TimeTicks now;
  ASSERT_TRUE(q.Reserve(now, base::Seconds(5)).has_value());
  for (int i = 0; i < 3; ++i) {
    q.DelayBehind(now);
    q.Reserve(now, base::TimeDelta());
  }
  // Still ends at 5 s: the next item starts at 5001 ms.
  EXPECT_EQ(q.Reserve(now, base::Milliseconds(1)), base::Milliseconds(5001));
}

TEST(InputQueueTest, RefusalBooksNothingSoDelayBehindKeepsOldEnd) {
  QueueClock q;
  base::TimeTicks now;
  ASSERT_TRUE(q.Reserve(now, base::Seconds(9)).has_value());
  ASSERT_FALSE(q.Reserve(now, base::Seconds(5)).has_value());
  EXPECT_EQ(q.DelayBehind(now), base::Seconds(9) + base::Milliseconds(1));
}

TEST(InputQueueTest, DelayBehindAFullQueueIsBoundedByTheBacklog) {
  QueueClock q;
  base::TimeTicks now;
  ASSERT_TRUE(q.Reserve(now, base::Seconds(10)).has_value());
  EXPECT_EQ(q.DelayBehind(now), base::Seconds(10) + base::Milliseconds(1));
  EXPECT_LE(q.DelayBehind(now + base::Seconds(3)),
            QueueClock::kMaxBacklog + base::Milliseconds(1) - base::Seconds(3));
  // A zero-length item never refuses, even on a full queue.
  EXPECT_TRUE(q.Reserve(now, base::TimeDelta()).has_value());
}

TEST(InputQueueTest, BookStockSlotSpacesDeferredEventsByOneFrame) {
  QueueClock q;
  base::TimeTicks now;
  ASSERT_TRUE(q.Reserve(now, base::Seconds(5)).has_value());
  base::TimeTicks later = now + base::Seconds(1);
  // First starts at end 5000 + 1 ms gap = 5001 ms, i.e. 4001 ms from `later`;
  // each next starts one slot (17 ms, gap included) after the previous.
  EXPECT_EQ(q.BookStockSlot(later), base::Milliseconds(4001));
  EXPECT_EQ(q.BookStockSlot(later), base::Milliseconds(4018));
  EXPECT_EQ(q.BookStockSlot(later), base::Milliseconds(4035));
  EXPECT_EQ(kStockSlot, base::Milliseconds(17));
}

TEST(InputQueueTest, BookStockSlotWhenIdleBooksNothing) {
  QueueClock q;
  base::TimeTicks now;
  EXPECT_EQ(q.BookStockSlot(now), base::TimeDelta());
  EXPECT_EQ(q.BookStockSlot(now), base::TimeDelta());
  EXPECT_EQ(q.Reserve(now, base::Milliseconds(100)), base::TimeDelta());
}

TEST(InputQueueTest, BookStockSlotIgnoresTheBacklogCap) {
  QueueClock q;
  base::TimeTicks now;
  ASSERT_TRUE(q.Reserve(now, base::Seconds(10)).has_value());
  EXPECT_EQ(q.BookStockSlot(now), base::Milliseconds(10001));
  EXPECT_EQ(q.BookStockSlot(now), base::Milliseconds(10018));
  EXPECT_EQ(q.BookStockSlot(now), base::Milliseconds(10035));
  // Over the cap now: a positive item is refused, a stock slot still is not.
  EXPECT_FALSE(q.Reserve(now, base::Milliseconds(1)).has_value());
  EXPECT_EQ(q.BookStockSlot(now), base::Milliseconds(10052));
}

}  // namespace
}  // namespace camoucfg

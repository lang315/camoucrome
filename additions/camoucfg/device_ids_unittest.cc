// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/device_ids.h"

#include <cstdint>
#include <set>
#include <string>

#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg {
namespace {

TEST(DeviceIdsTest, SeedZeroIsNoOp) {
  // rule 5: no mediaDevices:seed -> real value unchanged.
  EXPECT_EQ(SyntheticDeviceId(0, "audioinput", "real-mic-id", "https://a.test"),
            "real-mic-id");
}

TEST(DeviceIdsTest, EmptyRealIdStaysEmpty) {
  // The pre-grant (label-less) path never calls this with a real id at all;
  // if it did, hashing "" would still need to be a no-op.
  EXPECT_EQ(SyntheticDeviceId(1234, "audioinput", "", "https://a.test"), "");
}

TEST(DeviceIdsTest, DefaultSentinelIsPreserved) {
  // "default" is a real Chrome audio-default sentinel, not a device id --
  // hashing it would turn a stable, meaningful value into a fingerprint tell.
  EXPECT_EQ(SyntheticDeviceId(1234, "audiooutput", "default", "https://a.test"),
            "default");
}

TEST(DeviceIdsTest, NonDefaultIsSixtyFourLowercaseHex) {
  const std::string id =
      SyntheticDeviceId(1234, "videoinput", "real-cam-id", "https://a.test");
  ASSERT_EQ(id.size(), 64u);
  for (char c : id) {
    EXPECT_TRUE((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))
        << "non-lowercase-hex character: " << c;
  }
}

TEST(DeviceIdsTest, Deterministic) {
  EXPECT_EQ(SyntheticDeviceId(1234, "videoinput", "real-cam-id", "https://a.test"),
            SyntheticDeviceId(1234, "videoinput", "real-cam-id", "https://a.test"));
}

TEST(DeviceIdsTest, DifferentOriginsDiffer) {
  // Per-origin salt: a stable-across-origin id would itself be a cross-origin
  // tracking id, the opposite of the goal.
  EXPECT_NE(SyntheticDeviceId(1234, "videoinput", "real-cam-id", "https://a.test"),
            SyntheticDeviceId(1234, "videoinput", "real-cam-id", "https://b.test"));
}

TEST(DeviceIdsTest, DifferentSeedsDiffer) {
  EXPECT_NE(SyntheticDeviceId(1234, "videoinput", "real-cam-id", "https://a.test"),
            SyntheticDeviceId(5678, "videoinput", "real-cam-id", "https://a.test"));
}

TEST(DeviceIdsTest, DifferentRealIdsDiffer) {
  EXPECT_NE(SyntheticDeviceId(1234, "videoinput", "real-cam-id-1", "https://a.test"),
            SyntheticDeviceId(1234, "videoinput", "real-cam-id-2", "https://a.test"));
}

TEST(DeviceIdsTest, DifferentKindsDiffer) {
  EXPECT_NE(SyntheticDeviceId(1234, "videoinput", "real-id", "https://a.test"),
            SyntheticDeviceId(1234, "audioinput", "real-id", "https://a.test"));
}

TEST(DeviceIdsTest, InterWordDeltaIsNotAFixedConstant) {
  // The 64-hex output is 4 rounds of one hash concatenated. If a round
  // counter were folded in AFTER a shared prefix (seed/kind/real_id/origin),
  // the two halves would be related by one exact, precomputable delta mod
  // 2^64 for every id -- a perfect single-sample "is this camoucrome" oracle,
  // and the opposite of the "cannot distinguish from HMAC-SHA256 hex"
  // property this helper exists to provide. Vary real_id and check the
  // word0/word1 delta takes more than a couple of values.
  std::set<uint64_t> deltas;
  for (int i = 0; i < 8; ++i) {
    const std::string real_id = "dev-" + std::to_string(i);
    const std::string id =
        SyntheticDeviceId(1234, "videoinput", real_id, "https://a.test");
    ASSERT_EQ(id.size(), 64u);
    const uint64_t w0 = std::stoull(id.substr(0, 16), nullptr, 16);
    const uint64_t w1 = std::stoull(id.substr(16, 16), nullptr, 16);
    deltas.insert(w1 - w0);  // uint64_t subtraction wraps mod 2^64
  }
  EXPECT_GT(deltas.size(), 2u)
      << "word1-word0 collapses to too few distinct values";
}

}  // namespace
}  // namespace camoucfg

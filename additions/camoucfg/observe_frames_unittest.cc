// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/observe_frames.h"

#include <algorithm>
#include <string>
#include <utility>
#include <vector>

#include "base/values.h"
#include "components/camoucfg/observe_golden_test_util.h"
#include "components/camoucfg/observe_leaf.h"
#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg::observe {

TEST(ObserveFramesTest, GoldenWsParity) {
  int n = 0;
  for (const base::Value& c : *ObserveGolden().FindList("ws")) {
    const base::DictValue& d = c.GetDict();
    SCOPED_TRACE(*d.FindString("name"));
    auto [units, partial] = FrameUnits(*d.FindInt("opcode"), FromB64(*d.FindString("b64")));
    EXPECT_EQ(partial, static_cast<size_t>(*d.FindInt("partial")));
    const base::ListValue& want = *d.FindList("units");
    ASSERT_EQ(units.size(), want.size());
    for (size_t i = 0; i < units.size(); ++i) {
      EXPECT_EQ(units[i].topic, want[i].GetList()[0].GetString());
      std::vector<std::pair<std::string, std::string>> got;
      for (const auto& [path, leaf] : units[i].fields) got.emplace_back(path, ValueClass(leaf));
      std::sort(got.begin(), got.end());
      EXPECT_EQ(got, PathClassPairs(want[i].GetList()[1].GetList()));
    }
    ++n;
  }
  EXPECT_GE(n, 15);
}

TEST(ObserveFramesTest, MqttFourByteLengthLimit) {
  // Python's _varint allows 4 length bytes. PINGREQ has no minimum body, so
  // without the limit the 5-byte form would parse as a packet.
  auto four = MqttParse(std::string("\xc0\x80\x80\x80\x00", 5));
  EXPECT_EQ(four.first.size(), 1u);
  EXPECT_EQ(four.second, 0u);
  auto five = MqttParse(std::string("\xc0\x80\x80\x80\x80\x00", 6));
  EXPECT_TRUE(five.first.empty());
  EXPECT_EQ(five.second, 6u);
  EXPECT_TRUE(MqttParse(std::string("\x30\xff\xff\xff\xff\x01", 6)).first.empty());
}

}  // namespace camoucfg::observe

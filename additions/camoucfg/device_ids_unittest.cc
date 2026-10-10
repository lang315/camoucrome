// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/device_ids.h"

#include <string>

#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg {
namespace {

TEST(DeviceIdsTest, MaskedLabelKeepsSentinelPrefix) {
  EXPECT_EQ(MaskedDeviceLabel("default", "Default - Realtek Mic", "Mic"),
            "Default - Mic");
  EXPECT_EQ(MaskedDeviceLabel("communications",
                              "Communications - Realtek Mic", "Mic"),
            "Communications - Mic");
}

TEST(DeviceIdsTest, MaskedLabelPlainDeviceGetsConfigured) {
  EXPECT_EQ(MaskedDeviceLabel("0123abcd", "Realtek - Mic Array", "Mic"), "Mic");
  EXPECT_EQ(MaskedDeviceLabel("default", "Default", "Mic"), "Mic");
}

}  // namespace
}  // namespace camoucfg

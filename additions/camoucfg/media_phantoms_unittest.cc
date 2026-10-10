// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/media_phantoms.h"

#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg {
namespace {

TEST(MediaPhantomsTest, VideoIsOneDeviceOnEveryPlatform) {
  for (bool windows : {false, true}) {
    auto v = PhantomDevicesFor("videoinput", "Cam", windows, "Default", "Communications");
    ASSERT_EQ(v.size(), 1u);
    EXPECT_EQ(v[0].device_id, "camou-phantom-videoinput");
    EXPECT_EQ(v[0].group_id, "camou-phantom-group-videoinput");
    EXPECT_EQ(v[0].label, "Cam");
  }
}

TEST(MediaPhantomsTest, AudioOnWindowsStartsWithBothSentinels) {
  for (const char* kind : {"audioinput", "audiooutput"}) {
    auto v = PhantomDevicesFor(kind, "Mic", true, "Default", "Communications");
    ASSERT_EQ(v.size(), 3u);
    EXPECT_EQ(v[0].device_id, "default");
    EXPECT_EQ(v[0].label, "Default - Mic");
    EXPECT_EQ(v[1].device_id, "communications");
    EXPECT_EQ(v[1].label, "Communications - Mic");
    EXPECT_EQ(v[2].device_id, std::string("camou-phantom-") + kind);
    EXPECT_EQ(v[2].label, "Mic");
    for (const auto& d : v) {
      EXPECT_EQ(d.group_id, std::string("camou-phantom-group-") + kind);
    }
  }
}

TEST(MediaPhantomsTest, AudioOffWindowsHasNoSentinels) {
  auto v = PhantomDevicesFor("audioinput", "Mic", false, "Default", "");
  ASSERT_EQ(v.size(), 1u);
  EXPECT_EQ(v[0].device_id, "camou-phantom-audioinput");
}

TEST(MediaPhantomsTest, LocalizedSentinelPrefix) {
  auto v = PhantomDevicesFor("audioinput", "Mic", true, "Standard", "Kommunikation");
  EXPECT_EQ(v[0].label, "Standard - Mic");
  EXPECT_EQ(v[1].label, "Kommunikation - Mic");
}

TEST(MediaPhantomsTest, IsPhantomDeviceId) {
  EXPECT_TRUE(IsPhantomDeviceId("camou-phantom-audioinput"));
  EXPECT_FALSE(IsPhantomDeviceId("camou-phantom-group-audioinput"));
  EXPECT_FALSE(IsPhantomDeviceId("default"));
  EXPECT_FALSE(IsPhantomDeviceId(""));
}

}  // namespace
}  // namespace camoucfg

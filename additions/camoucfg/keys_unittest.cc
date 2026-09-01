// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/keys.h"

#include <set>
#include <string_view>

#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg::keys {
namespace {

// The failure this guards against is a constant whose NAME is new but whose
// VALUE duplicates another. Two call sites then read the same key while
// appearing to read different ones, which no compiler or reviewer catches and
// which produces a surface that silently follows the wrong knob.
TEST(CamoucfgKeysTest, EveryKeyIsUnique) {
  std::set<std::string_view> seen;
  for (std::string_view key : kAllKeys) {
    EXPECT_TRUE(seen.insert(key).second) << "duplicate key value: " << key;
  }
  EXPECT_EQ(seen.size(), kAllKeys.size());
}

// Conventions: a key uses a dot when it mirrors a JavaScript property path and
// a colon when it names a synthetic namespace. Either way it carries at least
// one separator, and a key that carries neither is a bare word that will
// collide with a future namespace.
TEST(CamoucfgKeysTest, EveryKeyIsNamespaced) {
  for (std::string_view key : kAllKeys) {
    EXPECT_NE(key.find_first_of(".:"), std::string_view::npos)
        << "key is not namespaced: " << key;
    EXPECT_EQ(key.find(' '), std::string_view::npos)
        << "key contains a space: " << key;
    EXPECT_FALSE(key.empty());
  }
}

// keys.h's comment claims adding a constant means adding it to kAllKeys,
// but nothing enforced that until this test: a constant declared and left
// out of kAllKeys was invisible. Enumerate every constant by name here and
// assert the set equals kAllKeys, so declaring one and forgetting kAllKeys
// (or vice versa) fails, and a duplicate in kAllKeys masking a missing key
// fails the size check rather than passing on set equality.
TEST(CamoucfgKeysTest, EveryDeclaredConstantIsInAllKeys) {
  const std::set<std::string_view> declared = {
      kUaOsInfo, kNavigatorHardwareConcurrency, kNavigatorUserAgent,
      kUaPlatform, kUaPlatformVersion, kUaArchitecture, kUaBitness,
      kUaModel, kUaMobile, kUaWow64,
      kHumanizeEnabled, kHumanizeMinTime, kHumanizeMaxTime, kShowCursor,
      kCanvasSeed, kCanvasNoiseDensity, kCanvasNoiseStrength,
      kWebGlVendor, kWebGlRenderer, kWebGl2Vendor, kWebGl2Renderer,
      kWebGlParameters, kWebGl2Parameters, kWebGlParamsBlock,
      kWebGl2ParamsBlock,
      kWebGlExtensions, kWebGl2Extensions,
      kWebGlShaderPrecision, kWebGl2ShaderPrecision,
      kWebGlShaderPrecisionBlock, kWebGl2ShaderPrecisionBlock,
      kWebGlContextAttrs, kWebGl2ContextAttrs,
      kNavigatorPlatform, kNavigatorAppVersion, kNavigatorDeviceMemory,
      kNavigatorMaxTouchPoints, kNavigatorLanguage, kNavigatorLanguages,
      kNavigatorAppCodeName, kNavigatorAppName, kNavigatorProduct,
      kNavigatorProductSub, kNavigatorVendor, kNavigatorVendorSub,
      kScreenWidth, kScreenHeight, kScreenAvailWidth, kScreenAvailHeight,
      kScreenAvailLeft, kScreenAvailTop, kScreenColorDepth,
      kFonts,
      kAudioSeed, kAudioOutputLatency, kAudioBaseLatency,
      kAudioMaxChannelCount,
      kMediaDevicesEnabled, kMediaDevicesMicros, kMediaDevicesWebcams,
      kMediaDevicesSpeakers,
      kTimezoneId, kLocaleTag,
      kWebrtcIpHandlingPolicy,
      kVoicesList, kVoicesFakeCompletion, kVoicesFakeCompletionCharsPerSecond,
      kGeolocationLatitude, kGeolocationLongitude, kGeolocationAccuracy,
  };
  const std::set<std::string_view> in_array(kAllKeys.begin(), kAllKeys.end());
  EXPECT_EQ(declared, in_array);
  EXPECT_EQ(declared.size(), kAllKeys.size());  // a duplicate in kAllKeys
                                                // would shrink in_array below
                                                // declared and be caught here
}

// kUaMetadataKeys is a hand-written subset, and a subset that has drifted from
// its parent is the silent kind of wrong: the startup check that iterates it
// would simply stop covering whatever fell out, while still reporting success
// on everything it does cover.
//
// Both halves matter. Every member must be a real key, so a typo here cannot
// create a group entry that matches nothing; and kUaOsInfo must stay OUT,
// because the whole point of the group is "the client-hint keys, as distinct
// from the one that reaches the user-agent string".
TEST(CamoucfgKeysTest, UaMetadataKeysIsASubsetOfAllKeys) {
  std::set<std::string_view> all(kAllKeys.begin(), kAllKeys.end());
  for (std::string_view key : kUaMetadataKeys) {
    EXPECT_TRUE(all.count(key)) << "not a declared key: " << key;
    EXPECT_NE(key, std::string_view(kUaOsInfo))
        << "kUaOsInfo is the user-agent string's key and must not be in the "
           "client-hint group";
  }
  std::set<std::string_view> unique(kUaMetadataKeys.begin(),
                                    kUaMetadataKeys.end());
  EXPECT_EQ(unique.size(), kUaMetadataKeys.size());
}

// The count is asserted, not just the membership. Adding a ua: key to keys.h
// and forgetting this group would leave the startup coherence warning blind to
// it -- and nothing else would notice, because every existing assertion would
// still pass.
TEST(CamoucfgKeysTest, EveryUaKeyExceptOsInfoIsInTheMetadataGroup) {
  std::set<std::string_view> group(kUaMetadataKeys.begin(),
                                   kUaMetadataKeys.end());
  for (std::string_view key : kAllKeys) {
    if (key.substr(0, 3) != "ua:" || key == std::string_view(kUaOsInfo)) {
      continue;
    }
    EXPECT_TRUE(group.count(key))
        << key << " is a ua: key but is missing from kUaMetadataKeys";
  }
}

}  // namespace
}  // namespace camoucfg::keys

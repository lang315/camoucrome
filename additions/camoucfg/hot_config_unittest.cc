// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/hot_config.h"

#include <iostream>

#include "base/json/json_reader.h"
#include "base/time/time.h"
#include "base/values.h"
#include "components/camoucfg/keys.h"
#include "components/camoucfg/mask_config_internal.h"
#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg {
namespace {

base::DictValue Parse(const char* json) {
  std::optional<base::DictValue> d =
      base::JSONReader::ReadDict(json, base::JSON_PARSE_RFC);
  EXPECT_TRUE(d.has_value());
  return d ? std::move(*d) : base::DictValue();
}

// The cached value equals what the per-read getters return for every key.
TEST(CamoucfgHotConfigTest, PresentKeysEqualTheGetters) {
  base::DictValue cfg = Parse(R"({
    "navigator.platform": "Win32", "navigator.language": "fr-FR",
    "screen.width": 1920, "screen.height": 1080, "screen.colorDepth": 24,
    "screen.availLeft": 0, "screen.availTop": 0,
    "screen.availWidth": 1920, "screen.availHeight": 1040,
    "navigator.hardwareConcurrency": 8, "navigator.deviceMemory": 8,
    "window.outerWidth": 1920, "window.outerHeight": 1040,
    "window.screenX": -8, "window.screenY": 0,
    "navigator.appCodeName": "Mozilla", "navigator.appName": "Netscape",
    "navigator.appVersion": "5.0 Windows", "navigator.product": "Gecko",
    "navigator.productSub": "20030107", "navigator.vendor": "Google Inc.",
    "navigator.vendorSub": "x"})");
  HotConfig hot = internal::HotFrom(cfg, "Linux x86_64");
  EXPECT_EQ(hot.platform, internal::GetStringFrom(cfg, keys::kNavigatorPlatform));
  EXPECT_EQ(hot.language, internal::GetStringFrom(cfg, keys::kNavigatorLanguage));
  EXPECT_EQ(hot.navigator_hardware_concurrency,
            internal::GetUint32From(cfg, keys::kNavigatorHardwareConcurrency));
  EXPECT_EQ(hot.navigator_device_memory,
            internal::GetDoubleFrom(cfg, keys::kNavigatorDeviceMemory));
  EXPECT_EQ(hot.navigator_app_code_name,
            internal::GetStringFrom(cfg, keys::kNavigatorAppCodeName));
  EXPECT_EQ(hot.navigator_app_name,
            internal::GetStringFrom(cfg, keys::kNavigatorAppName));
  EXPECT_EQ(hot.navigator_app_version,
            internal::GetStringFrom(cfg, keys::kNavigatorAppVersion));
  EXPECT_EQ(hot.navigator_product,
            internal::GetStringFrom(cfg, keys::kNavigatorProduct));
  EXPECT_EQ(hot.navigator_product_sub,
            internal::GetStringFrom(cfg, keys::kNavigatorProductSub));
  EXPECT_EQ(hot.navigator_vendor,
            internal::GetStringFrom(cfg, keys::kNavigatorVendor));
  EXPECT_EQ(hot.navigator_vendor_sub,
            internal::GetStringFrom(cfg, keys::kNavigatorVendorSub));
  EXPECT_EQ(hot.window_outer_width, internal::GetInt32From(cfg, keys::kWindowOuterWidth));
  EXPECT_EQ(hot.window_outer_height, internal::GetInt32From(cfg, keys::kWindowOuterHeight));
  EXPECT_EQ(hot.window_screen_x, internal::GetInt32From(cfg, keys::kWindowScreenX));
  EXPECT_EQ(hot.window_screen_y, internal::GetInt32From(cfg, keys::kWindowScreenY));
  EXPECT_EQ(hot.screen_width, internal::GetUint32From(cfg, keys::kScreenWidth));
  EXPECT_EQ(hot.screen_height, internal::GetUint32From(cfg, keys::kScreenHeight));
  EXPECT_EQ(hot.screen_color_depth,
            internal::GetUint32From(cfg, keys::kScreenColorDepth));
  EXPECT_EQ(hot.screen_avail_left,
            internal::GetUint32From(cfg, keys::kScreenAvailLeft));
  EXPECT_EQ(hot.screen_avail_top,
            internal::GetUint32From(cfg, keys::kScreenAvailTop));
  EXPECT_EQ(hot.screen_avail_width,
            internal::GetUint32From(cfg, keys::kScreenAvailWidth));
  EXPECT_EQ(hot.screen_avail_height,
            internal::GetUint32From(cfg, keys::kScreenAvailHeight));
  EXPECT_EQ(*hot.platform, "Win32");  // configured wins over the derived one
  EXPECT_EQ(hot.platform_configured, "Win32");
}

// An absent key stays nullopt; nothing is cached as an empty string.
TEST(CamoucfgHotConfigTest, AbsentKeysStayAbsent) {
  HotConfig hot = internal::HotFrom(Parse("{}"), "");
  EXPECT_FALSE(hot.platform.has_value());
  EXPECT_FALSE(hot.language.has_value());
  EXPECT_FALSE(hot.screen_width.has_value());
  EXPECT_FALSE(hot.navigator_hardware_concurrency.has_value());
  EXPECT_FALSE(hot.navigator_device_memory.has_value());
  EXPECT_FALSE(hot.window_outer_width.has_value());
  EXPECT_FALSE(hot.window_outer_height.has_value());
  EXPECT_FALSE(hot.window_screen_x.has_value());
  EXPECT_FALSE(hot.window_screen_y.has_value());
  EXPECT_FALSE(hot.navigator_app_code_name.has_value());
  EXPECT_FALSE(hot.navigator_app_name.has_value());
  EXPECT_FALSE(hot.navigator_app_version.has_value());
  EXPECT_FALSE(hot.navigator_product.has_value());
  EXPECT_FALSE(hot.navigator_product_sub.has_value());
  EXPECT_FALSE(hot.navigator_vendor.has_value());
  EXPECT_FALSE(hot.navigator_vendor_sub.has_value());
  EXPECT_FALSE(hot.screen_avail_height.has_value());
  EXPECT_FALSE(hot.screen_color_depth.has_value());
}

// No navigator.platform but a claimed OS: the frozen literal; none claimed: host.
TEST(CamoucfgHotConfigTest, PlatformFallsBackToTheClaimedOsLiteral) {
  EXPECT_EQ(internal::HotFrom(Parse("{}"), "Win32").platform, "Win32");
  // ... but the window getter's key stays the configured one only.
  EXPECT_FALSE(internal::HotFrom(Parse("{}"), "Win32").platform_configured.has_value());
  EXPECT_FALSE(internal::HotFrom(Parse("{}"), "").platform.has_value());
}

// A wrong-typed value is absent, as GetString/GetUint32 treat it.
TEST(CamoucfgHotConfigTest, WrongTypedKeysAreAbsent) {
  base::DictValue cfg =
      Parse(R"({"navigator.language": 5, "screen.width": "wide", "window.screenX": "left"})");
  HotConfig hot = internal::HotFrom(cfg, "");
  EXPECT_FALSE(hot.language.has_value());
  EXPECT_FALSE(hot.screen_width.has_value());
  EXPECT_FALSE(hot.window_screen_x.has_value());
}

// Built once: a second read returns the same object, no second parse.
TEST(CamoucfgHotConfigTest, TheProcessInstanceIsBuiltOnce) {
  EXPECT_EQ(&Hot(GlobalScope()), &Hot(GlobalScope()));
}


// Measurement, not a check (run with --gtest_also_run_disabled_tests): what one
// read costs through the dictionary against the cached struct, on a config of a
// generated identity's size. Plan step 1 of the getter-cost slice.
TEST(CamoucfgHotConfigTest, DISABLED_CostPerRead) {
  base::DictValue cfg = Parse(R"({
    "navigator.platform": "Win32", "navigator.language": "en-US",
    "navigator.languages": ["en-US", "en"], "navigator.hardwareConcurrency": 8,
    "navigator.deviceMemory": 8, "navigator.maxTouchPoints": 0,
    "screen.width": 1920, "screen.height": 1080, "screen.colorDepth": 24,
    "screen.availLeft": 0, "screen.availTop": 0,
    "screen.availWidth": 1920, "screen.availHeight": 1040,
    "window.outerWidth": 1920, "window.outerHeight": 1040,
    "window.screenX": 0, "window.screenY": 0})");
  for (int i = 0; i < 40; ++i)
    cfg.Set("zz:filler" + std::to_string(i), i);  // a realistic key count
  constexpr int kN = 2000000;
  volatile uint64_t sink = 0;
  auto time = [&](auto fn) {
    base::TimeTicks t0 = base::TimeTicks::Now();
    for (int i = 0; i < kN; ++i) fn();
    return (base::TimeTicks::Now() - t0).InNanoseconds() / double(kN);
  };
  double get_u32 = time([&] { sink += *internal::GetUint32From(cfg, keys::kScreenAvailWidth); });
  double get_u32_miss = time([&] { sink += internal::GetUint32From(cfg, "x:none").has_value(); });
  double get_str = time([&] { sink += internal::GetStringFrom(cfg, keys::kNavigatorPlatform)->size(); });
  HotConfig hot = internal::HotFrom(cfg, "Win32");
  double hot_u32 = time([&] { sink += *hot.screen_avail_width; });
  double hot_str = time([&] { sink += hot.platform->size(); });
  std::cerr << "COST ns/read: GetUint32From hit " << get_u32 << ", miss " << get_u32_miss
            << ", GetStringFrom hit (lookup + std::string copy) " << get_str
            << " | cached uint32 " << hot_u32 << ", cached string size " << hot_str << std::endl;
}

}  // namespace
}  // namespace camoucfg

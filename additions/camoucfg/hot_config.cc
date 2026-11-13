// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/hot_config.h"

#include "base/no_destructor.h"

#include "components/camoucfg/derive.h"
#include "components/camoucfg/keys.h"
#include "components/camoucfg/mask_config_internal.h"

namespace camoucfg {

namespace internal {

HotConfig HotFrom(const base::DictValue& cfg, std::string_view derived_platform) {
  HotConfig hot;
  hot.platform_configured = GetStringFrom(cfg, keys::kNavigatorPlatform);
  hot.platform = hot.platform_configured;
  if (!hot.platform && !derived_platform.empty()) {
    hot.platform = std::string(derived_platform);
  }
  hot.language = GetStringFrom(cfg, keys::kNavigatorLanguage);
  hot.navigator_app_code_name = GetStringFrom(cfg, keys::kNavigatorAppCodeName);
  hot.navigator_app_name = GetStringFrom(cfg, keys::kNavigatorAppName);
  hot.navigator_app_version = GetStringFrom(cfg, keys::kNavigatorAppVersion);
  hot.navigator_product = GetStringFrom(cfg, keys::kNavigatorProduct);
  hot.navigator_product_sub = GetStringFrom(cfg, keys::kNavigatorProductSub);
  hot.navigator_vendor = GetStringFrom(cfg, keys::kNavigatorVendor);
  hot.navigator_vendor_sub = GetStringFrom(cfg, keys::kNavigatorVendorSub);
  hot.navigator_hardware_concurrency =
      GetUint32From(cfg, keys::kNavigatorHardwareConcurrency);
  hot.navigator_device_memory = GetDoubleFrom(cfg, keys::kNavigatorDeviceMemory);
  hot.window_outer_width = GetInt32From(cfg, keys::kWindowOuterWidth);
  hot.window_outer_height = GetInt32From(cfg, keys::kWindowOuterHeight);
  hot.window_screen_x = GetInt32From(cfg, keys::kWindowScreenX);
  hot.window_screen_y = GetInt32From(cfg, keys::kWindowScreenY);
  hot.screen_color_depth = GetUint32From(cfg, keys::kScreenColorDepth);
  hot.screen_width = GetUint32From(cfg, keys::kScreenWidth);
  hot.screen_height = GetUint32From(cfg, keys::kScreenHeight);
  hot.screen_avail_left = GetUint32From(cfg, keys::kScreenAvailLeft);
  hot.screen_avail_top = GetUint32From(cfg, keys::kScreenAvailTop);
  hot.screen_avail_width = GetUint32From(cfg, keys::kScreenAvailWidth);
  hot.screen_avail_height = GetUint32From(cfg, keys::kScreenAvailHeight);
  return hot;
}

}  // namespace internal

const HotConfig& Hot(const ConfigScope& scope) {
  // A function-local static: thread-safe initialisation, immutable after.
  static const base::NoDestructor<HotConfig> hot(internal::HotFrom(
      internal::ParsedConfig(), CanonicalNavigatorPlatformFor(ClaimedOs(scope))));
  return *hot;
}

}  // namespace camoucfg

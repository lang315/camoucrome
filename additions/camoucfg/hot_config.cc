// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/hot_config.h"

#include "base/no_destructor.h"

#include "components/camoucfg/derive.h"
#include "components/camoucfg/domain_validator.h"
#include "components/camoucfg/keys.h"
#include "components/camoucfg/mask_config_internal.h"

namespace camoucfg {

namespace internal {

HotConfig HotFrom(const base::DictValue& cfg,
                  std::string_view derived_platform,
                  OsFamily claimed_os) {
  HotConfig hot;
  hot.claimed_os = claimed_os;
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
  // Out of its domain: left empty, so the consumer reports the real value
  // (stock Chrome never reports e.g. 64). The startup check already logged it.
  if (hot.navigator_device_memory &&
      CheckDomain(keys::kNavigatorDeviceMemory, *hot.navigator_device_memory)) {
    hot.navigator_device_memory.reset();
  }
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
  hot.navigator_max_touch_points =
      GetUint32From(cfg, keys::kNavigatorMaxTouchPoints);
  hot.audio_base_latency = GetDoubleFrom(cfg, keys::kAudioBaseLatency);
  hot.audio_output_latency = GetDoubleFrom(cfg, keys::kAudioOutputLatency);
  hot.audio_max_channel_count = GetUint32From(cfg, keys::kAudioMaxChannelCount);
  return hot;
}

}  // namespace internal

const HotConfig& Hot(const ConfigScope& scope) {
  // A function-local static: thread-safe initialisation, immutable after.
  static const base::NoDestructor<HotConfig> hot([&scope] {
    const OsFamily os = ClaimedOs(scope);
    return internal::HotFrom(internal::ParsedConfig(),
                             CanonicalNavigatorPlatformFor(os), os);
  }());
  return *hot;
}

}  // namespace camoucfg

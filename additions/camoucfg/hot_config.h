// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_HOT_CONFIG_H_
#define COMPONENTS_CAMOUCFG_HOT_CONFIG_H_

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

#include "components/camoucfg/mask_config.h"

namespace base {
class DictValue;
}

namespace camoucfg {

// The values of the keys a page reads on every call (navigator.platform and
// .language, screen.*), read out of the configuration once. The configuration
// is immutable after parse (CLAUDE.md), so this is safe to share between
// threads, and a getter that reads it costs a load instead of a dictionary
// lookup, a std::string copy and a UTF-8 decode per read (timing parity, PR
// "measure_timing_parity": 100-240 ns over the unconfigured getter, which a
// page can time against an untouched getter). An absent (or wrong-typed) key
// stays nullopt, exactly as in GetString/GetUint32.
struct HotConfig {
  // navigator.platform if configured; else the frozen reduced literal of the
  // claimed OS (CanonicalNavigatorPlatformFor(ClaimedOs)); nullopt when neither
  // exists, which leaves the host value.
  std::optional<std::string> platform;
  // navigator.platform as configured, with no derived fallback (the window
  // getter applies only the configured key; the worker and the fallback path
  // use `platform`).
  std::optional<std::string> platform_configured;
  std::optional<std::string> language;
  std::optional<std::string> navigator_app_code_name;
  std::optional<std::string> navigator_app_name;
  std::optional<std::string> navigator_app_version;
  std::optional<std::string> navigator_product;
  std::optional<std::string> navigator_product_sub;
  std::optional<std::string> navigator_vendor;
  std::optional<std::string> navigator_vendor_sub;
  std::optional<uint32_t> navigator_hardware_concurrency;
  std::optional<double> navigator_device_memory;
  std::optional<int32_t> window_outer_width;
  std::optional<int32_t> window_outer_height;
  std::optional<int32_t> window_screen_x;
  std::optional<int32_t> window_screen_y;
  std::optional<uint32_t> screen_color_depth;
  std::optional<uint32_t> screen_width;
  std::optional<uint32_t> screen_height;
  std::optional<uint32_t> screen_avail_left;
  std::optional<uint32_t> screen_avail_top;
  std::optional<uint32_t> screen_avail_width;
  std::optional<uint32_t> screen_avail_height;
};

// The process's HotConfig, built on first use (the same instant ParsedConfig()
// is). The scope is ignored today, as in every getter (see blink_scope.h).
const HotConfig& Hot(const ConfigScope& scope);

namespace internal {
// `derived_platform` is CanonicalNavigatorPlatformFor(ClaimedOs): empty when
// nothing is claimed.
HotConfig HotFrom(const base::DictValue& cfg, std::string_view derived_platform);
}  // namespace internal

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_HOT_CONFIG_H_

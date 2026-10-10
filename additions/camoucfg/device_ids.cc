// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/device_ids.h"

#include <cstdint>
#include <string>
#include <string_view>

#include "components/camoucfg/keys.h"

namespace camoucfg {

std::string MaskedDeviceLabel(std::string_view device_id,
                              std::string_view chrome_label,
                              std::string_view configured) {
  if (device_id == "default" || device_id == "communications") {
    const size_t sep = chrome_label.find(" - ");
    if (sep != std::string_view::npos) {
      return std::string(chrome_label.substr(0, sep + 3)) +
             std::string(configured);
    }
  }
  return std::string(configured);
}

uint32_t ActiveMediaDevicesSeed(const ConfigScope& scope) {
  if (!GetBool(scope, keys::kMediaDevicesEnabled).value_or(false)) {
    return 0;
  }
  return GetUint32(scope, keys::kMediaDevicesSeed).value_or(0);
}

}  // namespace camoucfg

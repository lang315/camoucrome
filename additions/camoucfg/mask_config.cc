// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/mask_config.h"

#include <algorithm>

#include "components/camoucfg/keys.h"
#include "components/camoucfg/mask_config_internal.h"

namespace camoucfg {

const ConfigScope& GlobalScope() {
  // A plain function-local static, not base::NoDestructor. ConfigScope is
  // empty and therefore trivially destructible, which NoDestructor
  // static_asserts against, and there is no exit-time destructor to avoid.
  static ConfigScope scope;
  return scope;
}

std::optional<std::string> GetString(const ConfigScope& scope,
                                     std::string_view key) {
  return internal::GetStringFrom(internal::ParsedConfig(), key);
}

std::optional<uint32_t> GetUint32(const ConfigScope& scope,
                                  std::string_view key) {
  return internal::GetUint32From(internal::ParsedConfig(), key);
}

std::optional<int32_t> GetInt32(const ConfigScope& scope,
                                std::string_view key) {
  return internal::GetInt32From(internal::ParsedConfig(), key);
}

std::optional<double> GetDouble(const ConfigScope& scope,
                                std::string_view key) {
  return internal::GetDoubleFrom(internal::ParsedConfig(), key);
}

std::optional<bool> GetBool(const ConfigScope& scope, std::string_view key) {
  return internal::GetBoolFrom(internal::ParsedConfig(), key);
}

std::vector<std::string> GetStringList(const ConfigScope& scope,
                                       std::string_view key) {
  return internal::GetStringListFrom(internal::ParsedConfig(), key);
}

bool HasKey(const ConfigScope& scope, std::string_view key) {
  return internal::HasKeyIn(internal::ParsedConfig(), key);
}

std::vector<std::string> UnrecognisedKeys(const ConfigScope& scope) {
  std::vector<std::string> unrecognised;
  for (const auto [key, value] : internal::ParsedConfig()) {
    if (std::find(keys::kAllKeys.begin(), keys::kAllKeys.end(), key) ==
        keys::kAllKeys.end()) {
      unrecognised.push_back(key);
    }
  }
  return unrecognised;
}

}  // namespace camoucfg

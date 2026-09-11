// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/mask_config.h"

#include <algorithm>

#include "base/strings/string_util.h"
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

std::vector<VoiceConfig> GetVoices(const ConfigScope& scope) {
  return internal::GetVoicesFrom(internal::ParsedConfig(),
                                 keys::kVoicesList);
}

bool HasKey(const ConfigScope& scope, std::string_view key) {
  return internal::HasKeyIn(internal::ParsedConfig(), key);
}

namespace internal {

bool IsFontAllowedFrom(const base::DictValue& cfg, std::string_view family) {
  if (!HasKeyIn(cfg, keys::kFonts))
    return true;  // rule 5: unconfigured => every host font visible.
  for (const std::string& allowed : GetStringListFrom(cfg, keys::kFonts)) {
    if (base::EqualsCaseInsensitiveASCII(allowed, family))
      return true;
  }
  return false;
}

std::optional<std::string> FontAliasFrom(const base::DictValue& cfg, std::string_view family) {
  const base::DictValue* map = cfg.FindDict(keys::kFontsAlias);
  if (!map) {
    return std::nullopt;
  }
  for (const auto [requested, target] : *map) {
    if (target.is_string() && !target.GetString().empty() &&
        base::EqualsCaseInsensitiveASCII(requested, family)) {
      return target.GetString();
    }
  }
  return std::nullopt;
}

}  // namespace internal

bool IsFontAllowed(const ConfigScope& scope, std::string_view family) {
  return internal::IsFontAllowedFrom(internal::ParsedConfig(), family);
}

std::optional<std::string> FontAlias(const ConfigScope& scope, std::string_view family) {
  return internal::FontAliasFrom(internal::ParsedConfig(), family);
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

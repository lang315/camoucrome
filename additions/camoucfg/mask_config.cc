// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/mask_config.h"

#include <algorithm>

#include "base/environment.h"
#include "base/logging.h"
#include "base/no_destructor.h"
#include "base/values.h"
#include "components/camoucfg/keys.h"
#include "components/camoucfg/mask_config_internal.h"

namespace camoucfg {
namespace {

// Parsed exactly once per process, on first access, in whichever process
// touches the configuration first.
const base::DictValue& Config() {
  static const base::NoDestructor<base::DictValue> dict([] {
    std::unique_ptr<base::Environment> env = base::Environment::Create();
    auto get = [&env](const std::string& name) -> std::optional<std::string> {
      return env->GetVar(name);
    };
    const std::string raw = internal::AssembleRawConfig(get);
    const bool strict = env->GetVar("CAMOU_CONFIG_STRICT").has_value();
    base::DictValue parsed = internal::ParseConfig(raw, strict);
    VLOG(1) << "camoucfg: parsed " << parsed.size() << " key(s)";
    return parsed;
  }());
  return *dict;
}

}  // namespace

const ConfigScope& GlobalScope() {
  // A plain function-local static, not base::NoDestructor. ConfigScope is
  // empty and therefore trivially destructible, which NoDestructor
  // static_asserts against, and there is no exit-time destructor to avoid.
  static ConfigScope scope;
  return scope;
}

std::optional<std::string> GetString(const ConfigScope& scope,
                                     std::string_view key) {
  return internal::GetStringFrom(Config(), key);
}

std::optional<uint32_t> GetUint32(const ConfigScope& scope,
                                  std::string_view key) {
  return internal::GetUint32From(Config(), key);
}

std::optional<int32_t> GetInt32(const ConfigScope& scope,
                                std::string_view key) {
  return internal::GetInt32From(Config(), key);
}

std::optional<double> GetDouble(const ConfigScope& scope,
                                std::string_view key) {
  return internal::GetDoubleFrom(Config(), key);
}

std::optional<bool> GetBool(const ConfigScope& scope, std::string_view key) {
  return internal::GetBoolFrom(Config(), key);
}

std::vector<std::string> GetStringList(const ConfigScope& scope,
                                       std::string_view key) {
  return internal::GetStringListFrom(Config(), key);
}

bool HasKey(const ConfigScope& scope, std::string_view key) {
  return internal::HasKeyIn(Config(), key);
}

std::vector<std::string> UnrecognisedKeys(const ConfigScope& scope) {
  std::vector<std::string> unrecognised;
  for (const auto [key, value] : Config()) {
    if (std::find(keys::kAllKeys.begin(), keys::kAllKeys.end(), key) ==
        keys::kAllKeys.end()) {
      unrecognised.push_back(key);
    }
  }
  return unrecognised;
}

}  // namespace camoucfg

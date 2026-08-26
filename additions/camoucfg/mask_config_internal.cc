// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/mask_config_internal.h"

#include "base/json/json_reader.h"
#include "base/logging.h"
#include "base/strings/strcat.h"
#include "base/strings/string_number_conversions.h"

namespace camoucfg::internal {

namespace {

void WarnWrongType(std::string_view key, const char* expected) {
  LOG(WARNING) << "camoucfg: key '" << key << "' is not " << expected
               << "; falling back to the real value";
}

}  // namespace

std::string AssembleRawConfig(EnvGetter get) {
  std::string assembled;
  for (int index = 1;; ++index) {
    std::optional<std::string> chunk =
        get(base::StrCat({"CAMOU_CONFIG_", base::NumberToString(index)}));
    if (!chunk.has_value()) {
      break;
    }
    assembled += *chunk;
  }

  if (!assembled.empty()) {
    return assembled;
  }

  std::optional<std::string> single = get("CAMOU_CONFIG");
  return single.value_or(std::string());
}

base::DictValue ParseConfig(std::string_view raw, bool strict) {
  if (raw.empty()) {
    return base::DictValue();
  }

  // ReadDict rejects both malformed JSON and valid JSON that is not an
  // object, in one call. `options` has no default in this revision and must
  // be passed; JSON_PARSE_RFC is the strict reading, which is right for a
  // machine-generated configuration — comments and trailing commas in a
  // fingerprint would mean the generator is broken.
  std::optional<base::DictValue> parsed =
      base::JSONReader::ReadDict(raw, base::JSON_PARSE_RFC);
  if (!parsed.has_value()) {
    LOG(ERROR) << "camoucfg: configuration is not a JSON object; "
               << "all spoofing is disabled and real values will be reported";
    CHECK(!strict) << "camoucfg: refusing to start with an invalid "
                   << "configuration because CAMOU_CONFIG_STRICT is set";
    return base::DictValue();
  }

  return std::move(*parsed);
}

std::optional<std::string> GetStringFrom(const base::DictValue& cfg,
                                         std::string_view key) {
  const base::Value* value = cfg.Find(key);
  if (!value) {
    return std::nullopt;
  }
  if (!value->is_string()) {
    WarnWrongType(key, "a string");
    return std::nullopt;
  }
  return value->GetString();
}

std::optional<uint32_t> GetUint32From(const base::DictValue& cfg,
                                      std::string_view key) {
  const base::Value* value = cfg.Find(key);
  if (!value) {
    return std::nullopt;
  }
  if (!value->is_int()) {
    WarnWrongType(key, "an integer");
    return std::nullopt;
  }
  const int as_int = value->GetInt();
  if (as_int < 0) {
    WarnWrongType(key, "a non-negative integer");
    return std::nullopt;
  }
  return static_cast<uint32_t>(as_int);
}

std::optional<int32_t> GetInt32From(const base::DictValue& cfg,
                                    std::string_view key) {
  const base::Value* value = cfg.Find(key);
  if (!value) {
    return std::nullopt;
  }
  if (!value->is_int()) {
    WarnWrongType(key, "an integer");
    return std::nullopt;
  }
  return value->GetInt();
}

std::optional<double> GetDoubleFrom(const base::DictValue& cfg,
                                    std::string_view key) {
  const base::Value* value = cfg.Find(key);
  if (!value) {
    return std::nullopt;
  }
  // A JSON number with no fractional part parses as an int. Widening it is
  // what a configuration author expects, so accept both.
  if (value->is_int()) {
    return static_cast<double>(value->GetInt());
  }
  if (!value->is_double()) {
    WarnWrongType(key, "a number");
    return std::nullopt;
  }
  return value->GetDouble();
}

std::optional<bool> GetBoolFrom(const base::DictValue& cfg,
                                std::string_view key) {
  const base::Value* value = cfg.Find(key);
  if (!value) {
    return std::nullopt;
  }
  if (!value->is_bool()) {
    WarnWrongType(key, "a boolean");
    return std::nullopt;
  }
  return value->GetBool();
}

std::vector<std::string> GetStringListFrom(const base::DictValue& cfg,
                                           std::string_view key) {
  const base::Value* value = cfg.Find(key);
  if (!value) {
    return {};
  }
  if (!value->is_list()) {
    WarnWrongType(key, "a list");
    return {};
  }

  std::vector<std::string> out;
  for (const base::Value& entry : value->GetList()) {
    if (!entry.is_string()) {
      WarnWrongType(key, "a list of strings");
      return {};
    }
    out.push_back(entry.GetString());
  }
  return out;
}

bool HasKeyIn(const base::DictValue& cfg, std::string_view key) {
  return cfg.Find(key) != nullptr;
}

}  // namespace camoucfg::internal

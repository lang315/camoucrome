// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/mask_config_internal.h"

#include <cmath>
#include <limits>
#include <string_view>

#include "base/environment.h"
#include "base/json/json_reader.h"
#include "base/logging.h"
#include "base/no_destructor.h"
#include "base/strings/strcat.h"
#include "base/strings/string_number_conversions.h"
#include "components/camoucfg/keys.h"
#include "components/camoucfg/preset_loader.h"
#include "components/version_info/version_info.h"

namespace camoucfg::internal {

namespace {

void WarnWrongType(std::string_view key, const char* expected) {
  LOG(WARNING) << "camoucfg: key '" << key << "' is not " << expected
               << "; falling back to the real value";
}

// A JSON number as an integer in [lo, hi]. JSONReader stores whole numbers
// outside int's range (every seed above 2^31-1) and any number written with
// a fraction part ("1920.0") as a double; those are integers too when they
// are whole and in range.
std::optional<int64_t> IntegralIn(const base::Value& value, int64_t lo,
                                  int64_t hi) {
  double d;
  if (value.is_int()) {
    d = value.GetInt();
  } else if (value.is_double()) {
    d = value.GetDouble();
  } else {
    return std::nullopt;
  }
  if (!(d >= static_cast<double>(lo) && d <= static_cast<double>(hi)) ||
      d != std::trunc(d)) {
    return std::nullopt;
  }
  return static_cast<int64_t>(d);
}

}  // namespace

std::string AssembleRawConfig(EnvGetter get, std::string_view prefix) {
  std::string assembled;
  for (int index = 1;; ++index) {
    std::optional<std::string> chunk =
        get(base::StrCat({prefix, "_", base::NumberToString(index)}));
    if (!chunk.has_value()) {
      break;
    }
    assembled += *chunk;
  }

  if (!assembled.empty()) {
    return assembled;
  }

  std::optional<std::string> single = get(std::string(prefix));
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
    LOG(ERROR) << "camoucfg: configuration is not a JSON object; its keys "
               << "are ignored and report real values (a CAMOU_PRESET, if "
               << "set, still applies)";
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
  std::optional<int64_t> v =
      IntegralIn(*value, 0, std::numeric_limits<uint32_t>::max());
  if (!v) {
    WarnWrongType(key, "an integer in [0, 2^32)");
    return std::nullopt;
  }
  return static_cast<uint32_t>(*v);
}

std::optional<int32_t> GetInt32From(const base::DictValue& cfg,
                                    std::string_view key) {
  const base::Value* value = cfg.Find(key);
  if (!value) {
    return std::nullopt;
  }
  std::optional<int64_t> v =
      IntegralIn(*value, std::numeric_limits<int32_t>::min(),
                 std::numeric_limits<int32_t>::max());
  if (!v) {
    WarnWrongType(key, "a 32-bit integer");
    return std::nullopt;
  }
  return static_cast<int32_t>(*v);
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

std::vector<VoiceConfig> GetVoicesFrom(const base::DictValue& cfg,
                                       std::string_view key) {
  const base::Value* value = cfg.Find(key);
  if (!value) {
    return {};
  }
  if (!value->is_list()) {
    WarnWrongType(key, "a list");
    return {};
  }
  std::vector<VoiceConfig> out;
  for (const base::Value& entry : value->GetList()) {
    if (!entry.is_dict()) {
      WarnWrongType(key, "a list of voice objects");
      return {};
    }
    const base::DictValue& d = entry.GetDict();
    VoiceConfig v;
    if (const std::string* s = d.FindString("name")) {
      v.name = *s;
    }
    if (const std::string* s = d.FindString("lang")) {
      v.lang = *s;
    }
    if (const std::string* s = d.FindString("voiceURI")) {
      v.voice_uri = *s;
    } else {
      v.voice_uri = v.name;  // fall back to the display name
    }
    v.is_local_service = d.FindBool("localService").value_or(true);
    v.is_default = d.FindBool("default").value_or(false);
    out.push_back(std::move(v));
  }
  return out;
}

bool HasKeyIn(const base::DictValue& cfg, std::string_view key) {
  return cfg.Find(key) != nullptr;
}

base::DictValue MergeExplicitOverPreset(base::DictValue expanded_preset,
                                        base::DictValue explicit_cfg) {
  // An explicit null means "not set": it must not erase a preset value.
  std::vector<std::string> nulls;
  for (const auto [key, value] : explicit_cfg) {
    if (value.is_none()) {
      nulls.push_back(key);
    }
  }
  for (const std::string& key : nulls) {
    explicit_cfg.Remove(key);
  }
  OverridePresetGroups(expanded_preset, explicit_cfg);
  expanded_preset.Merge(std::move(explicit_cfg));
  return expanded_preset;
}

const base::DictValue& ParsedConfig() {
  static const base::NoDestructor<base::DictValue> dict([] {
    std::unique_ptr<base::Environment> env = base::Environment::Create();
    auto get = [&env](const std::string& name) -> std::optional<std::string> {
      return env->GetVar(name);
    };
    const std::string raw = AssembleRawConfig(get);
    const bool strict = env->GetVar("CAMOU_CONFIG_STRICT").has_value();
    base::DictValue parsed = ParseConfig(raw, strict);
    const std::string raw_preset = AssembleRawConfig(get, "CAMOU_PRESET");
    if (!raw_preset.empty()) {
      // Same rule as the config -- malformed refuses under strict, otherwise
      // is ignored -- but its own message: ParseConfig's says all spoofing
      // is disabled, which is untrue here, the explicit keys still apply.
      std::optional<base::DictValue> preset =
          base::JSONReader::ReadDict(raw_preset, base::JSON_PARSE_RFC);
      if (!preset.has_value()) {
        LOG(ERROR) << "camoucfg: preset is not a JSON object; ignored, "
                   << "explicit configuration still applies";
        CHECK(!strict) << "camoucfg: refusing to start with an invalid "
                       << "preset because CAMOU_CONFIG_STRICT is set";
      } else {
        // Merge is recursive: an explicit webGl:parameters overrides the
        // preset's table pname by pname, not as a whole.
        parsed = MergeExplicitOverPreset(
            ExpandPreset(*preset, version_info::GetMajorVersionNumberAsInt()),
            std::move(parsed));
      }
    }
    VLOG(1) << "camoucfg: parsed " << parsed.size() << " key(s)";
    return parsed;
  }());
  return *dict;
}

std::optional<GLValue> GLParamFrom(const base::DictValue& cfg,
                                   uint32_t pname, bool is_webgl2) {
  const base::DictValue* params = cfg.FindDict(
      is_webgl2 ? keys::kWebGl2Parameters : keys::kWebGlParameters);
  if (!params) {
    return std::nullopt;
  }
  const base::Value* v = params->Find(base::NumberToString(pname));
  if (!v) {
    return std::nullopt;
  }
  switch (v->type()) {
    case base::Value::Type::INTEGER:
      return GLValue(int64_t{v->GetInt()});
    case base::Value::Type::DOUBLE:
      return GLValue(v->GetDouble());
    case base::Value::Type::BOOLEAN:
      return GLValue(v->GetBool());
    case base::Value::Type::STRING:
      return GLValue(v->GetString());
    case base::Value::Type::LIST: {
      std::vector<double> out;
      for (const base::Value& e : v->GetList()) {
        if (e.is_int()) {
          out.push_back(e.GetInt());
        } else if (e.is_double()) {
          out.push_back(e.GetDouble());
        } else {
          return std::nullopt;  // heterogeneous/garbage list
        }
      }
      return GLValue(std::move(out));
    }
    default:
      return std::nullopt;
  }
}

bool GLBlockFrom(const base::DictValue& cfg, bool is_webgl2) {
  return cfg.FindBool(is_webgl2 ? keys::kWebGl2ParamsBlock
                                : keys::kWebGlParamsBlock)
      .value_or(false);
}

std::optional<std::array<int, 3>> GLShaderPrecisionFrom(
    const base::DictValue& cfg, uint32_t shadertype, uint32_t precisiontype,
    bool is_webgl2) {
  const base::DictValue* m = cfg.FindDict(
      is_webgl2 ? keys::kWebGl2ShaderPrecision : keys::kWebGlShaderPrecision);
  if (!m) {
    return std::nullopt;
  }
  const base::Value* v = m->Find(base::NumberToString(shadertype) + ":" +
                                 base::NumberToString(precisiontype));
  if (!v || !v->is_list() || v->GetList().size() != 3) {
    return std::nullopt;
  }
  std::array<int, 3> out{};
  for (int i = 0; i < 3; ++i) {
    if (!v->GetList()[i].is_int()) {
      return std::nullopt;
    }
    out[i] = v->GetList()[i].GetInt();
  }
  return out;
}

bool GLShaderPrecisionBlockFrom(const base::DictValue& cfg, bool is_webgl2) {
  return cfg.FindBool(is_webgl2 ? keys::kWebGl2ShaderPrecisionBlock
                                : keys::kWebGlShaderPrecisionBlock)
      .value_or(false);
}

const base::DictValue* GLContextAttrsFrom(const base::DictValue& cfg,
                                          bool is_webgl2) {
  return cfg.FindDict(is_webgl2 ? keys::kWebGl2ContextAttrs
                                : keys::kWebGlContextAttrs);
}

}  // namespace camoucfg::internal

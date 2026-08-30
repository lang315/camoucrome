// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/mask_config_internal.h"

#include "base/environment.h"
#include "base/json/json_reader.h"
#include "base/logging.h"
#include "base/no_destructor.h"
#include "base/strings/strcat.h"
#include "base/strings/string_number_conversions.h"
#include "components/camoucfg/keys.h"

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

const base::DictValue& ParsedConfig() {
  static const base::NoDestructor<base::DictValue> dict([] {
    std::unique_ptr<base::Environment> env = base::Environment::Create();
    auto get = [&env](const std::string& name) -> std::optional<std::string> {
      return env->GetVar(name);
    };
    const std::string raw = AssembleRawConfig(get);
    const bool strict = env->GetVar("CAMOU_CONFIG_STRICT").has_value();
    base::DictValue parsed = ParseConfig(raw, strict);
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

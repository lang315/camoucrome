// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/gl_params.h"

#include "components/camoucfg/keys.h"
#include "components/camoucfg/mask_config_internal.h"

namespace camoucfg {

std::optional<GLValue> GLParam(const ConfigScope& scope, uint32_t pname,
                               bool is_webgl2) {
  return internal::GLParamFrom(internal::ParsedConfig(), pname, is_webgl2);
}

std::optional<std::string> GLVendor(const ConfigScope& scope,
                                    bool is_webgl2) {
  return GetString(scope,
                   is_webgl2 ? keys::kWebGl2Vendor : keys::kWebGlVendor);
}

std::optional<std::string> GLRenderer(const ConfigScope& scope,
                                      bool is_webgl2) {
  return GetString(scope,
                   is_webgl2 ? keys::kWebGl2Renderer : keys::kWebGlRenderer);
}

bool GLBlockIfNotDefined(const ConfigScope& scope, bool is_webgl2) {
  return internal::GLBlockFrom(internal::ParsedConfig(), is_webgl2);
}

std::optional<std::array<int, 3>> GLShaderPrecision(const ConfigScope& scope,
                                                    uint32_t shadertype,
                                                    uint32_t precisiontype,
                                                    bool is_webgl2) {
  return internal::GLShaderPrecisionFrom(internal::ParsedConfig(), shadertype,
                                         precisiontype, is_webgl2);
}

bool GLShaderPrecisionBlock(const ConfigScope& scope, bool is_webgl2) {
  return internal::GLShaderPrecisionBlockFrom(internal::ParsedConfig(),
                                              is_webgl2);
}

const base::DictValue* GLContextAttrs(const ConfigScope& scope,
                                      bool is_webgl2) {
  return internal::GLContextAttrsFrom(internal::ParsedConfig(), is_webgl2);
}

bool GLParamsConfigured(const ConfigScope& scope, bool is_webgl2) {
  const base::DictValue* d = internal::ParsedConfig().FindDict(
      is_webgl2 ? keys::kWebGl2Parameters : keys::kWebGlParameters);
  return d && !d->empty();
}

bool GLShaderPrecisionConfigured(const ConfigScope& scope, bool is_webgl2) {
  const base::DictValue* d = internal::ParsedConfig().FindDict(
      is_webgl2 ? keys::kWebGl2ShaderPrecision : keys::kWebGlShaderPrecision);
  return d && !d->empty();
}

bool GLContextAttrsConfigured(const ConfigScope& scope, bool is_webgl2) {
  const base::DictValue* d = GLContextAttrs(scope, is_webgl2);
  return d && !d->empty();
}

bool GLExtensionsConfigured(const ConfigScope& scope, bool is_webgl2) {
  return !GetStringList(scope, is_webgl2 ? keys::kWebGl2Extensions
                                         : keys::kWebGlExtensions)
              .empty();
}

}  // namespace camoucfg

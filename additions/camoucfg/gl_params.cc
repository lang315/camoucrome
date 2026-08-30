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

}  // namespace camoucfg

// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_GL_PARAMS_H_
#define COMPONENTS_CAMOUCFG_GL_PARAMS_H_

#include <cstdint>
#include <optional>
#include <string>
#include <variant>
#include <vector>

#include "components/camoucfg/mask_config.h"

namespace camoucfg {

// A WebGL getParameter() return value, as configured. getParameter()'s
// return type varies by pname -- an int, a float, a bool, a string, or a
// float array such as ALIASED_LINE_WIDTH_RANGE -- so this variant carries
// whichever of those the configuration supplied for a given pname.
using GLValue =
    std::variant<int64_t, double, bool, std::string, std::vector<double>>;

// Looks up `pname`'s decimal string inside the webGl:parameters map (or,
// when is_webgl2 is true, webGl2:parameters) and returns its typed value.
// nullopt when the map, or the pname within it, is absent -- the caller
// falls back to the real value, never a placeholder.
std::optional<GLValue> GLParam(const ConfigScope& scope, uint32_t pname,
                               bool is_webgl2);

// webGl:vendor / webGl2:vendor and webGl:renderer / webGl2:renderer -- the
// UNMASKED_VENDOR_WEBGL / UNMASKED_RENDERER_WEBGL strings a page reads
// through the WEBGL_debug_renderer_info extension.
std::optional<std::string> GLVendor(const ConfigScope& scope, bool is_webgl2);
std::optional<std::string> GLRenderer(const ConfigScope& scope,
                                      bool is_webgl2);

// webGl:parameters:blockIfNotDefined / webGl2:parameters:blockIfNotDefined.
// Defaults to false when absent.
bool GLBlockIfNotDefined(const ConfigScope& scope, bool is_webgl2);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_GL_PARAMS_H_

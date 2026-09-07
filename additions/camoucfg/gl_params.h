// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_GL_PARAMS_H_
#define COMPONENTS_CAMOUCFG_GL_PARAMS_H_

#include <array>
#include <cstdint>
#include <optional>
#include <string>
#include <variant>
#include <vector>

#include "base/values.h"
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

// getShaderPrecisionFormat(shadertype, precisiontype)'s return value, read
// from the webGl:shaderPrecisionFormats map (or webGl2: when is_webgl2) keyed
// by the compound string "<shadertype>:<precisiontype>". nullopt when the
// map, or the compound key within it, is absent -- the caller falls back to
// the real value, never a placeholder.
std::optional<std::array<int, 3>> GLShaderPrecision(const ConfigScope& scope,
                                                    uint32_t shadertype,
                                                    uint32_t precisiontype,
                                                    bool is_webgl2);

// webGl:shaderPrecisionFormats:blockIfNotDefined /
// webGl2:shaderPrecisionFormats:blockIfNotDefined. Defaults to false when
// absent.
bool GLShaderPrecisionBlock(const ConfigScope& scope, bool is_webgl2);

// webGl:contextAttributes / webGl2:contextAttributes -- the
// WebGLContextAttributes dict a page reads back through
// getContextAttributes(). Returns nullptr when the key is absent; callers
// read individual bool/string fields off the returned dict.
const base::DictValue* GLContextAttrs(const ConfigScope& scope,
                                      bool is_webgl2);

// Whether the operator configured a spoofed capability VALUE for each WebGL
// surface: the map/list is present AND non-empty. An empty map or list
// configures no value -- every value read resolves to the host exactly as an
// absent key does (verified against each consumer: FindDict-missing pnames, and
// the extension hook's `if (!list.empty())` fall-through). (A bare
// `...:blockIfNotDefined` flag with an empty/absent map is a separate case: it
// can make blockable pnames error rather than return the host value, but it
// spoofs no value, so it is deliberately not treated as "configured" here.)
// Type-aware: a wrong-typed value (FindDict / GetStringList returns null /
// empty) reads as not configured. SP5's coherence validator uses these to
// require the identity strings (webGl:renderer / webGl:vendor) whenever any
// capability value is spoofed, so a spoofed GPU capability never sits beside
// this machine's real GPU identity.
bool GLParamsConfigured(const ConfigScope& scope, bool is_webgl2);
bool GLShaderPrecisionConfigured(const ConfigScope& scope, bool is_webgl2);
bool GLContextAttrsConfigured(const ConfigScope& scope, bool is_webgl2);
bool GLExtensionsConfigured(const ConfigScope& scope, bool is_webgl2);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_GL_PARAMS_H_

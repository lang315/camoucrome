// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_MASK_CONFIG_INTERNAL_H_
#define COMPONENTS_CAMOUCFG_MASK_CONFIG_INTERNAL_H_

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "base/functional/function_ref.h"
#include "base/values.h"
#include "components/camoucfg/gl_params.h"

namespace camoucfg::internal {

// Signature of an environment lookup. Injected so tests never mutate the
// real process environment.
using EnvGetter =
    base::FunctionRef<std::optional<std::string>(const std::string&)>;

// Concatenates CAMOU_CONFIG_1, CAMOU_CONFIG_2, ... in index order, stopping
// at the first index that is absent. Falls back to the unnumbered
// CAMOU_CONFIG when that concatenation comes out **empty** — which covers
// both "no numbered variable was set at all" and "every numbered variable
// that was set held an empty string". Returns an empty string when neither
// form yields anything, the normal case for a stock run.
//
// The trigger is emptiness of the result, not absence of CAMOU_CONFIG_1.
// Those differ when a numbered variable is present but empty, and the
// difference is deliberate: Camoufox's MaskConfig.hpp checks
// `if (jsonString.empty())` after the same loop, and this transport has to
// stay byte-compatible with it. PresentButEmptyChunkFallsBackToUnnumbered
// is the test that pins the distinction.
//
// The chunking exists because Windows caps a single environment variable
// near 32KB and a full fingerprint exceeds that.
std::string AssembleRawConfig(EnvGetter get);

// Parses the assembled configuration. The expected shape is a flat JSON
// object whose keys are dotted or colon-separated strings.
//
// Returns an empty dictionary when `raw` is empty, which is the normal
// stock-run case and is not logged. Malformed JSON, or valid JSON that is
// not an object, logs one error and returns an empty dictionary — every
// surface then falls back to its real value. When `strict` is true the same
// conditions abort the process instead, so that a misconfigured run fails
// loudly rather than silently exposing the real machine.
base::DictValue ParseConfig(std::string_view raw, bool strict);

// Typed lookups over an already-parsed configuration.
//
// Each returns nullopt when the key is absent, and logs a warning naming the
// key and returns nullopt when the key is present with the wrong type. A
// caller that gets nullopt falls back to the real value; never to a
// placeholder.
//
// These take the dictionary explicitly rather than reading process-global
// state so that every type path is testable. The public API in
// mask_config.h forwards to them with the process configuration.
std::optional<std::string> GetStringFrom(const base::DictValue& cfg,
                                         std::string_view key);
std::optional<uint32_t> GetUint32From(const base::DictValue& cfg,
                                      std::string_view key);
std::optional<int32_t> GetInt32From(const base::DictValue& cfg,
                                    std::string_view key);
std::optional<double> GetDoubleFrom(const base::DictValue& cfg,
                                    std::string_view key);
std::optional<bool> GetBoolFrom(const base::DictValue& cfg,
                                std::string_view key);
std::vector<std::string> GetStringListFrom(const base::DictValue& cfg,
                                           std::string_view key);
bool HasKeyIn(const base::DictValue& cfg, std::string_view key);

// The process-wide parsed configuration, owned here (rather than as a
// file-local in mask_config.cc) so that mask_config.cc's getters and
// gl_params.cc's GLParam() / GLBlockIfNotDefined() read the same parsed
// singleton instead of each parsing the environment separately.
const base::DictValue& ParsedConfig();

// Real logic behind camoucfg::GLParam() -- see gl_params.h for the public
// API this backs. `cfg` is a namespaced flat dict whose "webGl:parameters" /
// "webGl2:parameters" entry is itself a nested map, keyed by the decimal
// string of a GLenum pname, of whatever getParameter(pname) should return.
std::optional<GLValue> GLParamFrom(const base::DictValue& cfg,
                                   uint32_t pname, bool is_webgl2);

// Real logic behind camoucfg::GLBlockIfNotDefined().
bool GLBlockFrom(const base::DictValue& cfg, bool is_webgl2);

}  // namespace camoucfg::internal

#endif  // COMPONENTS_CAMOUCFG_MASK_CONFIG_INTERNAL_H_

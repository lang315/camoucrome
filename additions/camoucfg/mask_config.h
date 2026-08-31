// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_MASK_CONFIG_H_
#define COMPONENTS_CAMOUCFG_MASK_CONFIG_H_

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "base/values.h"

namespace camoucfg {

// Identifies which configuration a lookup reads.
//
// Today there is exactly one, returned by GlobalScope(). The parameter
// exists so that a later per-context store — pushed from the browser process
// or set over the DevTools protocol — can be introduced by changing how a
// scope is obtained, without editing a single call site. Camoufox reached
// the same conclusion the hard way: its issue #57, per-context timezone not
// working, is what a global-only configuration costs when the requirement
// arrives later.
class ConfigScope {
 public:
  ConfigScope(const ConfigScope&) = delete;
  ConfigScope& operator=(const ConfigScope&) = delete;

 private:
  // base::NoDestructor static_asserts against a trivially destructible T
  // (base/no_destructor.h): "please use a function-local static of type T
  // directly instead". ConfigScope has no members and an implicit
  // destructor, so it is trivially destructible, and a plain function-local
  // static already has no exit-time destructor to skip — NoDestructor would
  // buy nothing here. GlobalScope() constructs the singleton directly via a
  // function-local static, so it is GlobalScope — not NoDestructor — that
  // needs access to this constructor.
  friend const ConfigScope& GlobalScope();
  ConfigScope() = default;
};

// The process-wide configuration. Parsed from the environment on first use.
const ConfigScope& GlobalScope();

// Each getter returns nullopt when the key is absent, and logs a warning and
// returns nullopt when the key is present with the wrong type. Callers are
// expected to fall back to the real value; never to a placeholder.
std::optional<std::string> GetString(const ConfigScope& scope,
                                     std::string_view key);
std::optional<uint32_t> GetUint32(const ConfigScope& scope,
                                  std::string_view key);
std::optional<int32_t> GetInt32(const ConfigScope& scope,
                                std::string_view key);
std::optional<double> GetDouble(const ConfigScope& scope,
                                std::string_view key);
std::optional<bool> GetBool(const ConfigScope& scope, std::string_view key);

// Returns an empty vector when the key is absent or is not a list of strings.
std::vector<std::string> GetStringList(const ConfigScope& scope,
                                       std::string_view key);

// True when |family| may resolve to a real host face: no "fonts" key is set
// (every host font visible), or |family| is in the list (case-insensitive).
// The gate applies this only to non-generic families (generics always render).
bool IsFontAllowed(const ConfigScope& scope, std::string_view family);

bool HasKey(const ConfigScope& scope, std::string_view key);

// The keys present in the configuration that keys.h does not declare.
//
// A mistyped key is otherwise completely SILENT. Nothing matches it, every
// getter falls back to the real value, and the browser runs entirely
// unspoofed while the operator believes it is disguised. For an anti-detect
// build that is worse than a crash: it fails in the one direction the user
// cannot observe, and the page cannot tell them either.
//
// Returns the unrecognised keys rather than the whole dictionary, so the
// parsed configuration stays encapsulated and callers cannot start reading
// keys that bypass the typed getters above.
std::vector<std::string> UnrecognisedKeys(const ConfigScope& scope);

// IsFontAllowed's testable core: the same logic, operating on an
// already-parsed configuration instead of the process-wide ParsedConfig()
// singleton, so every case (absent key, populated list, present-but-empty
// list) is testable without depending on process-launch environment state.
// Mirrors mask_config_internal.h's GetStringFrom/HasKeyIn split and
// gl_params.h's GLParam()/GLParamFrom() split; declared here rather than in
// mask_config_internal.h because this task's file scope is limited to
// mask_config.h/.cc — see the SP4-fonts Task 1 report for the follow-up.
namespace internal {
bool IsFontAllowedFrom(const base::DictValue& cfg, std::string_view family);
}  // namespace internal

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_MASK_CONFIG_H_

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

bool HasKey(const ConfigScope& scope, std::string_view key);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_MASK_CONFIG_H_

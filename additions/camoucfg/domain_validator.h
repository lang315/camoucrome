// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_DOMAIN_VALIDATOR_H_
#define COMPONENTS_CAMOUCFG_DOMAIN_VALIDATOR_H_

#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "components/camoucfg/mask_config.h"

namespace camoucfg {

// A single configured numeric value that falls outside the range a downstream
// Chromium consumer will accept. Unlike a coherence Violation (which is about
// two keys disagreeing), this is about one key on its own being out of range.
struct DomainViolation {
  std::string key;
  std::string value;   // the offending value, stringified for the log line
  std::string reason;  // human-readable description of the allowed range
};

// Pure per-value domain check: table lookup plus a range compare, with NO
// configuration access. Returns a violation when `value` is outside the domain
// registered for `key`, and nullopt when it is in range OR when `key` has no
// registered domain.
//
// It is factored out from ValidateDomains precisely so it can be tested
// exhaustively with literals. ScopeFor() is process-global and the parsed
// config is cached once per process, so anything that reads config is
// one-process-per-configuration to test; a pure function is not.
std::optional<DomainViolation> CheckDomain(std::string_view key, double value);

// Reads every domain-registered key from the configuration and reports each
// value that is out of range. Pure in the same sense as Validate(): it reports,
// it does not repair and it does not log. An absent key, or a key present with
// the wrong type, is skipped -- a range check has nothing to say about a value
// that is not a number, and the getter has already warned about the wrong type.
std::vector<DomainViolation> ValidateDomains(const ConfigScope& scope);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_DOMAIN_VALIDATOR_H_

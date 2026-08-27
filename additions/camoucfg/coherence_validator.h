// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_COHERENCE_VALIDATOR_H_
#define COMPONENTS_CAMOUCFG_COHERENCE_VALIDATOR_H_

#include <string>
#include <string_view>
#include <vector>

#include "components/camoucfg/mask_config.h"

namespace camoucfg {

struct Violation {
  std::string_view invariant_id;
  // The key that decided the answer -- keys[0] of the entry. Carried so a log
  // line and a test can both name WHICH value the wrong one disagrees with,
  // rather than reporting a contradiction without saying against what.
  std::string authoritative_key;
  // The key this violation would change. Empty when the policy is kReject and
  // no repair is defined.
  std::string repaired_key;
  std::string old_value;
  std::string new_value;
};

// Evaluates every registry entry against the configuration and reports what is
// wrong. Pure: it reports, it does not repair and it does not log.
//
// Keeping detection separate from what is done about it is what lets the test
// suite assert "this configuration violates exactly this entry and no other"
// without also asserting a policy decision.
std::vector<Violation> Validate(const ConfigScope& scope);

// Called once from the browser process before any renderer exists. Returns
// false when startup must be refused.
//
// Under CAMOU_CONFIG_STRICT every violation refuses. Otherwise a kRepair entry
// is reported loudly and a kReject entry refuses.
//
// It does not repair, and it is not named as though it does. Applying repairs
// needs a write path into the cached configuration -- a change to a component
// three sub-projects already depend on -- and gets its own task and tests. A
// name promising an action it does not perform misleads at every call site,
// which is worse than a log line doing the same at the console.
//
// This runs in the BROWSER process by design, and the reason is a rule rather
// than a convenience. Conventions forbid a renderer crashing on bad
// configuration, because a crash is itself a fingerprint; the browser process
// is the only point at which the fork can still decline to start. It is also
// the only place that can see the whole configuration at once, which a
// relational invariant needs by definition.
bool ValidateAtStartup(const ConfigScope& scope);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_COHERENCE_VALIDATOR_H_

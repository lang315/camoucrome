// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_COHERENCE_VALIDATOR_H_
#define COMPONENTS_CAMOUCFG_COHERENCE_VALIDATOR_H_

#include <optional>
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
  // The key this violation would change. Every registry entry is
  // Policy::kRepair -- invariants.h's AllPoliciesAreRepair static_assert
  // enforces it, since kReject is declared but not handled below -- so this
  // is always populated for a reported violation.
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

// A configured WebGL identity string whose pair is absent. Unlike a Violation
// (two present keys disagreeing on a value), this is a PRESENCE incoherence:
// one of {renderer, vendor} for an API is configured and the other is left to
// leak this machine's real value. There is no value to substitute -- repairing
// would mean inventing the missing string -- so the report names the two keys
// and asks the operator to set both or neither.
struct PairingViolation {
  std::string present_key;  // the channel the operator configured
  std::string absent_key;   // its pair, which still reports the real value
};

// Pure pairing check: given whether each side of an API's {renderer, vendor}
// pair resolves, returns a violation when EXACTLY ONE does, naming the present
// key and the absent one. nullopt when both resolve or neither does. Reads no
// configuration -- factored out from ValidatePairing so the both-or-none branch
// (a security decision: == vs != silently disables or over-fires the check)
// is testable with literals, exactly as CheckDomain is for ValidateDomains.
std::optional<PairingViolation> CheckPairing(bool renderer_resolves,
                                             bool vendor_resolves,
                                             std::string_view renderer_key,
                                             std::string_view vendor_key);

// Reads the configuration and reports each API (webGl, webGl2) whose renderer
// and vendor are not both-present-or-both-absent. "Resolves" mirrors the
// getParameter() consumer's FULL resolution (webgl_rendering_context_base.cc,
// sp3b): the dedicated key OR a string entry in the parameters table at the
// pname. Design sp3-webgl-canvas-design.md:256-257 and :283 make the validator
// the owner of this pairing; a renderer without its vendor is invalid config.
std::vector<PairingViolation> ValidatePairing(const ConfigScope& scope);

// Called once from the browser process before any renderer exists. Returns
// false when startup must be refused.
//
// It does not branch on `policy` at all -- only on CAMOU_CONFIG_STRICT.
// Every entry in the registry is Policy::kRepair; invariants.h static_asserts
// that, so a Policy::kReject entry fails the build instead of being silently
// read and reported as though it were kRepair. Under strict mode every
// violation refuses startup; otherwise every violation is reported loudly
// and none of them is applied.
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

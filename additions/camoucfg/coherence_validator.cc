// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/coherence_validator.h"

#include <memory>
#include <optional>

#include "base/environment.h"
#include "base/logging.h"
#include "components/camoucfg/derive.h"
#include "components/camoucfg/invariants.h"
#include "components/camoucfg/keys.h"

namespace camoucfg {
namespace {

OsFamily OsFamilyOfKey(const ConfigScope& scope, std::string_view key) {
  std::optional<std::string> value = GetString(scope, key);
  if (!value.has_value()) {
    return OsFamily::kUnknown;
  }
  // Which reading applies is a property of the key, not of the text. osInfo
  // holds a user-agent OS segment and platform holds a UA-CH token; guessing
  // from the string would make "Linux" ambiguous between the two, since it is
  // a valid value of one and a substring of the other.
  return key == keys::kUaOsInfo ? OsFamilyFromOsInfo(*value)
                                : OsFamilyFromUaChPlatform(*value);
}

// A key that is absent, or present but unrecognised, constrains nothing.
//
// That is deliberate and worth stating, because "unrecognised" looks like
// something a validator should complain about. This entry's job is catching
// values that CONTRADICT each other. An absent key constrains nothing FOR
// THIS RELATIONAL ENTRY -- the incoherence an absent partner creates (one
// channel spoofed, the other silently reporting the real OS) is reported by
// the startup diagnostic in content/browser/browser_main_loop.cc, not here.
// An unrecognised value is a per-key type question rather than a relational
// one -- SP5b's to reject, not this entry's to guess about. Treating an
// unparseable string as a disagreement would make the validator report a
// contradiction it cannot actually demonstrate.
std::vector<Violation> CheckSameOsFamily(const ConfigScope& scope,
                                         const invariants::Invariant& inv) {
  OsFamily first = OsFamilyOfKey(scope, inv.keys[0]);
  OsFamily second = OsFamilyOfKey(scope, inv.keys[1]);
  if (first == OsFamily::kUnknown || second == OsFamily::kUnknown ||
      first == second) {
    return {};
  }

  // keys[0] is authoritative. For this entry that is ua:osInfo, which lands in
  // the user-agent string -- the surface a detector reads first -- so naming
  // the other as the one to change minimises the difference from what pages
  // already see.
  Violation v;
  v.invariant_id = inv.id;
  v.authoritative_key = std::string(inv.keys[0]);
  v.repaired_key = std::string(inv.keys[1]);
  v.old_value = GetString(scope, inv.keys[1]).value_or(std::string());
  v.new_value = std::string(CanonicalUaChPlatformFor(first));
  return {v};
}

}  // namespace

std::vector<Violation> Validate(const ConfigScope& scope) {
  std::vector<Violation> violations;
  for (const invariants::Invariant& inv : invariants::kAllInvariants) {
    switch (inv.relation) {
      case invariants::Relation::kSameOsFamily: {
        std::vector<Violation> found = CheckSameOsFamily(scope, inv);
        violations.insert(violations.end(), found.begin(), found.end());
        break;
      }
    }
  }
  return violations;
}

bool ValidateAtStartup(const ConfigScope& scope) {
  std::vector<Violation> violations = Validate(scope);
  if (violations.empty()) {
    return true;
  }

  std::unique_ptr<base::Environment> env = base::Environment::Create();
  const bool strict = env->GetVar("CAMOU_CONFIG_STRICT").has_value();

  for (const Violation& v : violations) {
    // The message says what is true: the value is wrong and it has NOT been
    // changed. Applying repairs needs a write path into the cached
    // configuration, which is a change to a component three sub-projects
    // depend on and gets its own task and its own tests.
    //
    // The function is called ValidateAtStartup and not
    // ValidateAndRepairAtStartup for the same reason. A name that claims an
    // action it does not perform is the failure this project has counted
    // repeatedly, and it is worse in an identifier than in a log line because
    // it misleads at the call site rather than at the console.
    LOG(ERROR) << "camoucfg: invariant '" << v.invariant_id << "' violated. '"
               << v.repaired_key << "' is '" << v.old_value
               << "', which disagrees with '" << v.authoritative_key
               << "'. It should be '" << v.new_value
               << "'. Not repaired: set it yourself, or set "
                  "CAMOU_CONFIG_STRICT=1 to refuse startup instead of running "
                  "an incoherent fingerprint.";
  }
  return !strict;
}

}  // namespace camoucfg

// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/coherence_validator.h"

#include <array>
#include <memory>
#include <optional>
#include <set>
#include <string>
#include <string_view>

#include "base/environment.h"
#include "base/files/file_path.h"
#include "base/files/file_util.h"
#include "base/json/json_reader.h"
#include "base/path_service.h"
#include "components/camoucfg/invariants.h"
#include "components/camoucfg/keys.h"
#include "components/camoucfg/mask_config.h"
#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg {
namespace {

using invariants::kAllInvariants;

// --- Guard tests: what makes the registry trustworthy at all ---

// A registry that has drifted from the code enforcing it is worse than no
// registry, because it reads as coverage while providing none. Until SP6a
// generates the header from the JSON, this is what keeps the two in step.
TEST(CoherenceValidatorTest, RegistryMatchesGeneratedHeader) {
  base::FilePath root;
  ASSERT_TRUE(base::PathService::Get(base::DIR_SRC_TEST_DATA_ROOT, &root));
  base::FilePath json = root.AppendASCII("components")
                            .AppendASCII("camoucfg")
                            .AppendASCII("invariants.json");
  std::string raw;
  ASSERT_TRUE(base::ReadFileToString(json, &raw)) << json;

  std::optional<base::DictValue> parsed =
      base::JSONReader::ReadDict(raw, base::JSON_PARSE_RFC);
  ASSERT_TRUE(parsed.has_value());
  const base::ListValue* entries = parsed->FindList("invariants");
  ASSERT_TRUE(entries);

  std::set<std::string> in_json;
  for (const base::Value& entry : *entries) {
    const std::string* id = entry.GetDict().FindString("id");
    ASSERT_TRUE(id);
    in_json.insert(*id);
  }
  std::set<std::string> in_header;
  for (const invariants::Invariant& inv : kAllInvariants) {
    in_header.insert(std::string(inv.id));
  }
  EXPECT_EQ(in_json, in_header);
}

// Found while writing the registry, not planned: an entry naming a key that
// does not exist in keys.h is SILENT. The validator asks for it, gets nullopt,
// treats the key as absent, and skips it -- so the entry reads as protection
// and provides none. That is the registry's own version of the failure it
// exists to prevent, and it costs four lines to close.
TEST(CoherenceValidatorTest, EveryInvariantKeyIsDeclaredInTheRegistry) {
  std::set<std::string_view> declared(keys::kAllKeys.begin(),
                                      keys::kAllKeys.end());
  for (const invariants::Invariant& inv : kAllInvariants) {
    for (std::string_view key : inv.keys) {
      EXPECT_TRUE(declared.count(key))
          << "invariant '" << inv.id << "' names an undeclared key: " << key;
    }
  }
}

TEST(CoherenceValidatorTest, EveryInvariantIdIsUnique) {
  std::set<std::string_view> seen;
  for (const invariants::Invariant& inv : kAllInvariants) {
    EXPECT_TRUE(seen.insert(inv.id).second) << "duplicate id: " << inv.id;
  }
  EXPECT_EQ(seen.size(), kAllInvariants.size());
}

// --- The mutation harness ---
//
// Verification item 1: a registry entry with no passing mutation test is
// documentation, not enforcement. The loop over kAllInvariants below makes
// that structural rather than diligent -- an entry added to the registry with
// no mutation defined here fails MutationsExistForEveryInvariant, so the gap
// cannot happen quietly.

struct Mutation {
  std::string_view invariant_id;
  std::string_view config;           // violates exactly this invariant
  std::string_view expect_repaired;  // the key the validator should name
};

constexpr std::array<Mutation, 1> kMutations = {{
    {"ua-os-family-agrees",
     R"({"ua:osInfo":"Windows NT 10.0; Win64; x64","ua:platform":"Linux"})",
     "ua:platform"},
}};

TEST(CoherenceValidatorTest, MutationsExistForEveryInvariant) {
  for (const invariants::Invariant& inv : kAllInvariants) {
    bool found = false;
    for (const Mutation& m : kMutations) {
      found = found || m.invariant_id == inv.id;
    }
    EXPECT_TRUE(found) << "no mutation defined for invariant: " << inv.id;
  }
}

// Each configuration-dependent case runs in its OWN PROCESS. camoucfg::Config()
// reads the environment once and caches it in a function-local static
// (mask_config.cc:18), so several differently-configured cases in one binary
// would all see whichever configuration latched first -- and the later ones
// would pass or fail for reasons having nothing to do with what they assert.
// The runner supplies CAMOU_CONFIG and CAMOUCFG_TEST_INVARIANT per invocation.
TEST(CoherenceValidatorTest, MutationIsCaughtAndNothingElseIs) {
  std::unique_ptr<base::Environment> env = base::Environment::Create();
  std::optional<std::string> which = env->GetVar("CAMOUCFG_TEST_INVARIANT");
  ASSERT_TRUE(which.has_value())
      << "set CAMOUCFG_TEST_INVARIANT and CAMOU_CONFIG; this case is driven "
         "one process per mutation because the config latches per process";

  const Mutation* mutation = nullptr;
  for (const Mutation& m : kMutations) {
    if (m.invariant_id == *which) {
      mutation = &m;
    }
  }
  ASSERT_TRUE(mutation) << "no mutation named " << *which;

  // Exactly one, and exactly the right one. An entry that also fires on an
  // unrelated corruption is as useless as one that never fires: it would make
  // every future violation report look like this one.
  std::vector<Violation> violations = Validate(GlobalScope());
  ASSERT_EQ(violations.size(), 1u);
  EXPECT_EQ(violations[0].invariant_id, mutation->invariant_id);
  EXPECT_EQ(violations[0].repaired_key, mutation->expect_repaired);
}

// Without this, a validator that reported a violation unconditionally would
// pass every test above. Also driven with an explicit CAMOU_CONFIG, for the
// latching reason given above.
TEST(CoherenceValidatorTest, CleanConfigProducesNoViolations) {
  EXPECT_TRUE(Validate(GlobalScope()).empty());
}

}  // namespace
}  // namespace camoucfg

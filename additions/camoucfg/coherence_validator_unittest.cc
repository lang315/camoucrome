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
//
// Comparing `id` sets is not enough: it would pass a JSON edited to swap
// `keys` order (which surface is authoritative), or one whose `relation` or
// `policy` string no longer matches the header's enum, or one with a
// duplicate entry masking a missing one (set equality hides a count
// mismatch). So this compares every field, `keys` element-by-element and IN
// ORDER -- keys[0] is authoritative per invariants.h -- and asserts the
// entry counts match before comparing entries at all.
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

  // A JSON entry with no header counterpart, or vice versa, must fail even
  // if every entry that IS matched by id agrees field-for-field.
  ASSERT_EQ(entries->size(), kAllInvariants.size());

  // The loop below matches JSON -> header only, so on its own it cannot
  // notice a header entry that nothing in the JSON ever matched: two JSON
  // entries with a duplicate id both resolve to the same header entry and
  // compare clean, the sizes are equal (checked above), and a genuinely new
  // header entry is never looked at. Recording which header ids were
  // actually matched, and asserting that set covers every header entry,
  // closes that -- and as a side effect covers JSON-side id uniqueness too,
  // since a duplicate JSON id can only ever add one id to this set.
  std::set<std::string> matched_ids;

  for (const base::Value& entry : *entries) {
    const base::DictValue& dict = entry.GetDict();
    const std::string* id = dict.FindString("id");
    ASSERT_TRUE(id);

    const invariants::Invariant* header_entry = nullptr;
    for (const invariants::Invariant& inv : kAllInvariants) {
      if (inv.id == *id) {
        header_entry = &inv;
      }
    }
    ASSERT_TRUE(header_entry) << "id in JSON but not in header: " << *id;
    matched_ids.insert(*id);

    const base::ListValue* json_keys = dict.FindList("keys");
    ASSERT_TRUE(json_keys) << *id;
    ASSERT_EQ(json_keys->size(), header_entry->keys.size()) << *id;
    size_t index = 0;
    for (const base::Value& key_value : *json_keys) {
      const std::string* key = key_value.GetIfString();
      ASSERT_TRUE(key) << *id;
      EXPECT_EQ(*key, header_entry->keys[index])
          << *id << " keys[" << index << "]";
      ++index;
    }

    const std::string* relation = dict.FindString("relation");
    ASSERT_TRUE(relation) << *id;
    if (*relation == "same-os-family") {
      EXPECT_EQ(header_entry->relation, invariants::Relation::kSameOsFamily)
          << *id;
    } else if (*relation == "fits-within") {
      EXPECT_EQ(header_entry->relation, invariants::Relation::kFitsWithin)
          << *id;
    } else if (*relation == "same-platform-bucket") {
      EXPECT_EQ(header_entry->relation,
                invariants::Relation::kSamePlatformBucket)
          << *id;
    } else {
      ADD_FAILURE() << *id << " has a relation this test does not know: "
                    << *relation;
    }

    const std::string* policy = dict.FindString("policy");
    ASSERT_TRUE(policy) << *id;
    if (*policy == "repair") {
      EXPECT_EQ(header_entry->policy, invariants::Policy::kRepair) << *id;
    } else if (*policy == "reject") {
      EXPECT_EQ(header_entry->policy, invariants::Policy::kReject) << *id;
    } else {
      ADD_FAILURE() << *id << " has a policy this test does not know: "
                    << *policy;
    }
  }

  // A JSON with a duplicate id (e.g. two "ua-os-family-agrees" entries)
  // alongside a header that gained a genuinely new entry would still pass
  // the size check above and every per-entry comparison in the loop -- both
  // JSON entries just resolve to the same header entry. This is what
  // actually notices the missing header entry, and it also covers JSON-side
  // id uniqueness: a duplicate JSON id can add at most one id to the set.
  EXPECT_EQ(matched_ids.size(), kAllInvariants.size());
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

constexpr std::array<Mutation, 4> kMutations = {{
    {"ua-os-family-agrees",
     R"({"ua:osInfo":"Windows NT 10.0; Win64; x64","ua:platform":"Linux"})",
     "ua:platform"},
    // availWidth > width: a work area wider than the display containing it.
    // Sets only the width axis, so screen-avail-height-fits stays absent and
    // exactly one violation is produced. Numbers, not strings -- GetUint32
    // wants a JSON integer.
    {"screen-avail-width-fits",
     R"({"screen.width":1920,"screen.availWidth":2560})",
     "screen.availWidth"},
    {"screen-avail-height-fits",
     R"({"screen.height":1080,"screen.availHeight":1440})",
     "screen.availHeight"},
    // A Windows UA beside an explicit macOS navigator.platform. ua:platform is
    // absent, so ua-os-family-agrees stays silent and exactly one violation is
    // produced -- navigator.platform, which should be "Win32".
    {"navigator-platform-matches-os",
     R"({"ua:osInfo":"Windows NT 10.0; Win64; x64","navigator.platform":"MacIntel"})",
     "navigator.platform"},
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

  // The runner drives this case with CAMOU_CONFIG set from its OWN bash copy of
  // the config, keyed by the same id. Pinning it against kMutations' copy makes
  // the two config lists a verified mirror rather than two hand-kept copies
  // that drift silently -- mutation->config is read by nothing else, so without
  // this the C++ config strings are dead data and the comment beside them
  // ("violates exactly this invariant") is unchecked.
  ASSERT_EQ(env->GetVar("CAMOU_CONFIG").value_or(std::string()),
            std::string(mutation->config));

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
//
// The comment above always claimed this runs with an explicit config; nothing
// enforced it. Run bare -- no CAMOU_CONFIG -- both keys resolve kUnknown,
// Validate() has nothing to compare, and the EXPECT_TRUE below passed anyway,
// against a validator that was never actually exercised. The assertion below
// fails closed on that case instead.
TEST(CoherenceValidatorTest, CleanConfigProducesNoViolations) {
  // Both keys, not just kUaOsInfo -- asserting one resolved would let a
  // config that only sets kUaOsInfo satisfy this test without CheckSameOsFamily
  // ever comparing two present values, since OsFamilyOfKey(kUnknown) short-
  // circuits Validate() to "no violations" for the wrong reason.
  ASSERT_TRUE(GetString(GlobalScope(), keys::kUaOsInfo).has_value())
      << "run with CAMOU_CONFIG set to a coherent configuration; see the "
         "runner";
  ASSERT_TRUE(GetString(GlobalScope(), keys::kUaPlatform).has_value())
      << "run with CAMOU_CONFIG set to a coherent configuration; see the "
         "runner";
  // The coherent config sets the screen cluster with availWidth == width and
  // availHeight == height -- the real no-taskbar state, which the fits-within
  // relation must accept (it fires only on strictly greater). Asserting the
  // four keys resolved, exactly as the UA keys above are asserted, keeps that
  // coverage from silently vanishing if a screen key in the runner's COHERENT
  // config is typo'd: without this, a mistyped key would leave the geometry
  // relation with nothing to compare and this test would pass having never
  // exercised the equality boundary at all.
  ASSERT_TRUE(GetUint32(GlobalScope(), keys::kScreenWidth).has_value())
      << "coherent config must set screen.width; see the runner";
  ASSERT_TRUE(GetUint32(GlobalScope(), keys::kScreenHeight).has_value())
      << "coherent config must set screen.height; see the runner";
  ASSERT_TRUE(GetUint32(GlobalScope(), keys::kScreenAvailWidth).has_value())
      << "coherent config must set screen.availWidth; see the runner";
  ASSERT_TRUE(GetUint32(GlobalScope(), keys::kScreenAvailHeight).has_value())
      << "coherent config must set screen.availHeight; see the runner";
  // Presence is not enough: this test claims to exercise the equality boundary
  // (availWidth == width, the no-taskbar state fits-within must accept), and a
  // config with availWidth simply < width would pass identically without ever
  // testing it. Pin equality so the boundary is actually the thing under test
  // -- the control is only useful if the two sides are guaranteed equal.
  ASSERT_EQ(*GetUint32(GlobalScope(), keys::kScreenAvailWidth),
            *GetUint32(GlobalScope(), keys::kScreenWidth));
  ASSERT_EQ(*GetUint32(GlobalScope(), keys::kScreenAvailHeight),
            *GetUint32(GlobalScope(), keys::kScreenHeight));
  // The coherent config sets navigator.platform to "Win32", the canonical
  // reduced platform of the Windows ua:osInfo above, so this test exercises the
  // same-platform-bucket relation at its coherent boundary. Without the key
  // set, CheckSamePlatformBucket short-circuits on an absent navigator.platform
  // and this test would pass having never compared the two -- the same vacuous
  // pass the UA and screen assertions above guard against.
  ASSERT_TRUE(GetString(GlobalScope(), keys::kNavigatorPlatform).has_value())
      << "coherent config must set navigator.platform; see the runner";
  EXPECT_TRUE(Validate(GlobalScope()).empty());
}

// --- WebGL renderer/vendor pairing ---
//
// CheckPairing is pure (it reads no configuration), so these run in a plain
// filter, one process for all of them, and assert the both-or-none branch with
// literals -- the same split domain_validator draws between the pure CheckDomain
// (unit-tested here) and the config-reading ValidateDomains (exercised on the
// box). The config-reading half, ValidatePairing -- including the parameters-
// table resolution and the strict-refusal wiring -- is proven end-to-end by
// verify_webgl_pairing.py, where a real getParameter() read confirms the
// resolution mirrors the consumer.

TEST(PairingTest, RendererWithoutVendorNamesVendorAbsent) {
  std::optional<PairingViolation> v = CheckPairing(
      /*renderer_resolves=*/true, /*vendor_resolves=*/false,
      keys::kWebGlRenderer, keys::kWebGlVendor);
  ASSERT_TRUE(v.has_value());
  EXPECT_EQ(v->present_key, keys::kWebGlRenderer);
  EXPECT_EQ(v->absent_key, keys::kWebGlVendor);
}

TEST(PairingTest, VendorWithoutRendererNamesRendererAbsent) {
  std::optional<PairingViolation> v = CheckPairing(
      /*renderer_resolves=*/false, /*vendor_resolves=*/true,
      keys::kWebGlRenderer, keys::kWebGlVendor);
  ASSERT_TRUE(v.has_value());
  EXPECT_EQ(v->present_key, keys::kWebGlVendor);
  EXPECT_EQ(v->absent_key, keys::kWebGlRenderer);
}

TEST(PairingTest, BothResolvedIsCoherent) {
  EXPECT_FALSE(CheckPairing(/*renderer_resolves=*/true,
                            /*vendor_resolves=*/true, keys::kWebGlRenderer,
                            keys::kWebGlVendor)
                   .has_value());
}

TEST(PairingTest, NeitherResolvedIsCoherent) {
  // The unconfigured case: nothing is spoofed, so there is nothing to pair.
  EXPECT_FALSE(CheckPairing(/*renderer_resolves=*/false,
                            /*vendor_resolves=*/false, keys::kWebGlRenderer,
                            keys::kWebGlVendor)
                   .has_value());
}

// --- WebGL capability <-> identity presence ---
//
// CapabilityLeaksIdentity is pure (reads no configuration), so like PairingTest
// these run in a plain filter with literals. The config-reading half
// (ValidateCapabilityIdentity, and the type-aware presence getters it calls) is
// proven end-to-end by verify_webgl_capability_identity.py, where a real
// getParameter() read confirms the leak and its presence semantics.

TEST(CapabilityIdentityTest, CapabilityWithBothIdentityAbsentLeaks) {
  EXPECT_TRUE(CapabilityLeaksIdentity(/*capability_configured=*/true,
                                      /*renderer_resolves=*/false,
                                      /*vendor_resolves=*/false));
}

TEST(CapabilityIdentityTest, PartialIdentityIsThePairingChecksToReport) {
  // Exactly one identity string resolving is ValidatePairing's to report, not
  // this entry's -- so this gate stays closed in both directions.
  EXPECT_FALSE(CapabilityLeaksIdentity(/*capability_configured=*/true,
                                       /*renderer_resolves=*/true,
                                       /*vendor_resolves=*/false));
  EXPECT_FALSE(CapabilityLeaksIdentity(/*capability_configured=*/true,
                                       /*renderer_resolves=*/false,
                                       /*vendor_resolves=*/true));
}

TEST(CapabilityIdentityTest, CapabilityWithFullIdentityIsCoherent) {
  EXPECT_FALSE(CapabilityLeaksIdentity(/*capability_configured=*/true,
                                       /*renderer_resolves=*/true,
                                       /*vendor_resolves=*/true));
}

TEST(CapabilityIdentityTest, NoCapabilityNeverLeaks) {
  // Identity absent but nothing spoofed: the one-directional rule -- identity
  // without capabilities is the fork's own simple spoof, not this entry's.
  EXPECT_FALSE(CapabilityLeaksIdentity(/*capability_configured=*/false,
                                       /*renderer_resolves=*/false,
                                       /*vendor_resolves=*/false));
}

}  // namespace
}  // namespace camoucfg

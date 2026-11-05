// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/observe_match.h"

#include <algorithm>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

#include "base/values.h"
#include "components/camoucfg/observe_body.h"
#include "components/camoucfg/observe_golden_test_util.h"
#include "components/camoucfg/observe_leaf.h"
#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg::observe {

TEST(ObserveMatchTest, GoldenHttpMatchParity) {
  base::DictValue g = ObserveGolden();
  const base::DictValue& truth = *g.FindDict("truth");
  int hits = 0;
  for (const base::Value& c : *g.FindList("http")) {
    const base::DictValue& d = c.GetDict();
    SCOPED_TRACE(*d.FindString("name"));
    BodyFields f = Fields(FromB64(*d.FindString("b64")), *d.FindString("ct"),
                          true, nullptr);
    std::vector<std::tuple<std::string, std::string, std::string, bool>> got;
    std::vector<std::pair<std::string, std::string>> bools;
    for (const auto& [path, leaf] : f.fields) {
      for (const Hit& h : Match(leaf, truth)) {
        got.emplace_back(path, h.surface, h.encoding, h.weak);
      }
      for (const std::string& s : BoolMatches(leaf, truth)) {
        bools.emplace_back(path, s);
      }
    }
    std::sort(got.begin(), got.end());
    std::sort(bools.begin(), bools.end());
    std::vector<std::tuple<std::string, std::string, std::string, bool>> want;
    for (const base::Value& m : *d.FindList("matches")) {
      const base::ListValue& l = m.GetList();
      want.emplace_back(l[0].GetString(), l[1].GetString(), l[2].GetString(),
                        l[3].GetBool());
    }
    std::sort(want.begin(), want.end());
    EXPECT_EQ(got, want);
    EXPECT_EQ(bools, PathClassPairs(*d.FindList("bools")));
    hits += got.size();
  }
  EXPECT_GE(hits, 10);  // every encoding appears in the golden file
}

// Not a divergence after all (found at compile time): base::NumberToString
// writes 1e+16 like Python's str(1e16), so the string form matches.
TEST(ObserveMatchTest, LargeFloatReprMatchesPython) {
  base::DictValue truth;
  truth.Set("x", 1e16);
  const std::vector<Hit> hits = Match(Leaf::Str("1e+16"), truth);
  ASSERT_EQ(hits.size(), 1u);
  EXPECT_EQ(hits[0].encoding, "str");
}

TEST(ObserveMatchTest, SkippedValues) {
  base::DictValue truth;
  truth.Set("a", "");
  truth.Set("b", 0);
  Leaf b;
  b.type = Leaf::Type::kBool;
  EXPECT_TRUE(Match(b, truth).empty());
  EXPECT_TRUE(Match(Leaf::Str(""), truth).empty());
  EXPECT_TRUE(Match(Leaf::Opaque(4), truth).empty());
}

}  // namespace camoucfg::observe

// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/keys.h"

#include <set>
#include <string_view>

#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg::keys {
namespace {

// The failure this guards against is a constant whose NAME is new but whose
// VALUE duplicates another. Two call sites then read the same key while
// appearing to read different ones, which no compiler or reviewer catches and
// which produces a surface that silently follows the wrong knob.
TEST(CamoucfgKeysTest, EveryKeyIsUnique) {
  std::set<std::string_view> seen;
  for (std::string_view key : kAllKeys) {
    EXPECT_TRUE(seen.insert(key).second) << "duplicate key value: " << key;
  }
  EXPECT_EQ(seen.size(), kAllKeys.size());
}

// Conventions: a key uses a dot when it mirrors a JavaScript property path and
// a colon when it names a synthetic namespace. Either way it carries at least
// one separator, and a key that carries neither is a bare word that will
// collide with a future namespace.
TEST(CamoucfgKeysTest, EveryKeyIsNamespaced) {
  for (std::string_view key : kAllKeys) {
    EXPECT_NE(key.find_first_of(".:"), std::string_view::npos)
        << "key is not namespaced: " << key;
    EXPECT_EQ(key.find(' '), std::string_view::npos)
        << "key contains a space: " << key;
    EXPECT_FALSE(key.empty());
  }
}

}  // namespace
}  // namespace camoucfg::keys

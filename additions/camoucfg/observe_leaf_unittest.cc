// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/observe_leaf.h"

#include <optional>
#include <string>
#include <utility>

#include "base/values.h"
#include "components/camoucfg/observe_golden_test_util.h"
#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg::observe {

TEST(ObserveLeafTest, ValueClassMatchesPython) {
  EXPECT_EQ(ValueClass(Leaf::Opaque(300)), "opaque<300>");
  Leaf b; b.type = Leaf::Type::kBool;
  EXPECT_EQ(ValueClass(b), "bool");
  EXPECT_EQ(ValueClass(Leaf()), "null");
  EXPECT_EQ(ValueClass(Leaf::FromValue(base::Value(8))), "int");
  EXPECT_EQ(ValueClass(Leaf::FromValue(base::Value(12345678901.0))), "id");
  EXPECT_EQ(ValueClass(Leaf::FromValue(base::Value(1.5))), "float");
  EXPECT_EQ(ValueClass(Leaf::Str("1234567890")), "id");
  EXPECT_EQ(ValueClass(Leaf::Str("1234567890\n")), "id");  // Python's $ allows one trailing newline
  EXPECT_EQ(ValueClass(Leaf::Str("123456789")), "str<9>");
  EXPECT_EQ(ValueClass(Leaf::Str("\xC3\xA9t\xC3\xA9")), "str<3>");  // code points, not bytes
}

TEST(ObserveLeafTest, GoldenBase64Parity) {
  for (const base::Value& c : *ObserveGolden().FindList("b64")) {
    const base::DictValue& d = c.GetDict();
    SCOPED_TRACE(*d.FindString("in"));
    std::optional<std::string> got = B64DecodeStrict(*d.FindString("in"));
    const std::string* want = d.FindString("out_b64");
    ASSERT_EQ(got.has_value(), want != nullptr);
    if (want) EXPECT_EQ(*got, FromB64(*want));
  }
}

TEST(ObserveLeafTest, PyStripUsesPythonWhitespace) {
  EXPECT_EQ(PyStrip("\xC2\xA0 abc\xE3\x80\x80\n"), "abc");
  EXPECT_EQ(PyLStrip("\x1c{x"), "{x");
}

TEST(ObserveLeafTest, ParseJsonContainerOnlyDictOrList) {
  EXPECT_TRUE(ParseJsonContainer("{\"a\":1}"));
  EXPECT_TRUE(ParseJsonContainer(" [1] "));
  EXPECT_FALSE(ParseJsonContainer("1"));
  EXPECT_FALSE(ParseJsonContainer("\"x\""));
  EXPECT_FALSE(ParseJsonContainer("{a:1}"));
}

}  // namespace camoucfg::observe

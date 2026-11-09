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

// base::Value keeps no int/float token kind: INTEGER is a Python int, an
// integral DOUBLE below 2^31 had a decimal point (float), from 2^31 a big int.
TEST(ObserveLeafTest, NumberClassification) {
  const Leaf two = Leaf::FromValue(base::Value(2.0));
  EXPECT_EQ(two.type, Leaf::Type::kFloat);
  EXPECT_EQ(PyNumStr(two), "2.0");
  EXPECT_EQ(ValueClass(two), "float");
  EXPECT_EQ(PyNumStr(Leaf::FromValue(base::Value(1.25))), "1.25");
  EXPECT_EQ(PyNumStr(Leaf::FromValue(base::Value(1e-5))), "1e-05");
  EXPECT_EQ(PyNumStr(Leaf::FromValue(base::Value(1e15 + 0.5))), "1000000000000000.5");
  EXPECT_EQ(PyNumStr(Leaf::FromValue(base::Value(8))), "8");

  const Leaf above = Leaf::FromValue(base::Value(2147483648.0));
  EXPECT_EQ(above.type, Leaf::Type::kInt);
  EXPECT_EQ(ValueClass(above), "id");
  EXPECT_EQ(PyNumStr(above), "2147483648");
  const Leaf mid = Leaf::FromValue(base::Value(1e15));
  EXPECT_EQ(mid.type, Leaf::Type::kInt);
  EXPECT_EQ(ValueClass(mid), "id");
  EXPECT_EQ(PyNumStr(mid), "1000000000000000");
  const Leaf big = Leaf::FromValue(base::Value(1e16));
  EXPECT_EQ(ValueClass(big), "id");
  EXPECT_EQ(PyNumStr(big), "10000000000000000");
  EXPECT_EQ(PyNumStr(Leaf::FromValue(base::Value(-2147483649.0))), "-2147483649");
  // From 1e21 JS writes exponent form: a Python float.
  const Leaf huge = Leaf::FromValue(base::Value(1e21));
  EXPECT_EQ(huge.type, Leaf::Type::kFloat);
  EXPECT_EQ(PyNumStr(huge), "1e+21");
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

// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/observe_blowfish.h"

#include <cstdint>
#include <optional>
#include <string>
#include <utility>

#include "base/check.h"
#include "base/strings/string_number_conversions.h"
#include "base/values.h"
#include "components/camoucfg/observe_golden_test_util.h"
#include "components/camoucfg/observe_leaf.h"
#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg::observe {

namespace {
std::string Hex(std::string_view hex) {
  std::string out;
  CHECK(base::HexStringToString(hex, &out));
  return out;
}
}  // namespace

TEST(ObserveBlowfishTest, InitTablesArePi) {
  EXPECT_EQ(kBlowfishInitP[0], 0x243f6a88u);
  EXPECT_EQ(kBlowfishInitP[17], 0x8979fb1bu);
  EXPECT_EQ(kBlowfishInitS[0][0], 0xd1310ba6u);
  EXPECT_EQ(kBlowfishInitS[3][255], 0x3ac372e6u);
}

TEST(ObserveBlowfishTest, EcbVectors) {
  struct { const char* key; uint64_t plain; uint64_t cipher; } v[] = {
      {"0000000000000000", 0x0000000000000000, 0x4EF997456198DD78},
      {"FFFFFFFFFFFFFFFF", 0xFFFFFFFFFFFFFFFF, 0x51866FD5B85ECB8A},
      {"3000000000000000", 0x1000000000000001, 0x7D856F9A613063F2},
      {"0123456789ABCDEF", 0x1111111111111111, 0x61F9C3802281B096},
      {"FEDCBA9876543210", 0x0123456789ABCDEF, 0x0ACEAB0FC6A0A28D},
  };
  for (const auto& t : v) {
    EXPECT_EQ(BlowfishEncryptBlock(Hex(t.key), t.plain), t.cipher) << t.key;
  }
}

TEST(ObserveBlowfishTest, CbcVector) {
  std::optional<std::string> plain = BlowfishCbcDecrypt(
      Hex("0123456789ABCDEFF0E1D2C3B4A59687"), Hex("FEDCBA9876543210"),
      Hex("6B77B4D63006DEE605B156E27403979358DEB9E7154616D959F1652BD5FF92CC"));
  ASSERT_TRUE(plain);
  EXPECT_EQ(*plain, std::string("7654321 Now is the time for \0\0\0\0", 32));
  EXPECT_FALSE(BlowfishCbcDecrypt(Hex("0123456789ABCDEF"), Hex("FEDCBA9876543210"), "short"));
}

TEST(ObserveSjdTest, GoldenParity) {
  for (const base::Value& c : *ObserveGolden().FindList("sjd")) {
    const base::DictValue& d = c.GetDict();
    SCOPED_TRACE(*d.FindString("name"));
    std::optional<base::DictValue> got = DecodeSjd(*d.FindDict("event"));
    const base::Value* want = d.Find("doc");
    if (want->is_none()) {
      EXPECT_FALSE(got);
    } else {
      ASSERT_TRUE(got);
      EXPECT_EQ(base::Value(std::move(*got)), *want);
    }
  }
}

// Pins a documented divergence, not parity: a container signal value is a str<n> of its JSON length here; Python measures its repr.
TEST(ObserveSjdTest, ContainerValueIsItsJson) {
  base::DictValue d;
  d.Set("a", 1);
  EXPECT_EQ(ValueClass(Leaf::FromValue(base::Value(std::move(d)))), "str<7>");
}

}  // namespace camoucfg::observe

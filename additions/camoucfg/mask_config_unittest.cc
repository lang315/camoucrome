// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/mask_config_internal.h"

#include <map>
#include <optional>
#include <string>
#include <vector>

#include "base/test/gtest_util.h"
#include "base/values.h"
#include "components/camoucfg/mask_config.h"
#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg::internal {
namespace {

// Builds an environment lookup over a fixed map, so tests never touch the
// real process environment.
auto EnvFrom(const std::map<std::string, std::string>& vars) {
  return [&vars](const std::string& name) -> std::optional<std::string> {
    auto it = vars.find(name);
    if (it == vars.end()) {
      return std::nullopt;
    }
    return it->second;
  };
}

TEST(AssembleRawConfigTest, ReturnsEmptyWhenNothingSet) {
  std::map<std::string, std::string> vars;
  auto env = EnvFrom(vars);
  EXPECT_EQ(AssembleRawConfig(env), "");
}

TEST(AssembleRawConfigTest, ReadsUnnumberedFallback) {
  std::map<std::string, std::string> vars{{"CAMOU_CONFIG", "{\"a\":1}"}};
  auto env = EnvFrom(vars);
  EXPECT_EQ(AssembleRawConfig(env), "{\"a\":1}");
}

TEST(AssembleRawConfigTest, ConcatenatesChunksInIndexOrder) {
  std::map<std::string, std::string> vars{
      {"CAMOU_CONFIG_1", "{\"a\":"},
      {"CAMOU_CONFIG_2", "1,\"b\":"},
      {"CAMOU_CONFIG_3", "2}"},
  };
  auto env = EnvFrom(vars);
  EXPECT_EQ(AssembleRawConfig(env), "{\"a\":1,\"b\":2}");
}

TEST(AssembleRawConfigTest, StopsAtFirstMissingIndex) {
  std::map<std::string, std::string> vars{
      {"CAMOU_CONFIG_1", "one"},
      {"CAMOU_CONFIG_3", "three"},
  };
  auto env = EnvFrom(vars);
  EXPECT_EQ(AssembleRawConfig(env), "one");
}

TEST(AssembleRawConfigTest, NumberedChunksWinOverUnnumbered) {
  std::map<std::string, std::string> vars{
      {"CAMOU_CONFIG", "ignored"},
      {"CAMOU_CONFIG_1", "used"},
  };
  auto env = EnvFrom(vars);
  EXPECT_EQ(AssembleRawConfig(env), "used");
}

// The one case that tells the two candidate semantics apart. The fallback
// fires on the concatenation being empty, not on CAMOU_CONFIG_1 being
// absent, so a present-but-empty chunk still falls through to the
// unnumbered variable. Camoufox's MaskConfig.hpp behaves identically, and
// the byte-compatibility constraint makes that binding: a future change to
// presence-tracking would return "" here and silently diverge from the
// reference on identical environment bytes.
TEST(AssembleRawConfigTest, PresentButEmptyChunkFallsBackToUnnumbered) {
  std::map<std::string, std::string> vars{
      {"CAMOU_CONFIG_1", ""},
      {"CAMOU_CONFIG", "ignored"},
  };
  auto env = EnvFrom(vars);
  EXPECT_EQ(AssembleRawConfig(env), "ignored");
}

TEST(ParseConfigTest, EmptyInputYieldsEmptyDict) {
  base::DictValue dict = ParseConfig("", /*strict=*/false);
  EXPECT_TRUE(dict.empty());
}

TEST(ParseConfigTest, ParsesFlatObject) {
  base::DictValue dict =
      ParseConfig(R"({"navigator.hardwareConcurrency":8})", /*strict=*/false);
  ASSERT_EQ(dict.size(), 1u);
  EXPECT_EQ(dict.FindInt("navigator.hardwareConcurrency"), 8);
}

TEST(ParseConfigTest, MalformedJsonYieldsEmptyDictWhenNotStrict) {
  base::DictValue dict = ParseConfig("{not json", /*strict=*/false);
  EXPECT_TRUE(dict.empty());
}

TEST(ParseConfigTest, NonObjectJsonYieldsEmptyDict) {
  base::DictValue dict = ParseConfig("[1,2,3]", /*strict=*/false);
  EXPECT_TRUE(dict.empty());
}

// The empty-input guard is load-bearing and easy to delete by accident,
// because EmptyInputYieldsEmptyDict passes without it: ReadDict("") also
// returns nullopt and reaches the same malformed branch. The difference
// only shows in strict mode, where losing the guard would CHECK-abort
// every ordinary unconfigured launch. This is the one test that fails if
// the guard goes away.
TEST(ParseConfigTest, EmptyInputIsNotAnErrorEvenInStrictMode) {
  base::DictValue dict = ParseConfig("", /*strict=*/true);
  EXPECT_TRUE(dict.empty());
}

// EXPECT_CHECK_DEATH_WITH rather than a bare EXPECT_DEATH matching the
// message. base/test/gtest_util.h branches on CHECK_WILL_STREAM(): in build
// configurations that strip CHECK message text it degrades to matching "",
// so a hand-written EXPECT_DEATH(..., "camoucfg") would fail there and read
// as a defect in the code rather than in the assertion.
TEST(ParseConfigDeathTest, MalformedJsonAbortsWhenStrict) {
  EXPECT_CHECK_DEATH_WITH(ParseConfig("{not json", /*strict=*/true),
                          "camoucfg");
}

base::DictValue Fixture() {
  return ParseConfig(R"({
    "s": "text",
    "u": 8,
    "neg": -3,
    "d": 1.5,
    "b": true,
    "list": ["a", "b"],
    "mixed": ["a", 1]
  })",
                     /*strict=*/false);
}

TEST(GettersTest, ReadCorrectTypes) {
  base::DictValue cfg = Fixture();
  EXPECT_EQ(GetStringFrom(cfg, "s"), "text");
  EXPECT_EQ(GetUint32From(cfg, "u"), 8u);
  EXPECT_EQ(GetInt32From(cfg, "neg"), -3);
  EXPECT_EQ(GetDoubleFrom(cfg, "d"), 1.5);
  EXPECT_EQ(GetBoolFrom(cfg, "b"), true);
  EXPECT_EQ(GetStringListFrom(cfg, "list"),
            (std::vector<std::string>{"a", "b"}));
  EXPECT_TRUE(HasKeyIn(cfg, "s"));
}

TEST(GettersTest, AbsentKeysAreSilentlyEmpty) {
  base::DictValue cfg = Fixture();
  EXPECT_FALSE(GetStringFrom(cfg, "missing").has_value());
  EXPECT_FALSE(GetUint32From(cfg, "missing").has_value());
  EXPECT_FALSE(GetInt32From(cfg, "missing").has_value());
  EXPECT_FALSE(GetDoubleFrom(cfg, "missing").has_value());
  EXPECT_FALSE(GetBoolFrom(cfg, "missing").has_value());
  EXPECT_TRUE(GetStringListFrom(cfg, "missing").empty());
  EXPECT_FALSE(HasKeyIn(cfg, "missing"));
}

TEST(GettersTest, WrongTypesReturnEmpty) {
  base::DictValue cfg = Fixture();
  EXPECT_FALSE(GetStringFrom(cfg, "u").has_value());
  EXPECT_FALSE(GetUint32From(cfg, "s").has_value());
  EXPECT_FALSE(GetInt32From(cfg, "s").has_value());
  EXPECT_FALSE(GetDoubleFrom(cfg, "s").has_value());
  EXPECT_FALSE(GetBoolFrom(cfg, "u").has_value());
  EXPECT_TRUE(GetStringListFrom(cfg, "s").empty());
  EXPECT_TRUE(GetStringListFrom(cfg, "mixed").empty());
}

TEST(GettersTest, NegativeIntegerIsNotAnUnsigned) {
  base::DictValue cfg = Fixture();
  EXPECT_FALSE(GetUint32From(cfg, "neg").has_value());
}

TEST(GettersTest, WholeNumberWidensToDouble) {
  base::DictValue cfg = Fixture();
  EXPECT_EQ(GetDoubleFrom(cfg, "u"), 8.0);
}

// GetStringListFrom returns {} for an absent key, a wrong-typed key, and a
// genuinely empty list alike. That collapse is accepted rather than
// accidental: all three mean "no list configured" and the caller falls back
// to the real value either way. A caller that needs to tell them apart has
// HasKeyIn. Pinned so the ambiguity stays a recorded decision.
TEST(GettersTest, ExplicitEmptyListIsEmptyButPresent) {
  base::DictValue cfg = ParseConfig(R"({"empty": []})", /*strict=*/false);
  EXPECT_TRUE(GetStringListFrom(cfg, "empty").empty());
  EXPECT_TRUE(HasKeyIn(cfg, "empty"));
  EXPECT_FALSE(HasKeyIn(cfg, "absent"));
}

// All seven, not a representative sample. std::optional's converting
// constructor means several plausible miswirings compile cleanly: GetDouble
// forwarding to GetInt32From, GetInt32 to GetUint32From, or GetBool to
// HasKeyIn all build without complaint. The last one is the dangerous one --
// HasKeyIn returns false for an absent key, which becomes an *engaged*
// optional(false), so a caller would treat "not configured" as "configured
// to false" and stop falling back to the real value. Asserting every getter
// on an absent key catches exactly that.
TEST(MaskConfigTest, AbsentKeysReturnNullopt) {
  const camoucfg::ConfigScope& scope = camoucfg::GlobalScope();
  EXPECT_FALSE(camoucfg::GetString(scope, "nope.not.here").has_value());
  EXPECT_FALSE(camoucfg::GetUint32(scope, "nope.not.here").has_value());
  EXPECT_FALSE(camoucfg::GetInt32(scope, "nope.not.here").has_value());
  EXPECT_FALSE(camoucfg::GetDouble(scope, "nope.not.here").has_value());
  EXPECT_FALSE(camoucfg::GetBool(scope, "nope.not.here").has_value());
  EXPECT_TRUE(camoucfg::GetStringList(scope, "nope.not.here").empty());
  EXPECT_FALSE(camoucfg::HasKey(scope, "nope.not.here"));
}

}  // namespace
}  // namespace camoucfg::internal

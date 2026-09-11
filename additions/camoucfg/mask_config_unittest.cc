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
#include "components/camoucfg/keys.h"
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

TEST(AssembleRawConfigTest, PrefixSelectsThePresetFamily) {
  std::map<std::string, std::string> env = {{"CAMOU_CONFIG", "config"},
                                            {"CAMOU_PRESET_1", "pre"},
                                            {"CAMOU_PRESET_2", "set"}};
  EXPECT_EQ(AssembleRawConfig(EnvFrom(env), "CAMOU_PRESET"), "preset");
  EXPECT_EQ(AssembleRawConfig(EnvFrom(env)), "config");
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

TEST(GettersTest, GetVoicesParsesObjects) {
  base::DictValue cfg = ParseConfig(R"({"voices:list": [
      {"voiceURI":"urn:x","name":"Alex","lang":"en-US","localService":true,"default":true},
      {"name":"Zira","lang":"en-GB"}
  ]})", /*strict=*/false);
  std::vector<VoiceConfig> v = GetVoicesFrom(cfg, "voices:list");
  ASSERT_EQ(v.size(), 2u);
  EXPECT_EQ(v[0].voice_uri, "urn:x");
  EXPECT_EQ(v[0].name, "Alex");
  EXPECT_EQ(v[0].lang, "en-US");
  EXPECT_TRUE(v[0].is_local_service);
  EXPECT_TRUE(v[0].is_default);
  EXPECT_EQ(v[1].voice_uri, "Zira");   // falls back to name
  EXPECT_FALSE(v[1].is_default);       // default false
  EXPECT_TRUE(v[1].is_local_service);  // default true
}

TEST(GettersTest, GetVoicesEmptyWhenAbsentOrWrongType) {
  base::DictValue a = ParseConfig(R"({})", /*strict=*/false);
  EXPECT_TRUE(GetVoicesFrom(a, "voices:list").empty());
  base::DictValue b = ParseConfig(R"({"voices:list": "notalist"})", /*strict=*/false);
  EXPECT_TRUE(GetVoicesFrom(b, "voices:list").empty());
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

// camoucfg::IsFontAllowed(scope, family) always reads the process-wide
// ParsedConfig() singleton (parsed once, on first use, for the life of the
// binary -- same as every other camoucfg:: getter above), so it cannot be
// driven through three different "fonts" configurations within one test
// binary. IsFontAllowedFrom is the testable core that takes an
// already-parsed base::DictValue instead, the same split GettersTest above
// and gl_params_unittest.cc's GLParamsTest use for exactly this reason.
TEST(IsFontAllowedTest, AbsentKeyAllowsEveryFamily) {
  base::DictValue cfg = ParseConfig("{}", /*strict=*/false);
  EXPECT_TRUE(IsFontAllowedFrom(cfg, "Arial"));
}

TEST(IsFontAllowedTest, PresentListAllowsMembersCaseInsensitively) {
  base::DictValue cfg =
      ParseConfig(R"({"fonts:list": ["Arial", "Helvetica"]})", /*strict=*/false);
  EXPECT_TRUE(IsFontAllowedFrom(cfg, "Arial"));
  EXPECT_TRUE(IsFontAllowedFrom(cfg, "arial"));
  EXPECT_FALSE(IsFontAllowedFrom(cfg, "Calibri"));
}

TEST(IsFontAllowedTest, PresentButEmptyListAllowsNoFamily) {
  base::DictValue cfg = ParseConfig(R"({"fonts:list": []})", /*strict=*/false);
  EXPECT_FALSE(IsFontAllowedFrom(cfg, "Arial"));
}

// Exercises the real public entry point end-to-end, on the one scenario the
// process-wide singleton can safely stand in for: the same "nothing sets
// this key" assumption MaskConfigTest.AbsentKeysReturnNullopt above already
// makes about the test environment.
TEST(IsFontAllowedTest, PublicApiForwardsForTheAbsentCase) {
  EXPECT_TRUE(
      camoucfg::IsFontAllowed(camoucfg::GlobalScope(), "Arial"));
}

}  // namespace
}  // namespace camoucfg::internal

// fonts-iii: the alias map is read case-insensitively on the requested name;
// an absent key, an unknown family or an empty target aliases nothing.
TEST(FontAliasTest, AliasIsCaseInsensitiveAndAbsentAliasesNothing) {
  base::DictValue cfg;
  EXPECT_FALSE(camoucfg::internal::FontAliasFrom(cfg, "Segoe UI").has_value());
  base::DictValue map;
  map.Set("Segoe UI", "Selawik");
  map.Set("Consolas", "Liberation Mono");
  map.Set("Empty", "");
  cfg.Set(camoucfg::keys::kFontsAlias, std::move(map));
  EXPECT_EQ(camoucfg::internal::FontAliasFrom(cfg, "segoe ui"), "Selawik");
  EXPECT_EQ(camoucfg::internal::FontAliasFrom(cfg, "Consolas"), "Liberation Mono");
  EXPECT_FALSE(camoucfg::internal::FontAliasFrom(cfg, "Selawik").has_value());
  EXPECT_FALSE(camoucfg::internal::FontAliasFrom(cfg, "Empty").has_value());
  // src:local() lookups read fonts:aliasLocal only: a family aliased for CSS is
  // not aliased for local() unless that map says so, and vice versa.
  base::DictValue local;
  local.Set("Georgia", "Gelasio Regular");
  local.Set("SegoeUI-Bold", "Selawik Bold");
  cfg.Set(camoucfg::keys::kFontsAliasLocal, std::move(local));
  EXPECT_EQ(camoucfg::internal::FontAliasFrom(cfg, "georgia", true), "Gelasio Regular");
  EXPECT_EQ(camoucfg::internal::FontAliasFrom(cfg, "SegoeUI-Bold", true), "Selawik Bold");
  EXPECT_FALSE(camoucfg::internal::FontAliasFrom(cfg, "Georgia", false).has_value());
  EXPECT_FALSE(camoucfg::internal::FontAliasFrom(cfg, "Segoe UI", true).has_value());
}

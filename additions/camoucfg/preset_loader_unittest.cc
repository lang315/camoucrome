// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/preset_loader.h"

#include <optional>
#include <string>

#include "base/json/json_reader.h"
#include "base/values.h"
#include "components/camoucfg/derive.h"
#include "components/camoucfg/keys.h"
#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg {
namespace {

base::DictValue Preset(const char* json) {
  std::optional<base::DictValue> parsed =
      base::JSONReader::ReadDict(json, base::JSON_PARSE_RFC);
  CHECK(parsed.has_value()) << json;
  return std::move(*parsed);
}

constexpr int kMilestone = 153;

constexpr char kFull[] = R"json({
  "milestone": 153,
  "os": "Windows",
  "platformVersion": "15.0.0",
  "gpu": {
    "vendor": "Google Inc. (NVIDIA)",
    "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002504) Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "parameters": {"3379": 16384, "34921": 16}
  },
  "screen": {"width": 1920, "height": 1080, "availWidth": 1920, "availHeight": 1040},
  "fonts": ["Arial", "Segoe UI"],
  "locale": "en-US",
  "timezone": "America/New_York",
  "dpr": 1.25,
  "sampleRate": 48000,
  "provenance": {"captured": "2026-09-10"}
})json";

// The field -> key table, one assertion per emitted key.
TEST(PresetLoaderTest, FullPresetExpandsToEveryMappedKey) {
  base::DictValue out = ExpandPreset(Preset(kFull), kMilestone);

  EXPECT_EQ(*out.FindString(keys::kUaOsInfo), "Windows NT 10.0; Win64; x64");
  EXPECT_EQ(*out.FindString(keys::kUaPlatform), "Windows");
  EXPECT_EQ(*out.FindString(keys::kUaPlatformVersion), "15.0.0");

  EXPECT_EQ(*out.FindString(keys::kWebGlVendor), "Google Inc. (NVIDIA)");
  EXPECT_EQ(*out.FindString(keys::kWebGl2Vendor), "Google Inc. (NVIDIA)");
  EXPECT_EQ(*out.FindString(keys::kWebGlRenderer),
            *out.FindString(keys::kWebGl2Renderer));
  EXPECT_EQ(out.FindDict(keys::kWebGlParameters)->FindInt("3379"), 16384);
  EXPECT_EQ(out.FindDict(keys::kWebGl2Parameters)->FindInt("34921"), 16);

  EXPECT_EQ(out.FindInt(keys::kScreenWidth), 1920);
  EXPECT_EQ(out.FindInt(keys::kScreenHeight), 1080);
  EXPECT_EQ(out.FindInt(keys::kScreenAvailWidth), 1920);
  EXPECT_EQ(out.FindInt(keys::kScreenAvailHeight), 1040);

  EXPECT_EQ(out.FindList(keys::kFonts)->size(), 2u);

  EXPECT_EQ(*out.FindString(keys::kLocaleTag), "en-US");
  EXPECT_EQ(*out.FindString(keys::kNavigatorLanguage), "en-US");
  const base::ListValue* languages = out.FindList(keys::kNavigatorLanguages);
  ASSERT_EQ(languages->size(), 2u);
  EXPECT_EQ((*languages)[0].GetString(), "en-US");
  EXPECT_EQ((*languages)[1].GetString(), "en");

  EXPECT_EQ(*out.FindString(keys::kTimezoneId), "America/New_York");

  // 3 OS + 6 GPU + 4 screen + 1 fonts + 3 locale + 1 timezone.
  EXPECT_EQ(out.size(), 18u);
}

// What a preset must never turn into a key: the derived, the per-instance,
// and the version-bearing (see the table in preset_loader.cc).
TEST(PresetLoaderTest, DoesNotEmitDerivedOrPerInstanceKeys) {
  base::DictValue out = ExpandPreset(Preset(kFull), kMilestone);
  EXPECT_FALSE(out.contains(keys::kNavigatorPlatform));
  EXPECT_FALSE(out.contains(keys::kNavigatorUserAgent));
  EXPECT_FALSE(out.contains(keys::kScreenColorDepth));
  EXPECT_FALSE(out.contains(keys::kWindowOuterWidth));
  EXPECT_FALSE(out.contains(keys::kCanvasSeed));
  EXPECT_FALSE(out.contains(keys::kAudioSeed));
  EXPECT_FALSE(out.contains(keys::kMediaDevicesSeed));
  EXPECT_FALSE(out.contains("dpr"));
  EXPECT_FALSE(out.contains("sampleRate"));
  EXPECT_FALSE(out.contains("provenance"));
}

TEST(PresetLoaderTest, EmptyPresetExpandsToNothing) {
  EXPECT_TRUE(ExpandPreset(Preset("{}"), kMilestone).empty());
}

TEST(PresetLoaderTest, UnknownOsEmitsNoOsKeys) {
  base::DictValue out =
      ExpandPreset(Preset(R"({"os":"Chromium OS","timezone":"UTC"})"),
                   kMilestone);
  EXPECT_FALSE(out.contains(keys::kUaOsInfo));
  EXPECT_FALSE(out.contains(keys::kUaPlatform));
  EXPECT_EQ(*out.FindString(keys::kTimezoneId), "UTC");
}

TEST(PresetLoaderTest, LocaleWithoutRegionHeadsAOneEntryList) {
  base::DictValue out = ExpandPreset(Preset(R"({"locale":"de"})"), kMilestone);
  const base::ListValue* languages = out.FindList(keys::kNavigatorLanguages);
  ASSERT_EQ(languages->size(), 1u);
  EXPECT_EQ((*languages)[0].GetString(), "de");
}

// A wrong-typed field is skipped, not coerced: "1920" is not a width.
TEST(PresetLoaderTest, WrongTypedFieldIsSkipped) {
  base::DictValue out = ExpandPreset(
      Preset(R"({"screen":{"width":"1920","height":1080},"fonts":"Arial"})"),
      kMilestone);
  EXPECT_FALSE(out.contains(keys::kScreenWidth));
  EXPECT_EQ(out.FindInt(keys::kScreenHeight), 1080);
  EXPECT_FALSE(out.contains(keys::kFonts));
}


// The preset derives ua:osInfo and ua:platform from one field. An explicit
// key for either must re-derive the pair, or ClaimedOs (osInfo first) keeps
// answering with the preset's OS (review 2026-09-24 #7).
TEST(OverridePresetGroupsTest, ExplicitPlatformRederivesOsInfo) {
  base::DictValue expanded = ExpandPreset(Preset(R"({"os": "macOS"})"), kMilestone);
  base::DictValue explicit_cfg;
  explicit_cfg.Set(keys::kUaPlatform, "Windows");
  OverridePresetGroups(expanded, explicit_cfg);
  EXPECT_EQ(*expanded.FindString(keys::kUaOsInfo),
            CanonicalOsInfoFor(OsFamily::kWindows));
  EXPECT_EQ(*expanded.FindString(keys::kUaPlatform), "Windows");
}

TEST(OverridePresetGroupsTest, ExplicitOsInfoRederivesPlatform) {
  base::DictValue expanded = ExpandPreset(Preset(R"({"os": "Windows"})"), kMilestone);
  base::DictValue explicit_cfg;
  explicit_cfg.Set(keys::kUaOsInfo,
                   std::string(CanonicalOsInfoFor(OsFamily::kMac)));
  OverridePresetGroups(expanded, explicit_cfg);
  EXPECT_EQ(*expanded.FindString(keys::kUaPlatform),
            CanonicalUaChPlatformFor(OsFamily::kMac));
}

// Explicit navigator.languages re-derives the preset's language and tag.
TEST(OverridePresetGroupsTest, ExplicitLanguagesRederivesLocale) {
  base::DictValue expanded =
      ExpandPreset(Preset(R"({"locale": "fr-FR"})"), kMilestone);
  base::DictValue explicit_cfg;
  base::ListValue langs;
  langs.Append("de-DE");
  langs.Append("de");
  explicit_cfg.Set(keys::kNavigatorLanguages, std::move(langs));
  OverridePresetGroups(expanded, explicit_cfg);
  EXPECT_EQ(*expanded.FindString(keys::kNavigatorLanguage), "de-DE");
  EXPECT_EQ(*expanded.FindString(keys::kLocaleTag), "de-DE");
}

TEST(OverridePresetGroupsTest, ExplicitLanguageRederivesTheList) {
  base::DictValue expanded =
      ExpandPreset(Preset(R"({"locale": "fr-FR"})"), kMilestone);
  base::DictValue explicit_cfg;
  explicit_cfg.Set(keys::kNavigatorLanguage, "ja-JP");
  OverridePresetGroups(expanded, explicit_cfg);
  const base::ListValue* langs = expanded.FindList(keys::kNavigatorLanguages);
  ASSERT_TRUE(langs);
  ASSERT_EQ(langs->size(), 2u);
  EXPECT_EQ((*langs)[0].GetString(), "ja-JP");
  EXPECT_EQ((*langs)[1].GetString(), "ja");
  EXPECT_EQ(*expanded.FindString(keys::kLocaleTag), "ja-JP");
}

TEST(OverridePresetGroupsTest, UnrelatedExplicitKeyLeavesGroupsAlone) {
  base::DictValue expanded = ExpandPreset(Preset(kFull), kMilestone);
  base::DictValue before = expanded.Clone();
  base::DictValue explicit_cfg;
  explicit_cfg.Set(keys::kTimezoneId, "Asia/Tokyo");
  OverridePresetGroups(expanded, explicit_cfg);
  EXPECT_EQ(expanded, before);
}

}  // namespace
}  // namespace camoucfg

// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/observe_body.h"

#include <algorithm>
#include <map>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "base/json/json_writer.h"
#include "base/time/time.h"
#include "base/values.h"
#include "components/camoucfg/observe_golden_test_util.h"
#include "components/camoucfg/observe_leaf.h"
#include "testing/gtest/include/gtest/gtest.h"
#include "third_party/zlib/google/compression_utils.h"

namespace camoucfg::observe {

namespace {
std::vector<std::pair<std::string, std::string>> Classes(const std::vector<Field>& f) {
  std::vector<std::pair<std::string, std::string>> out;
  for (const auto& [path, leaf] : f) out.emplace_back(path, ValueClass(leaf));
  std::sort(out.begin(), out.end());
  return out;
}
}  // namespace

TEST(ObserveBodyTest, GoldenInflateParity) {
  for (const base::Value& c : *ObserveGolden().FindList("inflate")) {
    const base::DictValue& d = c.GetDict();
    SCOPED_TRACE(*d.FindString("name"));
    std::optional<std::string> got = Inflate(FromB64(*d.FindString("in_b64")));
    const std::string in = FromB64(*d.FindString("in_b64"));
    const std::string* want = d.FindString("out_b64");
    // Python returns the input when nothing decodes; the golden writes null then.
    std::string effective = got.value_or(in);
    EXPECT_EQ(effective, want ? FromB64(*want) : in);
  }
}

TEST(ObserveBodyTest, GoldenHttpParity) {
  int n = 0;
  for (const base::Value& c : *ObserveGolden().FindList("http")) {
    const base::DictValue& d = c.GetDict();
    SCOPED_TRACE(*d.FindString("name"));
    SjdStats stats;
    BodyFields f = Fields(FromB64(*d.FindString("b64")), *d.FindString("ct"), true, &stats);
    EXPECT_EQ(f.kind, *d.FindString("kind"));
    EXPECT_EQ(Classes(f.fields), PathClassPairs(*d.FindList("fields")));
    EXPECT_EQ(stats.decoded, (*d.FindList("sjd"))[0].GetInt());
    EXPECT_EQ(stats.failed, (*d.FindList("sjd"))[1].GetInt());
    ++n;
  }
  EXPECT_GE(n, 25);  // a golden file that lost its cases measures nothing
}

TEST(ObserveBodyTest, GoldenDivergentCasesPinCpp) {
  const std::map<std::string, std::pair<std::string, std::vector<std::pair<std::string, std::string>>>> cpp = {
      {"big-int-precision", {"json", {{"a", "id"}}}},
      {"integral-float-past-int32", {"json", {{"a", "id"}}}},
      {"json-depth-300", {"opaque", {}}},
      {"unicode-digits-id", {"json", {{"a", "str<10>"}}}},
  };
  size_t seen = 0;
  for (const base::Value& c : *ObserveGolden().FindList("divergent")) {
    const base::DictValue& d = c.GetDict();
    const auto it = cpp.find(*d.FindString("name"));
    ASSERT_NE(it, cpp.end()) << *d.FindString("name");
    BodyFields f = Fields(FromB64(*d.FindString("b64")), *d.FindString("ct"), true, nullptr);
    EXPECT_EQ(f.kind, it->second.first);
    EXPECT_EQ(Classes(f.fields), it->second.second);
    if (it->first == "big-int-precision") {
      // The class agrees; the digits do not (base::Value stores the integer
      // as a double, which holds 9007199254740992).
      ASSERT_EQ(f.fields.size(), 1u);
      EXPECT_EQ((*d.FindList("text"))[0].GetList()[1].GetString(), "9007199254740993");
      EXPECT_EQ(Display(f.fields[0].second), "9007199254740992");
    }
    ++seen;
  }
  EXPECT_EQ(seen, cpp.size());
}

TEST(ObserveBodyTest, InflateBombIsCapped) {
  std::string zeros(20 << 20, '\0');
  std::string packed;
  ASSERT_TRUE(compression::GzipCompress(zeros, &packed));
  base::TimeTicks t0 = base::TimeTicks::Now();
  EXPECT_FALSE(Inflate(packed));
  EXPECT_LT(base::TimeTicks::Now() - t0, base::Seconds(5));
}

TEST(ObserveBodyTest, InflateBombSetsCut) {
  std::string zeros(20 << 20, '\0');
  std::string packed;
  ASSERT_TRUE(compression::GzipCompress(zeros, &packed));
  bool capped = false;
  EXPECT_FALSE(Inflate(packed, &capped));
  EXPECT_TRUE(capped);
  BodyFields f = Fields(packed, "", true, nullptr);
  EXPECT_EQ(f.kind, "opaque");
  EXPECT_TRUE(f.cut);
  // A small valid gzip does not cut.
  std::string small;
  ASSERT_TRUE(compression::GzipCompress(std::string("{\"a\":1}"), &small));
  BodyFields g = Fields(small, "", true, nullptr);
  EXPECT_EQ(g.kind, "json");
  EXPECT_FALSE(g.cut);
}

TEST(ObserveBodyTest, DeepNestingStops) {
  // 70 nested lists: under base::JSONReader's depth limit, over kMaxWalkDepth.
  const std::string deep = std::string(70, '[') + "1" + std::string(70, ']');
  BodyFields f = Fields(deep, "", true, nullptr);
  EXPECT_EQ(f.kind, "json");
  EXPECT_TRUE(f.cut);
  EXPECT_TRUE(f.fields.empty());
  // JSON inside a string inside a string is walked into (3 levels).
  std::string s = "{\"w\":1517}";
  for (int i = 0; i < 2; ++i) {
    std::string quoted;
    base::JSONWriter::Write(base::Value(s), &quoted);
    s = "[" + quoted + "]";
  }
  BodyFields g = Fields(s, "", true, nullptr);
  ASSERT_EQ(g.fields.size(), 1u);
  EXPECT_EQ(g.fields[0].first, "[][].w");
  EXPECT_FALSE(g.cut);
}

TEST(ObserveBodyTest, MultipartPartBombSetsCut) {
  std::string zeros(20 << 20, '\0');
  std::string packed;
  ASSERT_TRUE(compression::GzipCompress(zeros, &packed));
  const std::string raw =
      "--B\r\nContent-Disposition: form-data; name=\"p\"\r\n\r\n" + packed +
      "\r\n--B--\r\n";
  BodyFields f = Fields(raw, "multipart/form-data; boundary=B", true, nullptr);
  EXPECT_EQ(f.kind, "multipart");
  ASSERT_EQ(f.fields.size(), 1u);
  EXPECT_EQ(f.fields[0].second.type, Leaf::Type::kOpaque);
  EXPECT_TRUE(f.cut);
}

TEST(ObserveBodyTest, ExactFieldCapThenEmptyContainerDoesNotCut) {
  std::string s = "[";
  for (size_t i = 0; i < kMaxFields; ++i) s += "1,";
  s += "[]]";
  BodyFields f = Fields(s, "", true, nullptr);
  EXPECT_EQ(f.fields.size(), kMaxFields);
  EXPECT_FALSE(f.cut);
  BodyFields g = Fields(s.substr(0, s.size() - 3) + "2]", "", true, nullptr);
  EXPECT_TRUE(g.cut);  // a field past the cap does cut
}

TEST(ObserveBodyTest, NumberClassesMatchOracle) {
  BodyFields f = Fields(
      R"({"dpr":2.0,"mid":1000000000000000,"big":10000000000000000,"s":2147483647,"a":2147483648})",
      "", true, nullptr);
  EXPECT_EQ(Classes(f.fields),
            (std::vector<std::pair<std::string, std::string>>{
                {"a", "id"}, {"big", "id"}, {"dpr", "float"}, {"mid", "id"}, {"s", "id"}}));
}

TEST(ObserveBodyTest, FieldCapCuts) {
  std::string s = "[";
  for (int i = 0; i < 6000; ++i) s += (i ? ",1" : "1");
  s += "]";
  BodyFields f = Fields(s, "", true, nullptr);
  EXPECT_EQ(f.fields.size(), kMaxFields);
  EXPECT_TRUE(f.cut);
}

}  // namespace camoucfg::observe

// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/gl_params.h"

#include "base/values.h"
#include "components/camoucfg/mask_config_internal.h"
#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg {
namespace {

base::DictValue Parse(std::string_view json) {
  return internal::ParseConfig(json, /*strict=*/false);
}

TEST(GLParamsTest, ReadsIntFromParameterMap) {
  auto cfg = Parse(R"({"webGl:parameters":{"3379":16384}})");  // MAX_TEXTURE_SIZE
  auto v = internal::GLParamFrom(cfg, 3379, /*is_webgl2=*/false);
  ASSERT_TRUE(v.has_value());
  ASSERT_TRUE(std::holds_alternative<int64_t>(*v));
  EXPECT_EQ(std::get<int64_t>(*v), 16384);
}

TEST(GLParamsTest, ReadsFloatArrayFromParameterMap) {
  auto cfg = Parse(R"({"webGl:parameters":{"33902":[1.0,1024.0]}})");  // ALIASED_LINE_WIDTH_RANGE
  auto v = internal::GLParamFrom(cfg, 33902, false);
  ASSERT_TRUE(v.has_value());
  ASSERT_TRUE(std::holds_alternative<std::vector<double>>(*v));
  EXPECT_EQ(std::get<std::vector<double>>(*v).size(), 2u);
}

TEST(GLParamsTest, ReadsStringFromParameterMap) {
  auto cfg = Parse(R"({"webGl:parameters":{"7936":"WebKit"}})");  // VENDOR
  auto v = internal::GLParamFrom(cfg, 7936, false);
  ASSERT_TRUE(std::holds_alternative<std::string>(*v));
}

TEST(GLParamsTest, NamespaceSplit) {
  auto cfg = Parse(R"({"webGl:parameters":{"3379":16384},"webGl2:parameters":{"3379":32768}})");
  EXPECT_EQ(std::get<int64_t>(*internal::GLParamFrom(cfg, 3379, false)), 16384);
  EXPECT_EQ(std::get<int64_t>(*internal::GLParamFrom(cfg, 3379, true)), 32768);
}

TEST(GLParamsTest, AbsentIsNullopt) {
  auto cfg = Parse(R"({"webGl:parameters":{"3379":16384}})");
  EXPECT_FALSE(internal::GLParamFrom(cfg, 9999, false).has_value());
  EXPECT_FALSE(internal::GLParamFrom(Parse("{}"), 3379, false).has_value());
}

TEST(GLParamsTest, BlockIfNotDefined) {
  auto cfg = Parse(R"({"webGl:parameters:blockIfNotDefined":true})");
  EXPECT_TRUE(internal::GLBlockFrom(cfg, false));
  EXPECT_FALSE(internal::GLBlockFrom(cfg, true));   // webGl2 not set
  EXPECT_FALSE(internal::GLBlockFrom(Parse("{}"), false));  // default false
}

TEST(GLParamsTest, ReadsShaderPrecision) {
  auto cfg = Parse(R"({"webGl:shaderPrecisionFormats":{"35633:36338":[127,127,23]}})");
  // 35633 VERTEX_SHADER, 36338 HIGH_FLOAT
  auto v = internal::GLShaderPrecisionFrom(cfg, 35633, 36338, false);
  ASSERT_TRUE(v.has_value());
  EXPECT_EQ((*v)[0], 127); EXPECT_EQ((*v)[2], 23);
  EXPECT_FALSE(internal::GLShaderPrecisionFrom(cfg, 35633, 36338, true).has_value());  // webGl2 unset
  EXPECT_FALSE(internal::GLShaderPrecisionFrom(Parse("{}"), 35633, 36338, false).has_value());
}

TEST(GLParamsTest, ShaderPrecisionRejectsMalformed) {
  // wrong-length or non-int array -> nullopt, not a partial/garbage array
  EXPECT_FALSE(internal::GLShaderPrecisionFrom(
      Parse(R"({"webGl:shaderPrecisionFormats":{"1:2":[1,2]}})"), 1, 2, false).has_value());
  EXPECT_FALSE(internal::GLShaderPrecisionFrom(
      Parse(R"({"webGl:shaderPrecisionFormats":{"1:2":[1,2,"x"]}})"), 1, 2, false).has_value());
}

TEST(GLParamsTest, ReadsContextAttrs) {
  auto cfg = Parse(R"({"webGl:contextAttributes":{"antialias":false,"powerPreference":"high-performance"}})");
  const base::DictValue* d = internal::GLContextAttrsFrom(cfg, false);
  ASSERT_NE(d, nullptr);
  EXPECT_EQ(d->FindBool("antialias"), std::optional<bool>(false));
  EXPECT_EQ(*d->FindString("powerPreference"), "high-performance");
  EXPECT_EQ(internal::GLContextAttrsFrom(cfg, true), nullptr);  // webGl2 unset
}

}  // namespace
}  // namespace camoucfg

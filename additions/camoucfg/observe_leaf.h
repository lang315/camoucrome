// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_OBSERVE_LEAF_H_
#define COMPONENTS_CAMOUCFG_OBSERVE_LEAF_H_

#include <cstddef>
#include <optional>
#include <string>
#include <string_view>
#include <utility>

#include "base/values.h"

namespace camoucfg::observe {

// One decoded value in the Python oracle's types (scripts/observe_drive.py):
// str, int, float, bool, None, and Opaque (bytes known only by length).
struct Leaf {
  enum class Type { kStr, kInt, kFloat, kBool, kNull, kOpaque };
  Type type = Type::kNull;
  std::string str;        // kStr, valid UTF-8
  double num = 0;         // kInt (integral) and kFloat
  bool b = false;         // kBool
  size_t opaque_len = 0;  // kOpaque

  static Leaf Str(std::string s);
  static Leaf Opaque(size_t n);
  // A JSON scalar. base::JSONReader keeps no int/float token kind: an integral
  // double below 1e21 counts as Python's int (JS JSON writes integers that
  // way). A container becomes kStr of its JSON (sjd signal values only).
  static Leaf FromValue(const base::Value& v);
};

using Field = std::pair<std::string, Leaf>;

std::string ValueClass(const Leaf& leaf);
std::string Display(const Leaf& leaf);
std::string PyNumStr(const Leaf& leaf);
size_t CodePoints(std::string_view utf8);
bool IsUtf8(std::string_view bytes);
std::string Utf8Replace(std::string_view bytes);
std::string_view PyStrip(std::string_view s);
std::string_view PyLStrip(std::string_view s);
std::optional<std::string> B64DecodeStrict(std::string_view s);
std::optional<base::Value> ParseJsonContainer(std::string_view text);

}  // namespace camoucfg::observe

#endif  // COMPONENTS_CAMOUCFG_OBSERVE_LEAF_H_

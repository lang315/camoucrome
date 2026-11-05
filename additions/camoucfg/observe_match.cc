// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/observe_match.h"

#include <cmath>
#include <optional>
#include <string_view>

#include "base/strings/string_util.h"
#include "components/camoucfg/observe_leaf.h"

namespace camoucfg::observe {

namespace {

using T = Leaf::Type;

bool IsNum(const Leaf& l) {
  return l.type == T::kInt || l.type == T::kFloat;
}

// shortcut: a whole number below 100, or a string of 3 characters or fewer
// ("4g"), equals surfaces by chance; reported apart, not dropped.
bool Weak(const Leaf& v) {
  return (IsNum(v) && std::trunc(v.num) == v.num && std::fabs(v.num) < 100) ||
         (v.type == T::kStr && CodePoints(v.str) <= 3);
}

// Python f"{v}" of a truth value used in a WxH pair.
std::optional<std::string> TruthStr(const base::Value* v) {
  if (!v || v->is_none()) {
    return std::nullopt;
  }
  if (v->is_string()) {
    return v->GetString();
  }
  if (v->is_int() || v->is_double()) {
    return PyNumStr(Leaf::FromValue(*v));
  }
  return std::nullopt;
}

constexpr struct {
  const char* name;
  const char* w;
  const char* h;
} kPairs[] = {{"screen", "screen.width", "screen.height"},
              {"screen.avail", "screen.availWidth", "screen.availHeight"},
              {"window.inner", "window.innerWidth", "window.innerHeight"},
              {"window.outer", "window.outerWidth", "window.outerHeight"}};

}  // namespace

std::vector<Hit> Match(const Leaf& value, const base::DictValue& truth) {
  std::vector<Hit> out;
  if (value.type == T::kBool || value.type == T::kOpaque ||
      value.type == T::kNull || (value.type == T::kStr && value.str.empty())) {
    return out;
  }
  for (auto [surface, tv] : truth) {
    if (tv.is_none() || tv.is_bool()) {
      continue;
    }
    const bool scalar = !tv.is_list() && !tv.is_dict();
    const Leaf t = scalar ? Leaf::FromValue(tv) : Leaf();
    if (scalar && ((value.type == T::kStr && t.type == T::kStr &&
                    value.str == t.str) ||
                   (IsNum(value) && IsNum(t) && value.num == t.num))) {
      out.push_back({surface, "exact", Weak(value)});
    } else if (scalar && IsNum(t) && value.type == T::kStr &&
               value.str == PyNumStr(t)) {
      out.push_back({surface, "str", Weak(t)});
    } else if (scalar && surface == "navigator.userAgent" &&
               value.type == T::kStr && t.type == T::kStr &&
               CodePoints(value.str) >= 20 &&
               (t.str.find(value.str) != std::string::npos ||
                value.str.find(t.str) != std::string::npos)) {
      out.push_back({surface, "substr", false});
    } else if (tv.is_list() && value.type == T::kStr) {
      bool all_str = true;
      std::vector<std::string_view> parts;
      for (const base::Value& x : tv.GetList()) {
        all_str = all_str && x.is_string();
        if (x.is_string()) {
          parts.push_back(x.GetString());
        }
      }
      if (all_str && value.str == base::JoinString(parts, ",")) {
        out.push_back({surface, "joined", false});
      }
    }
    if (surface == "timezoneOffset" && IsNum(value) && IsNum(t) &&
        t.num != 0 && value.num == -t.num) {
      out.push_back({surface, "tzoffset-neg", Weak(value)});
    }
  }
  if (value.type == T::kStr) {
    for (const auto& p : kPairs) {
      const std::optional<std::string> w = TruthStr(truth.Find(p.w));
      const std::optional<std::string> h = TruthStr(truth.Find(p.h));
      if (w && h &&
          (value.str == *w + "x" + *h || value.str == *w + "*" + *h)) {
        out.push_back({p.name, "WxH", false});
      }
    }
  }
  return out;
}

std::vector<std::string> BoolMatches(const Leaf& value,
                                     const base::DictValue& truth) {
  std::vector<std::string> out;
  if (value.type != T::kBool) {
    return out;
  }
  for (auto [surface, tv] : truth) {
    if (tv.is_bool() && tv.GetBool() == value.b) {
      out.push_back(surface);
    }
  }
  return out;
}

}  // namespace camoucfg::observe

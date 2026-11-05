// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/observe_leaf.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <string>

#include "base/json/json_reader.h"
#include "base/json/json_writer.h"
#include "base/notreached.h"
#include "base/strings/string_number_conversions.h"
#include "base/strings/string_util.h"
#include "base/strings/stringprintf.h"
#include "base/strings/strcat.h"
#include "base/strings/utf_string_conversions.h"

namespace camoucfg::observe {

namespace {

// str.isspace() code points, as UTF-8.
constexpr std::string_view kPySpaces[] = {
    "\t", "\n", "\v", "\f", "\r", "\x1c", "\x1d", "\x1e", "\x1f", " ",
    "\xC2\x85", "\xC2\xA0", "\xE1\x9A\x80", "\xE2\x80\x80", "\xE2\x80\x81",
    "\xE2\x80\x82", "\xE2\x80\x83", "\xE2\x80\x84", "\xE2\x80\x85",
    "\xE2\x80\x86", "\xE2\x80\x87", "\xE2\x80\x88", "\xE2\x80\x89",
    "\xE2\x80\x8A", "\xE2\x80\xA8", "\xE2\x80\xA9", "\xE2\x80\xAF",
    "\xE2\x81\x9F", "\xE3\x80\x80"};

bool StripFront(std::string_view& s) {
  for (std::string_view p : kPySpaces) {
    if (s.starts_with(p)) {
      s.remove_prefix(p.size());
      return true;
    }
  }
  return false;
}

bool StripBack(std::string_view& s) {
  for (std::string_view p : kPySpaces) {
    if (s.ends_with(p)) {
      s.remove_suffix(p.size());
      return true;
    }
  }
  return false;
}

// ID_RE = ^\d{10,}$. shortcut: ASCII digits only; Python's \d also takes
// other Unicode digits (golden divergent case unicode-digits-id).
bool IsIdString(std::string_view s) {
  if (s.ends_with('\n')) {
    s.remove_suffix(1);
  }
  return s.size() >= 10 && std::all_of(s.begin(), s.end(), base::IsAsciiDigit<char>);
}

int B64Index(char c) {
  if (c >= 'A' && c <= 'Z') return c - 'A';
  if (c >= 'a' && c <= 'z') return c - 'a' + 26;
  if (c >= '0' && c <= '9') return c - '0' + 52;
  if (c == '+') return 62;
  if (c == '/') return 63;
  return -1;
}

}  // namespace

Leaf Leaf::Str(std::string s) {
  Leaf l;
  l.type = Type::kStr;
  l.str = std::move(s);
  return l;
}

Leaf Leaf::Opaque(size_t n) {
  Leaf l;
  l.type = Type::kOpaque;
  l.opaque_len = n;
  return l;
}

Leaf Leaf::FromValue(const base::Value& v) {
  Leaf l;
  switch (v.type()) {
    case base::Value::Type::NONE:
      break;
    case base::Value::Type::BOOLEAN:
      l.type = Type::kBool;
      l.b = v.GetBool();
      break;
    case base::Value::Type::INTEGER:
      l.type = Type::kInt;
      l.num = v.GetInt();
      break;
    case base::Value::Type::DOUBLE: {
      // JSONReader stores an integer token that fits int32 as INTEGER and any
      // other number as DOUBLE. So an integral double below 2^31 had a decimal
      // point or exponent (Python float); one from 2^31 up was a big integer
      // (Python int), except from 1e21 up, where JS writes exponent form.
      const double d = v.GetDouble();
      const double a = std::fabs(d);
      l.type = (std::trunc(d) == d && a >= 2147483648.0 && a < 1e21)
                   ? Type::kInt
                   : Type::kFloat;
      l.num = d;
      break;
    }
    case base::Value::Type::STRING:
      l.type = Type::kStr;
      l.str = v.GetString();
      break;
    default:  // BINARY never comes out of JSONReader; DICT and LIST do
      l.type = Type::kStr;
      base::JSONWriter::Write(v, &l.str);
      break;
  }
  return l;
}

namespace {

// The decimal digits of an integral double that was a JSON integer. Exact
// below 2^53; above it base::Value already lost digits (pinned divergence,
// golden "big-int-precision"), and this prints the double's own digits.
std::string IntegerText(double d) {
  return base::StringPrintf("%.0f", d);
}

// Python repr(float): the shortest digits that round-trip, written plain for
// decimal exponents -4..15 and as d.ddde+XX (two exponent digits) otherwise.
std::string FloatRepr(double d) {
  if (d == 0) {
    return std::signbit(d) ? "-0.0" : "0.0";
  }
  std::string sci;
  for (int prec = 0; prec < 17; ++prec) {
    sci = base::StringPrintf("%.*e", prec, d);
    double back = 0;
    if (base::StringToDouble(sci, &back) && back == d) {
      break;
    }
  }
  const bool neg = sci[0] == '-';
  const size_t e_at = sci.find('e');
  std::string digits;
  for (size_t i = neg ? 1 : 0; i < e_at; ++i) {
    if (sci[i] != '.') {
      digits.push_back(sci[i]);
    }
  }
  while (digits.size() > 1 && digits.back() == '0') {
    digits.pop_back();
  }
  const int exp = std::stoi(sci.substr(e_at + 1));
  std::string out;
  if (exp >= -4 && exp < 16) {
    if (exp < 0) {
      out = "0." + std::string(-exp - 1, '0') + digits;
    } else if (digits.size() <= static_cast<size_t>(exp) + 1) {
      out = digits + std::string(exp + 1 - digits.size(), '0') + ".0";
    } else {
      out = digits.substr(0, exp + 1) + "." + digits.substr(exp + 1);
    }
  } else {
    out = digits.substr(0, 1);
    if (digits.size() > 1) {
      out += "." + digits.substr(1);
    }
    const int a = std::abs(exp);
    out += base::StringPrintf("e%c%02d", exp < 0 ? '-' : '+', a);
  }
  return neg ? "-" + out : out;
}

}  // namespace

std::string PyNumStr(const Leaf& leaf) {
  if (leaf.type == Leaf::Type::kInt) {
    return IntegerText(leaf.num);
  }
  return FloatRepr(leaf.num);
}

std::string ValueClass(const Leaf& v) {
  switch (v.type) {
    case Leaf::Type::kOpaque:
      return base::StrCat({"opaque<", base::NumberToString(v.opaque_len), ">"});
    case Leaf::Type::kBool:
      return "bool";
    case Leaf::Type::kNull:
      return "null";
    case Leaf::Type::kInt:
      return IntegerText(std::fabs(v.num)).size() >= 10 ? "id" : "int";
    case Leaf::Type::kFloat:
      return "float";
    case Leaf::Type::kStr:
      return IsIdString(v.str)
                 ? "id"
                 : base::StrCat({"str<", base::NumberToString(CodePoints(v.str)), ">"});
  }
  NOTREACHED();
}

std::string Display(const Leaf& v) {
  switch (v.type) {
    case Leaf::Type::kOpaque:
      return ValueClass(v);
    case Leaf::Type::kBool:
      return v.b ? "true" : "false";
    case Leaf::Type::kNull:
      return "null";
    case Leaf::Type::kInt:
    case Leaf::Type::kFloat:
      return PyNumStr(v);
    case Leaf::Type::kStr: {
      size_t i = 0, n = 0;
      while (i < v.str.size() && n < 120) {
        ++i;
        while (i < v.str.size() && (v.str[i] & 0xC0) == 0x80) ++i;
        ++n;
      }
      return i < v.str.size() ? v.str.substr(0, i) + "\xE2\x80\xA6" : v.str;
    }
  }
  NOTREACHED();
}

size_t CodePoints(std::string_view s) {
  return std::count_if(s.begin(), s.end(),
                       [](char c) { return (c & 0xC0) != 0x80; });
}

bool IsUtf8(std::string_view bytes) {
  return base::IsStringUTF8AllowingNoncharacters(bytes);
}

std::string Utf8Replace(std::string_view bytes) {
  if (IsUtf8(bytes)) {
    return std::string(bytes);
  }
  // shortcut: base's replacement follows ICU's maximal-subpart rule, as Python
  // does; a difference would show only in the count of U+FFFD in a name.
  std::u16string u;
  base::UTF8ToUTF16(bytes.data(), bytes.size(), &u);
  return base::UTF16ToUTF8(u);
}

std::string_view PyStrip(std::string_view s) {
  while (StripFront(s)) {}
  while (StripBack(s)) {}
  return s;
}

std::string_view PyLStrip(std::string_view s) {
  while (StripFront(s)) {}
  return s;
}

// base64.b64decode(s, validate=True) on Python 3.12 (a2b_base64 strict mode):
// only the alphabet, padding only at the end, no data after padding, and
// the padding the data length needs (any, after a complete quad). Trailing bits
// are not checked.
std::optional<std::string> B64DecodeStrict(std::string_view s) {
  size_t data = 0;
  while (data < s.size() && B64Index(s[data]) >= 0) ++data;
  size_t pads = 0;
  while (data + pads < s.size() && s[data + pads] == '=') ++pads;
  if (data + pads != s.size() || (data == 0 && pads > 0)) {
    return std::nullopt;
  }
  // Python takes any padding after a complete quad ("YWJj=" -> "abc", golden
  // case); otherwise exactly the padding the data length needs.
  static constexpr size_t kPadsFor[4] = {0, 9, 2, 1};  // 9: never valid
  if (data % 4 != 0 && kPadsFor[data % 4] != pads) {
    return std::nullopt;
  }
  std::string out;
  uint32_t acc = 0;
  int bits = 0;
  for (size_t i = 0; i < data; ++i) {
    acc = (acc << 6) | static_cast<uint32_t>(B64Index(s[i]));
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      out.push_back(static_cast<char>((acc >> bits) & 0xFF));
    }
  }
  return out;
}

std::optional<base::Value> ParseJsonContainer(std::string_view text) {
  std::optional<base::Value> v = base::JSONReader::Read(text, base::JSON_PARSE_RFC);
  if (!v || !(v->is_dict() || v->is_list())) {
    return std::nullopt;
  }
  return v;
}

}  // namespace camoucfg::observe

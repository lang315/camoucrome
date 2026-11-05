// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/observe_body.h"

#include "base/strings/strcat.h"
#include "base/strings/string_split.h"
#include "base/strings/string_util.h"
#include "components/camoucfg/observe_blowfish.h"
#include "third_party/zlib/zlib.h"

namespace camoucfg::observe {

namespace {

// One zlib stream (inflateInit2 window bits): its output and the input bytes it
// used, or nullopt when it does not end (Python: "incomplete or truncated
// stream") or its output passes kMaxInflated (then *capped is set).
std::optional<std::pair<std::string, size_t>> InflateOne(std::string_view in,
                                                         int window_bits,
                                                         bool* capped) {
  z_stream z = {};
  if (inflateInit2(&z, window_bits) != Z_OK) {
    return std::nullopt;
  }
  z.next_in = reinterpret_cast<Bytef*>(const_cast<char*>(in.data()));
  z.avail_in = static_cast<uInt>(in.size());
  std::string out;
  char buf[16384];
  int rc = Z_OK;
  while (rc == Z_OK) {
    z.next_out = reinterpret_cast<Bytef*>(buf);
    z.avail_out = sizeof(buf);
    rc = inflate(&z, Z_NO_FLUSH);
    out.append(buf, sizeof(buf) - z.avail_out);
    if (out.size() > kMaxInflated) {
      rc = Z_MEM_ERROR;
      *capped = true;
    }
  }
  const size_t used = in.size() - z.avail_in;
  inflateEnd(&z);
  if (rc != Z_STREAM_END) {
    return std::nullopt;
  }
  return std::make_pair(std::move(out), used);
}

// gzip.decompress(): members back to back, NUL padding between and after
// them; empty input is an empty output.
std::optional<std::string> Gunzip(std::string_view in, bool* capped) {
  std::string all;
  while (!in.empty()) {
    auto one = InflateOne(in, 16 + MAX_WBITS, capped);
    if (!one) {
      return std::nullopt;
    }
    if (all.size() + one->first.size() > kMaxInflated) {
      *capped = true;
      return std::nullopt;
    }
    all += one->first;
    in.remove_prefix(one->second);
    while (!in.empty() && in.front() == '\0') {
      in.remove_prefix(1);
    }
  }
  return all;
}

bool IsBoundaryStop(char c) {
  return c == '"' || c == ';' || c == ',' || c == ' ' || (c >= 0x09 && c <= 0x0d) ||
         (c >= 0x1c && c <= 0x1f);
}

std::vector<std::string_view> SplitOn(std::string_view s, std::string_view d) {
  std::vector<std::string_view> out;
  size_t start = 0;
  for (size_t at = s.find(d); at != std::string_view::npos; at = s.find(d, start)) {
    out.push_back(s.substr(start, at - start));
    start = at + d.size();
  }
  out.push_back(s.substr(start));
  return out;
}

// re.search(rb"content-disposition:[^\r\n]*", head, re.I)
std::optional<std::string_view> FindDisposition(std::string_view head) {
  const size_t at = base::ToLowerASCII(head).find("content-disposition:");
  if (at == std::string::npos) {
    return std::nullopt;
  }
  const size_t end = head.find_first_of("\r\n", at);
  return head.substr(at, end == std::string_view::npos ? end : end - at);
}

// re.search(rb'(?<![A-Za-z])name="([^"]*)"', disp)
std::optional<std::string_view> FindName(std::string_view disp) {
  for (size_t at = disp.find("name=\""); at != std::string_view::npos;
       at = disp.find("name=\"", at + 1)) {
    if (at > 0 && base::IsAsciiAlpha(disp[at - 1])) {
      continue;
    }
    const size_t value = at + 6;
    const size_t close = disp.find('"', value);
    if (close == std::string_view::npos) {
      return std::nullopt;
    }
    return disp.substr(value, close - value);
  }
  return std::nullopt;
}

// _part_value(): text, inflated first when the bytes are not text; a file part
// is text only when it is JSON; anything else keeps only its length.
Leaf PartValue(std::string_view body, bool filename, bool* cut) {
  std::string text;
  if (IsUtf8(body)) {
    text = std::string(body);
  } else if (std::optional<std::string> inflated = Inflate(body, cut);
             inflated && IsUtf8(*inflated)) {
    text = std::move(*inflated);
  } else {
    return Leaf::Opaque(body.size());
  }
  if (filename && !ParseJsonContainer(text)) {
    return Leaf::Opaque(body.size());
  }
  return Leaf::Str(std::move(text));
}

// name.replace('+', ' ') then urllib.parse.unquote(errors="replace").
std::string Unquote(std::string_view s) {
  std::string bytes;
  for (size_t i = 0; i < s.size(); ++i) {
    if (s[i] == '+') {
      bytes.push_back(' ');
    } else if (s[i] == '%' && i + 2 < s.size() && base::IsHexDigit(s[i + 1]) &&
               base::IsHexDigit(s[i + 2])) {
      bytes.push_back(static_cast<char>(base::HexDigitToInt(s[i + 1]) * 16 +
                                        base::HexDigitToInt(s[i + 2])));
      i += 2;
    } else {
      bytes.push_back(s[i]);
    }
  }
  return Utf8Replace(bytes);
}

}  // namespace

std::optional<std::string> Inflate(std::string_view raw, bool* capped) {
  bool local = false;
  if (!capped) {
    capped = &local;
  }
  if (std::optional<std::string> g = Gunzip(raw, capped)) {
    return g;
  }
  if (auto z = InflateOne(raw, MAX_WBITS, capped)) {
    return std::move(z->first);
  }
  if (auto d = InflateOne(raw, -MAX_WBITS, capped)) {
    return std::move(d->first);
  }
  return std::nullopt;
}

std::optional<std::string> Boundary(std::string_view raw, std::string_view ct) {
  // re.search(r'boundary="?([^";,\s]+)"?', ct, re.I)
  const std::string lower = base::ToLowerASCII(ct);
  for (size_t at = lower.find("boundary="); at != std::string::npos;
       at = lower.find("boundary=", at + 1)) {
    size_t i = at + 9;
    if (i < ct.size() && ct[i] == '"') {
      ++i;
    }
    size_t j = i;
    while (j < ct.size() && !IsBoundaryStop(ct[j])) {
      ++j;
    }
    if (j > i) {
      return std::string(ct.substr(i, j - i));
    }
  }
  const std::string_view first = raw.substr(0, raw.find("\r\n"));
  if (first.starts_with("--") && first.size() > 2 && first.size() <= 200 &&
      first.find(' ') == std::string_view::npos) {
    return std::string(first.substr(2));
  }
  return std::nullopt;
}

std::vector<std::pair<std::string, Leaf>> MultipartParts(std::string_view raw,
                                                         std::string_view boundary,
                                                         bool* cut) {
  std::vector<std::pair<std::string, Leaf>> parts;
  const std::vector<std::string_view> chunks = SplitOn(raw, base::StrCat({"--", boundary}));
  for (size_t c = 1; c < chunks.size(); ++c) {
    std::string_view chunk = chunks[c];
    if (chunk.starts_with("--")) {
      break;  // the closing delimiter
    }
    const size_t k = chunk.find_first_not_of("\r\n");
    chunk = k == std::string_view::npos ? std::string_view() : chunk.substr(k);
    const size_t sep = chunk.find("\r\n\r\n");
    if (sep == std::string_view::npos) {
      continue;
    }
    const std::optional<std::string_view> disp = FindDisposition(chunk.substr(0, sep));
    const std::optional<std::string_view> name = disp ? FindName(*disp) : std::nullopt;
    if (!name) {
      continue;
    }
    std::string_view body = chunk.substr(sep + 4);
    if (body.ends_with("\r\n")) {
      body.remove_suffix(2);
    }
    parts.emplace_back(Utf8Replace(*name),
                       PartValue(body, disp->find("filename=") != std::string_view::npos, cut));
  }
  return parts;
}

std::vector<std::pair<std::string, std::string>> ParseQsl(std::string_view text) {
  std::vector<std::pair<std::string, std::string>> out;
  for (std::string_view piece : base::SplitStringPiece(
           text, "&", base::KEEP_WHITESPACE, base::SPLIT_WANT_ALL)) {
    if (piece.empty()) {
      continue;
    }
    const size_t eq = piece.find('=');
    out.emplace_back(Unquote(piece.substr(0, eq)),
                     eq == std::string_view::npos ? std::string()
                                                  : Unquote(piece.substr(eq + 1)));
  }
  return out;
}

Decoded DecodeBody(std::string_view raw_in, std::string_view content_type, bool allow_b64) {
  Decoded d;
  d.kind = "opaque";
  const std::string raw = Inflate(raw_in, &d.cut).value_or(std::string(raw_in));
  if (std::optional<std::string> boundary = Boundary(raw, content_type)) {
    auto parts = MultipartParts(raw, *boundary, &d.cut);
    if (!parts.empty()) {
      d.kind = "multipart";
      d.pairs = std::move(parts);
      return d;
    }
  }
  if (!IsUtf8(raw)) {
    return d;
  }
  if (std::optional<base::Value> j = ParseJsonContainer(raw)) {
    d.kind = "json";
    d.json = std::move(*j);
    return d;
  }
  // base64 before form: its '=' padding parses as a form key; a real form
  // fails validation on '&' and '%'.
  if (allow_b64) {
    std::optional<std::string> inner = B64DecodeStrict(PyStrip(raw));
    if (inner && !inner->empty() && *inner != raw) {
      Decoded in = DecodeBody(*inner, "", false);
      if (in.kind != "opaque") {
        in.cut |= d.cut;
        return in;
      }
      d.cut = d.cut || in.cut;
    }
  }
  const std::string_view l = PyLStrip(raw);
  if (raw.find('=') != std::string::npos && !l.starts_with('{') && !l.starts_with('[')) {
    auto pairs = ParseQsl(raw);
    if (!pairs.empty()) {
      d.kind = "form";
      for (auto& [k, v] : pairs) {
        d.pairs.emplace_back(std::move(k), Leaf::Str(std::move(v)));
      }
    }
  }
  return d;
}

void Walker::Walk(const base::Value& v, const std::string& prefix, int depth) {
  if (depth > kMaxWalkDepth) {
    cut = true;
    return;
  }
  if (v.is_dict()) {
    for (auto [k, child] : v.GetDict()) {
      const std::string path = prefix.empty() ? k : base::StrCat({prefix, ".", k});
      Walk(child, path, depth + 1);
      if (site_hooks && child.is_string()) {
        ExpandSjd(path, v.GetDict());
      }
    }
    return;
  }
  if (v.is_list()) {
    for (const base::Value& item : v.GetList()) {
      Walk(item, prefix + "[]", depth + 1);
    }
    return;
  }
  if (v.is_string()) {
    if (std::optional<base::Value> j = ParseJsonContainer(v.GetString())) {
      Walk(*j, prefix, depth + 1);
      return;
    }
  }
  if (out->size() >= kMaxFields) {
    cut = true;
    return;
  }
  out->emplace_back(prefix, Leaf::FromValue(v));
}

void Walker::WalkLeaf(const Leaf& leaf, const std::string& prefix, int depth) {
  if (leaf.type == Leaf::Type::kStr) {
    if (std::optional<base::Value> j = ParseJsonContainer(leaf.str)) {
      Walk(*j, prefix, depth + 1);
      return;
    }
  }
  if (out->size() >= kMaxFields) {
    cut = true;
    return;
  }
  out->emplace_back(prefix, leaf);
}

void Walker::ExpandSjd(const std::string& path, const base::DictValue& event) {
  const size_t dot = path.rfind('.');
  if (std::string_view(path).substr(dot == std::string::npos ? 0 : dot + 1) != "sjd") {
    return;
  }
  bool any = false;  // the hook returned at least one pair
  if (std::optional<base::DictValue> doc = DecodeSjd(event)) {
    for (auto [id, values] : *doc) {
      for (const base::Value& item : values.GetList()) {
        any = true;
        if (out->size() >= kMaxFields) {
          cut = true;
          break;
        }
        out->emplace_back(base::StrCat({path, ".", id, "[]"}), Leaf::FromValue(item));
      }
    }
  }
  if (stats) {
    ++(any ? stats->decoded : stats->failed);
  }
}

BodyFields Fields(std::string_view raw, std::string_view content_type, bool site_hooks,
                  SjdStats* stats) {
  BodyFields r;
  Decoded d = DecodeBody(raw, content_type);
  r.kind = d.kind;
  Walker w{site_hooks, stats, &r.fields};
  if (d.kind == "json") {
    w.Walk(d.json, "", 0);
  } else {
    for (const auto& [name, value] : d.pairs) {
      w.WalkLeaf(value, name, 0);
    }
  }
  r.cut = w.cut || d.cut;
  return r;
}

}  // namespace camoucfg::observe

// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_OBSERVE_BODY_H_
#define COMPONENTS_CAMOUCFG_OBSERVE_BODY_H_

#include <cstddef>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "base/memory/raw_ptr.h"
#include "base/values.h"
#include "components/camoucfg/observe_leaf.h"

namespace camoucfg::observe {

inline constexpr size_t kMaxInflated = 8 << 20;
inline constexpr int kMaxWalkDepth = 64;
inline constexpr size_t kMaxFields = 5000;

struct SjdStats {
  int decoded = 0;
  int failed = 0;
};

// scripts/observe_drive._inflate(): gzip, zlib, then raw deflate; nullopt when
// none decodes. Output past kMaxInflated also gives nullopt, and sets *capped
// (when given) so the caller can report the cut.
std::optional<std::string> Inflate(std::string_view raw, bool* capped = nullptr);
std::optional<std::string> Boundary(std::string_view raw,
                                    std::string_view content_type);
// *cut (when given) is set when a part's inflate hit kMaxInflated.
std::vector<std::pair<std::string, Leaf>> MultipartParts(
    std::string_view raw,
    std::string_view boundary,
    bool* cut = nullptr);
std::vector<std::pair<std::string, std::string>> ParseQsl(std::string_view);

struct Decoded {
  std::string kind;  // "json", "multipart", "form" or "opaque"
  base::Value json;
  std::vector<std::pair<std::string, Leaf>> pairs;
  bool cut = false;  // an inflate hit kMaxInflated
};

Decoded DecodeBody(std::string_view raw,
                   std::string_view content_type,
                   bool allow_b64 = true);

// The JSON walk of observe_drive.walk(): dict keys joined by '.', list items
// as '[]', a string that is JSON is walked into. With site_hooks (Python
// passes the site for HTTP bodies only), a string leaf whose last path segment
// is "sjd" is opened with its dict's "asid" (sites/facebook.expand_fields).
struct Walker {
  bool site_hooks = false;
  raw_ptr<SjdStats> stats = nullptr;
  raw_ptr<std::vector<Field>> out = nullptr;
  bool cut = false;  // kMaxFields or kMaxWalkDepth was hit

  void Walk(const base::Value& v, const std::string& prefix, int depth);
  void WalkLeaf(const Leaf& leaf, const std::string& prefix, int depth);
  void ExpandSjd(const std::string& path, const base::DictValue& event);
};

struct BodyFields {
  std::string kind;
  std::vector<Field> fields;
  // The walker dropped something (kMaxFields, kMaxWalkDepth) or an inflate hit
  // kMaxInflated. Shown on the page as body_cut.
  bool cut = false;
};

BodyFields Fields(std::string_view raw,
                  std::string_view content_type,
                  bool site_hooks,
                  SjdStats* stats);

}  // namespace camoucfg::observe

#endif  // COMPONENTS_CAMOUCFG_OBSERVE_BODY_H_

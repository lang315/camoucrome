// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_OBSERVE_GOLDEN_TEST_UTIL_H_
#define COMPONENTS_CAMOUCFG_OBSERVE_GOLDEN_TEST_UTIL_H_

#include <algorithm>
#include <string>
#include <utility>
#include <vector>

#include "base/base64.h"
#include "base/check.h"
#include "base/files/file_path.h"
#include "base/files/file_util.h"
#include "base/json/json_reader.h"
#include "base/path_service.h"
#include "base/values.h"

namespace camoucfg::observe {

// The golden cases scripts/gen_observe_golden.py wrote from the Python oracle.
inline base::DictValue ObserveGolden() {
  base::FilePath root;
  CHECK(base::PathService::Get(base::DIR_SRC_TEST_DATA_ROOT, &root));
  std::string text;
  CHECK(base::ReadFileToString(
      root.AppendASCII("components/camoucfg/observe_golden.json"), &text));
  return *base::JSONReader::ReadDict(text, base::JSON_PARSE_RFC);
}

inline std::string FromB64(std::string_view b64) {
  std::string out;
  CHECK(base::Base64Decode(b64, &out));
  return out;
}

// [["path", "class"], ...] as sorted pairs.
inline std::vector<std::pair<std::string, std::string>> PathClassPairs(
    const base::ListValue& list) {
  std::vector<std::pair<std::string, std::string>> out;
  for (const base::Value& v : list) {
    out.emplace_back(v.GetList()[0].GetString(), v.GetList()[1].GetString());
  }
  std::sort(out.begin(), out.end());
  return out;
}

}  // namespace camoucfg::observe

#endif  // COMPONENTS_CAMOUCFG_OBSERVE_GOLDEN_TEST_UTIL_H_

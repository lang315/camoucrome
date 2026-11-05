// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_OBSERVE_MATCH_H_
#define COMPONENTS_CAMOUCFG_OBSERVE_MATCH_H_

#include <string>
#include <vector>

#include "base/values.h"
#include "components/camoucfg/observe_leaf.h"

namespace camoucfg::observe {

struct Hit {
  std::string surface;
  std::string encoding;  // exact, str, substr, joined, tzoffset-neg, WxH
  bool weak = false;
};

// Port of observe_drive.match: the truth surfaces a decoded value equals.
std::vector<Hit> Match(const Leaf& value, const base::DictValue& truth);

// Port of observe_drive.bool_matches: the surfaces whose boolean truth equals
// a boolean value.
std::vector<std::string> BoolMatches(const Leaf& value,
                                     const base::DictValue& truth);

}  // namespace camoucfg::observe

#endif  // COMPONENTS_CAMOUCFG_OBSERVE_MATCH_H_

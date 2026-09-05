// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_DEVICE_IDS_H_
#define COMPONENTS_CAMOUCFG_DEVICE_IDS_H_

#include <cstdint>
#include <string>
#include <string_view>

namespace camoucfg {

// Deterministic, origin-salted synthetic device id. 64 lowercase hex,
// matching a real salted device id's shape (a page cannot distinguish it from
// HMAC-SHA256 hex). Pure: the same (seed, kind, real_id, origin) yields the
// same output.
//   - seed == 0 -> real_id unchanged (rule 5 no-op).
//   - real_id empty -> "" (pre-grant path never calls this).
//   - real_id == "default" -> "default" (real Chrome sentinel, preserved).
// Folds ORIGIN so two origins with the same seed differ (per-origin salt) --
// a stable-across-origin id would itself be a cross-origin tracking id, the
// opposite of the goal. Folds `kind` and `real_id` too, so different device
// kinds or different underlying devices never collide.
std::string SyntheticDeviceId(uint64_t seed, std::string_view kind,
                              std::string_view real_id,
                              std::string_view origin);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_DEVICE_IDS_H_

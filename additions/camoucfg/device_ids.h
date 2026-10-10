// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_DEVICE_IDS_H_
#define COMPONENTS_CAMOUCFG_DEVICE_IDS_H_

#include <cstdint>
#include <string>
#include <string_view>

#include "components/camoucfg/mask_config.h"

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

// The label an enumerated entry shows when the identity's label for its kind
// is `configured`. A Windows sentinel ("default"/"communications", labelled
// "<localized prefix> - <device>") keeps Chrome's prefix and swaps only the
// device name; every other entry shows `configured` (S3).
std::string MaskedDeviceLabel(std::string_view device_id,
                              std::string_view chrome_label,
                              std::string_view configured);

// The label an identity's device shows when its kind's label key is absent.
// One copy, shared by the browser phantoms (media_devices_manager.cc), the
// enumerate transform (media_devices.cc) and the track label
// (media_stream_track_impl.cc).
inline constexpr char kDefaultCameraLabel[] = "Integrated Camera";
inline constexpr char kDefaultMicrophoneLabel[] = "Microphone (Realtek Audio)";
inline constexpr char kDefaultSpeakerLabel[] = "Speakers (Realtek Audio)";

// The mediaDevices seed when media-device spoofing is active, else 0. Active
// means mediaDevices:enabled is true AND mediaDevices:seed is non-zero; every
// media-device hook (browser phantoms, the device-id fold, the renderer's
// list and track label) uses this one rule (S3b).
uint32_t ActiveMediaDevicesSeed(const ConfigScope& scope);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_DEVICE_IDS_H_

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

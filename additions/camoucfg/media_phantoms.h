// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_MEDIA_PHANTOMS_H_
#define COMPONENTS_CAMOUCFG_MEDIA_PHANTOMS_H_

#include <string>
#include <string_view>
#include <vector>

namespace camoucfg {

// One raw (pre-HMAC) enumerate entry for a claimed device the host lacks
// (S3). Chrome's TranslateMediaDeviceInfo hashes device_id and group_id, so
// neither raw string reaches a page.
struct PhantomDevice {
  std::string device_id;
  std::string label;
  std::string group_id;
};

// The raw entries Chrome lists for one device of `kind` ("audioinput",
// "videoinput" or "audiooutput"). On Windows an audio kind starts with the
// "default" and "communications" sentinels (audio_manager_win.cc), labelled
// "<default_name> - <label>" and "<communications_name> - <label>" and sharing
// the device's group (audio_manager_base.cc). The names are Chrome's
// localized AudioDeviceDescription names, passed in by the caller.
std::vector<PhantomDevice> PhantomDevicesFor(std::string_view kind,
                                             std::string_view label,
                                             bool windows,
                                             std::string_view default_name,
                                             std::string_view communications_name);

// True for the raw id of a phantom device (not its sentinels or its group).
bool IsPhantomDeviceId(std::string_view raw_id);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_MEDIA_PHANTOMS_H_

// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/media_phantoms.h"

#include "base/strings/strcat.h"

namespace camoucfg {
namespace {
constexpr char kPhantomPrefix[] = "camou-phantom-";
constexpr char kPhantomGroupPrefix[] = "camou-phantom-group-";
}  // namespace

std::vector<PhantomDevice> PhantomDevicesFor(std::string_view kind,
                                             std::string_view label,
                                             bool windows,
                                             std::string_view default_name,
                                             std::string_view communications_name) {
  const std::string group = base::StrCat({kPhantomGroupPrefix, kind});
  std::vector<PhantomDevice> out;
  if (windows && kind != "videoinput") {
    out.push_back({"default", base::StrCat({default_name, " - ", label}), group});
    out.push_back({"communications",
                   base::StrCat({communications_name, " - ", label}), group});
  }
  out.push_back({base::StrCat({kPhantomPrefix, kind}), std::string(label), group});
  return out;
}

bool IsPhantomDeviceId(std::string_view raw_id) {
  return raw_id.starts_with(kPhantomPrefix) &&
         !raw_id.starts_with(kPhantomGroupPrefix);
}

}  // namespace camoucfg

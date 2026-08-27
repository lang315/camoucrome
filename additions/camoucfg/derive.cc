// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/derive.h"

#include <array>
#include <optional>
#include <string>

#include "components/camoucfg/keys.h"

namespace camoucfg {
namespace {

struct OsForms {
  OsFamily family;
  std::string_view ua_ch_platform;  // navigator.userAgentData.platform
  std::string_view os_info;         // the UA string's OS segment
  std::string_view marker;          // the token that identifies os_info
};

// Order matters for `marker`. "Linux; Android 10; K" and
// "X11; CrOS x86_64 14541.0.0" both contain text a Linux match would also
// accept, so the more specific markers are tested first.
// DeriveTest.AndroidIsNotMistakenForLinux asserts that ordering rather than
// leaving it to whoever next edits this array. Its ChromeOS sibling does not:
// "X11; CrOS x86_64 14541.0.0" contains no "Linux", so only the Android case
// can fail if this order changes. The test file says the same beside both.
//
// The os_info and ua_ch_platform strings are Chromium's own, from
// GetUnifiedPlatform() and GetPlatformForUAMetadata() in
// components/embedder_support/user_agent_utils.cc, so a repaired value is
// byte-identical to what a real BRANDED Chrome on that OS emits.
//
// "Branded" is not a hedge. GetPlatformForUAMetadata() returns "Chrome OS"
// only under BUILDFLAG(GOOGLE_CHROME_BRANDING) and "Chromium OS" otherwise,
// and this build is unbranded -- so the value below deliberately does NOT
// match what this binary's own copy of that function returns. "Chrome OS" is
// still the right repair target, because SP7 decision D1 has the fork present
// as Chrome; the earlier wording claimed these strings came back from this
// tree's function, which is false and was unfalsifiable by any test.
//
// Consequence worth knowing: "Chromium OS" as a configured value resolves to
// kUnknown and is therefore never validated.
constexpr std::array<OsForms, 5> kForms = {{
    {OsFamily::kAndroid, "Android", "Linux; Android 10; K", "Android"},
    {OsFamily::kChromeOs, "Chrome OS", "X11; CrOS x86_64 14541.0.0", "CrOS"},
    {OsFamily::kWindows, "Windows", "Windows NT 10.0; Win64; x64", "Windows NT"},
    {OsFamily::kMac, "macOS", "Macintosh; Intel Mac OS X 10_15_7", "Macintosh"},
    {OsFamily::kLinux, "Linux", "X11; Linux x86_64", "Linux"},
}};

}  // namespace

OsFamily OsFamilyFromUaChPlatform(std::string_view ua_ch_platform) {
  for (const OsForms& form : kForms) {
    if (ua_ch_platform == form.ua_ch_platform) {
      return form.family;
    }
  }
  return OsFamily::kUnknown;
}

OsFamily OsFamilyFromOsInfo(std::string_view os_info) {
  for (const OsForms& form : kForms) {
    if (os_info.find(form.marker) != std::string_view::npos) {
      return form.family;
    }
  }
  return OsFamily::kUnknown;
}

std::string_view CanonicalOsInfoFor(OsFamily os) {
  for (const OsForms& form : kForms) {
    if (form.family == os) {
      return form.os_info;
    }
  }
  return {};
}

std::string_view CanonicalUaChPlatformFor(OsFamily os) {
  for (const OsForms& form : kForms) {
    if (form.family == os) {
      return form.ua_ch_platform;
    }
  }
  return {};
}

OsFamily ClaimedOs(const ConfigScope& scope) {
  // osInfo first: it lands in the user-agent string, the surface a detector
  // reads first. An osInfo that is set but unrecognised falls through to
  // platform rather than answering kUnknown, so one malformed key does not
  // hide a well-formed one.
  if (std::optional<std::string> os_info = GetString(scope, keys::kUaOsInfo)) {
    OsFamily from_os_info = OsFamilyFromOsInfo(*os_info);
    if (from_os_info != OsFamily::kUnknown) {
      return from_os_info;
    }
  }
  if (std::optional<std::string> platform =
          GetString(scope, keys::kUaPlatform)) {
    return OsFamilyFromUaChPlatform(*platform);
  }
  return OsFamily::kUnknown;
}

}  // namespace camoucfg

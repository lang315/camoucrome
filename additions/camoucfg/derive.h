// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_DERIVE_H_
#define COMPONENTS_CAMOUCFG_DERIVE_H_

#include <string_view>

#include "components/camoucfg/mask_config.h"

// Values that are a function of other values.
//
// Conventions: a derived value gets no configuration key of its own, because
// an independent override creates the opportunity for incoherence rather than
// removing it. Everything declared here is computed, never configured.

namespace camoucfg {

enum class OsFamily {
  kUnknown,
  kWindows,
  kMac,
  kLinux,
  kAndroid,
  kChromeOs,
};

// The UA-CH platform token, as `navigator.userAgentData.platform` reports it
// and as Sec-CH-UA-Platform carries it. A closed set: anything else is
// kUnknown rather than a guess, because a key holding a typo must not silently
// resolve to a plausible operating system.
OsFamily OsFamilyFromUaChPlatform(std::string_view ua_ch_platform);

// The OS segment of a user-agent string -- what `ua:osInfo` holds, e.g.
// "Windows NT 10.0; Win64; x64". Not a whole user agent.
//
// This is the ONLY place in the project permitted to look at that text. SP1's
// spec forbids every sub-project from deriving the claimed OS locally, and
// conventions assigns the single derivation here, because two derivations of
// one fact are two chances to disagree.
OsFamily OsFamilyFromOsInfo(std::string_view os_info);

// The canonical spelling of each form, for repairs.
//
// The os_info column is Chromium's own literal from GetUnifiedPlatform();
// the ua_ch_platform column is from GetPlatformForUAMetadata(). Both live in
// components/embedder_support/user_agent_utils.cc, so a repaired value is
// byte-identical to what a real BRANDED Chrome on that OS emits -- not
// something this project invented, and, for kChromeOs, not what this
// (unbranded) binary's own copy of GetPlatformForUAMetadata() returns
// either; see the kForms comment in derive.cc for why that distinction
// matters. kUnknown yields the empty string in both.
std::string_view CanonicalOsInfoFor(OsFamily os);
std::string_view CanonicalUaChPlatformFor(OsFamily os);

// The operating system this configuration is claiming.
//
// `ua:osInfo` is consulted first because it lands in the user-agent string,
// which is the surface a detector reads first; `ua:platform` is the fallback.
// With neither set the answer is kUnknown -- meaning "not claiming anything",
// which is different from claiming the host's real OS. A caller that needs the
// real one should ask the platform, not this function.
OsFamily ClaimedOs(const ConfigScope& scope);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_DERIVE_H_

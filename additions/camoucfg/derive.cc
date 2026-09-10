// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/derive.h"

#include <array>
#include <cstdint>
#include <cstdlib>
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

// SplitMix64 finalizer (Vigna 2015), used as a stateless mixer of one 64-bit
// word. mouse_trajectories.cc has a twin, but that one is a stateful *stream*
// object; this is a stateless function. Two 3-line finalizers are not worth a
// shared header -- extract one only if a third caller appears.
uint64_t Mix64(uint64_t z) {
  z += 0x9E3779B97F4A7C15ULL;
  z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
  z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
  return z ^ (z >> 31);
}

// FNV-1a 64 of the (short) domain string, so "canvas", "audio", "fontmetric"
// seed uncorrelated streams from a single config seed.
uint64_t DomainHash(std::string_view domain) {
  uint64_t h = 0xCBF29CE484222325ULL;
  for (char c : domain) {
    h ^= static_cast<uint8_t>(c);
    h *= 0x100000001B3ULL;
  }
  return h;
}

// One pseudo-random 64-bit word for (seed, domain, index). Mix64(index) first
// so adjacent indices don't produce trivially related inputs before the outer
// mix.
uint64_t Draw(uint64_t seed, std::string_view domain, uint64_t index) {
  return Mix64(seed ^ DomainHash(domain) ^ Mix64(index));
}

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

std::string_view CanonicalNavigatorPlatformFor(OsFamily os) {
  // navigator.platform does not fit kForms: real Chrome reports a fixed string
  // that is NOT the UA-CH platform token -- "Win32" (not "Windows"), "MacIntel"
  // (not "macOS"), "Linux x86_64" (not "Linux"). These are the FROZEN per-OS
  // literals GetReducedNavigatorPlatform() (navigator_base.cc) returns under the
  // reduced User-Agent, which is the live path NavigatorBase::platform() serves
  // and the default in a modern Chrome. Freezing them independent of the host's
  // real architecture is the whole point of UA reduction, so "Linux x86_64" is
  // what a real reduced Chrome reports on ANY Linux, any arch -- there is a
  // single byte-identical value for the Linux family after all, and deriving it
  // satisfies the same discipline CanonicalUaChPlatformFor holds. (The
  // non-reduced navigator_id.cc #else builds "Linux <arch>" from uname, but that
  // branch is compiled out on every desktop target and is not what runs.)
  // kUnknown -> empty: no OS is claimed, so the caller keeps the host's own
  // value rather than inventing one.
  //
  // These are a hand-kept copy of GetReducedNavigatorPlatform()'s literals with
  // no build-time tie to it, and DeriveTest pins them against this copy -- so an
  // upstream change to the frozen reduced strings would pass the unit test. The
  // guard against that drift is the end-to-end RP-* cases in
  // verify_navplatform_derive.py, which read the real reduced path for Win/Mac/
  // Android, not the unit test.
  switch (os) {
    case OsFamily::kWindows:
      return "Win32";
    case OsFamily::kMac:
      return "MacIntel";
    case OsFamily::kLinux:
    case OsFamily::kChromeOs:
      return "Linux x86_64";
    case OsFamily::kAndroid:
      return "Linux armv8l";
    case OsFamily::kUnknown:
      return {};
  }
  return {};  // GCC: enum switch is exhaustive but control-flow analysis needs it.
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

int32_t DeriveDelta(uint64_t seed, std::string_view domain, uint64_t index,
                    int32_t bound) {
  if (bound == 0) {
    return 0;
  }
  const uint64_t b = static_cast<uint64_t>(
      std::abs(static_cast<int64_t>(bound)));
  const uint64_t span = 2 * b + 1;  // -b .. +b inclusive
  const uint64_t r = Draw(seed, domain, index) % span;
  return static_cast<int32_t>(static_cast<int64_t>(r) - static_cast<int64_t>(b));
}

double DeriveUnit(uint64_t seed, std::string_view domain, uint64_t index) {
  // Top 53 bits map exactly onto a double's mantissa, as in mouse_trajectories.
  return (Draw(seed, domain, index) >> 11) * 0x1.0p-53;
}

}  // namespace camoucfg

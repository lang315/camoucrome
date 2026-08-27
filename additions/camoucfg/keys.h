// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_KEYS_H_
#define COMPONENTS_CAMOUCFG_KEYS_H_

#include <array>
#include <string_view>

// The registry of configuration keys.
//
// Its purpose is that keys stop being string literals at call sites. A key
// mistyped at one of two sites that should agree produces a surface that
// silently follows a knob nobody set, and neither the compiler nor a reviewer
// reading one file can see it.
//
// Conventions commits to generating this from settings/keys.json in SP6a. It
// is hand-written for now because generation buys exactly one thing beyond
// what a header of constants already buys — a single source feeding both these
// constants and the client's validation table — and the client's table does not
// exist yet. The SP6a task that introduces the generator must emit these same
// constant names so that no call site moves.
//
// Naming rule, from 00-conventions.md: a dot when the key mirrors a JavaScript
// property path exactly, a colon when it names a synthetic namespace with no
// direct JS counterpart. A value derived from another gets no key at all.

namespace camoucfg::keys {

// The OS segment of the user-agent string, e.g. "Windows NT 10.0; Win64; x64".
// Colon-namespaced: it names a substring of a JS property, not the property.
//
// It is deliberately not the whole user-agent string. A whole string carries a
// browser version, and Camoucrome never reports a version other than the one
// its binary was compiled from — so accepting one would mean either emitting a
// contradiction or parsing the string to extract the part we want, and SP1
// forbids parsing user agents locally.
inline constexpr char kUaOsInfo[] = "ua:osInfo";

// Not supported. Present in the registry so the startup validator can warn
// that it was ignored and name kUaOsInfo instead. Camoufox uses this key, so a
// config written for Camoufox will contain it; failing loudly beats producing
// an unspoofed user agent in silence.
inline constexpr char kNavigatorUserAgent[] = "navigator.userAgent";

// The blink::UserAgentMetadata fields. One colon namespace for one struct:
// `platform` and `mobile` do have JavaScript counterparts, but `architecture`,
// `bitness`, `platformVersion`, `model` and `wow64` are reachable only through
// getHighEntropyValues() and are not properties at all. Splitting one struct
// across two naming conventions would be worse than a namespace that is a
// little loose.
//
// Absent from this list on purpose: `brands`, `fullVersionList` and
// `formFactors`. The first two carry the version, which is never spoofed. The
// third is derived from `mobile` by GetFormFactorsClientHint(), and conventions
// gives a derived value no key of its own.
inline constexpr char kUaDataPlatform[] = "navigator.uaData:platform";
inline constexpr char kUaDataPlatformVersion[] =
    "navigator.uaData:platformVersion";
inline constexpr char kUaDataArchitecture[] = "navigator.uaData:architecture";
inline constexpr char kUaDataBitness[] = "navigator.uaData:bitness";
inline constexpr char kUaDataModel[] = "navigator.uaData:model";
inline constexpr char kUaDataMobile[] = "navigator.uaData:mobile";
inline constexpr char kUaDataWow64[] = "navigator.uaData:wow64";

// Every key above. A new constant must be added here too, which is what makes
// the uniqueness test meaningful.
inline constexpr std::array<std::string_view, 9> kAllKeys = {
    kUaOsInfo,          kNavigatorUserAgent,    kUaDataPlatform,
    kUaDataPlatformVersion, kUaDataArchitecture, kUaDataBitness,
    kUaDataModel,       kUaDataMobile,          kUaDataWow64,
};

}  // namespace camoucfg::keys

#endif  // COMPONENTS_CAMOUCFG_KEYS_H_

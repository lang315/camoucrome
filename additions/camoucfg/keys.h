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
// KNOWN LIMITATION: one value cannot express both user-agent forms. Chromium
// emits either the reduced or the full string, and the substitution point sits
// below that choice, so whichever form the build picked gets this value whole.
// macOS is the clearest case -- reduced is the frozen literal
// "Macintosh; Intel Mac OS X 10_15_7" while full carries the real version,
// "... 14_5_0" -- so a value written for one form is wrong for the other.
//
// Latent today, because a given build emits one form and a profile is written
// for that build. It becomes live when profiles are shared across builds that
// differ. SP6's generator owns it: it knows which build a profile targets, and
// having the browser translate between forms would mean parsing this value,
// which SP1 forbids for the same reason it refuses navigator.userAgent.
inline constexpr char kUaOsInfo[] = "ua:osInfo";

// SP0's tracer-bullet surface, read in NavigatorBase::hardwareConcurrency()
// and probed once at startup in BrowserMainLoop::EarlyInitialization().
//
// It predates this registry, so both of those sites were written with the
// string literal. That is exactly what the registry exists to end -- a key
// mistyped at one of two sites that must agree is invisible to the compiler
// and to a reviewer reading either file alone. Listing it here makes the
// registry complete.
//
// Both call sites now use this constant: browser_main_loop.cc and
// navigator_base.cc. They are in different processes and must agree, which is
// the whole reason the key is here rather than typed twice.
inline constexpr char kNavigatorHardwareConcurrency[] =
    "navigator.hardwareConcurrency";

// Not supported. Present in the registry so the startup validator can warn
// that it was ignored and name kUaOsInfo instead. Camoufox uses this key, so a
// config written for Camoufox will contain it; failing loudly beats producing
// an unspoofed user agent in silence.
inline constexpr char kNavigatorUserAgent[] = "navigator.userAgent";

// The blink::UserAgentMetadata fields, in one fully synthetic `ua:` namespace
// alongside kUaOsInfo above.
//
// An earlier draft spelled these "navigator.uaData:platform". A reviewer caught
// that `navigator.uaData` is not a property path at all -- the real API is
// `navigator.userAgentData` -- so the dot segment promised a JS path that does
// not resolve, which is exactly what the conventions naming rule exists to stop.
//
// The fix is not to lengthen it to `navigator.userAgentData:`. Most of this
// struct is not a property under any spelling: `architecture`, `bitness`,
// `platformVersion`, `model` and `wow64` are reachable only through
// getHighEntropyValues(), and `mobile` and `platform` reach the wire as
// Sec-CH-UA-* headers whether or not any script ever reads them. A dotted
// prefix would claim a correspondence that holds for two of seven members.
//
// So: `navigator.*` keys are reserved for values that mirror a real JS property
// path exactly, which SP1b's keys do. Everything describing the UA identity
// itself lives under `ua:`, next to `webGl:` and `canvas:`. One namespace, one
// subject, no false promise.
//
// Absent from this list on purpose: `brands`, `fullVersionList` and
// `formFactors`. The first two carry the version, which is never spoofed. The
// third is derived from `mobile` by GetFormFactorsClientHint(), and conventions
// gives a derived value no key of its own.
inline constexpr char kUaPlatform[] = "ua:platform";
inline constexpr char kUaPlatformVersion[] = "ua:platformVersion";
inline constexpr char kUaArchitecture[] = "ua:architecture";
inline constexpr char kUaBitness[] = "ua:bitness";
inline constexpr char kUaModel[] = "ua:model";
inline constexpr char kUaMobile[] = "ua:mobile";
inline constexpr char kUaWow64[] = "ua:wow64";

// The humanized-cursor generator's knobs, in their own synthetic `humanize:`
// namespace -- none mirrors a JS property path. `humanize:` is a pure
// namespace with no bare `humanize` key, the same shape as `ua:` above.
inline constexpr char kHumanizeEnabled[] = "humanize:enabled";
inline constexpr char kHumanizeMinTime[] = "humanize:minTime";
inline constexpr char kHumanizeMaxTime[] = "humanize:maxTime";

// Cursor visibility. A separate namespace from `humanize:` on purpose: it is
// a rendering concern (a visible cursor overlay), not part of humanizing the
// movement path/timing itself.
inline constexpr char kShowCursor[] = "cursor:show";

// Every key above. A new constant must be added here too, which is what makes
// the uniqueness test meaningful.
inline constexpr std::array<std::string_view, 14> kAllKeys = {
    kUaOsInfo,
    kNavigatorHardwareConcurrency,
    kNavigatorUserAgent,
    kUaPlatform,
    kUaPlatformVersion,
    kUaArchitecture,
    kUaBitness,
    kUaModel,
    kUaMobile,
    kUaWow64,
    kHumanizeEnabled,
    kHumanizeMinTime,
    kHumanizeMaxTime,
    kShowCursor,
};

// The UA client-hint keys, without kUaOsInfo.
//
// The split is what the list is for. These seven reach
// navigator.userAgentData and the Sec-CH-UA-* headers; kUaOsInfo reaches the
// user-agent string. Setting any of these without kUaOsInfo produces a
// fingerprint that contradicts itself on two surfaces a page reads for free,
// so startup warns about exactly that combination and needs the group by name
// rather than as seven open-coded HasKey calls that a later key would silently
// fall out of.
inline constexpr std::array<std::string_view, 7> kUaMetadataKeys = {
    kUaPlatform, kUaPlatformVersion, kUaArchitecture, kUaBitness,
    kUaModel,    kUaMobile,          kUaWow64,
};

}  // namespace camoucfg::keys

#endif  // COMPONENTS_CAMOUCFG_KEYS_H_

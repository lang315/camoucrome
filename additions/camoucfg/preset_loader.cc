// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/preset_loader.h"

#include <algorithm>
#include <climits>
#include <cmath>
#include <iterator>
#include <optional>
#include <string>
#include <string_view>
#include <utility>

#include "base/logging.h"
#include "base/strings/string_number_conversions.h"
#include "components/camoucfg/derive.h"
#include "components/camoucfg/keys.h"

namespace camoucfg {

// Preset field -> configuration key.
//
//   milestone            (int)   compared with the fork's own; warning only
//   os                   (str)   UA-CH platform name: "Windows", "macOS",
//                                "Linux", "Android", "Chrome OS"
//                                -> ua:osInfo, ua:platform (canonical forms
//                                   from derive.h, the ones the validator
//                                   accepts as coherent)
//   platformVersion      (str)   -> ua:platformVersion
//   gpu.vendor           (str)   -> webGl:vendor, webGl2:vendor
//   gpu.renderer         (str)   -> webGl:renderer, webGl2:renderer
//   gpu.parameters       (dict)  -> webGl:parameters, webGl2:parameters
//                                   (same table on both contexts)
//   screen.width/height/availWidth/availHeight (int)
//                                -> screen.width/height/availWidth/availHeight
//   fonts                (list)  -> fonts:list
//   locale               (str)   -> locale:tag, navigator.language,
//                                   navigator.languages = [tag, primary]
//   timezone             (str)   -> timezone:id
//
// Deliberately not emitted, and why:
//   navigator.platform   derived from the claimed OS at read time already
//   screen.colorDepth, window.*, dpr
//                        window geometry is per instance; dpr has no key
//   canvas/audio/mediaDevices seeds
//                        per instance, never part of a device identity
//   sampleRate           no key by the SP4 decision
//   UA string, brands, fullVersionList, Sec-CH-UA
//                        version-bearing; produced by the fork's own
//                        milestone (spec 4.4), so a preset cannot go stale
//                        on them
namespace {

void CopyString(const base::DictValue& from, std::string_view field,
                base::DictValue& to, std::string_view key) {
  if (const std::string* s = from.FindString(field)) {
    to.Set(key, *s);
  }
}

// A whole number written as a double (1920.0) counts, as it does for the
// config getters; a fraction does not.
void CopyInt(const base::DictValue& from, std::string_view field,
             base::DictValue& to, std::string_view key) {
  if (std::optional<int> i = from.FindInt(field)) {
    to.Set(key, *i);
  } else if (std::optional<double> d = from.FindDouble(field);
             d && *d == std::trunc(*d) && std::abs(*d) <= INT_MAX) {
    to.Set(key, static_cast<int>(*d));
  }
}

void SetOsKeys(base::DictValue& out, OsFamily family) {
  out.Set(keys::kUaOsInfo, std::string(CanonicalOsInfoFor(family)));
  out.Set(keys::kUaPlatform, std::string(CanonicalUaChPlatformFor(family)));
}

// locale:tag, navigator.language, navigator.languages = [tag, primary].
void SetLocaleKeys(base::DictValue& out, const std::string& locale) {
  out.Set(keys::kLocaleTag, locale);
  out.Set(keys::kNavigatorLanguage, locale);
  base::ListValue languages;
  languages.Append(locale);
  std::string primary = locale.substr(0, locale.find('-'));
  if (primary != locale) {
    languages.Append(primary);
  }
  out.Set(keys::kNavigatorLanguages, std::move(languages));
}

}  // namespace

base::DictValue ExpandPreset(const base::DictValue& preset,
                             int fork_milestone) {
  base::DictValue out;

  // A field outside the table is the realistic mistake -- a typo, or a
  // CAMOU_CONFIG-shaped object passed as a preset -- and would otherwise be
  // silent, expanding to nothing.
  for (const auto [field, value] : preset) {
    static constexpr std::string_view kKnown[] = {
        "milestone", "os",     "platformVersion", "gpu",      "screen", "fonts",
        "locale",    "timezone", "dpr",          "sampleRate", "provenance"};
    if (std::find(std::begin(kKnown), std::end(kKnown), field) ==
        std::end(kKnown)) {
      LOG(WARNING) << "camoucfg: preset field '" << field
                   << "' is not one the loader knows; ignored";
    }
  }

  std::optional<int> milestone = preset.FindInt("milestone");
  if (!milestone.has_value() || *milestone != fork_milestone) {
    LOG(WARNING) << "camoucfg: preset milestone "
                 << (milestone ? base::NumberToString(*milestone)
                              : std::string("missing"))
                 << " differs from this build's " << fork_milestone
                 << "; its hardware and locale claims stay valid, no "
                 << "version-bearing field is taken from a preset";
  }

  if (const std::string* os = preset.FindString("os")) {
    OsFamily family = OsFamilyFromUaChPlatform(*os);
    if (family == OsFamily::kUnknown) {
      LOG(WARNING) << "camoucfg: preset os '" << *os
                   << "' is not a UA-CH platform name; no OS keys emitted";
    } else {
      SetOsKeys(out, family);
    }
  }
  CopyString(preset, "platformVersion", out, keys::kUaPlatformVersion);

  if (const base::DictValue* gpu = preset.FindDict("gpu")) {
    CopyString(*gpu, "vendor", out, keys::kWebGlVendor);
    CopyString(*gpu, "vendor", out, keys::kWebGl2Vendor);
    CopyString(*gpu, "renderer", out, keys::kWebGlRenderer);
    CopyString(*gpu, "renderer", out, keys::kWebGl2Renderer);
    if (const base::DictValue* params = gpu->FindDict("parameters")) {
      out.Set(keys::kWebGlParameters, params->Clone());
      out.Set(keys::kWebGl2Parameters, params->Clone());
    }
  }

  if (const base::DictValue* screen = preset.FindDict("screen")) {
    CopyInt(*screen, "width", out, keys::kScreenWidth);
    CopyInt(*screen, "height", out, keys::kScreenHeight);
    CopyInt(*screen, "availWidth", out, keys::kScreenAvailWidth);
    CopyInt(*screen, "availHeight", out, keys::kScreenAvailHeight);
  }

  if (const base::ListValue* fonts = preset.FindList("fonts")) {
    out.Set(keys::kFonts, fonts->Clone());
  }

  if (const std::string* locale = preset.FindString("locale")) {
    SetLocaleKeys(out, *locale);
  }

  CopyString(preset, "timezone", out, keys::kTimezoneId);
  return out;
}

void OverridePresetGroups(base::DictValue& expanded,
                          const base::DictValue& explicit_cfg) {
  // The OS pair: explicit osInfo decides first, as ClaimedOs does.
  OsFamily os = OsFamily::kUnknown;
  if (const std::string* v = explicit_cfg.FindString(keys::kUaOsInfo)) {
    os = OsFamilyFromOsInfo(*v);
  }
  if (os == OsFamily::kUnknown) {
    if (const std::string* v = explicit_cfg.FindString(keys::kUaPlatform)) {
      os = OsFamilyFromUaChPlatform(*v);
    }
  }
  if (os != OsFamily::kUnknown &&
      (expanded.contains(keys::kUaOsInfo) ||
       expanded.contains(keys::kUaPlatform))) {
    SetOsKeys(expanded, os);
  }

  // The locale triple, headed by the most specific explicit key.
  const std::string* head = nullptr;
  if (const base::ListValue* langs =
          explicit_cfg.FindList(keys::kNavigatorLanguages);
      langs && !langs->empty() && (*langs)[0].is_string()) {
    head = &(*langs)[0].GetString();
  } else if (const std::string* language =
                 explicit_cfg.FindString(keys::kNavigatorLanguage)) {
    head = language;
  } else if (const std::string* tag = explicit_cfg.FindString(keys::kLocaleTag)) {
    head = tag;
  }
  if (head && expanded.contains(keys::kLocaleTag)) {
    SetLocaleKeys(expanded, *head);
  }

  // The GPU identity: the preset gave both contexts one vendor and renderer,
  // so an explicit webGl:* string moves webGl2:* with it unless the author
  // set webGl2:* too (the merge then lets that key win).
  static constexpr std::pair<std::string_view, std::string_view> kGpuPairs[] = {
      {keys::kWebGlVendor, keys::kWebGl2Vendor},
      {keys::kWebGlRenderer, keys::kWebGl2Renderer}};
  for (const auto& [webgl, webgl2] : kGpuPairs) {
    if (const std::string* value = explicit_cfg.FindString(webgl);
        value && expanded.contains(webgl2) && !explicit_cfg.contains(webgl2)) {
      expanded.Set(webgl2, *value);
    }
  }
}

}  // namespace camoucfg

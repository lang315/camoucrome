// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/domain_validator.h"

#include <array>
#include <limits>

#include "base/strings/string_number_conversions.h"
#include "components/camoucfg/keys.h"

namespace camoucfg {
namespace {

struct DomainEntry {
  std::string_view key;
  // Both ends inclusive. The one consumer modelled so far, geoposition.cc's
  // ValidateGeoposition, bounds every axis with >= and <=, so an inclusive
  // [min, max] mirrors it exactly. A half-open axis (accuracy >= 0) sets max to
  // +infinity so only the lower bound can bite.
  double min;
  double max;
  std::string_view reason;
};

// Numeric domains that a downstream Chromium consumer ALREADY rejects. An entry
// earns its place only by mirroring such a rejection -- a value the browser
// itself would refuse -- never by general plausibility. Without this check an
// out-of-range value passes the config layer untouched and is dropped silently
// downstream, so the spoof no-ops and the author sees a stock result with no
// diagnostic.
//
// Geolocation is the one such consumer so far.
// services/device/public/cpp/geolocation/geoposition.cc, ValidateGeoposition():
// latitude in [-90, 90], longitude in [-180, 180], accuracy >= 0. timestamp is
// synthesized by the fork, never configured, so it has no key and no entry.
constexpr auto kDomains = std::to_array<DomainEntry>({
    {keys::kGeolocationLatitude, -90.0, 90.0, "latitude must be in [-90, 90]"},
    {keys::kGeolocationLongitude, -180.0, 180.0,
     "longitude must be in [-180, 180]"},
    {keys::kGeolocationAccuracy, 0.0, std::numeric_limits<double>::infinity(),
     "accuracy must be >= 0"},
});

}  // namespace

std::optional<DomainViolation> CheckDomain(std::string_view key, double value) {
  for (const DomainEntry& entry : kDomains) {
    if (entry.key != key) {
      continue;
    }
    // A NaN value fails both comparisons and is reported -- which is correct, a
    // NaN coordinate is not in any range.
    if (value >= entry.min && value <= entry.max) {
      return std::nullopt;
    }
    DomainViolation violation;
    violation.key = std::string(key);
    violation.value = base::NumberToString(value);
    violation.reason = std::string(entry.reason);
    return violation;
  }
  return std::nullopt;  // No registered domain for this key.
}

std::vector<DomainViolation> ValidateDomains(const ConfigScope& scope) {
  std::vector<DomainViolation> violations;
  for (const DomainEntry& entry : kDomains) {
    std::optional<double> value = GetDouble(scope, entry.key);
    if (!value.has_value()) {
      continue;  // Absent, or wrong type (the getter already warned).
    }
    std::optional<DomainViolation> violation = CheckDomain(entry.key, *value);
    if (violation.has_value()) {
      violations.push_back(*violation);
    }
  }
  return violations;
}

}  // namespace camoucfg

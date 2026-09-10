// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/domain_validator.h"

#include <limits>
#include <optional>

#include "components/camoucfg/keys.h"
#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg {
namespace {

// CheckDomain is pure -- it reads no configuration -- so unlike
// CoherenceValidatorTest these cases run in a plain filter, one process for all
// of them, and can assert boundaries with literals.

TEST(DomainValidatorTest, LatitudeBoundariesInclusive) {
  EXPECT_FALSE(CheckDomain(keys::kGeolocationLatitude, 0.0).has_value());
  // The bound is >= / <=, so the endpoints themselves are valid.
  EXPECT_FALSE(CheckDomain(keys::kGeolocationLatitude, -90.0).has_value());
  EXPECT_FALSE(CheckDomain(keys::kGeolocationLatitude, 90.0).has_value());
  // Just outside is a violation, on both ends.
  EXPECT_TRUE(CheckDomain(keys::kGeolocationLatitude, -90.0001).has_value());
  EXPECT_TRUE(CheckDomain(keys::kGeolocationLatitude, 90.0001).has_value());
  // The motivating case.
  EXPECT_TRUE(CheckDomain(keys::kGeolocationLatitude, 91.0).has_value());
}

TEST(DomainValidatorTest, LongitudeBoundariesInclusive) {
  EXPECT_FALSE(CheckDomain(keys::kGeolocationLongitude, 0.0).has_value());
  EXPECT_FALSE(CheckDomain(keys::kGeolocationLongitude, -180.0).has_value());
  EXPECT_FALSE(CheckDomain(keys::kGeolocationLongitude, 180.0).has_value());
  EXPECT_TRUE(CheckDomain(keys::kGeolocationLongitude, -180.0001).has_value());
  EXPECT_TRUE(CheckDomain(keys::kGeolocationLongitude, 180.0001).has_value());
}

TEST(DomainValidatorTest, AccuracyLowerBoundOnly) {
  // accuracy >= 0: zero is valid, any positive is valid, negative is not.
  EXPECT_FALSE(CheckDomain(keys::kGeolocationAccuracy, 0.0).has_value());
  EXPECT_FALSE(CheckDomain(keys::kGeolocationAccuracy, 1000000.0).has_value());
  EXPECT_TRUE(CheckDomain(keys::kGeolocationAccuracy, -1e-9).has_value());
}

TEST(DomainValidatorTest, DeviceMemoryBoundariesInclusive) {
  EXPECT_FALSE(CheckDomain(keys::kNavigatorDeviceMemory, 0.25).has_value());
  EXPECT_FALSE(CheckDomain(keys::kNavigatorDeviceMemory, 8.0).has_value());
  // The motivating cases: what the pool says and Chrome never does.
  EXPECT_TRUE(CheckDomain(keys::kNavigatorDeviceMemory, 16.0).has_value());
  EXPECT_TRUE(CheckDomain(keys::kNavigatorDeviceMemory, 32.0).has_value());
  EXPECT_TRUE(CheckDomain(keys::kNavigatorDeviceMemory, 0.0).has_value());
}

TEST(DomainValidatorTest, ReportNamesKeyValueAndRange) {
  std::optional<DomainViolation> v =
      CheckDomain(keys::kGeolocationLatitude, 91.0);
  ASSERT_TRUE(v.has_value());
  EXPECT_EQ(v->key, keys::kGeolocationLatitude);
  EXPECT_EQ(v->value, "91");
  EXPECT_FALSE(v->reason.empty());
}

TEST(DomainValidatorTest, NaNIsAViolation) {
  // domain_validator.cc claims a NaN value is reported, and that this mirrors
  // ValidateGeoposition (NaN >= -90. is also false there). Lock the claim.
  // NaN cannot actually arrive through CAMOU_CONFIG -- base::JSONReader rejects
  // NaN/Infinity literals -- so this is the only place the branch is exercised;
  // it also drives base::NumberToString(NaN) inside the violation constructor.
  EXPECT_TRUE(CheckDomain(keys::kGeolocationLatitude,
                          std::numeric_limits<double>::quiet_NaN())
                  .has_value());
}

TEST(DomainValidatorTest, KeyWithNoRegisteredDomainIsNeverAViolation) {
  // A key that has no numeric domain is not this check's business, whatever the
  // value -- it must not be reported.
  EXPECT_FALSE(CheckDomain(keys::kNavigatorUserAgent, 91.0).has_value());
  EXPECT_FALSE(CheckDomain("not:a:key", -999.0).has_value());
}

}  // namespace
}  // namespace camoucfg

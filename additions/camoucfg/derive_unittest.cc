// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/derive.h"

#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg {
namespace {

TEST(DeriveTest, RecognisesEachUaChPlatformString) {
  EXPECT_EQ(OsFamilyFromUaChPlatform("Windows"), OsFamily::kWindows);
  EXPECT_EQ(OsFamilyFromUaChPlatform("macOS"), OsFamily::kMac);
  EXPECT_EQ(OsFamilyFromUaChPlatform("Linux"), OsFamily::kLinux);
  EXPECT_EQ(OsFamilyFromUaChPlatform("Android"), OsFamily::kAndroid);
  EXPECT_EQ(OsFamilyFromUaChPlatform("Chrome OS"), OsFamily::kChromeOs);
}

// Anything outside the closed set is unknown, not a guess. A key holding a
// typo must not silently resolve to a plausible operating system, because a
// plausible wrong answer is worse here than no answer: the validator would
// then compare two values it believes it understands.
TEST(DeriveTest, UnrecognisedUaChPlatformIsUnknown) {
  EXPECT_EQ(OsFamilyFromUaChPlatform("windows"), OsFamily::kUnknown);
  EXPECT_EQ(OsFamilyFromUaChPlatform("Win32"), OsFamily::kUnknown);
  EXPECT_EQ(OsFamilyFromUaChPlatform(""), OsFamily::kUnknown);
}

TEST(DeriveTest, RecognisesOsInfoSegments) {
  EXPECT_EQ(OsFamilyFromOsInfo("Windows NT 10.0; Win64; x64"),
            OsFamily::kWindows);
  EXPECT_EQ(OsFamilyFromOsInfo("Macintosh; Intel Mac OS X 10_15_7"),
            OsFamily::kMac);
  EXPECT_EQ(OsFamilyFromOsInfo("X11; Linux x86_64"), OsFamily::kLinux);
  EXPECT_EQ(OsFamilyFromOsInfo("Linux; Android 10; K"), OsFamily::kAndroid);
  EXPECT_EQ(OsFamilyFromOsInfo("X11; CrOS x86_64 14541.0.0"),
            OsFamily::kChromeOs);
  EXPECT_EQ(OsFamilyFromOsInfo("nonsense"), OsFamily::kUnknown);
}

// The ordering hazard in kForms, asserted rather than left to reading order.
//
// These two assertions are NOT equally load-bearing, and saying so matters
// more than having both. Verified by mutation before this file was committed:
// moving the Linux entry to the front of kForms fails the Android assertion
// and passes the ChromeOS one, because "Linux; Android 10; K" contains the
// token "Linux" while "X11; CrOS x86_64 14541.0.0" does not.
//
// So the Android case guards the current ordering. The ChromeOS case guards a
// future change to the canonical string -- real ChromeOS user agents are
// sometimes spelled "X11; CrOS Linux x86_64", and if that form is ever adopted
// here this assertion starts doing work. Kept for that reason, and labelled so
// nobody reads it as evidence the ordering is tested twice.
TEST(DeriveTest, AndroidIsNotMistakenForLinux) {
  EXPECT_NE(OsFamilyFromOsInfo("Linux; Android 10; K"), OsFamily::kLinux);
}

TEST(DeriveTest, ChromeOsIsNotMistakenForLinux) {
  EXPECT_NE(OsFamilyFromOsInfo("X11; CrOS x86_64 14541.0.0"), OsFamily::kLinux);
}

// A repaired value must be byte-identical to what a real Chrome on that OS
// emits, which is why the canonical strings are Chromium's own literals from
// GetUnifiedPlatform() rather than something typed here. Round-tripping is
// what keeps the two columns of kForms in step.
TEST(DeriveTest, CanonicalFormsRoundTrip) {
  for (OsFamily os : {OsFamily::kWindows, OsFamily::kMac, OsFamily::kLinux,
                      OsFamily::kAndroid, OsFamily::kChromeOs}) {
    EXPECT_EQ(OsFamilyFromOsInfo(CanonicalOsInfoFor(os)), os);
    EXPECT_EQ(OsFamilyFromUaChPlatform(CanonicalUaChPlatformFor(os)), os);
  }
}

TEST(DeriveTest, CanonicalFormsOfUnknownAreEmpty) {
  EXPECT_TRUE(CanonicalOsInfoFor(OsFamily::kUnknown).empty());
  EXPECT_TRUE(CanonicalUaChPlatformFor(OsFamily::kUnknown).empty());
}

// ClaimedOs() is absent on purpose. It reads configuration, which camoucfg
// latches once per process (mask_config.cc:18), so exercising it needs its own
// process invocation with CAMOU_CONFIG set externally. The coherence validator
// covers it that way; adding a sixth per-process invocation here for one
// function would buy nothing the validator's tests do not already give.

}  // namespace
}  // namespace camoucfg

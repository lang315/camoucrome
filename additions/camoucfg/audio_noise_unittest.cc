// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/audio_noise.h"

#include <cmath>
#include <cstdint>
#include <vector>

#include "base/containers/span.h"
#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg {
namespace {

// A deterministic non-uniform sample buffer to perturb. A uniform buffer
// hides content-dependence bugs, so vary the values (and include a zero, for
// the relative-mode "zero stays zero" case).
std::vector<float> Buffer(size_t n) {
  std::vector<float> v(n);
  for (size_t i = 0; i < n; ++i) {
    v[i] = static_cast<float>(std::sin(static_cast<double>(i) * 0.37));
  }
  if (n > 0) {
    v[0] = 0.0f;  // guarantee a zero sample for the relative-mode case
  }
  return v;
}

TEST(PerturbAudioTest, SeedZeroIsNoOp) {
  auto a = Buffer(64);
  auto orig = a;
  PerturbAudioSamples(base::span(a), /*seed=*/0, "audio", /*epsilon=*/0.01f,
                      /*relative=*/false);
  EXPECT_EQ(a, orig);  // byte-identical to stock when spoof is off
}

TEST(PerturbAudioTest, SameInputsGiveSameOutput) {
  // The determinism guarantee: two reads of the same buffer reproduce.
  auto a = Buffer(64);
  auto b = Buffer(64);
  PerturbAudioSamples(base::span(a), /*seed=*/12345, "audio",
                      /*epsilon=*/0.01f, /*relative=*/false);
  PerturbAudioSamples(base::span(b), 12345, "audio", 0.01f, false);
  EXPECT_EQ(a, b);
}

TEST(PerturbAudioTest, EveryDeltaIsWithinEpsilonAdditive) {
  auto a = Buffer(64);
  auto orig = a;
  constexpr float kEpsilon = 0.01f;
  PerturbAudioSamples(base::span(a), 12345, "audio", kEpsilon,
                      /*relative=*/false);
  bool changed = false;
  for (size_t i = 0; i < a.size(); ++i) {
    const float d = a[i] - orig[i];
    EXPECT_GE(d, -kEpsilon);
    EXPECT_LE(d, kEpsilon);
    if (d != 0.0f) {
      changed = true;
    }
  }
  EXPECT_TRUE(changed) << "no sample was perturbed";
}

TEST(PerturbAudioTest, DifferentSeedsGiveDifferentOutputs) {
  auto a = Buffer(64);
  auto b = Buffer(64);
  PerturbAudioSamples(base::span(a), 111, "audio", 0.01f, false);
  PerturbAudioSamples(base::span(b), 222, "audio", 0.01f, false);
  EXPECT_NE(a, b);
}

TEST(PerturbAudioTest, RelativeModeKeepsZeroSampleAtZero) {
  auto a = Buffer(64);
  ASSERT_EQ(a[0], 0.0f);
  auto orig = a;
  PerturbAudioSamples(base::span(a), 12345, "audio", 0.05f,
                      /*relative=*/true);
  EXPECT_EQ(a[0], 0.0f) << "0 * (1 + delta) must stay exactly 0";
  // A non-zero sample should have changed.
  bool changed = false;
  for (size_t i = 1; i < a.size(); ++i) {
    if (a[i] != orig[i]) {
      changed = true;
      break;
    }
  }
  EXPECT_TRUE(changed) << "no non-zero sample was perturbed in relative mode";
}

TEST(PerturbAudioTest, AdditiveModeKeepsAllZeroBufferExactlyZero) {
  // Regression test: unconditional additive noise (samples[i] += delta) would
  // turn every element of a silent (all-zero) buffer into a small nonzero
  // value -- a targeted "does this browser tamper with audio buffers?" probe,
  // since a fresh, unrendered AudioBuffer is genuinely all-zero on stock.
  std::vector<float> a(64, 0.0f);
  PerturbAudioSamples(base::span(a), /*seed=*/777, "audio", /*epsilon=*/1e-4f,
                      /*relative=*/false);
  for (float v : a) {
    EXPECT_EQ(v, 0.0f) << "additive noise must preserve an all-zero buffer";
  }
}

TEST(PerturbAudioTest, AdditiveModeKeepsZeroSamplesExactWhilePerturbingRest) {
  // Mixed buffer: the zero sample must stay exactly 0.0, while non-zero
  // (real signal) samples are still perturbed -- the fix must not disable
  // additive noise on genuine signal.
  auto a = Buffer(64);
  ASSERT_EQ(a[0], 0.0f);
  auto orig = a;
  PerturbAudioSamples(base::span(a), 777, "audio", 0.01f, /*relative=*/false);
  EXPECT_EQ(a[0], 0.0f) << "additive mode must preserve an exact-zero sample";
  bool changed = false;
  for (size_t i = 1; i < a.size(); ++i) {
    if (a[i] != orig[i]) {
      changed = true;
      break;
    }
  }
  EXPECT_TRUE(changed) << "no non-zero sample was perturbed in additive mode";
}

TEST(PerturbAudioTest, DifferentBuffersGetDifferentNoiseFields) {
  // Content-hash fold: the SAME seed on two DIFFERENT buffers must diverge at
  // indices other than the one that differs, so an attacker cannot map the
  // field once and subtract it from every later readback.
  auto a = Buffer(64);
  auto b = Buffer(64);
  b[1] += 0.5f;  // change content elsewhere
  auto a_orig = a, b_orig = b;
  PerturbAudioSamples(base::span(a), 777, "audio", 0.01f, false);
  PerturbAudioSamples(base::span(b), 777, "audio", 0.01f, false);
  bool fields_differ = false;
  for (size_t i = 2; i < a.size(); ++i) {  // skip index 0 (zero) and index 1 (changed)
    const float da = a[i] - a_orig[i];
    const float db = b[i] - b_orig[i];
    if (da != db) {
      fields_differ = true;
      break;
    }
  }
  EXPECT_TRUE(fields_differ) << "noise field ignores content; map-and-subtract "
                               "would defeat it";
}

}  // namespace
}  // namespace camoucfg

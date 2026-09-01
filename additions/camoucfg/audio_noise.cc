// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/audio_noise.h"

#include <cstring>

#include "base/containers/span.h"
#include "components/camoucfg/derive.h"
#include "components/camoucfg/keys.h"

namespace camoucfg {

namespace {
// FNV-1a over the raw sample bytes -- same construction as canvas_noise.cc's
// ContentHash, so different buffers diverge and identical buffers reproduce.
uint64_t ContentHash(base::span<const float> samples) {
  uint64_t h = 1469598103934665603ULL;
  // float has no unique object representation (+0/-0 compare equal but
  // differ bitwise), so as_bytes() needs the explicit allow_nonunique_obj
  // opt-in. That's fine here: this hash only needs to be content-sensitive
  // and reproducible, not injective.
  base::span<const uint8_t> bytes =
      base::as_bytes(base::allow_nonunique_obj, samples);
  for (uint8_t b : bytes) {
    h ^= b;
    h *= 1099511628211ULL;
  }
  return h;
}
}  // namespace

void PerturbAudioSamples(base::span<float> samples, uint64_t seed,
                         std::string_view domain, float epsilon, bool relative) {
  if (seed == 0 || samples.empty() || epsilon == 0.0f) {
    return;
  }
  const uint64_t eseed = seed ^ ContentHash(samples);
  for (size_t i = 0; i < samples.size(); ++i) {
    const double u = DeriveUnit(eseed, domain, i);      // [0, 1)
    const float delta = static_cast<float>((u - 0.5) * 2.0) * epsilon;
    if (relative) {
      samples[i] *= (1.0f + delta);
    } else {
      samples[i] += delta;
    }
  }
}

void PerturbAudioFromConfig(base::span<float> samples, std::string_view domain,
                            float epsilon, bool relative,
                            const ConfigScope& scope) {
  const std::optional<uint32_t> seed = GetUint32(scope, keys::kAudioSeed);
  if (!seed || *seed == 0) {
    return;
  }
  PerturbAudioSamples(samples, static_cast<uint64_t>(*seed), domain, epsilon,
                      relative);
}

}  // namespace camoucfg

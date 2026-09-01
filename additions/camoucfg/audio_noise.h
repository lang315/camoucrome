// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_AUDIO_NOISE_H_
#define COMPONENTS_CAMOUCFG_AUDIO_NOISE_H_

#include <cstdint>
#include <string_view>

#include "base/containers/span.h"
#include "components/camoucfg/mask_config.h"

namespace camoucfg {

// Adds a deterministic, imperceptible per-sample delta to a float audio buffer,
// in place. A pure function of (samples, seed, domain, epsilon, relative): the
// same inputs yield the same output, so a re-read of the same buffer reproduces
// (the SP3 §4.3 reread-determinism property).
//
//   - seed == 0 is a no-op (rule 5): the buffer is left byte-identical.
//   - A content hash of the buffer is folded into the seed, so different buffers
//     get different noise fields while an identical buffer reproduces.
//   - delta_i = (DeriveUnit(eseed, domain, i) - 0.5) * 2 * epsilon.
//     relative == false: samples[i] += delta_i, UNLESS samples[i] == 0.0f, in
//       which case it is left exactly 0.0 (raw samples in [-1, 1]).
//     relative == true : samples[i] *= (1 + delta_i)  (magnitudes of any scale).
//   - Both modes preserve an exact-zero sample, so an all-silent buffer stays
//     byte-identical to stock.
//
// Caller responsibility for reread-determinism: perturb a buffer's backing store
// at most once (AudioBuffer guards with a flag), or perturb a per-frame-rebuilt
// buffer (AnalyserNode's magnitude_buffer_). Never re-perturb a store you already
// mutated -- the content hash would then re-derive a different field.
void PerturbAudioSamples(base::span<float> samples, uint64_t seed,
                         std::string_view domain, float epsilon, bool relative);

// Reads audio:seed from `scope` and calls PerturbAudioSamples. Absent or 0 seed
// is a no-op. This is the ONE place kAudioSeed is read.
void PerturbAudioFromConfig(base::span<float> samples, std::string_view domain,
                            float epsilon, bool relative,
                            const ConfigScope& scope);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_AUDIO_NOISE_H_

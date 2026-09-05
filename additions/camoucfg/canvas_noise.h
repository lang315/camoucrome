// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_CANVAS_NOISE_H_
#define COMPONENTS_CAMOUCFG_CANVAS_NOISE_H_

#include <cstddef>
#include <cstdint>
#include <string_view>

#include "components/camoucfg/mask_config.h"

namespace camoucfg {

// Applies deterministic readback noise to a tightly-packed 8-bit RGBA buffer,
// in place. A pure function of its arguments: the same (bytes, seed, density,
// strength) yields the same output, so a page reading the same canvas twice
// sees identical pixels and cannot detect the noise by re-rendering. This is
// the single most important property in SP3 (§4.3).
//
//   - seed == 0 is a no-op: the buffer is left byte-identical to stock, which
//     is how "no canvas:seed -> real value" (rule 5) is honoured.
//   - A content hash of the buffer is folded into the seed, so two different
//     drawings get different noise fields (an attacker cannot map the field
//     once and subtract it from every later readback), while a re-read of the
//     same drawing reproduces exactly (§7.3 decision A).
//   - RGB channels only; every 4th byte (alpha) is left untouched.
//   - `density` in [0, 1] is the fraction of RGB channels gated for
//     perturbation; density <= 0 or length < 4 is a no-op.
//   - `strength` bounds the per-channel delta: values land in
//     [-strength, +strength], clamped into [0, 255].
//
// Noise is applied on READBACK only, never at draw time -- callers pass a copy
// of the pixels leaving the canvas, never the canvas's own store.
void PerturbRgba(uint8_t* data, size_t length, uint64_t seed, double density,
                 int32_t strength);

// Reads canvas:seed / canvas:noiseDensity / canvas:noiseStrength from `scope`
// and calls PerturbRgba. This is the ONE place the canvas keys and their
// defaults (density 0.0005, strength 1) are read; every Blink readback site
// calls only this, never a key directly. Absent or zero canvas:seed is a
// no-op.
void PerturbRgbaFromConfig(uint8_t* data, size_t length,
                           const ConfigScope& scope);

// Grid-preserving, seed-keyed jitter of ONE TextMetrics readback (metric-jitter
// slice). Pure: the same (stock, seed, index, domain) yields the same output, so
// a page re-reading the same (text, font) sees identical metrics and cannot
// detect the jitter by re-measuring.
//   - seed == 0  -> stock unchanged (rule 5: no canvas:seed -> real value).
//   - stock == 0 -> stock unchanged (zero guard: real Chrome returns exact 0 for
//     empty ink / empty string / zero baseline; a non-zero there is a tell).
//   - integer stock -> stock + DeriveDelta(seed, domain, index, 1)      (integer grid).
//   - fractional    -> stock + DeriveDelta(seed, domain, index, 8)/64.0 (dyadic, <=0.125px).
// `domain` separates fields so each derives an independent delta from one seed.
// `index` is a caller-supplied content hash: for text-dependent fields
// hash(text)^hash(font); for font-constant fields hash(font) only (keeps them
// text-independent). See metric-jitter measurement §3-4.
double PerturbMetric(double stock, uint64_t seed, uint64_t index,
                     std::string_view domain);

// canvas:seed as a uint64 (0 if absent). The one place the metric path reads the
// seed key; Blink reads it once per measureText and calls PerturbMetric per field.
uint64_t CanvasSeed(const ConfigScope& scope);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_CANVAS_NOISE_H_

// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_CANVAS_NOISE_H_
#define COMPONENTS_CAMOUCFG_CANVAS_NOISE_H_

#include <array>
#include <cstddef>
#include <cstdint>
#include <string_view>

#include "components/camoucfg/mask_config.h"

namespace camoucfg {

// Readback noise, in place, on a `width` x `height` RGBA8 image whose rows are
// `row_bytes` apart. `source` is an unperturbed copy with the same geometry,
// and every eligibility test reads it, so the result does not depend on the
// order pixels are visited in. A pixel changes only if
//   - it is interior (it has four neighbours),
//   - its alpha is at least max(min_alpha, 1),
//   - it differs, in any of its four bytes, from each of its four neighbours.
// A solid region, a hard edge and a 1px line give every pixel a same-coloured
// neighbour, so they read as stock (S1). Each RGB channel is gated by
// `density` and moved by up to +-`strength`, clamped to [0, alpha]: for
// premultiplied data every result is a value stock can store at that alpha.
// `density` is the fraction of eligible pixels' RGB channels perturbed; the
// default is calibrated in measurements/2026-10-canvas-noise.md.
// Data that is not premultiplied passes min_alpha 255. Pure: a function of
// (seed, x, y, channel) and `source`. seed == 0, density <= 0 (or NaN), or
// strength <= 0 is a no-op.
void PerturbRgbaEdges(uint8_t* data, const uint8_t* source, size_t width,
                      size_t height, size_t row_bytes, uint64_t seed,
                      double density, int32_t strength, uint8_t min_alpha);

// A hash of a whole canvas's current contents (RGBA8, `row_bytes` apart),
// from an even sample of at most 65536 pixels plus the size.
uint64_t CanvasStateHash(const uint8_t* rgba, size_t width, size_t height,
                         size_t row_bytes);

// PerturbRgbaEdges over a tightly packed `width` x `height` RGBA8 rect (the
// WebGL readPixels buffer), neighbours read within the rect, with a hash of
// its first 1024 bytes folded into `seed` (review 2026-09-24 #23). Only
// opaque pixels change: a premultipliedAlpha:false context stores
// unpremultiplied values.
void PerturbRgba(uint8_t* data, size_t width, size_t height, uint64_t seed,
                 double density, int32_t strength);

// canvas:noiseDensity / canvas:noiseStrength with their defaults. The ONE
// place the canvas noise keys are read.
void CanvasNoiseParams(const ConfigScope& scope, double& density,
                       int32_t& strength);

// Reads canvas:seed / canvas:noiseDensity / canvas:noiseStrength from `scope`
// and calls PerturbRgba. The WebGL readPixels path; the canvas sites use
// NoisedCanvasImage (canvas_readback.h). Absent or zero canvas:seed is a no-op.
void PerturbRgbaFromConfig(uint8_t* data, size_t width, size_t height,
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

// The per-profile sub-pixel origin of canvas text (canvas noise redesign,
// target design): {dx, dy}, each in [0, 1), derived from canvas:seed alone
// (domain canvas-text-offset). {0, 0} for seed 0, so no seed draws as stock.
std::array<float, 2> TextOffset(uint64_t seed);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_CANVAS_NOISE_H_

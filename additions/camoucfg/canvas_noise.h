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

// Per-pixel readback-noise eligibility (canvas noise S2b). `cells` holds one
// byte per cell of (1 << shift) x (1 << shift) pixels, `stride` cells per
// row, in the same row order as the image; a pixel may change only if its
// cell is exactly kNoiseMaskAa. The mask covers `width` x `height` pixels and
// applies only to an image of that size. A default NoiseMask (cells ==
// nullptr) lets every pixel change.
inline constexpr uint8_t kNoiseMaskAa = 1;
inline constexpr uint8_t kNoiseMaskImported = 2;
struct NoiseMask {
  const uint8_t* cells = nullptr;
  size_t stride = 0;
  int shift = 0;
  size_t width = 0;
  size_t height = 0;
  // The buffer's origin inside the mask, for a region of the canvas: pixel
  // (x, y) of the buffer uses the mask cell of (x0 + x, y0 + y).
  size_t x0 = 0;
  size_t y0 = 0;
};

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
// Data that is not premultiplied passes min_alpha 255.
// Pure: the noise of a pixel is a function of (seed, its 3x3 neighbourhood in
// `source`, channel) -- no position and no whole-image state (canvas noise
// S2b), so one patch gets one noise wherever it is and whatever else the
// image holds. The patch is hashed in top-down row order; `bottom_up` says the
// buffer's rows run bottom-up (WebGL readPixels), so one image gets one field
// in either orientation. `mask` gates each pixel (see NoiseMask); a mask whose
// window (x0, y0, width, height) does not fit inside it, or a mask with
// `bottom_up`, makes the call a no-op. seed == 0, density <= 0 (or
// NaN), or strength <= 0 is a no-op.
void PerturbRgbaEdges(uint8_t* data, const uint8_t* source, size_t width,
                      size_t height, size_t row_bytes, uint64_t seed,
                      double density, int32_t strength, uint8_t min_alpha,
                      const NoiseMask& mask, bool bottom_up);

// PerturbRgbaEdges on `data` in place: the unperturbed rows it needs are
// kept in a two-row ring, so no copy of the buffer is made. Same field, byte
// for byte. Returns false, leaving `data` untouched, only when the ring (two
// rows) cannot be allocated.
bool PerturbRgbaEdgesInPlace(uint8_t* data, size_t width, size_t height,
                             size_t row_bytes, uint64_t seed, double density,
                             int32_t strength, uint8_t min_alpha,
                             const NoiseMask& mask, bool bottom_up);

// PerturbRgbaEdges over a `width` x `height` RGBA8 rect whose rows are
// `row_bytes` apart (the WebGL readPixels destination at its pack layout),
// neighbours read within the rect, no mask. The field depends only on each
// pixel's 3x3 patch, so row padding and stride do not change it. Only opaque
// pixels change: a premultipliedAlpha:false context stores unpremultiplied
// values. row_bytes < width * 4 is a no-op.
void PerturbRgba(uint8_t* data, size_t width, size_t height, size_t row_bytes,
                 uint64_t seed, double density, int32_t strength,
                 bool bottom_up);

// canvas:noiseDensity / canvas:noiseStrength with their defaults. The ONE
// place the canvas noise keys are read.
void CanvasNoiseParams(const ConfigScope& scope, double& density,
                       int32_t& strength);

// Reads canvas:seed / canvas:noiseDensity / canvas:noiseStrength from `scope`
// and calls PerturbRgba on bottom-up rows. The WebGL readPixels path; the canvas sites use
// NoisedCanvasImage (canvas_readback.h). Absent or zero canvas:seed is a no-op.
void PerturbRgbaFromConfig(uint8_t* data, size_t width, size_t height,
                           size_t row_bytes, const ConfigScope& scope);

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

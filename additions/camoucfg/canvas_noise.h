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

// Applies deterministic readback noise, in place, to a `width` x `height`
// RGBA8 rect whose rows are `row_bytes` apart and whose top-left pixel is
// canvas pixel (x0, y0). Pure: each channel's noise is a function of (seed,
// canvas x, canvas y, channel) only, so every readback of one canvas state --
// a full getImageData, a 1x1 getImageData, toDataURL -- agrees on every pixel.
// Callers fold a hash of the canvas state into `seed` (CanvasStateHash), so
// different drawings get different fields.
//
//   - seed == 0, density <= 0 (or NaN), or strength <= 0 is a no-op: the
//     buffer stays byte-identical to stock (rule 5).
//   - Only opaque pixels (alpha 255) change, and only their RGB. Stock never
//     shows RGB under alpha 0, and an unpremultiplied value under a partial
//     alpha lies on a grid a +-1 step would leave.
//   - `density` is the fraction of RGB channels perturbed, clamped to 1.
//   - `strength` bounds the per-channel delta, clamped to 255; values stay
//     in [0, 255].
//
// Noise is applied on READBACK only, never at draw time -- callers pass a copy
// of the pixels leaving the canvas, never the canvas's own store.
void PerturbRgbaAt(uint8_t* data, size_t width, size_t height,
                   size_t row_bytes, int64_t x0, int64_t y0, uint64_t seed,
                   double density, int32_t strength);

// A hash of a whole canvas's current contents (RGBA8, `row_bytes` apart),
// from an even sample of at most 65536 pixels plus the size.
uint64_t CanvasStateHash(const uint8_t* rgba, size_t width, size_t height,
                         size_t row_bytes);

// PerturbRgbaAt over a tightly-packed buffer treated as one row at (0, 0),
// with a hash of its first 1024 bytes folded into `seed`. The WebGL
// readPixels path, which has no canvas state to hash (review 2026-09-24 #23).
void PerturbRgba(uint8_t* data, size_t length, uint64_t seed, double density,
                 int32_t strength);

// Reads canvas:seed / canvas:noiseDensity / canvas:noiseStrength from `scope`
// and calls PerturbRgba (WebGL readPixels). The canvas readback sites use
// PerturbCanvasPixels (canvas_readback.h) instead. Absent or zero canvas:seed
// is a no-op.
void PerturbRgbaFromConfig(uint8_t* data, size_t length,
                           const ConfigScope& scope);

// Reads the canvas keys from `scope` and calls PerturbRgbaAt with
// `state_hash` folded into canvas:seed. Absent or zero canvas:seed is a
// no-op. Blink reaches it through PerturbCanvasPixels (canvas_readback.h).
void PerturbRgbaAtFromConfig(uint8_t* data, size_t width, size_t height,
                             size_t row_bytes, int64_t x0, int64_t y0,
                             uint64_t state_hash, const ConfigScope& scope);

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

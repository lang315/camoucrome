// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/canvas_mask.h"

#include <algorithm>
#include <utility>

#include "base/compiler_specific.h"
#include "base/containers/span.h"

namespace camoucfg {

CanvasNoiseMask::CanvasNoiseMask(size_t width, size_t height)
    : width_(width),
      height_(height),
      shift_(width * height > kMaxFullResPixels ? 2 : 0),
      stride_((width + (size_t{1} << shift_) - 1) >> shift_),
      rows_((height + (size_t{1} << shift_) - 1) >> shift_) {}

CanvasNoiseMask::~CanvasNoiseMask() = default;

void CanvasNoiseMask::Merge(const uint8_t* coverage, size_t coverage_stride,
                            int64_t left, int64_t top, size_t coverage_width,
                            size_t coverage_height, Kind kind) {
  if (coverage == nullptr || coverage_width == 0 || coverage_height == 0 ||
      coverage_stride < coverage_width) {
    return;
  }
  Apply(coverage, coverage_stride, left, top,
        left + static_cast<int64_t>(coverage_width),
        top + static_cast<int64_t>(coverage_height), kind);
}

void CanvasNoiseMask::MarkRect(int64_t left, int64_t top, int64_t width,
                               int64_t height, Kind kind) {
  if (width <= 0 || height <= 0) {
    return;
  }
  Apply(nullptr, 0, left, top, left + width, top + height, kind);
}

NoiseMask CanvasNoiseMask::view() const {
  return {cells_.empty() ? nullptr : cells_.data(), stride_, shift_, width_,
          height_};
}

void CanvasNoiseMask::Apply(const uint8_t* coverage, size_t coverage_stride,
                            int64_t left, int64_t top, int64_t right,
                            int64_t bottom, Kind kind) {
  const int64_t x0 = std::max<int64_t>(left, 0);
  const int64_t y0 = std::max<int64_t>(top, 0);
  const int64_t x1 = std::min<int64_t>(right, static_cast<int64_t>(width_));
  const int64_t y1 = std::min<int64_t>(bottom, static_cast<int64_t>(height_));
  if (x0 >= x1 || y0 >= y1) {
    return;
  }
  // SAFETY: the caller's coverage holds (bottom - top) rows of
  // `coverage_stride` bytes, the last at least (right - left) long.
  const base::span<const uint8_t> cov =
      coverage == nullptr
          ? base::span<const uint8_t>()
          : UNSAFE_BUFFERS(base::span<const uint8_t>(
                coverage, static_cast<size_t>(bottom - top - 1) *
                                  coverage_stride +
                              static_cast<size_t>(right - left)));
  auto at = [&](int64_t x, int64_t y) -> uint8_t {
    return cov.empty() ? 255
                       : cov[static_cast<size_t>(y - top) * coverage_stride +
                             static_cast<size_t>(x - left)];
  };
  bool changed = false;
  if ((kind == Kind::kSolidOpaque || kind == Kind::kClear) && !cells_.empty()) {
    // Clear each cell whose every canvas pixel is fully covered.
    const int64_t s = int64_t{1} << shift_;
    for (int64_t cy = y0 >> shift_; cy <= (y1 - 1) >> shift_; ++cy) {
      for (int64_t cx = x0 >> shift_; cx <= (x1 - 1) >> shift_; ++cx) {
        uint8_t& cell = cells_[static_cast<size_t>(cy) * stride_ +
                               static_cast<size_t>(cx)];
        if (cell == 0) {
          continue;
        }
        const int64_t px1 =
            std::min<int64_t>((cx + 1) * s, static_cast<int64_t>(width_));
        const int64_t py1 =
            std::min<int64_t>((cy + 1) * s, static_cast<int64_t>(height_));
        bool full = true;
        for (int64_t py = cy * s; py < py1 && full; ++py) {
          for (int64_t px = cx * s; px < px1 && full; ++px) {
            full = px >= x0 && px < x1 && py >= y0 && py < y1 &&
                   at(px, py) == 255;
          }
        }
        if (full) {
          if (cell == kNoiseMaskAa) {
            --aa_cells_;
          }
          cell = 0;
          changed = true;
        }
      }
    }
  }
  for (int64_t y = y0; y < y1; ++y) {
    for (int64_t x = x0; x < x1; ++x) {
      const uint8_t c = at(x, y);
      if (c == 0) {
        continue;
      }
      uint8_t bit = 0;
      switch (kind) {
        case Kind::kImported:
          bit = kNoiseMaskImported;
          break;
        case Kind::kAa:
          bit = kNoiseMaskAa;
          break;
        case Kind::kSolidOpaque:
        case Kind::kSolid:
        case Kind::kClear:
          bit = c == 255 ? 0 : kNoiseMaskAa;
          break;
      }
      if (bit == 0) {
        continue;
      }
      if (cells_.empty()) {
        cells_.assign(stride_ * rows_, 0);
      }
      uint8_t& cell = cells_[static_cast<size_t>(y >> shift_) * stride_ +
                             static_cast<size_t>(x >> shift_)];
      if ((cell & bit) != bit) {
        if (cell == kNoiseMaskAa) {
          --aa_cells_;
        }
        cell |= bit;
        if (cell == kNoiseMaskAa) {
          ++aa_cells_;
        }
        changed = true;
      }
    }
  }
  if (changed) {
    ++generation_;
  }
}

LazyCanvasNoiseMask::LazyCanvasNoiseMask() = default;
LazyCanvasNoiseMask::~LazyCanvasNoiseMask() = default;

void LazyCanvasNoiseMask::Add(size_t width, size_t height, size_t bytes,
                              Event event, bool apply_now) {
  pending_.push_back({width, height, bytes, std::move(event)});
  pending_bytes_ += bytes;
  if (apply_now) {
    Materialize();
    return;
  }
  while (pending_.size() > kMaxPendingEvents ||
         (pending_bytes_ > kMaxPendingBytes && pending_.size() > 1)) {
    ApplyFront();
  }
}

bool LazyCanvasNoiseMask::ApplyOldest() {
  if (pending_.empty()) {
    return false;
  }
  ApplyFront();
  return true;
}

void LazyCanvasNoiseMask::ApplyFront() const {
  Pending p = std::move(pending_.front());
  pending_.erase(pending_.begin());
  pending_bytes_ -= p.bytes;
  if (!mask_ || mask_->width() != p.width || mask_->height() != p.height) {
    Retire();
    mask_ = std::make_unique<CanvasNoiseMask>(p.width, p.height);
  }
  std::move(p.event).Run(*mask_);
}

void LazyCanvasNoiseMask::Retire() const {
  if (mask_) {
    retired_generations_ += mask_->generation() + 1;
    mask_.reset();
  }
}

void LazyCanvasNoiseMask::Reset() {
  pending_.clear();
  pending_bytes_ = 0;
  Retire();
}

void LazyCanvasNoiseMask::Materialize() const {
  while (!pending_.empty()) {
    ApplyFront();
  }
}

bool LazyCanvasNoiseMask::has_aa() const {
  Materialize();
  return mask_ && mask_->has_aa();
}

NoiseMask LazyCanvasNoiseMask::view() const {
  Materialize();
  return mask_ ? mask_->view() : NoiseMask();
}

uint64_t LazyCanvasNoiseMask::generation() const {
  Materialize();
  return mask_ ? retired_generations_ + mask_->generation() + 1 : 0;
}

}  // namespace camoucfg

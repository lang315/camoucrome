// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_CANVAS_MASK_H_
#define COMPONENTS_CAMOUCFG_CANVAS_MASK_H_

#include <cstddef>
#include <cstdint>
#include <memory>
#include <vector>

#include "base/functional/callback.h"
#include "base/time/time.h"

#include "components/camoucfg/canvas_noise.h"

namespace camoucfg {

// Which pixels of one 2D canvas may carry readback noise (canvas noise S2b,
// spec section 2). A cell holds kNoiseMaskAa (its value depends on the
// rasteriser) and/or kNoiseMaskImported (the page supplied it, or it may
// already carry noise); a pixel is eligible iff its cell is exactly
// kNoiseMaskAa. Blink merges every draw's coverage in. The cells are
// allocated at the first mark, so a canvas that never marks costs one empty
// object and reads as stock.
class CanvasNoiseMask {
 public:
  // What one draw does to the pixels it covers (the spec's table).
  enum class Kind {
    kSolidOpaque,  // full coverage clears both marks; partial sets aa
    kSolid,        // full coverage leaves the marks; partial sets aa
    kClear,        // clearRect: as kSolidOpaque
    kAa,           // any coverage sets aa
    kImported,     // any coverage sets imported
  };
  // At most this many pixels get one cell each (4096 x 4096). A larger
  // canvas keeps 4 x 4 px cells: marked if any pixel would be, cleared only
  // when every pixel is fully covered.
  static constexpr size_t kMaxFullResPixels = size_t{4096} * 4096;

  CanvasNoiseMask(size_t width, size_t height);
  CanvasNoiseMask(const CanvasNoiseMask&) = delete;
  CanvasNoiseMask& operator=(const CanvasNoiseMask&) = delete;
  ~CanvasNoiseMask();

  // `coverage`: A8, `coverage_width` x `coverage_height`, rows
  // `coverage_stride` bytes apart, its (0, 0) at canvas pixel (left, top).
  // Parts outside the canvas are ignored.
  void Merge(const uint8_t* coverage, size_t coverage_stride, int64_t left,
             int64_t top, size_t coverage_width, size_t coverage_height,
             Kind kind);
  // Merge() with full coverage of a rect.
  void MarkRect(int64_t left, int64_t top, int64_t width, int64_t height,
                Kind kind);

  bool empty() const { return cells_.empty(); }
  // True iff some cell is exactly kNoiseMaskAa (aa without imported): the
  // only cells readback noise may change.
  bool has_aa() const { return aa_cells_ > 0; }
  // The cells for PerturbRgbaEdgesInPlace. Only meaningful when !empty():
  // an empty view has cells == nullptr, which means "every pixel may change".
  NoiseMask view() const;
  // Bumps on every change, so a reader can key a cache on it.
  uint64_t generation() const { return generation_; }
  size_t width() const { return width_; }
  size_t height() const { return height_; }

 private:
  // `coverage` == nullptr means 255 everywhere.
  void Apply(const uint8_t* coverage, size_t coverage_stride, int64_t left,
             int64_t top, int64_t right, int64_t bottom, Kind kind);

  const size_t width_;
  const size_t height_;
  const int shift_;
  const size_t stride_;
  const size_t rows_;
  std::vector<uint8_t> cells_;
  uint64_t generation_ = 0;
  size_t aa_cells_ = 0;  // cells whose byte equals kNoiseMaskAa
};

// The mask of one 2D canvas, built when a read needs it instead of at every
// flush (release -5: building at flush cost the seeded canvas 3 us per op, 66%
// of it the software coverage raster, whether or not the page ever read the
// canvas back). A change to the mask is queued as an event that keeps what it
// needs alive (a flushed recording). The owner applies the queue event by event
// from an idle task (ApplyOldest), and every reader applies what is left first,
// in order, so a read pays for the tail only and the mask is byte for byte the
// one built at each event. A queue past kMaxPendingEvents events or
// kMaxPendingBytes of retained recordings applies its OLDEST event at each Add
// (never the whole queue: a frame stalls for one flush's walk, not sixteen).
class LazyCanvasNoiseMask {
 public:
  // One queued change to the mask of the canvas size it was queued for, worked in slices: Step() works until it
  // is done (true) or `deadline` has passed (false), checking the clock before every slice, the first included
  // (a maximal deadline never stops it). A recording's walk is such a job, so an idle task can stop inside a
  // recording instead of running one flush's walk, which can be tens of milliseconds, to its end.
  class Job {
   public:
    virtual ~Job() = default;
    virtual bool Step(CanvasNoiseMask& mask, base::TimeTicks deadline) = 0;
  };
  // A change that is done in one go.
  using Event = base::OnceCallback<void(CanvasNoiseMask&)>;
  static constexpr size_t kMaxPendingEvents = 16;
  static constexpr size_t kMaxPendingBytes = size_t{16} << 20;

  LazyCanvasNoiseMask();
  LazyCanvasNoiseMask(const LazyCanvasNoiseMask&) = delete;
  LazyCanvasNoiseMask& operator=(const LazyCanvasNoiseMask&) = delete;
  ~LazyCanvasNoiseMask();

  // Queues `event` for a canvas of `width` x `height` (a mask of another size
  // is replaced first, as a resize does); `bytes` is what the event keeps
  // alive. `apply_now` applies the whole queue, this event last: for an event
  // that holds images, which the queue must not pin. Past a cap the oldest
  // event is applied.
  void Add(size_t width, size_t height, size_t bytes, std::unique_ptr<Job> job,
           bool apply_now = false);
  void Add(size_t width, size_t height, size_t bytes, Event event,
           bool apply_now = false);
  // Works the oldest queued job until `deadline` (it stays queued, part done, when the deadline stops it);
  // false when none is queued.
  bool ApplyOldest(base::TimeTicks deadline = base::TimeTicks::Max());
  // The canvas restarts clear: the mask and every queued event are dropped.
  void Reset();

  // Each of these applies the queue first.
  bool has_aa() const;
  NoiseMask view() const;
  // Bumps on every change and never repeats, across resizes and resets too.
  uint64_t generation() const;

  size_t pending_events() const { return pending_.size(); }
  size_t pending_bytes() const { return pending_bytes_; }

 private:
  struct Pending {
    size_t width;
    size_t height;
    size_t bytes;
    std::unique_ptr<Job> job;
  };
  void Materialize() const;
  void StepFront(base::TimeTicks deadline) const;
  void Retire() const;

  mutable std::unique_ptr<CanvasNoiseMask> mask_;
  mutable std::vector<Pending> pending_;
  mutable size_t pending_bytes_ = 0;
  // Generations the retired masks used up.
  mutable uint64_t retired_generations_ = 0;
};

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_CANVAS_MASK_H_

// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/canvas_mask.h"

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <memory>
#include <utility>

#include "base/compiler_specific.h"
#include "base/containers/span.h"

namespace camoucfg {

CanvasNoiseMask::CanvasNoiseMask(size_t width, size_t height)
    : width_(width),
      height_(height),
      shift_(width * height > kMaxFullResPixels ? 2 : 0),
      stride_((width + (size_t{1} << shift_) - 1) >> shift_),
      rows_((height + (size_t{1} << shift_) - 1) >> shift_) {
  dirty_chunks_.assign((rows_ + kChunkRows - 1) / kChunkRows, 1);
}

CanvasNoiseMask::CanvasNoiseMask(const MaskSnapshot& from)
    : CanvasNoiseMask(from.width, from.height) {
  std::vector<uint8_t> cells = from.Flatten();
  if (cells.size() != stride_ * rows_ || from.shift != shift_) {
    return;  // not a snapshot of a mask of this size: start empty
  }
  cells_ = std::move(cells);
  aa_cells_ = static_cast<size_t>(
      std::count(cells_.begin(), cells_.end(), kNoiseMaskAa));
}

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
  const bool clear_kind = kind == Kind::kSolidOpaque || kind == Kind::kClear;
  const bool solid_kind = clear_kind || kind == Kind::kSolid;
  const uint8_t fixed_bit =
      kind == Kind::kImported ? kNoiseMaskImported : kNoiseMaskAa;
  if (shift_ == 0 && !cov.empty()) {
    // One cell per pixel: the clear (a fully covered pixel, clear kinds) and the
    // mark (aa on a partly covered pixel for the solid kinds, the kind's bit on
    // any covered pixel otherwise) never meet in one cell, so one pass in any
    // order is the two passes below. Raw rows: this is the walk's inner loop.
    for (int64_t y = y0; y < y1; ++y) {
      const uint8_t* const c = UNSAFE_BUFFERS(
          cov.data() + static_cast<size_t>(y - top) * coverage_stride +
          static_cast<size_t>(x0 - left));
      bool row_changed = false;
      const int64_t n = x1 - x0;
      for (int64_t i = 0; i < n; ++i) {
        // Most of a shape's bounds is uncovered: skip zeros a word at a time.
        if (i + 8 <= n) {
          uint64_t word;
          UNSAFE_BUFFERS(std::memcpy(&word, c + i, sizeof(word)));
          if (word == 0) {
            i += 7;
            continue;
          }
        }
        const uint8_t v = UNSAFE_BUFFERS(c[i]);
        if (v == 0) {
          continue;
        }
        uint8_t bit = fixed_bit;
        if (solid_kind) {
          if (v == 255) {
            if (clear_kind && !cells_.empty()) {
              uint8_t& cell = UNSAFE_BUFFERS(
                  cells_.data()[static_cast<size_t>(y) * stride_ +
                                static_cast<size_t>(x0 + i)]);
              if (cell != 0) {
                if (cell == kNoiseMaskAa) {
                  --aa_cells_;
                }
                cell = 0;
                row_changed = true;
              }
            }
            continue;
          }
          bit = kNoiseMaskAa;
        }
        if (cells_.empty()) {
          cells_.assign(stride_ * rows_, 0);
          MarkAllDirty();
        }
        uint8_t& cell = UNSAFE_BUFFERS(
            cells_.data()[static_cast<size_t>(y) * stride_ +
                          static_cast<size_t>(x0 + i)]);
        if ((cell & bit) != bit) {
          if (cell == kNoiseMaskAa) {
            --aa_cells_;
          }
          cell |= bit;
          if (cell == kNoiseMaskAa) {
            ++aa_cells_;
          }
          row_changed = true;
        }
      }
      if (row_changed) {
        MarkDirty(static_cast<size_t>(y));
        changed = true;
      }
    }
    if (changed) {
      ++generation_;
    }
    return;
  }
  if (clear_kind && !cells_.empty()) {
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
          MarkDirty(static_cast<size_t>(cy));
          changed = true;
        }
      }
    }
  }
  // The mark of a pixel: fixed for the aa and imported kinds, and for the
  // solid kinds aa on a partly covered pixel only. A solid kind without a
  // coverage buffer covers every pixel fully: nothing to mark.
  if (solid_kind && cov.empty()) {
    if (changed) {
      ++generation_;
    }
    return;
  }
  for (int64_t y = y0; y < y1; ++y) {
    base::span<const uint8_t> row;  // this row's coverage from x0 on
    if (!cov.empty()) {
      row = cov.subspan(
          static_cast<size_t>(y - top) * coverage_stride +
              static_cast<size_t>(x0 - left),
          static_cast<size_t>(x1 - x0));
    }
    const size_t cell_row = static_cast<size_t>(y >> shift_) * stride_;
    for (int64_t x = x0; x < x1; ++x) {
      const uint8_t c = row.empty() ? 255 : row[static_cast<size_t>(x - x0)];
      if (c == 0) {
        continue;
      }
      const uint8_t bit = solid_kind ? (c == 255 ? 0 : kNoiseMaskAa) : fixed_bit;
      if (bit == 0) {
        continue;
      }
      if (cells_.empty()) {
        cells_.assign(stride_ * rows_, 0);
        MarkAllDirty();
      }
      uint8_t& cell = cells_[cell_row + static_cast<size_t>(x >> shift_)];
      if ((cell & bit) != bit) {
        if (cell == kNoiseMaskAa) {
          --aa_cells_;
        }
        cell |= bit;
        MarkDirty(static_cast<size_t>(y >> shift_));
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

void CanvasNoiseMask::MarkDirty(size_t cell_row) {
  dirty_chunks_[cell_row / kChunkRows] = 1;
  any_dirty_ = true;
}

void CanvasNoiseMask::MarkAllDirty() {
  std::fill(dirty_chunks_.begin(), dirty_chunks_.end(), 1);
  any_dirty_ = true;
}

MaskChunk::MaskChunk(std::vector<uint8_t> bytes) : bytes_(std::move(bytes)) {}
MaskChunk::~MaskChunk() = default;
MaskSnapshot::MaskSnapshot() = default;
MaskSnapshot::~MaskSnapshot() = default;

std::vector<uint8_t> MaskSnapshot::Flatten() const {
  std::vector<uint8_t> flat;
  flat.reserve(stride * rows);
  for (const auto& chunk : chunks) {
    flat.insert(flat.end(), chunk->bytes().begin(), chunk->bytes().end());
  }
  return flat;
}

NoiseMask MaskSnapshot::ViewOf(const std::vector<uint8_t>& cells) const {
  return {cells.empty() ? nullptr : cells.data(), stride, shift, width, height};
}

scoped_refptr<const MaskSnapshot> CanvasNoiseMask::Snapshot(
    const MaskSnapshot* prev) {
  if (cells_.empty()) {
    return nullptr;
  }
  const size_t count = dirty_chunks_.size();
  // Every writer marks its chunk (Apply is the only one, with three sites, each
  // with a unit test). This catches only a path that moved the generation and
  // marked nothing at all; a missed mark next to another chunk's mark would not
  // be seen, and would be a stale frame.
  const bool unmarked = prev && prev->generation != generation_ && !any_dirty_;
  const bool shares = prev && !unmarked && prev->width == width_ &&
                      prev->height == height_ && prev->shift == shift_ &&
                      prev->chunks.size() == count;
  auto snapshot = base::MakeRefCounted<MaskSnapshot>();
  snapshot->width = width_;
  snapshot->height = height_;
  snapshot->stride = stride_;
  snapshot->rows = rows_;
  snapshot->shift = shift_;
  snapshot->generation = generation_;
  snapshot->chunks.reserve(count);
  for (size_t i = 0; i < count; ++i) {
    if (shares && !dirty_chunks_[i] && prev->chunks[i]) {
      snapshot->chunks.push_back(prev->chunks[i]);
      continue;
    }
    const size_t first = i * kChunkRows;
    const size_t last = std::min(rows_, first + kChunkRows);
    snapshot->chunks.push_back(base::MakeRefCounted<MaskChunk>(
        std::vector<uint8_t>(cells_.begin() + first * stride_,
                             cells_.begin() + last * stride_)));
  }
  std::fill(dirty_chunks_.begin(), dirty_chunks_.end(), 0);
  any_dirty_ = false;
  return snapshot;
}

LazyCanvasNoiseMask::LazyCanvasNoiseMask() = default;
LazyCanvasNoiseMask::~LazyCanvasNoiseMask() = default;

std::unique_ptr<LazyCanvasNoiseMask::Job> LazyCanvasNoiseMask::Job::Clone() const {
  return nullptr;
}

bool LazyCanvasNoiseMask::Job::IsEvent() const {
  return false;
}

namespace {

// An Event as a job: one slice that always finishes.
class EventJob final : public LazyCanvasNoiseMask::Job {
 public:
  explicit EventJob(LazyCanvasNoiseMask::Event event) : event_(std::move(event)) {}
  bool Step(CanvasNoiseMask& mask, base::TimeTicks) override {
    std::move(event_).Run(mask);
    return true;
  }
  bool IsEvent() const override { return true; }

 private:
  LazyCanvasNoiseMask::Event event_;
};

// Jobs merged into one, walked in order. Each part keeps its own bytes, so the
// queue can walk one part and free its bytes. Applying a whole job is
// idempotent (every cell goes through x -> (x & m) | b), so a frame that
// carries a merge whose older parts a memo already holds is still right.
class MergedJob final : public LazyCanvasNoiseMask::Job {
 public:
  void Append(std::unique_ptr<LazyCanvasNoiseMask::Job> job, size_t bytes) {
    parts_.push_back({std::move(job), bytes});
  }
  // Takes the parts `other` has not walked, after this one's.
  void Absorb(MergedJob& other) {
    unreported_ += other.unreported_;
    for (size_t i = other.index_; i < other.parts_.size(); ++i) {
      parts_.push_back(std::move(other.parts_[i]));
    }
    other.parts_.clear();
    other.index_ = 0;
    other.unreported_ = 0;
  }
  bool Step(CanvasNoiseMask& mask, base::TimeTicks deadline) override {
    while (index_ < parts_.size()) {
      Part& part = parts_[index_];
      if (!part.job->Step(mask, deadline)) {
        return false;
      }
      Finish(part);
    }
    return true;
  }
  bool FrontIsEvent() const { return parts_[index_].job->IsEvent(); }
  // Works the part in progress to its end on `mask` (null: releases it
  // unwalked); returns the bytes the finished parts free, and sets `*done`
  // when nothing is left.
  size_t FinishPart(CanvasNoiseMask* mask, bool* done) {
    Part& part = parts_[index_];
    if (mask) {
      part.job->Step(*mask, base::TimeTicks::Max());
    }
    Finish(part);
    *done = index_ >= parts_.size();
    const size_t freed = unreported_;
    unreported_ = 0;
    return freed;
  }
  // O(parts): every part not walked yet, each where it stands; null when one
  // cannot be copied (an Event).
  std::unique_ptr<LazyCanvasNoiseMask::Job> Clone() const override {
    auto copy = std::make_unique<MergedJob>();
    for (size_t i = index_; i < parts_.size(); ++i) {
      std::unique_ptr<LazyCanvasNoiseMask::Job> part = parts_[i].job->Clone();
      if (!part) {
        return nullptr;
      }
      copy->Append(std::move(part), parts_[i].bytes);
    }
    return copy;
  }

 private:
  struct Part {
    std::unique_ptr<LazyCanvasNoiseMask::Job> job;
    size_t bytes;
  };
  // A part is done: its recording is released, its bytes wait to be reported.
  void Finish(Part& part) {
    unreported_ += part.bytes;
    part.job.reset();
    ++index_;
  }

  std::vector<Part> parts_;
  size_t index_ = 0;       // the part in progress
  size_t unreported_ = 0;  // bytes of finished parts the queue still counts
};

}  // namespace

void LazyCanvasNoiseMask::Add(size_t width, size_t height, size_t bytes,
                              Event event, bool apply_now) {
  Add(width, height, bytes, std::make_unique<EventJob>(std::move(event)),
      apply_now);
}

void LazyCanvasNoiseMask::Add(size_t width, size_t height, size_t bytes,
                              std::unique_ptr<Job> job, bool apply_now) {
  ++revision_;
  bytes = std::max(bytes, kMinPartBytes);
  pending_.push_back({width, height, bytes, next_id_++, std::move(job)});
  pending_bytes_ += bytes;
  if (apply_now) {
    Materialize();
    return;
  }
  while (pending_.size() > kMaxPendingEvents) {
    if (!MergeOldestPair()) {
      ShedFront();
    }
  }
  // The newest job past the cap stays queued, unwalked, as before.
  while (pending_bytes_ > kMaxPendingBytes && pending_.size() > 1) {
    DropFront();
  }
}

void LazyCanvasNoiseMask::DropFront() const {
  Pending& p = pending_.front();
  if (p.id <= last_deferred_id_) {
    ParkFront();
    return;
  }
  auto* merged = p.merged ? static_cast<MergedJob*>(p.job.get()) : nullptr;
  const bool event = merged ? merged->FrontIsEvent() : p.job->IsEvent();
  if (event) {
    // An event is walked, never dropped: it costs no recording. The parked
    // jobs are older, so they go first.
    while (!parked_.empty()) {
      StepFront(base::TimeTicks::Max());
    }
    if (!merged) {
      StepFront(base::TimeTicks::Max());
      return;
    }
    touched_id_ = p.id;
  } else {
    ++counters_.dropped_total;
  }
  ++revision_;
  bool done = true;
  size_t freed =
      merged ? merged->FinishPart(event ? &MaskFor(p) : nullptr, &done)
             : p.bytes;
  freed = done ? p.bytes : std::min(freed, p.bytes);
  p.bytes -= freed;
  pending_bytes_ -= freed;
  if (done) {
    pending_.erase(pending_.begin());
  }
}

bool LazyCanvasNoiseMask::MergeOldestPair() const {
  for (size_t i = 0; i + 1 < pending_.size(); ++i) {
    Pending& a = pending_[i];
    Pending& b = pending_[i + 1];
    if (a.width != b.width || a.height != b.height ||
        (a.id > last_deferred_id_) != (b.id > last_deferred_id_)) {
      continue;
    }
    if (!a.merged) {
      auto merged = std::make_unique<MergedJob>();
      merged->Append(std::move(a.job), a.bytes);
      a.job = std::move(merged);
      a.merged = true;
    }
    auto* into = static_cast<MergedJob*>(a.job.get());
    if (b.merged) {
      into->Absorb(*static_cast<MergedJob*>(b.job.get()));
    } else {
      into->Append(std::move(b.job), b.bytes);
    }
    a.bytes += b.bytes;
    a.id = b.id;
    ++counters_.merged_total;
    pending_.erase(pending_.begin() + static_cast<ptrdiff_t>(i) + 1);
    return true;
  }
  return false;
}

void LazyCanvasNoiseMask::ShedFront() const {
  // The parked jobs are older: walked first.
  while (!parked_.empty()) {
    StepFront(base::TimeTicks::Max());
  }
  StepFront(base::TimeTicks::Max());
}

void LazyCanvasNoiseMask::ParkFront() const {
  // The last deferred frame carries it, and the page may read that frame (and
  // tell us) after this point; if it has, EvictParkedFront() walks it.
  Pending parked = std::move(pending_.front());
  pending_.erase(pending_.begin());
  pending_bytes_ -= parked.bytes;
  parked_bytes_ += parked.bytes;
  parked_.push_back(std::move(parked));
  ++counters_.parked_total;
  while (parked_.size() > kMaxParkedJobs ||
         (parked_bytes_ > kMaxParkedBytes && parked_.size() > 1)) {
    EvictParkedFront();
  }
}

void LazyCanvasNoiseMask::EvictParkedFront() const {
  if (parked_.front().id <= seen_floor_) {
    StepFront(base::TimeTicks::Max());
    ++counters_.seen_walked;
    return;
  }
  parked_bytes_ -= parked_.front().bytes;
  parked_.erase(parked_.begin());
  ++counters_.parked_evicted;
}

void LazyCanvasNoiseMask::NoteSeen(uint64_t id) {
  ++counters_.signals;
  if (id > seen_floor_) {
    seen_floor_ = id;
  }
}

bool LazyCanvasNoiseMask::ApplyOldest(base::TimeTicks deadline) {
  if (!has_work()) {
    return false;
  }
  StepFront(deadline);
  return true;
}

CanvasNoiseMask& LazyCanvasNoiseMask::MaskFor(const Pending& p) const {
  if (!mask_ || mask_->width() != p.width || mask_->height() != p.height) {
    Retire();
    mask_ = std::make_unique<CanvasNoiseMask>(p.width, p.height);
  }
  return *mask_;
}

void LazyCanvasNoiseMask::StepFront(base::TimeTicks deadline) const {
  ++revision_;
  const bool parked = !parked_.empty();
  Pending& p = parked ? parked_.front() : pending_.front();
  CanvasNoiseMask& mask = MaskFor(p);
  touched_id_ = p.id;
  if (p.job->Step(mask, deadline)) {
    if (parked) {
      parked_bytes_ -= p.bytes;
      parked_.erase(parked_.begin());
      ++counters_.parked_walked;
    } else {
      pending_bytes_ -= p.bytes;
      pending_.erase(pending_.begin());
    }
  }
}

void LazyCanvasNoiseMask::Retire() const {
  if (mask_) {
    retired_generations_ += mask_->generation() + 1;
    mask_.reset();
    ++epoch_;
  }
}

void LazyCanvasNoiseMask::Reset() {
  ++revision_;
  pending_.clear();
  pending_bytes_ = 0;
  parked_.clear();
  parked_bytes_ = 0;
  Retire();
  ++epoch_;
}

void LazyCanvasNoiseMask::Materialize() const {
  while (has_work()) {
    StepFront(base::TimeTicks::Max());
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

scoped_refptr<const MaskSnapshot> LazyCanvasNoiseMask::Snapshot(
    const MaskSnapshot* prev) const {
  Materialize();
  return mask_ ? mask_->Snapshot(prev) : nullptr;
}

uint64_t LazyCanvasNoiseMask::generation() const {
  Materialize();
  return mask_ ? retired_generations_ + mask_->generation() + 1 : 0;
}

LazyCanvasNoiseMask::DeferStatus LazyCanvasNoiseMask::Defer(
    const MaskSnapshot* prev,
    scoped_refptr<const DeferredMask>* out) const {
  if (!has_work()) {
    return DeferStatus::kNone;
  }
  if (pending_.size() > kMaxDeferredJobs ||
      pending_bytes_ > kMaxDeferredBytes) {
    return DeferStatus::kOverCap;
  }
  // The parked jobs are older than the queued ones: first, in order.
  const Pending& first = parked_.empty() ? pending_.front() : parked_.front();
  const size_t width = first.width;
  const size_t height = first.height;
  std::vector<std::unique_ptr<Job>> jobs;
  std::vector<uint64_t> ids;
  jobs.reserve(parked_.size() + pending_.size());
  ids.reserve(parked_.size() + pending_.size());
  size_t bytes = 0;
  for (const std::vector<Pending>* list : {&parked_, &pending_}) {
    for (const Pending& p : *list) {
      // StepFront() starts a fresh mask at a change of size: a queue of two
      // sizes is not one replay.
      std::unique_ptr<Job> copy;
      if (p.width == width && p.height == height) {
        copy = p.job->Clone();
      }
      if (!copy) {
        return DeferStatus::kNotClonable;
      }
      jobs.push_back(std::move(copy));
      ids.push_back(p.id);
      bytes += p.bytes;
    }
  }
  // Only now: Snapshot() consumes the mask's written-chunk marks, so it runs
  // only when its result is used.
  scoped_refptr<const MaskSnapshot> base;
  if (mask_ && mask_->width() == width && mask_->height() == height) {
    base = mask_->Snapshot(prev);
  }
  last_deferred_id_ = ids.back();
  *out = base::MakeRefCounted<DeferredMask>(
      width, height, std::move(base), std::move(jobs), std::move(ids), bytes,
      touched_id_, epoch_);
  return DeferStatus::kDeferred;
}

DeferredMask::DeferredMask(
    size_t width,
    size_t height,
    scoped_refptr<const MaskSnapshot> base,
    std::vector<std::unique_ptr<LazyCanvasNoiseMask::Job>> jobs,
    std::vector<uint64_t> ids,
    size_t bytes,
    uint64_t touched_id,
    uint64_t epoch)
    : width_(width),
      height_(height),
      base_(std::move(base)),
      jobs_(std::move(jobs)),
      ids_(std::move(ids)),
      bytes_(bytes),
      touched_id_(touched_id),
      epoch_(epoch) {}

DeferredMask::~DeferredMask() = default;

std::unique_ptr<CanvasNoiseMask> DeferredMask::Replay() const {
  // Each job runs on a copy: this object stays what it was made as. Defer()
  // copied every job once, so a copy that fails now is not expected; a mask
  // without that job would be a wrong mask, so nothing is walked (null).
  std::vector<std::unique_ptr<LazyCanvasNoiseMask::Job>> copies;
  copies.reserve(jobs_.size());
  for (const auto& job : jobs_) {
    std::unique_ptr<LazyCanvasNoiseMask::Job> copy = job->Clone();
    if (!copy) {
      return nullptr;
    }
    copies.push_back(std::move(copy));
  }
  auto mask = base_ ? std::make_unique<CanvasNoiseMask>(*base_)
                    : std::make_unique<CanvasNoiseMask>(width_, height_);
  for (const auto& copy : copies) {
    copy->Step(*mask, base::TimeTicks::Max());
  }
  return mask;
}

bool DeferredMask::Continue(CanvasNoiseMask& memo,
                            uint64_t memo_epoch,
                            uint64_t memo_id,
                            size_t* stepped) const {
  // The base holds only jobs up to touched_id_; every job of this frame after
  // memo_id is in jobs_ (or was never seen by anyone: a drop). So memo (every
  // job up to memo_id, in order) plus those jobs is this frame's mask.
  if (memo_epoch != epoch_ || memo.width() != width_ ||
      memo.height() != height_ || memo_id > last_id() ||
      touched_id_ > memo_id) {
    return false;
  }
  // All the copies first: a copy that fails (not expected, see Replay()) must
  // leave `memo` as it was, for the caller's full replay.
  std::vector<std::unique_ptr<LazyCanvasNoiseMask::Job>> copies;
  for (size_t i = 0; i < jobs_.size(); ++i) {
    if (ids_[i] <= memo_id) {
      continue;
    }
    std::unique_ptr<LazyCanvasNoiseMask::Job> copy = jobs_[i]->Clone();
    if (!copy) {
      return false;
    }
    copies.push_back(std::move(copy));
  }
  for (const auto& copy : copies) {
    copy->Step(memo, base::TimeTicks::Max());
  }
  if (stepped) {
    *stepped = copies.size();
  }
  return true;
}

}  // namespace camoucfg

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
#include "base/memory/ref_counted.h"
#include "base/memory/scoped_refptr.h"
#include "base/time/time.h"

#include "components/camoucfg/canvas_noise.h"

namespace camoucfg {

// A run of cell rows of a mask, immutable once made: shared by every snapshot
// that holds those rows unchanged.
class MaskChunk : public base::RefCountedThreadSafe<MaskChunk> {
 public:
  explicit MaskChunk(std::vector<uint8_t> bytes);
  const std::vector<uint8_t>& bytes() const { return bytes_; }

 private:
  friend class base::RefCountedThreadSafe<MaskChunk>;
  ~MaskChunk();
  const std::vector<uint8_t> bytes_;
};

// The cells of a CanvasNoiseMask at one moment, in row chunks (kChunkRows cell
// rows each), immutable and safe to hand to another thread: a worker takes one
// per committed frame and the main thread flattens it when the page reads the
// frame. A snapshot made from the previous one shares every chunk whose rows
// did not change, so a frame costs the chunks a shape touched.
class MaskSnapshot : public base::RefCountedThreadSafe<MaskSnapshot> {
 public:
  MaskSnapshot();

  size_t width = 0;
  size_t height = 0;
  size_t stride = 0;
  size_t rows = 0;
  int shift = 0;
  uint64_t generation = 0;
  std::vector<scoped_refptr<const MaskChunk>> chunks;

  // The cells as one contiguous buffer (stride * rows bytes), the layout
  // CanvasNoiseMask::view() has.
  std::vector<uint8_t> Flatten() const;
  // A NoiseMask over `cells` (what Flatten() returned).
  NoiseMask ViewOf(const std::vector<uint8_t>& cells) const;

 private:
  friend class base::RefCountedThreadSafe<MaskSnapshot>;
  ~MaskSnapshot();
};

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
  // A mask holding the cells `from` holds, which a mask of the same size made
  // (Snapshot()): the mask a replay starts from (DeferredMask).
  explicit CanvasNoiseMask(const MaskSnapshot& from);
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
  // The cells as they are now, as a MaskSnapshot that shares with `prev` (a
  // snapshot of this mask, or null) every chunk written to since. Null while no
  // cell was ever written. Clears the written-chunk marks: one consumer.
  scoped_refptr<const MaskSnapshot> Snapshot(const MaskSnapshot* prev);
  size_t width() const { return width_; }
  size_t height() const { return height_; }

 private:
  // `coverage` == nullptr means 255 everywhere.
  void Apply(const uint8_t* coverage, size_t coverage_stride, int64_t left,
             int64_t top, int64_t right, int64_t bottom, Kind kind);
  // Every write to cells_ marks the chunk of its cell row (Apply is the only
  // writer: the clear, the first allocation and the mark).
  void MarkDirty(size_t cell_row);
  void MarkAllDirty();

  const size_t width_;
  const size_t height_;
  const int shift_;
  const size_t stride_;
  const size_t rows_;
  std::vector<uint8_t> cells_;
  uint64_t generation_ = 0;
  size_t aa_cells_ = 0;  // cells whose byte equals kNoiseMaskAa
  // Per chunk of kChunkRows cell rows: written since the last Snapshot(). A new
  // mask starts all-dirty.
  static constexpr size_t kChunkRows = 64;
  std::vector<uint8_t> dirty_chunks_;
  bool any_dirty_ = true;
};

class DeferredMask;

// The mask of one 2D canvas, built when a read needs it instead of at every
// flush (release -5: building at flush cost the seeded canvas 3 us per op, 66%
// of it the software coverage raster, whether or not the page ever read the
// canvas back). A change to the mask is queued as an event that keeps what it
// needs alive (a flushed recording). The owner applies the queue event by event
// from an idle task (ApplyOldest), and every reader applies what is left first,
// in order, so a read pays for the tail only and the mask is byte for byte the
// one built at each event. Past kMaxPendingEvents queued jobs the two oldest
// are merged into one (no pixel work), so the count of flushes never loses a
// mark. Past kMaxPendingBytes of retained recordings the oldest recording (or
// the oldest part of a merge) is released unwalked, as the queue did before
// merging: walking it there would put the walk on the draw. Events (a put)
// keep no recording alive and are walked there instead. So a page that draws
// and flushes in a loop without ever reading (an animation, a benchmark)
// costs one queue push per flush.
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
    // A copy that stands where this job stands (a partly worked job resumes at
    // the op it stopped at) and shares nothing mutable with it, so another
    // thread may work it while this one goes on; null when the job cannot be
    // copied (an Event). Const and safe to call while no thread Steps the job.
    virtual std::unique_ptr<Job> Clone() const;
    // An Event: it keeps no recording alive, so the byte cap walks it rather
    // than drop it.
    virtual bool IsEvent() const;
  };
  // A change that is done in one go.
  using Event = base::OnceCallback<void(CanvasNoiseMask&)>;
  static constexpr size_t kMaxPendingEvents = 16;
  static constexpr size_t kMaxPendingBytes = size_t{16} << 20;
  // Each queued job is accounted at least this much, so zero-byte events are
  // bounded by the byte cap too.
  static constexpr size_t kMinPartBytes = 256;
  // What one frame may carry unapplied (Defer()): the queue's own caps plus the
  // parked jobs' (kMaxParkedJobs / kMaxParkedBytes: the jobs the queue shed
  // while the last frame carried them). So a frame carries at most 32 jobs and
  // pins at most 32 MB of the recordings until it is dropped. Only a single
  // recording past the byte cap, which the queue keeps as its last entry, is
  // over it.
  static constexpr size_t kMaxDeferredJobs = kMaxPendingEvents;
  static constexpr size_t kMaxDeferredBytes = kMaxPendingBytes;
  // A job the queue sheds while the last deferred frame carries it is parked,
  // not dropped (see NoteSeen()): at most this much, oldest evicted first.
  static constexpr size_t kMaxParkedJobs = 16;
  static constexpr size_t kMaxParkedBytes = size_t{16} << 20;
  enum class DeferStatus {
    kNone,         // nothing queued: the mask is as it is, Snapshot() is cheap
    kDeferred,     // a DeferredMask was made, nothing was applied
    kOverCap,      // one recording past kMaxDeferredBytes: apply it as before
    kNotClonable,  // an event, or a resize inside the queue: apply it
  };

  LazyCanvasNoiseMask();
  LazyCanvasNoiseMask(const LazyCanvasNoiseMask&) = delete;
  LazyCanvasNoiseMask& operator=(const LazyCanvasNoiseMask&) = delete;
  ~LazyCanvasNoiseMask();

  // Queues `event` for a canvas of `width` x `height` (a mask of another size
  // is replaced first, as a resize does); `bytes` is what the event keeps
  // alive (at least kMinPartBytes is accounted). `apply_now` applies the whole
  // queue, this event last: for an event that holds images, which the queue
  // must not pin. Past the count cap the two oldest jobs are merged; past the
  // byte cap the oldest recording is dropped (an event is walked).
  void Add(size_t width, size_t height, size_t bytes, std::unique_ptr<Job> job,
           bool apply_now = false);
  void Add(size_t width, size_t height, size_t bytes, Event event,
           bool apply_now = false);
  // Works the oldest job (a parked one first, see NoteSeen()) until `deadline`
  // (it stays queued, part done, when the deadline stops it); false when none
  // is queued.
  bool ApplyOldest(base::TimeTicks deadline = base::TimeTicks::Max());
  // The canvas restarts clear: the mask and every queued event are dropped.
  void Reset();

  // Each of these applies the queue first.
  bool has_aa() const;
  NoiseMask view() const;
  // Bumps on every change and never repeats, across resizes and resets too.
  uint64_t generation() const;
  // CanvasNoiseMask::Snapshot() of the mask after the queue is applied.
  scoped_refptr<const MaskSnapshot> Snapshot(const MaskSnapshot* prev) const;
  // The mask as it will be once the queue is applied, without applying it:
  // the snapshot of the mask as it is now (shared with `prev` as Snapshot()
  // shares) and a copy of every queued job. `*out` is set on kDeferred only.
  // On any other status nothing was taken from the mask (`prev` stays the
  // latest snapshot of it).
  DeferStatus Defer(const MaskSnapshot* prev,
                    scoped_refptr<const DeferredMask>* out) const;
  // Bumps on every Add, every slice worked and every Reset, and applying the
  // queue is those slices: a cheap key that never applies the queue itself.
  uint64_t revision() const { return revision_; }

  size_t pending_events() const { return pending_.size(); }
  size_t pending_bytes() const { return pending_bytes_; }
  // Jobs still to walk: the queue and the parked ones.
  bool has_work() const { return !pending_.empty() || !parked_.empty(); }
  size_t parked_events() const { return parked_.size(); }
  size_t parked_bytes() const { return parked_bytes_; }

  // The page has read a frame (DeferredMask) whose newest job was `id`: from
  // now on a job up to `id` that the queue or the parked list would lose is
  // walked instead. Without it a frame the page read, and a frame it reads
  // after >16 unread flushes, would disagree about the pixels of the dropped
  // jobs (the second shows them raw). Jobs shed before the signal arrives sit
  // in the parked list (only a job the last deferred frame carries is parked),
  // so a signal that is a few flushes late still finds them. Never applies
  // anything itself: parked jobs are walked by the idle task, a read, or an
  // eviction, always in order, before any queued job.
  void NoteSeen(uint64_t id);
  // Every job gets a monotonic id at Add (from 1); 0 is "none".
  uint64_t last_id() const { return next_id_ - 1; }
  // Changes whenever the mask restarts from nothing (a resize, a Reset): a
  // memo of an older epoch is not a state of this mask.
  uint64_t epoch() const { return epoch_; }

  struct Counters {
    uint64_t signals = 0;         // NoteSeen() calls
    uint64_t parked_total = 0;    // jobs ever parked
    uint64_t parked_walked = 0;   // parked jobs walked (idle, read, signal)
    uint64_t parked_evicted = 0;  // parked jobs dropped at eviction (the page had not seen them)
    uint64_t seen_walked = 0;     // parked jobs the page had seen, walked at eviction
    uint64_t merged_total = 0;    // jobs merged into the job before them (count cap)
    uint64_t dropped_total = 0;   // recordings (or merge parts) dropped unwalked (byte cap)
  };
  const Counters& counters() const { return counters_; }

 private:
  struct Pending {
    size_t width;
    size_t height;
    size_t bytes;
    uint64_t id;  // a merged job has its newest part's id
    std::unique_ptr<Job> job;
    bool merged = false;  // `job` is a MergedJob
  };
  void Materialize() const;
  // Works the oldest job: the first parked one, else the queue's first.
  void StepFront(base::TimeTicks deadline) const;
  // The queue is past the byte cap: its first job is parked (the last deferred
  // frame carries it), or its oldest part is walked (an event) or dropped
  // unwalked (a recording).
  void DropFront() const;
  // Moves the queue's first job to the parked list, evicting past its caps.
  void ParkFront() const;
  // The mask the job `p` is walked on: a fresh one when its size changed.
  CanvasNoiseMask& MaskFor(const Pending& p) const;
  // Merges the oldest two queued jobs of one size that no deferred frame
  // splits (both carried by the last frame, or neither); false when none.
  bool MergeOldestPair() const;
  // The queue is past the count cap and nothing merges: its first job is
  // walked, after the parked jobs (the count route never drops).
  void ShedFront() const;
  void EvictParkedFront() const;
  void Retire() const;

  mutable std::unique_ptr<CanvasNoiseMask> mask_;
  mutable std::vector<Pending> pending_;
  mutable size_t pending_bytes_ = 0;
  // Generations the retired masks used up.
  mutable uint64_t retired_generations_ = 0;
  mutable uint64_t revision_ = 0;
  // Jobs shed from the queue while the last deferred frame carried them, oldest
  // first, all older than every queued job.
  mutable std::vector<Pending> parked_;
  mutable size_t parked_bytes_ = 0;
  uint64_t next_id_ = 1;
  // Jobs up to this id were read by the page (NoteSeen).
  uint64_t seen_floor_ = 0;
  // The newest job id the last Defer() put in a frame.
  mutable uint64_t last_deferred_id_ = 0;
  // The id of the job last stepped, wholly or in part: what the mask holds
  // comes from jobs up to it.
  mutable uint64_t touched_id_ = 0;
  mutable uint64_t epoch_ = 0;
  mutable Counters counters_;
};

// The mask of a LazyCanvasNoiseMask as it will be once its queue is applied, in
// a form another thread can finish: the cells already applied (an immutable
// snapshot, null while no cell was ever written) and a copy of each job still
// queued, at the op it stands at. Immutable and thread safe to share. A frame
// of a worker's canvas carries one so the worker does not walk its recordings
// at every commit; the page's read does it, once, on the main thread.
class DeferredMask : public base::RefCountedThreadSafe<DeferredMask> {
 public:
  DeferredMask(size_t width,
               size_t height,
               scoped_refptr<const MaskSnapshot> base,
               std::vector<std::unique_ptr<LazyCanvasNoiseMask::Job>> jobs,
               std::vector<uint64_t> ids,
               size_t bytes,
               uint64_t touched_id,
               uint64_t epoch);
  // The mask the queue builds, byte for byte (the jobs run to their end on
  // fresh copies, so any number of replays, on any thread, agree). Null when a
  // job cannot be copied again (Defer() copied each once: not expected); the
  // caller then has no mask and must not guess one.
  std::unique_ptr<CanvasNoiseMask> Replay() const;
  // The same mask, continued from `memo`: the mask an earlier frame of this
  // canvas (same epoch) replayed to, as of its newest job `memo_id`. Only the
  // jobs after `memo_id` are walked, on `memo` itself, which then is this
  // frame's mask. False, memo untouched, when this frame does not continue it
  // (another epoch or size, an older frame, or a base that holds a job past
  // `memo_id`, or a job that cannot be copied): replay from scratch then.
  // `*stepped` is the jobs walked.
  bool Continue(CanvasNoiseMask& memo,
                uint64_t memo_epoch,
                uint64_t memo_id,
                size_t* stepped) const;
  const scoped_refptr<const MaskSnapshot>& base() const { return base_; }
  size_t jobs() const { return jobs_.size(); }
  size_t bytes() const { return bytes_; }
  // The newest job in this frame (0: none).
  uint64_t last_id() const { return ids_.empty() ? 0 : ids_.back(); }
  uint64_t epoch() const { return epoch_; }

 private:
  friend class base::RefCountedThreadSafe<DeferredMask>;
  ~DeferredMask();
  const size_t width_;
  const size_t height_;
  const scoped_refptr<const MaskSnapshot> base_;
  const std::vector<std::unique_ptr<LazyCanvasNoiseMask::Job>> jobs_;
  const std::vector<uint64_t> ids_;
  const size_t bytes_;
  const uint64_t touched_id_;
  const uint64_t epoch_;
};

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_CANVAS_MASK_H_

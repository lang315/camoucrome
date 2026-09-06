# voices-ii measurement (2026-09-06)

Checkout HEAD `a727b57805`, content_shell over `about:blank` (SpeechSynthesis is
`Exposed=Window`, not secure-context gated). Follow-on to sp4-voices (roadmap
item 5), scope = **token + jitter + boundary** (operator decision; pause/resume
deferred).

sp4-voices fakes `speak()` completion for injected voices: an async `start`
(`DidStartSpeaking`) + a delayed `end` (`DidFinishSpeaking`, kNoError) at
`secs = text.length / (charsPerSecond · rate)`, both guarded
`self && u && u == CurrentSpeechUtterance()`. Its §4 named four residual tells;
this slice closes three.

---

## 1. The tells (measured RED, `measure_voices_ii.py`)

Config `{"voices:list":[{... voiceURI:"urn:camou:en" ...}]}`, one injected voice:

```
M-BOUNDARY: {"boundaries": [], "boundaryCount": 0}
M-PAUSE:    {"endMs": 3842, "paused_flag": false, "speaking_flag": true}   # deferred
M-LINEAR:   n=10 -> 801ms   n=40 -> 3202ms   ratio 3.994 (~= 4.000 exactly)
M-REUSE:    {"ends": [1573.6]}   # 24-char text, base ~1920ms -> fired ~347ms EARLY
```

- **M-BOUNDARY** — a fake voice fires **zero** `boundary` events; real TTS fires
  one per word. A probe attaching `onboundary` sees nothing = tell.
- **M-LINEAR** — `end` fires at exactly `text.length/(cps·rate)`: n=10→801ms,
  n=40→3202ms, ratio **3.994** (the residual ±ms is scheduler slop, not signal).
  A probe varying length reads a perfectly linear signal, unlike real TTS.
- **M-REUSE** — `speak(u)`, `cancel()`, `speak(u)` on the SAME utterance object:
  the first speak's stale delayed-`end` task can't be told from the fresh one by
  `== CurrentSpeechUtterance()`, so `end` fires ~347ms EARLY (1573 vs the 1920
  base). Not a crash (later task no-ops), but a spurious early `end`.
- **M-PAUSE** (deferred this slice): `pause()` doesn't delay `end` (3842 = base
  schedule) and `speechSynthesis.paused` stays false. Needs a getter intercept +
  timer save/restore — its own follow-on.

## 2. The fix (three edits, all in the fake-completion block)

`speech_synthesis.cc` `StartSpeakingImmediately()` (the `IsCamouVoice` branch)
and `speech_synthesis.h`. No new key; `modules/speech/BUILD.gn` already deps
`//components/camoucfg` (sp4-voices).

### 2.1 Generation token (M-REUSE)

Add member `uint64_t camou_fake_generation_ = 0;`. Bump it **once per speak
start**, at the top of `StartSpeakingImmediately()` — before the `IsCamouVoice`
branch, so **every** speak start bumps it, not only the fake ones:
`const uint64_t gen = ++camou_fake_generation_;`. Every posted task captures `gen`
by value and guards
`self && u && self->camou_fake_generation_ == gen && u == self->CurrentSpeechUtterance()`.
On `cancel()`+re-`speak()` of the same object, the re-speak bumps the counter, so
the stale task's captured `gen` no longer matches and it no-ops; the fresh task
matches and fires. The current speak is always the max generation (bumped in
exactly this one place, so it stays monotonic).

**Why the bump lives at the top of the method, not inside the fake branch**
(whole-branch review, Important): a page can `speak()` a camou voice, `cancel()`,
then reassign the SAME utterance to a **non-camou** voice and re-`speak()` it.
That re-speak takes the real/mojo path, which would leave a fake-branch-only
counter untouched — so the first speak's stale fake tasks (old value, object
current again) would still fire phantom start/boundary/end onto the real speak.
Bumping for every speak start invalidates them regardless of the re-speak's path.
**Not exercisable on content_shell** (it has no TTS backend, so the non-fake
re-speak fast-fails and the utterance leaves `CurrentSpeechUtterance()` before the
stale tasks evaluate — the existing `u == CurrentSpeechUtterance()` guard already
suppresses them there); the fix is verified by construction and matters on a
backend-present target (Win/mac OS TTS). `verify_voices_ii.py`'s V-REUSE2 keeps it
as a regression guard.

### 2.2 End-timing jitter (M-LINEAR)

Scale `secs` by `(1 + delta)`, `delta ∈ [-0.15, 0.15]`, derived **deterministically**
from an inline FNV-1a-64 hash of the utterance text + voiceURI (UTF-8 bytes) —
the same hashing shape as `device_ids.cc`, inlined so `modules/speech` does NOT
couple to `canvas_noise.h`. The derivation is reread-stable (same text+voiceURI →
same delta → same end), matching the sp3a/audio determinism discipline. (The
text/voiceURI byte streams are folded with no separator, so distinct
`(text,voiceURI)` splits could collide — harmless here, only determinism is
required, not collision resistance.)

**No `voices:seed` key** — a deliberate tradeoff (whole-branch review, Minor):
the jitter breaks the exact linear formula, which is its job. The cost of no seed
is that the same `(text, voiceURI)` yields the **same** delta on every install,
so a prober who already suspects the formula and correlates one probe text across
installs sees a stable per-text signature. That is a narrow, second-order
correlation on a niche surface; a per-profile `voices:seed` (a keys.h triple-edit
threaded through the derivation) is the upgrade if voice-timing correlation ever
matters. Not taken here.

### 2.3 Word-boundary events (M-BOUNDARY)

Split `text` into words (runs of non-whitespace; **skip empty runs** — a
`charLength==0` boundary is itself a tell). For each word, `PostDelayedTask` a
call to the existing `WordBoundaryEventOccurred(u, charIndex, charLength)` at
`(charIndex / text.length) · jitteredSecs`, guarded like the others. Post order:
**start first, then the boundary loop, then end** — the first word's boundary is
at delay 0 (charIndex 0) and same-runner FIFO orders it after the 0-delay start
(the sp4-voices "two 0-delay tasks" precedent), so the sequence is
start → boundary(0) → … → boundary(last) → end. `charLength` = the word's length.
Task count = word count, **capped at 4096** (whole-branch review, Minor): a
realistic utterance is far under this, but an enormous one would otherwise post
O(words) pending delayed tasks synchronously at `speak()` time (a self-inflicted
renderer memory spike). Whitespace is ASCII-only (`is_ws` covers space/tab/CR/LF/
FF); `charIndex`/`charLength` are UTF-16 code units, per the Web Speech spec — so
non-ASCII whitespace won't split words, a fidelity nuance on non-Latin text, not
a spec violation.

## 3. Verify (RED-first) — `verify_voices_ii.py`

- **V-BOUNDARY (RED discriminator):** `'the quick brown fox jumps'` →
  `boundaryCount == 5`; each event `name=='word'`; `charIndex` sequence
  `[0,4,10,16,20]`, `charLength` `[3,5,5,3,5]`; strictly increasing charIndex; all
  fire between `start` and `end`. Pre-fix 0 → FAIL.
- **V-JITTER-A (RED discriminator):** speak a fixed text (`'z'×40`, whose derived
  `|delta|` is 0.136 — comfortably non-trivial) and assert `endMs` matches the
  **exact FNV-predicted jittered end** (the verify replicates the C++ FNV-1a-64 in
  Python: same offset/prime, same text-then-voiceURI fold order, same
  `(h>>11)/2^53` unit) within 60ms, AND is >60ms away from the unjittered linear
  value `text.length/(12.5·rate)·1000`. Pre-fix `endMs` == the linear value
  (≈3200ms) ≠ the jittered prediction (≈3636ms) → FAIL; post-fix `endMs` ≈ the
  jittered prediction → PASS. (Asserting the exact prediction is strictly stronger
  than a bare deviation band or a length-ratio check, whose pre-fix 3.994 already
  sits ~0.006 off 4.0.)
- **V-JITTER-B (determinism guard, not a discriminator):** same text twice in one
  session → `|endMs1 − endMs2| < 30ms` (reread-stable). Passes pre- and post-fix;
  labelled a guard.
- **V-REUSE (RED discriminator):** `speak(u)`, wait ~1000ms, `cancel()`,
  `speak(u)` (same object). The stale task would fire ~`(base − 1000)`ms after
  re-speak; the fresh (jittered) task fires ~`base·(1±0.15)`ms after. With a
  ~1000ms cancel gap these windows are well separated, so assert exactly one
  `end` and `ends[0] > (base − cancelGap + margin)` clearly above the stale
  window. Pre-fix the stale early-end fails it.
- **V-REUSE2 (guard, non-discriminating on this harness):** the fake→non-fake
  transition (§2.1). `speak()` a camou voice, `cancel()`, reassign the SAME
  utterance to a non-camou voice and re-`speak()`; assert no stale fake boundary
  fires after the re-speak. content_shell's backend-less real path fast-fails and
  the utterance leaves `CurrentSpeechUtterance()` before the stale tasks evaluate,
  so this reads 0 both pre- and post-fix here (cannot go RED on this box) — kept
  as a regression guard; the §2.1 fix is verified by construction.
- **V-REGR:** `verify_sp4_voices.py` 5/5 stays green — V3 asserts
  `events == ['start','end']` exactly and `ms > 400`; boundary events dispatch on
  the utterance but V3's array only records start/end/error, so it is unaffected
  (confirmed, not assumed).

## 4. Residual (still deferred after this slice)

- **pause()/resume() + `speechSynthesis.paused`** (M-PAUSE) — needs a paused-state
  getter intercept and end/boundary timer save-restore. Own follow-on.
- **default-voice path** — an utterance with `voice` unset takes the real
  (backend-less) mojo path, not the fake completion (sp4-voices §4). Behavior
  differs on backend-less targets; benign where an OS TTS backend exists. Deferred.
- **voice lang ↔ locale coherence** — operator/preset responsibility (sp4-voices §4).

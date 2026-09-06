# audio-ii (media-ii Slice 3) measurement (2026-09-06)

Checkout HEAD `a727b57805`, content_shell over `--ozone-platform=headless`.
Slice 3 of the media-ii program (Slice 1 = mediaDevices getSettings/label
coherence, Slice 2 = phantom-webcam; both shipped).

sp4-audio (`audio_buffer.cc` / `realtime_analyser.cc`) masks the audio-readback
surfaces JS reaches through an **AudioBuffer**: `AudioBuffer.getChannelData` and
the `AnalyserNode` get{Float,Byte}{Frequency,TimeDomain}Data getters. The mask
is a one-shot: `AudioBuffer::CamouEnsureNoised()` guards on `did_camou_noise_`
and perturbs each channel store exactly once, on first readback.

Two render-thread **input** paths hand JS raw samples that never pass through
that one-shot on the channel store JS actually reads. sp4-audio's measurement
doc (`2026-09-01-sp4-audio-surfaces.md`, "Residual audio-fingerprint paths")
flagged both. This slice measures them and closes the one that is exercisable
here.

---

## 1. The two residual input paths

1. **`AudioWorkletProcessor.process(inputs, …)`** — `inputs[bus][channel]` are
   raw `Float32Array`s over v8 backing stores (`input_array_buffers_`, filled by
   `CopyPortToArrayBuffers` on the worklet thread), **never** `AudioBuffer`
   objects, so `getChannelData`'s hook is never on the path. A worklet that
   hashes its input sees stock samples regardless of `audio:seed`.

2. **`ScriptProcessorNode.onaudioprocess` → `event.inputBuffer`** — this IS an
   `AudioBuffer`, but ONE reused instance (`external_input_buffer_`) that the
   render thread re-fills from the raw backing buffer every callback
   (`DispatchEvent`, under `GetBufferLock`). The `did_camou_noise_` guard fires
   on the first `getChannelData` and never again, so **callback 1 is masked and
   every later callback hands JS the raw rendered samples.**

3. **`DynamicsCompressorNode.reduction`** — a single scalar, low value.
   Deferred, per sp4-audio's own verdict. Not reopened.

## 2. Measured tells (RED, `measure_audio_ii.py` + `verify_audio_ii.py`)

**ScriptProcessorNode — CONFIRMED and verifiable.** OfflineAudioContext,
`OscillatorNode(sine 1kHz) → ScriptProcessorNode(4096) → destination`, capturing
`event.inputBuffer.getChannelData(0)` for the first callbacks:

```
                       callback 1 (first 4)                 callback 2 (first 4)
stock (config None)  [0, 0.14199429, 0.28111103, ...]    [-0.68539762, -0.57505697, ...]
audio:seed=777       [0, 0.14191451, 0.28107953, ...]    [-0.68539762, -0.57505697, ...]  <- byte-identical
```

Callback 1 differs (the one-shot masked it); **callback 2 is byte-identical to
stock** — the raw leak. `verify_audio_ii.py` against the pre-fix binary:

```
FAIL S1  cb2 stock!=777:False  cb3 stock!=777:False   (raw leak)
FAIL S2  777 vs 888 cb2 differs:False                 (seed has no effect past cb1)
PASS S3  gating   PASS S4  zero-preservation
```

**AudioWorklet — the tell is structural but UNEXERCISABLE on this box.** A
recorder `AudioWorkletProcessor` cannot be instantiated here at all:
`OfflineAudioContext.audioWorklet.addModule(url)` **never resolves**, over both a
`blob:` module URL and an `http://127.0.0.1` served module, with
`isSecureContext === true` in both cases (measured with an 8-second in-page
`Promise.race` guard — the phase tracker is frozen at `addModule-called`,
`timedOut:true`, never reaching `addModule-resolved`). content_shell
`--ozone-platform=headless` does not start the AudioWorklet thread, so there is
no way to feed a known signal into a worklet and read back what it received. No
RED evidence, no GREEN check is obtainable here.

## 3. Scope decision

- **Ship: ScriptProcessorNode input mask.** Confirmed tell, RED-first
  established, GREEN-checkable on this box.
- **Residual, NOT shipped: AudioWorklet input mask.** The tell is real
  (structurally certain — worklet inputs never touch `getChannelData`), but it
  is unexercisable on this verify host, so a perturbation for it would be an
  **unverifiable spoof**, which this repo forbids (CLAUDE.md, "Verifying
  spoofing claims"). Shipping blind code that mutates the audio **render
  thread** every quantum is exactly the case that rule exists for. Documented
  as an upgrade (§5), not coded-by-symmetry.
- **Deferred: `DynamicsCompressorNode.reduction`** (sp4-audio's verdict).

## 4. The fix (ScriptProcessor) — one method, one call site

`AudioBuffer::CamouNoiseNow()` (new, public): the body of the old
`CamouEnsureNoised` **without** the one-shot early-return — it perturbs every
channel store and sets `did_camou_noise_`. `CamouEnsureNoised()` becomes
`if (did_camou_noise_) return; CamouNoiseNow();`, so the getChannelData/copyFrom-
Channel one-shot behaviour is byte-for-byte unchanged.

`ScriptProcessorNode::DispatchEvent` calls
`external_input_buffer_->CamouNoiseNow()` every callback, **after** the
backing→external copy and **outside** the `GetBufferLock` scope (the lock is what
the render thread `TryLock`s; on failure it outputs a silent quantum, so the mask
stays off that path). `DispatchEvent` is `CHECK(IsMainThread())`, so the
per-channel `std::string` domain alloc that `CamouNoiseNow` inherits from
sp4-audio is fine here (main thread, not the render thread). Setting the guard
also suppresses a double-noise: `event.inputBuffer.getChannelData()` would
otherwise fire the one-shot on callback 1 on top of `CamouNoiseNow`.

- **No new key** — reuses `audio:seed` via `PerturbAudioFromConfig` and the
  `"audio-buffer-<c>"` domain.
- **No BUILD.gn change** — `modules/webaudio/BUILD.gn` already deps
  `//components/camoucfg` (sp4-audio). Confirmed with `gn check`.

### Why callback 1 is NOT the verify discriminator

`CamouNoiseNow` derives from the same content and the same `"audio-buffer-c"`
domain the one-shot used, so on callback 1 it reproduces the **exact same**
masked field — callback 1 is byte-identical pre/post fix. The leak the fix
closes is callbacks 2+, so S1/S2 assert on **cb2 and cb3**, not cb1.

## 5. Residual: the AudioWorklet input mask (designed, not shipped)

When a harness that runs AudioWorklet is available (a real browser under
Playwright, or a content_shell build with the worklet thread), the mask is:
perturb the destination float span inside `CopyPortToArrayBuffers`
(`audio_worklet_processor.cc`, worklet thread) right after
`.copy_from(audio_bus->Channel(...)->Span())` — i.e. mask the JS-facing copy
(`input_array_buffers_`), never the shared `AudioBus`, so the downstream graph is
untouched. Two constraints that fall out of the render-thread context:

- **No heap alloc on the worklet thread.** Use a single string-literal domain
  (`"audio-worklet-input"`), not the per-channel `"audio-buffer-"+NumberToString`
  form — that allocs. A single literal is also *more* coherent: `PerturbAudio-
  Samples` folds `ContentHash(samples)`, so two channels with identical content
  get identical noise (matching stock's identical channels), and differing
  content self-decorrelates.
- **Content-keyed, never call-keyed.** `PerturbAudioSamples` already keys the
  field on `eseed = seed ^ ContentHash(samples)` and position `i`, so an
  identical input block yields an identical masked block across `process()` calls
  and across renders — no call counter in the domain. (A call-keyed field would
  make a worklet summing `inputs[0][0]` over N calls see non-deterministic noise
  where stock is bit-deterministic — a new tell.)

## 6. Verify (RED-first) — S1–S4 (`verify_audio_ii.py`)

- **S1 (RED discriminator)** `audio:seed=777`: callbacks **2 AND 3** differ from
  stock (config None). cb1 excluded (see §4). RED pre-fix (cb2/cb3 stock==777).
- **S2 (determinism)** `audio:seed=777` across two separate content_shell
  processes → byte-identical cb1/cb2/cb3; `audio:seed=888` diverges at cb2. RED
  pre-fix (cb2 is raw, so 888==777).
- **S3 (gating)** config `{}` → cb1/cb2/cb3 byte-identical to a bare config-None
  run (mask gated on config; absent → raw).
- **S4 (zero-preservation)** `audio:seed=777`, no source connected (silent input)
  → every sample of every callback exactly `0.0` (the additive-zero rule on the
  new call site; silence must not become a tamper tell).

Regression gate: `verify_sp4_audio.py` 12/12 must stay green — the
`CamouEnsureNoised → CamouNoiseNow` refactor sits on the path every A-check
exercises.

# SP4-audio surface measurements

Measured 2026-09-01 against the WSL checkout `~/chromium/src` (HEAD `a727b57805`),
read-only. SP4-audio is spec §3.3: AnalyserNode + AudioBuffer readback noise
(`audio:seed`) and the `AudioContext` scalar getters. It is a **seeded-noise**
surface — the second after SP3a canvas — and per spec §8 it **reuses SP3's
`DeriveDelta`/`DeriveUnit` primitive** (not the canvas pixel function).

## Surfaces + choke points

### Readback noise (the seeded-noise core)

| Surface | Choke | File:line | Note |
|---|---|---|---|
| `AnalyserNode.getFloatFrequencyData` | `RealtimeAnalyser::GetFloatFrequencyData` | `realtime_analyser.cc:106` | reads `magnitude_buffer_[i]` → dB |
| `AnalyserNode.getByteFrequencyData` | `RealtimeAnalyser::GetByteFrequencyData` | `:130` | **independently** reads the same `magnitude_buffer_[i]` → scaled byte |
| `AnalyserNode.getFloatTimeDomainData` | `RealtimeAnalyser::GetFloatTimeDomainData` | `:171` | reads the time-domain input ring |
| `AnalyserNode.getByteTimeDomainData` | `RealtimeAnalyser::GetByteTimeDomainData` | `:197` | same time-domain source, byte-scaled |
| `AudioBuffer.getChannelData` | `AudioBuffer::getChannelData` | `audio_buffer.cc:204,219` | returns `channels_[idx].Get()` — the **LIVE** DOMFloat32Array (not a copy) |
| `AudioBuffer.copyFromChannel` | `AudioBuffer::copyFromChannel` | `:227,233` | copies channel data into a caller destination |

**Freq-domain coherence — noise the SOURCE, not each destination.** `GetFloatFrequencyData`
and `GetByteFrequencyData` each read `magnitude_buffer_[i]` independently (Float →
dB, Byte → the same dB scaled to 0–255). A page that reads both and checks
`Byte ≈ scale(Float)` must see them agree. So perturb `magnitude_buffer_` once
(after `DoFFTAnalysis` populates it), and BOTH readbacks inherit the same
perturbation → coherent by construction. Perturbing each destination separately
would let Float and Byte diverge — a tell. Same for the two time-domain readbacks:
perturb the shared time-domain source.

**`getChannelData` returns the live array.** Unlike a canvas readback (a fresh
buffer each call), `getChannelData` hands back `channels_[idx]` itself — the same
object every call, page-writable. In-place perturbation therefore (a) mutates the
buffer the audio graph may still use, and (b) on reread would double-apply unless
guarded. The AudioContext fingerprint (OfflineAudioContext render → read once) is
read-only, so in-place is acceptable IF idempotent: fold a content-hash of the
channel into the per-read seed so re-deriving the already-perturbed data is stable
(the canvas §7.3 reread-determinism pattern). `copyFromChannel` copies out, so
noising the destination copy is clean and stateless — prefer routing the
fingerprint there conceptually, but both must be covered.

### Noise algorithm (decided — canvas §7.3 precedent, reused)

Reuse `camoucfg::DeriveDelta(seed, domain, index, bound)` / `DeriveUnit(seed,
domain, index)` (SP3a `derive.{h,cc}`). Per element: a symmetric imperceptible
delta from `DeriveUnit` (e.g. `(DeriveUnit − 0.5) × 2 × ε`) added to the float
sample / magnitude. Seed = `audio:seed`, with a content-hash of the buffer folded
in (per-buffer variation + reread-determinism), each readback method its own
`domain` string. Magnitude ε small enough to be inaudible / sub-perceptual but to
change any hash (the canvas density/strength analog — pick a fixed tiny ε for
audio, no separate density needed). SplitMix64 finaliser, `<random>` banned (as
SP3a).

### Scalar getters — split by coherence risk

| Getter | Choke | Risk | Call |
|---|---|---|---|
| `AudioContext.baseLatency` | `AudioContext::baseLatency` `audio_context.cc:1241` (returns `base_latency_`) | low — a reported seconds value, not structural | SP0 override |
| `AudioContext.outputLatency` | `AudioContext::outputLatency` `:1248` (quantized hardware latency) | low — reported estimate | SP0 override |
| `destination.maxChannelCount` | `AudioDestinationNode::maxChannelCount` `audio_destination_node.cc:41` | low — reported channel cap | SP0 override |
| `BaseAudioContext.sampleRate` | `BaseAudioContext::sampleRate` `base_audio_context.h:124` (returns `destination_handler_->SampleRate()`) | **HIGH — buffer-length tied** | see decision |

**`sampleRate` coherence risk.** `sampleRate()` returns the destination handler's
*real* render rate, and the context's buffers + `OfflineAudioContext(ch, length,
rate)` render length are tied to that real rate. Spoofing the getter alone
(reporting 44100 while hardware renders at 48000) desyncs the claimed rate from
observable buffer behaviour: a page rendering a 1-second tone gets the real
rate's sample count while `sampleRate` claims another — a two-read contradiction,
the audio analog of the screen inner/layout tell. Entropy is also low: real
desktop audio is almost always 44100 **or** 48000, so the spoof buys little and
risks incoherence. **Decision pending (see below).**

## Config keys (new, dotted/colon per convention)

- `audio:seed` — the readback-noise seed (synthetic → colon).
- `AudioContext:outputLatency`, `AudioContext:baseLatency`,
  `AudioContext:maxChannelCount` — scalar overrides (synthetic namespace → colon;
  they mirror JS but under a synthetic `AudioContext:` group like `webGl:` — matches
  spec §3.3's `AudioContext:*` naming).
- `AudioContext:sampleRate` — only if the decision includes it.

## Worker / Offline coverage

The high-value AudioContext fingerprint (fingerprintjs / CreepJS) uses
`OfflineAudioContext` → render → `getChannelData`/`copyFromChannel` on the main
thread, so the AudioBuffer choke covers it. `AnalyserNode` (`RealtimeAnalyser`) is
main-thread live. `AudioWorklet` runs sample processing on the audio render thread
and can read raw samples there — note it as a possible residual (a worklet reading
its input could see un-noised samples); confirm during implementation whether it
reaches the same buffers, and defer with a stated note if it is a separate path
(the fonts-ii discipline).

## Verification (spec §6 items 6–7)

- **Seed stability (item 6):** same `audio:seed` across two loads → byte-identical
  `getFloatFrequencyData`; two different seeds differ; a worker/OfflineAudioContext
  read matches. RED-first against stock.
- **Context values (item 7):** `sampleRate` (if in scope) / `outputLatency` /
  `baseLatency` / `maxChannelCount` return the configured values.
- **Stock fallback:** no `CAMOU_CONFIG` → every value + readback equals stock.
- **No new surface / native accessors:** `[native code]`, `Object.keys` unchanged.

## Decision (2026-09-01, user-confirmed)

**Keep `sampleRate` real; spoof the rest.** SP4-audio covers the readback noise
(AnalyserNode + AudioBuffer) plus `outputLatency` / `baseLatency` /
`maxChannelCount`. `sampleRate` is NOT spoofed — buffer-length-tied coherence risk
(reported rate vs observable sample count) for negligible entropy (≈44100/48000).
No `AudioContext:sampleRate` key. Documented as a scope limitation, the audio
analog of the screen monitor-only call. (If future evidence shows a detector keys
on sampleRate and a coherent whole-pipeline spoof is worth it, that is a follow-on,
like fonts-ii.)

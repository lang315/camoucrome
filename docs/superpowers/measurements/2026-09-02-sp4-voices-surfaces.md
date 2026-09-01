# SP4-voices surfaces measurement (2026-09-02)

Checkout HEAD `a727b57805`, `out/Default` content_shell.

`speechSynthesis.getVoices()` returns the platform TTS voice list — names,
languages, and voice URIs that are OS/install-specific, a strong fingerprint
(and a coherence signal: the voices' langs should match the spoofed
locale/timezone). This slice injects a config-driven voice list AND fakes
`speak()` completion for the injected voices so a `speak()`-probe cannot detect
that they have no backend (the 2026-09-02 scope decision: full parity).

---

## 1. Stock behavior (content_shell)

`speechSynthesis.getVoices()` (with an `onvoiceschanged` wait) → **`count: 0`,
`voices: []`**. The headless WSL box has no speech-dispatcher / TTS backend, so
the list is empty. An empty voice list is itself a tell: real desktop Chrome on
Windows/macOS ships OS voices, and most real Linux Chrome installs have ≥1 via
speech-dispatcher. So the spoof is **injection** of a plausible configured list,
not filtering an existing one.

## 2. Blink choke points

`third_party/blink/renderer/modules/speech/speech_synthesis.cc`:
- `getVoices()` (line 95) returns `voice_list_` (member,
  `HeapVector<Member<SpeechSynthesisVoice>>`, decl `speech_synthesis.h:135`).
- `OnSetVoiceList(Vector<mojom::blink::SpeechSynthesisVoicePtr>)` (line 85) is the
  mojo push from the browser: clears `voice_list_`, rebuilds it, then
  `VoicesDidChange()` (fires `voiceschanged`). On the empty box this either never
  fires or fires with an empty vector.
- `SpeechSynthesisVoice` wraps a `mojom::blink::SpeechSynthesisVoicePtr`
  (`MakeGarbageCollected<SpeechSynthesisVoice>(std::move(mojom_voice))`).
- The mojom struct (`third_party/blink/public/mojom/speech/speech_synthesis.mojom:21`):
  `SpeechSynthesisVoice { string voice_uri; string name; string lang; bool
  is_local_service; bool is_default; }` — an **exact match** to Camoufox's
  `{uri, name, lang, isLocal, isDefault}`.

**speak() path** (same file):
- `speak(utterance)` (119) → `utterance_queue_.push_back` → if first,
  `StartSpeakingImmediately()` (231) → `utterance->Start(this)` which drives the
  mojo `Speak`. A fake voice has no browser backend → this errors / never
  completes.
- Events return via `DidStartSpeaking` (177, fires `start`),
  `DidFinishSpeaking(utterance, error_code)` (→ `HandleSpeakingCompleted`, 246),
  `SpeakingErrorOccurred`. `HandleSpeakingCompleted` fires `end` on `kNoError`
  and `FireErrorEvent` otherwise, then advances the queue.

## 3. Port design

### 3.1 Voice-list injection

A helper `ApplyCamouVoices()` builds `voice_list_` from the configured voices
(each config entry → a `mojom::blink::SpeechSynthesisVoice` struct →
`MakeGarbageCollected<SpeechSynthesisVoice>`). When the `voices` config is
present it REPLACES the platform list (Camoufox's default-behavior;
`voices:blockIfNotDefined` nuance folded away — config voices are authoritative).
Called from:
- `getVoices()` after `TryEnsureMojomSynthesis()` — guarded so it builds once.
- end of `OnSetVoiceList()` — so a later browser push cannot reinstate the real
  voices; re-apply then `VoicesDidChange()` so `onvoiceschanged` sees the injected
  list.

Absent `voices` → helper is a no-op, stock behavior (rule 5).

### 3.2 speak() fake completion

In `StartSpeakingImmediately()`, before `utterance->Start(this)`: if the current
utterance's voice URI is one of the injected voices, DON'T go to mojo. Instead
(final shape, after the whole-branch review):
- `voices:fakeCompletion` true (default): **`PostTask`** the `DidStartSpeaking`
  (fires `start` — a real TTS backend fires `start` asynchronously *after*
  `speak()` returns, so a synchronous start is a trivial tell; the start is
  posted, not called inline), then `PostDelayedTask` the `DidFinishSpeaking(…,
  kNoError)` (fires `end`) after `fakeElapsedTime = utterance.text.length /
  (charsPerSecond * utterance.rate)` seconds — `charsPerSecond` from
  `voices:fakeCompletion:charsPerSecond` (default 12.5). Since `secs > 0` for
  non-empty text (and same-runner FIFO orders two 0-delay tasks for empty text),
  `start` precedes `end`. **Both** posted tasks guard
  `self && u && u == self->CurrentSpeechUtterance()` — the `u &&` is load-bearing:
  `u` is a `WrapWeakPersistent` that is null after GC, and `CurrentSpeechUtterance()`
  is null on an empty queue, so without it a `cancel()`+GC in the delay window
  makes the guard `nullptr == nullptr` → true → `DidFinishSpeaking(nullptr)` →
  `pop_front()` on an empty deque + a null deref (a renderer crash reachable in
  normal operation). Delaying `end` by the wall-clock fake duration is more
  faithful than Camoufox's fire-immediately-with-a-fake-elapsed-field.
- `voices:fakeCompletion` false: `SpeakingErrorOccurred(utterance)` (a
  deterministic, synchronous error — Camoufox's DispatchError path).

This closes the two common `speak()`-probes: a site listening for
`onstart`/`onend`/`onerror` sees an **async** `start` → wall-clock-delayed `end`
(or a deterministic error), not "voice in the list but speak() silently does
nothing / errors unexpectedly", and not the synchronous-start tell. Residual
tells that a *determined* probe can still read are enumerated in §4 (linear `end`
timing; no boundary/word events; pause/resume divergence; default-voice path).

### 3.3 Config accessor + keys

`voices` is an array of objects — CAMOU_CONFIG is already JSON (camoucfg parses
it with `base::JSONReader` internally), but the public camoucfg API exposes only
scalar getters + `GetStringList`. Add a **typed** accessor that keeps `base::Value`
out of the public API and encapsulates the parsing:

```cpp
struct VoiceConfig {
  std::string voice_uri;
  std::string name;
  std::string lang;
  bool is_local_service = true;
  bool is_default = false;
};
std::vector<VoiceConfig> GetVoices(const ConfigScope& scope);  // empty if absent/invalid
```

Config entry keys mirror the JS `SpeechSynthesisVoice` property names so the
operator config reads like what `getVoices()` returns:
`{"voiceURI":"...","name":"...","lang":"en-US","localService":true,"default":false}`.
`localService` defaults true, `default` defaults false, missing `voiceURI` falls
back to `name`.

Keys (colon namespace `voices:`; bare `voices` is a JS-adjacent list name — use
`voices:list` to stay namespaced per `EveryKeyIsNamespaced`):
- `voices:list` — the JSON array (consumed by `GetVoices`).
- `voices:fakeCompletion` — bool (default true), `GetBool`.
- `voices:fakeCompletion:charsPerSecond` — double (default 12.5), `GetDouble`.

Keys 64 → 67.

## 4. Coherence & residual (documented)

- **Voice lang ↔ locale coherence:** the injected voices' `lang` values should be
  consistent with the spoofed `locale:tag` / `navigator.language` (a fr-FR browser
  exposing only `en-US` voices is a tell). Operator/preset responsibility; the
  fingerprint-preset layer supplies a coherent voice set. Documented, not enforced.
- **`voices:blockIfNotDefined` folded away:** when `voices:list` is present the
  config voices are authoritative (real platform voices replaced); there is no
  partial-merge mode. On content_shell the platform list is empty anyway.
- **Posted tasks vs cancel/navigation:** both the async `start` and delayed `end`
  tasks guard `self && u && u == CurrentSpeechUtterance()`; `cancel()` clears the
  queue (→ current is null → guard fails, nothing fires), and window teardown
  nulls `self` (WeakPersistent). Worker scope: SpeechSynthesis is window-only
  (`Exposed=Window`), so no worker path.
- **Stale-timer on utterance-object REUSE (residual, voices-ii):** if a page
  `cancel()`s then re-`speak()`s the SAME `SpeechSynthesisUtterance` object, it
  becomes current again, and the first (stale) delayed task can no longer be told
  apart from the fresh one by the `== CurrentSpeechUtterance()` guard → a possibly
  EARLY `end`. Not a crash/UAF/double-fire (the later legitimate task finds the
  queue advanced and no-ops); a per-speak generation token would close it.
  Deferred.
- **Linear `end` timing is itself a tell (residual, voices-ii):** `end` fires at
  exactly `text.length / (charsPerSecond * rate)`; a probe varying length/rate
  reads a perfectly linear signal unlike real TTS jitter. The wall-clock delay
  fixes the *synchronous-end* tell but not the *deterministic-formula* tell.
- **Default-voice speak takes the real path (residual):** an utterance with
  `u.voice` unset → `IsCamouVoice` false → the real (backend-less on
  content_shell) mojo path, so it behaves differently from an explicitly-injected
  voice. Benign where a real OS TTS backend exists; a tell on backend-less
  targets. Deferred (voices-ii).
- **pause()/resume()/boundary events** on a fake voice are not synthesized (they
  go to mojo and no-op with no backend) — a deeper probe surface, deferred
  (voices-ii). async-start / end / error (the common probes) are covered.
- **Verification honesty:** V1 (list injected) and V3 (async start→delayed end)
  are genuine RED→GREEN proofs. V2 (`{}`→count 0) is DEGENERATE — content_shell's
  stock voice list is empty, so it cannot distinguish rule-5 (real list preserved)
  from a buggy unconditional clear; rule-5's non-destructiveness (the
  `voices.empty()` early-return before `voice_list_.clear()`) rests on code
  inspection, and "config absent + a nonempty real list" is not exercisable in
  this TTS-backend-less harness. V4 (fakeCompletion:false) pins the exact error
  contract (`error:synthesis-failed`, synchronous) after the whole-branch tightening.

## 5. Slice scope summary

| surface | this slice |
|---|---|
| `getVoices()` list | **inject** — config `voices:list` replaces the list (getVoices + OnSetVoiceList) |
| `speak()` on an injected voice | **fake completion** — async `start` → wall-clock-delayed `end` (`voices:fakeCompletion` + `:charsPerSecond`) or deterministic synchronous error |
| voice lang ↔ locale coherence | operator/preset responsibility (documented) |
| linear `end` timing / default-voice path / utterance-reuse early-end | residual tells, defer (voices-ii) |
| pause/resume/boundary on fake voice | defer (voices-ii) |

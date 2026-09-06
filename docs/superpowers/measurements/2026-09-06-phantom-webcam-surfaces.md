# phantom-webcam (media-ii Slice 2) measurement (2026-09-06)

Checkout HEAD `a727b57805`, content_shell over the `127.0.0.1` echo_server.
Slice 2 of the media-ii program (Slice 1 = getSettings/label coherence, shipped).

sp4-media injects a configured webcam/mic COUNT into `enumerateDevices()`. On a
host that lacks that hardware (the build box is camera-less, §1.3), the count is a
lie `getUserMedia` exposes.

---

## 1. The tell (measured, `measure_phantom.py`)

sp4 config `webcams=1, micros=1`, camera-less box, **no** `--use-fake-device`:

```
A (real, no fake-device):  videoinputs=1  getUserMedia({video:true}) -> NotFoundError
B (--use-fake-device):     videoinputs=1  getUserMedia({video:true}) -> ok   (audioinputs 1->3)
```

Run A is the tell: `enumerateDevices()` lists 1 videoinput, but `getUserMedia`
rejects with **`NotFoundError`** — *device absent*. A page cross-checking the two
sees a **phantom webcam**: a listed device that cannot exist. Run B (the flag) is
why the Slice-1 verify never saw it — `--use-fake-device` backs the phantom with a
synthetic stream.

## 2. Why `--use-fake-device` is NOT the fix (measured evidence)

The flag replaces the *entire* device list with Chromium's fixed fake set — Run B's
`audioinputs` jumped 1→3, ignoring the configured count. It is process-wide and
unconditional: it caps the openable count at (3 audio / 1 video / 3 out) regardless
of config, emits a **rotating test-pattern** video frame (a louder tell than
NotFoundError to any page that samples a frame), and needs `--use-fake-ui` (auto-
grants everything — a second anomaly) to avoid a headless prompt hang. It is a test
harness, not a spoof primitive. Not used.

## 3. The fix — error remap, not stream synthesis

What real Chrome returns for a device that is *present but unusable* (camera busy in
Zoom, hardware glitch) is **`NotReadableError`**, never `NotFoundError`.
`NotFoundError` means *absent* — the one thing that contradicts a listed device. So
the coherent answer for a configured-but-unbacked device is:

> `getUserMedia` → **`NotReadableError`** (present, cannot start), not `NotFoundError`.

This is a pure Blink error remap on the failure path — no frame synthesis, no
browser-process work. A page probing enumerate↔gUM coherence is satisfied
(NotReadableError is coherent with a listed device); a real user hits
NotReadableError constantly.

## 4. Choke point (measured)

`third_party/blink/renderer/modules/mediastream/user_media_request.cc`, the `Fail()`
error switch (~940-985): `case Result::NO_HARDWARE:` sets
`exception_code = kNotFoundError` (line ~969-971). `NO_HARDWARE` is produced in
`user_media_processor.cc` (~884/907/1134/1158) for the "no devices of the requested
kind" case.

Remap in that one case:
```cpp
case Result::NO_HARDWARE:
  if (/* spoofing claims the requested kind is present */) {
    exception_code = DOMExceptionCode::kNotReadableError;
    result_enum   = UserMediaRequestResult::kNotReadableError;   // (or the nearest enum)
  } else {
    exception_code = DOMExceptionCode::kNotFoundError;
    result_enum   = UserMediaRequestResult::kNotFoundError;
  }
  break;
```

Gate (config already exists — no new key): `mediaDevices:enabled` AND
`((Video() && webcams>0) || (Audio() && micros>0))`. `GetExecutionContext()` is in
scope (checked at ~940) for `ScopeFor`; `Video()`/`Audio()` give the requested kinds
(`user_media_request.h:130-131`); `webcams`/`micros` are `kMediaDevicesWebcams` /
`kMediaDevicesMicros` (defaults 1/3). No new keys, no helper.

- **DEPS/BUILD:** `user_media_request.cc` is in `modules/mediastream` — the same
  target whose `//components/camoucfg` dep sp4-media.patch already carries (the
  Slice-1 C1 fix). No BUILD.gn change; confirm with `gn check`.

## 5. Residuals (documented, not claimed)

- **A page that NEEDS the stream still gets none.** NotReadableError satisfies a
  coherence probe, not a consumer. A black `MediaStreamTrack` that actually opens is
  the upgrade — it IS browser-process work. Scoped out (Slice 2b).
- **pre-N / post-M enumerate count** (Slice 1 residual) — unchanged: pre-grant shows
  configured N, post-grant shows real M. Synthesizing phantom enumerate entries
  post-grant (`SyntheticDeviceId(seed, kind, "phantom:<ordinal>", origin)`) is
  Slice 2b.
- **Combined `{video,audio}` request where only one kind is spoofed-present** — the
  gate remaps if EITHER requested-and-configured kind is present; the genuinely-
  absent other kind then also reads NotReadableError. Rare; documented. (The common
  case is a single-kind request or both kinds configured.)

## 6. Verify (RED-first) — P1–P6

- **P1** stock (config `{}`), camera-less: `getUserMedia({video:true})` →
  `NotFoundError` (the RED baseline = Run A).
- **P2** spoof `webcams=1`, camera-less: → `NotReadableError`.
- **P3** spoof `webcams=0` (`micros=1`): video → still `NotFoundError` (no phantom
  claimed for video → no remap).
- **P4** config `{}` → stock exact (P1 unchanged).
- **P5** real device present — stand in with `--use-fake-device`: `getUserMedia`
  **succeeds** and is NOT remapped (the remap only fires on the NO_HARDWARE failure
  path).
- **P6 (no-regression, NOT the audio remap):** on this headless content_shell,
  `getUserMedia({audio:true})` fails with `NotSupportedError` at an **upstream** path
  (no audio subsystem) that never reaches `NO_HARDWARE`, so the `Audio() && micros>0`
  branch of the gate is **unexercised here**. P6 asserts the value is UNCHANGED
  (`NotSupportedError`), proving the remap doesn't disturb the audio path — it does
  NOT demonstrate the audio remap. The audio branch is verified only **by code
  symmetry** with the video branch (and with sp4-media's already-shipped audio gate);
  a positive audio-`NO_HARDWARE` demonstration needs a host with an audio subsystem
  but no microphone, which this box is not. Audio is low-priority per sp4-media §1.5b
  ("audio far less exposed").

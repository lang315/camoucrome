# S3: media device ids after a grant — design

This is backlog item S3 (`plans/2026-10-02-long-term-roadmap.md`), found in
step 2 (`measurements/2026-10-step2-baseline.md` §6 item 3). The pin is Chrome
`154.0.8037.93`. Every Chromium line cited below is at that tag and was read
from the source, not assumed. Abbreviations:

- MDM = `content/browser/renderer_host/media/media_devices_manager.cc`
- MDU = `content/browser/media/media_devices_util.cc`
- PC = `content/browser/renderer_host/media/media_devices_permission_checker.cc`
- BMD = Blink's `third_party/blink/renderer/modules/mediastream/media_devices.cc`

## Problem

With camera and microphone granted, stock Chrome on the Windows host lists its
real `audiooutput` device with a real `deviceId` and `groupId`. The fork lists
the claimed `audioinput`, `videoinput` and `audiooutput` devices with every id
`""`. That list is a shape no real Chrome produces with a grant, and it leaves
`mediaDevices:seed` unmeasurable.

### Root cause

- The host has no microphone and no camera, only the speaker
  (`measurements/step2-154/tables.md`: stock `oracle.mediaDevices` is
  `[["audiooutput", "", 0, 0]]`).
- `sp4-media.patch` (in `MediaDevices::DevicesEnumerated`) decides "pre-grant"
  from `result_contains_nonempty_input_device_ids`. Chromium sets that flag only
  for `audioinput` and `videoinput` entries (BMD:1458-1472). On a host with no
  inputs it is false even after a grant, so the patch replaces the whole list
  with blank entries, real `audiooutput` id included.
- The post-grant branch (the seed transform) needs real input devices. With
  none, the claimed camera and microphone have nothing to carry an id.

### Two more tells in the same code

1. **The kinds change across the grant.** Before the grant the fork claims a
   `videoinput`. After the grant the transform keeps only real devices, so on a
   host with a mic and no camera, the camera disappears.
2. **The labels of the sentinel entries.** On Windows Chrome lists `default` and
   `communications` audio entries ahead of the real devices, for input and
   output alike, whenever at least one device exists
   (`media/audio/win/audio_manager_win.cc:184-189`). They are labelled
   `<localized prefix> - <device>` (`media/audio/audio_device_description.cc:164-186`).
   The transform gives every entry of a kind the same configured label, so three
   entries all read `Speakers (Realtek Audio)`.

## Approaches considered

- **(A) Renderer only.** Synthesize ids for claimed-but-absent kinds in
  `DevicesEnumerated`. On a host without a camera, the reply holds no
  `videoinput` entry at all (MDM:1204-1213), so the renderer cannot see the
  camera grant. It would need an async `HasPermission` round trip (BMD:1303).
  The ids, the per-document group salt and the input capabilities would all be
  built by hand.
- **(B-wide) Phantoms in the browser's device snapshot.** Chrome's gating, HMAC
  and group salt all apply. But the snapshot also feeds getUserMedia,
  setSinkId, the device picker (`MediaCaptureDevicesImpl`), the removed-device
  stop and devicechange. getUserMedia would change from an early NotFoundError
  to a late NotReadableError, and phantoms would reach code that opens devices.
- **(B-narrow, chosen) Phantoms in the enumerate reply only.** Add raw phantom
  entries to the per-type `enumeration` in
  `MediaDevicesManager::OnDevicesEnumeratedAndRanked` (MDM:1152), before the
  translation loop (MDM:1198). Chrome then applies its own logic to them:
  - per-type permission gating, including the camera on a host without a
    camera, and the `audiooutput` gate on mic or speaker-selection (PC:72-91);
  - before the grant, one blank entry per non-empty type (MDM:1206-1208);
  - the deviceId HMAC over origin plus the per-storage-key salt (MDU:249-253),
    which is stable per profile, as on stock;
  - the groupId salt, which includes the per-document frame salt (MDU:60), so
    groupId changes per document, as on stock;
  - the capability probes, which iterate this same `enumeration`
    (MDM:1239-1241), so the list and capabilities sizes stay equal.

  getUserMedia, setSinkId, devicechange and the picker still read the real
  snapshot, so their behaviour does not change. On a claimed kind,
  `phantom-webcam.patch` already turns getUserMedia's NotFoundError into
  NotReadableError.

The research agent recommended (A), on the grounds that it is smaller. (B-narrow)
was chosen instead for three reasons:
- the camera grant is visible only in the browser;
- the HMAC, the per-document group salt and the video capability fallback come
  from Chrome itself, so none is reimplemented;
- the change stays inside one function's reply.

## Design

### Browser: phantom entries (new patch `s3-media-phantoms`)

In `OnDevicesEnumeratedAndRanked`, before the translation loop, read
`mediaDevices:enabled` through `camoucfg::GlobalScope()`.
`//content/browser:browser` already depends on `//components/camoucfg` and
`content/browser/DEPS` allows it (`sp0-config-layer.patch`). When the key is
true:

- **Which kinds.** A kind gets a phantom only when its raw list is **empty** and
  its configured count (`mediaDevices:micros`, `:webcams`, `:speakers`) is above
  zero. Real hardware is never touched. With the key absent or false, nothing
  changes (rule 5).
- **How many.** One phantom device per claimed kind, whatever the count. The
  counts come from browserforge's `multimediaDevices` (`client/python/camoucrome/gen.py:285-289`),
  which records the pre-grant list. That list holds at most one blank entry per
  kind (MDM:1206), so a count says only whether the kind is present. The
  pre-grant branch of `sp4-media.patch` already reads it that way.
- **The phantom device.** Raw `device_id` is `camou-phantom-<kind>`. Raw
  `group_id` is `camou-phantom-group-<kind>`. The label is the configured
  per-kind label (`mediaDevices:cameraLabel`, `:microphoneLabel`,
  `:speakerLabel`), with the same defaults as `sp4-media.patch`. Neither raw
  string reaches a page: `TranslateMediaDeviceInfo` HMACs both, and a blank
  entry carries neither.
- **Audio sentinels on Windows (`BUILDFLAG(IS_WIN)`).** A phantom audio kind
  lists `default`, `communications`, then the phantom device, which is the order
  `audio_manager_win.cc:184-189` produces. The sentinels carry the phantom's raw
  `group_id` (`audio_manager_base.cc:795-826`: sentinels share the group of the
  device they stand for). Their labels are
  `AudioDeviceDescription::GetDefaultDeviceName() + " - " + label` and
  `GetCommunicationsDeviceName() + " - " + label`. The prefix is localized, and
  the joiner is hard-coded as in `audio_device_description.cc:164-186`. The
  translation passes `default` and `communications` through unhashed
  (MDU:243-246). Other platforms get no sentinels. Linux and macOS shapes are an
  open item for the Linux beta.
- **Audio input capabilities.** The video probe on an unknown id returns an
  empty format list. Chrome's own fallback then reports six I420 formats
  (MDM:1033-1041), the same shape a camera with no format list gets, so video
  needs nothing. The audio probe on an unknown id returns `nullopt` on a host
  with no inputs, and Blink then drops the mic's audio capabilities
  (`input_device_info.cc:67`), a shape no granted real mic has. For a phantom
  `audioinput` id (the device and its sentinels), the loop at MDM:1291-1320
  supplies the parameters Windows itself uses as its fallback: stereo, 48 kHz
  (`audio_manager_win.cc:202-221`). It does this by calling
  `GotAudioInputCapabilities` directly, the way the `use_fake_devices_` branch
  does (MDM:1308-1313).
- The phantoms are never written into `current_snapshot_`.

### Renderer: changes to `sp4-media.patch`

- **Grant test.** The post-grant branch runs when any entry of any kind has a
  non-empty `device_id`, not only an input entry. A real `audiooutput` id proves
  a mic or speaker-selection grant (PC:72-85). With the phantoms, the claimed
  inputs carry ids after a grant anyway.
- **Pre-grant branch.** Same shape as before: one blank entry per claimed kind.
  The browser already sends that for phantom kinds. The branch stays because it
  also hides a kind the host really has when its count is 0.
- **Transform labels.** For an entry whose `device_id` is `default` or
  `communications`, Chrome's label is `<prefix> - <name>`. The transform keeps
  `<prefix> - ` and replaces only the name with the configured label. Every
  other entry gets the configured label, as today.
- `SyntheticDeviceId(seed, kind, id, origin)` is unchanged. Its input is now
  Chrome's HMAC (phantom or real), and its group input is Chrome's per-document
  group id, so the output stays per document. It already passes `default` and
  `communications` through.

### Not in scope

- getUserMedia on a phantom kind. It stays NotFoundError, remapped to
  NotReadableError by `phantom-webcam.patch`.
- A real host with more devices than the identity claims (for example two real
  mics). That is a pre-existing coherence question with its own slice.
- The Linux and macOS sentinel shapes.

## Verification (RED first)

Add `scripts/verify_s3_media.py`. It asserts an `EXPECTED` row count; a zero
exit alone is not enough. On WSL (content_shell, no media hardware at all) it
runs with `--use-fake-ui-for-media-stream`, which sets `has_permissions` for
all three types without a getUserMedia call (PC:154-160, 218-223). It never
uses `--use-fake-device-for-media-stream`: fake devices would make every kind
non-empty and hide the bug.

| Row | Check | Where it is RED on `main` |
|---|---|---|
| S3-1 | granted: every claimed kind is listed, and every non-sentinel `deviceId` is 64 hex | WSL: all ids `""` |
| S3-2 | granted: every `groupId` is 64 hex | WSL: `""` |
| S3-3 | not granted: one blank entry per claimed kind, every field `""` | guard, GREEN on both |
| S3-4 | the kinds are the same before and after the grant | guard on WSL (a device-less host takes the pre-grant branch both times). RED only on a host with exactly one real input kind, which is not run here and is recorded as such |
| S3-5 | same origin, same profile, two documents: `deviceId` equal, `groupId` different | WSL: `""` |
| S3-6 | two origins: `deviceId` differs | WSL: `""` |
| S3-7 | granted: the phantom mic's `getCapabilities()` has `sampleRate` and `channelCount`, and the phantom camera's has `width`/`height` ranges | WSL: no ids, empty capabilities |
| S3-8 | `mediaDevices:enabled` absent: the list equals stock content_shell (empty) | guard (rule 5) |

The `default` and `communications` sentinels are Windows only, so the Windows
build carries them:

| Row | Check | Where it is RED |
|---|---|---|
| S3-W1 | Windows host, fork vs stock, both granted through the same client (CDP `Browser.grantPermissions`): the stock arm's `audiooutput` ids are non-empty on both arms, compared by shape (kinds, id lengths, label prefixes, which ids are empty), never by value | `main`: the fork's are `""` |
| S3-W2 | Windows host, fork: the phantom `audioinput` starts with `default` and `communications`, labelled with the same prefixes as the real `audiooutput` sentinels on the same page | `main`: no ids, no sentinels |

`verify_media_ii.py`, `verify_phantom.py` and `verify_sp4_media.py` must stay
GREEN. They use fake devices, so they cover the real-device transform path.
Step 2's `mediaDevices.ids` row is re-run on the host. camoucrome-80 is told
before any headed run on the host (the console session 1 rule).

## Costs and risks

- The change adds one new content patch, at the end of `patches/series`. It
  touches two functions in a file Chromium edits often, so it adds rebase
  surface at each re-pin. If the code it hooks moves, `git apply --3way` fails
  loudly.
- A phantom's raw id is a fixed string. Its HMAC is still keyed by the
  per-profile salt and the origin, so phantoms are as linkable across profiles
  as real devices: not at all.
- The 48 kHz stereo choice for the phantom mic is Windows' own fallback, not a
  capture from a real mic. It is recorded as such in the measurement doc.

# S3b: device ids that round-trip — design

S3b follows S3 (`specs/2026-10-10-s3-media-device-ids-design.md`). It fixes:
- a tell that predates S3 and that S3's final review uncovered;
- a tell that S3 itself introduced;
- the S3 follow-ups listed in `measurements/2026-10-s3-media-device-ids.md` §8.

The pin is Chrome `154.0.8037.93`. Every Chromium line below was read on the build box, at `camoucrome/main` = `4b5fdddcd8`. The full research notes, with `[read]`/`[inferred]` marks, are summarised here.

Abbreviations:
- MDU = `content/browser/media/media_devices_util.cc`
- AOAH = `content/browser/renderer_host/media/audio_output_authorization_handler.cc`
- MDM = `content/browser/renderer_host/media/media_devices_manager.cc`

## Problem

### 1. A listed id cannot be used (since media-ii/sp4-media, with a seed set)

The browser hashes every raw device id with one function, `GetHMACForRawMediaDeviceID` (MDU:239-258). The hash is HMAC-SHA256, keyed by the origin, over the raw id plus a salt. `""`, `default` and `communications` pass through unhashed (MDU:243-247). Every reverse lookup re-hashes raw ids with that same function and compares (MDU:260-266).

The fork then hashes again in the renderer: the id becomes `SyntheticDeviceId(seed, kind, <browser id>, origin)`. This happens in the enumerate list (sp4-media) and in a track's `getSettings()`/`getCapabilities()` (media-ii-track). The page therefore sees `Synth(HMAC(raw))`, but the browser only ever matches `HMAC(raw)`.

The result, with a seed set and after a grant:
- `audio.setSinkId(<listed real speaker id>)` fails with **NotFoundError**. AOAH `TranslateDeviceID` (:295-319) finds no match.
- `AudioContext.setSinkId(<listed id>)` fails with **NotFoundError**, in the renderer (`audio_context.cc:286, 356-360`). Its id set comes from a direct browser enumerate that carries the unrewritten ids.
- `new AudioContext({sinkId: <listed id>})` gets an `error` event and stops rendering (`audio_context.cc:1988-1996`).
- `getUserMedia({audio|video: {deviceId: {exact: <listed id>}}})` fails with **OverconstrainedError("deviceId")**. The renderer matches the constraint against capability lists that carry browser ids (`media_stream_constraints_util_audio.cc:285-289`, `user_media_processor.cc:798-822, 1028-1063`).

Stock Chrome never rejects an id it has just listed, so this is a direct tell. No verify script calls these paths.

### 2. The phantom speaker cannot be used (new in S3)

On a host with no output device, S3 lists a phantom speaker. AOAH translates against the raw device list (:285-292), which has no phantoms. So `setSinkId(<phantom id>)` gives NotFoundError, with or without a seed. On Windows, `setSinkId("communications")` also fails there, because the raw output list is empty. And `NotifyDeviceChange` translates the raw snapshot (MDM:1931-1934): on the first devicechange, an AudioContext whose sink is the phantom loses its sink and errors.

On such a host, stock `setSinkId("")` resolves: AOAH reports `OUTPUT_DEVICE_STATUS_OK` with `UnavailableDeviceParams` (AOAH:336-352, `audio_system_helper.cc:123-131`), and playback goes to a silent fake sink (`audio_manager_base.cc:614-659`).

### 3. S3 follow-ups taken into this slice

- **M1:** the browser phantoms gate on `mediaDevices:enabled` only, while the renderer transform also needs a seed. With enabled set and no seed, the phantoms carry configured labels next to a real speaker that shows its real label.
- **M5:** the label defaults are written out in three patches.
- **M9:** style: include order, lines over 80 columns, a double blank line. (`<algorithm>` is already included at MDM:10, so that part of M9 needs no change.)
- **M10:** S3-W2 accepts `len >= 3`.
- **M11:** S3-8 compares only which fields are empty.

## Approaches considered

- **(A, chosen) Fold the seed into the browser's HMAC.** In `GetHMACForRawMediaDeviceID`, after the passthrough return, add the seed to the HMAC message. Every hash and every match goes through this one function:
  - enumerate and devicechange;
  - the capability lists and the getUserMedia match (`media_stream_manager.cc:146-173`);
  - track ids (`:2279-2283`);
  - output authorization;
  - selectAudioOutput;
  - the public `media_device_id.cc` API;
  - groupId.

  So they all agree by construction, and the renderer stops rewriting ids. `GotSalt` (MDU:43-66) was rejected as the hook: the empty-salt MediaAccessRequest (`media_stream_manager.cc:1724-1727`) and the public API build their own salts and would bypass it.
- **(B) Map ids back in the renderer.** Keep `Synth(HMAC)` and map it back in setSinkId, AudioContext and the getUserMedia constraints. That means many call sites and async lookups, and it breaks for an id the page stored before it enumerated. Rejected.
- **(C) Drop the seed from ids.** Remove the renderer rewrite and use Chrome's ids as they are. This is the smallest change, but ids stop rotating per identity when a profile is reused across identities. Rejected by the owner.

## Design

### One activation rule (M1)

A new camoucfg helper `MediaDevicesActive(scope)` is true when `mediaDevices:enabled` is true and `mediaDevices:seed` is non-zero. These all use it:
- the browser phantoms;
- the HMAC fold;
- the renderer's pre-grant shape and label masking;
- the track label mask.

With the helper false, nothing changes (rule 5). `gen.py` always sets a seed. The label defaults (`Integrated Camera`, `Microphone (Realtek Audio)`, `Speakers (Realtek Audio)`) become constants in one camoucfg header, which all three patches read (M5).

### Browser: the seed in the HMAC (new patch `s3b-device-id-seed`)

In `GetHMACForRawMediaDeviceID`, after the passthrough return at MDU:243-247, when `MediaDevicesActive(GlobalScope())` is true, add one `hmac.Update` of the seed's 4 bytes, little-endian (`base::U32ToLittleEndian`; the key is `uint32`), after the salt. Both `use_group_salt` branches get it, so groupId keeps its per-document frame salt.

The result:
- ids keep the stock shape: 64 lowercase hex, separate per origin, stable per profile;
- they change when the seed changes;
- the seed is never stored.

`//content/browser` already depends on camoucfg (`BUILD.gn:150`, `DEPS:48`). The function runs on the UI and IO threads, and the parsed config is immutable. `gn check` and `checkdeps` are run explicitly.

### Renderer: no id rewriting

- **sp4-media:**
  - the post-grant branch keeps label masking (`MaskedDeviceLabel`) and the capability copy from S3, but passes ids and groupIds through unchanged;
  - the pre-grant blank shape is unchanged;
  - the capability `device_id` rewrite goes.
- **media-ii-track:** `CamouMaskDeviceId` and its call sites go. `CamouMaskLabel` stays.
- **camoucfg:** `SyntheticDeviceId` and its tests are removed once nothing calls them.

### Phantom speaker output (I2)

`CamouWithPhantoms` moves from a file-local function in MDM to a declaration in `media_devices_manager.h`, gated by `MediaDevicesActive`. Two places use it:
- **AOAH `TranslateDeviceID`** matches the hash against the phantom-augmented output list. On a match whose raw id is a phantom (`camoucfg::IsPhantomDeviceId`) or a phantom-sourced `communications` sentinel, it authorizes `media::AudioDeviceDescription::kDefaultDeviceId`, which is exactly the stock default-sink path. It passes `id_for_renderer = ""`, as AOAH does for every non-session path.
- **`NotifyDeviceChange`** runs its translation over the phantom-augmented enumeration, so devicechange listeners, including AudioContext, keep seeing the phantom.

The phantoms still never enter `current_snapshot_`.

### Style (M9)

The include order in `s3-media-phantoms`, and `git cl format` on `media_phantoms.{h,cc}` and their tests; plus the double blank line in `device_ids_unittest.cc`.

## Verification (RED first)

**`scripts/verify_s3_media.py`** (WSL content_shell, `--use-fake-ui-for-media-stream`, real WSLg mic and speaker): EXPECTED goes from 8 to 12.

| Row | Check | RED on `main` |
|---|---|---|
| S3-9 | granted, seed set: `audio.setSinkId(<listed real audiooutput id>)` resolves, and `audio.sinkId` equals it | NotFoundError |
| S3-10 | granted, seed set: `getUserMedia({audio: {deviceId: {exact: <listed real audioinput id>}}})` succeeds, and the track's `getSettings().deviceId` and `groupId` equal the listed entry's | OverconstrainedError |
| S3-11 | granted, seed set: `new AudioContext()` then `setSinkId(<listed id>)` resolves | NotFoundError |
| S3-12 | granted, `mediaDevices:enabled` true and no seed: the list equals stock content_shell (kinds, labels, empty-field shape). This is M1's one activation rule | main lists a labelled phantom camera |

- S3-8 (M11) compares labels by value against stock content_shell, and compares the `getCapabilities()` key sets.
- The existing rows are updated where the id rewrite is gone. For example, S3-5's fork relation now comes from Chrome itself, and it must still match stock.

**`scripts/verify_s3_host.py`** (Windows host, headless): EXPECTED goes from 4 to 7.

| Row | Check | RED |
|---|---|---|
| S3-W5 | config `micros: 0, webcams: 0, speakers: 1`, mic granted: the fork's non-sentinel `audiooutput` id is 64 hex | a mutant restoring the input-only grant test |
| S3-W6 | `setSinkId(<listed real speaker id>)` resolves on the fork, as on stock | the S3 build: NotFoundError |
| S3-W7 | one user-data-dir, three launches with seeds A, A, B: the fork's speaker id is equal for A/A and differs for B (Chrome's salt persists per profile, so this measures the fold's seed sensitivity, which content_shell cannot) | guard: the S3 renderer hash was seed-sensitive too |

S3-W2 asserts exactly three `audioinput` entries, the third 64 hex (M10).

**Phantom speaker on a host with no output (WSL, test-only mutant).** No real host here lacks a speaker. A mutant build empties the raw `audiooutput` list in `OnDevicesEnumeratedAndRanked`, `NotifyDeviceChange` and AOAH's raw enumerate. It lives in a scratch commit and is never exported. Under it:

| Row | Check | RED |
|---|---|---|
| S3-M1 | `setSinkId(<phantom speaker id>)` resolves | NotFoundError, without the I2 fix |
| S3-M2 | `new AudioContext({sinkId: <phantom speaker id>})` reaches `state === 'running'` with `sinkId` equal to it and no `error` event within 3 s | without the fold and the I2 fix |

Both rows run in a separate script, `scripts/verify_s3b_phantom_out.py`, whose EXPECTED counts exactly these two rows. The script refuses to count rows unless the build really is the mutant: its stock arm (no config) must list no `audiooutput` at all, or it exits 2. A devicechange cannot be triggered on WSL without real hardware changing, so the `NotifyDeviceChange` part of the fix is unmeasured and recorded as such.

`verify_media_ii`, `verify_phantom` and `verify_sp4_media` must stay GREEN. Their HEX64 and rotation checks are re-baselined, because ids change value, not shape. The Windows verify set and step 2's stability probe are re-run.

## Not in scope

- M2, the bare `Default` sentinel label. A safe rule would need Chrome's localized sentinel names in the renderer, since a bare label from another audio backend can carry a device name. It is Linux-only, because Windows always labels sentinels `<prefix> - <device>`. It moves to the Linux sentinel-shape work.
- The phantom mic's latency, which stays parked.
- getUserMedia with an exact phantom id, which stays NO_HARDWARE → NotReadableError: a phantom cannot capture.
- The Linux and macOS sentinel shapes.

## Costs and risks

- **Rebase surface.** The fold adds one more `content/` patch, in a hot utility file; `git apply --3way` fails loudly if the function moves.
- **Shared ids.** Anything outside `content/` that compares device ids it did not get from `GetHMACForRawMediaDeviceID` would disagree. None was found in `content/`. Chrome-side users go through the public `media_device_id.cc`, which calls the same function (inferred; only `content/` was grepped).
- **Opaque origins.** Ids for opaque origins now follow Chrome's committed-origin keying, not the renderer's `SecurityOrigin::ToString()`. That is a closer match to stock.
- **Baselines.** Existing captures with fork ids change value. Nothing persists them; the verify baselines are regenerated.

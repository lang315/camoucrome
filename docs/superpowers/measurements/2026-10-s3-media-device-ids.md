# S3: enumerateDevices() ids after a grant, on a host without the claimed devices

Spec: `specs/2026-10-10-s3-media-device-ids-design.md`. Plan: `plans/2026-10-10-s3-media-device-ids.md`.

## 1. Setup

- Box checkout `~/chromium/src` moved off `camoucrome/main` onto the new branch `camoucrome/s3`, cut at `e585e8b5ce` (owner OK 2026-10-10). The branch holds 39 commits above the pin `f89f3a4363`.
- `camoucrome/main` is not moved until landing (Task 6).
- No-op build check (label `s3-base`, `autoninja -C out/Default content_shell components_unittests`): `Build Succeeded: 0 steps`. `out/Default` is the CI build of `e585e8b5ce`, so it is the RED build.

## 2. What WSL has

Stock content_shell under `--use-fake-ui-for-media-stream` (no fake devices) lists:
- `audioinput`: 2 entries (one device entry, one entry with an empty label), no empty ids.
- `audiooutput`: 2 entries, same shape.
- `videoinput`: none.

So `REAL_KINDS = [audioinput, audiooutput]` and `PHANTOM_KINDS = [videoinput]`: WSLg exposes a mic and a speaker, no camera. This is the spec's "host with one real input kind".

## 3. RED

Run on the unchanged `e585e8b5ce` build, `out/Default` (0 steps), script commit `6b40b16`. Result `2/8 FAIL`, rc=1.

| Row | Verdict | Note |
|---|---|---|
| S3-1 | FAIL | grant lists only the two real kinds; no phantom camera id |
| S3-2 | FAIL | no phantom group ids |
| S3-3 | PASS | guard: 1 entry per kind, all ids/groups/labels `""` without a grant |
| S3-4 | FAIL | kinds equal across the grant: pre has all three kinds, post lacks `videoinput`. RED here because WSL has a real mic and no camera: the claimed camera vanishes after the grant (the S3 bug) |
| S3-5 | FAIL | `ids equal=True` is vacuous on main (no phantom devices exist), so the persistent-id question stays open for Task 3 |
| S3-6 | FAIL | 0 ids on origin A and on origin B |
| S3-7 | FAIL | no phantom camera capabilities |
| S3-8 | PASS | guard (rule 5): `{}` config shape equals stock shape |

Only S3-3 and S3-8 are guards.

## 4. GREEN per task

### Task 3: `s3-media-phantoms` (box commit 037493b318, commit 40 of 40)

Edits to `media_devices_manager.cc` only. Anchors each occurred once. The phantom mic's capability parameters use
`audio_manager_win.cc`'s fallback frames-per-buffer, `kFallbackBufferSize = 2048` (not 480); the format stays
`AUDIO_PCM_LOW_LATENCY` (Windows' own fallback says `AUDIO_PCM_LINEAR`; the page cannot see the format).

- Build 1: 4258 steps (a large blink and `components_unittests` recompile on this tree). `gn check` browser and mediastream:
  `Header dependency check OK` each; both checkdeps runs print `SUCCESS`. `MediaPhantoms*`/`DeviceIds*` unit tests: 10 + 8 passed.
- `verify_s3_media`: 6/8. S3-1, 2, 3, 4, 6, 8 PASS (S3-4 turned green). Two rows fail for reasons outside this commit:
  - S3-5 `same_ids`: stock content_shell also gives different deviceIds to the main frame and a same-origin iframe
    (audioinput `8f4051..` vs `ecc74c..`), so it has no persistent ids; the phantom camera behaves the same. Groups are disjoint.
  - S3-7: the phantom camera's `getCapabilities()` has no width/height with the seed configured, but has
    `width {1..1920}, height {1..1080}` with the seed removed from the config. The post-grant branch of
    `third_party/blink/renderer/modules/mediastream/media_devices.cc` (`transformed`) builds new `InputDeviceInfo`
    objects without calling `SetVideoInputCapabilities`, which also drops the real mic's capabilities (stock has
    sampleRate 44100..48000 and channelCount 1..2; with the seed it has none). That is renderer code outside this commit.
- Regressions on the same build: `verify_media_ii` 13/13, `verify_phantom` 6/6, `verify_sp4_media` 4/4 (all ALL_PASS;
  `sp4_media_baseline.json` copied from `~/camoucrome-verify`, it is build-host-local).
- Mutation 1 (translation loop reads `enumeration`, 5 steps): the browser crashes, since the reply holds phantoms
  that translation skipped (raw and hashed sizes differ). S3-1, 2, 4, 5, 6, 7 FAIL on a closed page; S3-3, 8 PASS (2/8).
- Mutation 2 (phantoms computed but not added, 2 steps): S3-1 FAIL (`phantom ids=[]`), S3-2, 4, 5, 6, 7 FAIL; S3-3, 8 PASS (2/8).
- Restored: file identical to the edits, rebuilt (2 steps), 6/8 again.

### Task 4: renderer (sp4-media, media-ii-track)

- Grant test: any non-empty id in any kind marks the reply post-grant (`camou_any_device_id`), so a speakers-only host
  keeps its real speaker id. Not measurable on WSL (needs a host with a speaker and no inputs); its row is S3-W1 (Task 5).
- Sentinel prefix: enumerate and track labels both go through `MaskedDeviceLabel`, so a `default` or `communications`
  entry keeps Chrome's `<prefix> - ` on both surfaces (media-ii M4). `verify_media_ii` M11 still PASS (the fake device's
  `default` label has no ` - `).
- Capabilities under a seed: the first loop now hands the transform a `Clone()`, and the transform moves the capabilities
  onto the synthetic `InputDeviceInfo` (capability `device_id` set to the synthetic id, which the setters check). Before,
  every seeded input lost its capabilities: the phantom camera's width/height and the real mic's sampleRate/channelCount.
  S3-7 now also checks the real input's capabilities.
- S3-5 rewritten: stock content_shell has no persistent deviceId salt, so a same-origin iframe gets other deviceIds than
  its main frame. The row compares, per kind, "deviceId equal across documents" fork versus stock, and requires every
  fork groupId to differ between documents. Persistent per-profile stability is measured on the Windows host (Task 5).
- Build 12 steps; verify `verify_s3_media` 8/8, `verify_media_ii` 13/13, `verify_phantom` 6/6, `verify_sp4_media` 4/4;
  unit tests MediaPhantoms 10, DeviceIds 8 PASSED; `gn check` and `checkdeps` clean.
- Mutation (transform's capability setters dropped, 3 steps): S3-7 FAIL (7/8). Restored, rebuilt, 8/8.

## 5. Windows hashes and build

## 6. Host rows

## 7. Step 2 row

## 8. Gaps

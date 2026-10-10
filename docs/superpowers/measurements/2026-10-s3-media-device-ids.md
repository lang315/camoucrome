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

Run on the unchanged `e585e8b5ce` build, `out/Default` (0 steps), script commit `6b40b16`. Result: 2 of 8 rows PASS (the two guards), 6 FAIL, rc=1.

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
  `Header dependency check OK` each; both checkdeps runs print `SUCCESS`. `MediaPhantomsTest`/`DeviceIdsTest` unit tests: 18 passed (5 MediaPhantomsTest, 13 DeviceIdsTest).
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
  keeps its real speaker id. This change is unmeasured. WSL has inputs, and on the host the phantom inputs carry ids after
  the grant, so the old input-only test also takes the post-grant path and S3-W1 passes either way (see section 8).
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
  unit tests 18 PASSED (5 MediaPhantomsTest, 13 DeviceIdsTest); `gn check` and `checkdeps` clean.
- Mutation (transform's capability setters dropped, 3 steps): S3-7 FAIL (7/8). Restored, rebuilt, 8/8.

## 5. Windows hashes and build

Windows tree `D:\camou-win\chromium\src` at box `camoucrome/main` (`e585e8b5ce`); source box `camoucrome/s3` (`4b5fdddcd8`, 40 commits); branch `s3/media-device-ids` at `d100ac9`.
W12 replaced 10 files. Every pre hash equalled the box's `main` hash (3 new files ABSENT), and every post hash equalled the box's `s3` hash (0 mismatches):

| File | pre | post |
|---|---|---|
| `components/camoucfg/BUILD.gn` | 85b54c68 | 47beb115 |
| `components/camoucfg/device_ids.cc` | a7de6fbe | 3137f4e4 |
| `components/camoucfg/device_ids.h` | d9092ba3 | f379044b |
| `components/camoucfg/device_ids_unittest.cc` | 94f05c65 | e8447994 |
| `components/camoucfg/media_phantoms.cc` | ABSENT | b2a2169e |
| `components/camoucfg/media_phantoms.h` | ABSENT | 32b9bc37 |
| `components/camoucfg/media_phantoms_unittest.cc` | ABSENT | 8c9a822c |
| `content/browser/renderer_host/media/media_devices_manager.cc` | 3d35eda0 | 7eff2690 |
| `third_party/blink/renderer/modules/mediastream/media_devices.cc` | 99ce8c63 | 4993479a |
| `third_party/blink/renderer/modules/mediastream/media_stream_track_impl.cc` | 8c50236f | a3195c20 |

Host tree disclosure: `D:\camou-win\tree` (the script and client tree) was not refreshed to this branch. Only `scripts/verify_s3_host.py` was copied in, so `tree.commit` still carries the S2c stamp `5a61ea044e24`. The verify set, `verify_sp3a` and the host canvas run below therefore ran S3 binaries under an S2c-stamped tree; the client and those scripts are unchanged between the two.

Build `s3-1` (`autoninja -C out\Release chrome`, lock `s3 win build`): `Build Succeeded: 56 steps`, rc=0, 63 s.

## 6. Host rows

`verify_s3_host.py`, headless, fork (generated Windows identity, seed 1) against stock Chrome 154.0.8037.93 on the host. Shape lines carry kinds, id lengths and label prefixes only.

RED (S2c build, `out\Release` before the copy): `0/4 FAIL`.
- control: `audiooutput` ids of length 7, 14 and 64 (prefixes `Default`, `Communications`, none), so the grant landed.
- fork: one entry per kind, all ids length 0, no label prefixes.
- S3-W1 FAIL (fork ids empty). S3-W2 FAIL. S3-W3 FAIL (`getCapabilities()` has no keys). S3-W4 FAIL: `groups_differ=False` (fork groupIds all empty). `ids_equal=True` on the fork is vacuous there (every id is `""`); the row's failing clause is the group one.

GREEN (S3 build): `4/4 ALL_PASS`, rc=0.
- fork shape: `audioinput` 7 (`Default`), 14 (`Communications`), 64; `videoinput` 64; `audiooutput` 7 (`Default`), 14 (`Communications`), 64. The `Default` and `Communications` prefixes are Chrome's localized sentinel words, not device names.
- S3-W3 (phantom mic, no stock comparison: the host has no mic): keys `autoGainControl, channelCount, deviceId, echoCancellation, groupId, latency, noiseSuppression, sampleRate, sampleSize, voiceIsolation`; `sampleRate` 48000..48000, `channelCount` 1..2, `latency` present, 0..0.042666.
- S3-W4 (one profile, main document then a second same-origin document): stock `audiooutput` ids equal, 3 of 3 groupIds differ. Fork: all 7 ids equal, 7 of 7 groupIds differ. Stock showed the expected relation, so the row stands as written.

Fix round 1 (script `verify_s3_host.py` asserts ranges and non-empty ids; no rebuild, same `out\Release`):
- Shape lines now print a label prefix only for the `default` and `communications` entries; any other entry shows only whether its label contains ` - ` (`False` on this host).
- S3-W3 requires sampleRate min > 0 and min <= max, channelCount max >= 1, and a latency range with 0 <= min <= max (no hardcoded values).
- S3-W4 requires every fork deviceId and every stock audiooutput deviceId to be a sentinel or 64 hex before the equality clause.
- GREEN: `4/4 ALL_PASS`, rc=0.
- The S2c binary no longer exists (`out\Release` was rebuilt), so the new clauses were proved by running the script with stock Chrome as the fork arm and by three one-clause mutants:
  - stock as fork: `S3-W1: PASS`, `S3-W2: FAIL`, `S3-W3: FAIL`, `S3-W4: PASS`, `2/4 FAIL` (stock has the speaker but no phantom mic, no capabilities).
  - mutant 1 (sampleRate min must exceed 99999): `S3-W3: FAIL`, `3/4 FAIL`.
  - mutant 2 (sentinels no longer count as valid ids): `S3-W4: FAIL`, `ids_equal=False`, `3/4 FAIL`.
  - mutant 3 (latency min must exceed 5): `S3-W3: FAIL`, `3/4 FAIL`.
  - The original RED on the S2c build (`0/4 FAIL`) was with the first script version.

Latency finding: the phantom mic's `latency` max, 0.042666 s, is 2048 frames at 48 kHz, the `kFallbackBufferSize` of Task 3. It is a fixed value, not a measured one. Stock has no mic on this host, so whether a real Windows mic reports the same range is unmeasured.

Windows verify set (`windows_verify_set.py green`): 21/21 entries OK (`verify_host_oracle` keeps its known O2 FAIL). `verify_sp3a` on `chrome` (`CAMOU_SHELL=chrome`): 57 PASS and 6 FAIL (C2, C3, C4, C5, C10, C11: no stock baseline on the host, UNMEASURED), the S2c counts unchanged. Host canvas run headless: 9/9 PASS.

## 7. Step 2 row

`measure_step2.py run --only stability --modes headless` on the S3 build: 0 errors, 236 compared rows, 0 changed on both arms; `0 differing rows`. The run does not keep the id lists, so a wrapper (not committed) called the same probe and printed shapes only:

| arm | launch 1 and launch 2 | ids equal across launches | non-empty groupIds |
|---|---|---|---|
| control | 3 `audiooutput`, id lengths 7, 14, 64 | True | 3 |
| fork | 3 `audioinput`, 1 `videoinput`, 3 `audiooutput`; lengths 7, 14, 64, 64, 7, 14, 64 | True | 7 |

`mediaDevices.ids` is non-empty on both arms; step 2's finding S3 (empty ids after the grant) is closed on the fork.

## 8. Gaps

- Linux and macOS sentinel shapes are not built.
- `getUserMedia` on a phantom device: the exact-id path (`deviceId: {exact: <listed phantom id>}`) is unmeasured. It most likely ends in NO_HARDWARE, which `phantom-webcam` remaps to `NotReadableError`. `OverconstrainedError` is the possible worse alternative.
- A host with more real devices than the identity claims keeps the extra ones. Sharper case: a real kind with a configured count of 0 is hidden before the grant and shown after it, so the set of kinds changes across the grant on real hardware. This predates S3 and is the case S3-4 targets.
- The sentinel prefix (`Default - `, `Communications - `) follows the host UI locale, not the identity's language, so a German identity on an English host still reads `Default - `. This predates S3.
- On a host with no audio output, `setSinkId()` and `AudioContext` `sinkId` reject the phantom speaker's listed id with `NotFoundError`. Phantoms never enter the device snapshot that output authorization reads, and stock never rejects an id it just listed under a grant. This is a new tell that S3 introduces (before S3 such a host listed only blank ids). It is unmeasured; the claim rests on the spec's statement that `setSinkId` reads the real snapshot. Follow-up: accept phantom ids in output authorization, or keep the phantom speaker out of the reply until that exists; measure it with a host row on a host with no output device.
- The phantom mic's 48 kHz stereo is Windows' fallback, not a captured mic.
- The S3-4 RED needs a host with exactly one real input kind. It was run on WSL (real mic, no camera) but not on a second host shape.
- Phantom mic latency is unmeasured against a real mic. The range is 0..0.0427 s, which is 2048 frames at 48 kHz (Windows' fallback). A typical WASAPI mic reports about 0.01 s. The host has no mic, so there is no stock value to compare. Parked for the owner; the fix is a one-constant change.
- S3-5 on WSL is a guard, not a RED row: content_shell has no persistent deviceId salt. Persistent per-profile id stability is measured only by S3-W4 on the host.
- The grant test (any non-empty id marks the reply post-grant) is unmeasured. WSL has inputs. On the host the phantom inputs carry ids after the grant, so the old input-only test also takes the post-grant path, and S3-W1 passes with or without the change. Follow-up: host row S3-W5 under config `micros: 0, webcams: 0, speakers: 1` with the mic granted, requiring the fork's non-sentinel `audiooutput` id to be 64 hex, with its RED from a mutant that restores the old input-only test.
- `verify_sp4_media` needs `sp4_media_baseline.json`, which is not in the repo (build-host-local). This predates S3.

### Follow-ups (from the final review)

- M1: phantoms are gated on `mediaDevices:enabled` alone while the renderer transform also needs a non-zero seed, so a hand-written config with no seed shows a half-masked mix; gate the phantoms on the seed too, or document that the seed is required.
- M2: `MaskedDeviceLabel` turns a bare `Default` label into the configured name, giving two entries with the same label where stock shows `Default`; return the Chrome label unchanged for a bare sentinel and update the test.
- M3: the phantom mic gets its own groupId, while a real laptop mic and speaker on one codec may share one (unverified); capture stock on a laptop and, if shared, give the phantom mic the speaker's group.
- M4: the phantom camera label and missing facing mode may differ from a real integrated camera on Windows (unverified); capture the stock shape and carry a captured label from `gen.py`.
- M5: the default device labels are written out in three patches; move them into one camoucfg header so they cannot drift apart.
- M9: leftover style nits (include order, a missing `<algorithm>` include, lines over 80 columns, a double blank line); fix them in one box commit plus export.
- M10: S3-W2 accepts any three or more inputs instead of exactly three with a 64-hex third, and S3-7 hard-codes 1920x1080 from Chrome's fallback list; tighten both.
- M11: S3-8 compares only which fields are empty; compare label values and the `getCapabilities()` keys against stock.

S3b (`2026-10-s3b-device-id-seed.md`) closes I2, S3-W5, M1, M5, M9, M10 (the S3-W2 half; S3-7's 1920x1080 stays open) and M11. M2 moved to the Linux sentinel work.

## 9. Final counts

| Check | Result |
|---|---|
| WSL `verify_s3_media` | 8/8; RED on `main` (`e585e8b5ce`) 2/8 pass (S3-3, S3-8 guards); S3-5 was rewritten later into a guard and its RED was not seen |
| Host `verify_s3_host` | 4/4; RED on S2c 0/4, stock-as-fork 2/4, three per-clause mutants 3/4 each |
| WSL regressions | `verify_media_ii` 13/13, `verify_phantom` 6/6, `verify_sp4_media` 4/4 |
| Windows verify set | 21/21 (`verify_host_oracle` keeps its known O2 FAIL) |
| `verify_sp3a` on `chrome` | 57 PASS, 6 baseline-less (C2, C3, C4, C5, C10, C11) |
| Host canvas | 9/9 |
| Step 2 stability | 236 compared rows, 0 changed |

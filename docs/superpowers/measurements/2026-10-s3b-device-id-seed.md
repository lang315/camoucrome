# S3b: device ids that round-trip — measurements

Spec: `specs/2026-10-10-s3b-device-id-seed-design.md`. Plan: `plans/2026-10-10-s3b-device-id-seed.md`.
Pin 154.0.8037.93. Box branch `camoucrome/s3b` cut at `camoucrome/main` = `4b5fdddcd8`.

## 1. Setup

- Box `~/chromium/src` switched to `camoucrome/s3b` at `4b5fdddcd8`: 40 commits above the pin, tree clean, lock free.
- Baseline build `out/Default` (`content_shell components_unittests`) on that commit: `Build Succeeded: 263 steps`.
  Not a no-op: W3 `cp -r` of `additions/camoucfg` touched the mtimes of the camoucfg files (content identical, 0 drift lines).
  Far from thousands, so the mtimes are sound.

## 2. RED on the main build

`verify_s3_media.py` on the `camoucrome/main` build (`4b5fdddcd8`), first run, with a real host speaker and microphone (REAL_KINDS = audioinput, audiooutput; phantom kind = videoinput): `8/12 FAIL`.

| Row | Verdict | Note |
|---|---|---|
| S3-1..S3-7 | PASS | |
| S3-8 | PASS (guard) | by label and capability keys: True |
| S3-9 | FAIL | `sink: fork=NotFoundError stock=ok` |
| S3-10 | FAIL | `gum: fork=NotReadableError stock=ok` (no capability matches the listed id; phantom-webcam remaps NO_HARDWARE) |
| S3-11 | FAIL | `acSink: fork=NotFoundError stock=ok` |
| S3-12 | FAIL | enabled without a seed differs from stock by label and capability keys |

Mutant (W13, first version: only `current_snapshot_` emptied; DEFECTIVE, see section 4; `verify_s3b_phantom_out.py`): the mutant is live (stock lists 0 audiooutput, exit 1 not 2), `0/2 FAIL`:
`S3-M1 sink=NotFoundError`; `S3-M2 ac=state=suspended sinkMatch=false error=true`.
Mutant off: rebuilt, `grep -c S3B-MUTANT` = 0, tree clean.

Caveat on the lines above: the first mutant run had no stock control, and its liveness check (stock lists no audiooutput) was a host property: once WSLg lost its audio, `outs == 0` also held on the non-mutant build, so "the mutant is live" was vacuous while REAL_KINDS had no audiooutput. Fix round 2 replaces it:
- every session in `verify_s3b_phantom_out.py` passes `--use-fake-device-for-media-stream`, so a normal build lists a fake audiooutput and only the mutant lists none;
- each M row needs its stock control (`setSinkId("")`, a plain `AudioContext` reaching `running`) ok on the same build.

Fix round 2 runs (script `328fbad`):
- non-mutant main build: exit 2, `stock lists audiooutput: 3`, so liveness detects a normal build;
- W13 mutant on (2 steps): stock `outs=0`, controls `sink=ok ac=ok`, `S3-M1 FAIL sink=NotFoundError`, `S3-M2 FAIL ac=state=suspended sinkMatch=false error=true`, `0/2 FAIL`;
- mutant off (2 steps): `grep -c S3B-MUTANT` = 0, tree clean (0 status lines).

Build steps: baseline 263; mutant on 10; mutant off 2.

Host note: two later runs of `verify_s3_media.py`, after the mutant job, found REAL_KINDS = [] (WSLg listed no real audio device), so S3-9..S3-11 read "stock control failed: not measurable". Ruling: the SINK sessions (S3-9..S3-11) now pass `--use-fake-device-for-media-stream`; every other session stays without it.

Re-run on the main build with that change (`66427f0`), `8/12 FAIL`, REAL_KINDS = [] (phantom kinds: all three):

| Row | Verdict | Note |
|---|---|---|
| S3-1..S3-6 | PASS | |
| S3-7 | PASS | 2 input entries, capability ids equal own ids, range checks [True, True] (the real-input half has no real kind to check) |
| S3-8 | PASS (guard) | by label and capability keys: True |
| S3-9 | FAIL | `sink: fork=NotFoundError stock=ok` |
| S3-10 | FAIL | `gum: fork=OverconstrainedError stock=ok` (with a fake mic the listed id matches no device) |
| S3-11 | FAIL | `acSink: fork=NotFoundError stock=ok` |
| S3-12 | FAIL | enabled without a seed differs from stock |

WSLg audio back without fake devices: no (stock lists neither audioinput nor audiooutput).

**Note (Task 3 fix round 1):** the mutant RED above ran on a defective mutant (devicechange still received the real list). The valid RED is the product mutation in section 4 (`audio_output_authorization_handler.cc` iterating the raw list): 0/2 on the corrected mutant.

## 3. Browser: the seed fold and phantom output (Task 2)

Box `camoucrome/s3b` is 41 commits, `s3b-device-id-seed` last (106962c649).

- Fold in `GetHMACForRawMediaDeviceID` (new commit); `CamouWithPhantoms` exported
  and gated by `ActiveMediaDevicesSeed`; phantom-aware output authorization;
  `NotifyDeviceChange` uses the phantoms too (fixup in `s3-media-phantoms`).
- Build: 302 steps, 7m50s. `gn check` OK, checkdeps clean, 18 unit tests pass
  (`MediaPhantoms*:DeviceIds*`).
- Export: mtime reset 146 files; no-op rebuild 45 steps (1m41s).
  sha256: s3-media-phantoms.patch b1a93de6, s3b-device-id-seed.patch 56742fc3,
  series d2f71dd7.
- Verify: `verify_s3_media` 8/12 (S3-9..12 FAIL, as planned: S3-9..11 need the
  renderer change and S3-12 needs the renderer to use the same activation rule;
  the renderer in `sp4-media.patch` still makes blank entries on `enabled` alone).
  `verify_media_ii` 13/13, `verify_phantom` 6/6, `verify_sp4_media` 4/4.
- The Task 2 mutation check moves to Task 3, where it targets the browser gate
  after the renderer change.
- Environment finding: WSLg lost its audio devices since the 2026-09-01
  baseline. `verify_phantom` P6 and `verify_sp4_media` M4 had assumed a real mic
  and the stale `sp4_media_baseline.json`. Both now compare with a live stock run
  (P6: stock NotFoundError -> fork NotReadableError, since a claimed mic with no
  mic is a phantom, so gUM ends NO_HARDWARE and phantom-webcam remaps it).

## 4. Renderer: no id rewrite (Task 3)

The renderer keeps Chrome's ids (the browser folds the seed); `SyntheticDeviceId` is gone; sp4-media, media-ii-track and phantom-webcam take the one activation rule (`ActiveMediaDevicesSeed`).

- Build `s3b t3`: 264 steps. `gn check` (browser, mediastream): OK. `checkdeps`: SUCCESS. `MediaPhantoms*:DeviceIds*`: 7 tests PASSED.
- GREEN: `verify_s3_media` 12/12 (S3-12 PASS), `verify_media_ii` 13/13, `verify_phantom` 6/6, `verify_sp4_media` 4/4.
- Mutation, ids: `device_info.device_id + "x"` gives 8/12 (S3-1, S3-9, S3-10, S3-11 FAIL); restored 12/12.
- Mutation, browser gate back to enabled-only: 11/12 (only S3-12 FAIL); restored 12/12.
- Export: 41 commits; the 3 patches `sp4-media`, `media-ii-track` and `phantom-webcam` changed; mtime reset 148 files; the no-op rebuild built 59 steps.
- Fix round (`69dbc46`, box `ff5ecaa880`):
  - the review fixes reworded the `mediadevices-seed-when-enabled` why in `settings/invariants.json` (the only exported change);
  - build `s3b t3 fix1`: 264 steps; regressions 12/12, 13/13, 6/6, 4/4, units 7/7;
  - export: mtime reset 152 files, no-op rebuild 57 steps, sync check PASS.
- S3-M2: **resolved.** The first W13 mutant was defective (it emptied only `current_snapshot_`; devicechange still received the real list), and a second one (clearing in `AudioDevicesEnumerated`) was never live because `--use-fake-device-for-media-stream` takes the fake-device branch in `EnumerateAudioDevices`. The corrected mutant empties the list in `DevicesEnumerated` before `UpdateSnapshot`.
  - Corrected mutant: stock `outs=0`, controls `sink=ok ac=ok`, `S3-M1 PASS`, `S3-M2 PASS`, `2/2 ALL_PASS`.
  - AOAH mutation (loop over `enumeration` instead of `camou_enumeration`): `S3-M1 FAIL sink=NotFoundError`, `S3-M2 FAIL`, `0/2 FAIL`.
  - Restored: `grep -c S3B-MUTANT` = 0.

## 5. Windows build and hashes (Task 4)

Windows tree `D:\camou-win\chromium\src` at box `camoucrome/main` (`4b5fdddcd8`, S3); source box `camoucrome/s3b` (`ff5ecaa880`, 41 commits); branch `s3b/device-id-seed` at `d4e1dea`.
W12 replaced 15 files. Every pre hash equalled the box's `main` hash (0 ABSENT, 0 mismatches), and every post hash equalled the box's `s3b` hash (0 mismatches):

| File | pre | post |
|---|---|---|
| `components/camoucfg/device_ids.cc` | 3137f4e4 | 242afec9 |
| `components/camoucfg/device_ids.h` | f379044b | 65494b59 |
| `components/camoucfg/device_ids_unittest.cc` | e8447994 | 4aa87552 |
| `components/camoucfg/invariants.json` | e72100d7 | ae59afa0 |
| `components/camoucfg/keys.h` | 1af0f371 | 06419521 |
| `components/camoucfg/media_phantoms.cc` | b2a2169e | f812a667 |
| `components/camoucfg/media_phantoms.h` | 32b9bc37 | 747528d2 |
| `components/camoucfg/media_phantoms_unittest.cc` | 8c9a822c | cd99718d |
| `content/browser/media/media_devices_util.cc` | e42d3abd | 997dde6f |
| `content/browser/renderer_host/media/audio_output_authorization_handler.cc` | 3173a242 | 39f9735f |
| `content/browser/renderer_host/media/media_devices_manager.cc` | 7eff2690 | 2afa4399 |
| `content/browser/renderer_host/media/media_devices_manager.h` | 3e98c15b | b6d4c8c4 |
| `third_party/blink/renderer/modules/mediastream/media_devices.cc` | 4993479a | f3634b11 |
| `third_party/blink/renderer/modules/mediastream/media_stream_track_impl.cc` | a3195c20 | 6cc556a9 |
| `third_party/blink/renderer/modules/mediastream/user_media_request.cc` | 83b33f73 | 55b22460 |

Host tree disclosure: `D:\camou-win\tree` was not refreshed to this branch. Only `scripts/verify_s3_host.py` was copied in, so `tree.commit` still carries the S2c stamp `5a61ea044e24`.

Builds (`autoninja -C out\Release chrome`, lock `s3b host red`):
- `s3b-mut` (Windows-only mutant of `media_devices.cc`, below): `Build Succeeded: 131 steps`, rc=0, 142 s.
- `s3b-1` (real file restored): `Build Succeeded: 0 steps`. The copied file kept its older source mtime, so the build treated the mutant objects as current; not a result.
- `s3b-1b` (file touched): `Build Succeeded: 49 steps`, rc=0, 45 s. This is the GREEN binary.

## 6. Host rows (Task 4)

`verify_s3_host.py` (7 rows), headless, fork (generated Windows identity, seed 1) against stock Chrome 154.0.8037.93. Shape lines carry kinds, id lengths and label prefixes only.

RED (S3 build, before the copy): `6/7 FAIL`.
- `W5 outs=1 hex=True`, `W6 sink control=ok fork=NotFoundError`, `W7 same-seed equal=True other-seed disjoint=True n=1`.
- S3-W6 FAIL; S3-W1..W5 and S3-W7 PASS. S3-W5 and S3-W7 are guards on S3 (any-id grant test, seed-sensitive renderer hash).
- The control arm's sink is `ok`, so the grant landed.

S3-W5 mutant (Windows-only, never committed): the real `media_devices.cc` with the any-id test made input-only (`// S3B-WINMUT`, sha256 `126883b0`), on top of the 15 copied files. Build `s3b-mut`, 131 steps.
- `W5 outs=0 hex=False`, `W6 sink control=ok fork=ok`, `W7 ... n=1`; `S3-W5: FAIL`, `6/7 FAIL`.
- The input-only test takes the pre-grant branch, whose blank speaker entry `OUTS` filters out.
- The real file was copied back, its post hash `f3634b11` equals `s3b`, and `grep S3B-WINMUT` finds 0.

S3-W7 fold mutant (Windows-only, never committed; closes final-review I2): `content/browser/media/media_devices_util.cc` from `camoucrome/s3b` with the `hmac.Update(base::U32ToLittleEndian(seed));` line removed (sha256 `f0f9870a`). Copied over the Windows file and touched. Build `s3b-foldmut`: 4 steps, rc=0. Script at `b126642`:
```
W5 outs=1 hex=True
W6 sink control=ok fork=ok
W7 same-seed equal=True other-seed disjoint=False n=1
S3-W7: FAIL
6/7 FAIL
```
Real file copied back and touched (post hash `997dde6f` = `camoucrome/s3b`), build `s3b-2`: 4 steps, rc=0:
```
W7 same-seed equal=True other-seed disjoint=True n=1
7/7 ALL_PASS
```
S3-W7 is a RED-backed row for the fold. The script of this run is the tidied one (`6bbe112`, in `b126642`), so the tidy is re-run in the 7/7 above; the earlier S3-W5 mutant and `s3b-1b` runs used `d4e1dea`.

GREEN (`s3b-1b`): `7/7 ALL_PASS`, EXIT 0.
- `W5 outs=1 hex=True`; `W6 sink control=ok fork=ok`; `W7 same-seed equal=True other-seed disjoint=True n=1`.
- fork shape unchanged: `audioinput` 7, 14, 64; `videoinput` 64; `audiooutput` 7, 14, 64.

Windows verify set (`windows_verify_set.py green`): `21/21 entries OK (green)`, EXIT 0 (`verify_host_oracle` keeps its known O2 FAIL).
`verify_sp3a` with `CAMOU_SHELL=chrome`: 57 PASS and 6 FAIL (C2, C3, C4, C5, C10, C11, no stock baseline on the host, UNMEASURED), counts unchanged from S3.
Host canvas (`measure_canvas_noise.py run --mode headless --seeds 8`): 9/9 PASS, EXIT 0.

## 7. Step 2 stability (Task 4)

`measure_step2.py run --only stability --modes headless` on the `s3b-1b` build: `0 errors`; `stability / headless: 0 differing rows`.

## 8. Gaps

- Phantom mic latency is still parked: the range is not measured against a real mic.
- `getUserMedia` with an exact phantom id still ends `NotReadableError`.
- The `NotifyDeviceChange` half of I2 is unmeasured: WSL raises no `devicechange`.
- M2 (a bare `Default` label turned into the configured name) moved to the Linux sentinel work.
- S3-W7 has a RED (the fold mutant, section 6), but its n is 1 on this host (one non-sentinel output id). No WSL row discriminates the fold: content_shell's salt rotates per launch, so M7/M8 stay confounded, and the ids and gate mutations target other code. S3-W7 on Chrome is the fold's only check.
- WSLg lost its audio devices during the slice. Since about 14:19 ICT on 2026-10-10 WSL lists no mic or speaker. So S3-9..11 run on fake devices, `REAL_KINDS=[]`, the real-input half of S3-7 has nothing to check, and `verify_phantom` P6 and `verify_sp4_media` M4 now compare against a live stock run.
- The first W13 mutant was defective: it emptied only the snapshot's audiooutput list, so change detection still saw the real list. Task 1's mutant RED is void. The valid RED is the AOAH raw-list mutation (0/2); the corrected mutant gives 2/2.
- W12 copy-back keeps the old mtime (`Copy-Item` preserved it), so the first GREEN build did 0 steps. Touch the file after any copy-back.

## 9. Final counts

- WSL `verify_s3_media`: 12/12; RED 8/12 on main.
- `verify_s3b_phantom_out` (corrected mutant): 2/2; RED 0/2 via the AOAH raw-list mutation.
- Mutation checks: 8/12 for the ids mutation, 11/12 for the browser gate mutation.
- Host `verify_s3_host`: 7/7; RED 6/7 on S3, plus the S3-W5 mutant (W5 FAIL) and the fold mutant (W7 FAIL, 6/7); 7/7 again on the restored build `s3b-2`.
- Regressions: `verify_media_ii` 13/13, `verify_phantom` 6/6, `verify_sp4_media` 4/4.
- Windows: verify set 21/21, `verify_sp3a` 57 PASS plus 6 without a baseline, canvas 9/9, step 2 stability 0 differing rows.
- Box: 41 commits.

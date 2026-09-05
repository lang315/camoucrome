# media-ii getSettings/getCapabilities coherence — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** Make a granted `MediaStreamTrack`'s `getSettings()/getCapabilities()/label`
coherent with the sp4-media-spoofed `enumerateDevices()` — post-grant, transform
real device ids/labels to seeded, origin-salted synthetic values via one helper
called from both the enumerate override and the track getters. Closes an
incoherence the spoof introduces (deviceId ∉ enumerate) + the real-hardware-label
leak. See `docs/superpowers/measurements/2026-09-05-media-ii-getsettings-surfaces.md`.

**Architecture:** grant-aware (the existing `result_contains_nonempty_input_device_ids`
flag is the pre/post-grant discriminator). Pre-grant: sp4 empty spoof unchanged.
Post-grant: `SyntheticDeviceId(seed, kind, real_id, origin)` transform at the
enumerate site AND the three track getters → coherent by construction.

**Harness:** `source /private/tmp/claude-501/-Users-lang-GolandProjects-github-com-lang315-camoufox/a03cdf7f-ea24-4267-99be-5f18eeb765f3/scratchpad/buildpc.sh`
(`pushcfg`/`pushfile`/`pullfile`/`pushto`/`unittests`/`contentshell`/`verify`).
Checkout `/home/lang/chromium/src` HEAD `a727b57805`. Confirm NON-ZERO build steps.
Long builds via `run_in_background`. This slice REVISES the applied sp4-media patch.

## Global Constraints

- All spoofing at C++/Blink, NEVER injected JS. (project invariant)
- **Grant-aware:** pre-grant (`!result_contains_nonempty_input_device_ids`) →
  sp4 empty spoof unchanged; post-grant → synthetic transform. The flag is
  computed at `media_devices.cc:1461-1474`, BEFORE the sp4 override (~1496) — read
  it there.
- **Origin salt preservation (critical):** the synthetic id folds the origin, so
  two origins with the same seed give DIFFERENT ids (real Chromium salts per-origin;
  a stable id would be a cross-origin linkable tell for our users). M8 gates this.
- **One helper, both sites:** the enumerate transform and the track getters call
  the identical `SyntheticDeviceId` on the identical real id → coherence by
  construction. Never fabricate ids independently at the two sites.
- **Preserve `deviceId=="default"`** unchanged (real Chrome literal, M10).
- **Do NOT touch `MediaStreamSource`** (shared with non-spoof paths); hook the
  Blink getters only.
- Keys triple-consistency (keys.h constant + kAllKeys array + size + keys_unittest
  `declared`). Count **78 → 82** (`mediaDevices:seed` + 3 label keys).
- Secure context: getUserMedia needs `127.0.0.1` echo_server; extra_flags REPLACE
  base flags → use `["--ozone-platform=headless","--use-fake-device-for-media-stream","--use-fake-ui-for-media-stream"]`.
- Blink files live only in the checkout (`pullfile`/`pushto`); extract in Task 3.
  `media_devices.cc` is already modified by sp4-media (this slice REVISES that
  patch); `media_stream_track_impl.cc` is a NEW patch.

---

### Task 1: `SyntheticDeviceId` helper + keys (82)

**Files:**
- Create: `additions/camoucfg/device_ids.h`, `device_ids.cc`, `device_ids_unittest.cc`
- Modify: `additions/camoucfg/keys.h` (4 keys, kAllKeys 78→82), `keys_unittest.cc`
- Modify: `additions/camoucfg/BUILD.gn` (add device_ids.cc + unittest to the target)

**Interfaces:** Produces `camoucfg::SyntheticDeviceId(uint64_t seed, std::string_view kind, std::string_view real_id, std::string_view origin) -> std::string`. Task 2 consumes it.

- [ ] **Step 1: device_ids.h/.cc** — pure helper:
```cpp
// Deterministic, origin-salted synthetic device id. 64 lowercase hex, matching a
// real salted device id's shape (a page cannot distinguish it from HMAC-SHA256
// hex). Pure: same (seed,kind,real_id,origin) -> same output.
//   - seed == 0 -> real_id unchanged (rule 5 no-op).
//   - real_id empty -> "" (pre-grant path never calls this).
//   - real_id == "default" -> "default" (real Chrome sentinel, preserved).
// Folds ORIGIN so two origins with the same seed differ (per-origin salt).
std::string SyntheticDeviceId(uint64_t seed, std::string_view kind,
                              std::string_view real_id, std::string_view origin);
```
Impl: if `seed==0 || real_id.empty()` → return `std::string(real_id)`. If
`real_id=="default"` → return `"default"`. Else build 64 hex: 4 rounds of a mixed
hash (reuse `DeriveDelta`'s hashing or an FNV-1a-64 over
`seed ‖ kind ‖ real_id ‖ origin ‖ round_counter`), each round → 16 hex chars,
concatenated. Lowercase hex.

- [ ] **Step 2: keys.h/keys_unittest.cc** — add (after the existing `mediaDevices:`
  keys): `kMediaDevicesSeed = "mediaDevices:seed"`, `kMediaDevicesCameraLabel =
  "mediaDevices:cameraLabel"`, `kMediaDevicesMicrophoneLabel =
  "mediaDevices:microphoneLabel"`, `kMediaDevicesSpeakerLabel =
  "mediaDevices:speakerLabel"`. Grow `std::array<…, 78>` → `82`; append to
  `kAllKeys` and to the `declared` set in keys_unittest.cc. (Colon-namespaced →
  `EveryKeyIsNamespaced` satisfied by the `:`.)

- [ ] **Step 3: BUILD.gn** — add `device_ids.cc`/`device_ids.h` to the camoucfg
  source set and `device_ids_unittest.cc` to the unittest source set (mirror how
  `canvas_noise` is listed).

- [ ] **Step 4: device_ids_unittest.cc** — assert: seed-0 → real_id unchanged;
  empty → empty; `"default"` → `"default"`; non-default → 64 lowercase hex chars,
  deterministic (same args → same); different origin → different; different seed →
  different; different real_id → different; different kind → different.

- [ ] **Step 5: push + build + run**
```bash
pushcfg device_ids.h && pushcfg device_ids.cc && pushcfg device_ids_unittest.cc && pushcfg keys.h && pushcfg keys_unittest.cc && pushcfg BUILD.gn
unittests 'DeviceIdsTest.*:CamoucfgKeysTest.*'
```
Expected NON-ZERO build, all PASS incl. `EveryDeclaredConstantIsInAllKeys` (82).

- [ ] **Step 6: Commit** `additions/camoucfg/device_ids.* keys.h keys_unittest.cc BUILD.gn`
  msg `feat(media-ii): SyntheticDeviceId helper + mediaDevices seed/label keys`.

---

### Task 2: Blink — grant-aware enumerate transform + track getters (+ verify M1–M11)

**Files (checkout):** `media_devices.cc`, `media_stream_track_impl.cc`;
**(Mac):** `scripts/verify_media_ii.py`.

**Interfaces:** Consumes `camoucfg::SyntheticDeviceId`.

- [ ] **Step 1: verify `scripts/verify_media_ii.py`** — echo_server (secure ctx) +
  the fake-device+fake-ui flags. Implement M1–M11 (measurement §8). Grant is the
  axis: M1 pre-grant = no-gUM enumerate under sp4 config → empties; M2/M3/M4 =
  post-grant (gUM then re-enumerate + read track). M6/M8 = two `session()` calls
  (confirm echo_server binds a FIXED port so "same origin" holds; if random, make
  the port fixed or M6/M8 are vacuous). M9 = config `{}`, stock exact pre+post.
  Measure stock live, compare.

- [ ] **Step 2: RED-first** — push + run BEFORE edits. RED: M3 FAIL (track deviceId
  ∉ empty enumerate), M2/M4/M11 FAIL, M1/M9 PASS. Record.

- [ ] **Step 3: media_devices.cc** — inside the existing sp4 `if (GetBool(kMediaDevicesEnabled))`
  block, branch:
  - `if (!result_contains_nonempty_input_device_ids)` → the current empty-count
    spoof (unchanged).
  - `else` (post-grant) → do NOT replace with empties; instead **transform the real
    `media_devices` in place**: for each `MediaDeviceInfo`, replace deviceId/groupId
    with `SyntheticDeviceId(seed, kind, real_id, origin)` (kind from the device
    type; `origin = GetExecutionContext()->GetSecurityOrigin()->ToString()`), label
    with the configured generic per kind. `seed = GetUint32(scope, kMediaDevicesSeed).value_or(0)`.
    (Since `MediaDeviceInfo` fields are set at construction, rebuild the vector with
    `MakeGarbageCollected<InputDeviceInfo/MediaDeviceInfo>(synthId, synthLabel,
    synthGroup, type)` — mirror the existing empty-spoof construction.)
  - Add camoucfg includes if not already present (media_devices.cc already deps
    camoucfg via sp4-media).

- [ ] **Step 4: media_stream_track_impl.cc** — transform in the three getters
  (guard: only when `kMediaDevicesEnabled` and `seed != 0`; else real value):
  - `getSettings()` (@~634): wrap `platform_settings.device_id` /
    `platform_settings.group_id` through `SyntheticDeviceId` before `setDeviceId`/
    `setGroupId`.
  - `getCapabilities()` (@~487): same for `platform_capabilities.device_id/group_id`.
  - `label()` (@339): return the configured generic label for the track's kind
    (instead of `component_->GetSourceName()`).
  - kind from `component_->Source()->GetType()` (audio/video); origin from
    `GetExecutionContext()->GetSecurityOrigin()->ToString()`. Add the 3 camoucfg
    includes + `components/camoucfg/device_ids.h`. **Confirm** `media_stream_track_impl.cc`'s
    blink target allows the camoucfg DEPS (it is `modules/mediastream`; if not
    already allowed, the include-rule addition goes INTO the Task 3 patch — check
    `gn check`).

- [ ] **Step 5: Build + verify GREEN** — `contentshell` (NON-ZERO),
  `verify verify_media_ii.py` → M1–M11 all PASS.

- [ ] **Step 6: Save the two checkout diffs for review** (not committed here) —
  `git diff HEAD -- .../media_devices.cc` and `.../media_stream_track_impl.cc` to
  `.superpowers/sdd/task-2-media_devices.diff` and `…track.diff`. Commit ONLY
  `scripts/verify_media_ii.py`. msg `test(media-ii): verify M1-M11 (grant-aware id/label coherence)`.

---

### Task 3: Patches (revise sp4-media + new track patch), apply.sh, regression

**Files:** Modify `patches/sp4-media.patch` (re-extract, now with the grant-aware
branch); Create `patches/media-ii-track.patch`; Modify `scripts/apply.sh`.

- [ ] **Step 1: gn check** `//third_party/blink/renderer/modules/mediastream:*`
  (or the target compiling the two files) → confirm "Header dependency check OK"
  (the camoucfg includes). If a DEPS line is needed, it goes into the track patch.
- [ ] **Step 2: Re-extract** `patches/sp4-media.patch` = `git diff HEAD -- media_devices.cc`
  (FULL diff — confirm the ORIGINAL sp4 hunks AND the new branch both present, camoucfg
  includes as `+`, NOT delta-only). Create `patches/media-ii-track.patch` =
  `git diff HEAD -- media_stream_track_impl.cc`.
- [ ] **Step 3: Round-trip** — `git checkout --` both files, `git apply --3way`
  sp4-media.patch THEN media-ii-track.patch, `echo APPLY_OK`, `contentshell`
  (NON-ZERO), `verify verify_media_ii.py` → M1–M11.
- [ ] **Step 4: apply.sh** — sp4-media.patch already listed (its content changed, no
  reorder). Append `"$ROOT/patches/media-ii-track.patch"` LAST.
- [ ] **Step 5: Full regression** (record counts):
```bash
unittests 'DeviceIdsTest.*:CamoucfgKeysTest.*:CanvasNoiseTest.*:MaskConfigTest.*:GettersTest.*'
verify verify_media_ii.py       # M1-M11
verify verify_sp4_media.py      # sp4-media enumerate — MUST stay green (pre-grant path unchanged)
verify verify_metric_jitter.py  # 11/11 (last slice, unrelated — smoke)
```
  Expected: camoucfg all PASS (82 keys), sp4-media UNCHANGED (proves the revision
  didn't regress the pre-grant spoof).
- [ ] **Step 6: Commit** `patches/sp4-media.patch patches/media-ii-track.patch scripts/apply.sh`
  msg `feat(media-ii): grant-aware getSettings/getCapabilities/label coherence — patches + apply`.

---

## Self-Review notes

- **Coherence gate:** M3 (`track.deviceId ∈ enumerate`) + M4 (getCapabilities/label
  match) prove the one-helper-both-sites design; M8 (origin salt) proves we didn't
  introduce a cross-origin linkable id; M9 proves rule-5 no-op pre+post.
- **REVISES sp4-media** — Task 3 re-extracts `patches/sp4-media.patch`; the sp4-media
  verify in regression proves the pre-grant path is untouched.
- **Residuals (§7):** pre-N/post-M count → Slice 2; `applyConstraints` reverse-map →
  documented; selectAudioOutput/ondevicechange unchanged.
- **Slice 2 hook:** `SyntheticDeviceId` is keyed by kind+real_id — Slice 2 (phantom)
  can synthesize ids for devices with no real backing by using a synthetic real_id
  per ordinal without renaming this helper.

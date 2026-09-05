# media-ii getSettings/getCapabilities coherence measurement (2026-09-05)

Checkout HEAD `a727b57805`, content_shell over the `127.0.0.1` echo_server
(getUserMedia needs a secure context), `--use-fake-device-for-media-stream`
(+`--use-fake-ui-for-media-stream` to auto-grant). This is **Slice 1 of the
media-ii program** (from sp4-media §1.5b); Slice 2 = phantom-webcam / count
coherence, Slice 3 = audio-ii.

sp4-media spoofs `enumerateDevices()` (configured counts of empty-field devices)
but leaves the granted `MediaStreamTrack`'s `getSettings()/getCapabilities()/label`
reading the **real** platform values. This slice makes the track coherent with the
spoofed enumerate — closing an incoherence **the spoof itself introduces**.

---

## 1. The incoherence (measured)

`measure_media_getsettings.py`, sp4 config (`mediaDevices:enabled`, counts 1/1/1):

```
enumerate:  [audioinput "" "" "",  videoinput "" "" "",  audiooutput "" "" ""]   (all empty)
tracks:
  audio: getSettings.deviceId="default"  groupId="8fc721…"  label="Fake Default Audio Input"
  video: getSettings.deviceId="7a8aa4…"  groupId="000921…"  label="fake_device_0"
```

A page that grants, then reads the track: `getSettings().deviceId` is **non-empty
and NOT among the enumerated deviceIds** (which are all `""`), and `label` is the
**real device name** (on real hardware, the camera/mic model — a hardware tell).
Real Chrome's invariant is the opposite (§2).

## 2. Real Chrome invariant (measured, stock, config=None)

`measure_media_grant.py` — grant is the axis:

- **PRE-grant** (fake-device, NO fake-ui): one entry per kind, **all fields
  empty** (`deviceId/groupId/label = ""`). sp4's empty spoof **matches** this — no
  pre-grant tell, groupId is empty pre-grant too.
- **POST-grant** (fake-ui + getUserMedia + re-enumerate): enumerate returns
  **non-empty** ids/labels; and the granted **track's `getSettings()` triple
  (deviceId, groupId, label) is byte-identical to its matching `enumerate`
  entry**. Audio's default device reports the literal `deviceId="default"`.

So the real invariant is: **post-grant, `track.getSettings().deviceId ∈
enumerate deviceIds`, and every field matches the enumerate entry.** `content_shell`
**distinguishes** the two grant states (fake-ui toggles it) → the fix is testable
here (not a #44-style Linux-only blind spot).

**Per-origin salt (critical).** Across three launches the real video deviceId was
`7a8aa4…`, `8b08671b…`, `2b3b484d…` — all different. Chromium **salts device ids
per-origin** (they rotate, so they are not a cross-origin identifier). The spoof
MUST preserve this: a *stable* synthetic id would become a cross-origin linkable id
for our own users — the exact opposite of the goal. The synthetic transform folds
the origin in (M8 pins it).

## 3. The grant-aware model (the coherent target)

`DevicesEnumerated` (`media_devices.cc:1461-1474`) already computes
`result_contains_nonempty_input_device_ids` from the **real** list, **before** the
sp4 override (~1496). That flag IS the pre/post-grant discriminator — no new
plumbing:

- **Pre-grant** (`!flag`): sp4's empty-count spoof, **unchanged** (matches §2).
- **Post-grant** (`flag`): **transform** each real device in place —
  `deviceId → SyntheticDeviceId(seed, kind, real_id, origin)`,
  `groupId → SyntheticDeviceId(seed, "group", real_group, origin)`,
  `label → generic-per-kind` (config-driven). Keep the **real count** (the
  configured-count spoof stays a pre-grant thing; see §5 residual).

The **track getters apply the SAME helper to the SAME real id** → coherence by
construction (the metric-jitter M′ architecture: one helper, two call sites).

## 4. Hook sites (measured)

- **Enumerate transform:** `media_devices.cc` `DevicesEnumerated`, inside the
  existing sp4 `if (kMediaDevicesEnabled)` block, branched on
  `result_contains_nonempty_input_device_ids`.
- **Track getters** (`media_stream_track_impl.cc`), all reading the real platform
  value — transform before returning:
  - `getSettings()` (@618): `settings->setDeviceId(platform_settings.device_id)`
    (@634), `setGroupId(platform_settings.group_id)` (@636).
  - `getCapabilities()` (@475): `platform_capabilities.device_id/group_id` (@487).
  - `label()` (@339): `return component_->GetSourceName();`.
  - `kind` (audio/video) via `component_->Source()->GetType()`; origin via
    `GetExecutionContext()->GetSecurityOrigin()`.
- **Do NOT touch `MediaStreamSource`** (shared with non-spoof paths).

## 5. Synthetic id helper

New `camoucfg::SyntheticDeviceId(uint64_t seed, std::string_view kind,
std::string_view real_id, std::string_view origin) -> std::string` (64 lowercase
hex, matching real salted-id shape). Deterministic; 4 mixed hash rounds over
`seed ‖ kind ‖ real_id ‖ origin` (value need only be deterministic + shaped — a
fingerprinter cannot distinguish it from HMAC-SHA256 hex). **Preserve the
`"default"` sentinel**: when `real_id == "default"`, return `"default"` unchanged
(it is a literal in real Chrome, not a hash). Empty real_id → empty (pre-grant path
never calls this, but be safe).

## 6. Config keys (`mediaDevices:` colon namespace)

- `mediaDevices:seed` (uint32) — seeds the synthetic transform (0/absent → the
  transform is a no-op, real ids pass through; but the enumerate spoof still needs
  `mediaDevices:enabled`).
- `mediaDevices:cameraLabel` / `microphoneLabel` / `speakerLabel` (string) —
  generic per-kind labels. Defaults `"Integrated Camera"`,
  `"Microphone (Realtek Audio)"`, `"Speakers (Realtek Audio)"`. No model catalog.
- Keys 78 → 82.

## 7. Deferred / residual (documented)

- **pre-N / post-M count** — pre-grant shows the configured count N (empties);
  post-grant shows the real count M (transformed). If operator sets N≠M, a page
  comparing counts across a grant sees the change. This is **Slice 2** (count
  coherence + openability / phantom-webcam) by definition, not new to Slice 1.
  Operator guidance: set counts ≈ real.
- **`applyConstraints({deviceId: <synthetic>})`** — a page can read the synthetic
  id and pass it back; stock resolves it against the real ids, so it won't match
  and the constraint fails. Reverse-mapping is Slice 2 territory; documented, not
  silent.
- **`selectAudioOutput()` / `ondevicechange`** — unchanged (high-friction /
  situational; sp4-media §1.5b verdict stands).

## 8. Verify (grant is the axis, RED-first) — M1–M11

- **M1** pre-grant enumerate = sp4 empties (unchanged).
- **M2** post-grant enumerate: same count as stock post-grant; every deviceId
  non-empty and ≠ the real id.
- **M3 (coherence gate — fails today):** `track.getSettings().deviceId ∈ post-grant
  enumerate deviceIds`.
- **M4** `getCapabilities().deviceId === getSettings().deviceId`; `track.label ===`
  the enumerate label for that device.
- **M5** same session ×2 → identical.
- **M6** separate launches, same seed, **same origin** (fixed echo_server port —
  confirm, else vacuous) → identical.
- **M7** different seed → different.
- **M8 (salt preservation):** different origin, same seed → **different** ids.
- **M9** no config (`{}`) → stock exact, PRE and POST grant.
- **M10** audio `"default"` sentinel preserved.
- **M11** label === configured generic, not `fake_device_0` / real model.

**Verify-environment caveats (measured):**
- **M6/M7/M8 are confounded by per-launch id rotation.** `--use-fake-device`'s
  real device id rotates every launch (fake devices are re-created per process), so
  the synthetic id (which folds the real id) rotates too — the browser cannot hold
  the real id fixed to test "same seed+origin → identical". M6 is reformulated to
  "rotates like stock, no supercookie"; M7/M8's seed/origin sensitivity is carried
  by the Task-1 unit tests (`DifferentSeedsDiffer` / `DifferentOriginsDiffer`) plus
  code review that both call sites fold seed+origin. Stated so the gap is not silent.
- **Partial grant is unexpressible on content_shell.** `--use-fake-ui-for-media-stream`
  auto-grants **all** kinds even when `getUserMedia({audio:true})` requests one
  (measured: video still gets a real id) — so the ungranted-kind placeholder state
  cannot be produced here. The partial-grant label fix (§7) is therefore
  inspection-verified, not M-suite-verified.

## 7b. Post-review residuals (Task 2 whole-review)

- **Partial-grant label leak — FIXED.** `result_contains_nonempty_input_device_ids`
  is an *any-input* flag: an audio-only grant makes it true, so the post-grant
  transform also runs over the **ungranted video kind's placeholder** (real
  `device_id==""`). The synthetic id is empty (empty→empty), but the generic label
  was stamped unconditionally → `{videoinput, "", "", "Integrated Camera"}`, an
  empty-id-with-label shape real Chrome never emits (a self-evident tell in the
  exact direction the slice prevents). **Fix:** the enumerate transform gates the
  label on the real `device_id` (`device_label = device_id.empty() ? "" : label`),
  mirroring the track's `CamouMaskLabel` empty-id passthrough. Inspection-verified
  (unexpressible on content_shell, per §8 caveat).
- **`InputDeviceInfo.getCapabilities()` returns `{}` post-transform** (enumerate
  side) while the granted *track's* `getCapabilities()` carries the synthetic id
  (M4). A caps-level enumerate/track gap; pre-existing to sp4's empty entries, out
  of M1–M11 scope. **Slice 2** owns it.
- **`enabled && seed==0` footgun:** post-grant then falls through to the real device
  list AND real labels (both surfaces coherent — spec §6 no-op — but the operator
  who enabled spoofing without a seed is exposed post-grant). Operator guidance:
  set a non-zero `mediaDevices:seed` whenever `mediaDevices:enabled`.

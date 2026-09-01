# SP4-media surfaces measurement (2026-09-01)

Checkout HEAD `a727b57805`, `out/Default` (content_shell), `is_component_build`,
default GN args (no `proprietary_codecs`, default `ffmpeg_branding`).

SP4-media nominally covered two clusters: **device enumeration** and the
**codec support matrix**. Measurement splits them: enumeration is a clean
Blink spoof; the codec matrix is a build-config concern that a Blink lie makes
*worse*, not better. Per the 2026-09-01 scope decision, this slice ships the
enumeration spoof only and documents codecs as a deferred build SP.

---

## 1. Device enumeration — `navigator.mediaDevices.enumerateDevices()`

### 1.1 Choke point

`third_party/blink/renderer/modules/mediastream/media_devices.cc`,
`MediaDevices::DevicesEnumerated` (line ~1410). The browser process delivers the
device list over mojo as `enumeration` (`Vector<Vector<WebMediaDeviceInfo>>`,
indexed by `mojom::blink::MediaDeviceType`). The method loops those into a
`MediaDeviceInfoVector media_devices` of `InputDeviceInfo` (audio/video **input**,
carrying capabilities) and `MediaDeviceInfo` (audio **output**), then calls
`result_tracker->Resolve(media_devices)`.

This is the single JS-reachable resolution point. Rewriting `media_devices`
after the build loop and before `Resolve` overrides every device the page can
see, in one place. `result_contains_nonempty_input_device_ids` feeds a UMA
report only (`ReportCompletedEnumerateDevices`) — leaving it computed from the
real list is report-only and safe.

`MediaDeviceType` order (verify in implementer): `kMediaAudioInput`,
`kMediaVideoInput`, `kMediaAudioOutput`, `kNumMediaDeviceTypes`.

### 1.2 Secure-context gating (verify apparatus)

`navigator.mediaDevices` is **undefined** on `about:blank` (insecure). Measured:
`TypeError: Cannot read properties of undefined (reading 'enumerateDevices')`.
Reachable only from a secure context. Verify must drive over the `127.0.0.1`
`echo_server` origin (127.0.0.1 is a potentially-trustworthy origin →
`isSecureContext === true`), exactly like `verify_sp4_fonts` F5.

### 1.3 Stock list (build box, pre-permission)

```json
{ "count": 2, "byKind": {"audioinput": 1, "audiooutput": 1},
  "all": [ {"kind":"audioinput","label":"","deviceId":"","groupId":""},
           {"kind":"audiooutput","label":"","deviceId":"","groupId":""} ],
  "secure": true }
```

Pre-permission, every field except `kind` is empty (a presence signal, not
hardware detail). The WSL box has no camera → 0 `videoinput`. The fingerprint a
site reads without `getUserMedia` permission is therefore the **per-kind
count** with empty labels/ids.

**Baseline caveat (whole-branch review):** this baseline is `content_shell`, not
consumer Chrome. Real Chrome pre-permission may surface a `default` /
`communications` audio pseudo-device and a `groupId` pairing that the all-empty
spoof does not reproduce. The empty-field *shape* is validated against the
measured `content_shell` stock (§1.3), NOT against real Chrome — do not read
"coherent" as "byte-identical to Chrome".

### 1.4 Camoufox precedent (`patches/media-device-spoofing.patch`)

Camoufox spoofs device enumeration and **nothing else** in the media surface. In
`MediaDevices::FilterExposedDevices` it clears the exposed list and inserts
configured counts of fake devices, empty labels, via `MediaEngineFake`:

- `mediaDevices:enabled` (bool) — gate; absent/false → real list untouched.
- `mediaDevices:micros` (uint32, default 3) — audioinput count.
- `mediaDevices:webcams` (uint32, default 1) — videoinput count.
- `mediaDevices:speakers` (uint32, default 1) — audiooutput count (Firefox gates
  these on mic permission via `mCanExposeMicrophoneInfo`).

### 1.5 Port design (Layer 1)

At `DevicesEnumerated`, when `camoucfg::GetBool(scope, kMediaDevicesEnabled)`:
replace `media_devices` with `micros` audioinput + `webcams` videoinput +
`speakers` audiooutput, each an `InputDeviceInfo`(inputs) / `MediaDeviceInfo`
(output) with empty `label`/`deviceId`/`groupId`. Defaults 3/1/1 (Camoufox).
Absent gate → no-op (SP0 rule 5).

Empty fields match the measured stock **pre-permission** shape exactly →
trivially coherent for the pre-permission case, which is the high-value
fingerprint (sites enumerate before prompting).

**Layer-1 boundary / deferred (media-ii):** post-`getUserMedia`-grant, real
Chrome populates `label` and a salted per-origin `deviceId`/`groupId`; this port
still emits empty fields there. That state needs a prior permission grant (high
friction, rare for fingerprinting) and unique stable id synthesis (extra
surface). Documented, deferred — same shape as the fonts `local()` deferral.
Firefox's own `mCanExposeMicrophoneInfo` speaker-gating nuance folds into the
same follow-on.

### 1.5b Residual read paths NOT gated by this slice (whole-branch review)

`DevicesEnumerated` is the only `enumerateDevices` resolution point, but device
topology leaks through other surfaces the override does not touch. Each is a
`local()`-shaped cross-surface tell — the spoof asserts a device set that another
surface can contradict. All are Layer-1-deferred (media-ii), listed so the gap is
named, not silent:

- **`getUserMedia` count-coherence (pre-permission, no grant needed — the sharp
  one).** The override injects a configured *count* with no check that the host
  can back it. Default `webcams=1`; on a camera-less host (the build box itself,
  §1.3) `enumerateDevices()` then reports 1 `videoinput`, but
  `getUserMedia({video:true})` rejects with `NotFoundError` (Chromium fails
  without even prompting when zero capture devices exist). A site cross-checking
  the two sees a **phantom webcam**. Audio is far less exposed (over-counting mics
  is hard to probe with empty ids; `getUserMedia({audio:true})` uses the default).
  The verify cannot see this: it measures counts only, over `content_shell` with
  `--use-fake-device-for-media-stream`, where `getUserMedia` always succeeds. The
  tell manifests only in the shipped browser against real hardware.
- **`MediaStreamTrack.getSettings()` / `getCapabilities()`** read the real
  platform `device_id`/`group_id`/`label` (`media_stream_track_impl.cc`,
  `component_->GetSettings(...)`), bypassing `DevicesEnumerated` entirely. After a
  grant, `enumerateDevices()` still emits empty ids while the granted track's
  `getSettings().deviceId` returns a real salted id that is NOT one of the spoofed
  empties — an enumerate-vs-track incoherence the spoof *introduces*. Needs a
  permission grant (bounded severity).
- **`MediaDevices.selectAudioOutput()`** returns a real chosen-output `deviceId`
  + `label`, ungated. Very high friction (explicit user picker).
- **`ondevicechange`** fires on real hotplug while the spoofed list is static — a
  change event with no diff in the (spoofed) list. Situational (mid-session
  hotplug).
- **Operator config, not a browser tell:** `micros`/`webcams`/`speakers` are
  unclamped `uint32` (matches Camoufox — it does not clamp either). An absurd
  count is a self-inflicted foot-gun; keep configured counts small and realistic
  (a real machine is ~1–3 of each). No clamp added — that would be code+rebuild
  for an operator-only mistake.

### 1.6 Config keys (colon namespace)

`mediaDevices:` is a synthetic namespace — `micros`/`webcams`/`speakers`/`enabled`
are not properties of the `mediaDevices` object — so colon, per the naming rule,
matching Camoufox. Keys 57 → 61.

---

## 2. Codec support matrix — OUT of Blink scope (build-config concern)

### 2.1 Surfaces

- `HTMLMediaElement::canPlayType(type)` — `core/html/media/html_media_element.cc`
  line ~1060. Thin: `GetSupportsType(ContentType(mime))` → `""`/`"maybe"`/
  `"probably"`.
- `MediaSource.isTypeSupported(type)` — `modules/mediasource/media_source.cc`
  line ~521 → `IsTypeSupportedInternal` → `media::` support checks.
- `MediaCapabilities.decodingInfo()/encodingInfo()` —
  `modules/media_capabilities/media_capabilities.cc` lines ~811 / ~1046.

All three bottom out in the `media::` layer's real codec support, set at build
time by `proprietary_codecs` + `ffmpeg_branding`.

### 2.2 Measured matrix (stock content_shell, default GN)

| probe | canPlayType | MSE.isTypeSupported |
|---|---|---|
| `video/mp4; codecs="avc1.42E01E"` (H.264) | `""` | false |
| `audio/mp4; codecs="mp4a.40.2"` (AAC) | `""` | false |
| `audio/mpeg` (MP3) | `"probably"` | true |
| `video/webm; codecs="vp9"` | `"probably"` | true |
| `audio/webm; codecs="opus"` | `"probably"` | true |
| `video/mp4; codecs="av01..."` (AV1) | `"probably"` | true |
| `video/mp4; codecs="hvc1..."` (HEVC) | `""` | false |
| `video/ogg; codecs="theora"` | `""` | false |

This is the **classic Chromium-branding tell**: H.264/AAC/HEVC/Theora absent,
MP3/VP9/Opus/AV1 present. Real Chrome returns `"probably"` for H.264 and AAC.
The matrix reliably says "this is not stock Chrome".

### 2.3 Why not a Blink spoof

Remapping `canPlayType`→`"probably"` for H.264 while the build has no H.264
decoder makes the **functional** behavior diverge: playback of an actual H.264
resource still fails. A site that cross-checks `canPlayType` against a real
`<video>` load sees a mismatch — a *stronger* tell than the honest `""`. Camoufox
never spoofs codecs for the same reason.

### 2.4 Coherent fix (deferred build SP)

The only coherent fix is to build the decoders in: GN args
`proprietary_codecs=true ffmpeg_branding="Chrome"`, then the matrix matches Chrome
because the codecs genuinely exist. That is build-config + a full proprietary
rebuild (multibuild/args work), not a Blink patch. Deferred to its own SP per the
2026-09-01 scope decision. `canPlayType`/`isTypeSupported`/`decodingInfo` stay
**honest** in this slice.

---

## 3. Slice scope summary

| surface | this slice |
|---|---|
| `enumerateDevices` device counts | **spoof** — Blink `DevicesEnumerated`, 4 keys |
| device labels/ids post-permission | defer (media-ii) — emit empty, coherent pre-permission |
| `getUserMedia` count-coherence (phantom webcam) | defer (media-ii) — §1.5b, pre-permission tell on real hardware |
| track `getSettings()`/`getCapabilities()` real ids | defer (media-ii) — §1.5b, post-grant enumerate-vs-track incoherence |
| `selectAudioOutput()` / `ondevicechange` | defer (media-ii) — §1.5b, high-friction / situational |
| codec matrix (canPlayType/isTypeSupported/decodingInfo) | **honest** — build-flag SP, not Blink |

### 3.1 Open verify item (needs browser-side read)

The override replaces `enumeration` **unconditionally**. In a
permissions-policy-restricted cross-origin subframe (no `camera`/`microphone`
grant) the browser process normally delivers a reduced/suppressed list; the spoof
would show full counts there → a top-frame-vs-subframe inflation tell. Not
confirmed — `content_shell` grants everything, so the verify cannot exercise it,
and confirming the restricted-subframe list shape needs
`content/browser/renderer_host/media/media_devices_dispatcher_host.*` +
the Blink permissions-policy gate. Flagged as a media-ii follow-up check, not a
ship blocker.

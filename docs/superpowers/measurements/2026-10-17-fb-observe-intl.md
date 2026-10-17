# Facebook recon re-run with exact counts and Intl (arms 1 to 3, 2026-10-17)

This re-runs arms 1 to 3 of the 2026-10-07 facebook recon
(`2026-10-07-fb-observe.md`) on the observer build with fast-call counting
(PR #30) and V8 runtime call stats for Intl (PR #36,
`docs/superpowers/specs/2026-10-13-observer-intl-rcs-design.md`). It answers
three questions:
- what the exact counts are;
- which Intl built-ins facebook calls;
- whether the 10-07 arm 3, whose trace stopped at 58 s, missed anything.

By the owner's ruling, Instagram, Threads and arm 4 are not re-run.

Every number below comes from `scripts/observe_judge.py`'s `summarize` and
`observe_report.load_requests`. They ran on the Windows host over
`D:\camou-win\observe\facebook\arm{1,2,3}` and printed only API names,
counts, hosts and cookie names. The observer counts reads, not values.

## 1. Build and launch

- **Build.** Native `chrome.exe` `154.0.8037.93` in
  `D:\camou-win\chromium\src\out\Observe`, built 2026-10-13 09:22 UTC. Its
  `args.gn` is the release shape plus `camou_observe = true` and
  `v8_enable_runtime_call_stats = true`. The Windows tree carries the change
  set as applied files on the pin `f89f3a4363`, not as commits, so this
  document names no repo commit for it. No spoof config was set, so every
  surface returned the host's real value.
- **Launcher.** `D:\camou-win\observe\recon.ps1` with `-Intl`. That copy's
  SHA256 is `561d3113ff62a2fadce45998b889d5a8915fbc7240c455325bbdfdff3417c994`
  (from `ee27259`). `-Intl` adds the trace categories
  `v8,disabled-by-default-v8.runtime_stats`. No CDP, no driver.
- **Session.** Each arm went through `scripts/windows/run-interactive.ps1`,
  in the owner's interactive session 1. The S4 GPU crash in session 0 does
  not apply.
- **Arms.**
  - Arm 1: logged-out landing, fresh profile, one load of
    `https://www.facebook.com/`.
  - Arm 2: fresh login. The owner typed the credentials; tooling never
    handled them.
  - Arm 3: arm 2's profile, with the owner browsing and scrolling the feed.
- **Closing.** The owner closed nothing. Tooling sent WM_CLOSE every time:
  arm 1 at 30 s; arm 2 at 03:18:42 and arm 3 at 03:22:01 UTC, each after the
  owner said that arm was done. Every browser exited cleanly and wrote its
  trace.

The owner's login was then backed up on the host, for the unattended arm 3
(`docs/observer/README.md`, "Unattended recon (facebook)").

## 2. Coverage

| | arm 1 | arm 2 | arm 3 |
|---|---|---|---|
| trace span / netlog span | 29.7 / 30.3 s | 403.5 / 405.5 s | 179.7 / 184.0 s |
| trace buffer | no chunks discarded | no chunks discarded | no chunks discarded |
| 10-07, for comparison | 30 of 30 s | 152 of 188 s | **58 of 116 s** (buffer full) |

Every arm here is complete. The 10-07 arm-3 counts covered only the first
58 s and were lower bounds. The 10-07 canvas and WebGL counts were also
lower bounds, because fast-call bindings were not yet counted. Every count
below is exact for its session.

The owner drove arms 2 and 3, and they ran for different lengths on the two
dates (405 s against 188 s, and 184 s against 116 s). Compare their counts
across dates as shapes, not as rates.

## 3. Per-arm results (`https://facebook.com` site)

Like the 10-07 tables, these use the `https://facebook.com` site section.
Dedicated workers report no site, and their reads are listed separately.

### Summary

| | arm 1 10-07 | arm 1 10-17 | arm 2 10-07 | arm 2 10-17 | arm 3 10-07 | arm 3 10-17 |
|---|---|---|---|---|---|---|
| requests, `facebook.com` site | 35 | 36 | 386 | 584 | 925 | 1 467 |
| requests, whole session | 37 | 38 | 1 083 | 590 | 925 | 1 472 |
| `/ajax/bz` | 5 of 35 | **5 of 36** | 17 of 386 | **16 of 584** | 0 of 925 | **0 of 1 467** |
| observed calls, `facebook.com` site | 930 | 1 016 | 4 602 | 15 458 | 11 403 (58 s) | 41 878 |
| worker calls (separate section) | 0 | 0 | 46 | 96 | 61 (58 s) | 162 |

The 10-07 arm 2 visited four non-Meta sites, with 685 requests. The 10-17
arm 2 visited none. Its 6 requests outside `facebook.com` are Chrome's own
services: Web Store, autofill, `meta.com`'s `/.well-known/webauthn`, and the
password leak check (§6).

### Surface groups (calls)

| group | arm 1 10-07 | arm 1 10-17 | arm 2 10-07 | arm 2 10-17 | arm 3 10-07 (58 s) | arm 3 10-17 |
|---|---|---|---|---|---|---|
| layout-probe | 78 | 101 | 1 601 | 8 472 | 6 734 | 29 814 |
| storage | 236 | 257 | 1 556 | 2 971 | 3 190 | 8 634 |
| navigator | 211 | 187 | 955 | 3 062 | 1 476 | 3 252 |
| canvas | 378 | 374 | 382 | 758 | 0 | 170 |
| webgl | 0 | **68** | 76 | 140 | 0 | 0 |
| webgpu | 0 | **2** | 0 | **6** | 0 | 0 |
| screen | 18 | 18 | 22 | 30 | 2 | 6 |
| audio | 9 | 9 | 9 | 18 | 0 | 0 |
| fonts | 0 | 0 | 1 | 1 | 1 | 2 |
| intl (built-in calls, §4) | — | 8 | — | 60 | — | 57 |
| total, without intl | 930 | 1 016 | 4 602 | 15 458 | 11 403 | 41 878 |

No arm saw a webrtc row.

### Members

| member | arm 1 10-07 | arm 1 10-17 | arm 2 10-07 | arm 2 10-17 | arm 3 10-07 (58 s) | arm 3 10-17 |
|---|---|---|---|---|---|---|
| `Storage.getItem` | 171 | 182 | 1 142 | 2 046 | 2 713 | 7 104 |
| `Storage.key` | 17 | 17 | 123 | 280 | 167 | 534 |
| `Storage.length` (get) | 24 | 24 | 147 | 317 | 177 | 565 |
| `Element.getBoundingClientRect` | 13 | 26 | 427 | 1 294 | 1 534 | 8 822 |
| `HTMLElement.offsetHeight` / `offsetWidth` (get) | — | below top 30 | — | 3 530 / 1 774 | — | 2 829 / 1 464 |
| `Window.innerHeight` / `innerWidth` (get) | 13 / 15 | 17 / 19 | 300 / 268 | 710 / 619 | 1 701 / 1 530 | 6 713 / 6 039 |
| `Window.devicePixelRatio` (get) | below top 25 | 9 | 100 | 167 | 515 | 2 662 |
| `Window.matchMedia` | 25 | 26 | 172 | 324 | 408 | 960 |
| `Navigator.deviceMemory` (get) | 14 | 10 | 168 | 1 394 | 590 | 1 575 |
| `Navigator.connection` (get) | 45 | 16 | 247 | 173 | 253 | 80 |
| `NetworkInformation.rtt` (get) | 17 | 19 | 68 | 103 | 76 | 159 |
| `Navigator.hardwareConcurrency` (get) | 23 | 25 | 87 | 127 | 78 | 172 |
| `Navigator.serviceWorker` (get) | 0 | 0 | 52 | 676 | 259 | 750 |
| `Navigator.userAgentData` (get) | 1 | 1 | 1 | 2 | 0 | 0 |
| `NavigatorUAData.getHighEntropyValues` | 0 | 0 | 0 | 0 | 0 | 0 |
| `CanvasRenderingContext2D.measureText` | 87 | 87 | 87 | 174 | 0 | 0 |
| `CanvasRenderingContext2D.font` (set) | 74 | 74 | 74 | 148 | 0 | 0 |
| `CanvasRenderingContext2D.getImageData` | 9 | 9 | below top 25 | 20 | 0 | 56 |
| `HTMLCanvasElement.toDataURL` | 2 | 2 | 2 | 4 | 0 | 0 |
| `WebGLRenderingContext.getParameter` | 0 | 24 | 28 | 50 | 0 | 0 |
| `WebGL2RenderingContext.getParameter` | — | 10 | — | 20 | 0 | 0 |
| `GPU.requestAdapter` / `GPUAdapter.features` (get) | 0 / 0 | 1 / 1 | 0 / 0 | 3 / 3 | 0 / 0 | 0 / 0 |

Notes:
- **Arm 1's WebGL rows** are the full render-and-read sequence that 10-07
  saw only in arm 2, over 24 members:
  - shader compile and link, `drawArrays` and `readPixels`;
  - `getParameter` (24 on WebGL 1, 10 on WebGL 2),
    `getShaderPrecisionFormat`, `getExtension` and
    `getSupportedExtensions`, on both contexts.
- **Arm 1's audio rows** are the 10-07 sequence again: an `AudioContext`
  constructed, read (`baseLatency`, `outputLatency`, `sampleRate`,
  `destination`, `audioWorklet`) and closed.
- **Arm 2 runs arm 1's fingerprint battery twice.** Audio, `measureText`,
  `font` and `toDataURL` are each exactly 2× arm 1, and WebGL is 140
  against 2 × 68. The battery ran once per page load, before and after
  login.
- **Arm 3's canvas rows** are not the text battery. They are
  `getImageData` 56 and `drawImage`, `getContext` and `width`/`height` sets
  28 each: image work on the feed.

Worker reads (`WorkerNavigator` and `NetworkInformation`, the separate
section):

| member | arm 2 10-07 | arm 2 10-17 | arm 3 10-07 (58 s) | arm 3 10-17 |
|---|---|---|---|---|
| `userAgent` | 25 | 42 | 19 | 55 |
| `onLine` | 9 | 31 | 14 | 44 |
| `deviceMemory` | 4 | 8 | 6 | 15 |
| `userAgentData` | 4 | 7 | 3 | 9 |
| `languages` / `locks` | 2 / 2 | 4 / 4 | 2 / 2 | 6 / 6 |
| `hardwareConcurrency` | 0 | 0 | 2 | 6 |
| `connection` | 0 | 0 | 7 | 3 |
| `NetworkInformation.downlink` / `effectiveType` / `rtt` | 0 | 0 | 2 each | 6 each |

## 4. Intl built-ins (new)

These are runtime-call-stats counters on the `facebook.com` site, summed
over every V8 entry slice. The names are V8's bare builtin names.

| builtin | arm 1 | arm 2 | arm 3 |
|---|---|---|---|
| `DateTimeFormatConstructor` | 4 | 10 | 4 |
| `DateTimeFormatPrototypeResolvedOptions` | 4 | 10 | 4 |
| `StringPrototypeLocaleCompareIntl` | 0 | 40 | 48 |
| `StringPrototypeToLocaleUpperCase` | 0 | 0 | 1 |

Every arm constructs `Intl.DateTimeFormat` and reads `resolvedOptions()`,
in equal numbers. That pair is the usual way to read the time zone and
locale. The logged-out landing does it 4 times, and nothing else in Intl.
`localeCompare` appears only once logged in, at sorting volumes.

`Date.prototype.getTimezoneOffset` is a CSA builtin with no counter. It
stays unobservable (`observe_report.NOT_OBSERVABLE`).

## 5. Requests and cookies

Hosts under the `facebook.com` site. Query strings are dropped, and CDN
point-of-presence names are collapsed to `*`.

| host | arm 1 10-07 | arm 1 10-17 | arm 2 10-07 | arm 2 10-17 | arm 3 10-07 | arm 3 10-17 |
|---|---|---|---|---|---|---|
| `static.xx.fbcdn.net` | 23 | 24 | 184 | 294 | 326 | 533 |
| `www.facebook.com` | 9 | 10 | 107 | 154 | 177 | 279 |
| `scontent.*.fbcdn.net` | 0 | 0 | 81 | 83 | 413 | 341 |
| `video.*.fbcdn.net` | 0 | 0 | — | 33 | — | 284 |
| `gateway.facebook.com` | 0 | 0 | 5 | 10 | 5 | 15 |
| `web-chat-e2ee`, `reg-e2ee` `.facebook.com`, `www.fbsbx.com` | 0 | 0 | 4 | 5 | 3 | 6 |
| `content-autofill.googleapis.com` | 2 | 1 | 4 | 4 | 1 | 9 |
| `www.instagram.com` | — | 1 | — | 1 | — | 0 |
| other | 1 | 0 | 1 | 0 | 0 | 0 |

10-07 did not split out the `video.*` and `www.instagram.com` rows. Its
"other" row may hold them.

`/ajax/` endpoints on `www.facebook.com`:

| path | arm 1 10-17 | arm 2 10-17 | arm 3 10-17 |
|---|---|---|---|
| `POST /ajax/bz` | 5 | 16 | 0 |
| `GET /ajax/bootloader-endpoint/` | 1 | 35 | 62 |
| `POST /ajax/bulk-route-definitions/` | 0 | 15 | 68 |
| `POST /ajax/relay-ef/` | 0 | 2 | 16 |
| `POST /ajax/bnzai` | 0 | 11 | 14 |
| `POST /ajax/qm/` | 1 | 6 | 6 |
| `POST /ajax/route-definition/` | 0 | 1 | 6 |
| `POST /ajax/webstorage/process_keys/` | 1 | 5 | 3 |
| `POST /ajax/comet_error_reports/` | 0 | 3 | 3 |
| `GET /ajax/dtsg/` | 0 | 2 | 3 |
| `POST /ajax/navigation/` | 0 | 0 | 2 |
| `POST /ajax/browser_error_reports/` | 1 | 1 | 0 |

`.facebook.com` cookie names:

| arm | names |
|---|---|
| 1 | `datr`, `fr`, `sb`, `wd` (same as 10-07) |
| 2 | `c_user`, `datr`, `fr`, `locale`, `sb`, `wd`, `xs` |
| 3 | the arm-2 seven plus `ps_l` and `ps_n` (same nine as 10-07) |

Arm 2's cookie database was copied when arm 2 closed, and `ps_l`/`ps_n`
were set later, during arm 3 on the same profile. The unattended arm 3
counts as logged in only with `c_user` and `xs`.

## 6. Findings and limits

1. **The fingerprint battery runs on the logged-out landing.** On 10-17,
   arm 1 ran WebGL (68 calls, full render-and-read) and WebGPU
   (`GPU.requestAdapter` and `GPUAdapter.features`). On 10-07 it ran
   neither, although that build did count WebGL (the 10-07 arm 2 saw 76
   calls) and had `GPU` on its allow-list. With one sample per date, a
   battery rolled out between the dates cannot be told apart from one
   served per visit. Either way, a
   logged-out first load already reads WebGL and WebGPU.
2. **WebGPU is now read.** 10-07 saw no webgpu row in any arm. On 10-17 it
   was 2 calls in arm 1 and 6 in arm 2, always requested next to the WebGL
   battery. The adapter's feature set is now a facebook-read surface. On a
   build where WebGPU differs by session (S4), it is a coherence risk.
3. **Every arm reads the time zone the Intl way.** `DateTimeFormat` plus
   `resolvedOptions` runs 4 to 10 times per arm, logged out included. A
   time zone that disagrees with the exit IP (roadmap backlog 13) is
   visible to facebook from the first load.
4. **The established feed sends no `/ajax/bz`.** It made 0 of 1 467
   requests on 10-17 and 0 of 925 on 10-07. The `bz` stream belongs to the
   landing and login pages. The feed runs no audio, WebGL, WebGPU or text
   canvas, over its complete 180 s trace. That rules out the 10-07 doubt
   that the battery ran after its 58 s cutoff.
5. **The login fired Chrome's password leak check.** Arm 2 sent requests to
   `passwordsleakcheck-pa.googleapis.com`. That is Chrome's own feature
   (a hashed credential prefix sent to Google), not facebook's. A stock
   Chrome does the same. It is listed because it is traffic the fork sends
   at login.
6. **Arms 2 and 3 doubled or tripled their layout-probe and storage counts**
   against 10-07. Both sessions were longer and fully traced, so this shows
   volume, not new behaviour.

Limits:
- Each arm is one sample, and arms 2 and 3 are owner-driven sessions of
  different lengths.
- Arm 3 includes the owner's scrolling. The unattended arm 3 that
  `observe-auto.ps1` runs is one load and 120 s with no input, so its
  baseline is not comparable to this arm 3's volumes.
- This launch path does not read `chrome://gpu`'s crash count. Session 1
  is the guard.
- Dedicated workers are counted in their own section, not in the site
  totals.
- Arm 4, Instagram and Threads are not re-run, by the owner's ruling.

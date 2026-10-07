# Facebook recon with the tracking observer (four arms)

This is the first live measurement with the tracking observer
(`docs/superpowers/specs/2026-10-06-tracking-observer-design.md`, operator guide
`docs/observer/README.md`). It answers one question for facebook.com: which
fingerprint surfaces Meta's code reads on this build, and what the browser
sends back. Instagram and Threads are a later document; their arm-1 runs
exist but are not analysed here.

Every number below comes from the per-arm `report.md` files on the Windows
host (`D:\camou-win\observe\facebook\<arm>\report.md`), read with a small
aggregating script that printed only API names, counts, hosts, path prefixes
and cookie names, or from the controller ledger of the run. The observer
counts reads, not values: a row says that a page read `deviceMemory`, not what
it got.

## 1. Method

### Build

The browser was native `chrome.exe` on the Windows host, built in its own out
dir `D:\camou-win\chromium\src\out\Observe` from the change set at Chrome
`154.0.8037.93` (the pin) plus the observer slice (`patches/observe.patch`,
`camou_observe = true`). The tree also carried the S2b canvas-noise work in
progress at the time. That does not affect the counts: the observer event fires
at the binding entry, before any spoof hook runs, and no spoof config was set
(neither launcher sets `CAMOU_CONFIG` or `CAMOU_PRESET`), so every surface
returned the real value of the host.

Arms 1 to 3 and the first arm 4 ran on the phase-1 build. The arm-4 re-run used
the phase-1c rebuild with script attribution (commits `31431c9..ee0c7da`, a
435-step incremental build that finished at 08:29 ICT).

### Launch

Every arm was launched by `D:\camou-win\observe\recon.ps1`. It starts the
browser headed with `--user-data-dir`, `--no-first-run`,
`--no-default-browser-check`, the `--trace-startup*` flags and `--log-net-log`,
and attaches nothing: no CDP, no driver. When the browser closes, it runs
`scripts/observe_report.py` over the trace, the netlog and a copy of the
profile's cookie database. Each arm got a fresh profile, except arm 3, which
reused arm 2's profile so that the session was already logged in.

- **Arm 1, logged-out landing.** This arm was launched by tooling, under an
  exception the owner approved on 2026-10-07 (the spec records it under
  "Recon"). It ran from session 0, the non-interactive desktop: one load of
  `https://www.facebook.com/`, 30 s, no interaction, no repeats. Session 0 has
  no window manager, so a graceful close was impossible. A self-test on
  example.com showed that first: `taskkill` was refused and no trace was
  written. The launch therefore added `--remote-debugging-port=0`, and the one
  CDP message sent was `Browser.close` at 30 s, with no `Runtime.enable` and no
  page-target attach. The debug port was open during this arm. It ran between
  the owner's ruling at 07:26 ICT and 07:36 ICT.
- **Arms 2 to 4** were driven by the owner by hand, in their RDP session
  (session 1), through one-off scheduled tasks that started `recon.ps1`. The
  owner typed the credentials; tooling never handled them. An RDP session
  changes the display adapter and resolution the browser sees. The observer
  counts reads, not values, so the counts stand, but the screen and GPU values
  those reads returned were the RDP session's values.
  - Arm 2, fresh login: launched 07:36 ICT.
  - Arm 3, established session, about two minutes of feed browsing: launched
    07:40 ICT on arm 2's profile.
  - Arm 4, third-party page (tiki.vn home page and a product page): first run
    launched 07:47 ICT (kept as `arm4-noscript`), re-run with script
    attribution launched 08:33 ICT (`arm4`).

All times are 2026-10-07, ICT (UTC+7).

## 2. A trace-filter defect found during the recon

Arms 1 to 3 and the first arm 4 ran with
`--trace-startup=disabled-by-default-camou.observe`. A filter that lists only a
disabled-by-default category still enables every default category, so these
traces recorded all of Chrome's normal tracing as well. They were 85 MB (arm 1),
898 MB (arm 2), about 900 MB (arm 3) and 560 MB (first arm 4). They also held
more of the browsing session than the observer needs.

`observe_report.py` reads only events in the
`disabled-by-default-camou.observe` category, so the extra categories add no
rows. They did cost rows in two arms, because they filled the trace buffer
(next subsection). The fix (`a9e23d1`, docs `4c7d6da`) changed the filter to
`-*,disabled-by-default-camou.observe` in the README, the spec,
`verify_observe.py`, `recon.ps1` and `arm1.ps1`. On the same probe page the new
filter wrote 68.9 KB with 2 categories, against 7.17 MB with 77 categories
before. `verify_observe.py` went RED 0/11 and GREEN 11/11 twice with it. The
README's overhead table was measured again with only the observer category on,
because the earlier "on" timing had included every default category.

The arm-4 re-run used the new filter. Its trace was 8.1 MB, against 560 MB for
the same page with the old one.

### The buffer filled in arms 2 and 3

With `--trace-startup-record-mode=record-as-much-as-possible` the trace buffer
is 200 MB (`buffer_size` 209 715 200 in each trace's `traced_buf` stats). A
full buffer discards every new chunk, so the whole trace stops, observer events
included, while the browser and the netlog carry on. The last observer event
and the last trace event are 0.03 to 0.38 s apart in every arm, so comparing
those two clears every arm and shows nothing. The trace's end against the
netlog's requests does show it (read on the Windows host on 2026-10-07 by
streaming each trace line by line):

| | arm 1 | arm 2 | arm 3 | first arm 4 | arm 4 re-run |
|---|---|---|---|---|---|
| buffer written | 18.7 MB | 200 MB (full) | 200 MB (full) | 124 MB | 5.3 MB |
| chunks discarded | 0 | 21 109 | 21 683 | 0 | 0 |
| trace span | 30.2 s | 152.0 s | 58.1 s | 50.1 s | 2 451 s |
| requests, first to last | 29.9 s | 187.7 s | 116.2 s | 49.6 s | 2 451 s |
| requests after the trace ended | 0 of 37 | 311 of 1 083 | 189 of 925 | 0 of 719 | 1 of 836 (same ms) |

- **Arm 1 and the first arm 4: unaffected.** No chunk was discarded and no
  request came after the trace's end.
- **Arm 2: close to complete for facebook.com.** The trace stopped 35.9 s
  before the last request. 309 of the 311 later requests were under the four
  non-Meta sites the owner visited afterwards; 2 of the 386 `facebook.com`
  requests came later, and no `/ajax/bz`. Its facebook.com counts are lower
  bounds, but the untraced tail was almost all other sites.
- **Arm 3: the trace covers the first 58 s of 116 s.** 189 of its 925
  requests (20 %), all under `facebook.com`, came after the trace stopped.
  Every arm-3 observer count in this document covers only that first minute
  and is a lower bound. Request counts and `/ajax/bz` come from the netlog,
  which covers the whole session; the untraced tail had no `/ajax/bz`.
- **The arm-4 re-run** used 5.3 MB of the buffer in a 41-minute session, so the
  `-*,` filter makes a fill unlikely. `observe_report.py` now prints whether the
  buffer discarded chunks.

## 3. Per-arm results

The report groups rows by top-level site. The tables below use the
`https://facebook.com` section, whose reading origin was
`https://www.facebook.com` for all but 3 calls (from `https://www.fbsbx.com`).
Dedicated workers report no site, so their reads land in a separate
`https://www.facebook.com` section (a known report limitation). They are listed
separately here. The controller ledger added them into the navigator totals
(1 001 for arm 2, 1 537 for arm 3), and the tables below do not.

Every `/ajax/bz` count has its denominator next to it: the requests under the
`facebook.com` site, and the whole session.

### Summary

| | arm 1 (logged out) | arm 2 (fresh login) | arm 3 (established, browsing) |
|---|---|---|---|
| requests, `facebook.com` site | 35 | 386 | 925 |
| requests, whole session | 37 | 1 083 (685 of them under four non-Meta sites, excluded) | 925 |
| `/ajax/bz` | **5 of 35** | **17 of 386** | **0 of 925** |
| observed calls, `facebook.com` site | 930 | 4 602 | 11 403 (first 58 s) |
| worker calls (separate section) | 0 | 46 | 61 (first 58 s) |
| trace covered, of the request span | 30 of 30 s | 152 of 188 s | **58 of 116 s** |

Arm 3's trace stopped when its buffer filled (section 2): every arm-3 observer
count in the tables below covers the first 58 s and is a lower bound. Arm 2's
untraced tail was almost all non-Meta sites.

Arm 2's profile also visited several non-Meta sites during the owner's session.
Those sections (four sites, 685 requests) and their cookies are left out of
every table here. Arm 3 reused that profile but visited no other site; its
cookie database still holds the other sites' cookies, which are also left out.

### Surface groups (calls)

| group | arm 1 | arm 2 | arm 3 |
|---|---|---|---|
| layout-probe | 78 | 1 601 | 6 734 |
| storage | 236 | 1 556 | 3 190 |
| navigator | 211 | 955 | 1 476 |
| canvas | 378 | 382 | 0 |
| webgl | 0 | 76 | 0 |
| screen | 18 | 22 | 2 |
| audio | 9 | 9 | 0 |
| fonts | 0 | 1 | 1 |
| total | 930 | 4 602 | 11 403 |

No arm saw a webgpu or webrtc row. The one `fonts` call in arms 2 and 3 is
`FontFaceSet.ready`.

### Selected members (calls)

| member | arm 1 | arm 2 | arm 3 |
|---|---|---|---|
| `Storage.getItem` | 171 | 1 142 | 2 713 |
| `Storage.key` | 17 | 123 | 167 |
| `Storage.length` (get) | 24 | 147 | 177 |
| `Element.getBoundingClientRect` | 13 | 427 | 1 534 |
| `Window.innerHeight` / `innerWidth` (get) | 13 / 15 | 300 / 268 | 1 701 / 1 530 |
| `Window.devicePixelRatio` (get) | below top 25 | 100 | 515 |
| `Window.matchMedia` | 25 | 172 | 408 |
| `Navigator.deviceMemory` (get) | 14 | 168 | 590 |
| `Navigator.connection` (get) | 45 | 247 | 253 |
| `NetworkInformation.rtt` (get) | 17 | 68 | 76 |
| `Navigator.hardwareConcurrency` (get) | 23 | 87 | 78 |
| `Navigator.serviceWorker` (get) | 0 | 52 | 259 |
| `Navigator.userAgentData` (get) | 1 | 1 | 0 |
| `NavigatorUAData.getHighEntropyValues` | 0 | 0 | 0 |
| `CanvasRenderingContext2D.measureText` | 87 | 87 | 0 |
| `CanvasRenderingContext2D.font` (set) | 74 | 74 | 0 |
| `CanvasRenderingContext2D.getImageData` | 9 | below top 25 | 0 |
| `HTMLCanvasElement.toDataURL` | 2 | 2 | 0 |
| `WebGLRenderingContext.getParameter` | 0 | 28 | 0 |

The arm-1 audio rows are an `AudioContext` that is constructed, read
(`baseLatency`, `outputLatency`, `sampleRate`, `destination`, `audioWorklet`)
and closed. The same 9 calls appear in arm 2, before login. The arm-2 WebGL
rows are a full render-and-read sequence over 24 members: shader compile and
link, `drawArrays`, `readPixels`, `getParameter`, `getShaderPrecisionFormat`,
and `getSupportedExtensions` on both WebGL 1 and WebGL 2 contexts.

Worker reads (`WorkerNavigator`, the separate section):

| member | arm 2 | arm 3 |
|---|---|---|
| `userAgent` | 25 | 19 |
| `onLine` | 9 | 14 |
| `deviceMemory` | 4 | 6 |
| `userAgentData` | 4 | 3 |
| `connection` | 0 | 7 |
| `languages` / `locks` | 2 / 2 | 2 / 2 |
| `hardwareConcurrency` | 0 | 2 |
| `NetworkInformation.downlink` / `effectiveType` / `rtt` | 0 | 2 each |

### Requests (`facebook.com` site, query strings dropped)

| host | arm 1 | arm 2 | arm 3 |
|---|---|---|---|
| `static.xx.fbcdn.net` | 23 | 184 | 326 |
| `www.facebook.com` | 9 | 107 | 177 |
| `scontent.*.fbcdn.net` (media, several CDN POPs) | 0 | 81 | 413 |
| `gateway.facebook.com` (`GET /ws`) | 0 | 5 | 5 |
| `edge-chat`, `reg-e2ee`, `web-chat-e2ee` `.facebook.com`, `www.fbsbx.com` | 0 | 4 | 3 |
| `content-autofill.googleapis.com` (Chrome, see finding 6) | 2 | 4 | 1 |
| other | 1 | 1 | 0 |

`/ajax/` endpoints on `www.facebook.com`:

| path | arm 1 | arm 2 | arm 3 |
|---|---|---|---|
| `POST /ajax/bz` | 5 | 17 | 0 |
| `GET /ajax/bootloader-endpoint/` | 0 | 19 | 31 |
| `POST /ajax/bulk-route-definitions/` | 0 | 8 | 47 |
| `POST /ajax/relay-ef/` | 0 | 1 | 10 |
| `POST /ajax/bnzai` | 0 | 4 | 9 |
| `POST /ajax/qm/` | 1 | 3 | 1 |
| `POST /ajax/webstorage/process_keys/` | 1 | 3 | 2 |
| `POST /ajax/navigation/` | 0 | 0 | 2 |
| `POST /ajax/browser_error_reports/` | 1 | 1 | 0 |
| `POST /ajax/comet_error_reports/` | 0 | 2 | 1 |
| `GET /ajax/dtsg/` | 0 | 1 | 1 |

Arm 1 also made one request to `accounts.meta.com` (`GET /.well-known/webauthn`)
under its own `meta.com` site section, and arm 2 made the same request.

### Cookie names

| arm | `.facebook.com` cookie names |
|---|---|
| 1 | `datr`, `fr`, `sb`, `wd` |
| 2 | `c_user`, `datr`, `fr`, `locale`, `ps_l`, `ps_n`, `sb`, `wd`, `xs` |
| 3 | same nine as arm 2 (same profile) |

## 4. Arm 4: tiki.vn, a third-party page with the Meta Pixel and SDK

tiki.vn is a large Vietnamese shop that embeds the Meta Pixel and the Facebook
SDK. The owner opened the home page and one product page in a fresh profile,
so the browser was not logged in to Facebook.

| | first run (`arm4-noscript`, old filter) | re-run (`arm4`, script attribution, new filter) |
|---|---|---|
| requests, `tiki.vn` site | 697 | 810 |
| requests, whole session | 719 | 836 |
| observed calls, `tiki.vn` site | 21 154 | 22 221 |
| `/ajax/bz` | 0 of 697 | 0 of 810 |
| trace size | 560 MB | 8.1 MB |

The zero `/ajax/bz` is expected here: Falco is first-party facebook.com code.
One small non-Meta site section in each run (14 and 17 requests) is left out.

### Requests to Meta

| host | request | first run | re-run |
|---|---|---|---|
| `connect.facebook.net` | `GET /en_US/fbevents.js` | 1 | 1 |
| `connect.facebook.net` | `GET /signals/config/<pixel-id>` | 1 | 1 |
| `connect.facebook.net` | `GET /en_US/sdk.js` | 1 | 1 |
| `connect.facebook.net` | `GET /en_US/bundle/sdk.js/` | 1 | 1 |
| `connect.facebook.net` | `GET /app_config/json/<app-id>/` | 1 | 1 |
| `www.facebook.com` | `GET /x/oauth/status` | 1 | 1 |
| `www.facebook.com` | `POST /tr/` | **3** | **4** |

Cookie names: `_fbp` on `.tiki.vn` (the Pixel's first-party browser id) and
`fr` on `.facebook.com`, in a profile that never opened facebook.com. Five
other first-party cookies on `.tiki.vn` belong to Google Analytics, Google Ads,
Amplitude and Tiki's own tracker and are not listed.

### What origin attribution could not separate, and how script attribution did

In the first run all 21 154 calls had the reading origin `https://tiki.vn`, and
no call had a Meta origin. `fbevents.js` and `sdk.js` are loaded with
`<script src>` into the page, so they run as the page's own code, and a reading
origin cannot tell them apart from Tiki's scripts. (39 calls came from other,
non-Meta origins.) That limit led to phase 1c: each trace event
now carries the URL of the script at the top of the JavaScript stack
(`v8::StackTrace::CurrentScriptNameOrSourceURL`), and the report shows it as
host and path. A surrogate page that loads `fbevents.js` with Tiki's real
pixel id was ruled out, because it would send fabricated events into a third
party's pixel. Re-running the real page with script attribution answers the
same question without doing that.

The re-run split the 22 221 calls over 38 scripts:

| script | calls | share |
|---|---|---|
| Tiki's scripts (`frontend.tikicdn.com`, `tiki.vn`, one `blob:`) | 20 676 | 93.0 % |
| of which the single chunk `frontend.tikicdn.com/.../chunks/42221-*.js` | 18 051 | 81.2 % |
| Meta's three scripts (below) | 239 | 1.1 % |
| nine other third-party scripts | 1 274 | 5.7 % |
| `(no script)` | 32 | 0.1 % |

Meta's scripts, member by member:

| script | member | calls |
|---|---|---|
| `connect.facebook.net/en_US/fbevents.js` (154) | `Document.cookie` get / set | 42 / 5 |
| | `Navigator.userAgent` | 33 |
| | `Element.getBoundingClientRect` | 21 |
| | `Storage.getItem` / `setItem` | 13 / 2 |
| | `Screen.height` / `Screen.width` | 12 / 12 |
| | `Navigator.vendor` | 11 |
| | `Navigator.userAgentData`, `NavigatorUAData.brands`, `NavigatorUAData.platform` | 1 each |
| `connect.facebook.net/signals/config/<pixel-id>` (56) | `Storage.key` | 36 |
| | `Navigator.userAgent` | 13 |
| | `Storage.length` | 4 |
| | `Storage.getItem` | 3 |
| `connect.facebook.net/en_US/bundle/sdk.js/` (29) | `Storage.removeItem` / `setItem` / `getItem` | 11 / 9 / 7 |
| | `Navigator.userAgent` | 1 |
| | `Document.cookie` get | 1 |

No Meta script made a canvas, WebGL, audio, fonts or media call, and none
called `getHighEntropyValues`. The one `getHighEntropyValues` call and the two
WebGL calls on the page came from other scripts.

## 5. Findings

Arm-3 ("while browsing") observer counts here cover the first 58 s of that
session and are lower bounds (section 2); request counts cover all of it.

1. **`/ajax/bz` fires logged out and at login, and not at all while browsing an
   established session.** 5 of 35 requests on the logged-out landing page, 17
   of 386 at login, 0 of 925 during about two minutes of feed browsing on the
   same profile. The 925 requests in arm 3 show the netlog was recording; the
   zero is about Facebook, not about the instrument. Both counts come from the
   netlog, which covers the whole session, not from the trace that stopped
   at 58 s.
2. **WebGL, canvas and audio are read at login and not again in the same
   profile.** 76 WebGL calls in arm 2 (a full render and `readPixels`, plus
   parameter and extension queries), 0 in arm 1 and 0 in the traced first
   58 s of arm 3. Canvas and audio are also read on the landing page: 378
   canvas and 9 audio calls logged out, 382 and 9 in arm 2 (whose login starts
   from the same landing page), 0 and 0 in arm 3's first 58 s. Arm 3 reused
   arm 2's profile, so the likely reading is a fingerprint computed at login
   and kept in the profile, not an established session that is never
   fingerprinted (section 8). The landing-page canvas work
   is text-heavy (`measureText` 87, `font` set 74, `fillText` 13) and ends in
   `getImageData` 9 and `toDataURL` 2. The landing page also reads
   `navigator.userAgentData` once.
3. **`navigator.deviceMemory` is read hundreds of times when logged in.** 14
   calls logged out, 168 at login, 590 while browsing, plus 4 and 6 from
   workers. `navigator.connection` follows it (45, 247, 253) and
   `navigator.serviceWorker` appears once logged in (52, 259). In this run
   `deviceMemory` was not spoofed: no config was set, so the page got the
   host's real value. The key `navigator.deviceMemory` exists (SP1b) and only
   takes effect when configured. `connection` and its `NetworkInformation`
   fields have no key.
4. **Facebook's own pages read layout and storage far more than anything else.**
   While browsing, `layout-probe` (6 734) and `storage` (3 190) are 87 % of the
   11 403 calls. Much of this is ordinary feed rendering (viewport size,
   element geometry), so the counts alone do not show fingerprinting. The
   `Storage.key` and `Storage.length` reads (167 and 177) do enumerate
   localStorage.
5. **On a third-party page, Meta's scripts read cookies, localStorage, the user
   agent, screen size, element geometry and low-entropy UA Client Hints, and
   nothing else on the fingerprint list.** `fbevents.js` reads
   `document.cookie` 42 times and writes it 5 times (the `_fbp` cookie),
   `navigator.userAgent` 33 times and `navigator.vendor` 11 times, screen
   width and height 12 times each, and `getBoundingClientRect` 21 times. It
   also reads `navigator.userAgentData`, `.brands` and `.platform` once each,
   on desktop Chrome. The `signals/config/<pixel-id>` script enumerates
   localStorage (`Storage.key` 36, `Storage.length` 4). `bundle/sdk.js` uses
   localStorage as a cache. There were no canvas, WebGL, audio or font reads,
   and Meta's scripts made 239 of the page's 22 221 calls.
6. **Chrome itself contacted Google during the sessions. These requests are not
   visible to the page.** `passwordsleakcheck-pa.googleapis.com` received one
   `POST /v1/...` in arm 2, the login: this is Chrome's leaked-password check
   on the submitted credentials. `content-autofill.googleapis.com` was
   contacted in every arm, not only at login: 2 in arm 1, 4 (plus 2 more under
   its own section) in arm 2, 1 in arm 3, 4 and 6 in the tiki.vn runs. These
   are Autofill's server queries for the forms on the page. Neither host is
   among the levers in `patches/sp7-phone-home.patch` today. Both are
   candidates for the SP7 phone-home work. (`chromewebstore.googleapis.com`
   `POST /v2/items/...:fetchItemSnippet`, once per session, is the Windows-only
   Web Store request already open from `2026-10-04-safe-browsing.md`.)

## 6. Comparison with camoufox

Camoufox's observer (`build-tester/observer/REPORT.md`,
`recon_fb_live.json`, `docs/observer/fb-tracking-recon.md` and the static
`docs/observer/fb-beacon-generation.md` in the camoufox repo) records from its
seven spoof hooks. Its counts are drain windows, not reads.

**What the Chromium observer sees that the Firefox one could not:**

- Surfaces that have no spoof hook. `deviceMemory` (14/168/590),
  `connection` and `NetworkInformation.*`, `serviceWorker`, `storage`, and
  layout probes are all rows here. Camoufox's REPORT names `deviceMemory`,
  `userAgentData` and `connection` as invisible to it. Firefox does not
  implement them at all, so on Firefox there is nothing to read. On Chrome they
  exist and Facebook reads them hundreds of times.
- UA Client Hints: `Navigator.userAgentData` on the landing page and from
  `fbevents.js`, and `WorkerNavigator.userAgentData` from workers.
- Workers: 46 and 61 worker calls in arms 2 and 3 (`WorkerNavigator.userAgent`,
  `deviceMemory`, `userAgentData`, `connection`). Camoufox's scope caveat lists
  workers as structurally blind.
- Script attribution: the per-script split of section 4. Camoufox separated
  Meta's reads only with a surrogate page and a dummy pixel id, and that page
  sent no `/tr` beacon and touched `navigator` once.
- Real read counts instead of active windows.

**Where the results agree:**

- `/ajax/bz` gating. Camoufox measured 15 at a fresh login and 0 of 379 and
  0 of 347 in established sessions. Here: 17 of 386 at login, 0 of 925 while
  browsing.
- The Pixel's small surface. The static analysis found no canvas, WebGL,
  timezone, language, `hardwareConcurrency`, `devicePixelRatio` or
  `navigator.platform` reads in `fbevents.js`. The live trace agrees for every
  member on that list that the observer covers. Screen width and height, user
  agent and cookies are read, as the static analysis says.
- Logged-out cookie names: camoufox `datr`, `dpr`, `fr`, `sb`, `wd`; here
  `datr`, `fr`, `sb`, `wd`.

**Where they differ:**

- UA Client Hints from the Pixel on desktop. The static analysis says the Pixel's
  `clienthint` plugin (`getHighEntropyValues` for model, platformVersion and
  fullVersionList) is gated to Android Chrome and never runs on desktop. The
  live trace agrees on the high-entropy call, with 0 from Meta's scripts, but
  `fbevents.js` does read `navigator.userAgentData`, `.brands` and `.platform`
  once each on desktop Chrome 154. That is a low-entropy read the static pass
  did not report.
- `fbevents.js` also reads `navigator.vendor` (11), `getBoundingClientRect`
  (21) and localStorage, and the `signals/config` script enumerates
  localStorage keys. None of these is in the static surface table.
- Logged-out WebGL. Camoufox's headless logged-out run recorded a WebGL
  window, under prefs that force WebGL on. Here the logged-out landing page made
  no WebGL call, and WebGL appeared only at login.

## 7. Not observable

The report prints the spec's fixed list. A silence on any of these says nothing:

- V8 built-ins: `Intl.*` (`resolvedOptions().timeZone`, `supportedLocalesOf`),
  `Date.prototype.getTimezoneOffset`, `Math`. Intl is phase 2;
  `getTimezoneOffset` stays blind.
- CSS `@media` rules in stylesheets (only `matchMedia` is seen).
- Font enumeration by layout measurement beyond the listed layout members.
- TLS/JA3, HTTP/2 framing, anything computed server-side.
- Named and indexed access (`localStorage.foo`, `navigator.plugins[0]`). This
  matters here: Facebook's localStorage reads through property syntax are not
  in the `Storage.getItem` counts.
- Values: every count above is a read, not a value.
- V8 fast API calls. About 100 canvas-2D and WebGL methods and setters have a
  `[NoAllocDirectCall]` fast path. Once V8 optimizes a call site, those calls
  skip the hooked binding callback and are not counted, so the canvas and WebGL
  draw and state counts here (the arm-2 render sequence, `drawArrays`, shader
  calls, style setters) are lower bounds. Read-outs and the text calls
  (`toDataURL`, `getImageData`, `readPixels`, `getParameter`, `measureText`,
  `fillText`, `font`) are not affected. A zero row stays a real zero: the
  first calls at any site run before V8 optimizes it, and those are counted.

The reports also contain rows from Chrome's own internal pages, which every
table above excludes: `chrome://omnibox-popup.top-chrome` (16 calls in every
run), `chrome://new-tab-page` (308 in arm 2, 308 and 284 in the arm-4 runs),
and the new-tab page's 7 Google requests (`www.gstatic.com`, `play.google.com`,
`ogads-pa.clients6.google.com`) under `(no site)`. Arm 1 opened its URL
directly and has no new-tab page section.

## 8. What this does not show

- One session per arm, one account, one host, one day. Nothing is replicated,
  and arm 3's two minutes of browsing are one sample.
- Arm 3's trace stopped after 58 s of a 116 s session, when the old filter's
  bulk filled the 200 MB buffer (section 2). Its observer counts describe the
  first minute of browsing only.
- Arm 3's zeros for WebGL, canvas and audio do not show that an established
  session is never fingerprinted. Arm 3 reused arm 2's profile, which had just
  run the full login-time fingerprint; Facebook can keep that result in
  localStorage or a cookie and skip recomputing it. An established session in
  a profile that never saw a login fingerprint (or one with storage cleared)
  would separate the two readings.
- One third-party page. tiki.vn's Pixel configuration (its `signals/config`
  and the events it fires) is the site's own; another site may load
  more Pixel plugins.
- The display was an RDP session for arms 2 to 4 and session 0 for arm 1. The
  counts hold, but the screen and GPU values Facebook saw were those
  sessions' values, not a physical monitor's. Facebook may also branch on
  them.
- Arm 1 was closed through an open debug port and one `Browser.close`. The page
  could not observe this before the close, but the port was open for the 30 s.
- Arm 2's profile visited other sites in the same session, and arm 3 inherited
  their cookies. The tables here exclude those sites, but Facebook's scripts
  ran in a profile that was not pristine.
- Logged-out Instagram and Threads (arm 1 already ran for both) and the other
  arms for those sites are not covered here.
- Nothing here says what Facebook does with the reads, or decodes the
  `/ajax/bz` payload. That stays out of scope (`docs/observer/followups.md`).

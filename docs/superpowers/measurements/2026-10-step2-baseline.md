# Step 2 baseline at 154: the fork against stock Chrome, layers 1 and 2

Roadmap step 2 (`plans/2026-10-02-long-term-roadmap.md`), built by
`plans/2026-10-04-step2-measurement.md` from
`specs/2026-10-04-step2-measurement-design.md`. Measured on 2026-10-04 on
the build box's Windows 10 host.

The baseline is `step2-154/rows.json` and `step2-154/tables.md` (run
`20261004-225915`). Before committing, the host's public IP, city and
coordinates were replaced by `0.0.0.0`, `<city>` and `<coord>`, and
Pixelscan's country and district by `<country> / <district>`. Screenshots and raw
detector text stayed on the host.

## 1. What was compared

| | control | fork |
|---|---|---|
| executable | `C:\Program Files\Google\Chrome\Application\chrome.exe` | `D:\camou-win\chromium\src\out\Release\chrome.exe` |
| version (file `ProductVersion`) | 154.0.8037.93 | 154.0.8037.93 |
| config | none | `camoucrome.gen` Windows identity, seed 1; the second linkability profile uses seed 2 |
| launch | `camoucrome.launch()` | `camoucrome.launch()`, plus the identity's `window`/`dpr` |

Both arms run through one client call, in both modes (`headed` and
`headless`), under the real sandbox and the host's Intel GPU. No arm gets
SwiftShader or `--no-sandbox`. The browser argv of the two arms, read from
`Win32_Process`, differs only by
`--window-size=1920,1152 --force-device-scale-factor=1 --accept-lang=en-US`
on the fork and by the profile directories. Stock Chrome on the host is held
at 154 (Google Update disabled), so the pin and the control share a
milestone, as step 2's precondition requires.

The headed column runs inside the SSH session, on a 1024×768 desktop nobody
sees. The fork claims a 1920×1200 screen and a 1920×1152 window there. The
window cannot be that large, so headed `win.outerMinusInner*` reads 892 and
459. That is this harness, not something a user on a real desktop would see.

The command, run in the client venv on the host while holding the build lock
(owner `step2`):

```
python measure_step2.py run [--null] [--plant ARG] [--fresh-seeds] [--two-colour]
python measure_step2.py compare RUN_A RUN_B
```

## 2. The preconditions refuse

- **Version.** A fork executable whose `ProductVersion` is `10.0.19041.3996`
  exits rc=1 with `precondition: fork is 10.0.19041.3996, the pin is
  154.0.8037.93`. No run directory is written.
- **Argv.** A copy of the runner that does not allow the planted argument
  exits rc=1 with `precondition, argv parity: fork only:
  --use-angle=swiftshader`. No other difference was reported, so the argv
  read works on both arms.

## 3. Each probe, seen RED first

A null run puts stock Chrome, unconfigured, in both arms. It sets the noise
floor. A planted run then adds one known difference to the fork arm.

| probe | null run (stock vs stock) | planted difference | RED seen |
|---|---|---|---|
| L1 oracle | 0 `unexpected` in either mode | `--disable-blink-features=WebShare`: `nav.share`, `nav.canShare` and `navProto` show as `unexpected` in both modes (`20261004-220622`) | yes |
| noise | 1 colour on both arms | `--two-colour`: fork reads 2 and 2 (`20261004-220913`) | yes |
| network | equal `ja4` `t13d1517h2_8daaf6152771_cb7bf5808d99`; only `net.ja3` differs (volatile) | `--ssl-version-max=tls1.2`: `ja4` becomes `t12d1212h2_d34a8e72043a_0d32fd8a6501` | yes |
| stability | control stable once volatile leaves are set aside | `--fresh-seeds`: fork `audioFp` changes, and in headed `canvas.shape` too (`20261004-221203`) | yes |
| linkability | two stock profiles share 230 of 234 leaves (presence) | none | n/a |
| detectors | 0 `unexpected` rows and 0 lines after calibration (two null runs, `20261004-223334` and `223840`) | WebShare off: CreepJS (`properties (83)`→`(81)`, its headless and Fuzzy hashes) and sannysoft (the `share`/`canShare` lines) see it. **BrowserScan and Pixelscan do not** (`20261004-224342`) | CreepJS and sannysoft only |

The two stability bugs the null runs caught before their RED counted:

- **One origin for both launches.** The page server took a new port per launch. Device IDs are keyed by origin, so stock's IDs changed between two launches of one profile.
- **Two leaves, not one.** Device ID and group ID were joined in one leaf, and stock keeps a device's `deviceId` (`909a1ad2…`) but draws `groupId` per session (`286c5739…` then `b5a5219e…`). They are now separate leaves.

Pixelscan's landing page measured nothing: the scan waits for a click, so both
arms read the same marketing text. The probe now loads `/fingerprint-check`,
which runs on load.

## 4. Volatile: what changes between runs of one binary

Each entry is in `step2_rows.VOLATILE` or `VOLATILE_LINES`, with its reason,
and each has a test.

- **Oracle.**
  - `err.stack` names the page server, whose port changes.
  - `navConnection.downlink` and `navConnection.rtt` are network estimates.
  - `voices` loads asynchronously, and stock's list differed between launches.
  - `mediaDevices.groupIds` is drawn per session.
- **Network.** `ja3` changes because Chrome permutes its extension order.
- **CreepJS.**
  - Rows: the WebRTC `candidate`, `type & base ip`, `rtt`, `stack` and `trap`.
  - Lines: timings, the WebRTC section and the status section.
- **sannysoft.** The stack-depth line.
- **BrowserScan.**
  - Clocks, the visit counter, CDN edge IPs and per-load hashes.
  - An AdSense "related links" text that the page appends to value lines. It is stripped as a suffix, from 36 phrases seen in the captures.

Two null runs of all six probes then agree:
`compare 20261004-223334-null 20261004-223840-null` → `0 rows disagree
outside VOLATILE`.

## 5. Three fork runs: the fork is not stable on three rows

`compare` across fork runs `224819`, `225315` and `225915` found rows that
changed between runs of the fork while the control's did not. They are
findings, kept out of VOLATILE:

| row | runs | what happened |
|---|---|---|
| WebGPU adapter (headed, stability) | 1 of 3 | in run 2, `gpu.*` was present in one launch of a profile and absent in the other. The control never did this |
| HEVC `canPlayType`/`isTypeSupported` (headless, stability) | 2 of 3 (and once in headed, `221203`) | the answer flips between two launches of one profile. Every other read was `["probably", true]`, as on the host |
| CreepJS `FP ID` / `Fuzzy` (headed) | 1 of 3 (run 1) | CreepJS reported `rendering: 0% rgba noise` and a different FP ID; runs 2 and 3 agree on `8800a54a…` |

So the roadmap's "two runs agree row for row" holds for the harness (the null
pair) and for runs 2 and 3. It fails whenever a run catches one of these fork
instabilities. The baseline is run 3.

## 6. Findings, fork against stock

This section covers every row the baseline labels `unexpected`, plus the
stability and detector observations above. Some `unexpected` rows are not
findings. These are CreepJS's `N% headless` and `N% like headless` rows, whose
names carry the score, so the label table cannot name them. They are
favourable to the fork and are listed under "What did not differ". Rows labelled `expected` are the identity's values, or
the fork's deliberate deviations from stock under the same driver:

- `nav.webdriver` (SP2);
- the pointer media queries of a Windows claim on a mouseless host;
- the identity UA, where stock headless says `HeadlessChrome`.

The full lists are in `step2-154/tables.md`.

1. **Farbling is visible on a solid fill.** A 64×64 canvas filled with one
   colour reads back **3** distinct colours on the fork, and a WebGL clear
   reads **5**. Stock reads 1 in both modes. Any page can do this test.
2. **Canvas noise has little entropy, and one hash ignores the seed.** Across
   8 launches with different seeds:
   - `canvas.text` was `9c3103de` in 7.
   - `canvas.shape` repeated `561c139d` for three different seeds.

   The two identities of the linkability run share `canvas.text`.
3. **Device IDs are empty on the fork, even after the grant.**
   - With camera and microphone granted, stock lists real `deviceId`s and `groupId`s.
   - The fork lists its claimed `audioinput`/`videoinput`/`audiooutput` with every ID `""`.

   That is a tell. It also means device-ID stability cannot be measured on the fork.
4. **No remote voices.** CreepJS counts 19 remote speech voices on stock and
   `unsupported` (0) on the fork.
5. **The fork is unstable across launches** on WebGPU, HEVC and a CreepJS
   rendering check (§5).
6. **Two identities on one host share 216–218 of 234 oracle leaves.** Among
   them:
   - the host's real GPU (`gpu.*`);
   - `canvas.text`;
   - fonts, codecs and permissions;
   - audio-context properties;
   - the window and navigator prototypes.

   They differ in `audioFp`, `canvas.shape`, time zone, screen, cores, DPR
   and media devices.
7. **BrowserScan shows a "WebGL exception" on the fork**, and lists 95 fonts
   where stock lists 132.
8. **Pixelscan says "Masking detected" and "Timezone spoofed" for the fork**
   (stock: "No masking detected"). The identity claims `America/Chicago` from
   an IP that geolocates elsewhere, which is the proxy-and-IP layer the
   project leaves to the user. A run behind a proxy in the claimed region is
   what would tell whether masking is flagged for anything else.

What did not differ:

- **Network.** `ja4`, `http2.akamai_fingerprint`
  (`1:65536;2:0;4:6291456;6:262144|15663105|0|m,a,s,p`) and the header-name
  order are equal in both modes. The fork inherits the network fingerprint, as
  expected.
- **Rule 2.** `windowKeys` (237), `windowNames` and `navProto` are equal
  between the fork under an identity and stock. Rule 2 is now measured on
  `chrome.exe`, which `verify_host_oracle`'s probe marker had prevented.
- **HEVC.** On the GPU host, the fork answers HEVC like stock
  (`["probably", true]`) in every read outside the flips of §5. Backlog item 3
  was measured as `["", false]` under SwiftShader. With the real GPU, the
  remaining issue is the instability, not the claim.
- **Detectors that favour the fork.** In every case the stock arm runs under
  the driver, and the fork hides that:
  - BrowserScan says stock "appears to be controlled by a robot" and does not say it of the fork;
  - CreepJS rates stock 33% (headed) and 100% (headless) headless, and the fork 0%;
  - sannysoft fails stock headless on `CHR_MEMORY` and `HEADCHR_UA`;
  - Pixelscan says "Automated behavior detected" of stock and "No automated behavior detected" of the fork.

## 7. The public IP is in WebRTC, on both arms

CreepJS's WebRTC section lists a server-reflexive candidate carrying the
host's public IP, on stock and fork alike. That is Chrome's WebRTC
behaviour without a proxy or a WebRTC policy. It is the out-of-scope
network layer (roadmap "Out of scope": proxy and IP), and it is why the
baseline was scrubbed.

## 8. What this does not cover

- Layer 3 (commercial anti-bot) is backlog item 1.
- BrowserScan and Pixelscan did not see the planted WebShare difference.
  They do report differences (§6), but only for what those sites happen to
  test. An absence of difference there is weak evidence.
- Headed runs on an invisible SSH desktop (§1).
- Voices are VOLATILE (stock's list loads asynchronously), so the linkability
  list leaves them out. Whether two fork identities share a voice list is not
  measured here.
- The 156 re-pin must recapture this baseline on 156: the control and the
  fork both move.

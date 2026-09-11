# The B1 to-do list on the `chrome` binary, measured

Roadmap B1's cell listed what a `chrome` build would unblock. The build has
existed since 2026-09-10; this closes the list, with reference data from
stock Google Chrome **153.0.8010.36** on the build box's Windows 10 host
(the pinned tag), reached over `ssh buildpc` (`scripts/winhost.py`:
PowerShell, temp profiles, `--dump-dom` headless; a .NET websocket CDP
client on the host for headed runs, because `--dump-dom` does nothing
headed and the ssh mux master refuses port forwards).

## 1. `window.chrome` shape (SP2 §4.7)

`scripts/capture_chrome_object.py` records the recursive property tree of
`window.chrome` (own names, kinds, descriptor flags, function
length/name/`toString`; depth 4; never the timing values) plus
`navigator.plugins`/`mimeTypes`/`pdfViewerEnabled` and the `loadTimes()`/
`csi()` key sets, into `baselines/chrome-8010-stock-window-chrome.json`
(headless and headed). `scripts/verify_chrome_object.py` diffs the fork.

| row | result |
|---|---|
| O1 fork headless tree == stock headless tree | PASS, empty diff: top level `app`, `csi`, `loadTimes`, 32 properties |
| O2 plugins / mimeTypes / pdfViewerEnabled == stock | PASS: 5 PDF plugin entries (`PDF Viewer`, `Chrome PDF Viewer`, `Chromium PDF Viewer`, `Microsoft Edge PDF Viewer`, `WebKit built-in PDF`), 2 mime types, `pdfViewerEnabled true` |
| O3 `loadTimes()` (13 keys) / `csi()` (4 keys) key sets == stock, `csi().pageT >= 0` | PASS |
| O4 RED: `content_shell` (no `window.chrome`) against the same baseline | PASS, non-empty diff |

Stock headed vs headless: **identical** tree and plugin list — no headless
tell in this surface (B7 gets nothing from here). `chrome.runtime` is
absent on a plain page in stock 153 too (it appears only where an
extension messaging channel exists), so SP2's "over-completeness" worry
does not arise. `loadTimes().startLoadTime <= firstPaintTime` is false on
both (firstPaintTime 0 before paint on a file/loopback page) — a value,
not a shape.

## 2. `navigator.plugins` / `mimeTypes` / `pdfViewerEnabled`

Measured, not keyed: the fork equals stock in every field (§1 O2), headed
equals headless. Closed with no key, as the roadmap's "measure first"
asked.

## 3. `Sec-CH-UA*` / `userAgentData` end to end

Already verified before this pass: SP1a Task 8 against `chrome` (34/34
on M153 after the pristine baseline recapture, `verify_sp1a_chrome.py`,
sp6a-version-honesty doc). The roadmap sentence "unverified end-to-end"
was stale and is corrected; the verify is in the final regression sweep
(§6).

## 4. `headless_shell`'s `HeadlessChrome` token (SP2 D4 residual)

Closed by decision: `headless_shell` is neither shipped nor tested.
`package.py` targets `//chrome:chrome` only and the launcher contract's
executable is `chrome`. No code.

## 5. SP7 on chrome: `X-Client-Data` on a Google host

The header rides only on a profile that already holds a variations seed
with ids, so a fresh profile proves nothing. **Stock RED, constructed** on
the Windows host (`winhost.cdp_headers`, two launches on one temp
profile, headed, `Network.requestWillBeSentExtraInfo`):

| launch | request to `https://www.google.com/generate_204` | `x-client-data` |
|---|---|---|
| 1 (fresh profile, 25 s) | 1 | absent |
| 2 (same profile, 15 s) | 1 | **present** |

The fork, same two-launch shape on the box (`verify_sp7_phonehome.py`
P4): see the row in the ledger and §6 — expected absent both times with
no request to `clientservices.googleapis.com` / `update.googleapis.com`.

## 6. Regression sweep

Recorded in `.superpowers/sdd/progress.md` for this date: driver 6 rows,
launcher L1–L5, generator, d-pointer-touch, sp1a chrome, coherence runner.

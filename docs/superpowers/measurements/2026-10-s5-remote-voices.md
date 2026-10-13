# S5: remote speech voices — measurements

Spec: `specs/2026-10-13-s5-remote-voices-design.md`. Plan: `plans/2026-10-13-s5-remote-voices.md`.

## 1. Data

**Stock Chrome 155 on the owner's Mac, 2026-10-13.** This ran on stock Chrome with no fork; it was a throwaway probe, one launch online and one behind a dead proxy.

**What it listed.** `speechSynthesis.getVoices()` gave **210 voices**:
- 191 local voices. Their names and `lang` equal `settings/voices.json`'s macOS list, in order.
- 19 Google voices, `localService: false`, `default: false`, `voiceURI == name`. In order, `name` and `lang`, they equal the 19 in `baselines/chrome-8037-stock-oracle-windows.json` (stock 154 on the Windows host, headless and headed).

**When it arrived.** All 210 came in one `voiceschanged`, 143–191 ms after load, online and offline alike. The list is static, not fetched.

So the remote table is one list shared by every Chrome-branded OS build, and the committed macOS list needs no recapture.

## 2. Host: stock Chrome 154, session 1

Filled by Task 1.

## 3. WSL rows (`verify_voices_remote.py`)

Filled by Tasks 3 and 4.

## 4. Host: fork against stock, session 1

Filled by Task 5.

## 5. Regressions

Filled by Tasks 4 and 5.

## 6. Gaps

Filled by Task 6.

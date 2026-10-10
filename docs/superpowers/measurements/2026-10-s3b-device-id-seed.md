# S3b: device ids that round-trip — measurements

Spec: `specs/2026-10-10-s3b-device-id-seed-design.md`. Plan: `plans/2026-10-10-s3b-device-id-seed.md`.
Pin 154.0.8037.93. Box branch `camoucrome/s3b` cut at `camoucrome/main` = `4b5fdddcd8`.

## 1. Setup

- Box `~/chromium/src` switched to `camoucrome/s3b` at `4b5fdddcd8`: 40 commits above the pin, tree clean, lock free.
- Baseline build `out/Default` (`content_shell components_unittests`) on that commit: `Build Succeeded: 263 steps`.
  Not a no-op: W3 `cp -r` of `additions/camoucfg` touched the mtimes of the camoucfg files (content identical, 0 drift lines).
  Far from thousands, so the mtimes are sound.

## 2. RED on the main build
## 3. Browser: the seed fold and phantom output (Task 2)
## 4. Renderer: no id rewrite (Task 3)
## 5. Windows build and hashes (Task 4)
## 6. Host rows (Task 4)
## 7. Step 2 stability (Task 4)
## 8. Gaps

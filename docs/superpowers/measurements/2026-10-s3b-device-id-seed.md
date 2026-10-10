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

Mutant (W13: raw audiooutput snapshot emptied, `verify_s3b_phantom_out.py`): the mutant is live (stock lists 0 audiooutput, exit 1 not 2), `0/2 FAIL`:
`S3-M1 sink=NotFoundError`; `S3-M2 ac=state=suspended sinkMatch=false error=true`.
Mutant off: rebuilt, `grep -c S3B-MUTANT` = 0, tree clean.

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

## 3. Browser: the seed fold and phantom output (Task 2)
## 4. Renderer: no id rewrite (Task 3)
## 5. Windows build and hashes (Task 4)
## 6. Host rows (Task 4)
## 7. Step 2 stability (Task 4)
## 8. Gaps

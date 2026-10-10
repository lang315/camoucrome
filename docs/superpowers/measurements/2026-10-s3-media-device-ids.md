# S3: enumerateDevices() ids after a grant, on a host without the claimed devices

Spec: `specs/2026-10-10-s3-media-device-ids-design.md`. Plan: `plans/2026-10-10-s3-media-device-ids.md`.

## 1. Setup

- Box checkout `~/chromium/src` moved off `camoucrome/main` onto the new branch `camoucrome/s3`, cut at `e585e8b5ce` (owner OK 2026-10-10). The branch holds 39 commits above the pin `f89f3a4363`.
- `camoucrome/main` is not moved until landing (Task 6).
- No-op build check (label `s3-base`, `autoninja -C out/Default content_shell components_unittests`): `Build Succeeded: 0 steps`. `out/Default` is the CI build of `e585e8b5ce`, so it is the RED build.

## 2. What WSL has

Stock content_shell under `--use-fake-ui-for-media-stream` (no fake devices) lists:
- `audioinput`: 2 entries (one device entry, one entry with an empty label), no empty ids.
- `audiooutput`: 2 entries, same shape.
- `videoinput`: none.

So `REAL_KINDS = [audioinput, audiooutput]` and `PHANTOM_KINDS = [videoinput]`: WSLg exposes a mic and a speaker, no camera. This is the spec's "host with one real input kind".

## 3. RED

Run on the unchanged `e585e8b5ce` build, `out/Default` (0 steps), script commit `6b40b16`. Result `2/8 FAIL`, rc=1.

| Row | Verdict | Note |
|---|---|---|
| S3-1 | FAIL | grant lists only the two real kinds; no phantom camera id |
| S3-2 | FAIL | no phantom group ids |
| S3-3 | PASS | guard: 1 entry per kind, all ids/groups/labels `""` without a grant |
| S3-4 | FAIL | kinds equal across the grant: pre has all three kinds, post lacks `videoinput`. RED here because WSL has a real mic and no camera: the claimed camera vanishes after the grant (the S3 bug) |
| S3-5 | FAIL | `ids equal=True` is vacuous on main (no phantom devices exist), so the persistent-id question stays open for Task 3 |
| S3-6 | FAIL | 0 ids on origin A and on origin B |
| S3-7 | FAIL | no phantom camera capabilities |
| S3-8 | PASS | guard (rule 5): `{}` config shape equals stock shape |

Only S3-3 and S3-8 are guards.

## 4. GREEN per task

## 5. Windows hashes and build

## 6. Host rows

## 7. Step 2 row

## 8. Gaps

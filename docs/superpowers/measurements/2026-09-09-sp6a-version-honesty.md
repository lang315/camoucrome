# SP6a: the pin's version against Chrome stable (2026-09-09)

The roadmap's A2 #4 assumed the pin was *old* — "Chromium rolls every four
weeks and the fork's UA claims the real version, so an old pin is a page-visible
tell". Measured, the tell points the other way.

## 1. Measured

| | value | source |
|---|---|---|
| pin `0e8d4a9268` `chrome/VERSION` | `154.0.8026.0` | `git show` on the box |
| pin date | 2026-08-26, `main` | `git log` |
| Chrome stable, Linux, 2026-09-09 | `153.0.8010.36` (M153, `507c6ee3e2f3`) | chromiumdash `fetch_releases` |
| M153 branch | `8010`, branch point `86cee6df69e0` | chromiumdash `fetch_milestones` |
| M154 branch | `8037`, branch point `e10b20e60f16` — beta, not yet stable | same |

`8026` sits between the M153 branch point (`8010`) and the M154 branch point
(`8037`): a `main` snapshot that only Dev/Canary channel builds ever carried.
The fork's `Sec-CH-UA-Full-Version-List` and `navigator.userAgentData
.getHighEntropyValues(['fullVersionList'])` therefore report
`154.0.8026.0` — a build number no stable or beta user has. Not old: **never
shipped**. The reduced UA (`Chrome/154.0.0.0`) is a version a page only sees
from Dev/Canary at this date.

## 2. Decision (closes the SP6 §4.2 open question)

- **Pin to the current stable *tag*, not a branch head and not `main`.** The
  branch head (`refs/branch-heads/8010`) carries commits past the last
  shipped release, so its `chrome/VERSION` is a PATCH number no user runs
  yet either. The tag `153.0.8010.36` is what stable users report.
- **Refresh per milestone** (every ~4 weeks, when chromiumdash's stable
  milestone changes): rebase onto the newest stable tag of the new
  milestone. Patch-release re-pins within a milestone are optional and
  near-conflict-free (security cherry-picks).
- **A5 must assert** at cut time that `chrome/VERSION` equals a version
  chromiumdash lists as shipped on the stable channel. Not built today.
- `upstream.env` records hash **and** tag name (spec §4.2 asks for the branch
  alongside the hash).

## 3. The rebase drill (SP6 §6.7) — recorded below as it runs

Target: tag `153.0.8010.36` = `507c6ee3e2f3b2ca0e660547e5b9ea4820c67f4c`
(`chrome/VERSION` at the tag reads `153.0.8010.36`, confirmed with `git show`
after a `--depth=1` fetch of the tag; `.git` grew 1.6G → 1.7G).

**Prediction** (`git diff --stat 0e8d4a9268 153.0.8010.36 -- <the 70 files
the stack touches>`): 20 files changed upstream, +257/−556. Conflict
candidates are only those 20; the other 50 apply by construction.

**Drill** (`drill.sh`: worktree at the tag, `patches/series` order,
`git apply --3way`, commit per patch with the stem subject):

| result | patches |
|---|---|
| clean | 25 of 26 — including every one of the 19 whose files upstream touched but whose hunks did not overlap |
| conflict | `media-ii-track.patch`, 1 file, 1 hunk: the include block of `media_stream_track_impl.cc`. Upstream removed `wtf/text/format.h` (commit replaced WTF `Format()` with `String::Format`); our hunk added `weborigin/security_origin.h` on the adjacent line. Resolved by keeping ours and dropping the removed include; the patch's own added code calls no `Format()`. 0 conflicting lines of *logic* |

Standing rebase item from metric-jitter: `text_metrics.cc` / `.h` are
unchanged between the two bases (`git diff --stat` empty), so
`MirroredBaseline` still mirrors `GetFontBaseline` byte-for-byte; nothing to
re-diff.

Baseline for §6.7's trend rule: **26 patches, 70 files, 1 conflicting file,
1 conflicting hunk, 0 conflicting logic lines** for a 3-week base move
(2026-08-26 `main` → M153 stable tag). Result branch `camoucrome/main-8010`
(26 commits above the tag) on the box; `camoucrome/main` (the 0e8d branch)
kept until the sweep on the new base passes.

## 4. Base switch, build, sweep (2026-09-10)

- `~/chromium/src`: `check_checkout_sync` PASS first, then `git checkout -f
  --detach 153.0.8010.36`, `gclient sync --revision src@507c6ee3…`
  (three 560 s chunks), `gclient runhooks`; `chrome/VERSION` reads
  `153.0.8010.36`, tree clean.
- Pristine `content_shell` from scratch: ~41500 steps, about 4 h on 16 cores
  (a base move plus toolchain roll invalidates everything). Stock baseline
  captured from it: `baselines/content_shell-8010-stock-ua.json` — 235
  window keys, 81 navigator prototype props. Against the committed 0e8d
  baseline (recaptured from the fork's own build) the only difference is
  `queryLocalFonts`, which sp4-fonts removes on purpose; the 13 Protected
  Audience members are present in stock M153 too, so the field-trial
  measurement's open question ("does real Chrome expose them?") is answered
  for the stock binary: yes, with the testing config compiled out.
- `git checkout camoucrome/main-8010`, incremental rebuild: 164 steps.
- Sweep, content_shell rows (33 scripts; the 5 that need `chrome` run after
  its rebuild): **33 pass**. `verify_webrtc_ii_fakeip.py` fails as it must —
  it is the RED record of the rejected fake-local-IP slice (its header says
  so) and has been excluded from every sweep since 2026-09-07.
- Export from `camoucrome/main-8010` into the repo branch `rebase/8010`: 10
  of 26 patches re-cut. Every diff is an `index` line or a hunk offset except
  `media-ii-track.patch`, which now adds `security_origin.h` without the
  upstream-removed `wtf/text/format.h` beside it.

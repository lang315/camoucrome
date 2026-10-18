# GitHub history before the 2026-10-18 recreate

The repository was deleted and recreated on 2026-10-18 to remove host-identifying data
(spec `docs/superpowers/specs/2026-10-18-public-repo-scrub-design.md`). This file keeps its
40 pull requests and 526 workflow runs. Bodies are verbatim, apart from the scrub
rules, removed session links and commit ids mapped to the rewritten history. Runs keep no logs.
PR numbers below are the old ones; the recreated repository numbers from 1 again.

| PR | title | branch | state | opened (UTC) | merged (UTC) | merge commit |
|---|---|---|---|---|---|---|
| [#1](#pr-1) | docs: long-term roadmap (steps to first release, re-pin commitment, backlog) | `docs/long-term-roadmap` | merged | 2026-10-02T03:26:12Z | 2026-10-02T03:28:32Z | 5c1e19dac9 |
| [#2](#pr-2) | Step 0 tools: atomic rebuild_branch.sh, repin.py, runner hardening record | `step0/tools` | merged | 2026-10-02T07:41:31Z | 2026-10-02T17:03:50Z | 200276a053 |
| [#3](#pr-3) | repin: Chrome stable 154.0.8037.93, and step 0 closed | `repin/8037` | merged | 2026-10-02T17:05:25Z | 2026-10-03T01:46:17Z | 3715b92f4b |
| [#4](#pr-4) | feat(verify): lib_shell resolves its binaries and temp dir from the environment | `step1/lib-shell-paths` | merged | 2026-10-03T02:31:03Z | 2026-10-03T02:33:16Z | 3cbc314684 |
| [#5](#pr-5) | refactor(verify): one definition of where chrome is | `step1/one-chrome-path` | merged | 2026-10-03T02:51:56Z | 2026-10-03T02:57:13Z | fefba81925 |
| [#6](#pr-6) | refactor(verify): fold the eleven scripts' shared layout block into lib_shell.layout() | `step1/one-path-block` | merged | 2026-10-03T03:08:33Z | 2026-10-03T06:14:08Z | aeb79dc514 |
| [#7](#pr-7) | Step 1 first slice: a Windows verify substrate on the build that already exists | `step1/windows-substrate` | merged | 2026-10-03T07:16:11Z | 2026-10-03T07:18:34Z | b8b9ca7875 |
| [#8](#pr-8) | Windows: the renderer under the real sandbox | `step1/sandboxed-launch` | merged | 2026-10-03T07:26:40Z | 2026-10-03T07:29:27Z | 6bdb881168 |
| [#9](#pr-9) | Windows: worker parity under the sandbox | `step1/windows-worker-parity` | merged | 2026-10-03T07:33:12Z | 2026-10-03T07:35:19Z | fe5c774a47 |
| [#10](#pr-10) | Windows: CAMOU_EXE measured in both directions | `step1/windows-camou-exe` | merged | 2026-10-03T07:36:42Z | 2026-10-03T07:40:06Z | ec6366c33c |
| [#11](#pr-11) | Windows: crash dumps carry the identity's config (no upload) | `step1/windows-crashpad` | merged | 2026-10-03T07:46:57Z | 2026-10-03T07:57:52Z | e7eb752267 |
| [#12](#pr-12) | Windows: the Python client runs, sandboxed, with a chunked identity | `step1/windows-python-client` | merged | 2026-10-03T08:21:22Z | 2026-10-03T08:37:58Z | 2b02c3d785 |
| [#13](#pr-13) | Clients: crash dumps go to a temp dir each launch removes (backlog item 5) | `step1/windows-crash-dumps` | merged | 2026-10-03T08:32:13Z | 2026-10-03T08:42:55Z | f66a9c636e |
| [#14](#pr-14) | Verify runs remove the temp profiles they create; CLAUDE.md names the Node client | `step1/cleanup-temp-dirs` | merged | 2026-10-03T09:06:36Z | 2026-10-03T09:41:55Z | 50fed5deda |
| [#15](#pr-15) | Clients remove the temp profile and crash dir once close() returns; commit the Go probe | `step1/close-removes-after-exit` | merged | 2026-10-03T09:22:17Z | 2026-10-03T09:42:00Z | ae9a720ef8 |
| [#16](#pr-16) | Go and Node clients on Windows: probes read Win32_Process, run sandboxed, take a file config | `step1/windows-go-node` | merged | 2026-10-03T09:35:29Z | 2026-10-03T09:42:15Z | 52fffdb146 |
| [#17](#pr-17) | feat(client): a kept profile keeps its seeds | `step3/profile-seeds` | merged | 2026-10-03T12:26:29Z | 2026-10-04T02:32:29Z | c20d714da5 |
| [#18](#pr-18) | feat(box): one build at a time across the WSL checkout and the Windows tree | `step1/build-lock` | merged | 2026-10-03T12:29:09Z | 2026-10-04T02:28:05Z | 93679d9971 |
| [#19](#pr-19) | docs: settle the release gates -- MPL-2.0, codecs shipped, unsigned, acceptable use | `step3/release-gates` | merged | 2026-10-03T12:30:32Z | 2026-10-04T02:36:50Z | 3c9f44da4f |
| [#20](#pr-20) | feat(crash): the crashpad handler never writes a report | `step1/crashpad-no-dumps` | merged | 2026-10-03T22:33:21Z | 2026-10-04T02:23:12Z | 2c34cda501 |
| [#21](#pr-21) | docs: drop the acceptable-use statement, move the codec notice to the README | `step3/acceptable-use-review` | merged | 2026-10-04T03:01:49Z | 2026-10-04T03:23:15Z | ff2c4d3f6e |
| [#22](#pr-22) | Step 1 finished on Windows: named verify set, fonts on a Windows host, audio service, host oracle | `step1/windows-verify-set` | merged | 2026-10-04T05:03:35Z | 2026-10-04T08:10:21Z | a9d6c93688 |
| [#23](#pr-23) | docs(readme): bring the status up to step 1 finished on Windows | `docs/readme-step1` | merged | 2026-10-04T08:18:22Z | 2026-10-04T09:01:32Z | a4d730b58e |
| [#24](#pr-24) | Safe Browsing off by default (backlog 4); P4 and netlog harness fixes; Blink relink timed | `backlog4/safe-browsing` | merged | 2026-10-04T12:05:00Z | 2026-10-04T13:04:00Z | e37221f33b |
| [#25](#pr-25) | docs(CLAUDE.md): the box checkout has one branch now | `docs/box-branches` | merged | 2026-10-04T13:34:02Z | 2026-10-04T13:37:55Z | 6a51b95c91 |
| [#26](#pr-26) | Step 2: measurement layers 1 and 2, 154 baseline | `step2/measurement` | merged | 2026-10-04T16:33:29Z | 2026-10-04T22:56:55Z | d655afb0f5 |
| [#27](#pr-27) | S1+S2: canvas noise redesign (draw-time text offset, edge-only readback noise) | `s1/canvas-noise` | merged | 2026-10-05T16:08:59Z | 2026-10-05T23:17:23Z | 9abceabff3 |
| [#28](#pr-28) | S2b: patch-keyed canvas noise and per-pixel eligibility | `s2b/canvas-noise` | merged | 2026-10-06T15:04:35Z | 2026-10-07T02:32:35Z | 01b7376e9a |
| [#29](#pr-29) | Tracking observer (phase 1 + 1c) and facebook recon | `worktree-tracking-observer` | merged | 2026-10-07T06:39:56Z | 2026-10-07T07:15:15Z | ba1050c368 |
| [#30](#pr-30) | feat(observer): count V8 fast API calls | `worktree-observer-fastcall` | merged | 2026-10-08T13:08:23Z | 2026-10-08T23:57:28Z | c2755126cb |
| [#31](#pr-31) | S2c: canvas noise cost and WebGL reads (flush-time mask, regional getImageData, framebuffer reads) | `s2c/canvas-cost` | merged | 2026-10-09T00:03:36Z | 2026-10-10T01:14:37Z | 42defd43de |
| [#32](#pr-32) | S3: media device ids after a grant (phantom enumerate entries) | `s3/media-device-ids` | merged | 2026-10-10T06:30:34Z | 2026-10-10T06:35:26Z | 9771c12e11 |
| [#33](#pr-33) | S3b: media device ids that round-trip (seed folded into Chrome's HMAC) | `s3b/device-id-seed` | merged | 2026-10-10T10:28:13Z | 2026-10-12T12:27:34Z | ff71e9e1dc |
| [#34](#pr-34) | docs(observer): settle the 1b clone-to-JSON question | `docs-observer-1b-clone-json` | merged | 2026-10-12T12:38:19Z | 2026-10-12T15:46:04Z | 69dda6ba74 |
| [#35](#pr-35) | fix(d-pointer-touch): add the camoucfg dep to core/exported (observer follow-up A) | `fix/d-pointer-touch-dep` | merged | 2026-10-12T15:31:14Z | 2026-10-12T15:34:31Z | 6fda3cc724 |
| [#36](#pr-36) | observer: Intl built-in counts via V8 runtime call stats (phase 2) | `observer-d-intl-rcs` | merged | 2026-10-12T18:37:53Z | 2026-10-17T02:56:52Z | 8a31d86ad7 |
| [#37](#pr-37) | S5: Chrome's Google voices with stock's speak() shape (remote voices) | `s5/remote-voices` | merged | 2026-10-13T12:00:21Z | 2026-10-17T02:56:14Z | 645292d50f |
| [#38](#pr-38) | step2b: session-0 GPU gate for host harnesses, 20 detector pages, fork-at-main baseline in session 1 | `step2b-detectors` | merged | 2026-10-14T00:53:05Z | 2026-10-17T02:59:08Z | ec4863378b |
| [#39](#pr-39) | SP2c: humanized wheel — CDP mouseWheel as Windows notches | `worktree-sp2c-humanized-wheel` | merged | 2026-10-17T11:19:43Z | 2026-10-18T01:40:07Z | 67e2097dc0 |
| [#40](#pr-40) | Observer: automated facebook recon (observe-auto, arms 1 and 3) with a calibrated baseline | `e-fb-auto` | open | 2026-10-18T01:42:32Z |  |  |

<a id="pr-1"></a>
## #1 docs: long-term roadmap (steps to first release, re-pin commitment, backlog)

`docs/long-term-roadmap` into `main`, opened 2026-10-02T03:26:12Z, merged 2026-10-02T03:28:32Z.

## Summary

Adds `docs/superpowers/plans/2026-10-02-long-term-roadmap.md` and points `CLAUDE.md` "Read first" at it. Docs only; no code, patch or settings change.

The roadmap has four concrete steps to a first release, a standing re-pin commitment, and a ranked backlog after the release:

| Step | Content | Rough size |
|---|---|---|
| 0. Re-pin and safety | Move to current stable, fix `rebuild_branch.sh`, recovery drill, runner hardening | 1–2 weeks |
| 1. Windows foundation | Windows edit loop, `lib_shell` on Windows, clients, a named verify set on `chrome.exe` | 4–6 weeks |
| 2. Measurement, layers 1 and 2 | Host oracle and public detectors, with a like-for-like stock control | 2–3 weeks |
| 3. First release | Windows flagship plus Linux beta, after the release gates (codec licensing, LICENSE, signing, acceptable use) | 2–3 weeks |

Owner decisions it rests on (2026-10-02): product first, then depth; the user is an automation developer running many identities on one machine; Windows flagship with Linux as a labelled beta; measurement before new spoofing work, with commercial anti-bot measurement after the first release.

## How it was reviewed

Four independent review agents (feasibility, anti-detection, product, strategy) critiqued the first draft; all four returned "sound with changes". The draft was then rewritten. Changes that came from the review:

- Re-pin moved from a late phase to step 0 and made a standing commitment.
- Codec licensing and LICENSE added as release gates.
- Verification target fixed as `chrome.exe`; Windows foundation resized from 2–4 to 4–6 weeks.
- Stock control must run through the same client as the fork; no aggregate detector score.
- Commercial anti-bot results published at vendor level only.

## Evidence

Facts the roadmap states, checked on 2026-10-02:

```
$ chromiumdash fetch_milestone_schedule (mstone, stable_date)
154 2026-09-22
155 2026-10-06
156 2026-10-20
157 2026-11-03
$ chromiumdash fetch_releases?channel=Stable&platform=Windows  ->  154.0.8037.98
$ wc -l < patches/series            ->  32
$ ls LICENSE*                       ->  no matches found
$ grep '"license"' client/node/package.json  ->  "license": "MPL-2.0"
$ grep -n OPEN settings/build-args.gn
25:# --- DISTRIBUTION LICENSING: OPEN, deliberately (SP7 D2 part 2) ---
$ ls scripts/verify_*.py | wc -l    ->  50
$ grep -l lib_shell scripts/verify_*.py | wc -l  ->  41
$ grep -n 'SHELL =' scripts/lib_shell.py
28:SHELL = os.path.expanduser("~/chromium/src/out/Default/content_shell")
```

Not verified: the claim that clients redraw seeds on every launch rests on `settings/launcher.json` (`per_instance_seeds`, `persistent_context: true`); the client code path was not exercised.

CI: the `checks` workflow runs on this PR; `build-verify` does not apply (no change-set file touched).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

<a id="pr-2"></a>
## #2 Step 0 tools: atomic rebuild_branch.sh, repin.py, runner hardening record

`step0/tools` into `main`, opened 2026-10-02T07:41:31Z, merged 2026-10-02T17:03:50Z.

## Summary

First part of roadmap step 0 ("re-pin and safety"), executed from `docs/superpowers/plans/2026-10-02-step0-repin-and-safety.md` (added here).

- **`scripts/rebuild_branch.sh` is atomic.** It builds on a temporary branch and renames it only when every patch has landed. A failure or a signal before the rename leaves no branch and no worktree, so a failed run can be repeated. A third argument names the branch. It refuses a relative worktree path and an existing worktree directory.
- **New `scripts/repin.py`**: `target` (newest Windows Stable version from chromiumdash), `check <version>` (exit 1 unless it shipped on Stable), `retarget <tag> <rev>` (rewrites `upstream.env` last, renames the baselines named after the old build or revision, rewrites those literals in `scripts/*.py`).
- **Runner hardening on the build box**, recorded in `docs/superpowers/measurements/2026-10-repin.md`: `lang` has no sudo, WSL interop and `/mnt` automount are off, the runner is re-registered on the recreated repository.
- Both new test files run in `checks`.

Not in this PR: the re-pin itself, the recovery drill and the runbook (plan Tasks 4 to 6).

## Evidence

### `rebuild_branch.sh` (10 tests)

RED, the new tests against the script as it was on `main`:

```
$ python3 -m pytest -q scripts/test_rebuild_branch.py     (original script)
8 failed, 2 passed
```

The failures are the defects: the branch is left behind after a failing patch (`['camoucrome/main', 'main'] != ['main']`), the third argument is ignored, a relative worktree path is accepted, a series without a trailing newline drops its last patch, and a signal leaves the half-built branch.

GREEN:

```
$ python3 -m pytest -q scripts/test_rebuild_branch.py
10 passed
```

The post-rename case has its own test: a wrapper `git` sends SIGTERM to the script right after `branch -m` succeeds. Against the previous revision that test failed (the finished worktree was removed); now the branch and worktree survive and the script exits non-zero.

Signal tests repeated: 150/150 in the foreground and 150/150 as a background job, slowest run 1.33 s.

### `repin.py` (7 tests)

```
$ python3 -m pytest -q scripts/test_repin.py              (before the tool existed)
ModuleNotFoundError: No module named 'repin'
$ python3 -m pytest -q scripts/test_repin.py
7 passed
$ python3 scripts/repin.py target; echo exit=$?
155.0.8059.26
exit=0
$ python3 scripts/repin.py check 155.0.8059.26; echo exit=$?
155.0.8059.26: shipped on Windows Stable
exit=0
$ python3 scripts/repin.py check 154.0.8026.0; echo exit=$?
154.0.8026.0 is not listed as shipped on Windows Stable
exit=1
```

`154.0.8026.0` is the Dev-only build number of the project's first pin, so the third command is the RED case.

A dry run of `retarget` on a scratch copy of the real `scripts/`, `baselines/` and `upstream.env` left no old-pin literal in `scripts/*.py`, made no false match, and did not rename `chrome-0e8d4a9268-*`, `chrome-7922-*` or `content_shell-sp0-*`.

### The whole `checks` pytest line, locally

```
$ python3 -m pytest -q client/python/tests scripts/test_package.py scripts/test_fonts.py scripts/test_capture_webgl_profile.py scripts/test_rebuild_branch.py scripts/test_repin.py; echo exit=$?
78 passed
exit=0
$ for s in scripts/*.sh; do bash -n "$s"; done; echo exit=$?
exit=0
```

### Runner hardening (as user `<user>` on the box)

| Check | Before | After |
|---|---|---|
| `sudo -n true` | rc 0 | rc 1, "a password is required" |
| `ls /mnt/c` | Windows directories | 0 entries |
| `cmd.exe /c ver` | prints the Windows version | "command not found", rc 127 |
| Executing a real PE (`whoami.exe`) | n/a | refused: `UtilAcceptVsock:271: accept4 failed 110` |
| `autoninja -C out/Default content_shell` | n/a | `Build Succeeded: 0 steps`, rc 0 |
| `verify_review_2026_09_24.py` | n/a | `12/12 ALL_PASS`, rc 0 |

`build-verify` on `main` on the hardened box, every step green: https://github.com/lang315/camoucrome/actions/runs/36974876383

## How it was reviewed

Each code task had an implementer and a separate reviewer; a whole-branch review then found three real defects in the first version (cleanup could remove a foreign worktree given a relative path; cleanup skipped on SIGHUP/SIGTERM; a failed `retarget` could not be re-run), all reproduced and fixed here with a test each. A scoped re-review of those fixes found two more (a SIGINT test that fails when run as a background job; a window after the rename in which a signal removed the finished worktree), also fixed.

## Known limits

- One signal-test run timed out once before the test was changed to re-send its signal. The hang was never reproduced (0 in 300 runs since), so that change rests on an analysis of the cause, not on an observed failure.
- `repin.py check` exits 1 on a network failure as well as on "not shipped" (with a traceback in the first case).
- The capture command for the `content_shell` stock UA baseline is not recorded in the repository; the plan says so and leaves it to be settled on the box.
- On the box, the `ubuntu` user keeps its cloud-init `NOPASSWD` entry; the runner user `<user>` has no sudo and cannot reach it.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-3"></a>
## #3 repin: Chrome stable 154.0.8037.93, and step 0 closed

`repin/8037` into `main`, opened 2026-10-02T17:05:25Z, merged 2026-10-03T01:46:17Z.

Moves the change set from Chrome stable `153.0.8010.36` (`507c6ee3e2`) to
`154.0.8037.93` (`f89f3a4363`), and closes step 0 of the long-term roadmap.

Evidence: `docs/superpowers/measurements/2026-10-repin.md`.
Procedure, for the next one: `docs/superpowers/specs/repin-runbook.md`.

## Prediction against outcome

| | predicted | actual |
|---|---|---|
| Files that could conflict | 36 of the 89 the stack touches (+1048/−916 upstream) | 2 files, 1 hunk each |
| Commits | 37 | 37/37 rebased |
| Semantic conflicts (applied but would not compile) | unknown | **0** — the build and every unit suite passed first try |

The two conflicts:

| patch | file | upstream change | resolution |
|---|---|---|---|
| `sp3a-canvas-noise` | `core/offscreencanvas/offscreen_canvas.cc` | added `updateElementGeometry` + `clearElementGeometry` where our namespace block is inserted | kept both, upstream's first |
| `media-ii-track` | `modules/mediastream/media_stream_track_impl.cc` | re-added `wtf/text/format.h` beside our include | kept both, sorted |

## Timings

| step | duration |
|---|---|
| Fetch the tag | 112 s |
| Rebase worktree | 38 s |
| `gclient sync` + `runhooks` | 1021 s |
| `gn gen` + `gn check` (×2 "Header dependency check OK") | 16 s |
| **Build from scratch** (`chrome`, `content_shell`, `components_unittests`) | **22,215 s = 6 h 10 m, `Build Succeeded: 64324 steps`** |
| camoucfg suites (25) + `run_coherence_tests.sh` | 49 s — `SUCCESS: all tests passed`, **7/7 PASS** |
| `export.sh` | 1 s, 37 commits, 32 series lines |
| Pristine build at the tag / baseline captures / rebuild | 236 s / 39 s / 235 s |

About 7 h 40 m of machine time, 80% of it the one from-scratch build.

## What the export changed

21 of 32 patches, 105 insertions and 105 deletions: **84** `index` lines,
**114** hunk headers, **12** content lines — the two conflicts (4), context
drift in `sp4-geo` and `sp4-webrtc-ip` (4), and the `windows-oracle` comment
that names a baseline file (2). Nothing else.

## Verify sweep, before and after the recapture

| sweep | rc 0 | failures |
|---|---|---|
| 1, stale baselines | 32/44 | 2 expected, 5 from one new `window` key, 1 preset milestone, 4 from the wrong working directory |
| 2, recaptured | **48/51** | `verify_host_oracle` (now PASS, below), `verify_voices_ii` V-JITTER-B (flake: 5/5 on re-run), `verify_sp7_phonehome` P1 (below) |

`run_coherence_tests.sh`: **7/7 PASS**.

`verify_host_oracle` after the recapture and the two dispositions:
**0 DIFF, 239 same leaves, O1 O2 O3 O4 all PASS** (rc 0). O4 only passes with
the recaptured baseline, since it compares the host's own brand list.

## Baselines: recaptured, never edited

Seven, not the two the plan named — Chrome 154 adds `window.requestResize`, so
every captured key set from 153 was stale and five verifications were red for
that one reason. The UA captures are deterministic: two runs of each hashed
identically (`fe88c925…` for `chrome`, `08e7bc30…` for `content_shell`).

The three host baselines come from stock Chrome 154.0.8037.93 on the Windows
host. **The box can no longer reach that host** — the runner hardening removed
`~/.ssh` from `<user>` and `winhost.py` drives the host from the box — so they
were captured from the Mac through the sshgate MCP server and carried back with
a hash check per chunk. The runbook says so, and a proper fix is open.

## Three findings this re-pin surfaced (backlog items 2, 3, 4)

None of them is caused by the re-pin; the re-pin made them visible, which is
the point of doing it.

1. **Safe Browsing phones home on some startups.** `verify_sp7_phonehome` P1
   asserts the external-host set in 75 s is empty; it was `{}` on 153 after
   four RED→GREEN rounds. On 154 it saw `{"safebrowsing.googleapis.com": 1}`
   **once in six scored runs**, `{}` in the other five. Safe Browsing is not a
   component-updater registrant, so none of the sp7 levers touches it, and the
   build has `safe_browsing_mode = 1`. This is traffic, not a surface, so it is
   the highest-priority of the three. **It is not fixed in this PR** — the fix
   is a new lever plus a rebuild and a re-verify.
2. **HEVC claim.** The host answers `canPlayType` `"probably"` for
   `hev1.1.6.L93.B0` (OS decoder); the Linux build answers `""`. A
   Windows-claiming browser that cannot play HEVC is a tell. Excluded in
   `verify_host_oracle` with that reason in the code; delete the exclusion when
   the claim lands.
3. **WebGPU adapter identity.** The host returns an Intel adapter; the box has
   no GPU and the verify forces SwiftShader, so `requestAdapter()` is `null`
   and the subtree is absent. Excluded by prefix — which means O1 cannot see a
   WebGPU difference at all until this is measured on a machine with a GPU. The
   backlog entry says that out loud.

Also smaller, same script: a truncated netlog scores P1/P2 FAIL instead of
"could not measure".

## Step 9 gates

| gate | result |
|---|---|
| Second export changed `additions`, `patches`, `settings/invariants.json` | **0 files** (`git diff --name-only`; `git status --porcelain` counts the staged re-pin changes too and misreads as 23) |
| `check_checkout_sync.sh` | PASS, 41 files identical |
| `gen_keys.py --check` | PASS, 90 keys |
| `check_additions_build.py` | PASS, 38 sources |
| `gen_fontconfig.py --check` | PASS |
| `repin.py check 154.0.8037.93` | "shipped on Windows Stable" |
| `pytest` (the `checks` line) | 78 passed |
| Commits above the pin on `camoucrome/main` | 37 |

## Recovery drill (step 0's other half)

`rebuild_branch.sh` on the re-pinned tree: rc 0, **100 s**, every patch
"cleanly", **`git diff camoucrome/main camoucrome/drill | wc -l` = 0**. The
commit counts differ by design (32 patch commits vs 37, five touch only
`components/camoucfg`); the trees are identical, which is the property that
matters.

Atomic failure, on the real 69 GB checkout: `does-not-exist.patch` appended to
the series gives **rc 128**, `rebuild failed at does-not-exist.patch; the
temporary branch and ~/camoudrill2 were removed`, **0** branches left
and no worktree. The series was restored byte-identical and the drill cleaned
up.

## Five plan defects found while running it

Recorded in the measurement doc: the sync gate's path (`~/camoucrome-client` is
a partial copy without `patches/`), the sweep's working directory (four scripts
read fixtures beside themselves in `~/camoucrome-verify`), two baselines named
where seven need recapture, the preset milestone that `retarget` does not
touch, and the export gate read with `git status` instead of `git diff`.

## What a review of this branch changed

An independent review ran over the hand-written half of the diff. Six findings,
all fixed here; the three that matter:

1. **The `gpu` exclusion was measuring nothing.** Its comment justified itself
   by a property of the machine ("the box has no GPU, so `requestAdapter()`
   resolves to null") but the code matched on key name alone. On a box *with* a
   GPU — the Windows build box of roadmap step 1, or anyone dropping
   `--use-angle=swiftshader` from the probe argv — `gpu.info.*` and
   `gpu.limits.*` would be the host's real GPU reported under a spoofed Windows
   identity, and O1 would still have printed `0 DIFF … PASS`. It also silently
   dropped three capability integers that were compared exactly before. Each
   exclusion now carries a predicate on the fork's own report, evaluated once
   per run, and the run says so when one is not in effect. The HEVC exclusion
   got the same treatment: it lifts the day the Windows build answers HEVC, and
   it hides the *pair* `[canPlayType, isTypeSupported]`, which its comment had
   not said.
2. **O1's summary overstated its own evidence.** "N same leaves" was
   `len(all leaves) - len(diffs)`, so every leaf the loop skipped counted as
   agreement. The honest split on this run: **177 equal by value**, 41 compared
   by type only, 10 named in `KNOWN`, 11 prefix-excluded and never compared.
   The four buckets are printed now and asserted in the tests.
3. **`repin.py` would have falsified a history comment at the next re-pin.** The
   dated line this branch added to `verify_sp1a_chrome.py` holds the values that
   become the *next* re-pin's "old" pair, so `retarget` would have rewritten it
   into a record of a re-pin that never happened — in the one comment whose
   purpose is to stop the baseline becoming a recording of itself. Dated comment
   lines are exempt now, pinned by two tests.

Smaller: `settings/audio.json` cited 153 while deriving its figures from the
host-oracle baseline this branch recaptured at 154, and the runbook listed two
*corruptions to revert* among its *omissions to fill in* — the wrong thing to
diff for.

`scripts/test_verify_host_oracle.py` is new (the file had no tests): seven
cases, every one of them shown to fail with its fix neutered. The `checks`
pytest line runs it; locally that line is **87 passed**.

## Next re-pin

Due **by 2026-10-20**, when 156 goes stable. 154 was chosen over 155
early-stable because the Windows host that captures every stock baseline runs
154, and a baseline must describe the pin.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-4"></a>
## #4 feat(verify): lib_shell resolves its binaries and temp dir from the environment

`step1/lib-shell-paths` into `main`, opened 2026-10-03T02:31:03Z, merged 2026-10-03T02:33:16Z.

First piece of roadmap step 1 (Windows foundation): the verification library no
longer hardcodes a Linux machine's paths.

`scripts/lib_shell.py` held three constants that made every lib_shell-driven
verification Linux-only — both binary paths were
`expanduser("~/chromium/src/out/Default/...")` and the stderr log was a literal
`/tmp/...` path. 53 scripts import the module and 26 read these constants, so
the values are the only place that has to change.

## What changed

- `CAMOU_OUT` moves the build directory. The Windows tree builds into
  `out\Release` under a different root, which is what this exists for.
- `CAMOU_EXE` is reused, not invented. Eleven client-driven verify scripts
  already read it to aim at the `chrome` inside an extracted release archive,
  where no out directory exists. One variable now points both families at one
  binary. It names a file, so it must not move `content_shell` with it, and a
  test pins that.
- The stderr log goes through `tempfile.gettempdir()`. The literal `/tmp` was
  never wrong on the build box — the two agree there — and stops being right
  the moment this runs anywhere else. Windows has no `/tmp` at all, so `open()`
  would have failed at the first launch.
- `_binaries()` takes the environment and `os.name` as arguments because the
  constants resolve once at import. A test that mutated `os.environ` afterwards
  would measure nothing.
- The test harness used to end with `print(f"{7 - len(failures)} PASS")`. That
  stops being the number of checks the moment one is added, so it now counts the
  checks that ran.
- `.github/workflows/checks.yml` runs `scripts/test_lib_shell_launch.py`. It has
  been a hand-run guard since 2026-08-27 and grep finds it only in docs, which
  is the same as not having it. It needs no browser, no checkout and no pip
  install.

## What was deliberately not done

The roadmap's step 1 lists "parametrise `lib_shell.py` (binary path, flags, temp
dir)". The flags are not parametrised: `launch()` already takes `extra_flags`,
and `CHROME_FLAGS` (`--headless --no-first-run --no-default-browser-check`) is
already platform-neutral. A flags knob would be configuration for a value that
does not vary. `SHELL_FLAGS` keeps `--ozone-platform=headless`, which is
correct for the Linux `content_shell` it is the default for.

## Evidence

### Unit, on a Mac (12 PASS, 7 pre-existing + 5 new)

```
$ python3 scripts/test_lib_shell_launch.py
PASS  default argv is unchanged
PASS  default binary is content_shell
PASS  startup failure names content_shell
PASS  chrome argv is unchanged
PASS  chrome mode drops the content_shell headless switch
PASS  startup failure names chrome
PASS  CAMOU_CONFIG* is still scrubbed in chrome mode
PASS  no CAMOU_OUT keeps the paths every earlier run used
PASS  CAMOU_OUT moves both binaries
PASS  CAMOU_EXE wins for chrome and leaves content_shell alone
PASS  nt names chrome.exe and content_shell.exe
PASS  the stderr log is in the platform temp dir and carries the pid

12 PASS
```

The Mac matters for the last check: `gettempdir()` there is under
`/var/folders`, so a hardcoded `/tmp` fails it. On Linux the two coincide and
the check is weak — the comment beside it says so.

### Each new check seen RED, by removing the behaviour it claims to measure

Five mutations of `lib_shell.py`, each run with bytecode caching off, then
reverted:

| Mutation | Checks that failed |
|---|---|
| `CAMOU_OUT` ignored | `CAMOU_OUT moves both binaries`, `CAMOU_EXE wins for chrome and leaves content_shell alone` |
| `CAMOU_EXE` ignored | `CAMOU_EXE wins for chrome and leaves content_shell alone` (`got ('/w/out/Release/content_shell', '/w/out/Release/chrome')`) |
| `.exe` suffix dropped on `nt` | `nt names chrome.exe and content_shell.exe` |
| temp dir hardcoded back to `/tmp` | `the stderr log is in the platform temp dir and carries the pid` (`got /tmp/... (tempdir /var/folders/...)`) |
| default out dir changed to `out/Release` | `no CAMOU_OUT keeps the paths every earlier run used` |

The first attempt at this table was wrong and is worth recording: mutations 1
and 2 changed the file by the same number of bytes within the same second, so
Python reused the first mutation's `__pycache__` and the second run reported the
first one's failures. Re-run with `-B` and the cache cleared between mutations,
the second mutation kills exactly one check.

### On the build box, against the real 154 binaries

`$VERIFY/lib_shell.py` was replaced with this branch's version (original backed
up, restored afterwards, hash confirmed), then the six verifications CI runs
were run exactly as CI runs them, with no `CAMOU_OUT` set:

```
== verify_sp1a_chrome.py
PASS  8 unconfigured userAgentData matches the baseline
== verify_sp4_voices.py
5/5 ALL_PASS
== verify_fonts_bundle.py
17 PASS 0 FAIL
== verify_host_oracle.py
4 PASS 0 FAIL
== verify_windows_behaviour.py
14 PASS 0 FAIL
== verify_sp6b_generator.py
ALL_PASS
```

Those are the same six counts build-verify reported on `main` 40 minutes
earlier (run 37087364720): `8`, `5/5 ALL_PASS`, `17 PASS 0 FAIL`,
`4 PASS 0 FAIL`, `14 PASS 0 FAIL`, `ALL_PASS`. Nothing moved.

The knob is live rather than dead code, and fails loudly when aimed wrong:

```
== knob: CAMOU_OUT pointed at the same dir by hand
5/5 ALL_PASS
== knob RED: CAMOU_OUT pointed at a dir with no binary
FileNotFoundError: [Errno 2] No such file or directory: '~/no-such-out/content_shell'
== restore
913a3c63f30782d6fcce0a434686acfe55e3a5f30ac73ad13fbd21ba23734597  ~/camoucrome-verify/lib_shell.py
```

That hash is the file the box started with, so the verify tree is as it was.

### CI

`checks` on this branch: run 37089853544, success. The new step prints the
twelve PASS lines above; `python client tests + packager tests` reports
`87 passed in 2.82s`.

`build-verify` does not run on pull requests — it triggers on push to `main` —
so it has not run against this branch. On merge it should print the same six
counts listed above.

## Not verified

That any of this works on Windows. No Windows machine was touched in this
change, by choice. The `.exe` branch is checked for the name it chooses, not for
a browser that started, and the comment beside that check says so. The Windows
tree on the build box is still on the old pin (`507c6ee3e2`, Chrome
153.0.8010.36), so there is nothing there to run against yet.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-5"></a>
## #5 refactor(verify): one definition of where chrome is

`step1/one-chrome-path` into `main`, opened 2026-10-03T02:51:56Z, merged 2026-10-03T02:57:13Z.

Follow-up to #4. Eleven scripts repeated the same line:

```python
EXE = os.environ.get("CAMOU_EXE", f"{HOME}/chromium/src/out/Default/chrome")
```

so the default path existed in eleven places, and `CAMOU_OUT` — which `lib_shell`
started honouring in #4 — reached none of them. They all read `lib_shell.CHROME`
now, which is the same precedence they had (`CAMOU_EXE` first) plus `CAMOU_OUT`
underneath it.

## Why this needed a change to lib_shell too

Ten of the eleven do not import playwright at module scope. They drive the
browser through the client in a subprocess and deliberately keep playwright out
of their own process — `verify_chrome_object.py` goes as far as importing
`lib_shell` *inside* a function for that reason. A module-scope
`from playwright.sync_api import ...` in `lib_shell` would have made reading a
path cost those scripts a dependency they had avoided, and would have turned a
missing playwright into an `ImportError` in scripts that never needed it.

So playwright is now imported inside `evaluate()`, the one function that uses
it. `verify_chrome_object.py`'s in-function workaround is no longer needed and is
gone.

## Evidence

### Unit (13 PASS, Mac)

The new check is a subprocess with playwright blocked by a `meta_path` hook,
because playwright *is* installed on this machine — the test file's existing
stub never runs, so it proves nothing about the no-playwright case:

```
PASS  lib_shell imports with no playwright installed
...
13 PASS
```

Seen RED before the lazy import, which is the whole point of the check:

```
FAIL  lib_shell imports with no playwright installed: exit 1, out '', err ['ImportError: playwright is not installed here']
1 FAILED of 13: lib_shell imports with no playwright installed
```

The default path stays frozen by the check added in #4
(`no CAMOU_OUT keeps the paths every earlier run used`), so `EXE` resolves to
the byte-identical string it did before. `grep` finds the old literal in exactly
one place now: that frozen expectation in the test.

### On the build box, against the real 154 binaries

This branch's eleven scripts were installed into `$VERIFY` from the runner's own
clone (`git show origin/<branch>:scripts/<file>`), with the tree tarred up first
and restored afterwards. Ten of the eleven live there and all ten were run:

```
== verify_sp1a_chrome.py
PASS  8 unconfigured userAgentData matches the baseline
== verify_sp4_voices.py
5/5 ALL_PASS
== verify_fonts_bundle.py
17 PASS 0 FAIL
== verify_host_oracle.py
4 PASS 0 FAIL
== verify_windows_behaviour.py
14 PASS 0 FAIL
== verify_sp6b_generator.py
ALL_PASS
== verify_chrome_object.py
4 PASS 0 FAIL
== verify_font_metrics.py
5 PASS 0 FAIL
== verify_d_pointer_touch.py
5 PASS 0 FAIL
== verify_webgl_profile.py
4 PASS 0 FAIL
== verify_sp6b_launcher.py
ALL_PASS
== verify_sp6b_driver.py
ALL_PASS
```

The six that CI runs match the post-merge `build-verify` run on `main`
(37090208372) exactly: `8`, `5/5 ALL_PASS`, `17 PASS 0 FAIL`, `4 PASS 0 FAIL`,
`14 PASS 0 FAIL`, `ALL_PASS`. The other six are not in CI and had no recent
reference run, so what they establish is that each still starts a browser,
reaches its assertions and reports a count — which is what a changed `EXE` could
have broken.

Restore confirmed afterwards: `verify_host_oracle.py` is back to its own
`CAMOU_EXE` line.

**Not run:** `scripts/measure_d_gaps.py`, the eleventh script. It is a
`measure_*` script, so CI does not copy it into `$VERIFY`; it runs out of
`$CLIENT/scripts`. Its edit is the same one-line substitution as the other ten
and it compiles, but it was not executed.

### CI

`checks` on this branch: run 37090976580, success — the argv-freeze step
(added in #4) prints the thirteen PASS lines, and `87 passed` for pytest.

`build-verify` does not run on pull requests. On merge it should print the same
six counts listed above.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-6"></a>
## #6 refactor(verify): fold the eleven scripts' shared layout block into lib_shell.layout()

`step1/one-path-block` into `main`, opened 2026-10-03T03:08:33Z, merged 2026-10-03T06:14:08Z.

Finishes what #5 started: five more lines were repeated across the same eleven
scripts, all byte-identical.

| Line | Copies |
|---|---|
| `HOME = os.path.expanduser("~")` | 11 |
| `PY = os.environ.get("CAMOU_VENV", …) + "/bin/python3"` | 10 |
| `NODE = os.environ.get("PLAYWRIGHT_NODEJS_PATH", …)` | 10 |
| `CLIENT = pathlib.Path(os.environ.get("CAMOU_CLIENT", …))` | 5 |
| `FONTS_DIR = os.environ.get("CAMOU_FONTS_DIR", str(CLIENT / "fonts"))` | 4 |

Each script now calls `lib_shell.layout()` on one line, with no change at any
use site. `~/camoucrome-verify` as a *baseline* root is still expanded in eight
other scripts — this folds the layout block those eleven shared, not every path
on the box.

## The regression this PR shipped first, and the fix

The first commit made the five paths module constants. That latched
`CAMOU_CLIENT` at **lib_shell's** import, whenever that happened to be, so
lib_shell decided `CLIENT` for every script imported later in the same process.

```
$ python3 -m pytest -q scripts/        # main (fefba81)
60 passed in 31.37s

$ python3 -m pytest -q scripts/        # 3e600e3, the first commit here
ERROR scripts/test_verify_host_oracle.py - FileNotFoundError: [Errno 2] No such file or directory: '~/camoucrome-client/baselines/chrome-8037-stock-oracle-windows.json'
Interrupted: 1 error during collection
```

`test_verify_host_oracle.py` sets `CAMOU_CLIENT` and then imports the script
under test; `test_lib_shell_launch.py` had already imported lib_shell. **CI was
green on that commit** (run 37092206509) because its pytest list happens to
contain no other module that imports lib_shell at module scope, and the
argv-freeze step runs in its own process. A green run that measured nothing —
found by review, not by CI.

Fixed by making it a function: `layout(environ=None)` returns a `Layout`
namedtuple and each script calls it at its own import, where its own lines used
to be. The `environ` argument exists for the same reason `_binaries` has one,
and it is what lets the defaults and overrides be tested at all — as constants
they had no coverage.

Then, so the regression cannot hide behind argument order again,
`test_verify_host_oracle.py` imports lib_shell **before** setting
`CAMOU_CLIENT`. On the broken lib_shell that file now fails on its own:

```
ERROR scripts/test_verify_host_oracle.py - FileNotFoundError: ...
Interrupted: 1 error during collection
```

and on the fixed one, `7 passed`. CI already runs that file, so no workflow
change was needed.

## A second bug the review found

Five paths spelled the client tree by hand as `f"{HOME}/camoucrome-client/..."`
while their siblings in the same files followed `CAMOU_CLIENT`:
`verify_chrome_object`'s `BASELINE`, `verify_webgl_profile`'s `WEBGL_DIR`,
`verify_sp6b_driver`'s `NODE_PROBE` and its `launcher.json` fallback, and
`verify_sp6b_launcher`'s `launcher.json` fallback. With `CAMOU_CLIENT` set, a
run read its baseline from one tree and its settings from another. They go
through `CLIENT` now. With `CAMOU_CLIENT` unset — the box — the paths are
unchanged.

## The one line that is not duplication

`verify_sp6b_driver.py` keeps its own `NODE`, derived from `DRIVER_PATCHRIGHT`
(`CAMOU_DRIVER`), because folding it in would make `CAMOU_DRIVER` move the node
every other script uses — a behaviour change nobody asked for. `layout().node`
keeps the default the other ten had and says why.

## Evidence

### Unit

`scripts/test_lib_shell_launch.py`: **17 PASS** (13 from #4/#5, 4 new covering
`layout`'s defaults, its four overrides, `FONTS_DIR` following `CAMOU_CLIENT`,
and the late-binding property itself). `python3 -m pytest -q scripts/`:
**60 passed**. All of `scripts/` compiles.

### Lint, with a baseline so nothing pre-existing is claimed as new

`pyflakes scripts/*.py` on `main` and on this branch, line numbers stripped,
sorted and compared: nothing new. Removing the old definitions orphaned seven
`HOME` imports and five `import pathlib` lines, which is how they were found;
both are gone. Pre-existing unused imports elsewhere were left alone.

### On the build box, against the real 154 binaries

Installed into `$VERIFY` from the runner's own clone, tree tarred up first. The
resolved layout:

```
Layout(home='~', py='~/camoucrome-verify/venv/bin/python3',
       node='~/camoucrome-driver/node',
       client=PosixPath('~/camoucrome-client'),
       fonts_dir='~/camoucrome-client/fonts')
```

All ten of the eleven that live in `$VERIFY`, run after the fix:

```
== verify_sp1a_chrome.py          PASS  8 unconfigured userAgentData matches the baseline
== verify_sp4_voices.py           5/5 ALL_PASS
== verify_fonts_bundle.py         17 PASS 0 FAIL
== verify_host_oracle.py          4 PASS 0 FAIL
== verify_chrome_object.py        4 PASS 0 FAIL
== verify_webgl_profile.py        4 PASS 0 FAIL
== verify_windows_behaviour.py    14 PASS 0 FAIL
== verify_sp6b_generator.py       ALL_PASS
== verify_font_metrics.py         5 PASS 0 FAIL
== verify_d_pointer_touch.py      5 PASS 0 FAIL
== verify_sp6b_launcher.py        ALL_PASS
== verify_sp6b_driver.py          ALL_PASS
```

The six that CI runs match the post-merge `build-verify` run on `main`
(37091562851) exactly. The verify tree was restored afterwards and its
`lib_shell.py` hashes `4bea883efff050b16b248fdd7664322bd8b45432879cd7c01f696f8d397eeb1a`,
byte-for-byte `main`'s copy.

**Not run:** `scripts/measure_d_gaps.py` — a `measure_*` script, so CI does not
copy it into `$VERIFY`. Same substitution as the other ten, and it compiles, but
it was not executed.

### CI

`checks` on `2706751`: success. Worth stating plainly: `checks` was also green on
the broken commit, so on this branch CI is evidence that nothing cheap broke, not
evidence that the latch is gone — the `pytest -q scripts/` numbers and the
import-order guard are.

`build-verify` does not run on pull requests. On merge it should print the same
six counts listed above.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-7"></a>
## #7 Step 1 first slice: a Windows verify substrate on the build that already exists

`step1/windows-substrate` into `main`, opened 2026-10-03T07:16:11Z, merged 2026-10-03T07:18:34Z.

The first slice of roadmap Step 1, executed with no Chromium build: a committed
verification now runs natively against the fork's Windows `chrome.exe`, and the
Windows tree's state is measured well enough to decide what happens to it at the
re-pin due 2026-10-20.

No C++, no change to the change set, no baseline touched. One CI change and
documentation of measurements.

## The decision this slice rests on

The Windows tree holds a complete fork build at the **old** pin (`chrome.dll`
315.6 MB, ProductVersion `153.0.8010.36`, built 2026-09-25). Chrome 156 reaches
stable 2026-10-20, which is also when the re-pin is due, and that re-pin rebuilds
the Windows tree anyway. Re-pointing it to 154 now would spend about 7.5 h of
build time that 156 obsoletes in 17 days — and doing both on 2026-10-20 would put
the Windows build next to the re-pin's 6 h 10 m WSL build on one machine the same
day, with the build-overlap lock Step 1 still owes. So this slice proves the
plumbing against the binary that already exists, choosing verifications that
assert **behaviour** rather than a captured baseline, because a 153 binary cannot
match a 154 baseline.

## What is now measured on Windows

**The first committed verification green natively on `chrome.exe`:**

```
verify_sp2b.py    PASS 1, PASS 2, PASS 3, exit 0
```

with a RED control — the same script with `CAMOU_OUT` pointing at a directory
holding no binary gives 0 of 3 and exit 1.

**The direct proof that `tempfile.gettempdir()` replaced the hardcoded `/tmp`**
(PR #4): after a run, `%TEMP%\camoucrome_verify_stderr.3132.log` exists on the
host, 226 bytes, containing the `DevTools listening` line. Windows has no `/tmp`;
the old literal would have failed at the first launch.

**The host environment** it runs in: Python 3.9.13, playwright **1.55.0 — the
same version the build box has**, and the verify tree copied from repo commit
`aeb79dc`.

**`verify_sp7_fieldtrial.py`**, run second, exits 1 by design here, and the
triage matters more than the exit code:

| Rows | Verdict | Cause |
|---|---|---|
| F1–F4 | FAIL | (b) Linux-only: a Windows release build has no `content_shell.exe`, and those rows drive it |
| C1, C4 | PASS | the field-trial testing config is refused on Windows too |
| C2 | FAIL | **(c) a real Windows difference** |

C2 is a finding, reproduced on four runs: given `--enable-field-trial-config`,
`chrome.exe` prints the exclusion message — so the config is still refused — then
exits with **`0xC0000005`, an access violation**, where Linux exits with code 1.
Root cause unknown. It is now backlog item 5, with the qualifier that justifies
that rank (the trigger is an operator-supplied flag, not page-reachable) and the
first thing to check: whether the access violation produces a crashpad upload,
because that would make it network traffic.

## The correction that matters most in this PR

An earlier draft of the measurement document said `verify_sp2b.py` passing proves
`CAMOU_CONFIG` reaches the **renderer** on Windows. The final review showed that
is wrong, and the evidence is worth stating because the mistake would have been
expensive:

- `patches/sp2b-humanized-cursor.patch` touches exactly two files,
  `content/browser/devtools/protocol/input_handler.cc` and `.h`, and its three
  config reads use `camoucfg::GlobalScope()` there. That is the **browser**
  process.
- The only renderer-side row, F3 (`navigator.hardwareConcurrency`), never ran —
  no `content_shell.exe`.
- `scripts/lib_shell.py:282` hardcodes `--no-sandbox` into every `launch()`.
- `measurements/2026-09-24-review-triage.md:183` records this project's only
  Windows-specific bug: `CreateFilteredEnvironment()` strips every `CAMOU_*`
  variable from sandboxed children, so `navigator.hardwareConcurrency` read the
  real **16** under the default sandbox and the spoofed **3** under
  `--no-sandbox`.

So the argv that produced this green is the one argv under which that bug was
invisible, and the process it exercised is the one the filter never touched. The
document now says "browser process" in both places, and records that a Windows
renderer-surface verification requires a run **without** `--no-sandbox`, which
`launch()` cannot currently produce. That is a real follow-up, not an assumption.

## The Windows tree, for the 2026-10-20 re-point

`specs/repin-runbook.md` gains §7, answering the question that comes before an
irreversible act: may this tree be discarded? The tree holds the old change set
as an **uncommitted** working tree, no commits above the pin.

| Layer | What it proves | Result |
|---|---|---|
| 1, paths | no extra or missing path | 130 dirty = 89 patch targets + 41 untracked, `Compare-Object` empty |
| 2, new-file hashes | the 41 new files | **41 of 41 byte-identical** to the blobs at `200276a` |
| 3, byte replay | the 89 patched files | **89 of 89 byte-identical** after replaying all 32 old patches in series |

Three files' summed per-patch counts disagreed (`browser_main_loop.cc` 187/0 vs
207/20, `local_font_face_source.cc` 36/0 vs 38/2, `speech_synthesis.cc` 293/0 vs
308/15) because 2–3 patches each touch them and summing overcounts lines a later
patch rewrites; the net add-minus-remove is equal in all three, and the byte
replay settles them.

**Both hash loops were made to fail on purpose**, because a loop that has only
ever printed `differing 0` is not known to be able to report a difference — and
this one authorises discarding a tree:

```
Step D: first hash of a copy of the list altered
        -> BLOBDIFF components/camoucfg/BUILD.gn, checked 41 differing 1
        -> original list: differing 0
Step F: one `x` appended to the scratch copy of browser_main_loop.cc
        -> one DIFF line, byte-compared 89 differing 1
        -> scratch copy regenerated: differing 0
```

Nothing under `D:\camou-win\chromium\src` was touched. §7's eight code blocks
were then extracted from the document and run, reaching the same numbers — so the
runbook works as written, not only as remembered. It states its own deviations
(PowerShell lines joined with `; ` because the transport refuses newlines,
comment lines dropped, the prose `--include=<path>` form not re-run) and its
blind spot: all 89 targets are in the main `src` repo, so an edit under a
`.gitignore`d path or a DEPS-managed sub-repo is outside every layer's view.

Also recorded there: Git Bash is at `C:\Program Files\Git\bin\bash.exe` (MINGW64,
coreutils on PATH), while the host's `bash` is the WSL launcher and
`usr\bin\bash.exe` lacks coreutils unless started with `-l`;
`disable_fieldtrial_testing_config = true` lives in `out\Release\args.gn`, whose
canonical source is `settings/release-args.gn`, so a re-point must carry GN args
across and not only patches. Whether `apply.sh` and `rebuild_branch.sh` run under
Git Bash is **not measured** — they were deliberately not run.

## The CI hole this branch closes

`.github/workflows/checks.yml` named its test files by hand. That list is why the
`CLIENT` latch regression went green through CI last night: it contained no
*earlier* importer of `lib_shell` at module scope, so the cross-module ordering
that breaks `pytest scripts/` never happened there. Two test files in the tree,
`test_gen_keys.py` and `test_winhost.py`, had never run in CI at all.

The step now runs `pytest -q client/python/tests scripts/`. Measured in a venv
holding only `pytest` and `browserforge==1.2.4` — exactly what the runner
installs:

```
new command: 98 passed, exit 0, 0 skipped
old list:    87 passed
```

The delta is exactly 11: `test_gen_keys.py` (9) + `test_winhost.py` (2). And on
the real ubuntu runner, `python tests: clients, packager, scripts` printed
**`98 passed in 2.85s`** (run 37104255614).

## What this does NOT establish

Stated plainly, because the slice's value depends on not overclaiming it:

- Not the renderer path on Windows (see above), and not `CAMOU_EXE`, which was
  never exercised there.
- Not the Windows component build, and not the change loop end to end —
  `apply.sh` and `rebuild_branch.sh` were never run on the host.
- Not the Go or Node clients, and not fonts on Windows.
- Not any baseline-comparing verification: the binary is 153, the baselines are
  154.
- `layout()`'s `py` and `node` are Linux-shaped on the host
  (`.../venv/bin/python3`, no `.exe`) and do not exist there, so the ~10 scripts
  that read them cannot run on Windows yet. `lib_shell.SHELL` likewise resolves
  to a `content_shell.exe` a release build does not contain.
- `launch()`'s "exited during startup" message naming the binary is proven on
  Linux; through `verify_sp2b.py` on Windows the failure surfaces only as
  `[WinError 2]`.

A premise this slice killed, recorded because it cost an hour: **WSL automount is
disabled on this machine**, so `/mnt/d` inside WSL is an ordinary WSL-local
directory. A probe that ran `test -d /mnt/d` and wrote a file there succeeded
while the files landed nowhere Windows could see. The working transport is from
the Windows side, through `\\wsl.localhost\Ubuntu-24.04\...`; reading the Windows
tree from WSL is not possible, so git runs on the host. The executed plan carries
a dated `> **Amended 2026-10-03.**` block saying so rather than being rewritten.

## Process notes, for honesty about the commits

Two agents edited `specs/repin-runbook.md` in the same working tree at the same
time. Nothing was lost — the file is correct and the tree is clean — but the
commit boundaries do not partition the work: `9c4bba1` carries the two
"seen to print" lines that belong to the RED work in `b1863da`, and `b1863da`'s
subject names work its diff does not contain. Recorded rather than rewritten.

`checks` on this branch: run 37105685279, success. `build-verify` does not run on
pull requests; nothing here touches the change set, so the box's binaries are
unaffected.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-8"></a>
## #8 Windows: the renderer under the real sandbox

`step1/sandboxed-launch` into `main`, opened 2026-10-03T07:26:40Z, merged 2026-10-03T07:29:27Z.

The hole PR #7's own review opened, closed. On Windows, a renderer-consumed key
now reads the configured value **under the real sandbox** — the first time the
`windows-sandbox-env` fix has been measured by anything committed, and the one
measurement the previous slice structurally could not make.

No build. Same 153 `chrome.exe`.

## Why this could not be measured before

`lib_shell.launch()` passed `--no-sandbox` unconditionally. On Windows that is the
one argv under which the project's only Windows-specific bug is invisible:
`CreateFilteredEnvironment()` (`sandbox/win/src/broker_services.cc`) passes seven
variables to sandboxed children, so every `CAMOU_*` one is stripped and a
renderer-consumed key falls back to the real value.
`measurements/2026-09-24-review-triage.md:183` records the shape —
`navigator.hardwareConcurrency` read the real **16** under the default sandbox and
the spoofed **3** under `--no-sandbox`. Linux has no such filter, so no WSL run can
reproduce it. The fix shipped in September (571778d) and nothing committed had
re-measured it since, because the harness could not launch sandboxed at all.

So PR #7 could honestly claim only that the **browser** process reads the config
on Windows. This PR makes the renderer claim measurable, then measures it.

## The change

`launch()` and `session()` take `sandbox=False`; `sandbox=True` omits
`--no-sandbox`. The default keeps every earlier call's argv byte-identical, and
the frozen argv in `scripts/test_lib_shell_launch.py` is the guard — plus a second
row pinning that `--no-sandbox` is still `argv[1]` by default. It is opt-in per
call rather than a new default because a sandboxed launch may not start at all on
the Linux box; WSL2 needs user namespaces for it.

```
$ python3 scripts/test_lib_shell_launch.py
19 PASS
$ python3 -m pytest -q scripts/
60 passed
```

## The measurement, on the Windows host

```
A no-sandbox + config: ([3], None)
B sandboxed + config: ([3], None)
C sandboxed, no config: ([16], None)
```

**B** is the row nothing committed could reach. **C** is why B means anything: the
same sandboxed launch with no config at all reports this machine's real 16, so B's
3 did not come from a hardcoded default, a stale profile, or the probe itself.

## It is a committed verification, seen RED first

`scripts/verify_windows_sandbox_env.py`, three rows, asserting its own row count.
W2 *is* W1's control — the design point is that a spoofed value arriving from
anywhere but the config would show up in both rows.

RED, `CAMOU_OUT` pointing at a directory with no binary:

```
note: W1: sandboxed + config -> None (expect 3); FileNotFoundError: [WinError 2] The system cannot find the file specified
note: W2: sandboxed, no config -> None (expect anything but 3); FileNotFoundError: [WinError 2] ...
note: W3: --no-sandbox + config -> None (expect 3); FileNotFoundError: [WinError 2] ...
W1: FAIL
W2: FAIL
W3: FAIL
0 PASS 3 FAIL
exit=1
```

GREEN against the real build directory, and again on an immediate re-run, because
an intermittently green verification is worse than a slow one:

```
note: W1: sandboxed + config -> 3 (expect 3)
note: W2: sandboxed, no config -> 16 (expect anything but 3)
note: W3: --no-sandbox + config -> 3 (expect 3)
W1: PASS
W2: PASS
W3: PASS
3 PASS 0 FAIL
exit=0
```

## What this does NOT establish

- **Worker parity on Windows.** Conventions rule 3 requires a surface exposed to
  both a window and a worker to report identical values in both, and September did
  check a dedicated worker (`main=3 worker=3`). This script reads the main thread
  only. The row was left out rather than written untested; it is named in the
  measurement doc as worth adding.
- **Any other renderer-consumed key.** One key is one key.
- **That `out\Release`'s binary contains every patch the tree now holds.** It was
  built 2026-09-25 while the tree's content matches the change set at `200276a`,
  and the runbook's byte comparison is about the *tree*. W1 shows the binary
  contains a working fix, not that it is current.
- `CAMOU_EXE` on Windows, the component build, the change loop end to end, the Go
  and Node clients, fonts, and every baseline-comparing verification while the
  Windows binary is on the old pin.

## Documents corrected rather than quietly replaced

The measurement doc's "Any renderer-consumed key on Windows" entry is struck
through with a pointer to the new section, not deleted — everything it says about
`verify_sp2b.py` stays true, and it is the entry that motivated this work.

A trap worth the line, because it bit: installing the new `lib_shell.py` on the
host with `Copy-Item` from a path that had failed to be written left a
**zero-line** file in the verify tree, overwriting the working copy. It was
restored from the `.bak` taken in the same call. Take the backup first and check
the installed line count. The host's verify tree is consequently `aeb79dc` plus
two files from this branch, which the measurement doc records.

## Not in this PR

`verify_windows_sandbox_env.py` is not added to any CI job. It can only run on the
Windows host, which no workflow reaches, and `build-verify` does not run on pull
requests. `checks` on this branch: see below.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-9"></a>
## #9 Windows: worker parity under the sandbox

`step1/windows-worker-parity` into `main`, opened 2026-10-03T07:33:12Z, merged 2026-10-03T07:35:19Z.

Conventions rule 3 is non-negotiable: a surface exposed to both a window and a
worker must report identical values in both. PR #8 read the main thread only and
said so rather than carrying an untested row. This adds the two rows it named.

On Windows a renderer and a dedicated worker are separate processes, so
`CreateFilteredEnvironment()` could reach one and not the other — a fix that
applied to only one would look correct from the main thread alone.

**W4** is parity under the spoof. **W5** is parity with no config at all, which is
what stops W4 passing because both values happen to be the spoofed number. Both
expressions go through ONE session per case, so the pair comes from the same
process tree and the three launches did not become five. `EXPECTED` is 5 and the
script fails if its row count disagrees.

The blob-worker probe is copied from `verify_sp0.py:9-16` rather than imported,
because importing that module would execute its browser work.

## Evidence, on the Windows host against the 153 `chrome.exe`

RED first, `CAMOU_OUT` pointing at a directory with no binary. Note that W5's
`is not None` guard is what makes it FAIL rather than pass on two equal `None`s:

```
note: W4: sandboxed + config, worker -> None (expect 3, and equal to main None)
note: W5: sandboxed, no config, worker -> None (expect equal to main None)
W1: FAIL
W2: FAIL
W3: FAIL
W4: FAIL
W5: FAIL
0 PASS 5 FAIL
exit=1
```

GREEN against the real build directory, and again on an immediate re-run:

```
note: W1: sandboxed + config, main -> 3 (expect 3)
note: W2: sandboxed, no config, main -> 16 (expect anything but 3)
note: W3: --no-sandbox + config, main -> 3 (expect 3)
note: W4: sandboxed + config, worker -> 3 (expect 3, and equal to main 3)
note: W5: sandboxed, no config, worker -> 16 (expect equal to main 16)
W1: PASS
W2: PASS
W3: PASS
W4: PASS
W5: PASS
5 PASS 0 FAIL
exit=0
```

`main=3 worker=3` under the sandbox reproduces what September measured by hand
(`2026-09-24-review-triage.md:195`). `main=16 worker=16` unconfigured is the part
that was not measured then, and it is what makes the parity claim mean something.

## Documents

The measurement doc's "Worker parity on Windows" limitation is struck through with
a pointer to the new section rather than deleted — it is the entry that motivated
this work. The roadmap's Step 1 status drops worker parity from its open list,
which now reads: `CAMOU_EXE` on Windows, the component build, the change loop end
to end, the Go and Node clients, fonts, and every baseline-comparing verification
while the Windows binary is on the old pin.

Still not established: any renderer-consumed key other than this one, and that
`out\Release`'s binary contains every patch the tree now holds (it was built
2026-09-25 while the tree matches `200276a`).

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-10"></a>
## #10 Windows: CAMOU_EXE measured in both directions

`step1/windows-camou-exe` into `main`, opened 2026-10-03T07:36:42Z, merged 2026-10-03T07:40:06Z.

The last of the three knobs PR #4 shipped that had never run against a real
browser on Windows. Documentation only: the measurement needed no code change.

Until now, `CAMOU_EXE`'s precedence over `CAMOU_OUT` was proven only by
`scripts/test_lib_shell_launch.py` on a Mac, which checks the strings
`_binaries()` returns — not a browser that started.

## Evidence, on the Windows host against the 153 `chrome.exe`

`verify_windows_sandbox_env.py` is the instrument: its five rows need a working
chrome and fail all together without one.

```
=== GREEN: CAMOU_OUT bogus, CAMOU_EXE real -> EXE must win ===
CHROME = D:\camou-win\chromium\src\out\Release\chrome.exe
SHELL  = D:\no-such-out\content_shell.exe
5 PASS 0 FAIL
exit=0
=== RED: CAMOU_OUT real, CAMOU_EXE bogus -> EXE must still win ===
CHROME = D:\no-such\chrome.exe
0 PASS 5 FAIL
exit=1
```

The **RED** run is what proves precedence rather than mere use: a valid
`CAMOU_OUT` was available and was not taken.

The **GREEN** run's `SHELL` line measures a third property, on Windows for the
first time: `CAMOU_EXE` left `content_shell` under the bogus `CAMOU_OUT` instead
of dragging it along. That is the design claim PR #4 made — `CAMOU_EXE` names one
file, the chrome inside an extracted release archive, and must not move anything
else.

With this, all three things PR #4 shipped — `CAMOU_OUT`, `CAMOU_EXE` and
`tempfile.gettempdir()` — have run against a real browser on Windows.

## Documents

The measurement doc's `CAMOU_EXE` limitation is struck through with a pointer to
the new section rather than deleted. The roadmap's Step 1 open list now reads: the
component build, the change loop end to end, the Go and Node clients, fonts, and
every baseline-comparing verification while the Windows binary is on the old pin.

`build-verify` does not run on pull requests, and this PR touches only `docs/`, so
it will not run on merge either.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-11"></a>
## #11 Windows: crash dumps carry the identity's config (no upload)

`step1/windows-crashpad` into `main`, opened 2026-10-03T07:46:57Z, merged 2026-10-03T07:57:52Z.

Backlog item 5 ended on one question: does the Windows `0xC0000005` access
violation produce a crashpad **upload**? It does not. But answering it found
something larger: **every crash writes the identity's configuration to disk,
inside the profile, next to the real machine's environment.**

Documentation only. No code change. The fix is a decision this PR records rather
than makes.

## No upload — for a different reason than the Linux analysis gave

`measurements/2026-09-09-sp7-phone-home.md` concluded crash upload is off because
`GetCollectStatsConsent()` returns false without `GOOGLE_CHROME_BRANDING`. That is
the **Linux** client. On Windows the client delegates to
`install_static::GetCollectStatsConsent()`, which reads **machine state**: a
`MetricsReportingEnabled` policy under `SOFTWARE\Policies\<product>`, else a
`usagestats` registry value. On a managed Windows machine with that policy set,
consent is **true**.

What actually stops an upload, on every platform, is
`components/crash/core/app/crash_reporter_client.cc:144-147`:

```
std::string CrashReporterClient::GetUploadUrl() {
#if BUILDFLAG(GOOGLE_CHROME_BRANDING) && defined(OFFICIAL_BUILD)
  return kDefaultUploadURL;
#else
  return std::string();
```

The fork is neither, so the URL is empty. One override exists, operator-side:
`crashpad_win.cc:100-105` takes the URL from an environment variable "for
testing". On this host all four policy locations are absent. The sp7 document
gets a dated `> **Amended 2026-10-03.**` note rather than a rewrite.

## The finding: the dump carries the identity

A deliberate crash with a fresh profile writes a dump into that profile:

```
exit code: 0xC0000005
files under the profile's Crashpad: 3
  <udd>\Crashpad\metadata  114
  <udd>\Crashpad\settings.dat  40
  <udd>\Crashpad\reports\df89f437-24f0-4882-8b54-166f660e06f3.dmp  191104
```

Crashed again with a unique marker as a config value, then searched the dump —
as ASCII and as UTF-16LE, since the Windows environment block is UTF-16:

```
marker as ASCII:    False
marker as UTF-16LE: True
the string CAMOU_CONFIG as UTF-16LE: True
context: 4= CAMOU_CONFIG={"ua:osInfo":"ZQXJ7731MARKER"} ChocolateyInstall=C:\ProgramData\
=== control: same crash, no CAMOU_CONFIG ===
control marker as UTF-16LE: False
```

The minidump holds the process's **whole environment block**: the configuration
verbatim, beside every host variable. The control rules out the marker coming
from anywhere else.

The config is the identity. A crashed profile carries a plain-text record of who
it claimed to be next to the real machine's environment — the cross-profile link
that the roadmap's "many identities on one machine" decision must not have.
Nothing about this is specific to the field-trial flag; it is only a reliable
trigger.

## In the roadmap

New **backlog item 5**, ranked below Safe Browsing (item 4) because it is not
traffic, and above the crash-exit item (now 6) because it applies to every crash
rather than one flag. Levers listed, none chosen:

- stop crashpad initialising for the fork — `GetCrashDumpLocation` returning
  empty, `chrome/app/chrome_crash_reporter_client_win.cc:130-132`;
- or have the clients put the crash database somewhere they delete.

One non-lever ruled out explicitly: scrubbing `CAMOU_*` from the environment
after parsing would break the `windows-sandbox-env` fix, because child processes
need those variables.

The old items 5–10 become 6–11. The one reference to the old number, in the
substrate measurement doc, is updated; a grep over `docs/superpowers` found no
other.

## Also recorded, not fixed

`%TEMP%` on the host held 14 `camoucrome-verify-*` profile directories and 12
stderr logs after the day's verify runs. The directories were **empty** — nothing
leaked — but `lib_shell.shutdown()`'s `rmtree(..., ignore_errors=True)` had
removed their contents and not the directories, and `ignore_errors` hid it.
Separately, `launch()` runs `mkdtemp()` before `Popen`, so a `Popen` that raises
leaves the directory behind on every platform. Both belong to Step 1's "temp
directory cleanup".

## Housekeeping on the host

The three throwaway profiles made for the crash test, each holding a dump with
the host's whole environment, were deleted. So were the 14 empty directories and
12 logs. No fork `chrome.exe` process was left running.

## Not established

Whether Linux dumps carry the environment too. Crashpad writes dumps there
(`2026-09-09-sp7-phone-home.md:40`); their content is unmeasured.

`build-verify` does not run on this PR or on its merge: it touches only `docs/`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-12"></a>
## #12 Windows: the Python client runs, sandboxed, with a chunked identity

`step1/windows-python-client` into `main`, opened 2026-10-03T08:21:22Z, merged 2026-10-03T08:37:58Z.

The Python client runs on Windows. This is the first time `client/python` itself ran on the Windows host, against the same 153 `chrome.exe`. Before this, every Windows row had driven the browser through `lib_shell`.

No build. The client changes are: one real bug fix (temp profiles were never removed on Windows), the probe learning to read a Windows argv, and a guard on a failed `goto`. Everything else is in verify scripts and tests.

## What broke on Windows, each seen failing first

| Where | On Windows | Fix |
|---|---|---|
| `camoucrome.probe.browser_argv` | listed `/proc`, so every probe raised after the page had loaded: launcher verify **0 PASS 5 FAIL** | reads `Win32_Process` and splits with `CommandLineToArgvW` |
| `launch()` temp profile | the context's `close` event fires while the browser is still writing its profile, so `rmtree(ignore_errors=True)` left **3–193 files in every temp profile** (21 client profiles after one afternoon) | `remove_dir` retries until the directory is gone, bounded at 10 s |
| probe on a failed `goto` | never reached `ctx.close()`, so the profile stayed (152 files from the L3 RED row) | `try/finally` |
| `layout().py` | `<venv>/bin/python3` | `Scripts\python.exe` on `nt` (the same shape as `_binaries`) |
| driver verify Python rows | `{venv}/bin/python3` built by hand | `layout()` |
| driver verify C4 | `absent=['--noerrdialogs', '--ozone-override-screen-size=800,600', '--ozone-platform=headless', '--use-angle=swiftshader-webgl']` | these four are Linux-only; see below |
| `test_launcher.py`, `test_gen.py` | a `/`-joined suffix; an empty `zoneinfo` database (no `tzdata`) | compare the whole path; skip with a reason |

**Why C4 differs.** `headless_mode_init.cc` appends `--noerrdialogs` to the *in-process* command line on every OS. The ozone and ANGLE flags sit inside `#if BUILDFLAG(IS_LINUX)`. Linux shows `--noerrdialogs` only because Chromium rewrites its process title. On Windows, `Win32_Process.CommandLine` is the command line the driver passed. The strict-abort crash below shows the in-process addition directly:

```
[pid=16744][err]   "switch-6" = "--noerrdialogs"
[pid=16744][err]   "num-switches" = "6"
```

**Why a retry rather than another fix.** After `ctx.close()` returns, a single `rmtree` succeeds:

```
run 0: gone=True after 0.08s tries=1 first_err=None
run 1: gone=True after 0.06s tries=1 first_err=None
run 2: gone=True after 0.06s tries=1 first_err=None
run 3: gone=True after 0.08s tries=1 first_err=None
run 4: gone=True after 0.06s tries=1 first_err=None
```

The race is between the event and the browser's exit, and it lasts about 70 ms.

## Evidence on the Windows host

Setup: the client requires Python ≥3.10 and patchright 1.62.3. The host had only Python 3.9. I unpacked the official CPython 3.12.10 NuGet package into `D:\camou-win\python312`: no installer, no registry, no PATH change. SHA-256 is in the measurement doc.

RED, launcher verify before the probe fix:
```
FileNotFoundError: [WinError 3] The system cannot find the path specified: '/proc'
0 PASS 5 FAIL
```

GREEN at `455ca2b`:
```
pytest -q client/python/tests     39 passed
verify_sp6b_launcher.py           5 PASS 0 FAIL / ALL_PASS
verify_sp6b_driver.py
PASS  python-stock (expected RED)      C1 Runtime.enable=1; C5 +17/+21/+26% over three runs
      ok   C4 argv == launcher.json expected set: hits=[] unexpected=[] absent=[] argc=7
PASS  python-patchright (expected GREEN)  C1-C6 ok; C5 +0/+2/+2%
      ok   C4 argv == launcher.json expected set: hits=[] unexpected=[] absent=[] argc=7
FAIL  go-*, node-*: probe did not run   (no Go probe, no driver dirs on the host; expected)
client profiles left in %TEMP% after all of it: 0
```

C5 is SP2 D1's stack-timing signal. On Windows, as on Linux, stock Playwright's `Runtime.enable` costs about 20% on `new Error().stack`, and patchright removes that cost.

### New: `scripts/verify_windows_client.py`, the launch a user actually makes

Every probe row passes `--no-sandbox`, so none of them exercises a real `camoucrome.launch()` on Windows. A real launch puts the renderer behind `CreateFilteredEnvironment()`, and a generated identity is too long to fit in one environment string.

```
note: K1: 37387 chars -> 2 chunks, CAMOU_CONFIG present=False
note: K2: argc=6 --no-sandbox=False
note: K3: main -> 3 (expect 3)
note: K4: worker -> 3 (expect 3)
note: K5: no config -> 16 (expect anything but 3)
5 PASS 0 FAIL
```

The checked key is the identity's last, so it lives in the last chunk, and the launch is strict. RED, with `config_env` patched to drop the last chunk:

```
ERROR:components\camoucfg\mask_config_internal.cc:85] camoucfg: configuration is not a JSON object; ...
FATAL:components\camoucfg\mask_config_internal.cc:88] Check failed: !strict. ...
K1: FAIL  K2: FAIL  K3: FAIL  K4: FAIL  K5: PASS
1 PASS 4 FAIL
```

## Linux is unchanged (build box, branch code, 154 `chrome`)

The branch was archived from the runner's clone into `/tmp/camou-br-tree`, with `PYTHONPATH=<tree>/client/python` placed first. The CI client copy was not touched. Import origin:

```
/tmp/camou-br-tree/client/python/camoucrome/launcher.py True True   # remove_dir, windows_argv present
```

```
pytest -q client/python/tests   39 passed
verify_sp6b_launcher.py         5 PASS 0 FAIL / ALL_PASS
verify_sp6b_driver.py           ALL_PASS — all six drivers; C4 absent=[] argc=11 (Linux keeps its four self-added flags)
```

On the Mac: `pytest -q client/python/tests scripts/` gives **99 passed**, `test_lib_shell_launch.py` gives **20 PASS**, and `go test ./...` passes. The new `layout()` row was mutation-checked: with the old `/bin/python3` restored, the result is `1 FAILED of 20`.

## Not in this PR

- `verify_windows_client.py` is in no CI job. It can only run on the Windows host, which no workflow reaches. The same holds for `verify_windows_sandbox_env.py`.
- The Go and Node clients on Windows.
- Whether a crash dump lands in a client profile. That is the next PR (backlog item 5), which will build its crash-dir cleanup on `remove_dir`.
- The verify scripts' own temp dirs (`camoucrome-base-*`, the launcher's work dir) are never removed, on every OS. Pre-existing; I recorded it and did not fix it.
- Two other hardcoded `bin/python3` paths, in `measure_sp7_components.py` and `verify_sp1a_chrome.py`. Neither ran here.

`checks` on this branch: see below.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-13"></a>
## #13 Clients: crash dumps go to a temp dir each launch removes (backlog item 5)

`step1/windows-crash-dumps` into `main`, opened 2026-10-03T08:32:13Z, merged 2026-10-03T08:42:55Z.

The client-side fix for backlog item 5. Crash dumps carry the identity's config: the whole environment block, `CAMOU_CONFIG` verbatim, measured in #11. With this PR they no longer land in the profile.

**Stacked on #12.** The base is `step1/windows-python-client`, because the removal goes through #12's `remove_dir`. Once #12 merges, retarget this PR to `main`.

## The change

Chrome's `GetCrashDumpLocation` checks `BREAKPAD_DUMP_LOCATION` first and only falls back to `<user-data-dir>\Crashpad` when it is unset (`chrome/app/chrome_crash_reporter_client_win.cc:116-128`, read on the host's 153 tree). The POSIX client reads the same variable. So no C++ change is needed for launches that go through a client.

In all three clients (Python, Go, Node), every launch now:
- creates a temp `camoucrome-crash-*` directory;
- points `BREAKPAD_DUMP_LOCATION` at it;
- removes it when the context closes or the launch fails.

This holds for a **kept** profile too. Kept profiles were the real gap: temp profiles already took their dumps with them. The parent's `BREAKPAD_DUMP_LOCATION` is never inherited, the same as `FONTCONFIG_FILE`, because it would collect every identity's dumps in one place. Removal retries through the close-event race #12 measured: `remove_dir` in Python, a bounded `removeDir` in Go, `fs.rm` with `maxRetries` in Node. The contract gains `launch.crash_dumps`, and each client's tests assert they agree with it.

## Evidence

Unit tests, each written RED first:
```
python  pytest -q client/python/tests scripts/   100 passed   (RED: KeyError 'crash_dumps')
go      go vet ./... && go test ./...             ok           (RED: undefined: removeDir)
node    npm test                                   pass 13      (RED: not ok 13)
```
The new tests cover four things: the contract parity of the env name; that the parent's value is never inherited; that a kept profile's launch gets a crash dir outside the profile, removed on close while the profile stays; and that the crash dir is removed on a failed launch. Test-side `mkdtemp`s go under pytest's `tmp_path`, so CI's `/tmp` stays clean (checked: before 8, after 8).

**Windows host** (153 `chrome.exe`). The setup is a kept profile, config `{"ua:osInfo": "ZQXJ7731MARKER"}`, and a renderer crash via `page.goto("chrome://crash")`. Dumps were searched for the marker as UTF-16.

RED, #12's client:
```
client redirects crash dumps: False
mid-session: kept profile dumps 1 marker True
mid-session: crash dirs 0 dumps 0 marker False
after close: kept profile dumps 1 | Crashpad dir in profile: True
```

GREEN, this branch, three runs alike:
```
client redirects crash dumps: True
mid-session: kept profile dumps 0 marker False
mid-session: crash dirs 1 dumps 1 marker True
after close: kept profile dumps 0 | Crashpad dir in profile: False
after close: crash dirs left 0
leftover camou dirs: 0
```

New in this measurement: a **renderer** dump carries the identity too. #11 only showed it for a browser-process crash.

**Linux box** (154 `chrome`). The branch was archived from the runner's clone, with `PYTHONPATH=<tree>/client/python`; the CI client copy was not touched.
```
pytest -q client/python/tests      40 passed
node --test (node v24.18.1)        pass 13
crash probe                        crash dirs 1 dumps 1 → after close: crash dirs left 0; no Crashpad in the profile
verify_sp6b_launcher.py            5 PASS 0 FAIL / ALL_PASS
verify_sp6b_driver.py              ALL_PASS, all six drivers (python/go/node × stock/patchright)
/tmp/camoucrome-crash-* before/after   0 / 0
```
The Linux renderer dump did **not** contain the marker, as ASCII or as UTF-16. That is one crash of one process type, and it is recorded as exactly that.

## Not in this PR

- **Launches that bypass the clients.** `chrome.exe` run by hand still writes to `<profile>\Crashpad`. The C++ lever (crashpad not initialising in the fork) needs a Windows build on the current pin, so it goes with the 2026-10-20 re-pin. Backlog item 5 now says so.
- **A killed client process.** No close event runs, so the crash dir stays in temp, dumps included.
- **Go and Node on Windows.** Unit-tested, and run on the Linux box only.

`checks` on this branch: see below.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-14"></a>
## #14 Verify runs remove the temp profiles they create; CLAUDE.md names the Node client

`step1/cleanup-temp-dirs` into `main`, opened 2026-10-03T09:06:36Z, merged 2026-10-03T09:41:55Z.

Verify runs now remove the temp profiles they create. CLAUDE.md now names the Node client.

## The bug

Sweeping the hosts turned up two sources of leftover profiles.

1. **`lib_shell.launch()` with a missing binary.** The profile was created first, then `Popen` raised when the binary did not exist, and nothing removed it. A missing binary is exactly how a RED run is made (a wrong `CAMOU_OUT`). This left the 14 empty `camoucrome-verify-*` directories found on the Windows host on 2026-10-03; their timestamps (13:30, 14:23, 14:31, 14:35 host time) match that day's RED runs one for one. The profile is now removed when `Popen` raises. `shutdown()` is unchanged: three real sandboxed launches on Windows leave nothing, on main and on this branch alike.
2. **Five scripts never removed their own temp dirs:**
   - `verify_sp6b_driver.py` (`camoucrome-base-*`, one per baseline run)
   - `verify_sp6b_launcher.py` (`camoucrome-launcher-*`)
   - `verify_sp7_phonehome.py` (`camoucrome-p4-*`; the diff is mostly re-indentation, see `git diff -w`)
   - `measure_sp2b_attach.py`, `measure_sp2b_stack.py`

One item from the earlier list was dropped: "hardcoded `bin/python3`" in `measure_sp7_components.py` and `verify_sp1a_chrome.py`. Both occurrences are text, a docstring and a hint inside an error message, and neither is a path that runs.

## Evidence

**Unit test, written RED first** (`scripts/test_lib_shell_launch.py` §9, a launch with a missing binary):
```
main's lib_shell:   1 FAILED of 21: a launch whose binary is missing leaves no profile behind
this branch:        21 PASS
pytest -q client/python/tests scripts   100 passed
```

**Windows host** (`chrome.exe`, `verify-venv` Python 3.9; each tree `git archive`d from the runner's clone):
```
main | missing binary x3: ['FileNotFoundError', 'FileNotFoundError', 'FileNotFoundError'] profiles left: 3 | real launch x3: profiles left: 0
br   | missing binary x3: ['FileNotFoundError', 'FileNotFoundError', 'FileNotFoundError'] profiles left: 0 | real launch x3: profiles left: 0
```

**Linux box.** Each tree was archived from the runner's clone and run with `PYTHONPATH=<tree>/client/python`. The count is of `/tmp/camoucrome-launcher-*` and `/tmp/camoucrome-base-*`.
```
== main f66a9c6
verify_sp6b_launcher rc=0 last='ALL_PASS' temp dirs before=28 after=29
verify_sp6b_driver   rc=0 last='ALL_PASS' temp dirs before=29 after=32
== br 724a40e
verify_sp6b_launcher rc=0 last='ALL_PASS' temp dirs before=32 after=32
verify_sp6b_driver   rc=0 last='ALL_PASS' temp dirs before=32 after=32
```
Neither phonehome nor the two `measure_sp2b` scripts was run. Phonehome needs live traffic to google.com, and the measure scripts are one-off SP2b measurements. For all three, the evidence is that they compile, pass pyflakes, and have a reviewed diff.

## Found while measuring, not fixed here

All three clients leak their temp profile and crash dir on Linux. The `close` event fires while the browser is still shutting down. The client removes both directories, and the browser then re-creates them: 8 profile files written at shutdown, plus an empty crash dir. At the moment `ctx.close()` returns, no process still names the profile and both dirs exist again. The box's `/tmp` holds 518 such profiles, the newest from after #13 merged. This also means #13's Linux line "after close: crash dirs left 0" was measured too early. It needs its own fix and its own PR.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-15"></a>
## #15 Clients remove the temp profile and crash dir once close() returns; commit the Go probe

`step1/close-removes-after-exit` into `main`, opened 2026-10-03T09:22:17Z, merged 2026-10-03T09:42:00Z.

On Linux, all three clients left their temp profile and crash dir behind after every `close()`. They now remove both again once `close()` returns. This PR also commits the Go probe's source, which `.gitignore` had kept out of the repo.

## The bug

The context's `close` event fires while the browser is still shutting down. Traced in-process on the box with the Python client:
- `remove_dir` ran on the event, and both directories were gone right after it.
- 3 s later both existed again: the profile with 8 files (`Default/Network Persistent State`, `Default/Trust Tokens`, ...), and the crash dir empty, re-created by crashpad.
- When `ctx.close()` returns, no process names the profile in its argv, and both directories are already back. A removal at that point stays final.

The box's `/tmp` held 518 such profiles plus their crash dirs, the newest written after #13 merged. This also means #13's Linux line "after close: crash dirs left 0" was read too early; the measurement doc now says so in an amendment.

## The change

- **Python** (`removed_on_close`): `ctx.close` is wrapped for both the sync and the async API. A check on the box's patchright shows `iscoroutinefunction` is `True` for `async_api.BrowserContext.close` and `False` for the sync one, so the right branch is taken.
- **Go:** `Launch` returns a `closingContext` that embeds `playwright.BrowserContext` and overrides `Close`.
- **Node:** `ctx.close` is overridden.

All three keep the removal on the event too, because for a browser that crashed or was killed the event arrives after the process is gone.

Also in this PR:
- `client/go/.gitignore` said `camoucrome-probe`, meant for the built binary, and git applied it to `cmd/camoucrome-probe/` as well. So the Go probe behind two of `verify_sp6b_driver`'s six rows was **never in the repo**, and a fresh clone could not build it. The pattern is now anchored (`/camoucrome-probe`) and `main.go` is committed unchanged.
- The Node tests now remove the two `camou-fc-*` scratch roots they created on every run.

## Evidence

**Unit tests**, each written RED first. Each fake's `close()` re-creates the directories after the handler ran.
```
python  pytest -q client/python/tests       42 passed   (mutation: launcher reverted -> 2 failed, 40 passed)
go      go vet ./... && go test ./...        ok          (mutation: no remove in Close -> FAIL ... still there after Close returned)
node    node --test test/launcher.test.js    pass 14     (mutation: index.js reverted -> not ok 14)
node    camou-fc-* scratch dirs per run      main +2, branch +0
```

**Linux box**, in-process repro per client: 3 temp-profile launches, `about:blank`, close, wait 3 s, then count what is left of the 6 directories created. Each tree was `git archive`d from the runner's clone.
```
== main f66a9c6
python | launches 3, dirs created 6, left 3 s after close: 6
node   | launches 3, dirs created 6, left 3 s after close: 6
go     | launches 3, dirs created 6, left 3 s after close: 6
== br 252bdaa
python | launches 3, dirs created 6, left 3 s after close: 0
node   | launches 3, dirs created 6, left 3 s after close: 0
go     | launches 3, dirs created 6, left 3 s after close: 0
```

**Linux box, no regression**, from the branch tree. The Go probe was built from the newly committed source.
```
go test ok | node pass 14 | pytest 42 passed
verify_sp6b_driver   rc=0 ALL_PASS: python/go/node x stock(RED)/patchright(GREEN), six rows PASS; client temp dirs 522 -> 522
verify_sp6b_launcher rc=0 ALL_PASS: L1-L5 PASS;                                                    client temp dirs 522 -> 522
```

**Windows host** (`chrome.exe`, sandboxed, Python client, same repro: temp profile, no crash):
```
main   | launches 3, dirs created 6 left 3 s after close: 0
branch | launches 3, dirs created 6 left 3 s after close: 0
```
On Windows `remove_dir` keeps retrying for as long as the browser holds its files, which lasts until the process exits, so the leak was only ever measured on Linux. This row shows the change causes no regression on Windows. #13's kept-profile crash case was not re-run with a wait.

**Cleanup**, with approval and after the evidence above was taken: 604 leaked `/tmp/camoucrome-*` and `camou-fc-*` directories (113 MB) were removed from the box. None remain.

## Not established

- **A driver stopped without `close()`.** `pw.stop()`, the end of a `with sync_playwright()` block, or `ctx.browser.close()` take the browser down while only the event removal runs, and on Linux that one is early.
- **Go identity.** `page.Context()` returns the driver's own context, so it no longer `==` the value `Launch` returned.
- **Go and Node on Windows.** That is the next PR.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-16"></a>
## #16 Go and Node clients on Windows: probes read Win32_Process, run sandboxed, take a file config

`step1/windows-go-node` into `main`, opened 2026-10-03T09:35:29Z, merged 2026-10-03T09:42:15Z.

The Go and Node clients now run on Windows, measured on the host the same way the Python client was.

**Stacked on #15.** The base is `step1/close-removes-after-exit`, because the Go probe's source is first committed there. Once #15 merges, retarget this PR to `main`.

## The change

- **Probes read argv on Windows.** Both probes read the browser's argv from `/proc` only, so on Windows the Node probe threw and the Go probe returned no argv without any error. Both now read `Win32_Process` and split the command line with `CommandLineToArgvW`:
  - Go: through `syscall`, in a `//go:build windows` file. The `/proc` reader moves to `argv_other.go` unchanged.
  - Node: through PowerShell, which receives the script `-EncodedCommand` so no quoting has to survive.

  Like the Python probe, both skip a null command line and any `--type=` child.
- **`--sandbox`** drops the probes' `--no-sandbox`, the one argv under which the Windows sandbox's environment filter is invisible.
- **`--config @path`** reads the config from a file, because the generated 37 KB identity is past Windows' 32767-char command line. Go also gains `--strict`.
- **`verify_windows_client.py`** repeats K2-K4 through the Go and Node clients, as rows G2-G4 and N2-N4: 11 rows in all. Their probes read a page that writes both values into `#o` once the worker has answered.
- **Two unit tests** built expected paths with `/`, one in Go and one in Node, and failed on Windows on the separator alone. This is the first time either suite ran there.

## Evidence (Windows host, 153 `chrome.exe`)

**Unit suites on the host:** Go `ok` (vet clean), Node `pass 14 fail 0`, Python `42 passed`.

**`verify_windows_client.py`, GREEN:**
```
note: K1: 37387 chars -> 2 chunks, CAMOU_CONFIG present=False
note: G2: argc=6 --no-sandbox=False      note: N2: argc=6 --no-sandbox=False
note: G3: main -> 3 (expect 3)           note: N3: main -> 3 (expect 3)
note: G4: worker -> 3 (expect 3)         note: N4: worker -> 3 (expect 3)
note: K5: no config -> 16 (expect anything but 3)
11 PASS 0 FAIL
exit 0
```

**RED.** The Go probe was built from a copy of the tree in which the Go and Node clients drop the last config chunk. Under strict the config is then unparseable, the browser exits, and both probes fail. The Python K rows are untouched:
```
note: G2: argc=0 --no-sandbox=False; JSONDecodeError: ... ['  - [pid=22932] <gracefully close end>']
note: N2: argc=0 --no-sandbox=False; JSONDecodeError: ... ['  - [pid=19004] <gracefully close end>']
5 PASS 6 FAIL
exit 1
```

**`verify_sp6b_driver.py`, all six drivers on the host:**
```
PASS  python-stock  (expected RED)     C1 Runtime.enable=1   C5 +22%
PASS  python-patchright (GREEN)        C1 Runtime.enable=0   C5 +4%
PASS  go-stock      (expected RED)     C1 Runtime.enable=1   C5 +21%
PASS  go-patchright (GREEN)            C1 Runtime.enable=0   C5 +4%
PASS  node-stock    (expected RED)     C1 Runtime.enable=1   C5 +21%
PASS  node-patchright (GREEN)          C1 Runtime.enable=0   C5 +5%
ALL_PASS
```
The log carries one `ConnectionAbortedError` traceback, raised by the verify's own page server when a client dropped a connection; no row depends on it.

Leftovers 3 s after the runs: no client profile and no crash dir. There were 3 `camoucrome-base-*`, the driver verify's own baseline profiles, which #14 fixes (that fix is not on this branch).

**Linux box, no regression** (branch tree, Go probe built from it):
```
verify_sp6b_driver rc=0 ALL_PASS, six rows; client temp dirs 0 -> 0
go vet/test ok | node pass 14 | pytest client/python/tests scripts: 98 passed, 4 failed
```
Those 4 failures are `test_package.py`, identical on main under the same invocation (`main: 4 failed, 96 passed`). They come from running a `git archive` tree that has no `.git`, and they are not a regression.

## Host changes, each approved

- Go 1.27.1 at `D:\camou-win\go`, from go.dev's zip; its SHA-256 matched the published value.
- `D:\camou-win\driver-patchright` and `driver-stock`: playwright-go only accepts a driver whose `--version` contains `1.62.1`, while the host's patchright driver is 1.62.3. These are the box's `patchright-core`/`playwright-core` 1.62.1 packages (pure JS), copied over UNC, each beside `client-venv`'s `node.exe` (v24.18.1).
- `D:\camou-win\probes\green\camoucrome-probe.exe`, built from this branch. `D:\camou-win\tree` now holds this branch.

## Not established

- **Fonts.** No `FONTCONFIG_FILE` path was exercised on Windows.
- **Windows CI** (backlog item 8). This host run was done by hand.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-17"></a>
## #17 feat(client): a kept profile keeps its seeds

`step3/profile-seeds` into `main`, opened 2026-10-03T12:26:29Z, merged 2026-10-04T02:32:29Z.

## What

A kept profile now keeps its noise seeds. `profile_seeds(user_data_dir)` (Go `ProfileSeeds`, Node `profileSeeds`) draws `canvas:seed`, `audio:seed` and `mediaDevices:seed` once into `<user_data_dir>/camoucrome-seeds.json` and reads them back on every later launch.

Before this, every launch drew fresh seeds even when the profile was kept, so the same profile showed a different canvas, audio and device-ID fingerprint each session. Step 2's "stability across relaunch" row would have failed on that alone.

- The file name is in `settings/launcher.json` (`per_instance_seeds.profile_file`). Each client's tests read it from there.
- Keys missing from the file are drawn and added. A damaged file (bad JSON, not an object, zero, out of uint32 range, a string, a bool, a float) is an error, never a silent redraw. The test asserts the file is left unchanged.
- The file is written to a temp file and renamed over the target.
- `launch()` is unchanged; the caller opts in with `config={**profile_seeds(udd), **mine}`. This was the design choice approved for this change.

## Evidence

RED first. Each client's new tests failed before the code existed:
- Python: `AttributeError: module 'camoucrome' has no attribute 'profile_seeds'` (1) and `KeyError: 'profile_file'` (7). Result: `8 failed, 42 passed`.
- Go: `undefined: ProfileSeeds` (build failed).
- Node: `c.profileSeeds is not a function` (3 tests). Result: `# pass 14`.

GREEN (macOS, Python 3.12.1, Go, Node 22):

```
python: 50 passed in 0.85s
go:     --- PASS: TestPerInstanceSeedsMatchTheContract
        --- PASS: TestProfileSeedsAreDrawnOnceAndReadBack
        --- PASS: TestProfileSeedsReadAnotherClientsFileAndDrawOnlyTheMissingKeys
        --- PASS: TestProfileSeedsRefuseADamagedFileRatherThanRedraw
        ok  github.com/lang315/camoucrome/client/go
node:   ok 6 - profile seeds are drawn once and read back
        ok 7 - profile seeds read another client's file and draw only the missing keys
        ok 8 - profile seeds refuse a damaged file rather than redraw
        # pass 17  # fail 0
```

Cross-client, on one real profile directory:

```
python writes {"audio:seed": 3118228282, "canvas:seed": 3880845331, "mediaDevices:seed": 4167183280}
go reads      {"audio:seed":3118228282,"canvas:seed":3880845331,"mediaDevices:seed":4167183280} <nil>
(node, earlier run on another python-written file) node reads == python writes == python again
```

## Not measured here

- **In a browser.** That a relaunched profile reports the same canvas and audio hashes is Step 2's stability row. These tests prove only that the same seeds reach `CAMOU_CONFIG`.
- **On the build box.** The box is busy with the overnight Windows build. CI runs these suites on the next push to `main`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-18"></a>
## #18 feat(box): one build at a time across the WSL checkout and the Windows tree

`step1/build-lock` into `main`, opened 2026-10-03T12:29:09Z, merged 2026-10-04T02:28:05Z.

## What

One Chromium build at a time on the build PC. The WSL checkout (CI) and the native Windows tree share one machine, and neither can see the other's processes: WSL interop is off, and CI's `pgrep ninja` guard sees only WSL. On 2026-10-03 an unattended overnight Windows build was running that a CI push could have raced, and nothing on the WSL side would have known.

`scripts/build_lock.sh` is a `mkdir` lock at `~/.camou-build.lock` in WSL. It takes three commands: `acquire <owner>`, `release <owner>` and `status`.
- `acquire` refuses while a ninja runs in the WSL checkout, or while anyone holds the lock. When it refuses, it names the holder and the start time.
- Only the owner can release the lock.
- CI's guard step now runs `status`. The build step takes the lock and drops it on exit through `trap`.
- The Windows side calls the script with `wsl -u <user> -e bash ~/camoucrome-client/scripts/build_lock.sh ...` (absolute: the drill used an absolute path, and how PowerShell passes a bare `~` to `wsl.exe` was not measured). That copy is rsynced by CI, so it exists once this PR merges.

This PR delivers both halves of the Step 1 item "the Windows change loop … and a lock so the WSL and Windows builds never overlap". The second commit adds the written procedure to `specs/repin-runbook.md` §7, which replaces the "procedure … is still owed" sentence.
- **Re-pointing the tree to a new pin.** Every step of the 153 → 154 run, with its measured time and the trap it hit:
  - fetch `--depth=1`: 6 min (without `--depth=1` it hung);
  - `gclient sync -j 4 --no-history` with `DEPOT_TOOLS_UPDATE=0`: 21 min (HTTP 429 at 16 jobs);
  - `apply.sh` under Git Bash: 12 s, 32/32;
  - `gn gen`: 12 s;
  - build: 5 h 31 m, 57,101 steps.
- **The change loop.** Export on WSL → take the lock → `git apply --3way` only the changed patch (not a full re-apply, which rewrites all 130 files) → build, with a non-zero step count → verify, RED first → release the lock. Measured on the crashpad change: **8 steps, 25.68 s**.

## Evidence

RED first: `7 failed` before `build_lock.sh` existed.

GREEN on macOS:
```
test_a_second_build_is_refused_and_told_who_holds_the_lock PASSED
test_only_the_owner_releases_the_lock PASSED
test_a_running_ninja_refuses_the_lock PASSED      (a real process with "ninja -C out/Default" as its command line)
test_usage_errors_exit_2[args0..args3] PASSED
7 passed in 0.57s
```

GREEN on the build box's WSL (archive of `047ae86`, box venv): `7 passed in 23.52s`. The run was slow because the Windows build had the CPU.

From the Windows side, through `wsl.exe`, against the real lock path:
```
acquired by windows drill                                                   exit 0
refused: the build lock is held by windows drill since 2026-10-03T12:28:44Z exit 1   (acquire 'ci run 0')
held by windows drill since 2026-10-03T12:28:44Z                            exit 1   (status)
released by windows drill
free                                                                        exit 0
```

## Not covered

- **CI holding the lock in a real run.** That happens on the next `build-verify` run after merge. The YAML parses, but the workflow steps did not run here.
- **The overnight pipeline running now.** It predates this lock and does not take it. Do not merge anything that triggers `build-verify` until it finishes (around 02:00 VN), or the two builds will run at once.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-19"></a>
## #19 docs: settle the release gates -- MPL-2.0, codecs shipped, unsigned, acceptable use

`step3/release-gates` into `main`, opened 2026-10-03T12:30:32Z, merged 2026-10-04T02:36:50Z.

## What

The project owner decided three of Step 3's four release gates on 2026-10-03. The fourth (acceptable use) is drafted here for review.

| Gate | Decision | Where it is recorded |
|---|---|---|
| LICENSE | MPL-2.0, the same as Camoufox and `client/node/package.json` | `LICENSE` (canonical text), `client/python/pyproject.toml` |
| Codecs | Released binaries ship H.264/AAC; the patent exposure is accepted and stated | `settings/build-args.gn` comment, `ACCEPTABLE_USE.md`, roadmap |
| Code signing | Unsigned for the first release; the README explains SmartScreen | roadmap |
| Acceptable use | Draft for the owner to review | `ACCEPTABLE_USE.md` |

The roadmap's release-gates block now records each decision and the option it beat.

It also names a gap this surfaced: `package.py` packs no license file, and a Chromium binary must carry Chromium's `LICENSE` and its third-party notices (`about:credits`). That is listed as owed before any binary release; it is not fixed here.

## Evidence

- `LICENSE` is byte-identical to https://www.mozilla.org/media/MPL/2.0/index.txt (SHA-256 `3f3d9e0024b1921b…`, 373 lines).
- **The licence field.** The first commit declared `license = {text = "MPL-2.0"}`. Built the way CI builds (isolated, which pulls setuptools 84.0.0) on the box, that form printed `SetuptoolsDeprecationWarning: project.license as a TOML table is deprecated ... By 2027-Feb-18` three times. The second commit switches to the PEP 639 string `license = "MPL-2.0"` with `requires = ["setuptools>=77"]`. Rebuilt with setuptools 84.0.0: `exit 0`, **0** warning lines, and the wheel's METADATA carries `License-Expression: MPL-2.0`.
- No script or workflow reads `settings/build-args.gn` byte for byte (`git grep "build-args.gn" -- scripts .github` finds nothing). The change there is comments only, and no GN arg moved.

Not legal advice. The codec and licence decisions are the owner's.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-20"></a>
## #20 feat(crash): the crashpad handler never writes a report

`step1/crashpad-no-dumps` into `main`, opened 2026-10-03T22:33:21Z, merged 2026-10-04T02:23:12Z.

## What

Closes backlog item 5. Before this, any crash of a fork process made crashpad write a minidump holding the process's whole environment, `CAMOU_CONFIG` (the identity) included. The client lever (PR #13) covered launches through the clients. This covers every launch: a browser started by hand or by another tool, and a client killed before its close event.

- **`patches/crashpad-no-dumps.patch`:** one call in `components/crash/core/app/crashpad.cc` `InitializeCrashpadImpl`, `CrashpadInfo::GetCrashpadInfo()->set_crashpad_handler_behavior(TriState::kDisabled)`. The handler skips the report write and still terminates the process with the exception's own code. That is the check at `handler/win/crash_report_exception_handler.cc:82`; Linux has it at `handler/linux/capture_snapshot.cc:63`, and macOS honours it too. The handler process still starts, no WER involvement, same exit codes. Exported from the box branch, where the commit subject is `crashpad-no-dumps`; the patch hash matches the export.
- **The roadmap's named lever was wrong.** `GetCrashDumpLocation` returning empty still lets `crashpad_win.cc:151` start the handler with an empty database. The handler fails, and crashes then fall to Windows Error Reporting, outside the profile and possibly uploaded.
- **`scripts/verify_crash_dumps.py`:** launches through `lib_shell` with no client and no `BREAKPAD_DUMP_LOCATION`, and a marker in the config. It crashes the renderer (C1, `chrome://crash`) and the browser (C2, `Browser.crash`). It then searches the profile, `%TEMP%`, the default crash database, `%LOCALAPPDATA%\CrashDumps` and both WER stores for new dumps and for the marker.
  - A row passes only if the crash is seen and nothing new is found.
  - A crash that never happens is `NOT MEASURED`, never PASS. The first draft's C2 trigger, `chrome://inducebrowsercrashforrealz`, did nothing under `--headless`, and the row said so.
- **CI:** `build-verify` runs `verify_crash_dumps.py`.
- **Docs:**
  - The measurement doc gains a section, "The crashpad lever".
  - Backlog item 5 is marked closed.
  - The roadmap ruling that kept the Windows tree on 153 is marked superseded: the tree is now 154.

## Evidence

| Binary | Run | C1 renderer | C2 browser (exit code) |
|---|---|---|---|
| Linux 154 (box), before | RED | FAIL: 1 dump in `~/.config/chromium/Crash Reports/pending/` | FAIL: 1 dump (-6) |
| Linux 154, lever (6 steps, 22 s) | GREEN ×2 | PASS: 0 dumps | PASS: 0 dumps (-6) |
| Windows 153, old binary | RED | FAIL: 1 dump in `<profile>\Crashpad\reports`, marker 1 | FAIL: 1 dump, marker 1 (`0x80000003`) |
| Windows 154, before | RED | FAIL: 1 dump, marker 1 | FAIL: 1 dump, marker 1 (`0x80000003`) |
| Windows 154, lever (8 steps, 25.68 s) | GREEN ×2 | PASS: 0 dumps, marker 0 | PASS: 0 dumps, marker 0 (`0x80000003`) |

Windows 154 build: `chrome.exe 154.0.8037.93`, `Build Succeeded: 57101 steps` in 5 h 31 m. The change set from `main` applied 32/32.

Same Windows binary, client verifies:
- `verify_windows_client.py`: `11 PASS 0 FAIL`; `%TEMP%` `camoucrome-*` left: 0.
- `verify_sp6b_driver.py` in the overnight run: **FAIL**. The `go-patchright` C5 stack timing was +22% against a 15% bound; it ran straight after the 5.5 h build, and the same run had Python at -2% and Node at +9%.
- Re-run three times on the idle host (CPU 1%): **ALL_PASS ×3**. Patched C5 values were +7% to +10%; the stock rows were +25% to +27% (RED as expected).

The FAIL is recorded in the measurement doc as load sensitivity of a timing check, not dropped.

## Not measured

- **macOS:** not built here; only the source check above.
- **The GPU-process crash path, `DumpWithoutCrashing` and hung-renderer dumps:** covered by the same switch in source, not crashed on purpose.
- **CI:** CI runs the new verify only after merge. Merge this PR **first** of the open ones, because the box branch already carries `crashpad-no-dumps` and `check_checkout_sync.sh` fails the others until it lands.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-21"></a>
## #21 docs: drop the acceptable-use statement, move the codec notice to the README

`step3/acceptable-use-review` into `main`, opened 2026-10-04T03:01:49Z, merged 2026-10-04T03:23:15Z.

The owner decided against an acceptable-use statement. This removes `ACCEPTABLE_USE.md` (added as a draft in #19) and keeps the one part a release gate depends on.

- **`ACCEPTABLE_USE.md` deleted.** MPL-2.0 governs copying and modification and carries its own warranty disclaimer (sections 6 and 7 of `LICENSE`), so nothing licence-related is lost.
- **Codec notice moved to the README**, new section "Licence and codecs". It is the step 3 codec gate's required statement of the H.264/AAC patent exposure. It carries two fixes from reviewing the draft:
  - The opt-out names both GN args. The draft said only `proprietary_codecs = false`, but `settings/build-args.gn` also sets `ffmpeg_branding = "Chrome"`. Their defaults, read from `gn` on the build box's WSL tree:
    ```
    proprietary_codecs
        Current value = true
          From //out/Default/args.gn:7
        Overridden from the default = false
    ffmpeg_branding
        Current value = "Chrome"
          From //out/Default/args.gn:8
        Overridden from the default = "Chromium"
    ```
  - It says it is not legal advice, as `build-args.gn` does.
- **Roadmap changes:**
  - The acceptable-use gate reads "Decided 2026-10-04: none."
  - The codec gate points to the README.
  - The risk table's takedown row no longer lists the statement as a response.
- **Roadmap snapshot dated.** "Where the project stands" is a 2026-10-02 snapshot and now says so. Three of its bullets point to the step that records what changed since: the LICENSE and codec decisions (step 3) and the Windows tree's move to 154 (step 1).

Evidence that no reference is left: `git grep -n ACCEPTABLE_USE` returns nothing (exit 1).

Docs only. `build-verify` does not run: its `paths` filter is `patches/ additions/ settings/ scripts/ client/ upstream.env` and the workflow file, so this PR does not start a box build.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-22"></a>
## #22 Step 1 finished on Windows: named verify set, fonts on a Windows host, audio service, host oracle

`step1/windows-verify-set` into `main`, opened 2026-10-04T05:03:35Z, merged 2026-10-04T08:10:21Z.

Finishes roadmap step 1 on Windows. There is no Chromium build: everything ran against the fork's `chrome.exe` 154.0.8037.93 already built on the host, with the host's own stock Chrome 154.0.8037.93 as the control.

Spec: `docs/superpowers/specs/2026-10-04-step1-finish-design.md`. Plan: `docs/superpowers/plans/2026-10-04-step1-finish.md`. Measurements: `docs/superpowers/measurements/2026-10-04-windows-verify-set.md`.

## What changes
- **`scripts/lib_shell.py`**: `CAMOU_SHELL=chrome` makes `chrome` the default binary, with `CHROME_FLAGS` plus `--enable-logging=stderr`. When the variable is unset, the frozen argv is unchanged (`test_lib_shell_launch.py`: 24 PASS).
- **`scripts/windows_verify_set.py`** (new) is the named Windows verify set, 21 entries, with a runner.
  - `red` runs every entry against stock Chrome (`CAMOU_EXE`) and requires each one to exit non-zero with a FAIL row.
  - `green` runs the fork and requires each entry's asserted count.
  - It refuses to run if stock Chrome is not the pin's version or if `--only` names an entry it does not hold. A timeout marks that one entry BAD and the run continues.
  - An entry can declare known-failing rows (`known_fail`).
- **`scripts/verify_windows_fonts.py`** (new) has these rows:
  - F1: a host-only font is hidden.
  - F2 (once per client: Python, Go and Node): the four probed claimed families (Arial, Segoe UI, Times New Roman, Verdana) measure the same as stock, within the measureText jitter, and each wins over both fallbacks.
  - F4: system fallback measures the same as stock.
  - F3 (a measured count) and F5 are notes.
- **`scripts/verify_windows_sandbox_env.py`** gains audio-service rows A1 and A2, run under the real sandbox. A2 rejects the renderer's 44100 no-device fallback.
- **`scripts/verify_fonts_ii.py`** uses Windows host fonts on Windows.
- **`verify_host_oracle.py` and `verify_windows_fonts.py`** pass the identity by temp file instead of argv. A ~37 KB identity overflowed Windows' 32767-char command line.
- **Clients.** `settings/launcher.json` gains `launch.native_fonts`. The Python, Go and Node clients drop `fonts:alias` and `fonts:aliasLocal` when the claimed OS equals the host OS.
  - A config with nothing to drop passes through untouched.
  - A host OS the clients do not recognise never triggers the drop.
  - A Linux claim carries no alias keys (`fonts.json` `alias_map` has only Windows and macOS). Separately, a Windows or macOS claim on the Linux build box keeps its aliases, because the claimed OS differs from the host.
- **Docs**:
  - the measurement doc;
  - the roadmap: step 0 and step 1 done, a new backlog item for O2, new evidence for items 2 and 3;
  - runbook §7: how to release the held stock Chrome at the next re-pin.

## Evidence
### Host runs on `768982f` (the code head; the later commit is docs only)
```
v2-red.log    mode=red stock=154.0.8037.93 pin=154.0.8037.93 exe=C:\Program Files\Google\Chrome\Application\chrome.exe
              ... 21 x "OK  <script>: rc=1 N PASS M FAIL (want rc!=0 and a FAIL row)"
              21/21 entries OK (red)
v2-green1.log 21/21 entries OK (green)
v2-green2.log 21/21 entries OK (green)
              OK   verify_host_oracle.py: rc=1 3 PASS 1 FAIL (want 3 PASS and exactly the known-failing rows O2 FAIL)
```
The per-entry RED and GREEN counts are in the measurement doc's table.

### The font alias finding, before and after the client fix
```
before: note: F2 widths fork/stock: Arial=1807.99/1794.53; Segoe UI=1807.99/1808.06; Times New Roman=1807.99/1694.34; Verdana=1807.99/2057.67
after:  note: F2 widths fork mono|serif/stock: Arial=1794.64|1794.64/1794.53; Segoe UI=1807.99|1807.99/1808.06; Times New Roman=1694.46|1694.46/1694.34; Verdana=2057.71|2057.71/2057.67
        PASS  F2-py / F2-go / F2-node
```
The two-variant rule was also seen failing once. With Segoe UI aliased to a missing font, it measured `[1539.453125, 1694.3359375]` (the two bare fallbacks), `real_ok=False`. The unaliased control measured `[1808.056640625, 1808.056640625]`, `real_ok=True`.

### Audio service
```
note: A1: sandboxed + audio:sampleRate, AudioContext.sampleRate -> 22050 (expect 22050)
note: A2: sandboxed, no config, AudioContext.sampleRate -> 48000 (expect the device's own rate, not 22050 or the 44100 no-device fallback)
```

### Local suites at `4674631`
```
python3 scripts/test_lib_shell_launch.py              -> 24 PASS
pytest scripts/test_windows_verify_set.py scripts/test_verify_host_oracle.py client/python/tests -> 79 passed
cd client/go && go test -count=1 ./...                -> ok
node --test client/node/test/*.test.js                -> # pass 20 / # fail 0
python3 scripts/check_additions_build.py              -> PASS all 38 source files ... listed in BUILD.gn
python3 scripts/gen_keys.py --check                   -> PASS keys.h matches settings/keys.json (90 keys)
```

## Independent verification before merge (2026-10-04)
- **Linux box, branch head 4674631.** CI's steps were run against the branch tree, without touching the runner's clone or the CI verify dir:
  - pre-flight: additions 38 files PASS, keys 90 PASS, fontconfig PASS;
  - `test_lib_shell_launch.py`: 24 PASS;
  - pytest (CI's list plus `test_windows_verify_set.py` and `test_verify_host_oracle.py`): 117 passed. A first run showed 4 failures, all in `test_package` with `<tree> is not a git checkout`. That came from the archived tree; after `git init`, 10 of 10 package tests passed;
  - Go: ok. Node: pass 20, fail 0;
  - CI's browser verifies, all green: `sp1a_chrome`, `sp4_voices` 5/5, `fonts_bundle` 17/0, `host_oracle` 4/0 (O2 passes on Linux), `windows_behaviour` 14/0, `sp6b_generator` ALL_PASS, `crash_dumps` 2/0. Also `sp6b_launcher` and `sp6b_driver`, both ALL_PASS.
- **Windows host, PR head 4674631**, re-run fresh: `21/21 entries OK (red)` and `21/21 entries OK (green)`. Every per-entry count, the F2 widths, F3/F4/F5, A1 = 22050, A2 = 48000 and the oracle's O1 line match the measurement doc. Stock Chrome is still 154.0.8037.93 and the updater is still Disabled.
- **Document audit** (an independent reviewer checked every claim against the code). It found:
  - O2's cause was misstated as `IS_LINUX`-only code;
  - the GPU-process path list counted per-patch occurrences as files;
  - "no patched path is in GPU-process code" ignored `crashpad.cc`, which runs in every process but reads no config;
  - a few overclaims (the Segoe UI rule, "the claimed families").

  All are corrected in `2008ed9`, which changes prose and comments only. Every code-behaviour claim and local suite number checked out.

## Not done here, and why
- **O2 fails on the Windows build.** Under a Linux claim, the Windows build keeps `navigator.share`, `canShare` and `bluetooth`. The renderer block in `windows-oracle.patch` only enables them for a Windows or macOS claim, and nothing disables them under a Linux claim; stock Windows Chrome ships both on. The fix is a "Linux claim: disable" branch in that block. It is filed as backlog item 8 and marked `known_fail` in the set.
- **`verify_windows_client.py:130`** passes the generator's `{config, launch}` wrapper as the config. This predates the branch. K1's chunking row holds only because the wrapper is large. The doc records it, and the fix needs a larger identity shape.
- **Baseline-comparing scripts** are left out. Their baselines are `content_shell` or Linux captures, which step 2 recaptures.
- **The Windows component build** stays deferred until a Blink relink on `out\Release` is timed.
- **Linux `build-verify`** runs only when this merges (it triggers on pushes to `main`). The `checks` job runs on this PR.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-23"></a>
## #23 docs(readme): bring the status up to step 1 finished on Windows

`docs/readme-step1` into `main`, opened 2026-10-04T08:18:22Z, merged 2026-10-04T09:01:32Z.

## What

README only. It brings the status up to date after PR #22.

- **Patch count:** 33 patches, not 26.
- **New Windows paragraph:**
  - native `chrome.exe` 154 and the Windows-specific patches;
  - `scripts/windows_verify_set.py`: 21 entries, RED 21/21 against stock and GREEN 21/21 against the fork;
  - O2 is a known failure;
  - all three clients run on Windows.
- **`content_shell` paragraph:** `Sec-CH-UA*` and `userAgentData` are now verified against `chrome` (`verify_sp1a_chrome.py`), so they are no longer listed as unreachable.
- **Remaining work:** now points at the long-term roadmap (steps 0 and 1 done; steps 2 and 3 next). The per-slice residuals stay in the follow-on roadmap.
- **Pin:** the 156 re-pin date (by 2026-10-20), with a link to the runbook.
- **Layout table:** adds the Node client, `baselines/`, the newer `settings/` files and a fuller `scripts/` description.

## Evidence

Every claim was checked against the tree at `a9d6c93`. The numbers come from `docs/superpowers/measurements/2026-10-04-windows-verify-set.md` and the roadmap's step 1 status.

```
patches/series lines: 33
.patch files: 33
ok scripts/windows_verify_set.py
ok scripts/verify_sp1a_chrome.py
ok scripts/export.sh
ok scripts/repin.py
ok scripts/package.py
ok docs/superpowers/specs/repin-runbook.md
ok docs/superpowers/measurements/2026-10-04-windows-verify-set.md
ok docs/superpowers/plans/2026-10-02-long-term-roadmap.md
ok docs/superpowers/plans/2026-09-02-followon-roadmap.md
ok patches/crashpad-no-dumps.patch
ok patches/windows-sandbox-env.patch
ok patches/windows-oracle.patch
ok patches/windows-behaviour.patch
ok patches/windows-behaviour-ii.patch
Entry( count in scripts/windows_verify_set.py: 21
 README.md | 55 +++++++++++++++++++++++++++++++++++++------------------
 1 file changed, 37 insertions(+), 18 deletions(-)
```

No code, patch or CI-filtered path changed, so `build-verify` does not run. The last `build-verify` on `main` at `a9d6c93` (run 37188058874) was green.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-24"></a>
## #24 Safe Browsing off by default (backlog 4); P4 and netlog harness fixes; Blink relink timed

`backlog4/safe-browsing` into `main`, opened 2026-10-04T12:05:00Z, merged 2026-10-04T13:04:00Z.

## What

Closes roadmap backlog item 4: Safe Browsing phoning home. The full write-up is in `docs/superpowers/measurements/2026-10-04-safe-browsing.md`.

- **It was never intermittent.** The first list fetch (`POST safebrowsing.googleapis.com/v5/hashLists:batchGet`) fires on every start, at a uniformly random delay of 60–300 s (`kTimerStartIntervalSecMin/Max`). The 75 s window caught it about one start in sixteen.
- **The lever.** In `sp7-phone-home.patch`, `prefs::kSafeBrowsingEnabled` now defaults to `false`.
  - This is the "No protection" state a real user can choose. It was decided with the owner over two alternatives: stopping only the fetch, or a config key.
  - The cost: no phishing or malware protection by default.
  - It is exported from the box branch (one fixup folded into `sp7-phone-home`, still 38 commits). `check_checkout_sync` PASS.
- **`verify_sp7_phonehome` changes.**
  - P1 passes `--safebrowsing-fast-initial-lists-update`, which moves the fetch to 10–20 s.
  - New P5 is a navigation premise: a request to `sb.test` mapped to loopback.
  - The netlog is parsed line by line. An unreadable log scores `UNMEASURED` (exit 2), not FAIL.
  - The netlog goes to the platform temp dir.
- **P4 had measured nothing on Linux.** The script passed a second `--user-data-dir` in `extra_flags`. Chrome on Linux takes the last one and Windows the first, so on Linux both launches used fresh profiles, and on Windows P4 timed out.
  - `lib_shell.launch(user_data_dir=)` fixes this; the default argv is unchanged.
  - P4 now asserts that the profile was reused.
- **Windows.**
  - The lever was applied through runbook §7, built, and verified.
  - A one-file Blink relink on `out\Release` takes **38 s (49 steps)**, so the Windows component build is not needed.
- **New finding, filed rather than fixed:** `chromewebstore.googleapis.com` is requested within 75 s on the Windows build only. It is listed under roadmap item 4.

## Evidence

**RED before the lever, Linux `out/Default` chrome:**

```
note: P1: external hosts in 75s = {"safebrowsing.googleapis.com": 1} (expect {})
P1: FAIL   (4 of 4 runs: 75 s x3, 30 s x1)
```

**Lever build and export (box):**

```
2m02.12s Build Succeeded: 134 steps     (and 1m57.09s, 134 steps after a comment-only fold)
Header dependency check OK
exported 38 commits from camoucrome/main
 M patches/sp7-phone-home.patch   (+17)
PASS  all 41 copied files are identical in repo and checkout
7140164c488d589bcaffcef8e66b93f88b54305fd3e6b8e6ad25b5ae6117c769  patches/sp7-phone-home.patch   (same sha256 in this PR)
```

**GREEN, Linux:**

```
note: P1: external hosts in 75s = {} (expect {})     3 of 3 runs, P1-P5 PASS, rc=0
note: P1: external hosts in 330s = {} (expect {})    beyond the 300 s timer maximum
```

**P4 premise, Linux:** RED before the `launch()` change, GREEN after it.

```
P4: launch 1 wrote its profile where launch 2 reads it = False (expect True)   -> {'P4': False}
P4: launch 1 wrote its profile where launch 2 reads it = True (expect True)    -> {'P4': True}
```

**Duplicate `--user-data-dir` probe** (which directory got `DevToolsActivePort`):

```
Linux:   first(A): 0 last(B): 1
Windows: first(A): True last(B): False
```

**Windows `out\Release` chrome.exe 154:**

```
RED   P1 = {"chromewebstore.googleapis.com": 1, "safebrowsing.googleapis.com": 1}   (2 runs)
apply --include rc=0; git apply --check -R <whole revised patch> rc=0; blob 7bef349864 (= WSL)
28.47s Build Succeeded: 5 steps
GREEN P1 = {"chromewebstore.googleapis.com": 1}   (2 runs; Safe Browsing gone; P2-P5 PASS)
windows_verify_set.py green: 21/21 entries OK (green), EXIT 0
Blink relink (navigator.cc mtime touched): 38.38s Build Succeeded: 49 steps
```

`verify_sp7_phonehome` still exits 1 on Windows because of the Web Store request. That request is the filed item; it is not a regression.

**Unit and harness tests (Mac):**

```
test_lib_shell_launch.py: 26 PASS
pytest scripts/test_verify_sp7_phonehome.py scripts/test_windows_verify_set.py: 24 passed
```

`test_verify_sp7_phonehome.py`'s polledData case failed on the old parser, and the 3c checks in `test_lib_shell_launch.py` failed before `user_data_dir` existed.

**Box, CI's list at `3f89b4b`** (the head before the last commit, which changes wording in two docs only):

```
PASS  all 38 source files in additions/camoucfg/ are listed in BUILD.gn
PASS  keys.h matches settings/keys.json (90 keys); unit-test set and call sites consistent
PASS fontconfig files match settings/fonts.json
lib_shell argv: 26 PASS
pytest (CI list + test_verify_sp7_phonehome.py): 115 passed
go: ok  github.com/lang315/camoucrome/client/go
node: pass 20, fail 0
verify_sp1a_chrome     PASS  8 unconfigured userAgentData matches the baseline
verify_sp4_voices      5/5 ALL_PASS
verify_fonts_bundle    17 PASS 0 FAIL   (see below)
verify_host_oracle     4 PASS 0 FAIL
verify_windows_behaviour 14 PASS 0 FAIL
verify_sp6b_generator  ALL_PASS
verify_crash_dumps     2 PASS 0 FAIL (expected 2 PASS)
verify_sp7_fieldtrial  C4: PASS
verify_sp7_phonehome   P1-P5 PASS
```

Two things in that run are stated rather than hidden.

- **pytest.** The first pass printed `4 failed, 111 passed`. All four failures were in `scripts/test_package.py`, the same harness artifact seen on PR #22: the scratch tree is a `git archive`, not a checkout. After `git init` in that tree, the run gave `115 passed`.
- **`verify_fonts_bundle`.** The first pass failed once with `patchright TargetClosedError`. Two re-runs read `17 PASS 0 FAIL`, and the lever build had already read `17/0` before. This script never calls `lib_shell.launch()`: it launches through `camoucrome.probe` and uses only `lib_shell.CHROME` and `layout()`. So the `user_data_dir` change cannot reach it. It is a flake in the client probe path.

## Notes

- The box branch `camoucrome/main` already carries the folded lever (backup ref `camoucrome/main-pre-backlog4`). Until this PR merges, `check_checkout_sync` on any other PR will fail.
- While the comment-only fix was being folded, one `rebase --autosquash` ran detached after its ssh call returned and stopped with `index.lock write error: Bad file descriptor`. The branch ref was never moved.
  - The leftover files matched the commit being picked, byte for byte. They were moved to `~/bl4/rescue` and the rebase was aborted.
  - The rebase was re-run in the foreground. The result was 38 commits, a clean tree, and a one-file diff from the backup ref.
- Post-merge `build-verify` will report `0 steps`: the box already built the lever. The 134-step build above is the build evidence.
- `test_lib_shell_launch.py`, including the new 3c checks, runs in `checks.yml` on this PR.
- The Windows tree is stamped `555543e`. The only difference from the head is docs.
- Not re-checked: `verify_media_ii.py` cites a probe, no longer in the repo, that may have hit the same duplicate-flag trap as P4.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-25"></a>
## #25 docs(CLAUDE.md): the box checkout has one branch now

`docs/box-branches` into `main`, opened 2026-10-04T13:34:02Z, merged 2026-10-04T13:37:55Z.

## What

Two sentences in `CLAUDE.md` named `camoucrome/main-8010` and `camoucrome/main-0e8d` as retired branches on the build box. Both were deleted on 2026-10-04, at the owner's request, together with `camoucrome/main-pre-review` and five August-era branches. This PR rewords those two sentences. It is docs only.

## Evidence

Box, `~/chromium/src`, `git branch -D` output:

```
Deleted branch camoucrome/main-0e8d (was 6b6420840a).
Deleted branch camoucrome/main-8010 (was c41c7745ad).
Deleted branch camoucrome/main-pre-review (was ada4cdcfa4).
Deleted branch camoucrome-verify (was 0e8d4a9268).
Deleted branch camoucrome/reconstruct-sp1a (was 0e8d4a9268).
Deleted branch camoucrome/reconstruct-sp5a (was 0e8d4a9268).
Deleted branch camoucrome/sp0 (was 07cadeac4c).
Deleted branch camoucrome/sp5a (was a727b57805).
* camoucrome/main
```

No script, workflow or Python file references any of these names: `grep` over `*.sh`, `*.py` and `*.yml` returns nothing. The runbook mentions `main-8010` only as an example of the rename a re-pin performs. The SHAs above stay reachable through the box's reflog for about 90 days.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-26"></a>
## #26 Step 2: measurement layers 1 and 2, 154 baseline

`step2/measurement` into `main`, opened 2026-10-04T16:33:29Z, merged 2026-10-04T22:56:55Z.

## What

Roadmap step 2, "measurement, layers 1 and 2". The fork and stock Chrome 154 run through the same client (`camoucrome.launch()`) with the same argv, headed and headless, across six probes:

- the oracle
- noise readback
- the network fingerprint (`tls.peet.ws`)
- relaunch stability
- cross-profile linkability
- public detectors: CreepJS, BrowserScan, Pixelscan and sannysoft

Every differing row is labelled expected, volatile or unexpected. The run produces a 154 baseline and five new backlog findings (S1–S5).

- Spec: `docs/superpowers/specs/2026-10-04-step2-measurement-design.md`
- Plan: `docs/superpowers/plans/2026-10-04-step2-measurement.md`
- Evidence: `docs/superpowers/measurements/2026-10-step2-baseline.md`, with the baseline tables in `docs/superpowers/measurements/step2-154/`

Code:
- `scripts/step2_rows.py` is the pure half: labels, preconditions, run comparison and tables. It is unit-tested in CI.
- `scripts/measure_step2.py` is the host runner.
- `scripts/oracle_rules.py` takes `SHAPE_ONLY` and `flatten` out of `verify_host_oracle.py`. They moved byte for byte, and `test_verify_host_oracle` gives 7 passed before and after.

## Evidence

**CI-side tests (Mac).** `python3 -m pytest -q client/python/tests scripts/` gives `217 passed`. That includes the 73 tests in `scripts/test_step2_rows.py`, each seen failing first.

**On the Windows host.**
- Fork: `out\Release\chrome.exe`. Control: stock Chrome. Both report `ProductVersion` 154.0.8037.93. Google Update is held.
- All runs held the build lock (owner `step2`). It is released now.

Preconditions refuse on purpose:
- A fork executable with the wrong version: rc=1, `precondition: fork is 10.0.19041.3996, the pin is 154.0.8037.93`, and no run directory.
- A runner copy that does not allow the planted arg: rc=1, `precondition, argv parity: fork only: --use-angle=swiftshader`.

Each probe was seen RED first. A null run puts stock in both arms; a planted run adds one difference to the fork arm.

| probe | null run | planted RED |
|---|---|---|
| oracle | 0 unexpected | `--disable-blink-features=WebShare`: `nav.share`, `nav.canShare` and `navProto` unexpected, in both modes |
| noise | 1 colour per arm | `--two-colour`: 2 and 2 |
| network | `ja4` equal; `ja3` volatile | `--ssl-version-max=tls1.2`: `ja4` changes |
| stability | control stable | `--fresh-seeds`: fork `audioFp` (and headed `canvas.shape`) changes |
| detectors | 0 unexpected rows, 0 lines | CreepJS and sannysoft see WebShare off; BrowserScan and Pixelscan do not (documented) |

Run-to-run comparison:
- The two full null runs give `0 rows disagree outside VOLATILE`.
- The three fork runs differ only where the fork itself is unstable. These are recorded as finding S4, not as volatility:
  - the WebGPU adapter: 1 of 3 runs
  - the HEVC answer: 2 of 3 runs
  - CreepJS "rgba noise": 1 of 3 runs

**Findings, ranked into the roadmap backlog as S1–S5.**
- S1: a solid-fill canvas reads back 3 colours on the fork, and a WebGL clear reads 5. Stock reads 1.
- S2: canvas noise has low entropy.
- S3: device IDs are empty after the camera and microphone grant.
- S4: the fork is unstable across launches.
- S5: the fork has no remote voices.

The network fingerprint is equal to stock. Rule 2's window keys are now measured on `chrome.exe`, and they are equal to stock.

**Privacy.**
- The committed baseline had the host's public IP, city, coordinates and Pixelscan's district scrubbed.
- The branch history was rewritten (squash, filter-branch, force-push) so that no commit carries them.
- Screenshots and raw detector text stayed on the host.

## Not run

- `build-verify` only runs on `main`. This PR changes no `patches/` or `additions/` file. It does move two names out of `verify_host_oracle.py`, and that change is covered by its unit test.
- The host runner itself is not run in CI. It needs the Windows host and the network.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-27"></a>
## #27 S1+S2: canvas noise redesign (draw-time text offset, edge-only readback noise)

`s1/canvas-noise` into `main`, opened 2026-10-05T16:08:59Z, merged 2026-10-05T23:17:23Z.

## What

This PR fixes backlog **S1** and **S2** from the Step 2 tables.
- **S1:** canvas farbling was visible on a solid fill. A one-colour 2D fill read back 3 colours, and a WebGL clear read 5.
- **S2:** canvas noise had little entropy, so the oracle's canvas hashes usually equalled stock's.

**Spec:** `docs/superpowers/specs/2026-10-05-canvas-noise-redesign-design.md`. It was amended while planning: partial-alpha pixels became eligible through a premultiplied clamp, the imported-pixels flag replaced the `putImageData`-only flag, and C9 was adjusted.
**Plan:** `docs/superpowers/plans/2026-10-05-canvas-noise-redesign.md`.
**Measurements:** `docs/superpowers/measurements/2026-10-canvas-noise.md`.

A Phase 0 spike chose the **target design**. The spike ran on the Windows host GPU build, with readback noise off so that only the text offset was measured. P1–P5 all passed in both modes, and P1 and P2 each gave 8 distinct hashes of 8 seeds. The design:

- **Draw-time text offset.** Text is drawn at a per-seed sub-pixel origin (`camoucfg::TextOffset`, derived from `canvas:seed`). Every readback and every copy of a text canvas therefore agrees, because there is nothing to add afterwards.
- **Edge-only readback noise** (`PerturbRgbaEdges`).
  - A pixel is perturbed only if it is interior, its alpha is not 0, and it differs from all four of its neighbours.
  - The noise works on premultiplied values, clamped to `[0, alpha]`, so the readback stays on stock's value grid.
  - Solid fills, hard edges and 1px lines never change.
  - WebGL `readPixels` is opaque-only.
- **One snapshot hook.** `CanvasRenderingContext::CamouNoised()` noises the snapshot for every consumer: `getImageData`, `toDataURL`, `toBlob`, `convertToBlob`, and `GetSourceImageForCanvas`, which serves `drawImage`, `createPattern`, `createImageBitmap`, `texImage2D` and captureStream's two-copy path. Its cache is keyed before the readback.
- **Eligibility.**
  - A 2D canvas gets readback noise only if it drew anti-aliased geometry (curves, or a non-axis-aligned transform).
  - It must also not have imported pixels (`putImageData`, or a `drawImage` or `createPattern` from a canvas, `OffscreenCanvas` or `ImageBitmap`).
  - A canvas that is unsure reads as stock.
- **Density.** The `canvas:noiseDensity` default is now **0.04**, calibrated on the host: the smallest density that passed in both modes was 0.02, doubled for margin. There are no new config keys.

## Evidence

**RED on the build before this change** (Windows host, measurements §1):

| check | before |
|---|---|
| solid fill and WebGL clear distinct colours (S1) | FAIL (5 distinct 2D/WebGL colour-count pairs across seeds) |
| flat drawings equal stock, round trip exact (P3) | FAIL (edge, glClear, line, solid differ; not exact) |
| copies agree (P4) | FAIL |
| oracle text and shape vary per seed (S2) | FAIL (text 3 of 8, shape 7 of 8, stock among them) |
| rule 5 | PASS |

`verify_sp3a.py` on the WSL build before the change (§4) printed `FAIL 11`, `FAIL 12`, `FAIL 13` and `FAIL 14`, and ended `rc=1`.

**After the change.** On the Windows host the fork's `out\Release\chrome.exe` ran against stock Chrome 154.0.8037.93, with 8 seeds at the default density (§6, `final2-headed-b` and `final2-headless`, identical):

```
PASS  P1 text, 512x128 canvas, varies across seeds  (8 distinct of 8, stock among them: False)
PASS  P2 text, willReadFrequently canvas, varies across seeds  (8 distinct of 8, stock among them: False)
PASS  P3 flat drawings equal stock, putImageData round trip exact  (differ: [], round trip exact: True)
PASS  P4 drawImage and createImageBitmap agree with getImageData  (all agree: True)
PASS  P5 text at x and x+1 differ only by the shift  (all equal: True)
PASS  S2 oracle text canvas varies (>=6 distinct)  (8 distinct of 8, stock among them: False)
PASS  S2 oracle shape canvas varies (all distinct)  (8 distinct of 8, stock among them: False)
PASS  S1 solid fill and WebGL clear read one colour  (colours: [(1, 1)])
PASS  rule 5: the fork without config reads as stock  (differ: [])
```

**WSL, `content_shell` at HEAD** (§6):
- `verify_sp3a.py` ALL_PASS, 14/14.
- Mutation proof: with the imported-pixels flag removed, `FAIL 12` and `FAIL 13`. Restoring the flag brings back ALL_PASS.
- `verify_review_2026_09_24.py` 12/12. Its R1 and R2 now use eligible drawings.
- `components_unittests` canvas suites passed (gtest PASSED 10, 10, 8).
- `gn check` reported `Header dependency check OK` and checkdeps reported `SUCCESS`.

**Step 2 re-measure** (§7, scrubbed numbers only):
- noise reads 1 and 1;
- the fork's `canvas.text` and `canvas.shape` differ from control and are no longer leaves shared between profiles;
- they are stable across relaunch;
- the CreepJS "rgba noise" row is absent.

**Regression verifies on the host:** `verify_windows_client.py` 11 PASS 0 FAIL, and `verify_sp6b_driver.py` ALL_PASS.

**Builds, all reporting non-zero steps:** WSL 262, 53, 192 and 19 steps. Windows 218 (after one clang OOM retry), 59 and 49 steps.

**Mac:**
- `python3 -m pytest -q client/python/tests scripts/`: 229 passed.
- `check_additions_build.py`: PASS.
- `gen_keys.py --check`: PASS.
- `check_checkout_sync`: PASS.
- `export.sh` gate: empty after the commit.

## Not measured, or skipped

- **`verify_sp3a` baseline clauses on Windows: UNMEASURED.** The stock baseline file is not on the host. They ran on WSL against the baseline.
- **Copy-path cost: UNMEASURED.** A cache hit for an unchanged GPU canvas was not measured either.
- **Known tells and gaps** (§8, and the spec's "Amended while planning"):
  - `transferToImageBitmap`;
  - `createPattern` across contexts, and `createPattern` without a draw flipping eligibility;
  - any edit reseeds the readback field;
  - the noise field is keyed by position;
  - WebGL `readPixels` sub-rect versus full read;
  - captureStream's one-copy path;
  - `VideoFrame` from a canvas;
  - the `transferControlToOffscreen` placeholder.

  A follow-up (keying the noise on each pixel's 3×3 source patch) is on the roadmap.
- **Box branch state.** `camoucrome/main` on the box already carries this change set, so `build-verify` after the merge is expected to build 0 steps. The backup ref `camoucrome/main-pre-cn` stays until CI on main is green.

## Code-review fixes (three rounds after `/code-review`)

Measurement doc §9 holds the full output.

**Round 1** (items 1, 2, 4, 7, 8–11, plus new rows C15 and C16, RED first):
- The text offset now works in device space: it maps through the inverse of the transform's linear part. C15 covers it. The RED run showed 30–36 px shifts under `ctx.scale(40, 40)`.
- Every drawImage and createPattern source marks the canvas as holding imported pixels. C16 covers it with a decoded PNG drawn on an eligible canvas.
- The baseline `readPixels` now captures the FLAT clear.
- The flat rows now run on eligible canvases. The mutation proof confirms they test the edge rule: with the neighbour tests skipped, C11 FAILs.
- C7 and C8 now draw an arc with no text and compare against a live unconfigured run, so they test the hook.
- `verify_review` R1 and R3 now reach the noise path.

**Round 2** (re-review findings I-1 and I-2):
- `readPixels` noise now goes on the in-buffer part of the rect, at the real pack layout: PACK_ALIGNMENT, ROW_LENGTH, SKIP_PIXELS and SKIP_ROWS. The field is keyed by a tight copy of the pixels, so no layout returns the clean render.
- New rows C17 (align 8, odd width), C18 (WebGL2 ROW_LENGTH/SKIP) and C19 (a rect reaching past the buffer). All three failed on the round-1 build.

**Round 3** (re-review finding N-1):
- New guard `skip_pixels + width <= stride`, which is GL's own rule.
- New row C20, which reads with a layout GL rejects and checks the buffer stays untouched. C20 already passed on the round-2 build, because Blink rejects the call first. The guard is therefore defensive, and the doc says so.
- C19 is tightened: the in-buffer part must equal the default read, and the bytes outside the buffer must equal the unconfigured run's.

**Evidence at HEAD:**
- **WSL** `content_shell`:
  - `verify_sp3a` 20/20 ALL_PASS.
  - `verify_review_2026_09_24` 12/12.
  - Unit tests, `gn check` and `checkdeps` pass.
  - Builds took 190, 34 and 192 steps.
- **Windows** `out\Release`:
  - Builds took 70, 78 and 49 steps.
  - The host runner gave 9/9 headless in `final5`.
  - Headed: every row passed in at least one `final5` attempt, but no single attempt was a clean 9/9. WebGL context creation intermittently failed in unconfigured and seeded cells, so those rows were UNMEASURED or failed rule 5. That is a host flake: the change runs only after a context exists.
  - Windows `verify_sp3a`: C6–C9 and C12–C20 PASS. The baseline clauses are UNMEASURED because the host has no stock baseline file.
- **Patches:** the committed `patches/`, `additions/` and `settings/invariants.json` are byte-equal to a fresh `export.sh` of the box branch at `421a4b6` (verified on the box).

**Follow-ups, not in this PR:**
- Roadmap **S2b**, which needs its own spec:
  - the AA-geometry gaps (diagonal `lineTo`, curved `clip()`, `shadowBlur`);
  - per-canvas eligibility can be told apart across canvases;
  - WebGL→WebGL `texImage2D` takes a GPU path that skips the hook;
  - the cache cost;
  - keying the noise on each pixel's 3×3 source neighbourhood.
- Minor test follow-ups:
  - C19 does not cover the far-side clamp, or clipping combined with skip;
  - the guard's comment should say Blink rejects the call first.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-28"></a>
## #28 S2b: patch-keyed canvas noise and per-pixel eligibility

`s2b/canvas-noise` into `main`, opened 2026-10-06T15:04:35Z, merged 2026-10-07T02:32:35Z.

## What

Backlog **S2b** is the follow-up to S1/S2 (PR #27). It keys the canvas readback noise on local content and decides 2D eligibility per pixel, so the noise no longer moves with:
- position;
- edits elsewhere on the canvas;
- canvas reuse;
- the sub-rect of a WebGL read.

It also covers every anti-aliased operation without keeping a list of them.

**Spec:** `docs/superpowers/specs/2026-10-06-canvas-noise-s2b-design.md`. It has an "Amended during implementation" section, which binds.
**Plan:** `docs/superpowers/plans/2026-10-06-canvas-noise-s2b.md`.
**Measurements:** `docs/superpowers/measurements/2026-10-canvas-noise-s2b.md`, sections 1–12.

- **Patch-keyed field.** Each pixel's noise is a function of `canvas:seed`, its 3×3 source patch (hashed top-down) and the channel. Nothing else goes into it: no position, no `CanvasStateHash`, no content hash.
- **Per-pixel 2D eligibility.** The new class `camoucfg::CanvasNoiseMask` keeps two bits per pixel, `aa` and `imported`. At the one 2D choke point (`DrawInternal`), each draw's `draw_func` is replayed into a side recorder, and the record is played onto an A8 bitmap. The coverage is then merged by kind:
  - a solid opaque full cover clears both bits;
  - a partial cover, a gradient, or the shadow pass marks `aa`;
  - a pattern, an image or `putImageData` marks `imported`;
  - a composited draw marks its clip `imported`;
  - text marks nothing, unless it uses a pattern style;
  - a draw that changes no pixel (`nothingToDraw`) marks nothing.

  A pixel is noised only when it is `aa` and not `imported`. This replaces PR #27's sticky per-canvas flags.
- **Clearing draws.** `destination-out`, `copy` and `clearRect` clear the bits they cover, and `transferToImageBitmap` resets the mask. The `copy` clear is always a fill, even for a stroke.
- **Eligibility and memory.** A canvas is eligible only while some pixel carries an aa-only mark, so a canvas holding only imported pixels skips the noise path. Noise copies and the readPixels scratch use fallible allocation: a failed allocation means no noise, never a crash. CSS Paint worklets never replay their draws.
- **WebGL.**
  - `readPixels` reads up to four 1px strips around the in-buffer part, only when a seed is set, so a sub-rect read equals the matching part of a full read, byte for byte.
  - The WebGL snapshot is opaque-only, so `toDataURL` agrees with `readPixels`.
- **Density.** It stays at 0.04, and the calibration on the host still passes at that value. No new config keys.

## Evidence

**RED on `main`'s build before S2b** (WSL, section 1): `verify_sp3a` C1–C20 PASS, and every row from C21 to C29 FAILs, 12 lines with the stated causes, rc=1. Later rows were each seen failing on the build just before their fix:
- C27, redrawn because a 2-colour checkerboard has only 2 patch types (section 1 addendum);
- C30–C32 (section 5b);
- C33a–d (section 9);
- C33e (section 10);
- C34 (section 12).

**Mutation proof** (section 5): with coverage replaced by "dirty rect marked aa", C27 FAILs. Restoring the coverage makes it PASS again.

**WSL `content_shell` at the current head** (section 12):
```
verify_sp3a.py           41/41 ALL_PASS, rc=0
verify_review_2026_09_24 12/12 ALL_PASS
components_unittests     canvas suites pass (CanvasNoiseMask incl. aa-cell count, PerturbRgba*, NoisedImage*)
gn check core/canvas/webgl: Header dependency check OK; checkdeps: SUCCESS
builds: 363 (additions) + 29 (Blink) steps, rc=0; export: 38 commits, 0 fixups
```

**Windows `out\Release` at head** (section 12; W12 per-file replacement, every post hash equals the box's):
- build `s2b-4`: 197 steps, rc=0, after two clang out-of-memory restarts;
- host runner: headless 9/9 and headed 9/9, both on the second attempt. Each first attempt hit the known host GPU flake: stock had no WebGL context, so headless failed rule 5 and headed left P3 and S1 unmeasured. Both are recorded, not counted as passes;
- `verify_sp3a` on `chrome`: 35 PASS (C1, C6–C9, C12–C34); C2–C5, C10 and C11 are **UNMEASURED**, because the stock baseline is not on the host.

The previous head (section 11) was 9/9 in both modes on the first attempt.

The earlier Windows run at `9f2de63` (section 9) also passed, 9/9 in each mode, on the second attempt. Its first headless attempt failed rule 5 while stock had no WebGL context; that is recorded as a host GPU flake, not a pass. Calibration at 0.04 holds (section 7): S2 text 8 of 8 and shape 8 of 8, with stock among neither. Regression verifies (section 7): `verify_windows_client.py` 11 PASS 0 FAIL and `verify_sp6b_driver.py` ALL_PASS.

**Step 2 re-measure** (section 7, scrubbed numbers):
- noise is 1 and 1;
- the oracle canvases differ from control;
- the fork shares no canvas leaf;
- there is no CreepJS "rgba noise";
- the headless relaunch changed one HEVC codec leaf (S4 instability, not canvas).

**Cost** (WSL, CPU raster; sections 2 and 12). Seeded/unconfigured ratio:

| case | PR #27 | S2b |
|---|---|---|
| draw (10k arcs per frame) | 1.43× | ~4.5× |
| `readPixels` 64² | 1.33× | ~3.3× |
| `readPixels` 1024² | 15.89× | ~21.5× (40.9 ms vs 1.9 ms) |

Both draw and `readPixels` are **regressions** against PR #27, and the draw cost is above the spec's 2× line. Both are known gaps for S2c. An earlier "after" reading of 1.11× / 7.06× was invalid: it was measured before the seed gate, when the unconfigured arm also did the strip work (section 6, corrected in section 12). The rise of the seeded 1024² time from about 30 ms to about 40 ms is not yet explained.

**Mac:** `pytest` passes, and `check_additions_build.py` and `gen_keys.py --check` PASS.

## Not measured, pending, or known gaps

- **UNMEASURED:** the Windows `verify_sp3a` baseline clauses. There is also no row for GPU-accelerated 2D raster: every S2b 2D row uses a canvas of 128 px or less.
- **Known gaps** (measurement section 8, spec Known gaps):
  - draw cost ~4.5× and `readPixels` cost ~21.5× at 1024² (S2c);
  - a draw that changes no pixel can still switch noise off: `drawImage` of an empty source marks its dirty rect imported, and a composited transparent draw marks its clip imported;
  - full-resolution A8 replay on huge canvases;
  - a neighbour draw re-rolls a region's noise, which is inherent to patch keying, so C22 is "narrowed";
  - a composited draw switches noise off for its clip;
  - canvases above 4096² use coarse cells;
  - layers mark imported;
  - `drawMesh` textures;
  - the focus ring is unmarked;
  - the `readPixels` scratch copy;
  - pattern-styled text is covered by code review only;
  - `transferToImageBitmap`, the captureStream one-copy path and the `transferControlToOffscreen` placeholder stay as in PR #27.
- **Box backup ref:** `camoucrome/main-pre-s2b` stays until this merges and CI on main is green. Another session's branch was cut from it, so it is deleted only after telling that session.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



<a id="pr-29"></a>
## #29 Tracking observer (phase 1 + 1c) and facebook recon

`worktree-tracking-observer` into `main`, opened 2026-10-07T06:39:56Z, merged 2026-10-07T07:15:15Z.

## What this adds

A build-gated **tracking observer**, ported from camoufox's Tracking Observer and redesigned for Chromium. It is followed by a **facebook recon** made with it.

- **New patch slice `observe`** (last in `patches/series`):
  - GN arg `camou_observe`, which defaults to off. `package.py` refuses a release built with it.
  - A disabled-by-default trace category, `camou.observe`.
  - `camou_observe::Record(name, isolate)`, emitted from the Blink bindings generator for an allow-list of fingerprint interfaces and members. That is about 1 000 callbacks: navigator, screen, canvas, WebGL, WebGPU, audio, media, WebRTC, fonts, layout probes and storage.
  - The out-of-line `Emit` runs only when the category is enabled. It records `origin`, the top-level `site`, and the calling `script` URL.
  - With the flag off, the generated call is an empty inline; a RED/GREEN proof shows no context lookup was added to callbacks. With the flag on and the category off, the cost is one category check.
- **Scripts**
  - `scripts/observe_report.py`: per-site report with the script column, a top-scripts table, cookie names only (never values), query-stripped paths, and buffer-fill stats.
  - `scripts/verify_observe.py`: a 15-row browser verify, no CDP.
  - `scripts/windows/observe-*.ps1`: recon helpers.
  - `check_checkout_sync.sh` takes a branch argument.
- **Docs**
  - `docs/observer/README.md`, the operator guide, including what it cannot see.
  - Spec, plan and follow-ups.
  - `docs/superpowers/measurements/2026-10-07-fb-observe.md`.

## Evidence

**Tests on the merged tree (d5b739b):**
- `pytest -q scripts/test_observe_report.py scripts/test_package.py scripts/test_verify_observe.py scripts/test_gen_keys.py scripts/test_build_lock.py`: 44 passed.
- `gen_keys.py --check`: PASS (90 keys).
- `check_additions_build.py`: PASS (42 files).

**Browser verify** (`verify_observe.py`, content_shell, observer build):
- RED first: **0/15**. Every row failed wrong by one; there was no early abort.
- GREEN: **15/15**, twice.
- The rows check:
  - exact per-API counts with origin, site and script for the window;
  - worker reads;
  - a cross-site iframe;
  - an external `<script src>` from a second origin, which is the Meta Pixel case;
  - a non-allow-listed API (`Document.title`) at 0;
  - an off arm: tracing is on for other categories, there are 0 observer events, and other events are present.

**Regression:** the CI verify set against the observer build (flag on, category off) gives the same counts as main's last green run. With the slice's tests added, pytest went from 115 to 125.

**Windows** (native `out\Observe`): headless smoke test 10/10.

**Overhead** (worst-case microbenchmark, content_shell, 200k `navigator.userAgent` reads / 300 `toDataURL`):
- category off: 88.5 ms / 29.6 ms
- category on: 512.1 ms / 30.6 ms

**Box landing, done before this PR so build-verify on main stays green:**
- `observe` is cherry-picked onto box `camoucrome/main`, now **`cfd88ac347`** on top of S2b 8cf90b48.
- The export equals this branch's `patches/` byte for byte (`diff -rq` empty), and `check_checkout_sync.sh local ~/chromium/src` gives **rc=0**.
- `out/Default` was hand-built under `build_lock.sh` (`chrome content_shell components_unittests`): **9 477 steps, EXIT=0, 0 failures**.
- CI's `out/Default` does not set `camou_observe`, so CI prints a visible `SKIP verify_observe.py`. Whether CI should build with the flag is an open owner decision.

## Facebook recon (summary, details in the measurement doc)

- **Arm 1 (logged out) and arm 2 (login):** `/ajax/bz` fired in both. Facebook's own pages read canvas, audio and `NavigatorUAData` on landing. WebGL was read at login.
- **Logged-in session:** `navigator.deviceMemory` was read hundreds of times.
- **Arm 4, third-party page (<regional-site>) with Meta Pixel + SDK, attributed per script:**
  - `fbevents.js` read cookies, localStorage, the UA, screen size, element geometry and UA Client Hints on desktop Chrome.
  - The pixel config script enumerated localStorage keys.
  - No Meta script read canvas, WebGL, audio or fonts.
- **Phone-home:** Chrome itself contacted `passwordsleakcheck-pa.googleapis.com` at login and `content-autofill.googleapis.com` in every arm. Both are recorded for SP7.

## Known gaps (also in `docs/observer/followups.md`)

- **V8 fast API calls** (`[NoAllocDirectCall]` canvas/WebGL draw ops and setters) bypass the hook. Draw-op counts are lower bounds; read-outs are unaffected. A follow-up will count them.
- **Arm 3:** the first runs used a trace filter without `-*`, so the trace buffer filled. Arm 3 covers the first 58 of 116 s and its counts are lower bounds. The filter is fixed, and arm 3 should be re-run.
- **Blind spots:** V8 built-ins (`Intl`, `Date.getTimezoneOffset`), CSS `@media`, named/indexed interceptor access, TLS, and anything server-side.
- **Not yet done:** instagram/threads arms 2-4, the phase 1b `chrome://camou-observe` dashboard, and V8/Intl hooks.
- **Pre-existing, unrelated:** the `d-pointer-touch` patch lacks a `//components/camoucfg` dep in `core/exported/BUILD.gn`, so `gn check` fails on `web_view_impl.cc`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)


<a id="pr-30"></a>
## #30 feat(observer): count V8 fast API calls

`worktree-observer-fastcall` into `main`, opened 2026-10-08T13:08:23Z, merged 2026-10-08T23:57:28Z.

## Summary

Follow-up B of the tracking observer (`docs/observer/followups.md`). Until now the observer did not count V8 fast API calls. About 100 canvas-2D and WebGL methods and setters have a `[NoAllocDirectCall]` fast path that skips the hooked slow callback once V8 optimizes the call site, so canvas and WebGL draw and state counts were lower bounds.

- **`patches/observe.patch`:**
  - `bind_gen/interface.py` now also emits `camou_observe::Record(...)` in `make_no_alloc_direct_call_callback_def` and `make_attribute_set_nadc_callback_def`.
  - The fast paths stay registered.
  - `Emit` opens a `v8::HandleScope` and copies the script name with `Utf8LengthV2`/`WriteUtf8V2` instead of `ToCoreStringWithNullCheck`.
- **`scripts/verify_observe.py`:** a hot page runs 100 000 `fillRect` calls and `lineWidth` sets and asserts exact counts. That makes 17 rows, up from 15.
- **Docs:** the fast-call entry is removed from `NOT_OBSERVABLE` and from the README's blind spots. `followups.md` replaces "Merge preconditions" with the landing order for bindings slices, and notes that canvas counts in the facebook recon are lower bounds. The spec gets a resolution note.
- **`CLAUDE.md`:**
  - the build lock;
  - the landing order for a slice that changes the bindings;
  - the observer CI build;
  - a `docs/observer/` row in the layout table.

Plan: `docs/superpowers/plans/2026-10-08-observer-fastcall.md`.

## Evidence

### RED first: the old box build (`cfd88ac347`, before the hook)

`verify_observe.py` was run from this branch.

- **Green run, rc=1, 15/17 PASS.** The hot rows are short because the fast path took over:
  ```
  FAIL CanvasRenderingContext2D.fillRect x100000 (fast path) script=http://127.0.0.1:39801/hot.html: 7570 (want 100000)
  FAIL CanvasRenderingContext2D.lineWidth.set x100000 (fast path) script=http://127.0.0.1:39801/hot.html: 7570 (want 100000)
  15/17 PASS
  ```
- **`--red`:** `0/17 PASS (RED mode: expected failures)`, with hot rows at 4468.
- **Buffer:** both hot traces report `Trace buffer: no chunks discarded.`, so the short counts are not trace loss.

### GREEN: the new box build

- **Build:** `autoninja -C out/Default chrome content_shell components_unittests`.
  - Result: `Build Succeeded: 61 steps`, `EXIT=0`, finished 2026-10-08 16:57 VN.
  - Siso planned 60780 steps and pruned the unchanged regenerated bindings by restat.
  - It recompiled `camou_observe.o` and the four bindings that have fast callbacks: canvas 2D, offscreen canvas 2D, WebGL and WebGL2.
- **Generated code:** `v8_canvas_rendering_context_2d.cc` has `camou_observe::Record` in both the fast and the slow callbacks, with matching names:
  ```
  1172:void LineWidthAttributeSetNoAllocDirectCall(..., v8::FastApiCallbackOptions& v8_arg_callback_options) {
  1174:camou_observe::Record("CanvasRenderingContext2D.lineWidth.set", isolate);
  3001:void FillRectOperationNoAllocDirectCallArg4(..., v8::FastApiCallbackOptions& v8_arg_callback_options) {
  3003:camou_observe::Record("CanvasRenderingContext2D.fillRect", isolate);
  ```
- **`verify_observe.py` runs** (19:51–19:54 VN):
  - `--red`: `0/17 PASS`, rc=1. Every row fails as intended; the hot rows read `100000 (want 100001)`.
  - Green run 1: `17/17 PASS`, rc=0. Hot rows: `fillRect` 100000 and `lineWidth.set` 100000, script `hot.html`.
  - Green run 2: `17/17 PASS`, rc=0, with the same hot counts.
  - The empty-script fallback in the plan was not needed.
- **`--timing`** (a single run, no verdict):
  - Category off: 75.6 ms per 200k `navigator.userAgent` reads, 29.5 ms per 300 `toDataURL` calls. The README has 88.5 and 29.6.
  - Category on: 788.9 and 30.9 ms. The README has 512.1 and 30.6.
  - The on-arm `userAgent` figure is not attributed to this change. That getter has no fast path, and the difference is more than 10× what a HandleScope plus a short string copy costs. The README records it as a single run, and `followups.md` asks for repeated runs.
- **Box `camoucrome/main`:** `5c80c86e19` (`observe`, amended), parent `8cf90b48f8` (unchanged). The checkout is clean.
- **Export:** `diff -rq` between the base archive and the export shows that only `patches/observe.patch` differs. Its sha256 is the same on the box and the Mac: `482d7360…051e`.
- **Sync gate:** `check_checkout_sync.sh local ~/chromium/src` gives `PASS all 45 copied files are identical in repo and checkout`, rc=0.

### Mac pre-flight

```
PASS  all 42 source files in additions/camoucfg/ are listed in BUILD.gn
PASS  keys.h matches settings/keys.json (90 keys); unit-test set and call sites consistent
45 passed  (test_observe_report, test_verify_observe, test_package, test_gen_keys, test_build_lock)
```

### Not run or not verified

- The flag-off build (`camou_observe = false`) was not compiled in this change. `Record` is an empty inline under `#else` for both the slow and the fast hooks, so it is the same mechanism as before.
- Review minors are parked in `followups.md`:
  - the `Emit` comment wording;
  - a hot row run from a cross-origin iframe;
  - repeated `--timing` runs.

## Merge

The bindings change already landed on the box and `out/Default` is built, so CI's `build-verify` should build only a handful of steps. A dry run after the build once showed 16 pending steps, which were not investigated. CI then runs `verify_observe.py` with 17 rows.

The last commit, `e8beffb`, applies the final whole-branch review. It changes docs and the hot-arm `--red` guard in `verify_observe.py`, and touches no change-set files, so the sync gate still holds. The `followups.md` item to rebuild the Windows `out\Observe` before the next recon is open: until then that binary still undercounts canvas and WebGL calls. Merge only with the owner's approval and while no session is building on the box.

🤖 Generated with [Claude Code](https://claude.com/claude-code)


<a id="pr-31"></a>
## #31 S2c: canvas noise cost and WebGL reads (flush-time mask, regional getImageData, framebuffer reads)

`s2c/canvas-cost` into `main`, opened 2026-10-09T00:03:36Z, merged 2026-10-10T01:14:37Z.

## S2c: canvas noise cost and WebGL reads

> **Ready to merge (owner's call).** /code-review (13 findings) and its re-review rounds are fixed (measurements §13); box `camoucrome/main` was re-landed on the final code (e585e8b5ce) and Windows re-run on it (§9.9). Evidence below.

Spec `docs/superpowers/specs/2026-10-07-canvas-noise-s2c-design.md`; evidence in `docs/superpowers/measurements/2026-10-canvas-noise-s2c.md` (sections cited below).

### Spike (§1, S2b build, medians)
| case | unconfigured | seeded |
|---|---|---|
| one arc+fill | 0.375 us | 8.98 us (24x) |
| 10 000 arcs, no read | 2.85 ms | 85.8 ms (30x) |
| 10 000 arcs + 1x1 getImageData | 26.7 ms | 123.5 ms (4.6x) |
| 1x1 getImageData after one arc (1024^2) | <0.1 ms | 10.3 ms |
| WebGL readPixels 1024^2 | 1.9 ms | 40.7 ms (21x) |
| WebGL readPixels 64^2 sub-rect | 0.3 ms | 1.0 ms (3.3x) |

### RED and mutants
- §3: on the S2b build C35-C38 FAIL (framebuffer reads, texImage2D from WebGL).
- C39 mutant (regional noise on unpremultiplied values): FAIL 39 (`dC` 7) plus 21-26, 24a-d, 40 (§8).
- C45 mutant (`sx,sy` instead of `min(sx,0),min(sy,0)`): FAIL on 21, 23, 26, 39, 45 (§8.1).
- C44b mutant (clip mark restored in the looper branch): 52 PASS, 1 FAIL (§7.2).
- C37 mutant (every probe pixel agrees): FAIL, `edgeDiff` 7 (§6.2). C42 and C41 RED on the round-1 build (§6.1, §6.2). C43, C44 RED first (§7.1).
- Final review (§12.1): C46 (R8/RG8 FBO, 59 pixels with G or B != 0), C46b (RGBA4 FBO) and C47 (SRGB8_ALPHA8 read clean) FAIL on the pre-fix build; C36b passes there as a guard (after its first far-edge rect proved vacuous).

### /code-review round (§13, 2026-10-09)
- RED first: C48 (SVG `drawImage` at `globalAlpha` 0) FAIL on the build before the fix; `NoisedImageTest.MaskOfAnotherSizeChangesNothing` FAIL (355-step build). C49 (large sub-rect via margin strips) and C50 (`SharedArrayBuffer` view equals a plain view) are guards, failing under named mutants (58 PASS, 49 and 50 FAIL).
- GREEN: final build 207 steps; `verify_sp3a` 60/60 ALL_PASS; `verify_review` 12/12; unit filter 73 tests SUCCESS (`GoldenFieldUnchanged` holds both hashes, now for the in-place pass and an independent reference); `gn check` OK for core, canvas, webgl, camoucfg, camoucfg:canvas_readback; `checkdeps` SUCCESS for modules/canvas, core/html/canvas, modules/webgl, components/camoucfg; pytest 248 passed; sync check 45/45.
- Status: #1-#3, #5, #8-#13 fixed; #4 fixed with a stated residual; #6 fixed on the CPU path, GPU path not verifiable on the box; #7 fixed for large rects (small rects keep the one-piece re-read by design).
- Cost (seeded ms, before -> after runs 1/2): large full reads +0.2 to +0.85 ms (the #4 probe row); `read_2d`/`read_2d_mid` 0.000 -> 0.100 (per-flush coverage allocation, #8, not isolated); `draw_read` 64.35 -> 66.0; the rest within noise. Targets: `read_2d_mid` 0.10 PASS, `gl_flat.large` 1.50/1.71 and `gl_edges.large` 1.63/1.47 PASS, `draw_read` 2.72/2.59, `gl_edges.small` 2.04/2.17 and `gl_fbo.large` 3.95/4.35 MISS as before.

### /code-review round 3 (§13.10, 2026-10-09)
- Re-review `crfix-rereview2.md`. RED first: C52 (a url() filter of feFlood then feDropShadow in sRGB over an alpha-0 fill) FAIL on `3b05631c30`: 37 filtered pixels carried noise (first run failed on its own vacuity guard and was fixed, not counted). C53 (C18's WebGL2 pack layout on a page framebuffer) PASS there as a guard.
- Fix: the canvas-shadow layer skip also requires a drop-shadow filter with no input; comments say "before the page's read".
- GREEN: build 354 steps; `verify_sp3a` 63/63 ALL_PASS; `verify_review` 12/12; unit filter SUCCESS; `gn check` OK x5; `checkdeps` SUCCESS x4; pytest 248; box export 38/0/0 at `b6fe23620e`, sync 45/45. W5c not re-run (no timed path touched). `gl_fbo.large` 7.6 -> 4.8 ms: no code cause; most likely load-inflated earlier runs, unexplained.

### /code-review round 2 (§13.9, 2026-10-09)
- Re-review `crfix-rereview.md`. RED first: C51 (shadowed `globalAlpha` 0 `drawImage` of a translucent canvas) FAIL on `a3c026bc7e` (60 PASS).
- Fixes: WebGL decides every "will noise" question before the read (a read left stock goes straight into the view; a shared view gets back only the in-framebuffer part); #4's chunked partial-read residual stated and accepted by the owner; the drop-shadow layer marks only for an op that draws something; the coverage bitmap is made when the walk first needs the clip; the raster-uniqueID cache short-circuit is back for CPU snapshots; 80-column and test nits.
- GREEN: build 144 steps; `verify_sp3a` 61/61 ALL_PASS; `verify_review` 12/12; unit filter SUCCESS; `gn check` OK x5; `checkdeps` SUCCESS x4; pytest 248; box export 38/0/0 at `3b05631c30`, sync 45/45.
- Cost (0 chrome.exe on the host before each run): `gl_fbo.large` 7.6 -> 4.8 ms (2.55x / 2.53x, now PASS; cause not isolated); the rest within noise (`draw_read` 2.79x / 2.74x and `gl_edges.small` 2.00x / 1.93x still MISS; `read_2d_mid` 0.1 ms PASS).

### Final verdicts (before the /code-review round)
- WSL `verify_sp3a` 57/57 ALL_PASS (61/61 after the /code-review rounds), `verify_review` 12/12, unit filters (71 tests) SUCCESS, `gn check` OK for core, canvas, webgl, camoucfg; `checkdeps` clean for modules/canvas, core/html/canvas, modules/webgl, components/camoucfg (§12.3).
- Whole suite at hand-over: `pytest client/python/tests scripts/` 229 passed; `check_additions_build.py` PASS (42 files); `gen_keys.py --check` PASS (90 keys); sync check on the box: all 45 copied files identical.
- Unit suites: PerturbRgba, CanvasNoise, NoisedImage, NoisedRegion, CanvasNoiseMask, Derive (plus the readback suites).
- Build step counts (all non-zero): first workdir build 70 812 planned, then 219, 277, 357/355/356 (mutants), 260, 3-27 (incremental), 354 and 207 (final fixes); Windows 265 (§9.2) and 265 for the final code (§9.8).

### Cost, before and after (WSL CPU raster, §4 and §12.6 final run)
| case | before | after | target |
|---|---|---|---|
| per_draw_us | 23.71x | 0.93x (1.00-1.17x in other runs) | <=1.2 PASS |
| draw_read | 4.56x | 2.64x | <=2 MISS |
| read_2d | 9.4 ms | below timer (0.1 ms after §13) | reported only since §13 |
| read_2d_mid | n/a | 0.1 ms (§13) | <=0.5 PASS |
| gl_flat.large | 21.25x | 1.37x | <=3 PASS |
| gl_edges.large | 24.56x | 1.44x | <=3 PASS |
| gl_edges.small | 5.00x | 2.00x | <=1.5 MISS |
| gl_fbo.large | (not noised) | 4.16x | <=3 accepted MISS (after the 8-bit gate) |
| gl_fbo.small | (not noised) | 5.33x | none |
| shadow_read | n/a | ~3x | none |

### Windows, final code after /code-review (§9.9)
17 files replaced from box `camoucrome/s2c` (post hashes equal the box). A host-vs-box sweep of 478 canvas/webgl/camoucfg files found one stale file (`offscreen_canvas_rendering_context_2d.cc`, reverted to base by the review round, so the base diff skipped it); replaced. Build s2c-3b 194 steps rc=0. `verify_sp3a` on chrome: 63 rows, 57 PASS, 6 UNMEASURED (C2-C5, C10, C11: no stock baseline on the host); C39 and C45 pass on GPU raster (texture-backed regional `getImageData`, finding #6). Host runs: headless 9/9, headed 9/9 (attempt 1). `verify_windows_client` 11/0, `verify_sp6b_driver` ALL_PASS.

### Windows, final-review code (§9.8)
17 files replaced (post hashes equal the box at 4c115c6 / box 0ef3ff9aa1). Build s2c-2 265 steps rc=0. `verify_sp3a` on chrome: 57 rows, 51 PASS, 6 UNMEASURED (C2-C5, C10, C11: no stock baseline on the host). Host runs: headless 9/9 (attempt 2; attempt 1 was the WebGL flake), headed 9/9 (attempt 1). Calibration and Step 2 not re-run (field unchanged, gates only narrow).

### Windows (§9, before the final review fixes)
17 files replaced, pre hashes equal `8cf90b48`, post hashes equal the box. Build 265 steps rc=0. Host calibration at density 0.04: headless 9/9 and headed 9/9 PASS (S2 text 8 of 8, shape 8 of 8, rule 5 differ []). `verify_sp3a` on chrome 47 PASS, 6 FAIL that are UNMEASURED (C2-C5, C10, C11 need the stock baseline absent on the host). `verify_windows_client` 11/0, `verify_sp6b_driver` ALL_PASS.

### Step 2 (§9.7, run 20261008-130955, 0 errors)
`noise.canvas2d` 1 and `noise.webgl` 1; oracle canvas.text/shape differ from control; no canvas leaf shared between fork identities; stability 0 differing rows; no "noise" word in the four CreepJS captures.

### UNMEASURED / not done
- Windows `verify_sp3a` rows C2-C5, C10, C11 (no stock baseline on the host).
- GPU (texture-backed) `getImageData`: not regional, not measurable on the box.
- `draw_read` 2.64x, `gl_edges.small` 2.00x and `gl_fbo.large` 4.16x (accepted) miss their targets. Possible timing tell: seeded, a page-framebuffer read takes 3.0x (large) / 2.6x (small) a default-framebuffer read of the same size, against about 1.0x stock (§10); `shadow_read`, `gl_fbo.small` have none. Remaining gaps and parked review items: measurements §10.

### History note
The branch carries 8 `chore: temporary box ...` commits (box helper files, removed again in 1654ab7). The net tree is clean. Squashing them needs a force-push and the owner's go-ahead.

### Landing (done 2026-10-09, owner go-ahead, camoucrome-80 agreed)
- PR #30 (observe-fastcall) merged first (c275512, build-verify 37862262065 green), so box `camoucrome/main`'s observe commit equals origin/main's `patches/observe.patch`.
- origin/main merged into this branch: 09aeb59 (clean; pytest 248 passed).
- Box `~/chromium/src`, lock `s2c land`: backup ref `camoucrome/main-pre-s2c` = 5c80c86e19; `git rebase --onto camoucrome/s2c 8cf90b48 camoucrome/main` -> 776dc4d632 (39 commits: S2c's 38 + observe), clean. The 6 observe files are byte-identical before and after (their mtimes reset so the build did not redo base/bindings).
- `out/Default` (camou_observe = true): `Build Succeeded: 3456 steps`, rc=0. Unit filter PASS. `verify_sp3a` 57/57 ALL_PASS, `verify_observe` 17/17 (and `--red` 0/17 as expected), `verify_review` 12/12.
- `scripts/export.sh ~/chromium/src camoucrome/main` (39 commits) into a clone of 09aeb59: `git status --porcelain additions patches settings` empty, so `patches/` here equals the export; `patches/observe.patch` unchanged against origin/main.
- `check_checkout_sync.sh local`: PASS, all 45 copied files identical.

### Re-land after /code-review (2026-10-09)
- Box `~/chromium/src`, lock `s2c land2`: `git rebase --onto camoucrome/s2c camoucrome/main~1 camoucrome/main` (only the observe commit replayed) -> e585e8b5ce (39 commits), clean; observe files byte-identical, mtimes reset.
- `out/Default`: `Build Succeeded: 211 steps`, rc=0. Unit filter PASS. `verify_sp3a` 63/63 ALL_PASS, `verify_observe` 17/17 (`--red` 0/17 as expected), `verify_review` 12/12.
- On a git snapshot of this PR's head 6bf71e3: `check_checkout_sync.sh local` PASS (45 files identical), then `export.sh ~/chromium/src camoucrome/main` (39 commits) leaves `git status --porcelain additions patches settings` empty; `patches/observe.patch` is byte-identical to origin/main c275512.
- Backup ref `camoucrome/main-pre-s2c` (5c80c86e19) is deleted after this PR merges and CI is green.

🤖 Generated with [Claude Code](https://claude.com/claude-code)


<a id="pr-32"></a>
## #32 S3: media device ids after a grant (phantom enumerate entries)

`s3/media-device-ids` into `main`, opened 2026-10-10T06:30:34Z, merged 2026-10-10T06:35:26Z.

## Backlog S3: media device ids after a grant

Step 2 found that after a camera and microphone grant, the fork listed every claimed device with `deviceId: ""`, while stock Chrome on the same Windows host listed its real speaker with ids. The cause was sp4-media's pre-grant test: it looked only at input ids, and the host has a speaker and no inputs. As a result, `mediaDevices:seed` could not be measured.

- Spec: `docs/superpowers/specs/2026-10-10-s3-media-device-ids-design.md`
- Plan: `docs/superpowers/plans/2026-10-10-s3-media-device-ids.md`
- Evidence: `docs/superpowers/measurements/2026-10-s3-media-device-ids.md`

### What changes

**Browser (new `patches/s3-media-phantoms.patch`).** `MediaDevicesManager::OnDevicesEnumeratedAndRanked` adds a phantom device to a copy of the enumeration, only in the enumerate reply.

- A kind gets one phantom only when the identity claims it and the host has none. Real hardware is never replaced.
- Chrome then applies its own handling to the phantoms:
  - the permission gating;
  - the deviceId HMAC;
  - the per-document group salt;
  - the pre-grant blanking.
- On Windows, a phantom audio kind also gets `default` and `communications` sentinels, labelled with Chrome's own localized prefix.
- A phantom camera uses Chrome's fallback formats. A phantom mic reports 48 kHz stereo, which is Windows' fallback.
- The phantoms never enter `current_snapshot_`, so getUserMedia, setSinkId and devicechange are unchanged.
- With `mediaDevices:enabled` absent, nothing changes.

**camoucfg (additions).**
- `media_phantoms.{h,cc}` builds the phantom entries.
- `MaskedDeviceLabel` keeps the `<prefix> - ` of a sentinel label.

**Renderer (`sp4-media.patch`, `media-ii-track.patch`).**
- The grant test counts a non-empty id of any kind.
- The enumerate list and the track label both use `MaskedDeviceLabel`, so they stay equal (media-ii M4).
- The seeded transform keeps input capabilities. Before this PR it dropped them for real devices too (stock lists `sampleRate`/`channelCount`), which was a page-visible tell.

### Evidence

**WSL** (`content_shell`, `--use-fake-ui-for-media-stream`, no fake devices), `scripts/verify_s3_media.py`, EXPECTED 8:

| Build | Result |
|---|---|
| main (before S3) | `2/8 FAIL`: only the S3-3 and S3-8 guards pass |
| S3 | `8/8 ALL_PASS` |
| mutant: translation without phantoms | S3-1 FAIL (`phantom ids=[]`) |
| mutant: capability copy dropped | S3-7 FAIL, `7/8` |
| mutant: wrong capability id | S3-7 FAIL, `7/8` |

Regressions on S3: `verify_media_ii` 13/13, `verify_phantom` 6/6, `verify_sp4_media` 4/4.

Unit tests: 18 (5 `MediaPhantomsTest`, 13 `DeviceIdsTest`) pass. `gn check` and `checkdeps` are clean.

**Windows host** (stock Chrome vs fork, both headless, granted through CDP), `scripts/verify_s3_host.py`, EXPECTED 4:

| Build | Result |
|---|---|
| S2c (before S3) | `0/4 FAIL` |
| S3 | `4/4 ALL_PASS` |
| stock Chrome in the fork arm | `2/4 FAIL` (W2 and W3 fail: no phantom mic) |
| per-clause mutants | each gives `3/4 FAIL` on its own row |

The four host rows:
- **S3-W1:** both arms list a 64-hex `audiooutput` id.
- **S3-W2:** the phantom mic's sentinels carry the same prefixes as the real speaker's.
- **S3-W3:** phantom mic capability ranges.
- **S3-W4:** within one profile, deviceIds are stable across two documents and groupIds differ, matching stock.

The output carries only kinds, id lengths, label prefixes and ranges.

**Windows build and other host checks:**
- Ten files were replaced in the Windows tree. Every pre hash equals box `camoucrome/main` (S2c), and every post hash equals `camoucrome/s3`.
- `out\Release` rebuilt in 56 steps, rc=0.
- `windows_verify_set.py green` 21/21.
- `verify_sp3a` 57 PASS + 6 baseline-less (C2/C3/C4/C5/C10/C11), the same as S2c.
- Host canvas 9/9 headless.
- Step 2 stability: 0 changed rows, and `mediaDevices.ids` is non-empty on both arms.

**Box:**
- `camoucrome/main` = 4b5fdddcd8, 40 commits. It was landed by moving the ref onto the identical tree; the backup is `camoucrome/main-pre-s3`.
- `check_checkout_sync` PASS 48/48 against an archive of this branch.
- Exported files match by sha256.

### Gaps and follow-ups (measurement doc §8)

- **New tell:** on a host with no audio output, `setSinkId()` would reject the listed phantom speaker id. This is unmeasured; the follow-up is in §8.
- **Unmeasured: the any-id grant test.** On the host, phantom inputs carry ids anyway. The follow-up is host row S3-W5.
- **Unmeasured: the phantom mic's latency** (0..0.0427 s) against a real mic. Parked for the owner.
- **Unmeasured: the getUserMedia exact-id path on a phantom.**
- **Not built:** the Linux and macOS sentinel shapes.
- **S3b follow-ups from the final review:** seed gating, the bare sentinel label, label defaults kept in one place, style nits, and tighter W2/S3-8 clauses.

Not merged; the owner decides.

🤖 Generated with [Claude Code](https://claude.com/claude-code)


<a id="pr-33"></a>
## #33 S3b: media device ids that round-trip (seed folded into Chrome's HMAC)

`s3b/device-id-seed` into `main`, opened 2026-10-10T10:28:13Z, merged 2026-10-12T12:27:34Z.

## S3b: media device ids that round-trip

S3's final review found a tell that predates S3: with `mediaDevices:seed` set, the renderer rewrote every listed device id, but the browser only matches its own hash. So a page that passed back an id it had just been given got an error, where stock Chrome succeeds:
- `audio.setSinkId(<listed speaker id>)` → `NotFoundError`;
- `AudioContext.setSinkId(<listed id>)` → `NotFoundError`, and a constructor `sinkId` gets an `error` event;
- `getUserMedia({audio: {deviceId: {exact: <listed mic id>}}})` → `OverconstrainedError`.

On a host with no speaker, S3's phantom speaker had the same problem.

- Spec: `docs/superpowers/specs/2026-10-10-s3b-device-id-seed-design.md`
- Plan: `docs/superpowers/plans/2026-10-10-s3b-device-id-seed.md`
- Evidence: `docs/superpowers/measurements/2026-10-s3b-device-id-seed.md`

### What changes

- **Browser (new `patches/s3b-device-id-seed.patch`).** `GetHMACForRawMediaDeviceID` folds the seed into Chrome's one device-id HMAC, after the `default`/`communications` passthrough. Every hash and every match goes through that function, so they now agree by construction: enumerate, devicechange, getUserMedia matching, track ids, output authorization and groupId. Ids keep the stock shape: 64 hex, per origin, stable per profile, rotating with the seed.
- **Renderer (`sp4-media`, `media-ii-track`).** It no longer rewrites ids; it only masks labels, keeps the pre-grant shape and copies capabilities. `SyntheticDeviceId` is removed.
- **One activation rule.** `camoucfg::ActiveMediaDevicesSeed` (enabled AND a non-zero seed) gates every media-device hook: phantoms, the fold, renderer labels, the track label and `phantom-webcam`'s remap. **Behaviour change:** a config with `mediaDevices:enabled` but no seed now spoofs nothing. The generated clients always set a seed, so only hand-written configs are affected.
- **Phantom speaker (`s3-media-phantoms`).** `CamouWithPhantoms` is exported and applied in `NotifyDeviceChange` and in `AudioOutputAuthorizationHandler::TranslateDeviceID`. A phantom speaker exists only when the host has no output device, and a match authorizes the default output, as stock `setSinkId("")` does on such a host.
- **Smaller fixes.**
  - The label defaults live once, in `device_ids.h`.
  - Include order and formatting are cleaned up.
  - `verify_phantom` P6 and `verify_sp4_media` M4 compare against a live stock run. WSLg lost its audio devices mid-slice, and the M4 baseline file was never in the repo.

### Evidence

**WSL** (`content_shell`), `scripts/verify_s3_media.py`, EXPECTED 12. Rows S3-9..11 use fake devices with a stock control.

| Build | Result |
|---|---|
| main (S3) | `8/12 FAIL`: S3-9 NotFoundError, S3-10 OverconstrainedError, S3-11 NotFoundError (stock ok on all three); S3-12 FAIL |
| S3b | `12/12 ALL_PASS` |
| mutant: listed id ≠ Chrome's id | `8/12` (S3-1, S3-9..11 FAIL) |
| mutant: browser gate back to enabled-only | `11/12` (S3-12 FAIL) |

Regressions: `verify_media_ii` 13/13, `verify_phantom` 6/6, `verify_sp4_media` 4/4. Unit tests pass. `gn check`, `checkdeps` and `gen_keys --check` are clean.

**Phantom speaker** (`scripts/verify_s3b_phantom_out.py`, EXPECTED 2). This runs only under a test-only box mutant, never exported, that models a host with no output device. The script refuses a normal build, and each row has a stock control.

| Build | Result |
|---|---|
| S3b + mutant | `2/2` |
| + output authorization reading the raw list | `0/2` (S3-M1 NotFoundError, S3-M2 fails) |

**Windows host** (stock Chrome vs fork, headless), `scripts/verify_s3_host.py`, EXPECTED 7:

| Build | Result |
|---|---|
| S3 | `6/7 FAIL`: S3-W6 `setSinkId` fork=NotFoundError, control=ok |
| S3b with the renderer grant test made input-only (mutant) | S3-W5 FAIL |
| S3b with the fold line removed (mutant) | `6/7 FAIL`: S3-W7, other seed not disjoint |
| S3b | `7/7 ALL_PASS` |

- 15 files were replaced in the Windows tree. Every pre hash equals box `camoucrome/main` (S3), and every post hash equals `camoucrome/s3b`.
- `windows_verify_set.py green` 21/21.
- `verify_sp3a` 57 PASS + 6 baseline-less rows, as before.
- Host canvas 9/9.
- Step 2 stability: 0 differing rows.

**Box.** `camoucrome/main` = ff5ecaa880, 41 commits; the backup is `camoucrome/main-pre-s3b`. `check_checkout_sync` PASS 48/48 against an archive of this branch. The exported files match by sha256.

### Gaps and follow-ups (measurement doc §8)

- **Unmeasured:** the `NotifyDeviceChange` half of the phantom-speaker fix. A devicechange cannot be triggered on WSL.
- **Thin:** S3-W7 compares one output id on this host (n=1).
- **Still parked:** the phantom mic latency, getUserMedia exact on a phantom id (NotReadableError), and M2 (Linux sentinel labels).
- **Not measured on WSL now:** the real-input half of S3-7, because WSLg has no audio devices.
- **Other:** minor follow-ups from the final review, kept as S3b follow-ups.

Not merged; the owner decides.

🤖 Generated with [Claude Code](https://claude.com/claude-code)


<a id="pr-34"></a>
## #34 docs(observer): settle the 1b clone-to-JSON question

`docs-observer-1b-clone-json` into `main`, opened 2026-10-12T12:38:19Z, merged 2026-10-12T15:46:04Z.

## Summary

Follow-up C: a read-only spike on the phase 1b dashboard question that the tracking-observer spec left open, "can a cloned tracing session be read back as JSON through the exporter?"

The answer is yes, but not through an existing call:
- A cloned `ConsumerHost::TracingSession` returns raw proto.
- The only JSON entry point, `DisableTracingAndEmitJson`, stops the session.

The dashboard handler can repeat what `ConsumerHost` does after a stop, about 30 lines:
1. `CloneTrace`, then `ReadTrace`.
2. Feed the bytes to its own `TraceProcessorStorage`.
3. Call `json::ExportJson`.

This is the same exporter that produced every phase-1 `trace.json`, so `observe_report.py` remains the reference. The protobuf-decoder fallback is not needed, and no probe build is needed.

The PR changes only `docs/superpowers/specs/2026-10-06-tracking-observer-design.md`. It touches no change set (`additions/`, `patches/`, `settings/`) and does not trigger build-verify.

## Evidence

Everything below was read on the box checkout `~/chromium/src`, `camoucrome/main` = `ff5ecaa880`, with no edits and no build.

```
services/tracing/perfetto/consumer_host.cc:388:  DCHECK(!convert_to_legacy_json_);        # ReadBuffers on a clone = proto
services/tracing/perfetto/consumer_host.cc:425:      ...TraceProcessorStorage::CreateInstance(
services/tracing/perfetto/consumer_host.cc:446:  auto status = perfetto::trace_processor::json::ExportJson(
services/tracing/perfetto/consumer_host.cc:493:        trace_processor_->Parse(...TraceBlob::CopyFrom(chunk...)))
services/tracing/public/cpp/perfetto/perfetto_tracing_backend.cc:431:  ...convert_to_legacy_json()) {
services/tracing/public/cpp/perfetto/perfetto_tracing_backend.cc:432:        tracing_session_host_->DisableTracingAndEmitJson(
content/browser/tracing/traces_internals/traces_internals_handler.cc:233-243:  CloneTraceArgs{.unique_session_name=...}; CloneTrace(...) -> ReadTrace(...)
third_party/perfetto/include/perfetto/tracing/tracing.h:383: struct CloneTraceArgs { std::string unique_session_name; }
third_party/perfetto/include/perfetto/tracing/tracing.h:391: only one CloneTrace call can be pending at the same time
```

Symbols in `out/Default` (`nm -DC`):

```
=== .so defining ExportJson / TraceProcessorStorage::CreateInstance
libtest_trace_processor.so 2
libthird_party_perfetto_libperfetto.so 2
=== .so importing them
libbase.so 2
libcontent.so 2
libv8_libplatform.so 2
```

Build and include rules:

```
content/browser/BUILD.gn:298:    "//services/tracing:lib",
services/tracing/BUILD.gn:41:      "//third_party/perfetto/include/perfetto/ext/trace_processor:export_json",
services/tracing/BUILD.gn:43:      "//third_party/perfetto/include/perfetto/trace_processor:storage",
content/browser/tracing/DEPS:   "+third_party/perfetto/include",
```

Not run: no runtime check. The spec already defines 1b's first RED test, "the probe page read through the dashboard shows the counts the report shows", and that test is the runtime confirmation.

🤖 Generated with [Claude Code](https://claude.com/claude-code)


<a id="pr-35"></a>
## #35 fix(d-pointer-touch): add the camoucfg dep to core/exported (observer follow-up A)

`fix/d-pointer-touch-dep` into `main`, opened 2026-10-12T15:31:14Z, merged 2026-10-12T15:34:31Z.

## Summary

This is tracking-observer follow-up A.

`d-pointer-touch.patch` includes three `components/camoucfg` headers in `third_party/blink/renderer/core/exported/web_view_impl.cc`. Its `exported` target never declared `//components/camoucfg` as a dep. The build passed because the dep comes in transitively through `platform`, but `gn check` on that directory failed with 3 errors.

- `patches/d-pointer-touch.patch` now adds `"//components/camoucfg"` to `blink_core_sources("exported")` deps. It was re-exported from box `camoucrome/main`, where the line was fixed up into the `d-pointer-touch` commit. That commit went from `6c07a12f00` to `a1c3bab9aa`, and HEAD is now `1e1c03b5fe`, which was `ff5ecaa880` before.
- `docs/observer/followups.md`:
  - drops this item;
  - drops the `out\Observe` rebuild item, which was done on 2026-10-09;
  - notes the phase 1b clone-to-JSON spike (PR #34).

The box branch is already updated and built, so CI's sync gate holds once this merges.

## Evidence

All of this ran on the box, `~/chromium/src`, under `build_lock` "observe-A".

`gn check out/Default '//third_party/blink/renderer/core/exported/*'`, before the fix (RED):

```
ERROR at //third_party/blink/renderer/core/exported/web_view_impl.cc:34:11: Can't include this header from here.
#include "components/camoucfg/mask_config.h"
Suggestion: Add deps = [ "//components/camoucfg:camoucfg" ] to :exported (defined at //third_party/blink/renderer/core/exported/BUILD.gn:24)
error count: 3, rc=1
```

After the fixup (GREEN):

```
Header dependency check OK
rc=0
checkdeps.py third_party/blink/renderer/core/exported: SUCCESS rc=0
```

Fixup and rebase (`--autosquash` onto `d-pointer-touch~1`): the branch still has 11 commits from `d-pointer-touch~1`. `git diff --stat ff5ecaa880 HEAD`:

```
 third_party/blink/renderer/core/exported/BUILD.gn | 1 +
```

The mtimes of the other 67 replayed files were restored.

Build: `autoninja -C out/Default chrome content_shell components_unittests` returned `rc=0` with `Build Succeeded: 0 steps`. GN regenerated: `[0/2] Regenerating ninja files`, and `exported.ninja` (15:25:50Z) is newer than `BUILD.gn` (15:25:36Z). Zero steps is expected:
- `exported.ninja` now references `camoucfg/libcamoucfg.a`;
- `gn desc ... :exported deps` lists `//components/camoucfg:camoucfg`;
- no compile flags changed.

Export and sync gate (`export.sh ~/chromium/src` into a clone of `main` ff71e9e):

```
exported 41 commits from camoucrome/main.
git status --porcelain additions patches settings:
 M patches/d-pointer-touch.patch
check_checkout_sync.sh local: PASS  all 48 copied files are identical in repo and checkout  (rc=0)
```

`sha256(patches/d-pointer-touch.patch)` is `9808255f…2de86`, both in this branch and in the box export.

Not run:
- No fresh `apply.sh` round-trip on a pristine tree. The export gate shows the repo equals the box branch, and `gn check` passed on that branch.
- No browser verifies. The change is a GN dep only, with 0 compile steps.

🤖 Generated with [Claude Code](https://claude.com/claude-code)


<a id="pr-36"></a>
## #36 observer: Intl built-in counts via V8 runtime call stats (phase 2)

`observer-d-intl-rcs` into `main`, opened 2026-10-12T18:37:53Z, merged 2026-10-17T02:56:52Z.

Follow-up D: the observer report now counts the Intl built-ins a fingerprinting script uses to read time zone and locales (`new Intl.DateTimeFormat`, `resolvedOptions`, the `supportedLocalesOf` family, `localeCompare`, `toLocale*`, `Intl.Locale`, Segmenter, …). It reads V8's **runtime call stats** (RCS) from the trace.

- No V8 patch.
- No change to apply/export/sync/rebuild/repin tooling.
- Nothing extra for the 156 re-pin to carry beyond one `args.gn` line.

Spec: `docs/superpowers/specs/2026-10-13-observer-intl-rcs-design.md`. Plan: `docs/superpowers/plans/2026-10-13-observer-intl-rcs.md`.

## What changes
- **Build (observer out dirs only).**
  - Add `v8_enable_runtime_call_stats = true` next to `camou_observe = true`.
  - Box `out/Default` (CI's tree) already has it. Per the landing order it was rebuilt under lock `observe-D` before this PR. `args.gn` is box-local, so the sync gate would not have flagged a wrong order.
  - Documented in the README, `CLAUDE.md` and re-pin runbook step 6.
- **Recording (opt-in).** The Intl recipe adds two categories: `--trace-startup=-*,disabled-by-default-camou.observe,v8,disabled-by-default-v8.runtime_stats`. The default recipe and `observe-recon.ps1`'s default argv are unchanged. The launcher gains `-Intl`.
- **Report.** A new section, "V8 built-ins (Intl)", sums the RCS dumps on top-level `V8.Execute` / `V8.RunMicrotasks` slices, per site × entry script × builtin.
  - Entry script, in order of precedence: the Blink `v8.run` `fileName`, else the one observer-event script inside the slice, else `(unknown)`.
  - Site: the renderer's page site. A worker's origin is used only when the process has no event with a site.
  - The section prints `Intl: blind (…)` when no dump holds a counter. It never prints a silent 0.
- **Verify.** The probe page and its worker each make K calls of the constructor, `resolvedOptions` and `supportedLocalesOf`; each is asserted at exactly K per script.
  - Two arms must report blind: the off arm, and a new arm with `v8` on and `runtime_stats` off. The new arm also requires more than 0 V8 slices, so a blind result cannot come from a trace that measured nothing.
  - Total: 25 rows.

## Evidence

**Box build** (`~/chromium/src/out/Default`, lock `observe-D`, 17:43–18:05 UTC 2026-10-12):
```
13a14
> v8_enable_runtime_call_stats = true
v8_enable_runtime_call_stats = true
23m06.46s Build Succeeded: 1634 steps - 1.18/s
build rc=0 wall=1295s
released by observe-D
check_checkout_sync.sh: sync rc=0  PASS  all 48 copied files are identical in repo and checkout
```

**Real dump shape** (probe trace on the RCS build):
- dumps sit on `X` events as `args["runtime-call-stats"]`, a dict of `name -> [count, time]`;
- `v8.run` events are `X` with `args.fileName`.

The **first GREEN run read 19/25**: all six Intl rows were 0. The dump uses the bare builtin name (`DateTimeFormatConstructor`, 3+3 calls present), while the spec had assumed a `Builtin_` prefix. Fixed in ec28937, and the spec was corrected.

**GREEN** at 0516c2b (D's `verify_observe.py` from a private dir, box RCS build):
```
PASS DateTimeFormatConstructor site=http://127.0.0.1 script=127.0.0.1:35381/probe.html: 3 (want 3)
PASS DateTimeFormatPrototypeResolvedOptions site=http://127.0.0.1 script=127.0.0.1:35381/probe.html: 3 (want 3)
PASS DateTimeFormatSupportedLocalesOf site=http://127.0.0.1 script=127.0.0.1:35381/probe.html: 3 (want 3)
PASS DateTimeFormatConstructor site=http://127.0.0.1 script=127.0.0.1:35381/worker.js: 3 (want 3)
PASS DateTimeFormatPrototypeResolvedOptions site=http://127.0.0.1 script=127.0.0.1:35381/worker.js: 3 (want 3)
PASS DateTimeFormatSupportedLocalesOf site=http://127.0.0.1 script=127.0.0.1:35381/worker.js: 3 (want 3)
PASS off arm: report says Intl blind (want blind)
PASS v8 on, runtime_stats off: Intl blind with 21 V8 entry slices (want blind, >0 slices)
25/25 PASS
```

**RED** (`--red`, every expectation off by one): `0/25 PASS (RED mode: expected failures)`, rc=1.

**Unit tests:** Mac `python3 -m pytest -q scripts/test_observe_report.py scripts/test_verify_observe.py` gives `29 passed`. The box venv gives the same, `29 passed`.

**No regression on CI's tree.** CI's browser-verify list (main's copies in `~/camoucrome-verify`) run on the RCS build gives the same tallies as main's last CI run (38271241766):
- `sp1a PASS 8`
- `voices 5/5`
- `fonts 17 PASS 0 FAIL`
- `host_oracle 4/0`
- `windows_behaviour 14/0`
- `sp6b ALL_PASS`
- `crash_dumps 2/0`
- `verify_observe 17/17`

**Timing** (`verify_observe.py --timing`, 3 runs, `ua_200k_ms` / `todataurl_300_ms` / `trace_bytes`):

| run | off | on | intl |
|---|---|---|---|
| 1 | 94.7 / 30.3 / 244 871 | 854 / 33.6 / 52 534 115 | 952.7 / 32.3 / 52 548 451 |
| 2 | 92.9 / 29.4 / 247 911 | 883.7 / 33.1 / 52 535 207 | 1005.9 / 34.1 / 52 548 694 |
| 3 | 93.5 / 29.1 / 244 830 | 873.5 / 32.9 / 52 533 915 | 943.7 / 31.8 / 52 550 560 |

Within each run, the Intl recipe adds 8–14% to the on-arm getter loop and about 15 KB of `v8` events on this page.

**Final whole-branch review:** an independent reviewer found 0 Critical, 2 Important and 7 Minor. Both Important findings, plus a regex gap re-graded to Important, are fixed in 0516c2b, each with a test written to fail first:
- page site vs worker origin;
- attribution cost: 25 000 events × 3 000 slices went from 6.1 s to under 1.5 s;
- `Segments*` and `localeCompare` names, checked against this pin's CPP builtin list.

## Not done / open
- **Windows `out\Observe` not rebuilt** (followups item). E's arm 1 ran on the pre-RCS build, so rebuilding before arms 2/3 is the owner's call. Either:
  - rebuild with RCS and re-run arm 1 on it. On the box, main's 17 observer rows are unchanged on the RCS build with the stats category off.
  - or finish E on the current build and rebuild after.
- **Deferred minors:**
  - a malformed dump aborts the report;
  - the verify prints `0 (want 3)` rather than "blind" on a blind trace;
  - README Intl wording could say "C++ builtins only";
  - trace growth on real sites is unmeasured. The 15 KB figure is from a near-empty page, and Meta arms already filled the 200 MB buffer without `v8`.
- `Date.prototype.getTimezoneOffset` (CSA) and `Math` stay blind.
- **Rulings the owner may want to check:**
  - The report counts only `V8.Execute`/`V8.RunMicrotasks` dumps, although `IsolateInitialize`/`ScriptCompiler`/`NewContext` also carry dumps; none of those runs page JS.
  - The blind test reads the same two slice types.
  - The followups item "re-run --timing 3-5 times" is closed by the table above.

Do not merge without the owner's approval. After merge, CI's `verify_observe.py` asserts the Intl rows; box `out/Default` already has the arg.

🤖 Generated with [Claude Code](https://claude.com/claude-code)


<a id="pr-37"></a>
## #37 S5: Chrome's Google voices with stock's speak() shape (remote voices)

`s5/remote-voices` into `main`, opened 2026-10-13T12:00:21Z, merged 2026-10-17T02:56:14Z.

## S5: Chrome's Google voices, with stock's speak() shape

Step 2's baseline (finding 4) showed stock Chrome listing 19 remote Google voices (`localService: false`) after the local ones, where the fork lists none. Any page can read `speechSynthesis.getVoices()`, so the gap was a direct tell. Adding the list alone would open a second tell: the fork fakes `speak()` for every configured voice as a local voice does, with one `boundary` per word and an immediate `start`.

- Spec: `docs/superpowers/specs/2026-10-13-s5-remote-voices-design.md`. It ends with the amendments the measurements forced.
- Plan: `docs/superpowers/plans/2026-10-13-s5-remote-voices.md`.
- Evidence: `docs/superpowers/measurements/2026-10-s5-remote-voices.md`, §1–§6.

### What changes

- **Data.** `settings/voices.json` gains one shared `"remote"` table: the 19 voices, byte-exact from the stock 154 baseline. They equal stock 155's on a Mac. `gen.voices_keys` appends it after the local row (Windows, macOS). Linux is unchanged. The Go and Node clients call the Python generator.
- **Blink (`voices-ii`).** A configured voice with `localService: false` follows stock 154 as measured on the Windows host in the interactive session:
  - no boundaries;
  - `start` after 218–392 ms, drawn per speak;
  - 16.05 chars/s;
  - stock's measured rate curve, interpolated log-log over 0.1–2;
  - above rate 2, no event at all, as stock never starts one;
  - `pause()`/`resume()` fire no events, but move `end` by the paused time.

  No new config key: the behaviour derives from `localService`.
- **`cancel()` fix (predates S5; owner's ruling).** `cancel()` on any configured voice, local or remote, fired no event. Stock fires `error: interrupted` on both, and now the fork does too.
- **Probe and verify.** `scripts/measure_remote_voices.py` is the host probe:
  - it runs in session 1 through a temporary interactive task;
  - each launch is gated on chrome://gpu `GPU process crash count` == 0, with a session-0 RED;
  - all arms launch with the same three timer flags.

  `scripts/verify_voices_remote.py` holds the WSL rows (EXPECTED 11).
- **Docs.** The roadmap marks S2c, S3 and S3b merged. S4 is recorded as a session-0 harness artefact, folded into step2b. S5's voice half is done.

### Evidence

**Stock 154 on the Windows host** (§2, §4). All runs are in session 1, through a temporary interactive task. Every launch is gated on GPU crash count 0. The session-0 RED read crash count 1 and was marked UNMEASURED.
- **Voice list** (§2, 20 launches, 0 unmeasured): stock lists 3 local + the 19 Google voices in 9/10 launches; the other launch had only the 3 local. `--lang=fr`: the same 19, 10/10.
- **Google voice timing:**
  - start 109–1226 ms;
  - 0 boundaries;
  - 16 chars/s;
  - no cut-off at 540 chars (0/9).
- **Behaviour:**
  - rate curve 0.1 → ×3.04 … 2 → ×0.37 (deterministic to 0.2 %);
  - rate ≥ 2.25 never starts (15/15);
  - cancel gives `interrupted`;
  - pause/resume fire no events and `paused` stays false, while end moves by the pause;
  - the same text's start varies per call (69–2270 ms).

**WSL `content_shell`, `scripts/verify_voices_remote.py`** (EXPECTED 11):

| build | result |
|---|---|
| main + main's data | `1/9 FAIL` (9-row version): only the 3 local voices |
| main + S5 data | `2/9 FAIL`: 9 boundaries, start 4 ms, 12.5 cps, cancel fires no event, pause/resume events |
| S5 with the remote branch forced off (test-only mutant) | `3/9 FAIL` |
| S5 before the final-review fix | `9/11 FAIL`: R10 (start 397/390/397/397 ms), R6 (`paused` true) |
| **S5 final** (box `camoucrome/s5` = `0aec35868d`, after /simplify) | **`11/11 ALL_PASS`** |

**Regressions on WSL, S5 build:**
- `verify_sp4_voices` 5/5, `verify_voices_ii` 5/5, `verify_voices_pause` no FAIL.
- `verify_windows_behaviour` 12/14. V1/V3 read the box's client checkout, which is still on main; on the branch generator both rows evaluate true.
- `client/python` tests 54/54; `gen_keys --check` PASS; `check_additions_build` PASS.
- `gn check` for the speech module OK; checkdeps clean.
- Export: only `patches/voices-ii.patch` changes; `check_checkout_sync` PASS, 48/48 files identical.

**Host, fork against stock** (§4):

| cell | result |
|---|---|
| RED, fork on main (n = 3) | boundaries, start 0–3 ms, rate 3 plays, cancel silent |
| GREEN, fork on S5 rate-table build (n = 10) | every remote cell's event kinds equal stock's: 0 boundaries; cancel gives start, then error:interrupted; pause gives start, end; rate 3 never starts |
| GREEN durations | within 20 % of stock (−18 % … +13 %, the voices-ii per-text jitter) |
| GREEN starts | inside stock's pooled range |

The final-review fix (per-speak start, `paused` false) came after that host run. Its evidence is the stock readings plus WSL R6/R10.

**Windows build:** `out\Release` with the 2 speech files built in 55 steps. The Windows tree was then restored byte-exact to main and rebuilt in 55 steps, for step2b's measurements.

**/simplify pass** (behaviour unchanged, 11/11 after it):
- the remote decision is made once per speak (`camou_remote_`);
- the start is a `base::RandDouble()` draw;
- a paused remote speak waits out its remaining time instead of polling every 100 ms;
- the rate curve is simpler;
- the verify reuses `verify_voices_ii`'s `predicted_jitter`.

`verify_voices_ii` has been flaky on its two timing rows since a host reboot on 2026-10-14. An A/B on the same box gave 2/3 runs at 5/5 both before and after the change.

### Not done / gaps (measurement §6)

- **Not faked:**
  - stock's Google voices fail when offline;
  - stock's list is missing in about 1 of 10 launches, while the fork always lists it;
  - stock's start has a long network tail.
- **Unmeasured:**
  - the exact high-rate threshold inside (2, 2.25];
  - `pause`/`cancel` during the start delay;
  - activation (`not-allowed`).
- **The local fake path, before S5 and unchanged by it:**
  - start ≈ 0 ms against stock's ≈ 255;
  - rate-2 ratio 0.5 against stock's 0.70;
  - pause does not move the end.
- **Not rerun:** `windows_verify_set.py green` (21/21) on the S5 Windows build. The tree had to go back to main for step2b.
- **Host runs were in a disconnected RDP session.** Stock's SAPI voices fail there, so the host comparison covers only the remote voice.
- **Linux:** still no voice list.
- **Deferred review minors** (ledger):
  - the `camou_end_due_` comment;
  - R1 does not read `voiceURI`;
  - the empty-text and `fakeCompletion=false` checks are one-off launches, not rows;
  - one lambda's indentation.

**Box landing after merge:** `git -C ~/chromium/src branch -f camoucrome/main camoucrome/s5` (`0aec35868d`). Until then `camoucrome/main` stays at `1e1c03b5fe`, and the checkout sits on `camoucrome/s5`.

Not merged; the owner decides.

🤖 Generated with [Claude Code](https://claude.com/claude-code)


<a id="pr-38"></a>
## #38 step2b: session-0 GPU gate for host harnesses, 20 detector pages, fork-at-main baseline in session 1

`step2b-detectors` into `main`, opened 2026-10-14T00:53:05Z, merged 2026-10-17T02:59:08Z.

Step 2b. Spec: `docs/superpowers/specs/2026-10-13-step2b-detectors-design.md`. Plan: `docs/superpowers/plans/2026-10-13-step2b-detectors.md`. Measurement: `docs/superpowers/measurements/2026-10-step2b-detectors.md`.

This PR does three things:
- **Session-0 fix (S4, folded in).** Every Windows host harness now runs in the owner's interactive session (`scripts/windows/run-interactive.ps1`). Every launch is gated on `chrome://gpu`'s GPU crash count (`scripts/gpu_gate.py`). A nonzero or unreadable count is `UNMEASURED`, never PASS or FAIL.
  - Gated paths: `lib_shell`, which covers all 21 Windows set entries, plus `measure_step2`, `verify_host_oracle`, `verify_s3_host` and `winhost`.
  - Where no context or port exists, a session-id check stands in: `camoucrome.probe`, the client launches, and `winhost.dump_dom`.
- **20 public detector pages**, up from 4. Each gets verdict parsers, a verdict table in `tables.md`, a `blocked` row and `scrub()` before commit.
- **Fork at main on Windows, recaptured in session 1.** It overturns step 2's "fork unstable" rows: they were the session-0 GPU crash.

## Evidence

**Builds** (host, `build_lock`):
- `out\Release` at main `69dda6b`: dirty paths checked against main's change set before the reset (`miss=0`); `apply rc=0`; `Build Succeeded: 9400 steps`, 2 h 44 m.
- The first attempt at 16 jobs failed: `LLVM ERROR: out of memory`. The commit limit is 38.3 GB and WSL holds about 24 GB of it. The rebuild ran at `-j 8`.
- `out\Observe`: only `+v8_enable_runtime_call_stats = true` added; `Build Succeeded: 6148 steps`, 1 h 46 m.

**Gates RED in session 0, run directly over sshgate:**

| path | session gate (rc 3) | crash gate, `CAMOU_ALLOW_SESSION0=1` |
|---|---|---|
| `windows_verify_set.py` | `UNMEASURED session=0` | `BAD verify_sp1b.py: UNMEASURED (10)`, `0/1 entries OK; 1 UNMEASURED` |
| `lib_shell` (`verify_sp1b.py`) | — | 10 × `UNMEASURED gpu-crash=1` |
| `verify_host_oracle.py` | `UNMEASURED session=0` | `UNMEASURED gpu-crash=1 (O3)` and `(O4)` |
| `verify_s3_host.py` | `UNMEASURED session=0` | `UNMEASURED gpu-crash=2`, rc 3 |
| `measure_step2.py` | `UNMEASURED session=0` | noise: `GpuCrashed: UNMEASURED gpu-crash=1`; detectors: `det.sannysoft = UNMEASURED`, `gpu_crash=1`, raw text removed |
| `winhost` (its generated PowerShell) | `SESSION=0` | `GPU process crash count :1` |

**GREEN in session 1, RDP connected:**
- `windows_verify_set.py green`: `20/21 entries OK (green); 0 UNMEASURED`.
  - `verify_host_oracle` fails exactly O2, with the same message as 2026-10-04, so O2 is not the GPU artefact.
  - `verify_d_pointer_touch` is OK with V1 NOT MEASURED, by the owner's choice: the host has a mouse.
  - The one BAD is `verify_windows_sandbox_env` A2. The RDP audio device runs at 44100, which equals the no-device fallback that A2 excludes. A session-0 control passes A2 at 48000. This is recorded as an environment finding; the verify is unchanged.
- `verify_s3_host.py`: `7/7 ALL_PASS`.
- `winhost` wrapped: `SESSION=1`, crash count 0, no task or Chrome left behind.

**Measurement**, every run with `session=1`, 0 errors, 0 GPU crashes:
- **Liveness.** 20 of 24 pages live. Dropped:
  - brotector and BotD: GitHub Pages 404;
  - areyouheadless: 502, twice;
  - the Turnstile demo: token `XXXX.DUMMY.TOKEN.XXXX`.
- **Null runs.** Two runs, stock in both arms. After calibration, `compare` gives `0 rows disagree outside VOLATILE; 1 site cells unmeasured, skipped`.
- **Plants.** WebShare off, and AutomationControlled off. Every site but five browserleaks pages sees at least one plant. Those five are blind to both, and the doc says so.
- **Fork runs.** Three runs: one over RDP, and A and B in the console session after an unattended host reboot at 00:07 killed an RDP run. `compare A B` gives 2 rows, both Fingerprint Pro fork/headless: Proxy Detection and Suspect Score. They are findings.
- **Baseline.** `step2b-main/` is run B, put through `scrub` with the host's geo, ISP and user strings. A grep finds no address (only UA versions `154.0.0.0` / `99.0.0.0`), and no city, ISP or user name.

**Tests:**
- `python3 -m pytest -q scripts client/python/tests` → `406 passed`.
- `python3 scripts/test_lib_shell_launch.py` → `26 PASS`, frozen argv unchanged. All gates are no-ops off Windows.

**Final review.** An independent reviewer found 0 Critical, 6 Important and 8 Minor. The Important findings, and one Minor re-graded to Important, are fixed in `559f37e`, each with a test written to fail first:
- V1 now decides by `SM_MOUSEPRESENT`, not the measured value;
- scrub leaks fixed, and reduced UA versions are no longer masked;
- standalone verifies with an UNMEASURED line exit 3;
- `measure_step2 run` exits 1 and `compare` exits 2 when cells are unmeasured;
- a failed gate read is per-site UNMEASURED;
- CI runs `test_step2_rows.py` and `test_verify_d_pointer_touch.py`.

## Findings (fork against stock, session 1)

- **Remote voices.** CreepJS counts no remote voices on the fork (`unsupported` vs 19). This is step 2's finding 4; S5 (#37) addresses it.
- **Browser Tampering.** Fingerprint Pro says "Yes" on the fork in headless mode in every run, and in headed mode in one. Stock headed also read "Yes" once.
- **Timezone.**
  - Fingerprint Pro reports "timezone mismatch" on the VPN signal, and Pixelscan says "Timezone spoofed". The cause is the identity's `America/Chicago` against the host IP.
  - Fingerprint Pro also gives a low-confidence "residential proxy" that flips between runs.
- **fingerprint_scan.** The fork has no Summarizer (`NotSupportedError`/`TIMEOUT`).
- **Favourable.**
  - fingerprint_scan bot score 100 → 20/100.
  - The webdriver verdicts of dbi_bot, rebrowser, incolumitas and iphey pass on the fork.
  - No `Runtime.enable` or init-script leak.
  - Stability is empty and HEVC/WebGPU match stock (overturning step 2's §5).

## Decided by the owner (2026-10-14, commit `23554f7`)

- **Timezone label.** Fingerprint Pro's "timezone mismatch" stays `expected` in the table: the fork does what the config says.
  - Roadmap backlog item 13 is opened: derive timezone and locale from the proxy's IP (geoip), or warn.
  - The next recapture uses an identity whose zone matches the IP.
- **Country and zone.** The repo is public, so the step2b baseline now also scrubs the host's country (`<country>`) and time zone (`<host-zone>`). A grep finds no country, zone, address, place, ISP or user name. `step2-154/`, public since 2026-10-04, is not rewritten.

## Still for the owner

- **Windows set in session 1.** The set reads 20/21 there because of A2. If you want it GREEN, A2 needs the same premise treatment V1 got.
- **Deferred minors** (listed in the measurement doc):
  - `CdpChrome` error masking and its task lifetime are not run on the host;
  - `verify_s3_host` gives a traceback on `Unmeasured`;
  - edge cases in `parse_fingerprint_pro`;
  - task-wrapper robustness (unquoted path, start race);
  - three broad EXPECTED keys.
- **Not run on the host:** `winhost` over a real ssh master from WSL (none exists). Its generated PowerShell was run through sshgate in both sessions.

Not merged: waiting for the owner.

🤖 Generated with [Claude Code](https://claude.com/claude-code)


<a id="pr-39"></a>
## #39 SP2c: humanized wheel — CDP mouseWheel as Windows notches

`worktree-sp2c-humanized-wheel` into `main`, opened 2026-10-17T11:19:43Z, merged 2026-10-18T01:40:07Z.

## What

SP2c: humanized wheel. This is the first of the three sub-projects of backlog item 14, "Real input instead of node clicks".

With `humanize:enabled` and an effective Windows identity, a CDP `Input.dispatchMouseEvent` `mouseWheel` reaches the page as whole notches. Each notch is one `wheel` event of `deltaY 100` / `wheelDeltaY -120` / `deltaMode 0`, and the notches are 18–60 ms apart. This is the shape stock Chrome 154 gives a real Windows mouse wheel. Stock CDP gives one event carrying the whole delta, and that one event is the tell.

The effective identity is the claimed OS, or the build OS when nothing is claimed. Without the config, or under another OS, the path is stock's, byte for byte.

- Spec: `docs/superpowers/specs/2026-10-17-sp2c-humanized-wheel-design.md`
- Plan: `docs/superpowers/plans/2026-10-17-sp2c-humanized-wheel.md`
- Measurement and evidence: `docs/superpowers/measurements/2026-10-sp2c-wheel.md`

## Changes

- `additions/camoucfg/mouse_trajectories.{h,cc}` add `QuantizeWheel`. It rounds each axis to whole notches of 100 px. A non-zero delta below one notch becomes 1 notch. Each axis is clamped to 60 notches (6000 px), and a non-finite delta becomes zero. It also adds `kWindowsNotchCssPx`.
- `patches/sp2c-humanized-wheel.patch` changes `content/browser/devtools/protocol/input_handler.{cc,h}`. `InjectWheelEvent` gates on humanize, Windows and non-zero notches. When the gate holds, it schedules one `kScrollByPixel` event per notch with phase Began, then Changed. Only the last notch carries `kFromDebugger` and answers the CDP command. If the handler or widget is gone, the command answers `sendFailure`, so it never hangs.
- `scripts/capture_wheel_oracle.py` and `baselines/chrome-8037-wheel.json` hold the stock Chrome 154 oracle from the Windows host: real `SendInput` notches against CDP wheels. `scripts/winhost.py`'s `cdp_eval` gains `act_ps` and `window_style`.
- `scripts/verify_sp2c.py` has 11 rows and is wired into `build-verify.yml`. `test_capture_wheel_oracle.py` is added to the CI pytest list.

## Evidence

**Oracle**: stock Chrome `154.0.8037.93` on the Windows host, session 1, GPU crash count 0 on every arm.

| arm | n_wheel | deltaY | wheelDeltaY | mode |
|---|---|---|---|---|
| real1 (`SendInput` 1 notch) | 1 | 100 | -120 | 0 |
| real3 (3 notches, 40 ms apart) | 3 | 100 ×3 | -120 ×3 | 0 |
| cdp100 | 1 | 100 | -120 | 0 |
| cdp300 | 1 | 300 | -120 | 0 |

The RED gate's real3 against cdp300 differ on event count (3 against 1) and on the ratio `wheelDeltaY/deltaY` (-1.2 against -0.4).

**Unit tests**: `components_unittests --gtest_filter='MouseTrajectoriesTest.*'` on the box.
- RED, the test alone: `error: use of undeclared identifier 'QuantizeWheel'`.
- GREEN: `[  PASSED  ] 10 tests.`
- Mutant: the clamp moved to `kMaxWheelNotches + 1`. `QuantizeWheelClampsAndRejectsNonFinite` FAILED; restored, 10 passed.

**Header deps**:
- `gn check out/Default //content/browser:browser` reports `Header dependency check OK`.
- `checkdeps.py content/browser/devtools/protocol` reports `SUCCESS`.

**`verify_sp2c.py`**, WSL `chrome` built from `out/Default`, box `camoucrome/main` = `3da17048d5`.

| run | result |
|---|---|
| before SP2c (`0aec35868d`) | R2, R3, R7 FAIL, rc 1 |
| SP2c | 11/11 PASS, rc 0 |
| mutant `EffectiveOsIsWindows() → true` | R4, R5 FAIL |
| mutant: dead-widget branch never answers | R8, R11 FAIL `{"returned": false}`; R10 PASS (bfcache keeps the widget alive) |
| row-8 guard RED (the child waits 120 s) | R8 FAIL after 45 s; no Chrome left behind |

The 11 rows:
- R1 no config;
- R2 3 notches, gaps between 15 and 75 ms;
- R3 zero, sub-notch and X axis;
- R4 macOS;
- R5 nothing claimed;
- R6 keys and native accessors;
- R7 back-to-back;
- R8 same-document navigation;
- R9 DSF 2;
- R10 cross-site navigation;
- R11 cross-site navigation with bfcache off.

**Change-set gates**:
- Round trip: the patch re-applied onto `HEAD~1` gives `git diff --cached HEAD` = 0 lines, and `gn check` is OK.
- `check_checkout_sync.sh local` reports `PASS all 48 copied files are identical`.
- The export gate `git status --porcelain additions patches settings` is empty.

**Local**:
- `python3 -m pytest -q scripts/test_capture_wheel_oracle.py scripts/test_winhost.py` gives 14 passed.
- `check_additions_build.py` PASS.
- `gen_keys.py --check` PASS.

## Not run / open

- **The host-native arm was not run.** It compares `chrome.exe` with `humanize:enabled` against the oracle. It needs a Windows tree rebuild, which is the owner's call.
- **Animation is unmeasured.** No arm animated, real input included, possibly because of RDP. The notches use the same `kScrollByPixel` units as a real notch. It needs a console (non-RDP) session.
- **DPR is measured only at 100 %.** The host runs at 96 DPI. R9 checks the DSF-2 arithmetic on WSL only.
- **The 18–60 ms cadence is Camoufox's,** not measured from a hand.
- **The 156 re-pin must carry `sp2c-humanized-wheel`.**

Deferred minors from the final review:
- Diagonal notches carry both axes in one event.
- Intermediate notches lack `kFromDebugger`, so `setIgnoreInputEvents` drops them. SP2b behaves the same.
- Clients that do not await each wheel command interleave notches.
- R2's gap window may flake under CI load.
- R6 compares the key count, not the key list.
- A `red_gate` message says "animation".
- Each notch is allocated on the heap, and the cadence is hardcoded.
- Per-notch `cancelable` is not recorded.

🤖 Generated with [Claude Code](https://claude.com/claude-code)


<a id="pr-40"></a>
## #40 Observer: automated facebook recon (observe-auto, arms 1 and 3) with a calibrated baseline

`e-fb-auto` into `main`, opened 2026-10-18T01:42:32Z, open.

## What

Automated facebook recon. `scripts/windows/observe-auto.ps1` runs observer arm 1 (logged out) and arm 3 (the backed-up login) on the Windows host, one load each, with no input. `scripts/observe_judge.py` grades each arm `PASS`, `FAIL` (a baseline group is gone) or `UNMEASURED` (it did not measure, an expired login included). The owner allowed this narrow form on 2026-10-17. It is never scheduled or repeated, arm 2 (the login) stays manual, and tooling never types credentials.

- Spec: `docs/superpowers/specs/2026-10-17-observe-auto-fb-design.md`
- Plan: `docs/superpowers/plans/2026-10-17-observe-auto-fb.md`
- Measurements: `docs/superpowers/measurements/2026-10-17-fb-observe-intl.md` (§7 the 154 host runs, §8 calibration on 156)
- Operator guide: `docs/observer/README.md`, "Unattended recon (facebook)"

## Changes

- `scripts/observe_judge.py` (new): `summary`, `baseline` and `judge`, names and counts only. The judge reads a crash as `UNMEASURED` (exit 3), not `FAIL`. `baseline` refuses an unmeasured run. `judge` refuses a calibrated baseline with no entry for the arm (exit 2). Arm 3's login proof is the `c_user`/`xs` cookie names, read from `summary.json` once `cookies.db` is cleaned up.
- `scripts/windows/observe-recon.ps1`: unattended mode (`-Wait`, `-Out`, `-FromProfile`, `-KillBelowGB`): WM_CLOSE, a low-memory watchdog, `run.json`, and a catch for a chrome process that exits during close.
- `scripts/windows/observe-auto.ps1` (new): the one command. It gates on the owner's Active session, no native ninja/siso build, and 8 GB of commit headroom. On a timeout it gives `UNMEASURED` and stops the scheduled task. A judge that never ran is `UNMEASURED`. It deletes the profile copies and `cookies.db` afterwards.
- `docs/observer/baselines/facebook-auto.json` (new): the calibrated baseline, 2 runs on the 156 `out\Observe`.
- Docs: `CLAUDE.md` rule bullet, README, the 10-17 measurement doc, followups, the roadmap line.

## Evidence

Tests (Mac, at 44cb39c):

```
$ python3 -m pytest -q scripts client/python/tests
458 passed in 5.70s
```

Host runs, 2026-10-17 22:28–22:42 UTC, `out\Observe` 156.0.8078.36. The host files matched the branch by SHA-256 before the first load. The owner's session was Active, with 22.4 GB of headroom and no native build running.

| run | result |
|---|---|
| calibration 1 `20261017-222818` | arm 1 `PASS`, arm 3 `PASS`, `RC=0` |
| calibration 2 `20261017-223227` | arm 1 `PASS`, arm 3 `PASS`, `RC=0` |
| `observe_judge.py baseline` over both | rc 0; arm 1 requires 9 groups, arm 3 requires 7 |
| null test against the new baseline `20261017-223636` | every required row `PASS`, `RESULT PASS`, `RC=0` |
| RED intl blind (`-Arms 1 -NoIntl`) `20261017-224036` | `UNMEASURED arm1 intl blind`, `RC=3` |
| RED planted FAIL (judge only) | `FAIL arm1 fonts 0`, `arm1 FAIL`, exit 1 |
| RED GPU crash (judge only, `gpu_exit_lines` 0→1 on a copy) | `UNMEASURED arm1 gpu-crash lines=1`, exit 3 |
| sanity: manual 10-17 arm 3 summary | holds all 7 arm-3 required groups |

Host REDs on 154, 2026-10-17 (§7):

| run | result |
|---|---|
| gate: headroom (`-MinHeadroomGB 1000`) | `UNMEASURED low-memory`, exit 3 |
| gate: native build (a fake `ninja.exe`) | `UNMEASURED native build running (ninja)`, exit 3 |
| watchdog (`-KillBelowGB 1000`) | force-stopped, `low_memory_kill` true, `UNMEASURED no trace`, exit 3 |
| expired login (empty profile) | `UNMEASURED session expired`, exit 3 |
| GPU signal | `gpu_exit_lines` 1 in session 0, 0 in session 1 |
| recon throw | `ERROR: missing -FromProfile`, `EXIT=1` in 5 s |
| README detached launch during a native build | `RESULT UNMEASURED`, `RC=3`, no browser |

Final-review fixes, each with a failing test first: judge crash read as `FAIL`; baseline without the arm; baseline accepting an unmeasured run; arm-3 login proof after the `cookies.db` cleanup. On the host: a stale `$LASTEXITCODE` read as `PASS`, and a timeout that left recon running. For the second, `Unregister-ScheduledTask` was measured not to stop a running instance, while `Stop-ScheduledTask` does.

Privacy: the baseline holds group names, Intl built-in names and request counts only. The plan's grep for IPs, query strings and login cookies over it is empty. Each facebook load and each cookie stays on the host. This branch's history was rewritten on 2026-10-18, at the owner's request, to drop host-identifying text from older commits. The tip tree is identical to before the rewrite, apart from 44cb39c.

## Not checked

- The planted FAIL and the GPU crash were checked at the judge, not through a whole `observe-auto.ps1` run. The mapping from exit code to `RESULT` was checked by a host snippet.
- Three samples per arm, on one day, with one account. Arm 3's `fonts` is 1 call per load, the thinnest required row.
- The host's Google Chrome is still 154, so there is no stock comparison on 156.
- Deferred minors, from the final review:
  - coverage is not checked against `wait_s`;
  - usage-error messages are not asserted;
  - `-Arms` has no `ValidateSet`;
  - the gate accepts any Active session;
  - `-FromProfile` is unquoted;
  - the ≤ 10-run rule while another build holds the lock is not documented.

🤖 Generated with [Claude Code](https://claude.com/claude-code)


## Workflow runs

| run | workflow | event | branch | head | conclusion | started (UTC) | seconds |
|---|---|---|---|---|---|---|---|
| <a id="run-36212517509"></a>36212517509 | checks | push | `main` | d36cb8da6a | success | 2026-09-26T02:42:12Z | 38 |
| <a id="run-36959991139"></a>36959991139 | checks | push | `docs/long-term-roadmap` | (not in the rewritten history) | success | 2026-10-02T03:23:55Z | 39 |
| <a id="run-36960145232"></a>36960145232 | checks | push | `docs/long-term-roadmap` | ca052c331a | success | 2026-10-02T03:26:00Z | 30 |
| <a id="run-36960163090"></a>36960163090 | checks | pull_request | `docs/long-term-roadmap` | ca052c331a | success | 2026-10-02T03:26:15Z | 35 |
| <a id="run-36960330104"></a>36960330104 | checks | push | `main` | 5c1e19dac9 | success | 2026-10-02T03:28:35Z | 39 |
| <a id="run-36974876383"></a>36974876383 | build-verify | workflow_dispatch | `main` | 5c1e19dac9 | success | 2026-10-02T06:42:44Z | 875 |
| <a id="run-36979902198"></a>36979902198 | checks | push | `step0/tools` | 33714ce63b | success | 2026-10-02T07:41:31Z | 36 |
| <a id="run-36979906403"></a>36979906403 | checks | pull_request | `step0/tools` | 33714ce63b | success | 2026-10-02T07:41:34Z | 42 |
| <a id="run-37038168658"></a>37038168658 | checks | push | `main` | 200276a053 | success | 2026-10-02T17:03:53Z | 38 |
| <a id="run-37038168816"></a>37038168816 | build-verify | push | `main` | 200276a053 | failure | 2026-10-02T17:03:53Z | 45 |
| <a id="run-37038329463"></a>37038329463 | checks | push | `repin/8037` | 0b30d02232 | success | 2026-10-02T17:05:17Z | 42 |
| <a id="run-37038352238"></a>37038352238 | checks | pull_request | `repin/8037` | 0b30d02232 | success | 2026-10-02T17:05:29Z | 44 |
| <a id="run-37087364720"></a>37087364720 | build-verify | push | `main` | 3715b92f4b | success | 2026-10-03T01:46:19Z | 228 |
| <a id="run-37087364740"></a>37087364740 | checks | push | `main` | 3715b92f4b | success | 2026-10-03T01:46:19Z | 46 |
| <a id="run-37089853544"></a>37089853544 | checks | push | `step1/lib-shell-paths` | 6a30db065d | success | 2026-10-03T02:27:06Z | 42 |
| <a id="run-37090080241"></a>37090080241 | checks | pull_request | `step1/lib-shell-paths` | 6a30db065d | success | 2026-10-03T02:31:07Z | 45 |
| <a id="run-37090208326"></a>37090208326 | checks | push | `main` | 3cbc314684 | success | 2026-10-03T02:33:18Z | 45 |
| <a id="run-37090208372"></a>37090208372 | build-verify | push | `main` | 3cbc314684 | success | 2026-10-03T02:33:18Z | 230 |
| <a id="run-37090976580"></a>37090976580 | checks | push | `step1/one-chrome-path` | e829627cd0 | success | 2026-10-03T02:46:40Z | 46 |
| <a id="run-37091275519"></a>37091275519 | checks | pull_request | `step1/one-chrome-path` | e829627cd0 | success | 2026-10-03T02:51:59Z | 37 |
| <a id="run-37091562851"></a>37091562851 | build-verify | push | `main` | fefba81925 | success | 2026-10-03T02:57:15Z | 233 |
| <a id="run-37091562891"></a>37091562891 | checks | push | `main` | fefba81925 | success | 2026-10-03T02:57:15Z | 40 |
| <a id="run-37091928914"></a>37091928914 | checks | push | `step1/one-path-block` | 3e600e3323 | success | 2026-10-03T03:03:37Z | 40 |
| <a id="run-37092206509"></a>37092206509 | checks | pull_request | `step1/one-path-block` | 3e600e3323 | success | 2026-10-03T03:08:36Z | 29 |
| <a id="run-37093621805"></a>37093621805 | checks | push | `step1/one-path-block` | 9c9f1809de | success | 2026-10-03T03:33:53Z | 28 |
| <a id="run-37093624180"></a>37093624180 | checks | pull_request | `step1/one-path-block` | 9c9f1809de | success | 2026-10-03T03:33:56Z | 40 |
| <a id="run-37093937204"></a>37093937204 | checks | push | `step1/one-path-block` | 27067512d6 | success | 2026-10-03T03:39:35Z | 43 |
| <a id="run-37093939342"></a>37093939342 | checks | pull_request | `step1/one-path-block` | 27067512d6 | success | 2026-10-03T03:39:37Z | 34 |
| <a id="run-37094050304"></a>37094050304 | checks | push | `step1/one-path-block` | ea341ab4c6 | success | 2026-10-03T03:41:31Z | 43 |
| <a id="run-37094052774"></a>37094052774 | checks | pull_request | `step1/one-path-block` | ea341ab4c6 | success | 2026-10-03T03:41:33Z | 39 |
| <a id="run-37102382988"></a>37102382988 | build-verify | push | `main` | aeb79dc514 | success | 2026-10-03T06:14:11Z | 232 |
| <a id="run-37102383039"></a>37102383039 | checks | push | `main` | aeb79dc514 | success | 2026-10-03T06:14:11Z | 46 |
| <a id="run-37104255614"></a>37104255614 | checks | push | `step1/windows-substrate` | 27133fcb65 | success | 2026-10-03T06:48:29Z | 45 |
| <a id="run-37105685279"></a>37105685279 | checks | push | `step1/windows-substrate` | b1863daf2f | success | 2026-10-03T07:14:23Z | 41 |
| <a id="run-37105792045"></a>37105792045 | checks | pull_request | `step1/windows-substrate` | b1863daf2f | success | 2026-10-03T07:16:14Z | 34 |
| <a id="run-37105921509"></a>37105921509 | checks | push | `main` | b8b9ca7875 | success | 2026-10-03T07:18:36Z | 38 |
| <a id="run-37106075813"></a>37106075813 | checks | push | `step1/sandboxed-launch` | 3481e0dce1 | success | 2026-10-03T07:21:27Z | 35 |
| <a id="run-37106174322"></a>37106174322 | checks | push | `step1/sandboxed-launch` | 86d94547ec | success | 2026-10-03T07:23:15Z | 43 |
| <a id="run-37106311438"></a>37106311438 | checks | push | `step1/sandboxed-launch` | 65aba4111f | success | 2026-10-03T07:25:43Z | 37 |
| <a id="run-37106366201"></a>37106366201 | checks | pull_request | `step1/sandboxed-launch` | 65aba4111f | success | 2026-10-03T07:26:43Z | 42 |
| <a id="run-37106509969"></a>37106509969 | checks | push | `main` | 6bdb881168 | success | 2026-10-03T07:29:29Z | 49 |
| <a id="run-37106510060"></a>37106510060 | build-verify | push | `main` | 6bdb881168 | success | 2026-10-03T07:29:29Z | 232 |
| <a id="run-37106631917"></a>37106631917 | checks | push | `step1/windows-worker-parity` | e78ffd5451 | success | 2026-10-03T07:31:32Z | 50 |
| <a id="run-37106696159"></a>37106696159 | checks | push | `step1/windows-worker-parity` | d2ee0ee3d5 | success | 2026-10-03T07:32:42Z | 53 |
| <a id="run-37106726839"></a>37106726839 | checks | pull_request | `step1/windows-worker-parity` | d2ee0ee3d5 | success | 2026-10-03T07:33:15Z | 39 |
| <a id="run-37106844441"></a>37106844441 | build-verify | push | `main` | fe5c774a47 | success | 2026-10-03T07:35:22Z | 219 |
| <a id="run-37106844476"></a>37106844476 | checks | push | `main` | fe5c774a47 | success | 2026-10-03T07:35:22Z | 37 |
| <a id="run-37106905178"></a>37106905178 | checks | push | `step1/windows-camou-exe` | 7654d2ebc7 | success | 2026-10-03T07:36:29Z | 45 |
| <a id="run-37106919793"></a>37106919793 | checks | pull_request | `step1/windows-camou-exe` | 7654d2ebc7 | success | 2026-10-03T07:36:45Z | 53 |
| <a id="run-37107104715"></a>37107104715 | checks | push | `main` | ec6366c33c | success | 2026-10-03T07:40:08Z | 43 |
| <a id="run-37107468159"></a>37107468159 | checks | push | `step1/windows-crashpad` | 79df030b4b | success | 2026-10-03T07:46:38Z | 44 |
| <a id="run-37107488900"></a>37107488900 | checks | pull_request | `step1/windows-crashpad` | 79df030b4b | success | 2026-10-03T07:47:00Z | 40 |
| <a id="run-37108095319"></a>37108095319 | checks | push | `main` | e7eb752267 | success | 2026-10-03T07:57:54Z | 34 |
| <a id="run-37108519276"></a>37108519276 | checks | push | `step1/windows-python-client` | 4972612ba1 | success | 2026-10-03T08:05:20Z | 44 |
| <a id="run-37108573189"></a>37108573189 | checks | push | `step1/windows-python-client` | 51ff025e45 | success | 2026-10-03T08:06:20Z | 41 |
| <a id="run-37108654402"></a>37108654402 | checks | push | `step1/windows-python-client` | 9e7ae9aa98 | success | 2026-10-03T08:07:48Z | 38 |
| <a id="run-37108758785"></a>37108758785 | checks | push | `step1/windows-python-client` | eb9bbea237 | success | 2026-10-03T08:09:39Z | 74 |
| <a id="run-37108829726"></a>37108829726 | checks | push | `step1/windows-python-client` | 09da77ac78 | success | 2026-10-03T08:10:51Z | 45 |
| <a id="run-37108985847"></a>37108985847 | checks | push | `step1/windows-python-client` | f9e9556dcb | success | 2026-10-03T08:13:36Z | 44 |
| <a id="run-37109041739"></a>37109041739 | checks | push | `step1/windows-python-client` | 472a010ef6 | success | 2026-10-03T08:14:36Z | 36 |
| <a id="run-37109163817"></a>37109163817 | checks | push | `step1/windows-python-client` | cbea2e3160 | success | 2026-10-03T08:16:45Z | 40 |
| <a id="run-37109366951"></a>37109366951 | checks | push | `step1/windows-python-client` | 455ca2be5a | success | 2026-10-03T08:20:25Z | 37 |
| <a id="run-37109422529"></a>37109422529 | checks | pull_request | `step1/windows-python-client` | 455ca2be5a | success | 2026-10-03T08:21:25Z | 49 |
| <a id="run-37109689126"></a>37109689126 | checks | push | `step1/windows-crash-dumps` | aa4bb2c319 | success | 2026-10-03T08:26:10Z | 45 |
| <a id="run-37110006505"></a>37110006505 | checks | push | `step1/windows-crash-dumps` | 4665951db3 | success | 2026-10-03T08:31:44Z | 41 |
| <a id="run-37110038070"></a>37110038070 | checks | pull_request | `step1/windows-crash-dumps` | 4665951db3 | success | 2026-10-03T08:32:16Z | 40 |
| <a id="run-37110216257"></a>37110216257 | checks | push | `step1/windows-crash-dumps` | 3eac619375 | success | 2026-10-03T08:35:25Z | 41 |
| <a id="run-37110218908"></a>37110218908 | checks | pull_request | `step1/windows-crash-dumps` | 3eac619375 | success | 2026-10-03T08:35:28Z | 38 |
| <a id="run-37110357100"></a>37110357100 | build-verify | push | `main` | 2b02c3d785 | success | 2026-10-03T08:38:00Z | 232 |
| <a id="run-37110357175"></a>37110357175 | checks | push | `main` | 2b02c3d785 | success | 2026-10-03T08:38:00Z | 30 |
| <a id="run-37110623297"></a>37110623297 | checks | push | `main` | f66a9c636e | success | 2026-10-03T08:42:57Z | 45 |
| <a id="run-37110623320"></a>37110623320 | build-verify | push | `main` | f66a9c636e | success | 2026-10-03T08:42:57Z | 218 |
| <a id="run-37111364448"></a>37111364448 | checks | push | `step1/cleanup-temp-dirs` | (not in the rewritten history) | success | 2026-10-03T08:56:24Z | 38 |
| <a id="run-37111517963"></a>37111517963 | checks | push | `step1/cleanup-temp-dirs` | 724a40e702 | success | 2026-10-03T08:59:12Z | 38 |
| <a id="run-37111939198"></a>37111939198 | checks | pull_request | `step1/cleanup-temp-dirs` | 724a40e702 | success | 2026-10-03T09:06:40Z | 43 |
| <a id="run-37112232612"></a>37112232612 | checks | push | `step1/close-removes-after-exit` | 37a1d7f6d7 | success | 2026-10-03T09:11:55Z | 46 |
| <a id="run-37112368818"></a>37112368818 | checks | push | `step1/close-removes-after-exit` | 252bdaa311 | success | 2026-10-03T09:14:24Z | 45 |
| <a id="run-37112677781"></a>37112677781 | checks | push | `step1/close-removes-after-exit` | (not in the rewritten history) | success | 2026-10-03T09:19:54Z | 39 |
| <a id="run-37112796353"></a>37112796353 | checks | push | `step1/close-removes-after-exit` | c665381419 | success | 2026-10-03T09:21:55Z | 41 |
| <a id="run-37112822527"></a>37112822527 | checks | pull_request | `step1/close-removes-after-exit` | c665381419 | success | 2026-10-03T09:22:21Z | 34 |
| <a id="run-37113071443"></a>37113071443 | checks | push | `step1/windows-go-node` | a9fa49b1de | success | 2026-10-03T09:26:45Z | 42 |
| <a id="run-37113181110"></a>37113181110 | checks | push | `step1/windows-go-node` | 7528a76687 | success | 2026-10-03T09:28:45Z | 47 |
| <a id="run-37113214777"></a>37113214777 | checks | push | `step1/windows-go-node` | f23bf13571 | success | 2026-10-03T09:29:23Z | 43 |
| <a id="run-37113466821"></a>37113466821 | checks | push | `step1/windows-go-node` | b73695cfad | success | 2026-10-03T09:33:47Z | 28 |
| <a id="run-37113568757"></a>37113568757 | checks | pull_request | `step1/windows-go-node` | b73695cfad | success | 2026-10-03T09:35:32Z | 42 |
| <a id="run-37113924956"></a>37113924956 | checks | push | `main` | 50fed5deda | success | 2026-10-03T09:41:57Z | 57 |
| <a id="run-37113924962"></a>37113924962 | build-verify | push | `main` | 50fed5deda | success | 2026-10-03T09:41:57Z | 229 |
| <a id="run-37113931787"></a>37113931787 | checks | push | `main` | ae9a720ef8 | success | 2026-10-03T09:42:03Z | 41 |
| <a id="run-37113931819"></a>37113931819 | build-verify | push | `main` | ae9a720ef8 | cancelled | 2026-10-03T09:42:03Z | 16 |
| <a id="run-37113946852"></a>37113946852 | checks | push | `main` | 52fffdb146 | success | 2026-10-03T09:42:18Z | 38 |
| <a id="run-37113946868"></a>37113946868 | build-verify | push | `main` | 52fffdb146 | success | 2026-10-03T09:42:18Z | 430 |
| <a id="run-37117769402"></a>37117769402 | checks | push | `step1/crashpad-no-dumps` | 696ee123c3 | success | 2026-10-03T10:51:24Z | 35 |
| <a id="run-37117841787"></a>37117841787 | checks | push | `step1/crashpad-no-dumps` | a4a70f89b3 | success | 2026-10-03T10:52:44Z | 43 |
| <a id="run-37118000282"></a>37118000282 | checks | push | `step1/crashpad-no-dumps` | a9d91c54ad | success | 2026-10-03T10:55:51Z | 44 |
| <a id="run-37118473536"></a>37118473536 | checks | push | `step1/crashpad-no-dumps` | 148f992ff9 | success | 2026-10-03T11:04:26Z | 41 |
| <a id="run-37122856763"></a>37122856763 | checks | push | `step3/profile-seeds` | ea3bf57a3c | success | 2026-10-03T12:26:04Z | 37 |
| <a id="run-37122884501"></a>37122884501 | checks | pull_request | `step3/profile-seeds` | ea3bf57a3c | success | 2026-10-03T12:26:33Z | 30 |
| <a id="run-37122947130"></a>37122947130 | checks | push | `step1/build-lock` | 047ae8605f | success | 2026-10-03T12:27:45Z | 36 |
| <a id="run-37123024487"></a>37123024487 | checks | pull_request | `step1/build-lock` | 047ae8605f | success | 2026-10-03T12:29:12Z | 41 |
| <a id="run-37123085856"></a>37123085856 | checks | push | `step3/release-gates` | 09619d129c | success | 2026-10-03T12:30:18Z | 40 |
| <a id="run-37123105318"></a>37123105318 | checks | pull_request | `step3/release-gates` | 09619d129c | success | 2026-10-03T12:30:35Z | 39 |
| <a id="run-37158825710"></a>37158825710 | checks | push | `step1/crashpad-no-dumps` | c9815513a3 | success | 2026-10-03T22:33:00Z | 73 |
| <a id="run-37158847298"></a>37158847298 | checks | pull_request | `step1/crashpad-no-dumps` | c9815513a3 | success | 2026-10-03T22:33:24Z | 37 |
| <a id="run-37158899197"></a>37158899197 | checks | push | `step1/build-lock` | e11925d5cb | success | 2026-10-03T22:34:19Z | 37 |
| <a id="run-37158901848"></a>37158901848 | checks | pull_request | `step1/build-lock` | e11925d5cb | success | 2026-10-03T22:34:21Z | 73 |
| <a id="run-37158971369"></a>37158971369 | checks | push | `step3/release-gates` | 7d406f0f95 | success | 2026-10-03T22:35:34Z | 38 |
| <a id="run-37158973226"></a>37158973226 | checks | pull_request | `step3/release-gates` | 7d406f0f95 | success | 2026-10-03T22:35:36Z | 41 |
| <a id="run-37170892102"></a>37170892102 | checks | push | `main` | 2c34cda501 | success | 2026-10-04T02:23:15Z | 42 |
| <a id="run-37170892145"></a>37170892145 | build-verify | push | `main` | 2c34cda501 | success | 2026-10-04T02:23:15Z | 249 |
| <a id="run-37171141650"></a>37171141650 | checks | push | `main` | 93679d9971 | success | 2026-10-04T02:28:07Z | 42 |
| <a id="run-37171141657"></a>37171141657 | build-verify | push | `main` | 93679d9971 | success | 2026-10-04T02:28:07Z | 235 |
| <a id="run-37171370225"></a>37171370225 | build-verify | push | `main` | c20d714da5 | success | 2026-10-04T02:32:31Z | 235 |
| <a id="run-37171370304"></a>37171370304 | checks | push | `main` | c20d714da5 | success | 2026-10-04T02:32:31Z | 41 |
| <a id="run-37171597050"></a>37171597050 | checks | push | `main` | 3c9f44da4f | success | 2026-10-04T02:36:52Z | 30 |
| <a id="run-37171597061"></a>37171597061 | build-verify | push | `main` | 3c9f44da4f | success | 2026-10-04T02:36:52Z | 234 |
| <a id="run-37172842714"></a>37172842714 | checks | push | `step3/acceptable-use-review` | e10124023f | success | 2026-10-04T03:01:41Z | 39 |
| <a id="run-37172851960"></a>37172851960 | checks | pull_request | `step3/acceptable-use-review` | e10124023f | success | 2026-10-04T03:01:53Z | 45 |
| <a id="run-37172924151"></a>37172924151 | checks | push | `step3/acceptable-use-review` | af7d4c8ba8 | success | 2026-10-04T03:03:14Z | 29 |
| <a id="run-37172927102"></a>37172927102 | checks | pull_request | `step3/acceptable-use-review` | af7d4c8ba8 | success | 2026-10-04T03:03:18Z | 44 |
| <a id="run-37173763998"></a>37173763998 | checks | push | `step3/acceptable-use-review` | 5c2e3b0b2a | success | 2026-10-04T03:19:55Z | 38 |
| <a id="run-37173765787"></a>37173765787 | checks | pull_request | `step3/acceptable-use-review` | 5c2e3b0b2a | success | 2026-10-04T03:19:58Z | 46 |
| <a id="run-37173933634"></a>37173933634 | checks | push | `main` | ff2c4d3f6e | success | 2026-10-04T03:23:18Z | 44 |
| <a id="run-37175689588"></a>37175689588 | checks | push | `step1/windows-verify-set` | ff6e3417da | success | 2026-10-04T04:00:07Z | 36 |
| <a id="run-37176336788"></a>37176336788 | checks | push | `step1/windows-verify-set` | 3c5726bf23 | success | 2026-10-04T04:12:37Z | 38 |
| <a id="run-37176700491"></a>37176700491 | checks | push | `step1/windows-verify-set` | 0829edefb3 | success | 2026-10-04T04:20:02Z | 44 |
| <a id="run-37176796022"></a>37176796022 | checks | push | `step1/windows-verify-set` | 7862827f16 | success | 2026-10-04T04:22:00Z | 40 |
| <a id="run-37177317018"></a>37177317018 | checks | push | `step1/windows-verify-set` | 97ea16840b | success | 2026-10-04T04:32:47Z | 41 |
| <a id="run-37177471896"></a>37177471896 | checks | push | `step1/windows-verify-set` | 1e938ef42e | success | 2026-10-04T04:35:54Z | 41 |
| <a id="run-37177509381"></a>37177509381 | checks | push | `step1/windows-verify-set` | 4a5c0d46ab | success | 2026-10-04T04:36:43Z | 37 |
| <a id="run-37178068526"></a>37178068526 | checks | push | `step1/windows-verify-set` | 768982fa84 | success | 2026-10-04T04:48:40Z | 29 |
| <a id="run-37178765430"></a>37178765430 | checks | push | `step1/windows-verify-set` | 4674631539 | success | 2026-10-04T05:03:08Z | 47 |
| <a id="run-37178789857"></a>37178789857 | checks | pull_request | `step1/windows-verify-set` | 4674631539 | success | 2026-10-04T05:03:38Z | 76 |
| <a id="run-37187855137"></a>37187855137 | checks | push | `step1/windows-verify-set` | 2008ed9f98 | success | 2026-10-04T08:06:33Z | 36 |
| <a id="run-37187856976"></a>37187856976 | checks | pull_request | `step1/windows-verify-set` | 2008ed9f98 | success | 2026-10-04T08:06:35Z | 31 |
| <a id="run-37188058866"></a>37188058866 | checks | push | `main` | a9d6c93688 | success | 2026-10-04T08:10:24Z | 33 |
| <a id="run-37188058874"></a>37188058874 | build-verify | push | `main` | a9d6c93688 | success | 2026-10-04T08:10:24Z | 247 |
| <a id="run-37188475120"></a>37188475120 | checks | push | `docs/readme-step1` | 0b0152c661 | success | 2026-10-04T08:18:11Z | 46 |
| <a id="run-37188487913"></a>37188487913 | checks | pull_request | `docs/readme-step1` | 0b0152c661 | success | 2026-10-04T08:18:26Z | 39 |
| <a id="run-37190813309"></a>37190813309 | checks | push | `main` | a4d730b58e | success | 2026-10-04T09:01:35Z | 40 |
| <a id="run-37193849214"></a>37193849214 | checks | push | `backlog4/safe-browsing` | 5aa29c61c9 | success | 2026-10-04T09:58:25Z | 35 |
| <a id="run-37194015111"></a>37194015111 | checks | push | `backlog4/safe-browsing` | (not in the rewritten history) | success | 2026-10-04T10:01:21Z | 37 |
| <a id="run-37194029312"></a>37194029312 | checks | push | `backlog4/safe-browsing` | 0e05c3fae1 | success | 2026-10-04T10:01:39Z | 32 |
| <a id="run-37194181073"></a>37194181073 | checks | push | `backlog4/safe-browsing` | 757e786e9b | success | 2026-10-04T10:04:29Z | 30 |
| <a id="run-37197186576"></a>37197186576 | checks | push | `backlog4/safe-browsing` | e3f900d9cc | success | 2026-10-04T10:59:37Z | 34 |
| <a id="run-37199311677"></a>37199311677 | checks | push | `backlog4/safe-browsing` | 8888be5465 | success | 2026-10-04T11:36:23Z | 36 |
| <a id="run-37199527016"></a>37199527016 | checks | push | `backlog4/safe-browsing` | 324acbe5e9 | success | 2026-10-04T11:40:22Z | 45 |
| <a id="run-37199633065"></a>37199633065 | checks | push | `backlog4/safe-browsing` | 555543e275 | success | 2026-10-04T11:42:16Z | 36 |
| <a id="run-37200327989"></a>37200327989 | checks | push | `backlog4/safe-browsing` | 3f89b4b5dc | success | 2026-10-04T11:54:58Z | 43 |
| <a id="run-37200890640"></a>37200890640 | checks | push | `backlog4/safe-browsing` | 3bc33b9628 | success | 2026-10-04T12:05:00Z | 45 |
| <a id="run-37200895303"></a>37200895303 | checks | pull_request | `backlog4/safe-browsing` | 3bc33b9628 | success | 2026-10-04T12:05:04Z | 31 |
| <a id="run-37204298677"></a>37204298677 | checks | push | `main` | e37221f33b | success | 2026-10-04T13:04:03Z | 43 |
| <a id="run-37204298713"></a>37204298713 | build-verify | push | `main` | e37221f33b | success | 2026-10-04T13:04:03Z | 250 |
| <a id="run-37206075721"></a>37206075721 | checks | push | `docs/box-branches` | 3ace9a7bd1 | success | 2026-10-04T13:34:01Z | 41 |
| <a id="run-37206079943"></a>37206079943 | checks | pull_request | `docs/box-branches` | 3ace9a7bd1 | success | 2026-10-04T13:34:05Z | 43 |
| <a id="run-37206306275"></a>37206306275 | checks | push | `main` | 6a51b95c91 | success | 2026-10-04T13:37:58Z | 37 |
| <a id="run-37211690546"></a>37211690546 | checks | push | `step2/measurement` | 4afc8e973e | success | 2026-10-04T15:05:16Z | 44 |
| <a id="run-37211900065"></a>37211900065 | checks | push | `step2/measurement` | 35ca499650 | success | 2026-10-04T15:08:40Z | 40 |
| <a id="run-37212020998"></a>37212020998 | checks | push | `step2/measurement` | 876f3c0f1c | success | 2026-10-04T15:10:38Z | 42 |
| <a id="run-37212086757"></a>37212086757 | checks | push | `step2/measurement` | f68a4a7899 | success | 2026-10-04T15:11:43Z | 41 |
| <a id="run-37213220412"></a>37213220412 | checks | push | `step2/measurement` | (not in the rewritten history) | success | 2026-10-04T15:29:54Z | 42 |
| <a id="run-37213324469"></a>37213324469 | checks | push | `step2/measurement` | (not in the rewritten history) | success | 2026-10-04T15:31:28Z | 31 |
| <a id="run-37213434014"></a>37213434014 | checks | push | `step2/measurement` | (not in the rewritten history) | success | 2026-10-04T15:33:14Z | 74 |
| <a id="run-37214643078"></a>37214643078 | checks | push | `step2/measurement` | (not in the rewritten history) | success | 2026-10-04T15:52:28Z | 41 |
| <a id="run-37215657873"></a>37215657873 | checks | push | `step2/measurement` | (not in the rewritten history) | success | 2026-10-04T16:08:22Z | 50 |
| <a id="run-37215842819"></a>37215842819 | checks | push | `step2/measurement` | (not in the rewritten history) | success | 2026-10-04T16:11:23Z | 43 |
| <a id="run-37217118495"></a>37217118495 | checks | push | `step2/measurement` | (not in the rewritten history) | success | 2026-10-04T16:32:03Z | 41 |
| <a id="run-37217179352"></a>37217179352 | checks | push | `step2/measurement` | 3ebe541330 | success | 2026-10-04T16:33:05Z | 34 |
| <a id="run-37217208274"></a>37217208274 | checks | pull_request | `step2/measurement` | 3ebe541330 | success | 2026-10-04T16:33:32Z | 43 |
| <a id="run-37241935027"></a>37241935027 | checks | push | `main` | d655afb0f5 | success | 2026-10-04T22:56:58Z | 37 |
| <a id="run-37241935029"></a>37241935029 | build-verify | push | `main` | d655afb0f5 | success | 2026-10-04T22:56:58Z | 244 |
| <a id="run-37310665536"></a>37310665536 | checks | push | `s1/canvas-noise` | a19fec5f24 | success | 2026-10-05T12:36:06Z | 43 |
| <a id="run-37310889730"></a>37310889730 | checks | push | `s1/canvas-noise` | 2722a9ab52 | success | 2026-10-05T12:38:02Z | 43 |
| <a id="run-37311607729"></a>37311607729 | checks | push | `s1/canvas-noise` | 188e614e4b | success | 2026-10-05T12:44:16Z | 45 |
| <a id="run-37311867796"></a>37311867796 | checks | push | `s1/canvas-noise` | 6206d1deb1 | success | 2026-10-05T12:46:28Z | 40 |
| <a id="run-37312014969"></a>37312014969 | checks | push | `s1/canvas-noise` | 39ae8319d9 | success | 2026-10-05T12:47:44Z | 49 |
| <a id="run-37312202173"></a>37312202173 | checks | push | `s1/canvas-noise` | (not in the rewritten history) | success | 2026-10-05T12:49:22Z | 40 |
| <a id="run-37312240131"></a>37312240131 | checks | push | `s1/canvas-noise` | 1254777fe2 | success | 2026-10-05T12:49:41Z | 38 |
| <a id="run-37312528339"></a>37312528339 | checks | push | `s1/canvas-noise` | 17aa263796 | success | 2026-10-05T12:52:10Z | 45 |
| <a id="run-37312972102"></a>37312972102 | checks | push | `s1/canvas-noise` | c302ed27d1 | success | 2026-10-05T12:55:55Z | 37 |
| <a id="run-37313271262"></a>37313271262 | checks | push | `s1/canvas-noise` | 05f1643d9b | success | 2026-10-05T12:58:24Z | 44 |
| <a id="run-37313838002"></a>37313838002 | checks | push | `s1/canvas-noise` | c549f2d727 | success | 2026-10-05T13:02:58Z | 38 |
| <a id="run-37317654143"></a>37317654143 | checks | push | `s1/canvas-noise` | 7d0dd2a7e6 | success | 2026-10-05T13:32:57Z | 38 |
| <a id="run-37317748165"></a>37317748165 | checks | push | `s1/canvas-noise` | d337a33437 | success | 2026-10-05T13:33:39Z | 45 |
| <a id="run-37318945560"></a>37318945560 | checks | push | `s1/canvas-noise` | e03df9e04c | success | 2026-10-05T13:42:57Z | 46 |
| <a id="run-37320302322"></a>37320302322 | checks | push | `s1/canvas-noise` | 100a841e8f | success | 2026-10-05T13:53:27Z | 43 |
| <a id="run-37320562883"></a>37320562883 | checks | push | `s1/canvas-noise` | 03bd1a8459 | success | 2026-10-05T13:55:24Z | 34 |
| <a id="run-37322180724"></a>37322180724 | checks | push | `s1/canvas-noise` | 981bcc0695 | success | 2026-10-05T14:07:35Z | 47 |
| <a id="run-37325547989"></a>37325547989 | checks | push | `s1/canvas-noise` | 75602593c0 | success | 2026-10-05T14:32:38Z | 44 |
| <a id="run-37327218306"></a>37327218306 | checks | push | `s1/canvas-noise` | 5d81f67016 | success | 2026-10-05T14:45:00Z | 44 |
| <a id="run-37327576343"></a>37327576343 | checks | push | `s1/canvas-noise` | 9320a51fe9 | success | 2026-10-05T14:47:33Z | 44 |
| <a id="run-37328831611"></a>37328831611 | checks | push | `s1/canvas-noise` | e1b7137bee | success | 2026-10-05T14:56:47Z | 47 |
| <a id="run-37331093490"></a>37331093490 | checks | push | `s1/canvas-noise` | 35baf1f9be | success | 2026-10-05T15:13:41Z | 51 |
| <a id="run-37331840491"></a>37331840491 | checks | push | `s1/canvas-noise` | 4423e9e368 | success | 2026-10-05T15:19:08Z | 56 |
| <a id="run-37332177242"></a>37332177242 | checks | push | `s1/canvas-noise` | c83c15ebf4 | success | 2026-10-05T15:21:34Z | 51 |
| <a id="run-37332304199"></a>37332304199 | checks | push | `s1/canvas-noise` | f1045f4f1f | success | 2026-10-05T15:22:30Z | 45 |
| <a id="run-37338602135"></a>37338602135 | checks | pull_request | `s1/canvas-noise` | f1045f4f1f | success | 2026-10-05T16:09:20Z | 46 |
| <a id="run-37343235699"></a>37343235699 | checks | push | `s1/canvas-noise` | 856500c2bc | success | 2026-10-05T16:45:14Z | 46 |
| <a id="run-37343243075"></a>37343243075 | checks | pull_request | `s1/canvas-noise` | 856500c2bc | success | 2026-10-05T16:45:18Z | 44 |
| <a id="run-37343254304"></a>37343254304 | checks | push | `s1/canvas-noise` | 6dd1e604e6 | success | 2026-10-05T16:45:23Z | 41 |
| <a id="run-37343262304"></a>37343262304 | checks | pull_request | `s1/canvas-noise` | 6dd1e604e6 | success | 2026-10-05T16:45:27Z | 46 |
| <a id="run-37346878258"></a>37346878258 | checks | push | `s1/canvas-noise` | 10acd2e8de | success | 2026-10-05T17:14:02Z | 47 |
| <a id="run-37346886972"></a>37346886972 | checks | pull_request | `s1/canvas-noise` | 10acd2e8de | success | 2026-10-05T17:14:06Z | 44 |
| <a id="run-37347722073"></a>37347722073 | checks | push | `s1/canvas-noise` | fc9ca2a284 | success | 2026-10-05T17:20:45Z | 48 |
| <a id="run-37347728011"></a>37347728011 | checks | pull_request | `s1/canvas-noise` | fc9ca2a284 | success | 2026-10-05T17:20:48Z | 44 |
| <a id="run-37347763088"></a>37347763088 | checks | push | `s1/canvas-noise` | 710c07df7e | success | 2026-10-05T17:21:05Z | 39 |
| <a id="run-37347772173"></a>37347772173 | checks | pull_request | `s1/canvas-noise` | 710c07df7e | success | 2026-10-05T17:21:09Z | 47 |
| <a id="run-37349245217"></a>37349245217 | checks | push | `s1/canvas-noise` | 7381874126 | success | 2026-10-05T17:32:56Z | 44 |
| <a id="run-37349252899"></a>37349252899 | checks | pull_request | `s1/canvas-noise` | 7381874126 | success | 2026-10-05T17:33:00Z | 40 |
| <a id="run-37350054892"></a>37350054892 | checks | push | `s1/canvas-noise` | ed1a5eeb3e | success | 2026-10-05T17:39:26Z | 42 |
| <a id="run-37350062405"></a>37350062405 | checks | pull_request | `s1/canvas-noise` | ed1a5eeb3e | success | 2026-10-05T17:39:30Z | 40 |
| <a id="run-37351871642"></a>37351871642 | checks | push | `s1/canvas-noise` | fe12a7b81c | success | 2026-10-05T17:53:57Z | 45 |
| <a id="run-37351879138"></a>37351879138 | checks | pull_request | `s1/canvas-noise` | fe12a7b81c | success | 2026-10-05T17:54:00Z | 31 |
| <a id="run-37352754803"></a>37352754803 | checks | push | `s1/canvas-noise` | 4c35c878bc | success | 2026-10-05T18:00:54Z | 44 |
| <a id="run-37352762065"></a>37352762065 | checks | pull_request | `s1/canvas-noise` | 4c35c878bc | success | 2026-10-05T18:00:57Z | 36 |
| <a id="run-37353580034"></a>37353580034 | checks | push | `s1/canvas-noise` | a56f848d59 | success | 2026-10-05T18:07:31Z | 39 |
| <a id="run-37353586344"></a>37353586344 | checks | pull_request | `s1/canvas-noise` | a56f848d59 | success | 2026-10-05T18:07:34Z | 45 |
| <a id="run-37354109049"></a>37354109049 | checks | push | `s1/canvas-noise` | 64c2fcf847 | success | 2026-10-05T18:11:45Z | 47 |
| <a id="run-37354117521"></a>37354117521 | checks | pull_request | `s1/canvas-noise` | 64c2fcf847 | success | 2026-10-05T18:11:49Z | 44 |
| <a id="run-37356026212"></a>37356026212 | checks | push | `s1/canvas-noise` | 41e481a25d | success | 2026-10-05T18:27:00Z | 76 |
| <a id="run-37356268326"></a>37356268326 | checks | pull_request | `s1/canvas-noise` | 41e481a25d | success | 2026-10-05T18:28:57Z | 45 |
| <a id="run-37356593930"></a>37356593930 | checks | push | `s1/canvas-noise` | 421a4b65b2 | success | 2026-10-05T18:31:31Z | 45 |
| <a id="run-37356603668"></a>37356603668 | checks | pull_request | `s1/canvas-noise` | 421a4b65b2 | success | 2026-10-05T18:31:36Z | 53 |
| <a id="run-37387630747"></a>37387630747 | checks | push | `main` | 9abceabff3 | success | 2026-10-05T23:17:26Z | 38 |
| <a id="run-37387630949"></a>37387630949 | build-verify | push | `main` | 9abceabff3 | success | 2026-10-05T23:17:26Z | 431 |
| <a id="run-37401132923"></a>37401132923 | checks | push | `s2b/canvas-noise` | aa4645f8bc | success | 2026-10-06T01:49:50Z | 53 |
| <a id="run-37402519340"></a>37402519340 | checks | push | `s2b/canvas-noise` | c4e671f1e3 | success | 2026-10-06T02:06:28Z | 38 |
| <a id="run-37402949403"></a>37402949403 | checks | push | `s2b/canvas-noise` | 562fc2c18f | success | 2026-10-06T02:11:50Z | 40 |
| <a id="run-37403241076"></a>37403241076 | checks | push | `s2b/canvas-noise` | c1926fef7f | success | 2026-10-06T02:15:25Z | 39 |
| <a id="run-37403378688"></a>37403378688 | checks | push | `s2b/canvas-noise` | f39741bb82 | success | 2026-10-06T02:17:09Z | 42 |
| <a id="run-37403588530"></a>37403588530 | checks | push | `s2b/canvas-noise` | 27f7996370 | success | 2026-10-06T02:19:46Z | 36 |
| <a id="run-37403752435"></a>37403752435 | checks | push | `s2b/canvas-noise` | f171567428 | success | 2026-10-06T02:21:48Z | 47 |
| <a id="run-37404335114"></a>37404335114 | checks | push | `s2b/canvas-noise` | 78045c7a43 | success | 2026-10-06T02:28:56Z | 43 |
| <a id="run-37404353390"></a>37404353390 | checks | push | `s2b/canvas-noise` | aecfcfd6d6 | success | 2026-10-06T02:29:10Z | 50 |
| <a id="run-37404458792"></a>37404458792 | checks | push | `s2b/canvas-noise` | 7eb153f37f | success | 2026-10-06T02:30:26Z | 43 |
| <a id="run-37404600364"></a>37404600364 | checks | push | `s2b/canvas-noise` | a2e650cb89 | success | 2026-10-06T02:32:08Z | 39 |
| <a id="run-37404683290"></a>37404683290 | checks | push | `s2b/canvas-noise` | 5a1d2796f5 | success | 2026-10-06T02:33:09Z | 45 |
| <a id="run-37404910645"></a>37404910645 | checks | push | `s2b/canvas-noise` | dd8ae18cf4 | success | 2026-10-06T02:35:59Z | 52 |
| <a id="run-37405177267"></a>37405177267 | checks | push | `s2b/canvas-noise` | 73447a0f35 | success | 2026-10-06T02:39:17Z | 42 |
| <a id="run-37406775214"></a>37406775214 | checks | push | `s2b/canvas-noise` | (not in the rewritten history) | success | 2026-10-06T02:58:54Z | 40 |
| <a id="run-37406792881"></a>37406792881 | checks | push | `s2b/canvas-noise` | 0228b6e321 | success | 2026-10-06T02:59:07Z | 36 |
| <a id="run-37406819796"></a>37406819796 | checks | push | `s2b/canvas-noise` | fa9bdf723a | success | 2026-10-06T02:59:26Z | 43 |
| <a id="run-37407474935"></a>37407474935 | checks | push | `worktree-tracking-observer` | 2fc358e905 | success | 2026-10-06T03:07:16Z | 42 |
| <a id="run-37407595502"></a>37407595502 | checks | push | `tmp/observe-src` | (not in the rewritten history) | success | 2026-10-06T03:08:50Z | 39 |
| <a id="run-37407942741"></a>37407942741 | checks | push | `s2b/canvas-noise` | a47a5d0480 | success | 2026-10-06T03:13:14Z | 43 |
| <a id="run-37408936625"></a>37408936625 | checks | push | `s2b/canvas-noise` | d573746a04 | success | 2026-10-06T03:25:52Z | 41 |
| <a id="run-37408959242"></a>37408959242 | checks | push | `s2b/canvas-noise` | 9d6c137489 | success | 2026-10-06T03:26:09Z | 45 |
| <a id="run-37410252225"></a>37410252225 | checks | push | `s2b/canvas-noise` | (not in the rewritten history) | success | 2026-10-06T03:42:34Z | 46 |
| <a id="run-37410274772"></a>37410274772 | checks | push | `s2b/canvas-noise` | (not in the rewritten history) | success | 2026-10-06T03:42:52Z | 42 |
| <a id="run-37411486086"></a>37411486086 | checks | push | `s2b/canvas-noise` | 00f7b8f419 | success | 2026-10-06T03:58:22Z | 40 |
| <a id="run-37426261318"></a>37426261318 | checks | push | `s2b/canvas-noise` | c801e2a105 | success | 2026-10-06T06:52:49Z | 43 |
| <a id="run-37426279036"></a>37426279036 | checks | push | `s2b/canvas-noise` | 51144beb23 | success | 2026-10-06T06:53:00Z | 38 |
| <a id="run-37426345968"></a>37426345968 | checks | push | `worktree-tracking-observer` | 9e2753e7ed | success | 2026-10-06T06:53:40Z | 42 |
| <a id="run-37426515058"></a>37426515058 | checks | push | `s2b/canvas-noise` | 60bd008d3f | success | 2026-10-06T06:55:22Z | 41 |
| <a id="run-37426663376"></a>37426663376 | checks | push | `s2b/canvas-noise` | 92876079c0 | success | 2026-10-06T06:56:53Z | 39 |
| <a id="run-37428645563"></a>37428645563 | checks | push | `s2b/canvas-noise` | d059a7cb78 | success | 2026-10-06T07:16:30Z | 45 |
| <a id="run-37466546570"></a>37466546570 | checks | push | `s2b/canvas-noise` | f0019aa011 | success | 2026-10-06T12:53:12Z | 46 |
| <a id="run-37466768885"></a>37466768885 | checks | push | `worktree-tracking-observer` | 9e00231cc6 | success | 2026-10-06T12:54:59Z | 44 |
| <a id="run-37467537433"></a>37467537433 | checks | push | `worktree-tracking-observer` | 0ca0f0cca7 | success | 2026-10-06T13:01:11Z | 41 |
| <a id="run-37468046593"></a>37468046593 | checks | push | `s2b/canvas-noise` | 9f2de638d3 | success | 2026-10-06T13:05:06Z | 48 |
| <a id="run-37472055812"></a>37472055812 | checks | push | `s2b/canvas-noise` | fc7c05da12 | success | 2026-10-06T13:35:49Z | 37 |
| <a id="run-37473401415"></a>37473401415 | checks | push | `worktree-tracking-observer` | ddd416416b | success | 2026-10-06T13:45:58Z | 48 |
| <a id="run-37474406756"></a>37474406756 | checks | push | `worktree-tracking-observer` | b4bc0a687a | success | 2026-10-06T13:53:30Z | 47 |
| <a id="run-37476036201"></a>37476036201 | checks | push | `worktree-tracking-observer` | 3b72065331 | success | 2026-10-06T14:05:19Z | 42 |
| <a id="run-37479847933"></a>37479847933 | checks | push | `s2b/canvas-noise` | 6b7ddbecb4 | success | 2026-10-06T14:32:40Z | 47 |
| <a id="run-37481648162"></a>37481648162 | checks | push | `s2b/canvas-noise` | 29a98db59b | success | 2026-10-06T14:45:31Z | 47 |
| <a id="run-37484914183"></a>37484914183 | checks | pull_request | `s2b/canvas-noise` | 29a98db59b | success | 2026-10-06T15:08:48Z | 53 |
| <a id="run-37527893784"></a>37527893784 | checks | push | `s2b/canvas-noise` | 2dd8a123e6 | success | 2026-10-06T20:37:46Z | 41 |
| <a id="run-37527901486"></a>37527901486 | checks | pull_request | `s2b/canvas-noise` | 2dd8a123e6 | success | 2026-10-06T20:37:50Z | 43 |
| <a id="run-37552674365"></a>37552674365 | checks | push | `worktree-tracking-observer` | 3dd3681189 | success | 2026-10-07T00:34:25Z | 32 |
| <a id="run-37553809963"></a>37553809963 | checks | push | `worktree-tracking-observer` | fb5aa450d2 | success | 2026-10-07T00:47:35Z | 42 |
| <a id="run-37554098816"></a>37554098816 | checks | push | `worktree-tracking-observer` | bc81ac3b9d | success | 2026-10-07T00:50:58Z | 42 |
| <a id="run-37554178921"></a>37554178921 | checks | push | `worktree-tracking-observer` | 41714f1434 | success | 2026-10-07T00:51:56Z | 44 |
| <a id="run-37554634231"></a>37554634231 | checks | push | `worktree-tracking-observer` | c31b170fc4 | success | 2026-10-07T00:57:19Z | 54 |
| <a id="run-37555472648"></a>37555472648 | checks | push | `worktree-tracking-observer` | c21feee5c7 | success | 2026-10-07T01:06:57Z | 40 |
| <a id="run-37555852175"></a>37555852175 | checks | push | `worktree-tracking-observer` | dc53b31390 | success | 2026-10-07T01:11:31Z | 42 |
| <a id="run-37556374131"></a>37556374131 | checks | push | `s2b/canvas-noise` | c42e2405c2 | success | 2026-10-07T01:17:46Z | 46 |
| <a id="run-37556378201"></a>37556378201 | checks | pull_request | `s2b/canvas-noise` | c42e2405c2 | success | 2026-10-07T01:17:50Z | 40 |
| <a id="run-37558962993"></a>37558962993 | checks | push | `s2b/canvas-noise` | 276b39e541 | success | 2026-10-07T01:49:07Z | 37 |
| <a id="run-37558966705"></a>37558966705 | checks | pull_request | `s2b/canvas-noise` | 276b39e541 | success | 2026-10-07T01:49:09Z | 39 |
| <a id="run-37561197102"></a>37561197102 | checks | push | `s2b/canvas-noise` | 980932a858 | success | 2026-10-07T02:16:29Z | 49 |
| <a id="run-37561202173"></a>37561202173 | checks | pull_request | `s2b/canvas-noise` | 980932a858 | success | 2026-10-07T02:16:33Z | 41 |
| <a id="run-37561777070"></a>37561777070 | checks | push | `s2b/canvas-noise` | ec2ec3c71e | success | 2026-10-07T02:23:47Z | 39 |
| <a id="run-37561781283"></a>37561781283 | checks | pull_request | `s2b/canvas-noise` | ec2ec3c71e | success | 2026-10-07T02:23:51Z | 43 |
| <a id="run-37561935461"></a>37561935461 | checks | push | `worktree-tracking-observer` | e255873e30 | success | 2026-10-07T02:25:48Z | 44 |
| <a id="run-37562484559"></a>37562484559 | build-verify | push | `main` | 01b7376e9a | success | 2026-10-07T02:32:39Z | 726 |
| <a id="run-37562484572"></a>37562484572 | checks | push | `main` | 01b7376e9a | success | 2026-10-07T02:32:39Z | 42 |
| <a id="run-37563795181"></a>37563795181 | checks | push | `worktree-tracking-observer` | c25904bbe7 | success | 2026-10-07T02:49:09Z | 42 |
| <a id="run-37564214023"></a>37564214023 | checks | push | `worktree-tracking-observer` | 870d3353c4 | success | 2026-10-07T02:54:20Z | 56 |
| <a id="run-37564446084"></a>37564446084 | checks | push | `worktree-tracking-observer` | 2d530918dc | success | 2026-10-07T02:57:15Z | 41 |
| <a id="run-37564599008"></a>37564599008 | checks | push | `worktree-tracking-observer` | d5b739bace | success | 2026-10-07T02:59:14Z | 30 |
| <a id="run-37573396179"></a>37573396179 | checks | push | `s2c/canvas-cost` | f858347ff0 | success | 2026-10-07T04:50:37Z | 47 |
| <a id="run-37575008393"></a>37575008393 | checks | push | `s2c/canvas-cost` | 992d4c899a | success | 2026-10-07T05:10:23Z | 43 |
| <a id="run-37575295318"></a>37575295318 | checks | push | `s2c/canvas-cost` | cedbac31fd | success | 2026-10-07T05:14:00Z | 45 |
| <a id="run-37582767133"></a>37582767133 | checks | pull_request | `worktree-tracking-observer` | d5b739bace | success | 2026-10-07T06:39:59Z | 80 |
| <a id="run-37586203361"></a>37586203361 | checks | push | `main` | ba1050c368 | success | 2026-10-07T07:15:19Z | 31 |
| <a id="run-37586203388"></a>37586203388 | build-verify | push | `main` | ba1050c368 | success | 2026-10-07T07:15:19Z | 241 |
| <a id="run-37587051856"></a>37587051856 | checks | push | `s2c/canvas-cost` | f47858c1d9 | success | 2026-10-07T07:23:44Z | 42 |
| <a id="run-37715445209"></a>37715445209 | checks | push | `s2c/canvas-cost` | c95074b00c | success | 2026-10-08T01:57:04Z | 39 |
| <a id="run-37715626012"></a>37715626012 | checks | push | `s2c/canvas-cost` | faf10c18ad | success | 2026-10-08T01:59:20Z | 42 |
| <a id="run-37715853177"></a>37715853177 | checks | push | `s2c/canvas-cost` | d972d68fdb | success | 2026-10-08T02:01:57Z | 45 |
| <a id="run-37716622508"></a>37716622508 | checks | push | `s2c/canvas-cost` | a2076d5d77 | success | 2026-10-08T02:11:09Z | 42 |
| <a id="run-37716806158"></a>37716806158 | checks | push | `s2c/canvas-cost` | 0458ae32e7 | success | 2026-10-08T02:13:27Z | 31 |
| <a id="run-37724274830"></a>37724274830 | build-verify | workflow_dispatch | `main` | ba1050c368 | success | 2026-10-08T03:46:00Z | 275 |
| <a id="run-37724682539"></a>37724682539 | checks | push | `s2c/canvas-cost` | 015bfe73e0 | success | 2026-10-08T03:51:13Z | 42 |
| <a id="run-37725504919"></a>37725504919 | checks | push | `s2c/canvas-cost` | 32e70692cb | success | 2026-10-08T04:01:40Z | 36 |
| <a id="run-37725624049"></a>37725624049 | checks | push | `s2c/canvas-cost` | 877e4125ba | success | 2026-10-08T04:03:10Z | 42 |
| <a id="run-37737608900"></a>37737608900 | checks | push | `s2c/canvas-cost` | 41f1909638 | success | 2026-10-08T06:26:25Z | 45 |
| <a id="run-37737631120"></a>37737631120 | checks | push | `s2c/canvas-cost` | a8e4355515 | success | 2026-10-08T06:26:40Z | 50 |
| <a id="run-37739188793"></a>37739188793 | checks | push | `s2c/canvas-cost` | 189505f05a | success | 2026-10-08T06:43:26Z | 34 |
| <a id="run-37739377604"></a>37739377604 | checks | push | `s2c/canvas-cost` | d0e9aec841 | success | 2026-10-08T06:45:24Z | 40 |
| <a id="run-37740568116"></a>37740568116 | checks | push | `s2c/canvas-cost` | 103e5f3374 | success | 2026-10-08T06:57:55Z | 39 |
| <a id="run-37740687211"></a>37740687211 | checks | push | `s2c/canvas-cost` | (not in the rewritten history) | success | 2026-10-08T06:59:10Z | 43 |
| <a id="run-37741243542"></a>37741243542 | checks | push | `s2c/canvas-cost` | (not in the rewritten history) | success | 2026-10-08T07:04:44Z | 42 |
| <a id="run-37741333037"></a>37741333037 | checks | push | `s2c/canvas-cost` | (not in the rewritten history) | success | 2026-10-08T07:05:37Z | 43 |
| <a id="run-37741433691"></a>37741433691 | checks | push | `s2c/canvas-cost` | (not in the rewritten history) | success | 2026-10-08T07:06:36Z | 48 |
| <a id="run-37741594342"></a>37741594342 | checks | push | `s2c/canvas-cost` | (not in the rewritten history) | success | 2026-10-08T07:08:11Z | 37 |
| <a id="run-37741810989"></a>37741810989 | checks | push | `s2c/canvas-cost` | (not in the rewritten history) | success | 2026-10-08T07:10:21Z | 40 |
| <a id="run-37741906372"></a>37741906372 | checks | push | `s2c/canvas-cost` | (not in the rewritten history) | success | 2026-10-08T07:11:18Z | 41 |
| <a id="run-37742168222"></a>37742168222 | checks | push | `s2c/canvas-cost` | (not in the rewritten history) | success | 2026-10-08T07:13:58Z | 38 |
| <a id="run-37742438284"></a>37742438284 | checks | push | `s2c/canvas-cost` | 82b3dc5d6b | success | 2026-10-08T07:16:39Z | 42 |
| <a id="run-37742542217"></a>37742542217 | checks | push | `worktree-observer-fastcall` | dda1d81085 | success | 2026-10-08T07:17:41Z | 46 |
| <a id="run-37743875959"></a>37743875959 | checks | push | `s2c/canvas-cost` | bed1562d22 | success | 2026-10-08T07:30:40Z | 35 |
| <a id="run-37744567790"></a>37744567790 | checks | push | `worktree-observer-fastcall` | 72230bc40f | success | 2026-10-08T07:37:20Z | 40 |
| <a id="run-37746854204"></a>37746854204 | checks | push | `s2c/canvas-cost` | 60e6fd614d | success | 2026-10-08T07:59:12Z | 32 |
| <a id="run-37746921131"></a>37746921131 | checks | push | `s2c/canvas-cost` | cdeaddcde6 | success | 2026-10-08T07:59:51Z | 50 |
| <a id="run-37748954617"></a>37748954617 | checks | push | `s2c/canvas-cost` | f2bcec90aa | success | 2026-10-08T08:18:20Z | 40 |
| <a id="run-37752000063"></a>37752000063 | checks | push | `s2c/canvas-cost` | 7e3e9c0b0f | success | 2026-10-08T08:45:48Z | 73 |
| <a id="run-37752437352"></a>37752437352 | checks | push | `s2c/canvas-cost` | aff01aacb1 | success | 2026-10-08T08:49:45Z | 44 |
| <a id="run-37755443697"></a>37755443697 | checks | push | `s2c/canvas-cost` | 8a893541e7 | success | 2026-10-08T09:15:55Z | 36 |
| <a id="run-37755533915"></a>37755533915 | checks | push | `s2c/canvas-cost` | 669d571cf6 | success | 2026-10-08T09:16:41Z | 46 |
| <a id="run-37755781334"></a>37755781334 | checks | push | `s2c/canvas-cost` | 172c927ded | success | 2026-10-08T09:18:53Z | 40 |
| <a id="run-37759650938"></a>37759650938 | checks | push | `s2c/canvas-cost` | 50c0c1c6c7 | success | 2026-10-08T09:52:28Z | 43 |
| <a id="run-37777153262"></a>37777153262 | checks | push | `s2c/canvas-cost` | bccd7b708e | success | 2026-10-08T12:28:53Z | 45 |
| <a id="run-37779620338"></a>37779620338 | checks | push | `s2c/canvas-cost` | 19037b3ad6 | success | 2026-10-08T12:49:15Z | 43 |
| <a id="run-37779682339"></a>37779682339 | checks | push | `s2c/canvas-cost` | eb69880546 | success | 2026-10-08T12:49:46Z | 42 |
| <a id="run-37780767851"></a>37780767851 | checks | push | `worktree-observer-fastcall` | 1a102a1cfb | success | 2026-10-08T12:58:35Z | 42 |
| <a id="run-37781790739"></a>37781790739 | checks | push | `worktree-observer-fastcall` | 801c9bd49d | failure | 2026-10-08T13:06:32Z | 32 |
| <a id="run-37781851775"></a>37781851775 | checks | push | `worktree-observer-fastcall` | 5124f65bfb | success | 2026-10-08T13:07:02Z | 41 |
| <a id="run-37782031371"></a>37782031371 | checks | pull_request | `worktree-observer-fastcall` | 5124f65bfb | success | 2026-10-08T13:08:27Z | 43 |
| <a id="run-37782889998"></a>37782889998 | checks | push | `worktree-observer-fastcall` | e8beffbb8a | success | 2026-10-08T13:15:11Z | 40 |
| <a id="run-37782897442"></a>37782897442 | checks | pull_request | `worktree-observer-fastcall` | e8beffbb8a | success | 2026-10-08T13:15:14Z | 48 |
| <a id="run-37783026768"></a>37783026768 | checks | push | `s2c/canvas-cost` | 19638e0e31 | success | 2026-10-08T13:16:12Z | 32 |
| <a id="run-37783627506"></a>37783627506 | checks | push | `s2c/canvas-cost` | f90b7eb8fd | success | 2026-10-08T13:20:50Z | 51 |
| <a id="run-37786711746"></a>37786711746 | checks | push | `s2c/canvas-cost` | c70ce6b10f | success | 2026-10-08T13:44:11Z | 35 |
| <a id="run-37787018217"></a>37787018217 | checks | push | `s2c/canvas-cost` | 0c892d854a | success | 2026-10-08T13:46:24Z | 49 |
| <a id="run-37787217064"></a>37787217064 | checks | push | `s2c/canvas-cost` | abc3ef5e04 | success | 2026-10-08T13:47:55Z | 43 |
| <a id="run-37791386768"></a>37791386768 | checks | push | `s2c/canvas-cost` | 7c900a98d2 | success | 2026-10-08T14:18:33Z | 34 |
| <a id="run-37791953019"></a>37791953019 | checks | push | `s2c/canvas-cost` | 5246b1a2e7 | success | 2026-10-08T14:22:42Z | 42 |
| <a id="run-37794062570"></a>37794062570 | checks | push | `s2c/canvas-cost` | 4c115c6ef3 | success | 2026-10-08T14:38:01Z | 50 |
| <a id="run-37795308493"></a>37795308493 | checks | push | `s2c/canvas-cost` | 2e92761ec4 | success | 2026-10-08T14:47:08Z | 44 |
| <a id="run-37798179774"></a>37798179774 | checks | push | `s2c/canvas-cost` | ef0eed9a42 | success | 2026-10-08T15:07:49Z | 39 |
| <a id="run-37862262062"></a>37862262062 | checks | push | `main` | c2755126cb | success | 2026-10-08T23:57:31Z | 36 |
| <a id="run-37862262065"></a>37862262065 | build-verify | push | `main` | c2755126cb | success | 2026-10-08T23:57:31Z | 306 |
| <a id="run-37862795635"></a>37862795635 | checks | pull_request | `s2c/canvas-cost` | ef0eed9a42 | success | 2026-10-09T00:03:40Z | 41 |
| <a id="run-37862932801"></a>37862932801 | checks | push | `s2c/canvas-cost` | 09aeb59b91 | success | 2026-10-09T00:05:13Z | 41 |
| <a id="run-37862937008"></a>37862937008 | checks | pull_request | `s2c/canvas-cost` | 09aeb59b91 | success | 2026-10-09T00:05:16Z | 40 |
| <a id="run-37871232761"></a>37871232761 | checks | push | `s2c/canvas-cost` | 666ed7796d | success | 2026-10-09T01:44:29Z | 44 |
| <a id="run-37871236932"></a>37871236932 | checks | pull_request | `s2c/canvas-cost` | 666ed7796d | success | 2026-10-09T01:44:32Z | 47 |
| <a id="run-37872343569"></a>37872343569 | checks | push | `s2c/canvas-cost` | d6021f8637 | success | 2026-10-09T01:58:40Z | 46 |
| <a id="run-37872347668"></a>37872347668 | checks | pull_request | `s2c/canvas-cost` | d6021f8637 | success | 2026-10-09T01:58:43Z | 55 |
| <a id="run-37873493413"></a>37873493413 | checks | push | `s2c/canvas-cost` | d1ee1b6680 | success | 2026-10-09T02:12:53Z | 29 |
| <a id="run-37873632313"></a>37873632313 | checks | pull_request | `s2c/canvas-cost` | d1ee1b6680 | success | 2026-10-09T02:14:39Z | 42 |
| <a id="run-37874885760"></a>37874885760 | checks | push | `s2c/canvas-cost` | d12bc6986e | success | 2026-10-09T02:30:20Z | 44 |
| <a id="run-37875005126"></a>37875005126 | checks | pull_request | `s2c/canvas-cost` | d12bc6986e | success | 2026-10-09T02:31:47Z | 43 |
| <a id="run-37875171690"></a>37875171690 | checks | push | `s2c/canvas-cost` | 1d83ee49d5 | success | 2026-10-09T02:33:53Z | 43 |
| <a id="run-37875175149"></a>37875175149 | checks | pull_request | `s2c/canvas-cost` | 1d83ee49d5 | success | 2026-10-09T02:33:56Z | 33 |
| <a id="run-37877016549"></a>37877016549 | checks | push | `s2c/canvas-cost` | ea2fc90f51 | success | 2026-10-09T02:57:24Z | 43 |
| <a id="run-37877020140"></a>37877020140 | checks | pull_request | `s2c/canvas-cost` | ea2fc90f51 | success | 2026-10-09T02:57:27Z | 34 |
| <a id="run-37877603753"></a>37877603753 | checks | push | `s2c/canvas-cost` | 98bff8c021 | success | 2026-10-09T03:04:49Z | 52 |
| <a id="run-37877608882"></a>37877608882 | checks | pull_request | `s2c/canvas-cost` | 98bff8c021 | success | 2026-10-09T03:04:53Z | 42 |
| <a id="run-37879011214"></a>37879011214 | checks | push | `s2c/canvas-cost` | 26ed0ea8fe | success | 2026-10-09T03:22:56Z | 32 |
| <a id="run-37879016245"></a>37879016245 | checks | pull_request | `s2c/canvas-cost` | 26ed0ea8fe | success | 2026-10-09T03:23:00Z | 42 |
| <a id="run-37880489511"></a>37880489511 | checks | push | `s2c/canvas-cost` | fa11a9e010 | success | 2026-10-09T03:42:21Z | 44 |
| <a id="run-37880495937"></a>37880495937 | checks | pull_request | `s2c/canvas-cost` | fa11a9e010 | success | 2026-10-09T03:42:26Z | 37 |
| <a id="run-37880643018"></a>37880643018 | checks | push | `s2c/canvas-cost` | 0adaa9023d | success | 2026-10-09T03:44:22Z | 43 |
| <a id="run-37880648077"></a>37880648077 | checks | pull_request | `s2c/canvas-cost` | 0adaa9023d | success | 2026-10-09T03:44:26Z | 79 |
| <a id="run-37881653232"></a>37881653232 | checks | push | `s2c/canvas-cost` | 6bf71e306c | success | 2026-10-09T03:57:41Z | 47 |
| <a id="run-37881656216"></a>37881656216 | checks | pull_request | `s2c/canvas-cost` | 6bf71e306c | success | 2026-10-09T03:57:44Z | 44 |
| <a id="run-37884039895"></a>37884039895 | checks | push | `s2c/canvas-cost` | 98999c6e8a | success | 2026-10-09T04:28:29Z | 49 |
| <a id="run-37884044913"></a>37884044913 | checks | pull_request | `s2c/canvas-cost` | 98999c6e8a | success | 2026-10-09T04:28:33Z | 40 |
| <a id="run-37884143201"></a>37884143201 | checks | push | `s2c/canvas-cost` | 8708749113 | success | 2026-10-09T04:29:50Z | 42 |
| <a id="run-37884146693"></a>37884146693 | checks | pull_request | `s2c/canvas-cost` | 8708749113 | success | 2026-10-09T04:29:53Z | 35 |
| <a id="run-38012412975"></a>38012412975 | build-verify | push | `main` | 42defd43de | success | 2026-10-10T01:14:41Z | 644 |
| <a id="run-38012413087"></a>38012413087 | checks | push | `main` | 42defd43de | success | 2026-10-10T01:14:41Z | 46 |
| <a id="run-38014406741"></a>38014406741 | checks | push | `s3/media-device-ids` | e6131618c3 | success | 2026-10-10T01:45:33Z | 35 |
| <a id="run-38014966073"></a>38014966073 | checks | push | `s3/media-device-ids` | 2fd5f5ca77 | success | 2026-10-10T01:54:23Z | 42 |
| <a id="run-38015041970"></a>38015041970 | checks | push | `s3/media-device-ids` | 10471927bf | success | 2026-10-10T01:55:35Z | 41 |
| <a id="run-38015316657"></a>38015316657 | checks | push | `s3/media-device-ids` | 506c32207f | success | 2026-10-10T02:00:04Z | 42 |
| <a id="run-38020879769"></a>38020879769 | checks | push | `s3/media-device-ids` | 35e075ce73 | success | 2026-10-10T03:31:47Z | 32 |
| <a id="run-38021153804"></a>38021153804 | checks | push | `s3/media-device-ids` | f740b003dc | success | 2026-10-10T03:36:22Z | 36 |
| <a id="run-38021569275"></a>38021569275 | checks | push | `s3/media-device-ids` | 8f5aa29730 | success | 2026-10-10T03:43:34Z | 44 |
| <a id="run-38021707885"></a>38021707885 | checks | push | `s3/media-device-ids` | fa2103c8d2 | success | 2026-10-10T03:45:53Z | 43 |
| <a id="run-38021811865"></a>38021811865 | checks | push | `s3/media-device-ids` | cb9122f35b | success | 2026-10-10T03:47:42Z | 28 |
| <a id="run-38022920889"></a>38022920889 | checks | push | `s3/media-device-ids` | 85409fbc1c | success | 2026-10-10T04:06:50Z | 43 |
| <a id="run-38023381813"></a>38023381813 | checks | push | `s3/media-device-ids` | 548028552b | success | 2026-10-10T04:14:48Z | 40 |
| <a id="run-38023459693"></a>38023459693 | checks | push | `s3/media-device-ids` | b9a302a298 | success | 2026-10-10T04:15:59Z | 41 |
| <a id="run-38024251079"></a>38024251079 | checks | push | `s3/media-device-ids` | 52db0263be | success | 2026-10-10T04:29:37Z | 40 |
| <a id="run-38031183308"></a>38031183308 | checks | pull_request | `s3/media-device-ids` | 52db0263be | success | 2026-10-10T06:30:36Z | 44 |
| <a id="run-38031466931"></a>38031466931 | build-verify | push | `main` | 9771c12e11 | success | 2026-10-10T06:35:28Z | 375 |
| <a id="run-38031467047"></a>38031467047 | checks | push | `main` | 9771c12e11 | success | 2026-10-10T06:35:28Z | 40 |
| <a id="run-38032522139"></a>38032522139 | checks | push | `s3b/device-id-seed` | 1724317349 | success | 2026-10-10T06:53:52Z | 40 |
| <a id="run-38033491348"></a>38033491348 | checks | push | `s3b/device-id-seed` | 3947794a5e | success | 2026-10-10T07:10:14Z | 39 |
| <a id="run-38033605832"></a>38033605832 | checks | push | `s3b/device-id-seed` | 9ee5db6c46 | success | 2026-10-10T07:12:11Z | 30 |
| <a id="run-38034084970"></a>38034084970 | checks | push | `s3b/device-id-seed` | c5b6fd1e5c | success | 2026-10-10T07:20:23Z | 44 |
| <a id="run-38034119351"></a>38034119351 | checks | push | `s3b/device-id-seed` | 3c73c3cb87 | success | 2026-10-10T07:20:56Z | 43 |
| <a id="run-38034311408"></a>38034311408 | checks | push | `s3b/device-id-seed` | 4fe1ded532 | success | 2026-10-10T07:24:21Z | 46 |
| <a id="run-38034359132"></a>38034359132 | checks | push | `s3b/device-id-seed` | 5c89b041b1 | success | 2026-10-10T07:25:12Z | 35 |
| <a id="run-38034400126"></a>38034400126 | checks | push | `s3b/device-id-seed` | aff14f6461 | success | 2026-10-10T07:25:55Z | 38 |
| <a id="run-38034546489"></a>38034546489 | checks | push | `s3b/device-id-seed` | 5648cb2e9f | success | 2026-10-10T07:28:36Z | 38 |
| <a id="run-38034667378"></a>38034667378 | checks | push | `s3b/device-id-seed` | 2832685649 | success | 2026-10-10T07:30:40Z | 35 |
| <a id="run-38034731490"></a>38034731490 | checks | push | `s3b/device-id-seed` | 6ba7ee6ff7 | success | 2026-10-10T07:31:46Z | 43 |
| <a id="run-38034802548"></a>38034802548 | checks | push | `s3b/device-id-seed` | 38b9a64eed | success | 2026-10-10T07:33:02Z | 48 |
| <a id="run-38035539077"></a>38035539077 | checks | push | `s3b/device-id-seed` | 4beeeaa48f | success | 2026-10-10T07:45:48Z | 33 |
| <a id="run-38035800751"></a>38035800751 | checks | push | `s3b/device-id-seed` | 26779e709b | success | 2026-10-10T07:50:24Z | 41 |
| <a id="run-38035970231"></a>38035970231 | checks | push | `s3b/device-id-seed` | b67a4e4aef | success | 2026-10-10T07:53:17Z | 44 |
| <a id="run-38037047364"></a>38037047364 | checks | push | `s3b/device-id-seed` | 4df0d3828f | success | 2026-10-10T08:11:58Z | 38 |
| <a id="run-38037273066"></a>38037273066 | checks | push | `s3b/device-id-seed` | 5abf797dcf | success | 2026-10-10T08:15:52Z | 36 |
| <a id="run-38037592364"></a>38037592364 | checks | push | `s3b/device-id-seed` | bc9083ef83 | success | 2026-10-10T08:21:28Z | 45 |
| <a id="run-38038543989"></a>38038543989 | checks | push | `s3b/device-id-seed` | 9c42d7b763 | success | 2026-10-10T08:37:50Z | 43 |
| <a id="run-38038622612"></a>38038622612 | checks | push | `s3b/device-id-seed` | 3d5b42a33b | success | 2026-10-10T08:39:12Z | 35 |
| <a id="run-38040024089"></a>38040024089 | checks | push | `s3b/device-id-seed` | 3dda12d3aa | success | 2026-10-10T09:03:13Z | 47 |
| <a id="run-38040180335"></a>38040180335 | checks | push | `s3b/device-id-seed` | 8bde849b41 | success | 2026-10-10T09:05:49Z | 39 |
| <a id="run-38044770955"></a>38044770955 | checks | push | `s3b/device-id-seed` | 144dc48132 | success | 2026-10-10T10:24:11Z | 42 |
| <a id="run-38045005154"></a>38045005154 | checks | pull_request | `s3b/device-id-seed` | 144dc48132 | success | 2026-10-10T10:28:16Z | 43 |
| <a id="run-38045504958"></a>38045504958 | checks | push | `s3b/device-id-seed` | 119372f35e | success | 2026-10-10T10:36:44Z | 32 |
| <a id="run-38045507886"></a>38045507886 | checks | pull_request | `s3b/device-id-seed` | 119372f35e | success | 2026-10-10T10:36:47Z | 39 |
| <a id="run-38249156899"></a>38249156899 | build-verify | push | `main` | ff71e9e1dc | success | 2026-10-12T12:27:37Z | 341 |
| <a id="run-38249156909"></a>38249156909 | checks | push | `main` | ff71e9e1dc | success | 2026-10-12T12:27:37Z | 45 |
| <a id="run-38250247377"></a>38250247377 | checks | push | `docs-observer-1b-clone-json` | 7ee338cd8c | success | 2026-10-12T12:38:04Z | 44 |
| <a id="run-38250277921"></a>38250277921 | checks | pull_request | `docs-observer-1b-clone-json` | 7ee338cd8c | success | 2026-10-12T12:38:22Z | 46 |
| <a id="run-38270834817"></a>38270834817 | checks | push | `fix/d-pointer-touch-dep` | d39034b1b3 | success | 2026-10-12T15:31:14Z | 44 |
| <a id="run-38270843716"></a>38270843716 | checks | pull_request | `fix/d-pointer-touch-dep` | d39034b1b3 | success | 2026-10-12T15:31:18Z | 48 |
| <a id="run-38271241766"></a>38271241766 | build-verify | push | `main` | 6fda3cc724 | success | 2026-10-12T15:34:34Z | 307 |
| <a id="run-38271241831"></a>38271241831 | checks | push | `main` | 6fda3cc724 | success | 2026-10-12T15:34:34Z | 43 |
| <a id="run-38272635483"></a>38272635483 | checks | push | `main` | 69dda6ba74 | success | 2026-10-12T15:46:07Z | 44 |
| <a id="run-38286559083"></a>38286559083 | checks | push | `observer-d-intl-rcs` | d2bf0cbab3 | success | 2026-10-12T17:47:30Z | 37 |
| <a id="run-38289278050"></a>38289278050 | checks | push | `observer-d-intl-rcs` | ec28937e8d | success | 2026-10-12T18:11:49Z | 41 |
| <a id="run-38291789453"></a>38291789453 | checks | push | `observer-d-intl-rcs` | 0516c2b614 | success | 2026-10-12T18:34:07Z | 41 |
| <a id="run-38292219178"></a>38292219178 | checks | pull_request | `observer-d-intl-rcs` | 0516c2b614 | success | 2026-10-12T18:37:56Z | 73 |
| <a id="run-38335107744"></a>38335107744 | checks | push | `s5/remote-voices` | ee996b0c30 | success | 2026-10-13T02:03:54Z | 31 |
| <a id="run-38335260214"></a>38335260214 | checks | push | `s5/remote-voices` | 5aa5b8b73e | success | 2026-10-13T02:05:51Z | 38 |
| <a id="run-38336683248"></a>38336683248 | checks | push | `s5/remote-voices` | 79e388e252 | success | 2026-10-13T02:23:51Z | 42 |
| <a id="run-38337589557"></a>38337589557 | checks | push | `s5/remote-voices` | ffe7f959ea | success | 2026-10-13T02:35:19Z | 32 |
| <a id="run-38338509431"></a>38338509431 | checks | push | `s5/remote-voices` | a1f905ce3b | success | 2026-10-13T02:46:40Z | 51 |
| <a id="run-38338608534"></a>38338608534 | checks | push | `s5/remote-voices` | 7b9b796333 | success | 2026-10-13T02:47:54Z | 41 |
| <a id="run-38339358490"></a>38339358490 | checks | push | `s5/remote-voices` | 17a823e064 | success | 2026-10-13T02:57:17Z | 46 |
| <a id="run-38339500427"></a>38339500427 | checks | push | `s5/remote-voices` | 116d713b19 | success | 2026-10-13T02:59:05Z | 36 |
| <a id="run-38339682736"></a>38339682736 | checks | push | `s5/remote-voices` | bdc4962829 | success | 2026-10-13T03:01:11Z | 46 |
| <a id="run-38341875420"></a>38341875420 | checks | push | `s5/remote-voices` | 87f0ca52b6 | success | 2026-10-13T03:28:32Z | 29 |
| <a id="run-38342005997"></a>38342005997 | checks | push | `s5/remote-voices` | 6c573568f7 | success | 2026-10-13T03:30:11Z | 41 |
| <a id="run-38342271681"></a>38342271681 | checks | push | `step2b-detectors` | 874cc5343d | success | 2026-10-13T03:33:27Z | 48 |
| <a id="run-38342358617"></a>38342358617 | checks | push | `s5/remote-voices` | 74f5d5c7f5 | success | 2026-10-13T03:34:34Z | 40 |
| <a id="run-38342767493"></a>38342767493 | checks | push | `s5/remote-voices` | 82a9539d85 | success | 2026-10-13T03:39:51Z | 48 |
| <a id="run-38343016636"></a>38343016636 | checks | push | `s5/remote-voices` | bdbcc7fe1b | success | 2026-10-13T03:43:00Z | 37 |
| <a id="run-38343202134"></a>38343202134 | checks | push | `s5/remote-voices` | 89b2d19322 | success | 2026-10-13T03:45:22Z | 44 |
| <a id="run-38359293706"></a>38359293706 | checks | push | `s5/remote-voices` | b253fd0d14 | success | 2026-10-13T06:53:18Z | 31 |
| <a id="run-38363689336"></a>38363689336 | checks | push | `s5/remote-voices` | 6b1f745f1c | success | 2026-10-13T07:36:07Z | 50 |
| <a id="run-38363731590"></a>38363731590 | checks | push | `s5/remote-voices` | db72d34cc4 | success | 2026-10-13T07:36:31Z | 37 |
| <a id="run-38364231201"></a>38364231201 | checks | push | `s5/remote-voices` | 9fb14abda9 | success | 2026-10-13T07:41:05Z | 40 |
| <a id="run-38364270941"></a>38364270941 | checks | push | `s5/remote-voices` | 70d2f56795 | success | 2026-10-13T07:41:27Z | 40 |
| <a id="run-38380803243"></a>38380803243 | checks | push | `s5/remote-voices` | ec6409c7d1 | success | 2026-10-13T10:04:04Z | 46 |
| <a id="run-38382048367"></a>38382048367 | checks | push | `s5/remote-voices` | 300414ec21 | success | 2026-10-13T10:14:58Z | 30 |
| <a id="run-38382552098"></a>38382552098 | checks | push | `s5/remote-voices` | 4a4c1476a9 | success | 2026-10-13T10:19:20Z | 34 |
| <a id="run-38382768767"></a>38382768767 | checks | push | `s5/remote-voices` | 1de07af97e | success | 2026-10-13T10:21:12Z | 44 |
| <a id="run-38389104324"></a>38389104324 | checks | push | `s5/remote-voices` | fca89417fa | success | 2026-10-13T11:16:41Z | 35 |
| <a id="run-38389162816"></a>38389162816 | checks | push | `s5/remote-voices` | 04c66ee550 | success | 2026-10-13T11:17:11Z | 38 |
| <a id="run-38389361589"></a>38389361589 | checks | push | `step2b-detectors` | c346f2cc33 | success | 2026-10-13T11:18:57Z | 41 |
| <a id="run-38390405863"></a>38390405863 | checks | push | `s5/remote-voices` | d292e491a0 | success | 2026-10-13T11:28:04Z | 43 |
| <a id="run-38391814510"></a>38391814510 | checks | push | `step2b-detectors` | c7bfb59f71 | success | 2026-10-13T11:40:13Z | 36 |
| <a id="run-38392347891"></a>38392347891 | checks | push | `step2b-detectors` | 82cf664f77 | success | 2026-10-13T11:44:50Z | 42 |
| <a id="run-38393084483"></a>38393084483 | checks | push | `s5/remote-voices` | 32c58adf98 | success | 2026-10-13T11:51:08Z | 47 |
| <a id="run-38394023046"></a>38394023046 | checks | push | `s5/remote-voices` | 78d15bf9e8 | success | 2026-10-13T11:59:17Z | 41 |
| <a id="run-38394089295"></a>38394089295 | checks | push | `s5/remote-voices` | d0baa9edcb | success | 2026-10-13T11:59:52Z | 46 |
| <a id="run-38394159019"></a>38394159019 | checks | pull_request | `s5/remote-voices` | d0baa9edcb | success | 2026-10-13T12:00:24Z | 40 |
| <a id="run-38413241154"></a>38413241154 | checks | push | `step2b-detectors` | 9210c53c1a | success | 2026-10-13T14:25:36Z | 43 |
| <a id="run-38423153876"></a>38423153876 | checks | push | `step2b-detectors` | 5c257abaf9 | success | 2026-10-13T15:33:57Z | 50 |
| <a id="run-38433275608"></a>38433275608 | checks | push | `step2b-detectors` | 97ddac9d0a | success | 2026-10-13T16:46:43Z | 36 |
| <a id="run-38476331588"></a>38476331588 | checks | push | `s5/remote-voices` | f8a445efd4 | success | 2026-10-13T22:13:45Z | 44 |
| <a id="run-38476342251"></a>38476342251 | checks | pull_request | `s5/remote-voices` | f8a445efd4 | success | 2026-10-13T22:13:50Z | 40 |
| <a id="run-38491515002"></a>38491515002 | checks | push | `step2b-detectors` | bb2a22989c | success | 2026-10-14T00:40:38Z | 44 |
| <a id="run-38492407025"></a>38492407025 | checks | push | `s5/remote-voices` | 932a9b73c2 | success | 2026-10-14T00:50:20Z | 40 |
| <a id="run-38492413884"></a>38492413884 | checks | pull_request | `s5/remote-voices` | 932a9b73c2 | success | 2026-10-14T00:50:24Z | 42 |
| <a id="run-38492542525"></a>38492542525 | checks | push | `step2b-detectors` | 559f37e459 | success | 2026-10-14T00:51:48Z | 40 |
| <a id="run-38492606923"></a>38492606923 | checks | push | `step2b-detectors` | d098da3468 | success | 2026-10-14T00:52:30Z | 42 |
| <a id="run-38492664484"></a>38492664484 | checks | pull_request | `step2b-detectors` | d098da3468 | success | 2026-10-14T00:53:08Z | 45 |
| <a id="run-38497855070"></a>38497855070 | checks | push | `step2b-detectors` | 23554f73f7 | success | 2026-10-14T01:50:22Z | 158 |
| <a id="run-38497859006"></a>38497859006 | checks | pull_request | `step2b-detectors` | 23554f73f7 | success | 2026-10-14T01:50:25Z | 114 |
| <a id="run-38996850203"></a>38996850203 | checks | push | `main` | 645292d50f | success | 2026-10-17T02:56:18Z | 42 |
| <a id="run-38996850205"></a>38996850205 | build-verify | push | `main` | 645292d50f | success | 2026-10-17T02:56:18Z | 315 |
| <a id="run-38996888509"></a>38996888509 | build-verify | push | `main` | 8a31d86ad7 | cancelled | 2026-10-17T02:56:54Z | 137 |
| <a id="run-38996888523"></a>38996888523 | checks | push | `main` | 8a31d86ad7 | success | 2026-10-17T02:56:54Z | 42 |
| <a id="run-38996961183"></a>38996961183 | checks | push | `step2b-detectors` | 5f5e4f9494 | success | 2026-10-17T02:58:07Z | 40 |
| <a id="run-38996964594"></a>38996964594 | checks | pull_request | `step2b-detectors` | 5f5e4f9494 | success | 2026-10-17T02:58:10Z | 42 |
| <a id="run-38997020889"></a>38997020889 | build-verify | push | `main` | ec4863378b | success | 2026-10-17T02:59:10Z | 474 |
| <a id="run-38997020936"></a>38997020936 | checks | push | `main` | ec4863378b | success | 2026-10-17T02:59:10Z | 37 |
| <a id="run-39000444239"></a>39000444239 | checks | push | `repin/8078-prep` | 7ec40d46d8 | success | 2026-10-17T03:52:33Z | 47 |
| <a id="run-39001204528"></a>39001204528 | checks | push | `e-fb-auto` | (not in the rewritten history) | success | 2026-10-17T04:04:44Z | 385 |
| <a id="run-39001959655"></a>39001959655 | checks | push | `e-fb-auto` | (not in the rewritten history) | success | 2026-10-17T04:16:43Z | 46 |
| <a id="run-39017071211"></a>39017071211 | checks | push | `worktree-sp2c-humanized-wheel` | c32bdbf9bd | success | 2026-10-17T08:21:45Z | 39 |
| <a id="run-39017342660"></a>39017342660 | checks | push | `worktree-sp2c-humanized-wheel` | d7492bdc66 | success | 2026-10-17T08:26:04Z | 52 |
| <a id="run-39017360833"></a>39017360833 | checks | push | `worktree-sp2c-humanized-wheel` | 483b01a2e5 | success | 2026-10-17T08:26:20Z | 39 |
| <a id="run-39017780909"></a>39017780909 | checks | push | `worktree-sp2c-humanized-wheel` | 865c647e5d | success | 2026-10-17T08:32:58Z | 44 |
| <a id="run-39019734468"></a>39019734468 | checks | push | `worktree-sp2c-humanized-wheel` | 639fd66775 | success | 2026-10-17T09:04:24Z | 47 |
| <a id="run-39020446362"></a>39020446362 | checks | push | `worktree-sp2c-humanized-wheel` | ac5088364c | success | 2026-10-17T09:15:40Z | 46 |
| <a id="run-39021065885"></a>39021065885 | checks | push | `worktree-sp2c-humanized-wheel` | 3cd5b439fa | success | 2026-10-17T09:25:25Z | 34 |
| <a id="run-39021224961"></a>39021224961 | checks | push | `worktree-sp2c-humanized-wheel` | cdc2f6458a | success | 2026-10-17T09:27:55Z | 53 |
| <a id="run-39021329639"></a>39021329639 | checks | push | `e-fb-auto` | (not in the rewritten history) | success | 2026-10-17T09:29:38Z | 41 |
| <a id="run-39021564924"></a>39021564924 | checks | push | `e-fb-auto` | (not in the rewritten history) | success | 2026-10-17T09:33:06Z | 44 |
| <a id="run-39023360571"></a>39023360571 | checks | push | `e-fb-auto` | (not in the rewritten history) | success | 2026-10-17T10:02:08Z | 47 |
| <a id="run-39023365881"></a>39023365881 | checks | push | `worktree-sp2c-humanized-wheel` | 306e892063 | success | 2026-10-17T10:02:13Z | 43 |
| <a id="run-39023443705"></a>39023443705 | checks | push | `e-fb-auto` | (not in the rewritten history) | success | 2026-10-17T10:03:25Z | 42 |
| <a id="run-39023495139"></a>39023495139 | checks | push | `worktree-sp2c-humanized-wheel` | fa4b7de065 | success | 2026-10-17T10:04:13Z | 39 |
| <a id="run-39023799137"></a>39023799137 | checks | push | `worktree-sp2c-humanized-wheel` | 75733aa25c | success | 2026-10-17T10:09:06Z | 43 |
| <a id="run-39028274595"></a>39028274595 | checks | pull_request | `worktree-sp2c-humanized-wheel` | 75733aa25c | success | 2026-10-17T11:19:47Z | 44 |
| <a id="run-39037393612"></a>39037393612 | checks | push | `e-fb-auto` | (not in the rewritten history) | success | 2026-10-17T13:38:29Z | 41 |
| <a id="run-39037657028"></a>39037657028 | checks | push | `e-fb-auto` | (not in the rewritten history) | success | 2026-10-17T13:42:15Z | 43 |
| <a id="run-39076261296"></a>39076261296 | checks | push | `e-fb-auto` | (not in the rewritten history) | success | 2026-10-17T22:44:07Z | 31 |
| <a id="run-39076400355"></a>39076400355 | checks | push | `e-fb-auto` | (not in the rewritten history) | success | 2026-10-17T22:46:14Z | 43 |
| <a id="run-39087074892"></a>39087074892 | checks | push | `worktree-sp2c-humanized-wheel` | c0ba6b7016 | success | 2026-10-18T01:35:53Z | 39 |
| <a id="run-39087078529"></a>39087078529 | checks | pull_request | `worktree-sp2c-humanized-wheel` | c0ba6b7016 | success | 2026-10-18T01:35:57Z | 34 |
| <a id="run-39087244341"></a>39087244341 | checks | push | `worktree-sp2c-humanized-wheel` | 1d98772278 | success | 2026-10-18T01:38:50Z | 45 |
| <a id="run-39087247280"></a>39087247280 | checks | pull_request | `worktree-sp2c-humanized-wheel` | 1d98772278 | success | 2026-10-18T01:38:53Z | 43 |
| <a id="run-39087321453"></a>39087321453 | checks | push | `main` | 67e2097dc0 | success | 2026-10-18T01:40:11Z | 43 |
| <a id="run-39087321528"></a>39087321528 | build-verify | push | `main` | 67e2097dc0 | success | 2026-10-18T01:40:11Z | 348 |
| <a id="run-39087373701"></a>39087373701 | checks | push | `e-fb-auto` | 44cb39c38e | success | 2026-10-18T01:41:02Z | 50 |
| <a id="run-39106017961"></a>39106017961 | checks | push | `e-fb-auto` | 1540d312c3 | success | 2026-10-18T06:59:52Z | 40 |

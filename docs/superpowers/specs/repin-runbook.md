# Re-pin runbook

How to move the change set to a newer Chrome stable tag, how to get the box
branch back if it is lost, and how to rebuild the build machine from nothing.

Every command here was run on 2026-10-02 for the 153 → 154 re-pin. The
durations are measured on the build box (WSL2 Ubuntu 24.04 on the build PC,
`is_component_build=true`, `symbol_level=0`), not estimated. The evidence is
`docs/superpowers/measurements/2026-10-repin.md`.

## 1. When to re-pin

The commitment in `plans/2026-10-02-long-term-roadmap.md`: **never more than
one milestone behind stable.** Chrome's stable milestone moves every two weeks,
so a re-pin is due roughly every four. A patch-level bump inside the pinned
milestone is worth it only for a security fix the fork is exposed to.

```bash
python3 scripts/repin.py target          # newest Stable on Windows
python3 scripts/repin.py check <version> # did that version ship on Stable?
```

**The Windows host decides, not `target`.** The host that captures every stock
baseline runs one specific Chrome, and a baseline must describe the version
being pinned. On 2026-10-02 `target` said `155.0.8059.26` (early stable) while
the host ran `154.0.8037.93`, so the pin went to 154. Read the host's version
first:

```powershell
(Get-Item "C:\Program Files\Google\Chrome\Application\chrome.exe").VersionInfo.ProductVersion
```

If the host is behind, either let it update (`chrome://settings/help`) and
re-read, or pin what it runs and write down when the next re-pin falls due.

## 2. The checklist

`NEW_TAG` is the chosen version, `NEW_REV` its commit, `NEW_BUILD` the third
component (`154.0.8037.93` → `8037`). `OLD_REV` and `OLD_BUILD` are the same two
things for the pin being replaced — read both out of `upstream.env` before
anything moves, because step 9 renames the retired branch after `upstream.env`
has already been rewritten:

```bash
. upstream.env                                  # CHROMIUM_REV, CHROMIUM_TAG
OLD_REV=$CHROMIUM_REV
OLD_BUILD=$(echo "$CHROMIUM_TAG" | cut -d. -f3) # 153.0.8010.36 -> 8010
```

**1. Name the target.** §1 above. Record both versions and which one won.

**2. Fetch the tag and predict the conflicts** (box, as `lang`):

```bash
cd ~/chromium/src
bash <full repo copy>/scripts/check_checkout_sync.sh      # must PASS first
time git fetch --depth=1 origin "refs/tags/$NEW_TAG:refs/tags/$NEW_TAG"   # 112 s
NEW_REV=$(git rev-parse "$NEW_TAG^{commit}")
git show "$NEW_TAG:chrome/VERSION"
git diff --stat "$OLD_REV" "$NEW_TAG" -- $(git diff --name-only "$OLD_REV" camoucrome/main -- . ':(exclude)components/camoucfg') | tail -1
```

The last line is the prediction: only those files can conflict. 2026-10-02:
upstream had changed **36 of the 89** files the stack touches.

The sync gate needs a **full** repo copy. `~/camoucrome-client` is a partial
one without `patches/` and fails there; use
`~/actions-runner/_work/camoucrome/camoucrome` or a copy of it.

**3. Rebase a copy of the branch** (38 s for the worktree, minutes for the
rebase):

```bash
cd ~/chromium/src
git branch "camoucrome/main-$NEW_BUILD" camoucrome/main
git worktree add -q ~/camourebase "camoucrome/main-$NEW_BUILD"
cd ~/camourebase
time git -c user.name=camoucrome -c user.email=camoucrome@localhost rebase --onto "$NEW_TAG" "$OLD_REV"
```

Resolve each conflict in the file, `git add`, `rebase --continue`, and keep the
commit subject (it is the patch stem). Expect `git rev-list --count
$NEW_TAG..HEAD` to equal the old count (37 on 2026-10-02).

Then fix up the one comment that names a baseline: `windows-oracle` carries
`baselines/chrome-<old short rev>-stock-ua.json` in
`chrome/renderer/chrome_content_renderer_client.cc`. Amend it **in that
commit** (`git commit --fixup` + `GIT_SEQUENCE_EDITOR=true git rebase -i
--autosquash $NEW_TAG`), never by editing `patches/` by hand.

**4. Move the main checkout and build from scratch.** Confirm no build is
running, then:

```bash
cd ~/chromium/src
git worktree remove ~/camourebase
git checkout -f --detach "$NEW_TAG"                    # 20 s
time gclient sync --revision "src@$NEW_REV" -D         # 1015 s
time gclient runhooks                                  # 6 s
cat chrome/VERSION
git checkout "camoucrome/main-$NEW_BUILD"
gn gen out/Default                                     # 13 s
gn check out/Default '//components/camoucfg:*' && gn check out/Default //content/shell:content_shell
time autoninja -C out/Default chrome content_shell components_unittests
```

The build is **6 h 10 m / 64,324 steps** from scratch. Run it detached
(`setsid nohup … &`) with a log: an ssh drop kills a foreground build.

**5. Unit suites** (49 s):

```bash
cd ~/chromium/src
F=$(grep -hoE '^TEST(_F)?\(\w+' components/camoucfg/*_unittest.cc | sed -E 's/^TEST(_F)?\(//' | sort -u | grep -v CoherenceValidatorTest | sed 's/$/.*/' | paste -sd:)
out/Default/components_unittests --gtest_filter="$F"   # SUCCESS: all tests passed
bash <repo>/scripts/run_coherence_tests.sh             # 7/7 PASS
```

A compile error here is a patch that applied but no longer matches upstream's
API. Fix it in the commit that owns the file and record it as a semantic
conflict. 2026-10-02 had none.

**6. Export and retarget** (Mac):

```bash
git checkout -b "repin/$NEW_BUILD" origin/main
python3 scripts/repin.py retarget "$NEW_TAG" "$NEW_REV"
git status --short          # the baseline renames (git mv stages them)
git diff scripts/           # the literal rewrites
```

`retarget` renames the baselines and rewrites the version literals and the
10-hex short revision. Four things it leaves to a human — note that two of them
are **corruptions to revert**, not omissions to fill in, so diff for changed
lines, not only for missing ones:

- *(omission)* a bare major ("stock Chrome 153") in a docstring: `retarget`
  matches the full tag and the 10-hex revision, never a bare build number, so
  these survive untouched and must be edited.
- *(omission)* `settings/presets/chromium-<milestone>.json` and the milestone
  fixture in `verify_sp5b_preset.py`. `retarget` does not touch `settings/`.
- *(omission)* a value **derived** from a baseline rather than captured into
  one: `settings/audio.json`'s Windows block cites the host oracle capture, and
  `retarget`'s reason for skipping `settings/` ("the captured profiles record
  the Chrome they were captured from") does not cover it.
- *(corruption to revert)* an **undated** history sentence in prose. A line that
  opens with an ISO date (`# 2026-10-02: … -> … (Chrome stable …)`) is exempt —
  `HISTORY_RE` in `repin.py`, pinned by `test_repin.py` — because its
  right-hand values are the next re-pin's "old" pair and a blind rewrite would
  turn it into a record of a re-pin that never happened. An undated sentence
  saying the same thing gets rewritten, and only a reader can tell.

Then export from the rebased branch and bring the result back:

```bash
# box
bash <repo copy>/scripts/export.sh ~/chromium/src "camoucrome/main-$NEW_BUILD"   # 1 s
```

Classify every changed line: `index` lines and hunk offsets are noise, content
lines must be exactly the resolved conflicts. 2026-10-02: 21 patches, 105
lines, of which 12 content.

**7. Verify sweep** (box, 13 min, 50 scripts):

```bash
cd ~/camoucrome-verify                 # NOT ~/camoucrome-client/scripts
for s in verify_*.py; do
  [ "$s" = verify_webrtc_ii_fakeip.py ] && continue   # RED by design
  timeout 900 ./venv/bin/python3 "$s" > "/tmp/sweep.$s.log" 2>&1
  echo "rc=$? $s $(tail -1 "/tmp/sweep.$s.log" | cut -c1-90)"
done
```

Run it from `~/camoucrome-verify`: four scripts read fixtures beside
themselves there (`sp4_media_baseline.json`, `sp4_tzlocale_baseline.json`,
`sp4_webrtc_baseline.json`, `bear.mp4`) and fail with `FileNotFoundError`
anywhere else. CI runs them there too.

Everything that compares against a stock baseline is RED until step 8. That is
expected; everything else must be green at its asserted count.

**8. Recapture the baselines.** Never edit one. Seven, not two — a single new
`window` key invalidates every captured key set (154 added
`window.requestResize`).

From a **pristine tree at the tag** (236 s to build `chrome` +
`content_shell`):

```bash
cd ~/chromium/src && git checkout -f --detach "$NEW_TAG"
autoninja -C out/Default chrome content_shell
cd <repo copy>/scripts
PY=~/camoucrome-verify/venv/bin/python3
$PY capture_ua_baseline.py --shell ~/chromium/src/out/Default/chrome > /tmp/ua_chrome1.json
$PY capture_ua_baseline.py --shell ~/chromium/src/out/Default/chrome > /tmp/ua_chrome2.json
$PY capture_ua_baseline.py > /tmp/ua_shell1.json      # content_shell, the default
$PY capture_ua_baseline.py > /tmp/ua_shell2.json
sha256sum /tmp/ua_*.json       # the two runs of each MUST match
```

`capture_ua_baseline.py` prints to stdout — always redirect, and check
`provenance.binary` and `provenance.captured_at_commit` in the result before
accepting it.

Then, still pristine, the three that each verify captures itself
(`verify_sp3a.py`, `verify_sp4_audio.py`, `verify_sp4_fonts.py` with
`--capture-baseline`; they are box-local, not committed) and the SP0 stock
surface (`navigator.hardwareConcurrency`, its descriptor, `Object.keys(window)`,
the Navigator prototype, the UA). Then rebuild the patched branch (235 s) and
score them without the flag.

From **stock Chrome on the Windows host**: `capture_host_oracle.py`,
`capture_font_metrics.py`, `capture_chrome_object.py`.

> **The box can no longer reach the Windows host.** The hardening in
> `measurements/2026-10-repin.md` removed `~/.ssh` from `lang`, and
> `winhost.py` drives the host over OpenSSH *from the box*. Until that is
> fixed, run those three on a machine that can reach the host (the Mac, with
> `winhost.powershell` replaced by a stub that sends each script through the
> sshgate MCP server) and carry the JSON back. sshgate refuses a command
> containing a newline, so a script must arrive gzip+base64 on one line; a long
> blob can be corrupted in transit, so split it into chunks of about 500
> characters, write each to its own file, and **check each chunk's sha256 on
> arrival** before concatenating.

Read every moved leaf before accepting the capture, and dispositon each one:
the re-pin explains it, or it is a finding with a reason in the code and a
backlog entry. Then the gate for a baseline renamed but never recaptured:

```bash
git diff -M --summary origin/main -- baselines | grep '(100%)'   # must print nothing
```

**9. Switch the branch names and close the gates** (box, then Mac):

```bash
cd ~/chromium/src
git branch -m camoucrome/main "camoucrome/main-$OLD_BUILD"   # e.g. camoucrome/main-8010
git branch -m "camoucrome/main-$NEW_BUILD" camoucrome/main
git checkout camoucrome/main
bash <repo copy>/scripts/export.sh ~/chromium/src        # second export
git diff --name-only -- additions patches settings       # MUST be empty
bash <repo copy>/scripts/check_checkout_sync.sh          # PASS, 41 files
python3 scripts/gen_keys.py --check
python3 scripts/check_additions_build.py
python3 scripts/gen_fontconfig.py --check
python3 scripts/repin.py check "$NEW_TAG"
```

The gate is `git diff --name-only`, **not** `git status --porcelain`: status
counts the re-pin's own staged changes too and reads non-zero even when the
export is idempotent.

**10. Commit, PR, CI.** Update the pin where it is stated: `CLAUDE.md` (the pin
paragraph, the retired-branch sentence, the `baselines/` row), `README.md`, and
the roadmap's "Where the project stands". The PR body carries the prediction
against the actual conflict count, the timing table, both sweep summaries, and
step 9's gate output. After the merge, `build-verify` runs on `main` by itself.

## 3. What a re-pin costs

| phase | duration |
|---|---|
| Fetch the tag | 112 s |
| Worktree for the rebase copy | 38 s |
| `gclient sync` + `runhooks` | 1021 s |
| `gn gen` + `gn check` | 16 s |
| **Build from scratch** (`chrome`, `content_shell`, `components_unittests`) | **22,215 s — 6 h 10 m, 64,324 steps** |
| Unit suites + coherence | 49 s |
| Export | 1 s |
| Verify sweep (50 scripts) | 13 min |
| Pristine build at the tag | 236 s |
| Baseline captures | 39 s |
| Rebuild the patched branch | 235 s |
| Second export + the five gates | under 1 min |

**About 7 h 40 m of machine time**, 80% of it the one from-scratch build. One
overnight run on this hardware. The human time is the conflict resolution, the
baseline reading, and the write-up.

## 4. Recovering the branch

If `camoucrome/main` is lost (a `gclient sync` that moved HEAD, a pruned
worktree), rebuild it from the repository:

```bash
bash <repo copy>/scripts/rebuild_branch.sh "$HOME/chromium/src" "$HOME/camoudrill" camoucrome/drill
cd ~/chromium/src
git diff camoucrome/main camoucrome/drill | wc -l     # the proof: 0
```

The worktree directory must be **absolute** and must not exist; the branch must
not exist. The script is atomic: it builds on a temporary branch and renames it
at the end, so an interruption or a failing patch leaves no branch and no
worktree behind, and a rerun works. A worktree checkout of a Chromium tree
takes minutes — run it detached and read the log.

The two branches have different commit counts (the rebuilt one has one commit
per patch; the real one also has commits that only touch
`components/camoucfg`). **The trees must be identical**: `difflines=0`. A
non-zero value means the repo cannot reproduce what was built — stop and find
the content that exists only on the box.

## 5. Recovering the machine

In order. Durations are what this box took.

1. **WSL2 + Ubuntu 24.04** on the Windows host. Then `/etc/wsl.conf` with
   `systemd=true`, `[interop] enabled=false`, `appendWindowsPath=false`,
   `[automount] enabled=false`; `wsl --shutdown`; and **start the scheduled
   task `CamouWslKeepAlive`** afterwards, or the distro stops when the last
   `wsl` call returns and the runner goes offline.
2. **User `lang`, no sudo.** No `NOPASSWD` entry; `lang` in no group but its
   own. The owner keeps root through `wsl -d Ubuntu-24.04 -u root`.
3. **`depot_tools`** in `~/depot_tools` (1.2 GB), on `PATH`.
4. **The Chromium checkout** (69 GB with `out/Default`):
   `fetch --nohooks chromium`, `git checkout -f --detach <pin>`,
   `gclient sync --revision src@<pin> -D`, `gclient runhooks`.
5. **The branch**: `rebuild_branch.sh` (§4).
6. **`gn gen out/Default`** with `settings/build-args.gn` (component build,
   `symbol_level=0`, and the proprietary-codec pair).
7. **The build**: `autoninja -C out/Default chrome content_shell
   components_unittests` — 6 h 10 m from clean, 11 GB in `out/Default`.
8. **The verify environment** `~/camoucrome-verify` (463 MB): a Python 3.12
   venv with `patchright` 1.62.3, `playwright` 1.55.0 and `pytest`, plus the
   `verify_*.py` and `capture_*.py` copies, the fixtures beside them
   (`sp4_media_baseline.json`, `sp4_tzlocale_baseline.json`,
   `sp4_webrtc_baseline.json`, `bear.mp4`) and `baselines/`.
9. **The driver** `~/camoucrome-driver` (14 MB): the `patchright-core` driver
   directory and a Node binary (v24.18.1), reached through
   `PLAYWRIGHT_NODEJS_PATH`.
10. **The client tree** `~/camoucrome-client` (46 MB): `client/`, `settings/`,
    `baselines/`, `scripts/`, `fonts/` (12 families) and `upstream.env`, all
    rsynced from the repo exactly as `build-verify.yml`'s "sync the client
    tree" step does. Go 1.22.2 for the Go client tests.
11. **The runner** `~/actions-runner` (716 MB): as root `./svc.sh stop` and
    `uninstall`; as `lang` remove `.runner`, **`.runner_migrated`**,
    `.credentials`, `.credentials_rsaparams`, then `./config.sh --unattended
    --url <repo> --token <one-hour token> --name buildpc-wsl --labels
    buildpc-wsl --replace`; as root `./svc.sh install lang` and `./svc.sh
    start`. Leaving `.runner_migrated` in place makes `config.sh` refuse with
    "already configured".

## 6. What is not in the repo

| path | size | how to get it back |
|---|---|---|
| `~/chromium` | 69 GB | §5.4 — `fetch` + `gclient sync` at the pin |
| `~/chromium/src/out/Default` | 11 GB | §5.7 — rebuild, 6 h 10 m |
| `~/depot_tools` | 1.2 GB | clone from upstream |
| `~/actions-runner` | 716 MB | §5.11 — re-download and re-register |
| `~/camoucrome-verify/venv` | 463 MB | `python3 -m venv` + the pins in §5.8 |
| `~/camoucrome-driver` | 14 MB | the patchright driver + Node |
| `~/camoucrome-client` | 46 MB | rsync from the repo (CI does it every run) |
| `~/camoucrome-verify/baselines/*` not in `git ls-files baselines` | small | recapture: `content_shell-sp3a-stock-canvas.json`, `content_shell-sp4audio-stock.json`, `content_shell-sp4fonts-stock-keys.json` from a pristine `content_shell` at the pin with each verify's `--capture-baseline` |
| `~/camoucrome-verify/sp4_*_baseline.json`, `bear.mp4` | small | `verify_sp4_media.py`, `verify_sp4_tzlocale.py`, `verify_sp4_webrtc.py` with `--capture-baseline`; `bear.mp4` is a Chromium test asset (`media/test/data/bear.mp4`) |
| The GitHub runner registration token | — | generated per registration, never stored |

Everything else under `~` on this box is scratch from earlier slices
(`measure_*.py`, `probe_*.py`, old `camoucrome-cs*` copies, `sweeplogs`) and is
not needed to rebuild anything.

## 7. The Windows tree

`D:\camou-win\chromium\src` (host side; **not reachable from WSL**, whose
automount is off — run `git` on the host, PowerShell) is a second Chromium
checkout with the fork's native Windows build in `out\Release`. Measured
2026-10-03:

- **State**: HEAD `507c6ee3e2` (the 153 pin), **no commits above it**, no
  stashes. The change set is a bare working tree: 89 patched files staged
  (`git apply --3way` stages) and 41 untracked files (`components/camoucfg/`).
  `git diff --cached --stat`: 89 files, 3020 insertions, 114 deletions.
- **Is anything in it that the change set does not explain?** Compared by path
  against the change set at `3d78ae2` (the last commit on the 153 pin: the 89
  unique `+++ b/` targets of the 32 `patches/series` entries, plus the 40
  `additions/camoucfg/` files mapped to `components/camoucfg/`, plus the
  `settings/invariants.json` that `apply.sh` copies to
  `components/camoucfg/invariants.json`): 130 paths expected, 130 dirty, **no
  path in either direction unexplained**. The comparison is by path only;
  file contents were not diffed against the patches.
- **Not in the source tree**: `out\Release\args.gn` line 19 is
  `disable_fieldtrial_testing_config = true`. A re-point carries the GN args
  across, not only the patches.
- **Shell**: `C:\Program Files\Git\bin\bash.exe` and
  `C:\Program Files\Git\usr\bin\bash.exe` both exist (Git for Windows
  2.51.2). The `bash` on the host `PATH` is `C:\WINDOWS\system32\bash.exe`,
  the WSL launcher — call Git Bash by its full path. Whether `apply.sh` /
  `rebuild_branch.sh` run under it is **not yet measured**.
- **Ruling**: the tree is re-pointed at the 2026-10-20 re-pin, not at every
  milestone. Before discarding it, re-run the path comparison above: the
  tree currently holds nothing the repo lacks, and a later hand edit would
  show as a path outside the change set. `D:\camou-win\camoucrome` is a stale
  clone on a retired branch; do not fetch from or push from it.

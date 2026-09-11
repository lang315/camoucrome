# SP6b packaging (A5 #1, #4, #5) — 2026-09-10

Roadmap A5. SP6 §4.4: read GN's runtime-deps list, ship a portable archive,
no installer, no launcher binary. §4.2: stamp the source commit, refuse a
release assembled from mismatched stamps.

## 1. What ships and how it is built

`settings/release-args.gn` is the release shape: `build-args.gn`'s three
lines plus `is_component_build = false`, `is_debug = false`, symbols off,
`use_remoteexec = false`, `enable_nacl = false`. Not `is_official_build`:
PGO/LTO multiplies build time and changes nothing page-visible. The dev
loop (`out/Default`, component build) is not what ships and
`scripts/package.py` refuses it.

`scripts/package.py <src> --out out/Release --platform linux-x64` runs
`gn desc <out> //chrome:chrome runtime_deps` (transitive, GN-computed, so a
new dependency cannot be missed silently), refuses a listed file that is
not on disk (an unfinished build), refuses a `chrome/VERSION` that is not
`upstream.env`'s tag (version honesty), copies every dep into
`dist/camoucrome-<version>-<platform>/` (source-tree deps under `src/`),
adds `launcher.json` and `presets/`, writes `camoucrome-release.json`
(version, tag, revision, change-set commit, branch tip, `args.gn`, dep
count, time) into the archive and beside it, then packs `.tar.xz`
(`.zip` for `win-*`). `package.py --check dist/*.release.json` refuses
stamps that disagree on version, tag, revision, change-set commit or
branch tip: one release, one commit, every platform.

Unit (`scripts/test_package.py`, a fake tree with a `deps.txt` in place of
`gn desc`): staging copies every dep and the two extras, the stamp's
fields, tar.xz and zip, and the three refusals plus the stamp check.

## 2. Cheap CI (`.github/workflows/checks.yml`, A5 #4)

Everything that needs no Chromium checkout: `check_additions_build.py`,
`gen_keys.py --check`, `patches/series` names every patch once and every
patch is in it, the settings JSON parse and every invariant key is a
registered key, `bash -n` on every script, the Python client and packager
tests, the Go client tests. Full builds stay on the box until a release
cadence exists; a patch-applies-clean check needs a checkout and is not in
CI.

## 3. The first archive (box, `out/Release`, 2026-09-11)

Build: `settings/release-args.gn` in `out/Release`, `autoninja chrome`, 6 ×
55 min chunks (62421 steps; the last chunk 3354 steps in 30 min; the
`chrome` binary 519 MB, `symbol_level=0`). `gn desc out/Release
//chrome:chrome runtime_deps` is not a manifest as printed, and the first
run staged 10 files — three things measured, each now in `package.py` with
a test:

| what gn printed | lines | handling |
|---|---|---|
| its build-arg WARNING block, on stdout, ahead of the paths (`enable_nacl` no longer exists in 153; dropped from `release-args.gn`) | 9 | a path line is one whitespace-free token not starting with `^` — out-dir paths come **bare** (`chrome`, `locales/en-US.pak`; the first filter wanted `./` and kept 10 lines), source-tree ones `../../` |
| `gen/third_party/devtools-frontend/src/front_end/**` — the frontend sources the devtools targets mark as `data` for their own tests; the shipped copy is `resources.pak` (upstream's `installer.py` ships none of them) | 4803 | pruned |
| `pyproto/google/protobuf/**` — protobuf Python bindings a build tool lists as data | 36 | pruned |
| duplicates (`resources.pak`, `snapshot_blob.bin`, `v8_context_snapshot.bin`, two angledata jsons) | 5 | once each |

What remains: **254 files** (228 `locales/*.pak`, the binary, 9 `.so`,
crashpad handler, 4 pak, icudtl, two snapshots, angledata, the three
preloaded data dirs), all present on disk; `chrome_crashpad_handler` is
staged but SP7 keeps the reporter off. Staging 651 MB; archive
`camoucrome-153.0.8010.36-linux-x64.tar.xz` **155,904,424 bytes (149 MiB)**,
205 s to stage+pack, 8 s to extract. Stamp:
`chromium_tag 153.0.8010.36`, `chromium_rev 507c6ee3e2…`, `changeset_commit
dfe16b8` (passed by `--changeset-commit`: the box's copy is a tar extract,
not a checkout), `branch_tip 04e1dc8ff6`, the eleven `args.gn` values,
`runtime_deps 259` (the pre-dedupe count; the next run says 254).
`--check` on the one stamp: agree. RED first: `--out out/Default` was
refused ("refusing a component build").

**Self-contained, measured on the extracted tree, not the build dir:**

- DevTools opens from the archive: `devtools://devtools/bundled/devtools_app.html`
  loads (title `DevTools`, body text "DevTools is undocked"). RED: with
  `resources.pak` renamed the binary logs `Failed to load …/resources.pak`
  and the check never prints OPEN — so the pak, not the pruned `gen/`
  tree, is what carries the front end.
- The driver-contract sweep with `CAMOU_EXE=<extracted>/chrome`:
  `ALL_PASS`, six rows (Python/Go/Node × stock/patchright; the stock rows
  RED as expected), C4 argv 11 = the contract's set, 1223 own names, C5
  patchright −1 / +0 / +2 %. A missing `.pak`, `icudtl.dat` or `libEGL.so`
  fails here and nowhere else.

Not measured: a host without the build box's system libraries (the
archive carries no libc/GTK; the same is true of upstream's tarball), and
the `.zip` path on a real Windows tree.

**Second cut, 2026-09-11.** `out/Release` relinked with `d-pointer-touch`
and `android-claims-touch` (104 steps, 2 min), packaged at
`changeset_commit 58b59ab` / `branch_tip bc91762ccd`: 254 files,
155,877,928 bytes, 206 s, extract 8 s, `--check` ok; DevTools opens from
the extracted tree, six-driver sweep `ALL_PASS` on its `chrome`.

**Third cut, 2026-09-11, with the font bundle.** `out/Release` relinked
with `fonts-iii-alias` (105 steps); packaged at `changeset_commit 9474119`
/ `branch_tip 1474cae191` with `fonts/` (10 OFL families, 40 MB) and
`settings/fontconfig/` in the layout the launcher contract names: **300
files, 181,505,248 bytes (173 MiB)**, 218 s, extract 9 s, stamp `fonts:
true`, `--check` ok. On the extracted tree: `verify_fonts_bundle.py` in
archive mode (`CAMOU_EXE=<extracted>/chrome`, no `--fonts-dir`: the
launcher finds `fonts/` beside the executable) **4/4**, DevTools opens,
six-driver sweep `ALL_PASS`. The first attempt at this cut shipped no
fonts because the box's copy of `package.py` predated the fonts code — the
stamp's `fonts: false` said so; the doc's layout rule ("copy the packager
the repo has") is what caught it.

**Fourth cut, 2026-09-11, after review.** `out/Release` relinked with the
amended `fonts-iii-alias` (one-hop alias; 49 steps, 48 s — an incremental
release relink after one Blink file is under a minute, the 30+ min figure
was the first link) and packaged at `changeset_commit 65014e08bf` /
`branch_tip 85dfb6b3fc`: **300 files, 181,546,064 bytes (173 MiB)**,
extract 9 s, stamp `fonts: true`, `--check` ok. On the extracted tree:
`verify_fonts_bundle.py` in archive mode **6/6** (F6 worker parity, F7 the
cyclic map that crashed the third cut's renderer), DevTools opens,
six-driver sweep `ALL_PASS`. The third cut is superseded: its chrome
recurses on a cyclic hand-written `fonts:alias` and its manifest carries
the six developer fonts.

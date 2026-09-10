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

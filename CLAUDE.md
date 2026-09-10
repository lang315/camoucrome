# CLAUDE.md

Guidance for Claude Code (and any agent) working in this repository.

## What this is

Camoucrome is an anti-detect fork of **Chromium** — the Chromium counterpart to
[Camoufox](https://github.com/lang315/camoufox) (a Firefox fork). This repo is
**not the Chromium source**. It is a change set — whole new files in `additions/`
plus diffs in `patches/` — that `scripts/apply.sh` lays onto a pristine Chromium
checkout to produce a fingerprint-spoofing browser.

The change set is generated against Chromium **`507c6ee3e2`, the Chrome stable
tag `153.0.8010.36`** (`upstream.env` holds the full SHA and the tag;
`scripts/apply.sh` refuses any other HEAD). The pin is a *stable tag*, not
`main` and not a branch head, so the fork reports a version real users have;
re-pin to the newest stable tag whenever chromiumdash's stable milestone moves
(`docs/superpowers/measurements/2026-09-09-sp6a-version-honesty.md`). The
build box's checkout is on branch `camoucrome/main-8010` (the exported branch);
`camoucrome/main` is the retired 0e8d4a9268 branch, `a727b57805` was never an
upstream revision.

## The defining constraint (never violate)

**All fingerprint spoofing is implemented in C++ at the Blink/browser level,
never by injecting JavaScript into the page.** A page must not be able to observe
that a value was substituted:

- Accessors keep reporting `[native code]` (`...get.toString()` unchanged).
- `Object.keys(window)` is byte-identical to a stock build.
- A surface exposed to both a window and a worker reports identical values in
  both (worker parity — see conventions rule 3).

If a surface can only be reached from JS, say so and treat it as an open problem;
do not quietly inject. This is inherited from Camoufox and is the whole reason
the project exists.

## Read first

- **[`docs/superpowers/specs/00-conventions.md`](docs/superpowers/specs/00-conventions.md)**
  — the authoritative architecture decisions every spec assumes. Non-negotiable
  rules, the config API shape, the build environment, and (most importantly) the
  catalogue of ways a check can report success while measuring nothing. Read it
  before writing or verifying anything.
- **[`docs/superpowers/plans/2026-09-02-followon-roadmap.md`](docs/superpowers/plans/2026-09-02-followon-roadmap.md)**
  — slice ordering and per-slice status (shipped / partial / open); each slice's
  residual detail lives in its own measurement doc, not in the roadmap.

## Repository layout

| Path | Contents |
|---|---|
| `additions/` | whole new files, **copied** into the Chromium tree verbatim (esp. `additions/camoucfg/` — the C++ config layer) |
| `patches/` | diffs against files that **already exist** in Chromium |
| `settings/` | `invariants.json` (cross-surface invariant registry, SP5) and `build-args.gn` (canonical GN args, incl. the proprietary-codec pair) |
| `scripts/` | `apply.sh` (the applier) and `verify_*.py` (per-slice browser verifications) |
| `docs/superpowers/{specs,plans,measurements}/` | design specs, implementation plans, and per-slice surface measurements |
| `baselines/` | stock reference captures; three are committed (`git ls-files baselines`), the rest are build-host-local and regenerable |

New files go in `additions/`, edits to existing files go in `patches/`. This
split (from Camoufox, held across ~64 patches) keeps rebase conflicts confined to
the small diffs.

## The config layer (`//components/camoucfg`)

One GN target reachable from the browser, renderer, and GPU processes. Blink
reaches it through **per-header** `+components/camoucfg/<header>.h` grants in
`third_party/blink/renderer/DEPS` (least privilege; a new header needs a new
line).

- **Getters** — `GetString/GetUint32/GetInt32/GetDouble/GetBool(scope, key)` →
  `std::optional<...>`. Every getter takes a `ConfigScope` first arg. Get it with
  `camoucfg::ScopeFor(execution_context)` (or `ScopeFor(nullptr)` off the main
  thread); today every scope resolves to the same process-global config, parsed
  once into a `base::NoDestructor<base::DictValue>` (immutable after parse, so
  worker/render-thread reads are safe). **Never write a getter that omits the
  scope.**
- **Keys** are declared in `settings/keys.json` (name, key, type, doc) and
  `additions/camoucfg/keys.h` is **generated** from it by `scripts/gen_keys.py`
  — never edit the header. Adding a key: add the JSON entry, run the script,
  add the name to the `declared` set in `keys_unittest.cc`, commit all three.
  `scripts/gen_keys.py --check` fails on a stale header, a `declared` set that
  disagrees with the JSON, or a string literal in the key position of any
  `camoucfg::Get*` / `HasKey` call in `patches/` or `additions/`.
- **Naming** — a **dot** mirrors a JS property path exactly
  (`navigator.userAgent`, `window.outerHeight`); a **colon** names a synthetic
  namespace (`canvas:seed`, `webGl:renderer`). A value derived from another gets
  **no key** (an independent override only creates incoherence).
- **The SP0 hook pattern** — read the real value first; apply the config override
  only when the key is present; no-op when absent (conventions rule 5). Fall back
  to the real value, never a hardcoded placeholder. Apply configuration **last,
  after any `probe::Apply*Override` hook**, so the configured value wins without
  breaking DevTools emulation (never delete a probe call).

## Build & verify

Chromium builds on the user's Windows PC inside **WSL2 (Ubuntu 24.04)** as
non-root user `lang` at `~/chromium/src`, out dir `out/Default`
(`is_component_build=true`, `symbol_level=0`), so an incremental rebuild after one
Blink file is 1–3 min. The verification target is **`content_shell`** (small,
still exposes the DevTools protocol), not `chrome`.

Repo lives on the Mac; the build and every `verify_*.py` run on the WSL box
(`ssh buildpc`). Config reaches a build through the environment: `CAMOU_CONFIG`
holding a JSON object (or `CAMOU_CONFIG_1..N` concatenated in order, for
argv-length limits). `CAMOU_CONFIG_STRICT=1` turns unparseable config into a
startup abort instead of a silent fall-back to real values.

- Apply the change set: `scripts/apply.sh <chromium-src>` (copies `additions/`,
  then `git apply --3way` each patch in `patches/series` order — semantic, not
  alphabetical).
- The change set is **exported, not hand-extracted**: `~/chromium/src` on the
  build box is checked out on branch `camoucrome/main`, one commit per patch
  above the pin, commit subject == patch stem. `scripts/export.sh
  <chromium-src>` regenerates `patches/`, `patches/series`, `additions/` and
  `settings/invariants.json` from it; the gate is `git status --porcelain
  additions patches settings` empty afterwards. The loop: edit and build in
  `~/chromium/src`, verify, `git commit` there with the patch stem as subject
  (amend the slice's own commit when revising), then export — never a
  `git diff` pasted into `patches/`. `scripts/check_checkout_sync.sh` fails
  while the build tree has uncommitted or untracked edits, which is the state
  between "edited" and "committed". `scripts/rebuild_branch.sh` recreates the
  branch from the repo if it is ever lost (`camoucrome/main-0e8d` is the
  retired branch on the old pin).
- Browser verifications are `scripts/verify_*.py`, run under
  `~/camoucrome-verify/venv/bin/python3` (bare `python3` lacks `playwright`).
  They drive `content_shell` over CDP via `lib_shell.session(config, [js...])`.
- Unit tests: the `components_unittests` target. `--gtest_filter='Camoucfg*'`
  matches **1 of 17** suites (only `CamoucfgKeysTest`) — filter by suite name.
  `CoherenceValidatorTest.*` cannot run in one invocation: config is read once
  per process and cached, so one process can only latch one `CAMOU_CONFIG`. Use
  `scripts/run_coherence_tests.sh` (one process per case, asserts 6/6).
- Pre-flight, both cheap and both exist because the omission already happened:
  `python3 scripts/check_additions_build.py` (every `additions/camoucfg` source
  must be in its `BUILD.gn` `sources` — `coherence_validator.cc` sat there
  uncompiled for a full build cycle while everything reported green) and
  `bash scripts/check_checkout_sync.sh` (repo↔checkout byte drift; happened
  twice in one day, both found by accident).

**`content_shell` is not a complete browser, and the gap is load-bearing.**
Anything under `//chrome` is absent (`window.chrome` has no installer linked).
Worse, it sometimes **reimplements** a surface rather than omitting it —
`GetUserAgentMetadata()` is rebuilt in shell code with `platform="Unknown"` and
never calls the patched `embedder_support` producer, so a patch there is
invisible in `content_shell`. Before planning a verification, confirm the binary
under test actually **calls the function being patched** (grep the patched
symbol's callers, not the feature name).

## The dominant failure mode: a check that measures nothing

This is the project's most expensive class of bug — read 00-conventions.md's
table of them. The discipline:

- **RED-first.** Before trusting a verification, make it **fail on purpose** and
  confirm it says so. A GREEN run carries almost no information until you know
  what it measured. Assert the **expected count** or the **expected failure**, not
  just exit 0.
- **A precise comment beside an imprecise guard is a defect report.** The cheapest
  detector found here is reading a fix's own comment against the fix.
- **Read the brief against the tree before running anything** — the cheapest place
  this project finds defects.
- Confirm the build reports **NON-ZERO steps**; a stale `.o` gives a silent
  0-step no-op with stale results.

## Working with patches (traps that cost real time)

- **Revising a patch must re-extract EVERY path the original touched** — including
  its `BUILD.gn` dep line. Dropping a `//components/camoucfg` dep from a re-cut
  patch passes every green signal (the checkout already had the dep) and only
  fails on a fresh `apply.sh` + `gn check`.
- **To extract just your new edits when the file already belongs to an earlier
  patch:** snapshot the pre-edit worktree with `BASE=$(git stash create)` (no
  branch change), edit, then `git diff $BASE -- <files>` — this excludes the
  earlier patch's hunks. Gate the result: the earlier patch's added lines must not
  reappear in yours.
- **Round-trip every patch before trusting it:** revert the whole touched
  directory to pristine (`git checkout HEAD -- <dir>/`), `git apply --3way` the
  full patch sequence, then `gn check` the target ("Header dependency check OK"),
  rebuild, and re-run the verify. A single-file re-extraction can silently drop a
  cross-file dep.
- Two git behaviours mislead: `git apply --3way` **stages** its result, so
  `git diff --stat` reads empty afterwards — use `--cached`. And
  `git checkout -- <file>` reverts to the **staged** version if staged — use
  `git checkout HEAD -- <file>` for pristine.
- **Neither `gn check` nor `checkdeps.py` runs on a `.cc`-only build.** Run both
  explicitly whenever a change adds a cross-component include; a green build is not
  evidence.

## Non-negotiable rules (from 00-conventions.md §"Non-negotiable rules")

1. No JavaScript injection into page-visible scopes.
2. Native-looking accessors; `Object.keys(window)` unchanged vs stock.
3. Worker parity for any surface exposed to both.
4. **Coherence over coverage** — a spoofed value that contradicts another spoofed
   value is worse than not spoofing at all. SP5's invariant registry
   (`settings/invariants.json`) exists to catch these; extend it when a slice adds
   a numeric-range or cross-surface key.
5. Fall back to the real value when config is absent (with the behavioral-spoof
   refinement and the fail-closed exception noted in the conventions).

Bad config must never crash a renderer — a crash is itself a fingerprint.
